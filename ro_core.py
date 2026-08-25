"""ROItemSearchApp 共用 Python 核心（Stage 3）。

此模組刻意不依賴 PySide6 / FastAPI，Desktop 與 Web 都可以直接匯入。
Stage 3 為 Lua 裝備 parser 加入明確的 dependency container，並讓遷移腳本
可以把目前 Desktop 的 parser 實作搬進同一個模組。
"""

from __future__ import annotations

# 手動維護的共用核心版本；每次 ro_core.py 計算邏輯變更時都要遞增版本。
RO_CORE_VERSION = "v0.21.74"

from dataclasses import dataclass, field
import ast
from collections import defaultdict
import math
import os
import re
from typing import Any, Iterable


# =========================================================
# 核心狀態容器
# =========================================================


@dataclass
class CalculationContext:
    """Desktop 與未來 Web 呼叫共用的單次計算可變狀態。

    Stage 2 刻意讓 ``variables`` 保持彈性，讓既有 Desktop 名稱
    （如 ``total_DEX``、``base_STR`` 等）可以在不大幅重寫的情況下遷移。
    可變的裝備 / 技能 map 改成明確欄位，使 Lua parser 不再需要直接存取
    ``ItemSearchApp`` 模組全域變數。

    遷移期間 Desktop 可以直接以參照方式傳入現有 dict；
    Web 則應為每個 request 建立新的 context。
    """

    get_values: dict[int, Any] = field(default_factory=dict)
    refine_inputs: dict[int, int] = field(default_factory=dict)
    grade: Any = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)

    enabled_skill_levels: dict[int, int] = field(default_factory=dict)
    used_skill_levels: dict[int, bool] = field(default_factory=dict)

    weapon_level_map: dict[int, int] = field(default_factory=dict)
    armor_level_map: dict[int, int] = field(default_factory=dict)
    weapon_type_map: dict[int, int] = field(default_factory=dict)
    armor_weapon_map: dict[int, Any] = field(default_factory=dict)
    weapon_atk_map: dict[int, int] = field(default_factory=dict)
    weapon_matk_map: dict[int, int] = field(default_factory=dict)
    slot_item_id_map: dict[int, int] = field(default_factory=dict)

    equipped_items: dict[int, int] = field(default_factory=dict)
    pure_jobs: Any = field(default_factory=list)

    def get(self, name: str, default: Any = 0) -> Any:
        return self.variables.get(name, default)

    @classmethod
    def from_state(cls, state: Any) -> "CalculationContext":
        """由類 mapping 的舊版 state 物件建立 context。

        主要作為 Desktop 遷移橋接。可變 dict 刻意*不複製*：context 直接指向
        現有 dictionary，在把 parser 移到明確狀態邊界後方的同時，保留目前
        Desktop 的既有副作用。
        """
        try:
            getter = state.get
        except AttributeError as exc:
            raise TypeError("state must provide .get(name, default)") from exc

        stat_names = (
            "STR", "AGI", "VIT", "INT", "DEX", "LUK",
            "POW", "STA", "WIS", "SPL", "CON", "CRT",
        )
        variables: dict[str, Any] = {
            "target_element": getter("target_element", 0),
            "skill_focus_AGI": getter("skill_focus_AGI", 0),
            "skill_focus_DEX": getter("skill_focus_DEX", 0),
            "total_AGI": getter("total_AGI", 0),
            "total_DEX": getter("total_DEX", 0),
        }
        for stat in stat_names:
            for prefix in ("base", "job", "equip", "base_equip", "total"):
                key = f"{prefix}_{stat}"
                variables[key] = getter(key, 0)

        def dict_ref(name: str) -> dict:
            value = getter(name, None)
            return value if isinstance(value, dict) else {}

        return cls(
            variables=variables,
            enabled_skill_levels=dict_ref("enabled_skill_levels"),
            used_skill_levels=dict_ref("Use_skill_levels"),
            weapon_level_map=dict_ref("global_weapon_level_map"),
            armor_level_map=dict_ref("global_armor_level_map"),
            weapon_type_map=dict_ref("global_weapon_type_map"),
            armor_weapon_map=dict_ref("global_armor_weapon_map"),
            weapon_atk_map=dict_ref("global_weapon_atk_map"),
            weapon_matk_map=dict_ref("global_weapon_matk_map"),
            slot_item_id_map=dict_ref("slot_item_id_map"),
            pure_jobs=getter("GetPureJob", []) or [],
        )

    def bind_inputs(
        self,
        *,
        get_values: dict[int, Any] | None = None,
        refine_inputs: dict[int, int] | None = None,
        grade: Any = None,
    ) -> "CalculationContext":
        """綁定目前這次呼叫的輸入，並回傳 ``self`` 方便串接。"""
        if get_values is not None:
            self.get_values = get_values
        if refine_inputs is not None:
            self.refine_inputs = refine_inputs
        if grade is not None:
            self.grade = grade
        return self


class CoreDependencyError(RuntimeError):
    """Lua parser 被呼叫但缺少必要共用 dependency 時拋出的例外。"""


@dataclass
class CoreDependencies:
    """Lua 裝備 parser 使用、以唯讀為主的 dependency。

    ``CalculationContext`` 負責每個 request 的可變計算狀態。此物件刻意分離，
    只存放一般可跨 request 共用的查表 map / registry。Desktop 遷移期間，
    這些值直接指向既有 ItemSearchApp 物件；Web 則可以在不匯入 PySide6 或
    ItemSearchApp 的情況下建立同樣的 container。
    """

    values: dict[str, Any] = field(default_factory=dict)
    function_defs: dict[str, Any] = field(default_factory=dict)

    def require(self, name: str) -> Any:
        if name not in self.values:
            raise CoreDependencyError(
                f"Lua parser 缺少 dependency: {name}. "
                "請透過 CoreDependencies(values=...) 提供，或由 Desktop bridge 建立。"
            )
        return self.values[name]

    def register_function(self, name: str, desc: str, args: Any, vars: Any = None) -> None:
        """Core 版 Desktop register_function()，保留原本語意。"""
        if name in self.function_defs:
            return
        self.function_defs[name] = {
            "desc": desc,
            "args": args,
        }

    def missing(self, names: Iterable[str]) -> list[str]:
        return sorted(name for name in names if name not in self.values)

    def validate(self, names: Iterable[str]) -> None:
        missing = self.missing(names)
        if missing:
            raise CoreDependencyError(
                "Lua parser 缺少 dependencies: " + ", ".join(missing)
            )

    @classmethod
    def from_state(
        cls,
        state: Any,
        required_names: Iterable[str] = (),
    ) -> "CoreDependencies":
        """從模組全域變數或其他 mapping 橋接 Desktop 遷移資料。

        物件以參照方式保留，map 不做 deep copy。產生的 Stage 3 Desktop wrapper
        只用它來橋接既有共用資料。
        """
        try:
            getter = state.get
        except AttributeError as exc:
            raise TypeError("state must provide .get(name, default)") from exc

        sentinel = object()
        values: dict[str, Any] = {}
        for name in required_names:
            value = getter(name, sentinel)
            if value is not sentinel:
                values[name] = value

        defs = getter("function_defs", None)
        if not isinstance(defs, dict):
            defs = {}

        return cls(values=values, function_defs=defs)


# 由 apply_core_stage3.py 分析目前實際使用的 parser 後填入；
# 來源是使用者目前 ItemSearchApp.py 內的實際 parser。
CORE_LUA_DEPENDENCY_NAMES: tuple[str, ...] = ('class_map', 'element_map', 'excluded_stat_names', 'race_map', 'skill_map', 'stat_name_sets', 'weapon_type_map')


@dataclass
class CoreData:
    """Desktop 與 Web process 共用、以唯讀為主的資料。"""

    items: dict[int, dict[str, Any]] = field(default_factory=dict)
    equipment_blocks: dict[int, str] = field(default_factory=dict)
    combo_blocks: dict[int, str] = field(default_factory=dict)
    skills: dict[int, Any] = field(default_factory=dict)


# =========================================================
# 素質點數計算
# =========================================================


def calculate_stat_points(level: int, job_id: int) -> int:
    """計算可用素質點數；邏輯與 Desktop 完全一致。"""
    if 4302 <= job_id <= 4308:
        pt = 48
    else:
        pt = 100

    for i in range(1, level):
        if i < 100:
            pt += i // 5 + 3
        elif i <= 150:
            pt += i // 10 + 13
        elif i <= 185:
            pt += 28 + (i - 150) // 7
        elif i < 200:
            pt += 33 + (i - 185) // 7
    return pt


def raising_stats(stat_str: str) -> int:
    """計算素質點消耗；邏輯與 Desktop 完全一致。"""
    try:
        val = int(stat_str.split("+")[0])
    except Exception:
        return 0

    pt = 0
    for i in range(1, val):
        if i < 100:
            pt += (i - 1) // 10 + 2
        else:
            pt += 4 * ((i - 100) // 5) + 16
    return pt


# === 核心去重階段 1：DESKTOP / WEB 共用規則 ===
# 這些 helper 刻意不依賴 UI；Desktop adapter 仍可保留
# 相容 wrapper，但真正的規則 / 公式只保留在這裡。
TRAIT_STAT_NAMES = ("POW", "STA", "WIS", "SPL", "CON", "CRT")


def get_total_tstat_points(level: int) -> int:
    """回傳指定 BaseLv 可用的特性素質總點數。"""
    try:
        level = int(level)
    except (TypeError, ValueError):
        return 0

    if level < 200:
        return 0

    # 保留目前與 Desktop / ROCalculator 相容的上限。
    level = min(level, 285)
    block, offset = divmod(level - 200, 5)
    return 7 + block * 19 + offset * 3


def calculate_tstat_total_used(values) -> int:
    """從 mapping 或 iterable 加總已使用的特性素質點數。

    Desktop 可以傳入 UI 文字值，Web 可以直接傳 int。無效值沿用舊版 Desktop
    行為，視為 0。
    """
    if hasattr(values, "get"):
        mapping = values
        values = (mapping.get(name, 0) for name in TRAIT_STAT_NAMES)

    total = 0
    for value in values or ():
        try:
            total += int(value)
        except (TypeError, ValueError):
            continue
    return total


def calculate_armor_refine_bonus(refine: int, armor_level: int) -> dict:
    """
    計算單一防具的精煉 DEF、RES。

    DEF 累加規則：
        +1～+4   每次 +1
        +5～+8   每次 +2
        +9～+12  每次 +3
        +13～+16 每次 +4
        +17～+20 每次 +5

    防具等級：
        1級防具：DEF 使用原始累加值，RES = 0
        2級防具：DEF 為原始累加值 × 1.2，RES = 精煉 × 2

    這是拆分前 Desktop ``get_armor_bonus`` 的同一套公式；現在由 Core 作為唯一來源。
    """
    try:
        refine = int(refine)
        armor_level = int(armor_level)
    except (TypeError, ValueError) as exc:
        raise ValueError("精煉值與防具等級必須是整數") from exc

    if not 0 <= refine <= 20:
        raise ValueError(f"精煉值必須介於 0～20，目前為：{refine}")

    if armor_level not in (1, 2):
        return {"DEF": 0.0, "RES": 0}

    # 每 4 點精煉提升一個 DEF 增量階段。
    full_groups = refine // 4
    remainder = refine % 4
    # 例如 +10：4×1 + 4×2 + 2×3 = 18。
    def_units = (
        4 * full_groups * (full_groups + 1) // 2
        + remainder * (full_groups + 1)
    )

    if armor_level == 1:
        def_bonus = def_units
        res_bonus = 0
    else:
        def_bonus = def_units * 1.2
        res_bonus = refine * 2

    return {"DEF": round(def_bonus, 1), "RES": int(res_bonus)}


# =========================================================
# 物品資料解析
# =========================================================


def parse_lub_text(
    content: str,
    existing_items: dict[int, dict[str, Any]] | None = None,
    duplicate_mode: str = "skip",
    *,
    source_name: str = "<memory>",
    verbose: bool = False,
) -> dict[int, dict[str, Any]]:
    """把 iteminfo 格式的 Lua 文字解析成既有 Desktop dictionary 結構。

    解析規則與目前 ``ItemSearchApp.parse_lub_file`` 一致。與 Desktop 函式不同，
    此處直接接受文字，因此可用於 API 與單元測試，不需要 filesystem / UI 依賴。
    """
    item_entries = re.findall(
        r"\[(\d+)\]\s*=\s*{(.*?)}(?=,\s*\[\d+\]|\s*\[\d+\]|\s*$)",
        content,
        re.DOTALL,
    )

    parsed_items = existing_items.copy() if existing_items is not None else {}

    total = len(item_entries)
    if verbose:
        print(f"📦 開始讀取 {source_name}，共 {total} 筆物品資料。")

    added_count = 0
    overwritten_count = 0
    skipped_count = 0

    for index, (item_id, body) in enumerate(item_entries, start=1):
        try:
            if verbose and (index % 1000 == 0 or index == total):
                print(f"  → 正在讀取第 {index}/{total} 筆", end="\r")

            item_id = int(item_id)
            identified_name = re.search(
                r'(?<!un)identifiedDisplayName\s*=\s*"([^"]+)"', body
            )
            kr_name = re.search(
                r'(?<!un)identifiedResourceName\s*=\s*"([^"]+)"', body
            )
            slot = re.search(r"slotCount\s*=\s*(\d+)", body)

            desc_match = re.search(
                r"(?<!un)identifiedDescriptionName\s*=\s*{(.*?)}",
                body,
                re.DOTALL,
            )
            if desc_match:
                desc_body = desc_match.group(1)
                desc_lines_raw = re.findall(r'"([^"]*)"', desc_body)
                desc_lines: list[str] = []
                for line in desc_lines_raw:
                    cleaned = line.strip()
                    # 控制碼行過濾，但保留真正空白行
                    if re.fullmatch(r"\^?[a-fA-F0-9]+", cleaned):
                        continue
                    if cleaned == "":
                        desc_lines.append("")
                    else:
                        desc_lines.append(cleaned)
            else:
                desc_lines = []

            if identified_name and kr_name and slot:
                base_name = identified_name.group(1).strip()
                slot_count = int(slot.group(1))
                display_name = (
                    f"{base_name} [{slot_count}]" if slot_count > 0 else base_name
                )
                new_item = {
                    "name": display_name,
                    "base_name": base_name,
                    "kr_name": kr_name.group(1).strip(),
                    "description": desc_lines,
                    "slot": slot_count,
                }

                if item_id in parsed_items:
                    if duplicate_mode == "overwrite":
                        parsed_items[item_id] = new_item
                        overwritten_count += 1
                    elif duplicate_mode == "skip":
                        skipped_count += 1
                        continue
                else:
                    parsed_items[item_id] = new_item
                    added_count += 1
        except Exception:
            # 保留目前 Desktop 行為：格式錯誤的資料直接略過。
            continue

    if verbose:
        print()
        print(f"✅ 完成讀取 {source_name}")
        print(f"   新增：{added_count} 筆")
        print(f"   覆蓋：{overwritten_count} 筆")
        print(f"   略過：{skipped_count} 筆")

    return parsed_items


def parse_lub_file(
    filename: str | os.PathLike[str],
    existing_items: dict[int, dict[str, Any]] | None = None,
    duplicate_mode: str = "skip",
    *,
    verbose: bool = True,
) -> dict[int, dict[str, Any]]:
    """讀取並解析 iteminfo 格式檔案。

    檔案 / UI 錯誤顯示刻意留在 Core 外，因此允許 ``FileNotFoundError``
    直接往 Desktop / FastAPI 呼叫端傳遞。
    """
    with open(filename, "r", encoding="utf-8") as file:
        content = file.read()

    return parse_lub_text(
        content,
        existing_items,
        duplicate_mode,
        source_name=os.path.basename(os.fspath(filename)),
        verbose=verbose,
    )


def resolve_name_conflicts(
    parsed_items: dict[int, dict[str, Any]],
    equipment_blocks: dict[int, str],
) -> dict[int, dict[str, Any]]:
    """只有同名且存在裝備 block 的物品才附加 Item ID。

    修改資料的語意刻意與現有 Desktop 實作一致。
    """
    affected_items = {
        item_id: parsed_items[item_id]
        for item_id in equipment_blocks.keys()
        if item_id in parsed_items
    }

    name_count: dict[str, int] = {}
    for info in affected_items.values():
        name = info["name"]
        name_count[name] = name_count.get(name, 0) + 1

    for item_id, info in affected_items.items():
        name = info["name"]
        if name_count[name] > 1:
            info["name"] = f"{name} (ID:{item_id})"

    return parsed_items


def parse_equipment_blocks(content: str, *, verbose: bool = True) -> dict[int, str]:
    """使用與 Desktop 相同的演算法解析裝備 Lua block。"""
    blocks: dict[int, str] = {}
    pattern = re.compile(r"\[(\d+)\]\s*=\s*{", re.MULTILINE)
    matches = list(pattern.finditer(content))
    total = len(matches)

    if verbose:
        print(f"📦 開始解析裝備區塊，共 {total} 筆資料")

    for i, match in enumerate(matches):
        current = i + 1
        if verbose and ((total >= 1000 and current % 1000 == 0) or current == total):
            print(f"  → 處理中 {i + 1}/{total} 筆", end="\r")

        item_id = int(match.group(1))
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)

        block_text = content[start:end].strip()
        block_text_full = "{" + block_text.rstrip(",") + "}"
        blocks[item_id] = block_text_full

    if verbose:
        print(f"\n✅ 解析完成，共 {len(blocks)} 筆裝備。")

    return blocks


# =========================================================
# Lua 裝備效果 parser（Stage 3 注入點）
# =========================================================

# apply_core_stage3.py 會把轉換後的 parser 插入在正下方。

# === STAGE 3 LUA PARSER 開始 ===
# 由 apply_core_stage3.py 從本機 Stage 2 的 ItemSearchApp.py 抽出。
def parse_lua_effects_with_variables(
    block_text,
    refine_inputs,
    get_values,
    grade,
    unit_map,
    size_map,
    effect_map,
    hide_unrecognized=False,
    hide_physical=False,
    hide_magical=False,
    current_location_slot=None,
    context=None,
    dependencies=None
):
    if context is None:
        context = CalculationContext()
    if dependencies is None:
        dependencies = CoreDependencies()
    context.bind_inputs(
        get_values=get_values,
        refine_inputs=refine_inputs,
        grade=grade,
    )
    lines = block_text.splitlines()

    # 解析裝備 Lua 前，先把外部已知的角色/裝備基礎素質帶進本次 parser。
    # base_equip_* 會在 display_all_effects() 的前置掃描階段先建立，
    # 因此第一次解析就能使用，不需要等 replace_custom_calc_content() 跑完後再算第二次。
    variables = {
        "target_element": context.get("target_element", 0),
        "skill_focus_AGI": context.get("skill_focus_AGI", 0),
        "skill_focus_DEX": context.get("skill_focus_DEX", 0),
        "total_AGI": context.get("total_AGI", 0),
        "total_DEX": context.get("total_DEX", 0),
    }
    for _stat in ("STR", "AGI", "VIT", "INT", "DEX", "LUK",
                  "POW", "STA", "WIS", "SPL", "CON", "CRT"):
        variables[f"base_{_stat}"] = context.get(f"base_{_stat}", 0)
        variables[f"job_{_stat}"] = context.get(f"job_{_stat}", 0)
        variables[f"equip_{_stat}"] = context.get(f"equip_{_stat}", 0)
        variables[f"base_equip_{_stat}"] = context.get(f"base_equip_{_stat}", 0)
        variables[f"total_{_stat}"] = context.get(f"total_{_stat}", 0)

    sfct_handled = False  # ✅ 控制是否已處理過 SubSFCTEquipAmount
    skill_delay_accum = {}
    results = []
    condition_met = True
    indent_stack = []
    weapon_level_map = variables.setdefault("__weapon_level_map__", {})

    block_stack = []  # 用來追蹤 if-elseif-else 區塊狀態
    safe_globals = {"__builtins__": None}
    safe_locals = {"math": __import__("math")}






    # 快取常用 Lua expression pattern，避免此函式被大量呼叫時重複建立正則。
    regex_cache = getattr(parse_lua_effects_with_variables, "_regex_cache", None)
    if regex_cache is None:
        regex_cache = {
            "GET": re.compile(r"get\((\d+)\)"),
            "REFINE_LOCATION": re.compile(r"GetRefineLevel\s*\(\s*GetLocation\s*\(\s*\)\s*\)"),
            "REFINE": re.compile(r"GetRefineLevel\((\d+)\)"),
            "GRADE_LOCATION": re.compile(r"GetEquipGradeLevel\s*\(\s*GetLocation\s*\(\s*\)\s*\)"),
            "GRADE": re.compile(r"GetEquipGradeLevel\((\d+)\)"),
            "ARMOR_LOCATION": re.compile(r"GetEquipArmorLv\s*\(\s*GetLocation\s*\(\s*\)\s*\)"),
            "ARMOR": re.compile(r"GetEquipArmorLv\((\d+)\)"),
            "WEAPON_LV_LOCATION": re.compile(r"GetEquipWeaponLv\s*\(\s*GetLocation\s*\(\s*\)\s*\)"),
            "WEAPON_LV": re.compile(r"GetEquipWeaponLv\((\d+)\)"),
            "WEAPON_CLASS_LOCATION": re.compile(r"GetWeaponClass\s*\(\s*GetLocation\s*\(\s*\)\s*\)"),
            "ITEM_ID_LOCATION": re.compile(r"GetItemIDLocation\((\d+)\)"),
            "SKILL_LEVEL": re.compile(r"GetSkillLevel\((\d+)\)"),
            "PET_RELATIONSHIP": re.compile(r"GetPetRelationship\s*\(\s*\)"),
            "ALLOWED_EVAL": re.compile(r"^[0-9A-Za-z_+\-*/%().<>=!&|,\[\]\s]+$"),
        }
        parse_lua_effects_with_variables._regex_cache = regex_cache

    _RE_GET = regex_cache["GET"]
    _RE_REFINE_LOCATION = regex_cache["REFINE_LOCATION"]
    _RE_REFINE = regex_cache["REFINE"]
    _RE_GRADE_LOCATION = regex_cache["GRADE_LOCATION"]
    _RE_GRADE = regex_cache["GRADE"]
    _RE_ARMOR_LOCATION = regex_cache["ARMOR_LOCATION"]
    _RE_ARMOR = regex_cache["ARMOR"]
    _RE_WEAPON_LV_LOCATION = regex_cache["WEAPON_LV_LOCATION"]
    _RE_WEAPON_LV = regex_cache["WEAPON_LV"]
    _RE_WEAPON_CLASS_LOCATION = regex_cache["WEAPON_CLASS_LOCATION"]
    _RE_ITEM_ID_LOCATION = regex_cache["ITEM_ID_LOCATION"]
    _RE_SKILL_LEVEL = regex_cache["SKILL_LEVEL"]
    _RE_PET_RELATIONSHIP = regex_cache["PET_RELATIONSHIP"]
    _RE_ALLOWED_EVAL = regex_cache["ALLOWED_EVAL"]

    def get_grade_value(slot=None):
        """回傳指定 slot 的階級；同時支援整數 grade 與依 slot 儲存的 dict grade。"""
        if isinstance(grade, dict):
            target_slot = current_location_slot if slot is None else slot
            try:
                return grade.get(int(target_slot), 0) if target_slot is not None else 0
            except Exception:
                return 0
        try:
            return int(grade or 0)
        except Exception:
            return 0

    def normalize_lua_expr(expr, variables, get_values, refine_inputs):
        """把簡單 Lua expression 正規化成 Python 可求值的 expression。"""
        expr = str(expr).strip()

        expr = _RE_GET.sub(lambda m: str(get_values.get(int(m.group(1)), 0)), expr)
        expr = _RE_REFINE_LOCATION.sub(lambda m: str(refine_inputs.get(current_location_slot, 0) if current_location_slot is not None else 0), expr)
        expr = _RE_REFINE.sub(lambda m: str(refine_inputs.get(int(m.group(1)), 0)), expr)
        expr = _RE_GRADE_LOCATION.sub(lambda m: str(get_grade_value()), expr)
        expr = _RE_GRADE.sub(lambda m: str(get_grade_value(m.group(1))), expr)
        expr = _RE_ARMOR_LOCATION.sub(lambda m: str(context.armor_level_map.get(current_location_slot, 0) if current_location_slot is not None else 0), expr)
        expr = _RE_ARMOR.sub(lambda m: str(context.armor_level_map.get(int(m.group(1)), 0)), expr)
        expr = _RE_WEAPON_LV_LOCATION.sub(lambda m: str(context.weapon_level_map.get(current_location_slot, 0) if current_location_slot is not None else 0), expr)
        expr = _RE_WEAPON_LV.sub(lambda m: str(context.weapon_level_map.get(int(m.group(1)), 0)), expr)
        expr = _RE_WEAPON_CLASS_LOCATION.sub(lambda m: str(context.weapon_type_map.get(current_location_slot, 0) if current_location_slot is not None else 0), expr)
        expr = _RE_ITEM_ID_LOCATION.sub(lambda m: str(context.slot_item_id_map.get(int(m.group(1)), 0)), expr)
        expr = _RE_SKILL_LEVEL.sub(lambda m: str(context.enabled_skill_levels.get(int(m.group(1)), 0)), expr)
        expr = _RE_PET_RELATIONSHIP.sub(lambda m: str(get_grade_value()), expr)

        pure_jobs = context.pure_jobs
        expr = re.sub(r"GetPureJob\(\)\s*==\s*(\d+)", lambda m: f"({int(m.group(1))} in {list(pure_jobs)})", expr)
        expr = re.sub(r"GetPureJob\(\)\s*~=\s*(\d+)", lambda m: f"({int(m.group(1))} not in {list(pure_jobs)})", expr)

        expr = expr.replace("~=", "!=").replace("&&", " and ").replace("||", " or ")
        expr = re.sub(r"\btrue\b", "True", expr, flags=re.IGNORECASE)
        expr = re.sub(r"\bfalse\b", "False", expr, flags=re.IGNORECASE)
        expr = re.sub(r"\bnil\b", "0", expr, flags=re.IGNORECASE)

        # 僅替換純數值變數；dict/list 等內部狀態不應塞回 eval 字串。
        for v in sorted(variables.keys(), key=lambda x: -len(x)):
            value = variables[v]
            if isinstance(value, bool):
                value = int(value)
            if isinstance(value, (int, float)):
                expr = re.sub(rf'\b{re.escape(v)}\b', str(value), expr)

        # 補括號，容忍部分 Lua 資料少寫右括號的狀況。
        if expr.count("(") > expr.count(")"):
            expr += ")" * (expr.count("(") - expr.count(")"))

        return expr

    def _eval_python_expr(expr, local_vars=None):
        if not _RE_ALLOWED_EVAL.fullmatch(expr):
            raise ValueError(f"含不允許字元: {expr}")

        import ast
        import math

        def __idiv(a, b):
            # 除完立刻取整；正數情況等同 floor
            return int(a / b)

        class IntDivTransformer(ast.NodeTransformer):
            def visit_BinOp(self, node):
                self.generic_visit(node)

                if isinstance(node.op, ast.Div):
                    return ast.copy_location(
                        ast.Call(
                            func=ast.Name(id="__idiv", ctx=ast.Load()),
                            args=[node.left, node.right],
                            keywords=[]
                        ),
                        node
                    )

                return node

        tree = ast.parse(expr, mode="eval")
        tree = IntDivTransformer().visit(tree)
        ast.fix_missing_locations(tree)

        env = {
            "math": math,
            "__idiv": __idiv,
        }

        if local_vars:
            env.update({
                k: v for k, v in local_vars.items()
                if isinstance(v, (int, float, bool))
            })

        return eval(
            compile(tree, "<expr>", "eval"),
            {"__builtins__": None},
            env
        )

    def safe_eval_expr(expr, variables, get_values, refine_inputs, grade):
        normalized = normalize_lua_expr(expr, variables, get_values, refine_inputs)
        try:
            value = _eval_python_expr(normalized, variables)
            if isinstance(value, bool):
                return int(value)
            return int(value)
        except Exception:
            return f"{normalized}（無法解析）"

    def eval_condition_expr(expr):
        normalized = normalize_lua_expr(expr, variables, get_values, refine_inputs)
        try:
            return bool(_eval_python_expr(normalized, variables)), normalized, None
        except Exception as e:
            return False, normalized, e




    def split_lua_args(args_text: str):
        """切分簡單 Lua 風格函式參數，同時保留巢狀呼叫。"""
        args = []
        current = []
        depth = 0
        quote = None
        escape = False

        for ch in args_text:
            if quote:
                current.append(ch)
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == quote:
                    quote = None
                continue

            if ch in ('"', "'"):
                quote = ch
                current.append(ch)
            elif ch in "({[":
                depth += 1
                current.append(ch)
            elif ch in ")}]":
                depth = max(0, depth - 1)
                current.append(ch)
            elif ch == "," and depth == 0:
                args.append("".join(current).strip())
                current = []
            else:
                current.append(ch)

        tail = "".join(current).strip()
        if tail:
            args.append(tail)
        return args


    def get_lua_call_args(func_name: str, line_text: str, flags: int = 0):
        m = re.match(rf"{func_name}\s*\((.*)\)\s*$", line_text, flags)
        if not m:
            return None
        return split_lua_args(m.group(1))


    def eval_lua_arg(args, index: int, default=None):
        if args is None or index >= len(args):
            return default
        return safe_eval_expr(args[index], variables, get_values, refine_inputs, grade)


    def map_int_arg(args, index: int, mapping: dict, fallback_prefix: str):
        if args is None or index >= len(args):
            return f"{fallback_prefix}?"
        try:
            key = int(safe_eval_expr(args[index], variables, get_values, refine_inputs, grade))
        except Exception:
            try:
                key = int(args[index])
            except Exception:
                return f"{fallback_prefix}{args[index]}"
        return mapping.get(key, f"{fallback_prefix}{key}")

    for line in lines:
        original_line = line.strip()
        line = original_line.split("--")[0].strip()
        # 輸入層接受 Python 習慣的 elif；解析前統一成 Lua elseif。
        line = re.sub(r"^elif\b", "elseif", line)
        # 把 GetRefineLevel(GetLocation()) 轉為當前部位的 slot ID
        if current_location_slot is not None:
            refine_value = refine_inputs.get(current_location_slot, 0)
            line = re.sub(
                r"GetRefineLevel\s*\(\s*GetLocation\s*\(\s*\)\s*\)",
                str(refine_value),
                line
            )
            # 從全域變數中抓出該部位的武器等級
            if current_location_slot not in context.weapon_level_map:
                context.weapon_level_map[current_location_slot] = 0
            weapon_level = context.weapon_level_map.get(current_location_slot, 0)

            line = re.sub(
                r"GetEquipWeaponLv\s*\(\s*GetLocation\s*\(\s*\)\s*\)",
                str(weapon_level),
                line
            )
            # 從全域變數中抓出該部位的防具等級
            if current_location_slot not in context.armor_level_map:
                context.armor_level_map[current_location_slot] = 0
            armor_level = context.armor_level_map.get(current_location_slot, 0)
            line = re.sub(
                r"GetEquipArmorLv\s*\(\s*GetLocation\s*\(\s*\)\s*\)",
                str(armor_level),
                line
            )
            #從全域變數抓出技能等級
            line = re.sub(
                r"GetSkillLevel\((\d+)\)",
                lambda m: str(context.enabled_skill_levels.get(int(m.group(1)), 0)),
                line
            )
            # 從全域變數抓出該部位的武器類型（代碼）
            if current_location_slot not in context.weapon_type_map:
                context.weapon_type_map[current_location_slot] = 0
            weapon_class = context.weapon_type_map.get(current_location_slot, 0)

            line = re.sub(
                r"GetWeaponClass\s*\(\s*GetLocation\s*\(\s*\)\s*\)",
                str(weapon_class),
                line
            )

        if not line:
            continue
            
        # === 特殊判斷：若為 P.S = XXX 則直接顯示後面的文字 ===
        if line.startswith("P.S ="):
            comment = line.split("=", 1)[1].strip()
            results.append(f"📌P.S：{comment}")
            continue

        # 🔽  GetPetRelationship() 替換為傳入的裝備階級
        line = re.sub(r"GetPetRelationship\s*\(\s*\)", str(get_grade_value()), line)

        # 將 GetEquipGradeLevel(GetLocation()) 替換為傳入的裝備階級
        line = re.sub(r"GetEquipGradeLevel\s*\(\s*GetLocation\s*\(\s*\)\s*\)", str(get_grade_value()), line)
        # 補充解析 Type 與 Stat 同行的情況（裝備類別與屬性）
        type_stat_match = re.match(r'Type\s*=\s*"(.*?)"\s*,\s*Stat\s*=\s*\{(.*?)\}', line)
        if type_stat_match:
            eq_type = type_stat_match.group(1)
            stat_str = type_stat_match.group(2)
            stat_values = [int(x.strip()) for x in stat_str.split(",")]
            stat_names_list = dependencies.require("stat_name_sets").get(eq_type, dependencies.require("stat_name_sets")["armor"])

            results.append(f"🛠️ 類型：{eq_type}")
            for idx, val in enumerate(stat_values):
                if val != 0:
                    name = stat_names_list[idx] if idx < len(stat_names_list) else f"未知{idx}"
                    results.append(f"{name} +{val}")
            continue




        # 處理單行 Stat = {...}
        stat_match = re.search(r'Stat\s*=\s*\{([^\}]+)\}', line)
        if stat_match:
            stat_values = [int(x.strip()) for x in stat_match.group(1).split(",") if x.strip().isdigit()]

            # 嘗試在整體文本中找到 Type
            type_match = re.search(r'Type\s*=\s*"(\w+)"', block_text)
            equip_type = type_match.group(1) if type_match else "armor"
            stat_names = dependencies.require("stat_name_sets").get(equip_type, dependencies.require("stat_name_sets")["armor"])
            
            for idx, val in enumerate(stat_values):
                if val != 0:
                    stat_name = stat_names[idx] if idx < len(stat_names) else f"未知{idx}"
                    # ✅ 儲存武器或防具類型
                    context.armor_weapon_map[current_location_slot] = equip_type
                    # 儲存武器或防具等級
                    if stat_name == "武器等級":
                        context.weapon_level_map[current_location_slot] = val                    
                    elif stat_name == "防具等級":
                        context.armor_level_map[current_location_slot] = val
                    elif stat_name == "武器ATK":
                        context.weapon_atk_map[current_location_slot] = val
                        #print(f"設定武器ATK: 部位{current_location_slot} = {val}")
                    elif stat_name == "武器MATK":
                        context.weapon_matk_map[current_location_slot] = val
                        #print(f"設定武器MATK: 部位{current_location_slot} = {val}")

                        
                    # ✅ 處理武器類型（使用 map 轉換中文名稱）
                    if stat_name == "武器類型":
                        context.weapon_type_map[current_location_slot] = val
                        weapon_type_name = dependencies.require("weapon_type_map").get(val, f"未知武器類型({val})")
                        #results.append(f"武器類型：{weapon_type_name}")
                        continue  # 若你不想再輸出 "武器類型 +x" 可跳過

                    # 過濾排除屬性
                    if stat_name in dependencies.require("excluded_stat_names"):
                        continue

                    results.append(f"{stat_name} +{val}")



            
         # 處理 if 條件
        if_match = re.match(r"if\s+(.+?)\s+then", line)
        if if_match:
            # 檢查父層是否成立
            parent_active = all(block['active'] for block in block_stack)
            if not parent_active:
                block_stack.append({"active": False, "branch_taken": False})
                continue

            expr = if_match.group(1)
            condition_met, normalized_expr, err = eval_condition_expr(expr)
            if err is None:
                results.append(f"{'✅ if 條件成立' if condition_met else '❌ if 條件不成立'} : {expr}")
            else:
                results.append(f"⚠️ 無法解析條件: {expr}，轉換後: {normalized_expr}，錯誤: {err}")

            block_stack.append({"active": condition_met, "branch_taken": condition_met})
            continue

        # elseif 判斷
        elseif_match = re.match(r"elseif\s+(.+?)\s+then", line)
        if elseif_match:
            if not block_stack:
                raise Exception("elseif without if")
            # 先移除上一個分支
            last = block_stack.pop()
            parent_active = all(block['active'] for block in block_stack)
            if not parent_active or last["branch_taken"]:
                # 父層不成立 或 已有分支成立
                block_stack.append({"active": False, "branch_taken": True})
                continue

            expr = elseif_match.group(1)
            condition_met, normalized_expr, err = eval_condition_expr(expr)
            if err is None:
                results.append(f"{'✅ elseif 條件成立' if condition_met else '❌ elseif 條件不成立'} : {expr}")
            else:
                results.append(f"⚠️ 無法解析條件: {expr}，轉換後: {normalized_expr}，錯誤: {err}")

            
            block_stack.append({"active": condition_met, "branch_taken": condition_met})
            condition_met = all(block['active'] for block in block_stack)
            continue

        # else 判斷
        else_match = re.match(r"\s*else\b", line)
        if else_match:
            if not block_stack:
                raise Exception("else without if")
            last = block_stack.pop()
            parent_active = all(block['active'] for block in block_stack)
            
            if not parent_active or last["branch_taken"]:
                block_stack.append({"active": False, "branch_taken": True})
            else:
                block_stack.append({"active": True, "branch_taken": True})

            condition_met = all(block['active'] for block in block_stack)
            continue

        # end 判斷
        end_match = re.match(r"\s*end\b", line)
        if end_match:
            if block_stack:
                block_stack.pop()

            # --- 🔧 重置 condition_met 並回到父層狀態 ---
            # 若目前仍在某些區塊內，就依照父層 active 狀態決定
            if block_stack:
                condition_met = all(block['active'] for block in block_stack)
            else:
                # 已經完全跳出 if/elseif/else 區塊，重置為 True
                condition_met = True

            continue

        # 一般語句判斷
        if block_stack and not all(block['active'] for block in block_stack):
            continue


        # 支援多個 GetRefineLevel 連加 (先處理多段再處理單段)
        multi_refine_assign = re.match(
            r"(\w+)\s*=\s*GetRefineLevel\((\d+)\)((?:\s*\+\s*GetRefineLevel\((\d+)\))+)", line)
        if multi_refine_assign:
            var = multi_refine_assign.group(1)
            slots = re.findall(r"GetRefineLevel\((\d+)\)", line)
            try:
                value = sum([refine_inputs.get(int(slot), 0) for slot in slots])
                variables[var] = value
                results.append(f"📌 `{var}` = {value}（GetRefineLevel({'+'.join(slots)})）")
            except Exception as e:
                results.append(f"⚠️ 無法計算 `{var}` = GetRefineLevel({' + '.join(slots)})，錯誤：{e}")
            continue

        # 新增對 temp = GetRefineLevel(...) 的處理邏輯
        refine_assign = re.match(r"(\w+)\s*=\s*GetRefineLevel\((\d+)\)", line)
        if refine_assign:
            var, slot = refine_assign.groups()
            try:
                value = refine_inputs.get(int(slot), 0)
                variables[var] = value
                results.append(f"📌 `{var}` = {value}（GetRefineLevel({slot})）")
            except:
                results.append(f"⚠️ 無法計算 `{var}` = GetRefineLevel({slot})")
            continue
            


        # 新增對 temp = GetEquipGradeLevel(...) 的處理邏輯
        grade_assign = re.match(r"(\w+)\s*=\s*GetEquipGradeLevel\((\d+)\)", line)
        if grade_assign:
            var, slot = grade_assign.groups()
            try:
                # 如果 grade 是 dict，取對應部位；否則直接用整數
                value = get_grade_value(slot)
                #print(f"[DEBUG] slot {slot} 的 grade 值: {value} 來源: {original_line.strip()}")
                
                variables[var] = value
                results.append(f"📌 `{var}` = {value}（GetEquipGradeLevel({slot})）")
            except:
                results.append(f"⚠️ 無法計算 `{var}` = GetEquipGradeLevel({slot})")
            continue

        # 新增對 temp = GetEquipArmorLv(...) 的處理邏輯
        armor_assign = re.match(r"(\w+)\s*=\s*GetEquipArmorLv\((\d+)\)", line)
        if armor_assign:
            var, slot = armor_assign.groups()
            try:
                slot_i = int(slot)
                # 從全域表拿該部位的「防具等級」；沒設定就預設 0
                value = context.armor_level_map.get(slot_i, 0)
                variables[var] = value
                results.append(f"📌 `{var}` = {value}（GetEquipArmorLv({slot})）")
            except:
                results.append(f"⚠️ 無法計算 `{var}` = GetEquipArmorLv({slot})")
            continue

        # 新增對 temp = GetWeaponClass(...) 的處理邏輯
        weapon_type_name = re.match(r"(\w+)\s*=\s*GetWeaponClass\((\d+)\)", line)
        if weapon_type_name:
            var, slot = weapon_type_name.groups()
            try:
                slot_i = int(slot)
                # 從全域表取得該武器的位置類別，沒有設定則預設 0
                value = context.weapon_type_map.get(slot_i, 0)
                variables[var] = value
                results.append(f"📌 `{var}` = {value}（GetWeaponClass({slot})）")
            except:
                results.append(f"⚠️ 無法計算 `{var}` = GetWeaponClass({slot})")
            continue

        # 新增對 temp = GetEquipWeaponLv(...) 的處理邏輯
        weapon_Lv_name = re.match(r"(\w+)\s*=\s*GetEquipWeaponLv\((\d+)\)", line)
        if weapon_Lv_name:
            var, slot = weapon_Lv_name.groups()
            try:
                slot_i = int(slot)
                # 從全域表取得該武器的位置類別，沒有設定則預設 0
                value = context.weapon_level_map.get(slot_i, 0)
                variables[var] = value
                results.append(f"📌 `{var}` = {value}（GetEquipWeaponLv({slot})）")
            except:
                results.append(f"⚠️ 無法計算 `{var}` = GetEquipWeaponLv({slot})")
            continue
        
        # math.floor(...) 指定變數
        var_math = re.match(r"(\w+)\s*=\s*math\.floor\((.+)\)", line)
        if var_math:
            var, expr = var_math.groups()
            normalized_expr = normalize_lua_expr(expr, variables, get_values, refine_inputs)
            try:
                value = safe_eval_expr(f"math.floor({expr})", variables, get_values, refine_inputs, grade)
                if isinstance(value, str):
                    raise ValueError(value)
                variables[var] = value
                results.append(f"📌 `{var}` = {value}（floor({normalized_expr})）")
            except Exception as e:
                results.append(f"⚠️ 無法計算 `{var}` = floor({normalized_expr})，錯誤：{e}")
            continue

        # 一般變數指定
        var_assign = re.match(r"(\w+)\s*=\s*(.+)", line)
        if var_assign and not var_math:
            if not condition_met:
                results.append(f"⛔ 已跳過（條件不成立）: {original_line}")
                continue  # 不執行此行
            var, expr = var_assign.groups()
            if any(token in expr for token in ('"', "'", "{", "function")):
                continue

            if '"' in expr or "'" in expr or "{" in expr or "function" in expr:
                results.append(f"🟡一般變數 無法辨識: {original_line}")
                continue
            # 外部角色/裝備變數已在 parser 一開始同步到 variables，
            # 不要到一般變數指定時才補，否則 if / 函式參數會比這裡更早使用到舊值。
            normalized_expr = normalize_lua_expr(expr, variables, get_values, refine_inputs)
            try:
                value = safe_eval_expr(expr, variables, get_values, refine_inputs, grade)
                if isinstance(value, str):
                    raise ValueError(value)
                variables[var] = value
                results.append(f"📌 `{var}` = {value}")
            except Exception as e:
                results.append(f"⚠️ 無法計算 `{var}` = {normalized_expr}，錯誤：{e}")
            continue
            

        # 1. EnableSkill(skill_id, level)
        dependencies.register_function("EnableSkill", "可使用技能", [
            {"name": "技能", "map": "skill_map"},
            {"name": "等級", "type": "value"}
        ])
        enable_skill = re.match(r"EnableSkill\((\d+),\s*(\d+)\)", line)
        if enable_skill and condition_met:
            skill_id, level = enable_skill.groups()
            skill_id = int(skill_id)
            level = int(level)
            skill_name = dependencies.require("skill_map").get(skill_id, f"技能ID {skill_id}")
            results.append(f"可使用【{skill_name}】Lv.{level}")
            # ➕ 記錄技能等級
            context.enabled_skill_levels[skill_id] = level
            continue

        # UseSkill(skill_id)

        use_skill = re.match(r"UseSkill\(\s*(\d+)\s*\)", line)

        if use_skill and condition_met:
            skill_id = int(use_skill.group(1))
            skill_name = dependencies.require("skill_map").get(skill_id, f"技能ID {skill_id}")
            results.append(f"使用【{skill_name}】")  # 這裡不帶 Lv，也不紀錄等級
            #紀錄使用
            context.used_skill_levels[skill_id] = True 
            continue


        # AddExtParam(...)
        dependencies.register_function("AddExtParam", "增加基礎能力", [{"name": "無意義", "map": "1"},{"name": "能力", "map": "effect_map"},{"name": "數值", "type": "value"}])
        dependencies.register_function("SubExtParam", "減少基礎能力", [{"name": "無意義", "map": "1"},{"name": "能力", "map": "effect_map"},{"name": "數值", "type": "value"}])

        # AddExtParam / SubExtParam 合併處理
        ext = re.match(r"(Add|Sub)ExtParam\((\d+),\s*(\d+),\s*(.+)\)", line)
        if ext and condition_met:
            op, unit, param_id, val_expr = ext.groups()
            val = safe_eval_expr(val_expr, variables, get_values, refine_inputs, grade)

            unit_str = unit_map.get(int(unit), f"單位{unit}")
            effect_str = effect_map.get(int(param_id), f"參數{param_id}")

            # 解析失敗保護
            if not isinstance(val, int):
                results.append(f"{effect_str} ({val})（無法解析）")
                continue

            # 預設：Add=+、Sub=-
            def sign_for(op_: str, invert: bool = False) -> str:
                # invert=True 會反轉（給「攻擊後延遲」用）
                return "+" if ((op_ == "Add") != invert) else "-"

            # 特例 1：CRI、完全迴避（每 10 = 1）
            if effect_str in ("CRI", "完全迴避"):
                v = val // 10
                results.append(f"{effect_str} {sign_for(op)}{v}")
                continue

            # 特例 2：攻擊後延遲（Add=減少、Sub=增加）+ 一定加 %
            if effect_str in ("攻擊後延遲","(2轉以下)攻擊後延遲"):
                results.append(f"{effect_str} {sign_for(op, invert=True)}{val}%")
                continue

            # 一般情況：若名稱本身以 % 結尾（如 MATK% / ATK%），就帶 %
            percent_suffix = "%" if str(effect_str).endswith("%") else ""
            results.append(f"{effect_str} {sign_for(op)}{val}{percent_suffix}")
            continue

            
        # AddSpellDelay / SubSpellDelay 合併處理（技能後延遲 %）
        dependencies.register_function("AddSpellDelay", "增加技能後延遲", [{"name": "數值%", "type": "value"}])
        dependencies.register_function("SubSpellDelay", "減少技能後延遲", [{"name": "數值%", "type": "value"}])

        delay = re.match(r"(Add|Sub)SpellDelay\(\s*(.+)\s*\)\s*$", line)
        if delay and condition_met:
            op, expr = delay.groups()
            val = safe_eval_expr(expr, variables, get_values, refine_inputs, grade)

            if isinstance(val, int):
                sign = "+" if op == "Add" else "-"
                results.append(f"技能後延遲 {sign}{val}%")
            else:
                # 保留原本的「無法解析」提示
                sign = "+" if op == "Add" else "-"
                results.append(f"技能後延遲 {sign}({val})%（無法解析）")
            continue

        # 增減 變動詠唱時間（%）合併處理
        dependencies.register_function("SubSpellCastTime", "減少變動詠唱時間", [{"name": "數值%", "type": "value"}])
        dependencies.register_function("AddSpellCastTime", "增加變動詠唱時間", [{"name": "數值%", "type": "value"}])

        cast_time = re.match(r"(Add|Sub)SpellCastTime\(\s*(.+)\s*\)", line)
        if cast_time and condition_met:
            op, value_expr = cast_time.groups()
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)

            sign = "+" if op == "Add" else "-"
            try:
                results.append(f"變動詠唱時間 {sign}{val}%")
            except Exception:
                results.append(f"變動詠唱時間 {sign}({value_expr})%（無法解析）")
            continue


        # AddSFCTEquipAmount / SubSFCTEquipAmount（固定詠唱時間，第一參數是物品ID，第二參數是 ms 表達式，第三參數是數字）
        dependencies.register_function("SubSFCTEquipAmount", "減少固定詠唱時間", [
            {"name": "無意義", "map": "0"},#物品名稱
            {"name": "數值ms", "type": "value"},
            {"name": "無意義", "map": "0"}
        ])
        dependencies.register_function("AddSFCTEquipAmount", "增加固定詠唱時間", [
            {"name": "無意義", "map": "0"},#物品名稱
            {"name": "數值ms", "type": "value"},
            {"name": "無意義", "map": "0"}
        ])

        sfct = re.match(
            r"(Add|Sub)SFCTEquipAmount\(\s*(?:(\d+)\s*,\s*)?(.+?)\s*,\s*(\d+)\s*\)\s*$",
            line
        )
        if sfct and condition_met and not sfct_handled:
            op, item_id, expr, dummy = sfct.groups()

            # expr 是第二個參數，才是真正的 ms
            val_ms = safe_eval_expr(expr, variables, get_values, refine_inputs, grade)

            sign = "+" if op == "Add" else "-"
            if isinstance(val_ms, int):
                results.append(f"固定詠唱時間 {sign}{val_ms / 1000:.2f} 秒")
            else:
                results.append(f"固定詠唱時間 {sign}({val_ms}) 秒（無法解析）")

            sfct_handled = True
            continue

        sfct_2 = re.match(
            r"(Add|Sub)SFCTEquipPermill\(\s*(?:(\d+)\s*,\s*)?(.+?)\s*,\s*(\d+)\s*\)\s*$",
            line
        )
        if sfct_2 and condition_met and not sfct_handled:
            op, item_id, expr, dummy = sfct_2.groups()

            # expr 是第二個參數，才是真正的 ms
            val = safe_eval_expr(expr, variables, get_values, refine_inputs, grade)
            val = val // 10  # 轉為百分比
            sign = "+" if op == "Add" else "-"
            if isinstance(val, int):
                sign = "+" if op == "Add" else "-"
                results.append(f"固定詠唱時間 {sign}{val}%")
            else:
                # 保留原本的「無法解析」提示
                sign = "+" if op == "Add" else "-"
                results.append(f"固定詠唱時間 {sign}({val})%（無法解析）")
            continue

        # 增減「指定技能傷害(裝備段)」合併處理
        dependencies.register_function("AddDamage_SKID", "增加技能傷害(裝備段)", [
            {"name": "目標", "map": "unit_map"},
            {"name": "技能", "map": "skill_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubDamage_SKID", "減少技能傷害(裝備段)", [
            {"name": "目標", "map": "unit_map"},
            {"name": "技能", "map": "skill_map"},
            {"name": "數值%", "type": "value"}
        ])

        add_sub_dmg_skid = re.match(r"(Add|Sub)Damage_SKID\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)\s*$", line)
        if add_sub_dmg_skid and condition_met:
            op, skill_id, value_expr = add_sub_dmg_skid.groups()
            skill_name = dependencies.require("skill_map").get(int(skill_id), f"技能ID {skill_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)

            if isinstance(val, int):
                sign = "+" if op == "Add" else "-"
                results.append(f"技能【{skill_name}】傷害(裝備段) {sign}{val}%")
            else:
                sign = "+" if op == "Add" else "-"
                results.append(f"技能【{skill_name}】傷害(裝備段) {sign}({val})%（無法解析）")
            continue

            
        # 增減「指定技能傷害(技能段)」合併處理
        dependencies.register_function("AddDamage_passive_SKID", "增加技能傷害(技能段)", [
            {"name": "目標", "map": "unit_map"},
            {"name": "技能", "map": "skill_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubDamage_passive_SKID", "減少技能傷害(技能段)", [
            {"name": "目標", "map": "unit_map"},
            {"name": "技能", "map": "skill_map"},
            {"name": "數值%", "type": "value"}
        ])

        add_sub_dmg_passive = re.match(
            r"(Add|Sub)Damage_passive_SKID\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)\s*$",
            line
        )
        if add_sub_dmg_passive and condition_met:
            op, skill_id, value_expr = add_sub_dmg_passive.groups()
            skill_name = dependencies.require("skill_map").get(int(skill_id), f"技能ID {skill_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)

            sign = "+" if op == "Add" else "-"
            if isinstance(val, int):
                results.append(f"技能【{skill_name}】傷害(技能段) {sign}{val}%")
            else:
                results.append(f"技能【{skill_name}】傷害(技能段) {sign}({val})%（無法解析）")
            continue

            
        # 增減「指定技能傷害(技能段)」合併處理
        dependencies.register_function("AddSkillDelay", "增加技能固定冷卻", [
            {"name": "技能", "map": "skill_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubSkillDelay", "減少技能固定冷卻", [
            {"name": "技能", "map": "skill_map"},
            {"name": "數值%", "type": "value"}
        ])

        # 指定技能冷卻時間（毫秒）增加/減少 合併處理
        skill_delay = re.match(r"(Add|Sub)SkillDelay\(\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if skill_delay and condition_met:
            op, skill_id, delay_expr = skill_delay.groups()
            skill_name = dependencies.require("skill_map").get(int(skill_id), f"技能ID {skill_id}")
            val_ms = safe_eval_expr(delay_expr, variables, get_values, refine_inputs, grade)

            if isinstance(val_ms, int):
                delta = val_ms if op == "Add" else -val_ms
                skill_delay_accum[skill_name] = skill_delay_accum.get(skill_name, 0) + delta
            else:
                # 保留原本的無法解析提示
                results.append(f"技能【{skill_name}】冷卻時間變化 ({val_ms}) 毫秒（無法解析）")
            continue

        # Add/Sub SpecificSpellCastTime（指定技能變動詠唱時間 %）
        specific_cast = re.match(r"(Add|Sub)SpecificSpellCastTime\(\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if specific_cast and condition_met:
            op, skill_id, value_expr = specific_cast.groups()
            skill_name = dependencies.require("skill_map").get(int(skill_id), f"技能ID {skill_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)

            sign = "+" if op == "Add" else "-"
            if isinstance(val, int):
                results.append(f"技能【{skill_name}】變動詠唱時間 {sign}{val}%")
            else:
                results.append(f"技能【{skill_name}】變動詠唱時間 {sign}({val})%（無法解析）")
            continue
        # Add/Sub EXPPercent_KillRace (從擊殺魔物獲得的經驗%)
        exp_race = re.match(r"(Add|Sub)EXPPercent_KillRace\(\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if exp_race and condition_met:
            op, race_id, value_expr = exp_race.groups()
            race_name = dependencies.require("race_map").get(int(race_id), f"種族{race_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"從 {race_name} 型怪的經驗值 {sign}{val}%")
            continue

        #掉寶機率ReceiveItem_Equip(value)
        Item_attack = re.match(r"(Add|Sub)ReceiveItem_Equip\(\s*(.+?)\s*\)", line)
        if Item_attack and condition_met:
            op, value_expr = Item_attack.group(1,2)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"掉寶率 {sign}{value_expr}%")
            continue

        dependencies.register_function("就說通用了你還產生！", "----以上通用分隔線----", [])
        dependencies.register_function("就說以下魔法了你還產生！", "--以下魔法增減分隔線--", [])


#==========以上通用變數
#==========以下魔法判斷
        # Add/Sub SkillMDamage（屬性魔法傷害）
        dependencies.register_function("AddSkillMDamage", "增加屬性魔法傷害", [
            {"name": "屬性", "map": "element_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubSkillMDamage", "減少屬性魔法傷害", [
            {"name": "屬性", "map": "element_map"},
            {"name": "數值%", "type": "value"}
        ])
        skill_mdamage = re.match(r"(Add|Sub)SkillMDamage\(\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if skill_mdamage and condition_met:
            op, elem_id, value_expr = skill_mdamage.groups()
            element = dependencies.require("element_map").get(int(elem_id), f"屬性{elem_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"{element} 的魔法傷害 {sign}{val}%")
            continue

        # Add/Sub MDamage_Size（體型魔法）
        dependencies.register_function("AddMDamage_Size", "增加體型魔法傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "體型", "map": "size_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubMDamage_Size", "減少體型魔法傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "體型", "map": "size_map"},
            {"name": "數值%", "type": "value"}
        ])

        mdamage_size = re.match(r"(Add|Sub)MDamage_Size\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if mdamage_size and condition_met:
            op, size_id, value_expr = mdamage_size.groups()
            size_name = size_map.get(int(size_id), f"尺寸{size_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"對 {size_name} 敵人的魔法傷害 {sign}{val}%")
            continue

        # Add/Sub Mdamage_Race（對種族魔法傷害）
        dependencies.register_function("AddMdamage_Race", "增加種族魔法傷害", [
            {"name": "種族", "map": "race_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubMdamage_Race", "減少種族魔法傷害", [
            {"name": "種族", "map": "race_map"},
            {"name": "數值%", "type": "value"}
        ])

        mdamage_race = re.match(r"(Add|Sub)Mdamage_Race\(\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if mdamage_race and condition_met:
            op, race_id, value_expr = mdamage_race.groups()
            race_name = dependencies.require("race_map").get(int(race_id), f"種族{race_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"對 {race_name} 型怪的魔法傷害 {sign}{val}%")
            continue

        # Add/Sub MDamage_Property（對指定種族與屬性）
        dependencies.register_function("AddMDamage_Property", "增加屬性對象魔法傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "屬性", "map": "element_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubMDamage_Property", "減少屬性對象魔法傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "屬性", "map": "element_map"},
            {"name": "數值%", "type": "value"}
        ])

        add_mdamage_prop = re.match(r"(Add|Sub)MDamage_Property\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if add_mdamage_prop and condition_met:
            op, elem_id, value_expr = add_mdamage_prop.groups()
            elem_name = dependencies.require("element_map").get(int(elem_id), f"屬性{elem_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"對 {elem_name} 對象的魔法傷害 {sign}{val}%")
            continue
        # AddMdamage_Class（對階級魔法傷害）
        
        dependencies.register_function("AddMdamage_Class", "增加階級魔法傷害", [
            {"name": "階級", "map": "class_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubMdamage_Class", "減少階級魔法傷害", [
            {"name": "階級", "map": "class_map"},
            {"name": "數值%", "type": "value"}
        ])

        # AddMdamage_Class / SubMdamage_Class 合併處理
        mdamage_class = re.match(r"(Add|Sub)Mdamage_Class\(\s*(\d+)\s*,\s*(.+?)\s*\)", line)
        if mdamage_class and condition_met:
            op, class_id, value_expr = mdamage_class.groups()
            class_name = dependencies.require("class_map").get(int(class_id), f"階級{class_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)

            sign = "+" if op == "Add" else "-"
            results.append(f"對 {class_name} 階級的魔法傷害 {sign}{val}%")
            continue

        # SetIgnoreMdefClass（無視階級魔防）
        dependencies.register_function("SetIgnoreMdefClass", "無視階級魔法防禦", [
            {"name": "階級", "map": "class_map"},
            {"name": "數值%", "type": "value"}
        ])
        ignore_mdef = re.match(r"SetIgnoreMdefClass\((\d+),\s*(.+?)\)", line)
        if ignore_mdef and condition_met:
            class_id, value_expr = ignore_mdef.groups()
            class_name = dependencies.require("class_map").get(int(class_id), f"階級{class_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            results.append(f"無視 {class_name} 階級的魔法防禦 {val}%")
            continue
            
        # SetIgnoreMdefClass（無視種族魔防）
        dependencies.register_function("SetIgnoreMdefRace", "無視種族魔法防禦", [
            {"name": "種族", "map": "race_map"},
            {"name": "數值%", "type": "value"}
        ])
        ignore_mdef_race = re.match(r"SetIgnoreMdefRace\((\d+),\s*(.+?)\)", line)
        if ignore_mdef_race and condition_met:
            race_id, value_expr = ignore_mdef_race.groups()
            race_name = dependencies.require("race_map").get(int(race_id), f"種族{race_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            results.append(f"無視 {race_name} 型怪的魔法防禦 {val}%")
            continue

        # AddIgnore_MRES_RacePercent（無視種族魔抗）
        dependencies.register_function("AddIgnore_MRES_RacePercent", "無視種族魔法抗性", [
            {"name": "種族", "map": "race_map"},
            {"name": "數值%", "type": "value"}
        ])
        ignore_mres_race = re.match(r"(Add|Sub)Ignore_MRES_RacePercent\((\d+),\s*(.+?)\)", line)
        if ignore_mres_race and condition_met:
            op, race_id, value_expr = ignore_mres_race.groups()
            race_name = dependencies.require("race_map").get(int(race_id), f"種族{race_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"無視 {race_name} 型怪的魔法抗性 {sign}{val}%")
            continue
            
        # 增加特定魔物魔法傷害MonsterMAtkPercent(value)
        dependencies.register_function("MonsterMAtkPercent", "增加特定魔物魔法傷害", [
            {"name": "數值%", "type": "value"}
        ])
        mon_m_atk = re.match(r"MonsterMAtkPercent\(\s*(.+)\s*\)", line)
        if mon_m_atk and condition_met:
            value_expr = mon_m_atk.group(1)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            results.append(f"特定魔物魔法增傷 +{value_expr}%")
            continue
        # 減少特定魔物魔法傷害MonsterMAtkPercent(value)
        dependencies.register_function("SubMonsterMAtkPercent", "減少特定魔物魔法傷害", [
            {"name": "數值%", "type": "value"}
        ])
        mon_m_atk = re.match(r"SubMonsterMAtkPercent\(\s*(.+)\s*\)", line)
        if mon_m_atk and condition_met:
            value_expr = mon_m_atk.group(1)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            results.append(f"特定魔物魔法增傷 -{value_expr}%")
            continue

        dependencies.register_function("就說以上魔法了你還產生！", "--以上魔法增減分隔線--", [])
#===========以上魔法判斷
#===========以下物理判斷
        dependencies.register_function("就說以下物理了你還產生！", "--以下物理增減分隔線--", [])

        dependencies.register_function("WeaponMasteryATK", "修煉ATK", [
            {"name": "數值%", "type": "value"}
        ])
        #修煉ATK WeaponMasteryATK(value)
        MasteryATK_dmg = re.match(r"WeaponMasteryATK\(\s*(.+?)\s*\)", line)
        if MasteryATK_dmg and condition_met:
            value_expr = MasteryATK_dmg.group(1)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            results.append(f"修煉ATK +{value_expr}")
            continue

        #神威特殊atk SpecialATK
        KamuiATK_dmg = re.match(r"Kamui_SpecialATK\(\s*(.+?)\s*\)", line)
        if KamuiATK_dmg and condition_met:
            value_expr = KamuiATK_dmg.group(1)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            results.append(f"神威ATK +{value_expr}")
            continue

        dependencies.register_function("AddGuideAttack", "誘導攻擊機率", [
            {"name": "數值%", "type": "value"}
        ])
        #誘導攻擊機率AddGuideAttack(value)
        guide_attack = re.match(r"AddGuideAttack\(\s*(.+?)\s*\)", line)
        if guide_attack and condition_met:
            value_expr = guide_attack.group(1)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            results.append(f"誘導攻擊機率 +{value_expr}%")
            continue

        # AddDamage_HIT(1, value)
        dependencies.register_function("AddDamage_HIT", "增加物理命中傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubDamage_HIT", "減少物理命中傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "數值%", "type": "value"}
        ])
        melee_hit = re.match(r"(Add|Sub)Damage_HIT\(\s*1\s*,\s*(.+)\)", line)
        if melee_hit and condition_met:
            op, value_expr = melee_hit.group(1,2)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"物理命中傷害 {sign}{value_expr}%")
            continue

        # 近距離物理傷害AddMeleeAttackDamage(1, value)
        dependencies.register_function("AddMeleeAttackDamage", "增加近距離物理傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubMeleeAttackDamage", "減少近距離物理傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "數值%", "type": "value"}
        ])
        melee_dmg = re.match(r"(Add|Sub)MeleeAttackDamage\(\s*1\s*,\s*(.+)\)", line)
        if melee_dmg and condition_met:
            op, value_expr = melee_dmg.group(1,2)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"近距離物理傷害 {sign}{value_expr}%")
            continue

        # 遠距離物理傷害AddRangeAttackDamage(1, value)
        dependencies.register_function("AddRangeAttackDamage", "增加遠距離物理傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubRangeAttackDamage", "減少遠距離物理傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "數值%", "type": "value"}
        ])
        range_dmg = re.match(r"(Add|Sub)RangeAttackDamage\(\s*1\s*,\s*(.+)\)", line)
        if range_dmg and condition_met:
            op, value_expr = range_dmg.group(1,2)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"遠距離物理傷害 {sign}{value_expr}%")
            continue
            
        # AddBowAttackDamage(1, value)#弓攻擊力
        range_dmg = re.match(r"AddBowAttackDamage\(\s*1\s*,\s*(.+)\)", line)        
        if range_dmg and condition_met:
            value_expr = range_dmg.group(1)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            #results.append(f"遠距離物理傷害 +{value_expr}%")
            results.append(f"弓攻擊力 +{value_expr}%")
            continue

        # AddDamage_CRI(1, value)
        dependencies.register_function("AddDamage_CRI", "增加爆擊傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubDamage_CRI", "減少爆擊傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "數值%", "type": "value"}
        ])
        cri_dmg = re.match(r"(Add|Sub)Damage_CRI\(\s*1\s*,\s*(.+)\)", line)
        if cri_dmg and condition_met:
            op, value_expr = cri_dmg.group(1,2)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"爆擊傷害 {sign}{value_expr}%")
            continue

        # 體型物理傷害AddDamage_Size(1, size_id, value)
        dependencies.register_function("AddDamage_Size", "增加體型物理傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "體型", "map": "size_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubDamage_Size", "減少體型物理傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "體型", "map": "size_map"},
            {"name": "數值%", "type": "value"}
        ])
        size_dmg = re.match(r"(Add|Sub)Damage_Size\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if size_dmg and condition_met:
            
            op, size_id, value_expr = size_dmg.groups()
            size_str = size_map.get(int(size_id), f"體型{size_id}")
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"對 {size_str} 敵人的物理傷害 {sign}{value_expr}%")
            continue

        # RaceAddDamage(race_id, value)
        dependencies.register_function("RaceAddDamage", "增加種族物理傷害", [
            {"name": "種族", "map": "race_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("RaceSubDamage", "減少種族物理傷害", [
            {"name": "種族", "map": "race_map"},
            {"name": "數值%", "type": "value"}
        ])
        race_dmg = re.match(r"Race(Add|Sub)Damage\(\s*(\d+)\s*,\s*(.+)\s*\)\s*$", line)
        if race_dmg and condition_met:
            op, race_id, value_expr = race_dmg.groups()
            race_name = dependencies.require("race_map").get(int(race_id), f"種族{race_id}")
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"對 {race_name} 型怪的物理傷害 {sign}{value_expr}%")
            continue

        # AddDamage_Property（對指定種族與屬性）
        dependencies.register_function("AddDamage_Property", "增加屬性對象物理傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "屬性", "map": "element_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("SubDamage_Property", "減少屬性對象物理傷害", [
            {"name": "目標", "map": "unit_map"},
            {"name": "屬性", "map": "element_map"},
            {"name": "數值%", "type": "value"}
        ])
        add_damage_prop = re.match(r"(Add|Sub)Damage_Property\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if add_damage_prop and condition_met:
            op, elem_id, value_expr = add_damage_prop.groups()
            elem_name = dependencies.require("element_map").get(int(elem_id), f"屬性{elem_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"對 {elem_name} 對象的物理傷害 {sign}{val}%")
            continue


        # 階級物理傷害加成：ClassAddDamage(1, class_id, value)
        dependencies.register_function("ClassAddDamage", "增加階級的物理傷害", [
            {"name": "階級", "map": "class_map"},
            {"name": "目標", "map": "unit_map"},
            {"name": "數值%", "type": "value"}
        ])
        dependencies.register_function("ClassSubDamage", "減少階級的物理傷害", [
            {"name": "階級", "map": "class_map"},
            {"name": "目標", "map": "unit_map"},
            {"name": "數值%", "type": "value"}
        ])
        class_dmg = re.match(r"Class(Add|Sub)Damage\(\s*(\d+)\s*,\s*1\s*,\s*(.+?)\s*\)", line)
        if class_dmg and condition_met:
            op, class_id, expr_src = class_dmg.groups()
            class_name = dependencies.require("class_map").get(int(class_id), f"階級{class_id}")
            val = safe_eval_expr(expr_src, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"對 {class_name} 階級的物理傷害 {sign}{val}%")
            continue

        # SetIgnoreDEFClass(class_id)
        ignore_class = re.match(r"SetIgnoreDEFClass\((\d+)\)", line)
        if ignore_class and condition_met:
            class_name = dependencies.require("class_map").get(int(ignore_class.group(1)), f"階級{ignore_class.group(1)}")
            results.append(f"無視 {class_name} 階級的物理防禦")
            continue

        # SetIgnoreDefClass_Percent(class_id, value)
        dependencies.register_function("SetIgnoreDefClass_Percent", "無視階級物理防禦", [
            {"name": "階級", "map": "class_map"},
            {"name": "數值%", "type": "value"}
        ])
        ignore_class_pct = re.match(r"SetIgnoreDefClass_Percent\((\d+),\s*(\d+)\)", line)
        if ignore_class_pct and condition_met:
            class_id, value = ignore_class_pct.groups()
            class_name = dependencies.require("class_map").get(int(class_id), f"階級{class_id}")
            results.append(f"無視 {class_name} 階級的物理防禦 {value}%")
            continue

        # SetIgnoreDefRace_Percent(race_id, value)
        dependencies.register_function("SetIgnoreDefRace_Percent", "無視種族物理防禦", [
            {"name": "種族", "map": "race_map"},
            {"name": "數值%", "type": "value"}
        ])
        ignore_race_pct = re.match(r"SetIgnoreDefRace_Percent\((\d+),\s*(.+?)\)", line)
        if ignore_race_pct and condition_met:
            race_id, value_expr = ignore_race_pct.groups()
            race_name = dependencies.require("race_map").get(int(race_id), f"種族{race_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            results.append(f"無視 {race_name} 型怪的物理防禦 {val}%")
            continue

        # AddIgnore_RES_RacePercent(race_id, value)
        dependencies.register_function("AddIgnore_RES_RacePercent", "無視種族物理抗性", [
            {"name": "種族", "map": "race_map"},
            {"name": "數值%", "type": "value"}
        ])
        ignore_res_race = re.match(r"(Add|Sub)Ignore_RES_RacePercent\((\d+),\s*(.+?)\)", line)
        if ignore_res_race and condition_met:
            op, race_id, value_expr = ignore_res_race.groups()
            race_name = dependencies.require("race_map").get(int(race_id), f"種族{race_id}")
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"無視 {race_name} 型怪的物理抗性 {sign}{value_expr}%")
            continue

        # 特定魔物物理增傷MonsterAtkPercent(value)
        dependencies.register_function("MonsterAtkPercent", "增加特定魔物物理傷害", [
            {"name": "數值%", "type": "value"}
        ])       
        mon_atk = re.match(r"MonsterAtkPercent\(\s*(.+)\s*\)", line)
        if mon_atk and condition_met:
            value_expr = mon_atk.group(1)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            results.append(f"特定魔物物理增傷 +{value_expr}%")
            continue
        # 特定魔物物理減傷MonsterAtkPercent(value)
        dependencies.register_function("SubMonsterAtkPercent", "減少特定魔物物理傷害", [
            {"name": "數值%", "type": "value"}
        ])       
        mon_atk = re.match(r"SubMonsterAtkPercent\(\s*(.+)\s*\)", line)
        if mon_atk and condition_met:
            value_expr = mon_atk.group(1)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            results.append(f"特定魔物物理增傷 -{value_expr}%")
            continue


        # SetIgnoreDEFRace(race_id)
        ignore_race = re.match(r"SetIgnoreDEFRace\((\d+)\)", line)
        if ignore_race and condition_met:
            race_name = dependencies.require("race_map").get(int(ignore_race.group(1)), f"種族{ignore_race.group(1)}")
            results.append(f"無視 {race_name} 型怪的物理防禦 +100%")
            continue
            
        # PerfectDamage(1)
        perfect_damage = re.match(r"^PerfectDamage\(1\)$", line.strip())
        if perfect_damage and condition_met:
            results.append(f"武器體型修正 100%")
            continue

        WP_INVESTIGATE_dmg = re.match(r"SetInvestigate()", line)
        if WP_INVESTIGATE_dmg and condition_met:
            results.append(f"武器浸透勁效果")
            results.append(f"無視 全種族 型怪的物理防禦 +100%")
            #context.used_skill_levels[266] = True #會跟目前裝備衝突 改到計算內處理
            continue

        #部位
        dependencies.register_function("","--以下取得角色能力--",[])

        dependencies.register_function("get","取得基礎能力",[
            {"name": "", "type": "var_select", "map": "stat_fields"}
        ])
        dependencies.register_function("GetRefineLevel","取得裝備精煉",[
            {"name": "", "type": "var_select", "map": "equip_sitetype"}
        ])
        dependencies.register_function("GetEquipGradeLevel","取得裝備階級",[
            {"name": "", "type": "var_select", "map": "equip_sitetype"}
        ])
        dependencies.register_function("GetEquipArmorLv","取得防具等級",[
            {"name": "", "type": "var_select", "map": "equip_sitetype"}
        ])
        dependencies.register_function("GetEquipWeaponLv","取得武器等級",[
            {"name": "", "type": "var_select", "map": "equip_sitetype"}
        ])

#==============以上物理判斷

        # === 解析補完：先加入顯示/總效果清單，暫不接入最終傷害公式 ===
        # 注意：名稱刻意與既有傷害公式使用的 key 避開，避免新增解析後改變現有計算結果。


        # 治癒量 Add/SubHealValue(value)
        dependencies.register_function("AddHealValue", "增加治癒量", [{"name": "數值%", "type": "value"}])
        dependencies.register_function("SubHealValue", "減少治癒量", [{"name": "數值%", "type": "value"}])
        heal_value = re.match(r"(Add|Sub)HealValue\s*\((.*)\)\s*$", line)
        if heal_value and condition_met:
            op, args_text = heal_value.groups()
            val = eval_lua_arg(split_lua_args(args_text), 0, 0)
            sign = "+" if op == "Add" else "-"
            results.append(f"治癒量 {sign}{val}%")
            continue

        # 被治癒量 Add/SubHealModifyPercent(value)
        dependencies.register_function("AddHealModifyPercent", "增加被治癒量", [{"name": "數值%", "type": "value"}])
        dependencies.register_function("SubHealModifyPercent", "減少被治癒量", [{"name": "數值%", "type": "value"}])
        heal_modify = re.match(r"(Add|Sub)HealModifyPercent\s*\((.*)\)\s*$", line)
        if heal_modify and condition_met:
            op, args_text = heal_modify.groups()
            val = eval_lua_arg(split_lua_args(args_text), 0, 0)
            sign = "+" if op == "Add" else "-"
            results.append(f"被治癒量 {sign}{val}%")
            continue

        # HP/SP 吸收 Add/SubHPdrain(rate, amount) / Add/SubSPdrain(rate, amount)
        dependencies.register_function("AddHPdrain", "增加HP吸收", [{"name": "機率%", "type": "value"}, {"name": "吸收量%", "type": "value"}])
        dependencies.register_function("SubHPdrain", "減少HP吸收", [{"name": "機率%", "type": "value"}, {"name": "吸收量%", "type": "value"}])
        dependencies.register_function("AddSPdrain", "增加SP吸收", [{"name": "機率%", "type": "value"}, {"name": "吸收量%", "type": "value"}])
        dependencies.register_function("SubSPdrain", "減少SP吸收", [{"name": "機率%", "type": "value"}, {"name": "吸收量%", "type": "value"}])
        drain = re.match(r"(Add|Sub)(HP|SP)drain\s*\((.*)\)\s*$", line)
        if drain and condition_met:
            op, pool, args_text = drain.groups()
            args = split_lua_args(args_text)
            rate = eval_lua_arg(args, 0, 0)
            amount = eval_lua_arg(args, 1, None)
            sign = "+" if op == "Add" else "-"
            if amount is None:
                results.append(f"{pool}吸收 {sign}{rate}%")
            else:
                results.append(f"{pool}吸收機率 {sign}{rate}%")
                results.append(f"{pool}吸收量 {sign}{amount}%")
            continue

        # SP 消耗 Add/SubSPconsumption(value)，以及大小寫技能版本 add/subspconsumption(value, skill_id)
        dependencies.register_function("AddSPconsumption", "增加SP消耗", [{"name": "數值%", "type": "value"}])
        dependencies.register_function("SubSPconsumption", "減少SP消耗", [{"name": "數值%", "type": "value"}])
        sp_consumption = re.match(r"(Add|Sub)SPconsumption\s*\((.*)\)\s*$", line)
        if sp_consumption and condition_met:
            op, args_text = sp_consumption.groups()
            val = eval_lua_arg(split_lua_args(args_text), 0, 0)
            sign = "+" if op == "Add" else "-"
            results.append(f"SP消耗 {sign}{val}%")
            continue

        dependencies.register_function("addspconsumption", "增加指定技能SP消耗%", [{"name": "數值%", "type": "value"}, {"name": "技能", "map": "skill_map"}])
        dependencies.register_function("subspconsumption", "減少指定技能SP消耗%", [{"name": "數值%", "type": "value"}, {"name": "技能", "map": "skill_map"}])
        skill_sp_consumption_pct = re.match(r"(add|sub)spconsumption\s*\((.*)\)\s*$", line)
        if skill_sp_consumption_pct and condition_met:
            op, args_text = skill_sp_consumption_pct.groups()
            args = split_lua_args(args_text)
            val = eval_lua_arg(args, 0, 0)
            try:
                skill_id = int(eval_lua_arg(args, 1, 0))
            except Exception:
                skill_id = 0
            skill_name = dependencies.require("skill_map").get(skill_id, f"技能ID {skill_id}")
            sign = "+" if op == "add" else "-"
            results.append(f"技能【{skill_name}】SP消耗 {sign}{val}%")
            continue

        # 指定技能 SP 消耗 Add/SubSkillSP(skill_id, value)
        dependencies.register_function("AddSkillSP", "增加指定技能SP消耗", [{"name": "技能", "map": "skill_map"}, {"name": "數值", "type": "value"}])
        dependencies.register_function("SubSkillSP", "減少指定技能SP消耗", [{"name": "技能", "map": "skill_map"}, {"name": "數值", "type": "value"}])
        skill_sp = re.match(r"(Add|Sub)SkillSP\s*\((.*)\)\s*$", line)
        if skill_sp and condition_met:
            op, args_text = skill_sp.groups()
            args = split_lua_args(args_text)
            try:
                skill_id = int(eval_lua_arg(args, 0, 0))
            except Exception:
                skill_id = 0
            skill_name = dependencies.require("skill_map").get(skill_id, f"技能ID {skill_id}")
            val = eval_lua_arg(args, 1, 0)
            sign = "+" if op == "Add" else "-"
            results.append(f"技能【{skill_name}】SP消耗 {sign}{val}")
            continue

        # 受近距離物理傷害AddMeleeAttackDamage(0, value)
        # register_function("AddMeleeAttackDamage", "增加近距離物理傷害", [
        #     {"name": "目標", "map": "unit_map"},
        #     {"name": "數值%", "type": "value"}
        # ])
        # register_function("SubMeleeAttackDamage", "減少近距離物理傷害", [
        #     {"name": "目標", "map": "unit_map"},
        #     {"name": "數值%", "type": "value"}
        # ])
        melee_dmg = re.match(r"(Add|Sub)MeleeAttackDamage\(\s*0\s*,\s*(.+)\)", line)
        if melee_dmg and condition_met:
            op, value_expr = melee_dmg.group(1,2)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"受到近距離物理傷害 {sign}{value_expr}%")
            continue

        # 受遠距離物理傷害AddRangeAttackDamage(0, value)
        # register_function("AddRangeAttackDamage", "增加遠距離物理傷害", [
        #     {"name": "目標", "map": "unit_map"},
        #     {"name": "數值%", "type": "value"}
        # ])
        # register_function("SubRangeAttackDamage", "減少遠距離物理傷害", [
        #     {"name": "目標", "map": "unit_map"},
        #     {"name": "數值%", "type": "value"}
        # ])
        range_dmg = re.match(r"(Add|Sub)RangeAttackDamage\(\s*0\s*,\s*(.+)\)", line)
        if range_dmg and condition_met:
            op, value_expr = range_dmg.group(1,2)
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"受到遠距離物理傷害 {sign}{value_expr}%")
            continue


        # 對屬性攻擊耐性 Add/SubAttrTolerace(element, value)
        dependencies.register_function("AddAttrTolerace", "增加屬性攻擊抗性", [{"name": "屬性", "map": "element_map"}, {"name": "數值%", "type": "value"}])
        dependencies.register_function("SubAttrTolerace", "減少屬性攻擊抗性", [{"name": "屬性", "map": "element_map"}, {"name": "數值%", "type": "value"}])
        attr_tol = re.match(r"(Add|Sub)AttrTolerace\s*\((.*)\)\s*$", line)
        if attr_tol and condition_met:
            op, args_text = attr_tol.groups()
            args = split_lua_args(args_text)
            elem_name = map_int_arg(args, 0, dependencies.require("element_map"), "屬性")
            val = eval_lua_arg(args, 1, 0)
            sign = "+" if op == "Add" else "-"
            results.append(f"對 {elem_name} 攻擊抗性 {sign}{val}%")
            continue

        # 對屬性物理攻擊耐性 add/subattrtolerace(element, value)
        dependencies.register_function("addattrtolerace", "增加屬性物理攻擊抗性", [{"name": "屬性", "map": "element_map"}, {"name": "數值%", "type": "value"}])
        dependencies.register_function("subattrtolerace", "減少屬性物理攻擊抗性", [{"name": "屬性", "map": "element_map"}, {"name": "數值%", "type": "value"}])
        p_attr_tol = re.match(r"(add|sub)attrtolerace\s*\((.*)\)\s*$", line)
        if p_attr_tol and condition_met:
            op, args_text = p_attr_tol.groups()
            args = split_lua_args(args_text)
            elem_name = map_int_arg(args, 0, dependencies.require("element_map"), "屬性")
            val = eval_lua_arg(args, 1, 0)
            sign = "+" if op == "add" else "-"
            results.append(f"對 {elem_name} 攻擊抗性 {sign}{val}%")
            continue

        # Add/Sub Damage_Size（受體型物理）
        size_dmg = re.match(r"(Add|Sub)Damage_Size\(\s*0\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if size_dmg and condition_met:            
            op, size_id, value_expr = size_dmg.groups()
            size_str = size_map.get(int(size_id), f"體型{size_id}")
            value_expr = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"受到 {size_str} 敵人的物理傷害 {sign}{value_expr}%")
            continue

        # Add/Sub MDamage_Size（受體型魔法）
        mdamage_size = re.match(r"(Add|Sub)MDamage_Size\(\s*0\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if mdamage_size and condition_met:
            op, size_id, value_expr = mdamage_size.groups()
            size_name = size_map.get(int(size_id), f"尺寸{size_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"受到 {size_name} 敵人的魔法傷害 {sign}{val}%")
            continue

        # 對種族承傷/耐性 Add/SubRaceTolerace(race, value)
        # register_function("AddRaceTolerace", "增加種族抗性", [{"name": "種族", "map": "race_map"}, {"name": "數值%", "type": "value"}])
        # register_function("SubRaceTolerace", "減少種族抗性", [{"name": "種族", "map": "race_map"}, {"name": "數值%", "type": "value"}])
        race_tol = re.match(r"(Add|Sub)RaceTolerace\s*\((.*)\)\s*$", line)
        if race_tol and condition_met:
            op, args_text = race_tol.groups()
            args = split_lua_args(args_text)
            race_name = map_int_arg(args, 0, dependencies.require("race_map"), "種族")
            val = eval_lua_arg(args, 1, 0)
            # Tolerace 是耐性：Add = 承傷下降；Sub = 承傷上升
            sign = "-" if op == "Add" else "+"
            results.append(f"受到 {race_name} 型怪的傷害 {sign}{val}%")
            continue

        # AddDamage_Property（對指定種族與屬性）
        # register_function("AddDamage_Property", "增加屬性對象物理傷害", [
        #     {"name": "目標", "map": "unit_map"},
        #     {"name": "屬性", "map": "element_map"},
        #     {"name": "數值%", "type": "value"}
        # ])
        # register_function("SubDamage_Property", "減少屬性對象物理傷害", [
        #     {"name": "目標", "map": "unit_map"},
        #     {"name": "屬性", "map": "element_map"},
        #     {"name": "數值%", "type": "value"}
        # ])
        add_damage_prop = re.match(r"(Add|Sub)Damage_Property\(\s*0\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if add_damage_prop and condition_met:
            op, elem_id, value_expr = add_damage_prop.groups()
            elem_name = dependencies.require("element_map").get(int(elem_id), f"屬性{elem_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"受到 {elem_name} 對象的物理傷害 {sign}{val}%")
            continue

        # Add/Sub MDamage_Property（對指定種族與屬性）
        # register_function("AddMDamage_Property", "增加屬性對象魔法傷害", [
        #     {"name": "目標", "map": "unit_map"},
        #     {"name": "屬性", "map": "element_map"},
        #     {"name": "數值%", "type": "value"}
        # ])
        # register_function("SubMDamage_Property", "減少屬性對象魔法傷害", [
        #     {"name": "目標", "map": "unit_map"},
        #     {"name": "屬性", "map": "element_map"},
        #     {"name": "數值%", "type": "value"}
        # ])

        add_mdamage_prop = re.match(r"(Add|Sub)MDamage_Property\(\s*0\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
        if add_mdamage_prop and condition_met:
            op, elem_id, value_expr = add_mdamage_prop.groups()
            elem_name = dependencies.require("element_map").get(int(elem_id), f"屬性{elem_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"受到 {elem_name} 對象的魔法傷害 {sign}{val}%")
            continue


        # 受到階級敵人傷害 Add/SubClassAddDamage(class_id, 0, value)
        class_dmg = re.match(r"Class(Add|Sub)Damage\(\s*(\d+)\s*,\s*0\s*,\s*(.+?)\s*\)", line)
        if class_dmg and condition_met:
            op, class_id, expr_src = class_dmg.groups()
            class_name = dependencies.require("class_map").get(int(class_id), f"階級{class_id}")
            val = safe_eval_expr(expr_src, variables, get_values, refine_inputs, grade)
            sign = "+" if op == "Add" else "-"
            results.append(f"受到 {class_name} 階級的物理傷害 {sign}{val}%")
            continue

        # # 自身對種族承傷 RaceSub/AddDamageSelf(race, value)
        # register_function("RaceSubDamageSelf", "減少自身受到種族傷害", [{"name": "種族", "map": "race_map"}, {"name": "數值%", "type": "value"}])
        # register_function("RaceAddDamageSelf", "增加自身受到種族傷害", [{"name": "種族", "map": "race_map"}, {"name": "數值%", "type": "value"}])
        race_self = re.match(r"Race(Sub|Add)DamageSelf\s*\((.*)\)\s*$", line)
        if race_self and condition_met:
            op, args_text = race_self.groups()
            args = split_lua_args(args_text)
            race_name = map_int_arg(args, 0, dependencies.require("race_map"), "種族")
            val = eval_lua_arg(args, 1, 0)
            sign = "-" if op == "Sub" else "+"
            results.append(f"受到 {race_name} 型怪的傷害 {sign}{val}%")
            continue

        # # 受到某種族武器傷害 Add/SubAttackedWeaponPowerRaceTolerance(race, value)
        # register_function("AddAttackedWeaponPowerRaceTolerance", "增加受到種族武器傷害", [{"name": "種族", "map": "race_map"}, {"name": "數值%", "type": "value"}])
        # register_function("SubAttackedWeaponPowerRaceTolerance", "減少受到種族武器傷害", [{"name": "種族", "map": "race_map"}, {"name": "數值%", "type": "value"}])
        # race_weapon_tol = re.match(r"(Add|Sub)AttackedWeaponPowerRaceTolerance\s*\((.*)\)\s*$", line)
        # if race_weapon_tol and condition_met:
        #     op, args_text = race_weapon_tol.groups()
        #     args = split_lua_args(args_text)
        #     race_name = map_int_arg(args, 0, race_map, "種族")
        #     val = eval_lua_arg(args, 1, 0)
        #     sign = "+" if op == "Add" else "-"
        #     results.append(f"受到 {race_name} 型怪的武器傷害 {sign}{val}%")
        #     continue

        # # 遠距離武器傷害/受到遠距離武器傷害
        # register_function("AddAttackRangeWeaponPower", "增加遠距離武器傷害", [{"name": "目標", "map": "unit_map"}, {"name": "數值%", "type": "value"}])
        # register_function("SubAttackRangeWeaponPower", "減少遠距離武器傷害", [{"name": "目標", "map": "unit_map"}, {"name": "數值%", "type": "value"}])
        # atk_range_weapon = re.match(r"(Add|Sub)AttackRangeWeaponPower\s*\((.*)\)\s*$", line)
        # if atk_range_weapon and condition_met:
        #     op, args_text = atk_range_weapon.groups()
        #     args = split_lua_args(args_text)
        #     val = eval_lua_arg(args, 1 if len(args) > 1 else 0, 0)
        #     sign = "+" if op == "Add" else "-"
        #     results.append(f"遠距離武器傷害 {sign}{val}%")
        #     continue

        # register_function("AddAttackedRangeWeaponPower", "增加受到遠距離武器傷害", [{"name": "目標", "map": "unit_map"}, {"name": "數值%", "type": "value"}])
        # register_function("SubAttackedRangeWeaponPower", "減少受到遠距離武器傷害", [{"name": "目標", "map": "unit_map"}, {"name": "數值%", "type": "value"}])
        # attacked_range_weapon = re.match(r"(Add|Sub)AttackedRangeWeaponPower\s*\((.*)\)\s*$", line)
        # if attacked_range_weapon and condition_met:
        #     op, args_text = attacked_range_weapon.groups()
        #     args = split_lua_args(args_text)
        #     val = eval_lua_arg(args, 1 if len(args) > 1 else 0, 0)
        #     sign = "+" if op == "Add" else "-"
        #     results.append(f"受到遠距離武器傷害 {sign}{val}%")
        #     continue

        # # 只補反向版本，避免覆蓋既有 Add 版本的公式輸出 key
        # register_function("SubBowAttackDamage", "減少弓攻擊力", [{"name": "目標", "map": "unit_map"}, {"name": "數值%", "type": "value"}])
        # sub_bow = get_lua_call_args("SubBowAttackDamage", line)
        # if sub_bow and condition_met:
        #     val = eval_lua_arg(sub_bow, 1 if len(sub_bow) > 1 else 0, 0)
        #     results.append(f"弓攻擊力（未套公式） -{val}%")
        #     continue


        # register_function("SubGuideAttack", "減少誘導攻擊機率", [{"name": "數值%", "type": "value"}])
        # sub_guide = get_lua_call_args("SubGuideAttack", line)
        # if sub_guide and condition_met:
        #     val = eval_lua_arg(sub_guide, 0, 0)
        #     results.append(f"誘導攻擊機率 -{val}%")
        #     continue

        # 對種族 CRI Add/SubCRIPercent_Race(race, value)
        dependencies.register_function("AddCRIPercent_Race", "增加對種族CRI", [{"name": "種族", "map": "race_map"}, {"name": "數值%", "type": "value"}])
        dependencies.register_function("SubCRIPercent_Race", "減少對種族CRI", [{"name": "種族", "map": "race_map"}, {"name": "數值%", "type": "value"}])
        cri_race = re.match(r"(Add|Sub)CRIPercent_Race\s*\((.*)\)\s*$", line)
        if cri_race and condition_met:
            op, args_text = cri_race.groups()
            args = split_lua_args(args_text)
            race_name = map_int_arg(args, 0, dependencies.require("race_map"), "種族")
            val = eval_lua_arg(args, 1, 0)
            sign = "+" if op == "Add" else "-"
            results.append(f"對 {race_name} 型怪的CRI {sign}{val}%")
            continue

        # 反射類
        dependencies.register_function("AddMeleeAttackReflect", "增加近距離物理反射", [{"name": "數值%", "type": "value"}])
        dependencies.register_function("SubMeleeAttackReflect", "減少近距離物理反射", [{"name": "數值%", "type": "value"}])
        melee_reflect = re.match(r"(Add|Sub)MeleeAttackReflect\s*\((.*)\)\s*$", line)
        if melee_reflect and condition_met:
            op, args_text = melee_reflect.groups()
            val = eval_lua_arg(split_lua_args(args_text), 0, 0)
            sign = "+" if op == "Add" else "-"
            results.append(f"近距離物理反射 {sign}{val}%")
            continue

        dependencies.register_function("AddReflectMagic", "增加魔法反射", [{"name": "數值%", "type": "value"}])
        dependencies.register_function("SubReflectMagic", "減少魔法反射", [{"name": "數值%", "type": "value"}])
        magic_reflect = re.match(r"(Add|Sub)ReflectMagic\s*\((.*)\)\s*$", line)
        if magic_reflect and condition_met:
            op, args_text = magic_reflect.groups()
            val = eval_lua_arg(split_lua_args(args_text), 0, 0)
            sign = "+" if op == "Add" else "-"
            results.append(f"魔法反射 {sign}{val}%")
            continue

        dependencies.register_function("AddReflectTolerace", "增加反射傷害耐性", [{"name": "數值%", "type": "value"}])
        dependencies.register_function("SubReflectTolerace", "減少反射傷害耐性", [{"name": "數值%", "type": "value"}])
        reflect_tol = re.match(r"(Add|Sub)ReflectTolerace\s*\((.*)\)\s*$", line)
        if reflect_tol and condition_met:
            op, args_text = reflect_tol.groups()
            val = eval_lua_arg(split_lua_args(args_text), 0, 0)
            sign = "+" if op == "Add" else "-"
            results.append(f"反射傷害耐性 {sign}{val}%")
            continue

        # 增減「指定技能傷害(裝備段)」合併處理
        # register_function("AddDamage_SKID", "增加受到技能傷害", [
        #     {"name": "目標", "map": "unit_map"},
        #     {"name": "技能", "map": "skill_map"},
        #     {"name": "數值%", "type": "value"}
        # ])
        # register_function("SubDamage_SKID", "減少受到技能傷害", [
        #     {"name": "目標", "map": "unit_map"},
        #     {"name": "技能", "map": "skill_map"},
        #     {"name": "數值%", "type": "value"}
        # ])

        add_sub_dmg_skid = re.match(r"(Add|Sub)Damage_SKID\(\s*0\s*,\s*(\d+)\s*,\s*(.+)\s*\)\s*$", line)
        if add_sub_dmg_skid and condition_met:
            op, skill_id, value_expr = add_sub_dmg_skid.groups()
            skill_name = dependencies.require("skill_map").get(int(skill_id), f"技能ID {skill_id}")
            val = safe_eval_expr(value_expr, variables, get_values, refine_inputs, grade)

            if isinstance(val, int):
                sign = "+" if op == "Add" else "-"
                results.append(f"受到技能【{skill_name}】傷害 {sign}{val}%")
            else:
                sign = "+" if op == "Add" else "-"
                results.append(f"受到技能【{skill_name}】傷害 {sign}({val})%（無法解析）")
            continue

        # # Reset 類：輸出為「取消無視」，避免被現有無視防禦公式讀取
        # reset_ignore_class = get_lua_call_args("ResetIgnoreDEFClass", line)
        # if reset_ignore_class and condition_met:
        #     class_name = map_int_arg(reset_ignore_class, 0, class_map, "階級")
        #     results.append(f"取消無視 {class_name} 階級的物理防禦")
        #     continue

        # reset_ignore_class_pct = get_lua_call_args("ResetIgnoreDEFClass_Percent", line) or get_lua_call_args("ResetIgnoreDefClass_Percent", line)
        # if reset_ignore_class_pct and condition_met:
        #     class_name = map_int_arg(reset_ignore_class_pct, 0, class_map, "階級")
        #     val = eval_lua_arg(reset_ignore_class_pct, 1, 0)
        #     results.append(f"取消無視 {class_name} 階級的物理防禦 {val}%")
        #     continue

        # reset_ignore_race = get_lua_call_args("ResetIgnoreDEFRace", line)
        # if reset_ignore_race and condition_met:
        #     race_name = map_int_arg(reset_ignore_race, 0, race_map, "種族")
        #     results.append(f"取消無視 {race_name} 型怪的物理防禦")
        #     continue

        # reset_ignore_race_pct = get_lua_call_args("ResetIgnoreDefRace_Percent", line)
        # if reset_ignore_race_pct and condition_met:
        #     race_name = map_int_arg(reset_ignore_race_pct, 0, race_map, "種族")
        #     val = eval_lua_arg(reset_ignore_race_pct, 1, 0)
        #     results.append(f"取消無視 {race_name} 型怪的物理防禦 {val}%")
        #     continue

        # reset_ignore_mdef_class = get_lua_call_args("ResetIgnoreMdefClass", line)
        # if reset_ignore_mdef_class and condition_met:
        #     class_name = map_int_arg(reset_ignore_mdef_class, 0, class_map, "階級")
        #     val = eval_lua_arg(reset_ignore_mdef_class, 1, None)
        #     if val is None:
        #         results.append(f"取消無視 {class_name} 階級的魔法防禦")
        #     else:
        #         results.append(f"取消無視 {class_name} 階級的魔法防禦 {val}%")
        #     continue

        # reset_ignore_mdef_race = get_lua_call_args("ResetIgnoreMdefRace", line)
        # if reset_ignore_mdef_race and condition_met:
        #     race_name = map_int_arg(reset_ignore_mdef_race, 0, race_map, "種族")
        #     val = eval_lua_arg(reset_ignore_mdef_race, 1, None)
        #     if val is None:
        #         results.append(f"取消無視 {race_name} 型怪的魔法防禦")
        #     else:
        #         results.append(f"取消無視 {race_name} 型怪的魔法防禦 {val}%")
        #     continue

        # 純狀態/特殊效果，先顯示不計算
        # register_function("NoDispell", "詠唱不中斷", [])
        # register_function("Magicimmune", "不受魔法效果影響", [])
        # register_function("NoJamstone", "不消耗魔力礦石", [])
        # register_function("NoMadogearfuel", "不消耗魔導機甲燃料", [])
        # register_function("AddNeverknockback", "不會被擊退", [])
        # register_function("Clairvoyance", "可看見隱匿目標", [])
        # register_function("Reincarnation", "復活時恢復HP/SP", [])
        # register_function("SplashAttack", "普攻範圍增加", [])
        plain_effect_map = {
            "NoDispell": "詠唱不中斷",
            "Magicimmune": "不受魔法效果影響",
            "NoJamstone": "使用技能不消耗魔力礦石",
            "NoMadogearfuel": "不消耗魔導機甲燃料",
            "AddNeverknockback": "不會被擊退",
            "Clairvoyance": "可看見隱匿目標",
            "Reincarnation": "復活時恢復 HP/SP 100%",
            "SplashAttack": "普攻範圍增加",
        }
        plain_effect = re.match(r"(NoDispell|Magicimmune|NoJamstone|NoMadogearfuel|AddNeverknockback|Clairvoyance|Reincarnation|SplashAttack)\s*(?:\((.*)\))?\s*$", line)
        if plain_effect and condition_met:
            results.append(plain_effect_map.get(plain_effect.group(1), plain_effect.group(1)))
            continue

        # Condition(effect_id, duration, chance)
        # register_function("Condition", "賦予狀態", [
        #     {"name": "狀態", "type": "value"},
        #     {"name": "持續時間", "type": "value"},
        #     {"name": "機率", "type": "value"}
        # ])
        condition_effect = get_lua_call_args("Condition", line)
        if condition_effect and condition_met:
            status_map = {
                13: "霸體",
                14: "移動速度增加",
                15: "攻擊速度增加",
                21: "集中",
                26: "看見隱匿目標",
            }
            try:
                status_id = int(eval_lua_arg(condition_effect, 0, 0))
            except Exception:
                status_id = 0
            status_name = status_map.get(status_id, f"狀態ID {status_id}")
            duration = eval_lua_arg(condition_effect, 1, None)
            chance = eval_lua_arg(condition_effect, 2, None)
            extra = []
            if duration is not None:
                extra.append(f"持續 {duration}")
            if chance is not None:
                extra.append(f"機率 {chance}%")
            results.append(f"賦予狀態：{status_name}" + (f"（{'，'.join(extra)}）" if extra else ""))
            continue

#待處理判斷
#物理(物理反射%、對屬性減少傷害、對某種族的CRI+%
#魔法(魔法反射
#================以下判斷失敗或不成立區塊
        IGNORE_PREFIXES = ("local ", "Stat ", "{Type ", "}")

        if not hide_unrecognized:
            stripped = original_line.strip()
            if stripped and not stripped.startswith("--"):
                if not condition_met:
                    results.append(f"⛔ 已跳過（條件不成立）: {original_line}")
                else:
                    if stripped.startswith(IGNORE_PREFIXES):
                        continue

                    results.append(f"🟡line解析 無法辨識: {original_line}")


    for skill_name, total_ms in skill_delay_accum.items():
        sec = abs(total_ms) / 1000
        if total_ms < 0:
            results.append(f"技能【{skill_name}】冷卻時間 -{sec:.2f} 秒")
        else:
            results.append(f"技能【{skill_name}】冷卻時間 +{sec:.2f} 秒")

        # 所有邏輯都未匹配時：顯示無法辨識語句

    def _format_number(value):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if isinstance(value, int):
            return f"{value:+d}"
        return f"{value:+.2f}".rstrip("0").rstrip(".")

    def combine_effects(results):
        combined = defaultdict(float)
        final_lines = []
        
        for line in results:
            # 支援加總格式：「效果說明 +數值」、「效果說明 -數值%」與「效果說明 -0.20 秒」
            match = re.match(r"(.+?) ([+-]\d+(?:\.\d+)?)(%|秒)?$", line)
            if match:
                key = match.group(1).strip()
                value = float(match.group(2))
                suffix = match.group(3) or ""
                combined[(key, suffix)] += value
            else:
                final_lines.append(line)

        for (key, suffix), total in combined.items():
            final_lines.append(f"{key} {_format_number(total)}{suffix}")

        return final_lines

    def filter_hidden_effects(lines):
        if not hide_physical and not hide_magical:
            return lines

        physical_keywords = (
            "物理", "ATK", "P.ATK", "CRI", "C.RATE", "HIT",
            "近距離", "遠距離", "爆擊", "暴擊", "武器", "誘導攻擊"
        )
        magical_keywords = (
            "魔法", "MATK", "S.MATK", "MDEF", "MRES", "變動詠唱", "固定詠唱", "詠唱"
        )

        filtered = []
        for line in lines:
            if hide_physical and any(keyword in line for keyword in physical_keywords):
                continue
            if hide_magical and any(keyword in line for keyword in magical_keywords):
                continue
            filtered.append(line)
        return filtered

   
    final_results = combine_effects(results) if hide_unrecognized else results
    return filter_hidden_effects(final_results)
# === STAGE 3 LUA PARSER 結束 ===


# === STAGE 4 效果彙總開始 ===

@dataclass
class EquipmentSlotInput:
    """單一 Desktop 裝備 slot 的不依賴 Qt 快照。"""

    part_name: str
    slot_id: int
    equip_name: str = ""
    grade: int = 0
    cards: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class EquipmentEffectRequest:
    """供未來完整裝備計算器使用、可序列化的輸入邊界。

    Stage 4 在 Desktop 只負責建立 / 快照這個 request；既有 display_all_effects
    迴圈仍控制裝備遍歷，因此不會一次改掉全部計算行為。
    """

    get_values: dict[int, Any] = field(default_factory=dict)
    refine_inputs: dict[int, int] = field(default_factory=dict)
    slots: list[EquipmentSlotInput] = field(default_factory=list)
    enabled_skill_names: list[str] = field(default_factory=list)
    hide_unrecognized: bool = False
    hide_physical: bool = False
    hide_magical: bool = False
    show_source: bool = False
    sort_mode: str = "來源順序"


@dataclass
class EffectContribution:
    value: float | int
    source: str


@dataclass
class EffectTotal:
    key: str
    unit: str
    total: float | int
    entries: list[EffectContribution] = field(default_factory=list)


@dataclass
class EquipmentEffectResult:
    """完整計算器遷移前先導入、方便 API 使用的結果結構。"""

    effects: list[EffectTotal] = field(default_factory=list)
    combined_lines: list[str] = field(default_factory=list)
    combo_lines: list[str] = field(default_factory=list)
    triggered_combo_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Desktop 過渡期相容欄位；API 應優先使用 `effects`。
    legacy_effect_dict: dict[tuple[str, str], list[tuple[float | int, str]]] = field(default_factory=dict, repr=False)


def normalize_effect_key(key: str) -> str:
    """舊版 Desktop normalize_effect_key() 的 Core 對應實作。"""
    key = str(key).strip()
    # 完整保留目前觀察到的 Desktop 語意。這些替換看起來可能
    # 有些重複，但在職責搬進 Core 的過渡期間保留它們，
    # 可以避免輸出結果跟著改變。
    key = key.replace("固定詠唱時間", "固定詠唱時間")
    key = key.replace("變動詠唱時間", "變動詠唱時間")
    return key


def try_extract_effect(line: str):
    """依舊版 Desktop 語意解析一行已渲染效果文字。"""
    line = str(line)

    match = re.match(r"(.+?)\s*([+-]?[0-9]+)\%$", line)
    if match:
        return match.group(1).strip(), int(match.group(2)), "%"

    match = re.match(r"(.+?)\s*([+-]?[0-9.]+)\s*秒$", line)
    if match:
        return match.group(1).strip(), float(match.group(2)), "秒"

    match = re.match(r"(.+?)\s*([+-]?[0-9]+)$", line)
    if match:
        return match.group(1).strip(), int(match.group(2)), ""

    return None


def filter_effects(
    effects: Iterable[str],
    *,
    hide_unrecognized: bool = False,
    hide_physical: bool = False,
    hide_magical: bool = False,
) -> list[str]:
    """ItemSearchApp.filter_effects() 的不依賴 Qt 對應實作。"""
    hide_keywords: list[str] = []
    if hide_physical:
        hide_keywords.extend(["物理", "爆擊", "CRI", "武器ATK", "P.ATK"])
    if hide_magical:
        hide_keywords.extend(["魔法", "武器MATK", "S.MATK"])

    filtered = [
        line for line in effects
        if not any(keyword in line for keyword in hide_keywords)
    ]

    if hide_unrecognized:
        filtered = [
            line for line in filtered
            if not line.startswith(("🟡", "⚠️", "❌", "📌", "✅", "⛔", "可使用"))
        ]
    return filtered


def add_effect_lines(
    effect_dict: dict[tuple[str, str], list[tuple[float | int, str]]],
    lines: Iterable[str],
    source_label: str,
) -> dict[tuple[str, str], list[tuple[float | int, str]]]:
    """把 parser 輸出累積成舊版 effect_dict 結構。"""
    for line in lines:
        if not str(line).strip():
            continue
        parsed = try_extract_effect(str(line))
        if parsed:
            key, value, unit = parsed
            key = normalize_effect_key(key)
            effect_dict.setdefault((key, unit), []).append((value, source_label))
        else:
            text = str(line).strip()
            if text:
                key = normalize_effect_key(text)
                effect_dict.setdefault((key, ""), []).append((0, source_label))
    return effect_dict


def extract_combi_ids(block_text: str) -> list[int]:
    """依舊版 Desktop 語意抽出 Combiitem ID。"""
    match = re.search(r"Combiitem\s*=\s*\{([^}]*)}", str(block_text))
    if match:
        # 刻意保留舊行為：格式錯誤的非整數資料會直接拋出例外。
        return [int(item.strip()) for item in match.group(1).split(",")]
    return []


def extract_combo_items(combo_text: str) -> set[int]:
    """依舊版 Desktop 語意抽出 Item={...} 內的 ID。"""
    match = re.search(r"Item\s*=\s*\{([^}]*)}", str(combo_text))
    if match:
        items = match.group(1).split(",")
        result: set[int] = set()
        for raw in items:
            raw = raw.strip()
            if raw.isdigit():
                result.add(int(raw))
            elif raw != "":
                print(f"⚠️ 無法轉換為整數: '{raw}' in block: {combo_text}")
        return result
    return set()


def get_custom_sort_value(
    key: str,
    sort_mode: str,
    custom_sort_orders: dict[str, list[str]],
) -> int:
    order_list = custom_sort_orders.get(sort_mode, [])
    for idx, keyword in enumerate(order_list):
        if keyword in key:
            return idx
    return len(order_list)


def _sorted_effect_items(
    effect_dict: dict[tuple[str, str], list[tuple[float | int, str]]],
    *,
    sort_mode: str,
    custom_sort_orders: dict[str, list[str]] | None = None,
):
    custom_sort_orders = custom_sort_orders or {}
    if sort_mode == "來源順序":
        return list(effect_dict.items())
    if sort_mode == "依名稱":
        return sorted(effect_dict.items(), key=lambda item: (item[0][0], item[0][1]))
    if sort_mode in custom_sort_orders:
        return sorted(
            effect_dict.items(),
            key=lambda item: (
                get_custom_sort_value(item[0][0], sort_mode, custom_sort_orders),
                item[0][0],
            ),
        )
    return list(effect_dict.items())


def build_effect_totals(
    effect_dict: dict[tuple[str, str], list[tuple[float | int, str]]],
    *,
    sort_mode: str = "來源順序",
    custom_sort_orders: dict[str, list[str]] | None = None,
) -> list[EffectTotal]:
    """把舊版 tuple-key dict 轉成方便 API 使用的有序 list。"""
    totals: list[EffectTotal] = []
    for (key, unit), entries in _sorted_effect_items(
        effect_dict,
        sort_mode=sort_mode,
        custom_sort_orders=custom_sort_orders,
    ):
        total = sum(value for value, _ in entries)
        if unit == "秒":
            total = round(total, 1)
        totals.append(
            EffectTotal(
                key=key,
                unit=unit,
                total=total,
                entries=[
                    EffectContribution(value=value, source=source)
                    for value, source in entries
                ],
            )
        )
    return totals


def format_effect_dict(
    effect_dict: dict[tuple[str, str], list[tuple[float | int, str]]],
    *,
    show_source: bool = False,
    sort_mode: str = "來源順序",
    custom_sort_orders: dict[str, list[str]] | None = None,
) -> list[str]:
    """依既有格式輸出最終 Desktop 效果表。"""
    combined: list[str] = []
    totals = build_effect_totals(
        effect_dict,
        sort_mode=sort_mode,
        custom_sort_orders=custom_sort_orders,
    )

    for item in totals:
        if item.unit == "秒":
            value_str = f"{float(item.total):.1f}{item.unit}"
        else:
            value_str = f"{item.total:+g}{item.unit}"

        if show_source:
            for entry in item.entries:
                if item.unit == "秒":
                    val_str = f"{float(entry.value):.1f}{item.unit}"
                else:
                    val_str = f"{entry.value:+g}{item.unit}"
                combined.append(f"{item.key} {val_str}  ← 〔{entry.source}〕")
            combined.append(f"🧮↳ {item.key} {value_str}  ← 〔總和〕🧮")
            combined.append(" ")
        else:
            combined.append(f"{item.key} {value_str}")

    return combined

# === STAGE 4 效果彙總結束 ===


# === STAGE 5 裝備計算核心開始 ===

@dataclass
class EquipmentCalculationData:
    """Desktop 與未來 Web request 共用、以唯讀為主的資料。

    此物件刻意不包含任何每位使用者 / request 專屬的可變戰鬥狀態。Desktop 可以
    讓這些欄位直接指向既有已載入 dictionary；Web process 則可在啟動時建立一次，
    後續重複供多個 request 使用。
    """

    parsed_items: dict[int, dict[str, Any]] = field(default_factory=dict)
    equipment_data: dict[int, str] = field(default_factory=dict)
    skill_entries: dict[str, Any] = field(default_factory=dict)
    skillbuff_text: str = ""
    skill_map: dict[int, str] = field(default_factory=dict)
    unit_map: dict[Any, Any] = field(default_factory=dict)
    size_map: dict[Any, Any] = field(default_factory=dict)
    effect_map: dict[Any, Any] = field(default_factory=dict)
    custom_sort_orders: dict[str, list[str]] = field(default_factory=dict)
    job_dict: dict[Any, dict[str, Any]] = field(default_factory=dict)
    stat_name_sets: dict[str, list[str]] = field(default_factory=dict)


def _iter_item_ids_by_name(
    parsed_items: dict[int, dict[str, Any]],
    name: str,
):
    """依舊版 Desktop 相同的插入順序逐一產生所有符合的 ID。"""
    for item_id, item in parsed_items.items():
        if item.get("name") == name:
            yield item_id


def _parse_effect_block_for_equipment_calc(
    block_text: str,
    request: EquipmentEffectRequest,
    data: EquipmentCalculationData,
    *,
    grade: Any,
    current_location_slot: int | None,
    context: CalculationContext,
    dependencies: CoreDependencies,
) -> list[str]:
    try:
        parser = parse_lua_effects_with_variables
    except NameError as exc:
        raise RuntimeError(
            "Lua parser 尚未存在於 ro_core.py；請先完成 Stage 3。"
        ) from exc

    effects = parser(
        block_text,
        request.refine_inputs,
        request.get_values,
        grade,
        data.unit_map,
        data.size_map,
        data.effect_map,
        hide_unrecognized=request.hide_unrecognized,
        hide_physical=request.hide_physical,
        hide_magical=request.hide_magical,
        current_location_slot=current_location_slot,
        context=context,
        dependencies=dependencies,
    )
    return filter_effects(
        effects,
        hide_unrecognized=request.hide_unrecognized,
        hide_physical=request.hide_physical,
        hide_magical=request.hide_magical,
    )


def _add_numeric_only_effect_lines(
    effect_dict: dict[tuple[str, str], list[tuple[float | int, str]]],
    lines: Iterable[str],
    source_label: str,
) -> None:
    """舊版技能 / 料理行為：只有成功解析的數值行會進入總效果。"""
    for line in lines:
        if not str(line).strip():
            continue
        parsed = try_extract_effect(str(line))
        if not parsed:
            continue
        key, value, unit = parsed
        key = normalize_effect_key(key)
        effect_dict.setdefault((key, unit), []).append((value, source_label))


def _add_combo_effect_lines_legacy(
    effect_dict: dict[tuple[str, str], list[tuple[float | int, str]]],
    lines: Iterable[str],
    source_label: str,
) -> None:
    """保留舊版 display_all_effects() 使用的 combo-total 正則語意。"""
    for line in lines:
        match = re.match(r"(.+?) ([+\-]?\d+(?:\.\d+)?)(%|秒)?", str(line))
        if not match:
            continue
        key = match.group(1).strip()
        raw_value = match.group(2)
        value: float | int = float(raw_value) if "." in raw_value else int(raw_value)
        unit = match.group(3) or ""
        if not unit and "時間" in key:
            unit = "秒"
        effect_dict.setdefault((key, unit), []).append((value, f"套裝：{source_label}"))


def _apply_skillbuff_text_into_effect_dict(
    effect_dict: dict[tuple[str, str], list[tuple[float | int, str]]],
    request: EquipmentEffectRequest,
    data: EquipmentCalculationData,
    *,
    grade: Any,
    context: CalculationContext,
    dependencies: CoreDependencies,
) -> None:
    """Desktop apply_skill_buffs_into_effect_dict() 的 Core 版本。"""
    content = data.skillbuff_text or ""
    if not content:
        return

    def skill_level(skill_id: int) -> int:
        return context.enabled_skill_levels.get(skill_id, 0)

    # 保留舊版迭代語意：直接使用目前的 enabled-skill dictionary。
    for skill_id, level in context.enabled_skill_levels.items():
        pattern = rf"\[{skill_id}\]\s*=\s*\{{(.*?)\}}"
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            continue

        block = match.group(1)
        block = re.sub(
            r"GSklv\(\s*(\d+)\s*\)",
            lambda m: str(skill_level(int(m.group(1)))),
            block,
            flags=re.IGNORECASE,
        )

        effects = parse_lua_effects_with_variables(
            block,
            request.refine_inputs,
            request.get_values,
            grade,
            data.unit_map,
            data.size_map,
            data.effect_map,
            hide_unrecognized=True,
            current_location_slot=None,
            context=context,
            dependencies=dependencies,
        )

        skill_name = data.skill_map.get(skill_id, f"技能ID {skill_id}")
        source = f"技能：{skill_name} Lv.{level}"
        for line in effects:
            if str(line).startswith(("📌", "✅", "❌")):
                continue
            parsed = re.match(
                r"(.+?)\s*([+-]?\d+(?:\.\d+)?)(?:\s*([^\d\s]+))?$",
                str(line),
            )
            if not parsed:
                continue
            key, value_text, unit = parsed.groups()
            unit = unit or ""
            try:
                value = float(value_text)
            except (TypeError, ValueError):
                continue
            display_value: float | int = int(value) if value.is_integer() else round(value, 1)
            effect_dict.setdefault((key.strip(), unit), []).append((display_value, source))


def calculate_equipment_effects(
    request: EquipmentEffectRequest,
    data: EquipmentCalculationData,
    *,
    context: CalculationContext | None = None,
    dependencies: CoreDependencies | None = None,
) -> EquipmentEffectResult:
    """在不依賴 Qt 的情況下計算全部裝備效果。

    這是 Stage 5 的 Desktop / Web 共用邊界。`request` 是每位使用者的輸入，
    `data` 是以唯讀為主的共用遊戲資料，`context` 是單次計算可變狀態，
    `dependencies` 則存放 Lua parser 共用的查表 registry。
    """
    if not isinstance(request, EquipmentEffectRequest):
        raise TypeError("request 必須是 EquipmentEffectRequest")
    if not isinstance(data, EquipmentCalculationData):
        raise TypeError("data 必須是 EquipmentCalculationData")

    context = context or CalculationContext()
    dependencies = dependencies or CoreDependencies()
    context.bind_inputs(
        get_values=request.get_values,
        refine_inputs=request.refine_inputs,
    )

    # Stage 6：在解析 Lua 前先建立 base / job / base-equipment Stat context。
    precompute_base_equipment_stats(
        request,
        data,
        context=context,
        dependencies=dependencies,
    )

    effect_dict: dict[tuple[str, str], list[tuple[float | int, str]]] = {}
    warnings: list[str] = []
    combo_lines: list[str] = []
    triggered_combos: set[int] = set()
    triggered_combo_ids: list[int] = []
    legacy_grade: Any = 0

    # 舊版 Desktop 會先清空所有裝備部位，再重新建立 map。
    slot_ids = set(request.refine_inputs.keys())
    slot_ids.update(slot.slot_id for slot in request.slots)
    for slot_id in slot_ids:
        context.slot_item_id_map[slot_id] = 0

    # 裝備 / 卡片 / 手動輸入的附加效果文字。
    for slot in request.slots:
        if slot.equip_name:
            source = f"{slot.part_name}：{slot.equip_name}"
            for item_id in _iter_item_ids_by_name(data.parsed_items, slot.equip_name):
                if item_id not in data.equipment_data:
                    continue
                context.slot_item_id_map[slot.slot_id] = item_id
                legacy_grade = slot.grade
                lines = _parse_effect_block_for_equipment_calc(
                    data.equipment_data[item_id],
                    request,
                    data,
                    grade=slot.grade,
                    current_location_slot=slot.slot_id,
                    context=context,
                    dependencies=dependencies,
                )
                add_effect_lines(effect_dict, lines, source)

        for card_name in slot.cards:
            if not card_name:
                continue
            source = f"{slot.part_name}：{card_name}"
            for item_id in _iter_item_ids_by_name(data.parsed_items, card_name):
                if item_id not in data.equipment_data:
                    continue
                legacy_grade = slot.grade
                lines = _parse_effect_block_for_equipment_calc(
                    data.equipment_data[item_id],
                    request,
                    data,
                    grade=slot.grade,
                    current_location_slot=slot.slot_id,
                    context=context,
                    dependencies=dependencies,
                )
                add_effect_lines(effect_dict, lines, source)

        if slot.note:
            legacy_grade = slot.grade
            lines = _parse_effect_block_for_equipment_calc(
                slot.note,
                request,
                data,
                grade=slot.grade,
                current_location_slot=slot.slot_id,
                context=context,
                dependencies=dependencies,
            )
            add_effect_lines(effect_dict, lines, f"{slot.part_name}：詞條")

    # 已啟用技能 / 料理資料；保留 skill_entries 原始順序。
    enabled_names = set(request.enabled_skill_names)
    for skill_name, entry in data.skill_entries.items():
        if skill_name not in enabled_names:
            continue
        code = entry.get("code", [])
        code_block = code if isinstance(code, str) else "\n".join(code)
        legacy_grade = 0
        lines = _parse_effect_block_for_equipment_calc(
            code_block,
            request,
            data,
            grade=0,
            current_location_slot=None,
            context=context,
            dependencies=dependencies,
        )
        source = f"{entry.get('type', '技能')}：{skill_name}"
        _add_numeric_only_effect_lines(effect_dict, lines, source)

    # 比照 Desktop，直接由名稱收集已裝備 ID（裝備 + 卡片）。
    equipped_ids: set[int] = set()
    for slot in request.slots:
        if slot.equip_name:
            equipped_ids.update(_iter_item_ids_by_name(data.parsed_items, slot.equip_name))
        for card_name in slot.cards:
            if card_name:
                equipped_ids.update(_iter_item_ids_by_name(data.parsed_items, card_name))

    grade_map = {slot.slot_id: slot.grade for slot in request.slots}
    # 舊版 display_all_effects 會把迴圈最後一個 part_name 給 combo 的 GetLocation() 使用。
    # 保留這個可觀察行為，避免 combo 計算在重構時被悄悄改變。
    legacy_combo_slot = request.slots[-1].slot_id if request.slots else None

    for item_id in equipped_ids:
        block_text = data.equipment_data.get(item_id)
        if not block_text:
            continue
        for combo_id in extract_combi_ids(block_text):
            if combo_id in triggered_combos:
                continue
            combo_block = data.equipment_data.get(combo_id)
            if not combo_block:
                continue
            combo_items = extract_combo_items(combo_block)
            if not combo_items.issubset(equipped_ids):
                continue

            triggered_combos.add(combo_id)
            triggered_combo_ids.append(combo_id)
            legacy_grade = grade_map
            lines = _parse_effect_block_for_equipment_calc(
                combo_block,
                request,
                data,
                grade=grade_map,
                current_location_slot=legacy_combo_slot,
                context=context,
                dependencies=dependencies,
            )

            combo_item_names = [
                f"[{data.parsed_items.get(iid, {}).get('name', f'ID:{iid}')}]"
                for iid in combo_items
            ]
            source_label = "、".join(combo_item_names) if combo_item_names else f"套裝ID {combo_id}"
            if request.show_source:
                combo_lines.append(f"🧩套裝來源：{source_label}")
                combo_lines.extend(f"　　{line}" for line in lines)
            else:
                combo_lines.extend(lines)

            _add_combo_effect_lines_legacy(effect_dict, lines, source_label)

    # 被動技能 buff 刻意放在最後，與舊版 Desktop 順序一致。
    _apply_skillbuff_text_into_effect_dict(
        effect_dict,
        request,
        data,
        grade=legacy_grade,
        context=context,
        dependencies=dependencies,
    )

    totals = build_effect_totals(
        effect_dict,
        sort_mode=request.sort_mode,
        custom_sort_orders=data.custom_sort_orders,
    )
    combined = format_effect_dict(
        effect_dict,
        show_source=request.show_source,
        sort_mode=request.sort_mode,
        custom_sort_orders=data.custom_sort_orders,
    )
    return EquipmentEffectResult(
        effects=totals,
        combined_lines=combined,
        combo_lines=combo_lines,
        triggered_combo_ids=triggered_combo_ids,
        warnings=warnings,
        legacy_effect_dict=effect_dict,
    )

# === STAGE 5 裝備計算核心結束 ===


# === STAGE 6 基礎素質預計算 / API 序列化開始 ===

BASE_STAT_NAMES: tuple[str, ...] = (
    "STR", "AGI", "VIT", "INT", "DEX", "LUK",
    "POW", "STA", "WIS", "SPL", "CON", "CRT",
)

BASE_STAT_GIDS: dict[str, int] = {
    "STR": 32,
    "AGI": 33,
    "VIT": 34,
    "INT": 35,
    "DEX": 36,
    "LUK": 37,
    "POW": 255,
    "STA": 256,
    "WIS": 257,
    "SPL": 258,
    "CON": 259,
    "CRT": 260,
}


# === 核心去重階段 2：共用素質拆解 ===
# 唯一計算來源：基礎素質 + Job 加成 + 裝備效果 = 最終素質。
# Desktop 只負責收集 Qt widget 數值與畫面呈現。
def _shared_stat_to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _shared_stat_effect_total(effect_dict, stat, *, integer_effects=False):
    total = 0
    entries = (effect_dict or {}).get((stat, ""), []) or []
    for entry in entries:
        value = entry[0] if isinstance(entry, (tuple, list)) and entry else entry
        if isinstance(value, bool):
            value = int(value)
        if not isinstance(value, (int, float)):
            try:
                value = float(str(value).strip())
            except (TypeError, ValueError):
                continue
            if value.is_integer():
                value = int(value)
        total += value
    return int(total) if integer_effects else total


def calculate_stat_breakdown(
    *,
    get_values=None,
    base_values=None,
    job_bonus=None,
    effect_dict=None,
    base_equipment_stats=None,
    integer_effects=False,
):
    """回傳 12 種角色素質的共用拆解結果。

    ``get_values`` 是 Core / API 使用的形式，以 RO get(id) 為 key。
    ``base_values`` 是方便 Desktop 使用、以素質名稱為 key 的形式。
    ``integer_effects=True`` 會保留 Stage17 / Stage20 舊版整數語意。
    """
    get_values = get_values or {}
    base_values = base_values or {}
    job_bonus = job_bonus or []
    base_equipment_stats = base_equipment_stats or {}

    result = {}
    for index, stat in enumerate(BASE_STAT_NAMES):
        if stat in base_values:
            raw_base = base_values.get(stat, 0)
        else:
            gid = BASE_STAT_GIDS[stat]
            raw_base = get_values.get(gid, get_values.get(str(gid), 0))
        base = _shared_stat_to_int(raw_base, 0)

        if hasattr(job_bonus, "get"):
            raw_job = job_bonus.get(stat, 0)
        else:
            raw_job = job_bonus[index] if index < len(job_bonus) else 0
        job = _shared_stat_to_int(raw_job, 0)

        equip = _shared_stat_effect_total(
            effect_dict,
            stat,
            integer_effects=integer_effects,
        )
        base_equip = _shared_stat_to_int(base_equipment_stats.get(stat, 0), 0)
        total = base + job + equip

        result[stat] = {
            "base": base,
            "job": job,
            "equip": equip,
            "base_equip": base_equip,
            "job_equip": job + equip,
            "total": total,
            # 舊版 skill_focus_* 刻意不包含解析後的 Lua 效果。
            "focus": base + job + base_equip,
        }
    return result


@dataclass
class BaseEquipmentStatResult:
    """Lua 解析前基礎裝備 Stat 掃描的結構化輸出。"""

    base_stats: dict[str, int] = field(default_factory=dict)
    job_stats: dict[str, int] = field(default_factory=dict)
    base_equipment_stats: dict[str, int] = field(default_factory=dict)
    skill_focus_agi: int = 0
    skill_focus_dex: int = 0
    job_id: Any = 0
    job_code: Any = ""
    pure_jobs: Any = field(default_factory=list)


def precompute_base_equipment_stats(
    request: EquipmentEffectRequest,
    data: EquipmentCalculationData,
    *,
    context: CalculationContext | None = None,
    dependencies: CoreDependencies | None = None,
) -> BaseEquipmentStatResult:
    """在解析 Lua 效果前建立 base / job / base-equipment Stat 數值。

    保留舊版 Desktop 語意：
    - 只掃描已裝備物品主要的 ``Stat = {...}`` block；
    - 不包含精煉 / grade / 卡片 / 備註 / combo；
    - 同名物品依 parsed-item 的插入順序遍歷；
    - skill_focus_AGI / DEX 只包含 base + Job + base-equipment Stat。
    """
    if not isinstance(request, EquipmentEffectRequest):
        raise TypeError("request 必須是 EquipmentEffectRequest")
    if not isinstance(data, EquipmentCalculationData):
        raise TypeError("data 必須是 EquipmentCalculationData")

    context = context or CalculationContext()
    dependencies = dependencies or CoreDependencies()
    context.bind_inputs(
        get_values=request.get_values,
        refine_inputs=request.refine_inputs,
    )

    stat_name_sets = data.stat_name_sets
    if not stat_name_sets and "stat_name_sets" in dependencies.values:
        candidate = dependencies.values.get("stat_name_sets")
        if isinstance(candidate, dict):
            stat_name_sets = candidate

    base_equipment_stats = {stat: 0 for stat in BASE_STAT_NAMES}

    for slot in request.slots:
        equip_name = str(slot.equip_name or "").strip()
        if not equip_name:
            continue

        for item_id in _iter_item_ids_by_name(data.parsed_items, equip_name):
            block_text = data.equipment_data.get(item_id)
            if not block_text:
                continue

            type_match = re.search(r'Type\s*=\s*"([^"]+)"', block_text)
            equip_type = type_match.group(1) if type_match else "armor"
            names_for_type = stat_name_sets.get(
                equip_type,
                stat_name_sets.get("armor", []),
            )

            stat_match = re.search(r'Stat\s*=\s*\{([^}]*)\}', block_text, re.DOTALL)
            if not stat_match:
                continue

            raw_values = stat_match.group(1).split(",")
            for idx, raw_value in enumerate(raw_values):
                if idx >= len(names_for_type):
                    break
                try:
                    value = int(str(raw_value).strip())
                except (TypeError, ValueError):
                    continue
                stat_name = names_for_type[idx]
                if stat_name in base_equipment_stats:
                    base_equipment_stats[stat_name] += value

    job_id = request.get_values.get(19, 0)
    job_info = data.job_dict.get(job_id, {}) if isinstance(data.job_dict, dict) else {}
    job_bonus = job_info.get("TJobMaxPoint", []) or []
    pure_jobs = job_info.get("GetPureJob", []) or []
    job_code = job_info.get("id", "")

    stat_breakdown = calculate_stat_breakdown(
        get_values=request.get_values,
        job_bonus=job_bonus,
        effect_dict={},
        base_equipment_stats=base_equipment_stats,
        integer_effects=True,
    )
    base_stats: dict[str, int] = {}
    job_stats: dict[str, int] = {}
    for stat in BASE_STAT_NAMES:
        values = stat_breakdown[stat]
        base_stats[stat] = values["base"]
        job_stats[stat] = values["job"]
        context.variables[f"base_{stat}"] = values["base"]
        context.variables[f"job_{stat}"] = values["job"]
        context.variables[f"base_equip_{stat}"] = values["base_equip"]
    skill_focus_agi = stat_breakdown["AGI"]["focus"]
    skill_focus_dex = stat_breakdown["DEX"]["focus"]
    context.variables["skill_focus_AGI"] = skill_focus_agi
    context.variables["skill_focus_DEX"] = skill_focus_dex
    context.variables["job_idcore"] = job_code
    context.pure_jobs = pure_jobs

    return BaseEquipmentStatResult(
        base_stats=base_stats,
        job_stats=job_stats,
        base_equipment_stats=base_equipment_stats,
        skill_focus_agi=skill_focus_agi,
        skill_focus_dex=skill_focus_dex,
        job_id=job_id,
        job_code=job_code,
        pure_jobs=pure_jobs,
    )


def equipment_effect_request_from_dict(payload: Any) -> EquipmentEffectRequest:
    """把 JSON / 類 Pydantic 資料轉成 Core request dataclass。

    Core 不需要匯入 FastAPI / Pydantic。JSON object 中 gid / slot dictionary 的 key
    在可能的情況下會正規化回 int。
    """
    if isinstance(payload, EquipmentEffectRequest):
        return payload
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump()
    if not isinstance(payload, dict):
        raise TypeError("payload 必須是 dict / Pydantic model / EquipmentEffectRequest")

    def int_key_dict(value: Any) -> dict[int, Any]:
        if not isinstance(value, dict):
            return {}
        result: dict[int, Any] = {}
        for key, item in value.items():
            try:
                normalized = int(key)
            except (TypeError, ValueError):
                continue
            result[normalized] = item
        return result

    slots: list[EquipmentSlotInput] = []
    for raw_slot in payload.get("slots", []) or []:
        if isinstance(raw_slot, EquipmentSlotInput):
            slots.append(raw_slot)
            continue
        if hasattr(raw_slot, "model_dump"):
            raw_slot = raw_slot.model_dump()
        if not isinstance(raw_slot, dict):
            raise TypeError("slots 內容必須是 dict / EquipmentSlotInput")
        slots.append(
            EquipmentSlotInput(
                part_name=str(raw_slot.get("part_name", "")),
                slot_id=int(raw_slot.get("slot_id", 0)),
                equip_name=str(raw_slot.get("equip_name", "") or ""),
                grade=int(raw_slot.get("grade", 0) or 0),
                cards=[str(x) for x in (raw_slot.get("cards", []) or [])],
                note=str(raw_slot.get("note", "") or ""),
            )
        )

    refine_inputs_raw = int_key_dict(payload.get("refine_inputs", {}))
    refine_inputs: dict[int, int] = {}
    for key, value in refine_inputs_raw.items():
        try:
            refine_inputs[key] = int(value or 0)
        except (TypeError, ValueError):
            refine_inputs[key] = 0

    return EquipmentEffectRequest(
        get_values=int_key_dict(payload.get("get_values", {})),
        refine_inputs=refine_inputs,
        slots=slots,
        enabled_skill_names=[
            str(x) for x in (payload.get("enabled_skill_names", []) or [])
        ],
        hide_unrecognized=bool(payload.get("hide_unrecognized", False)),
        hide_physical=bool(payload.get("hide_physical", False)),
        hide_magical=bool(payload.get("hide_magical", False)),
        show_source=bool(payload.get("show_source", False)),
        sort_mode=str(payload.get("sort_mode", "來源順序") or "來源順序"),
    )


def equipment_effect_result_to_dict(result: EquipmentEffectResult) -> dict[str, Any]:
    """回傳可安全 JSON 化的公開結果；不包含過渡期 tuple-key dict。"""
    if not isinstance(result, EquipmentEffectResult):
        raise TypeError("result 必須是 EquipmentEffectResult")

    return {
        "effects": [
            {
                "key": item.key,
                "unit": item.unit,
                "total": item.total,
                "entries": [
                    {"value": entry.value, "source": entry.source}
                    for entry in item.entries
                ],
            }
            for item in result.effects
        ],
        "combined_lines": list(result.combined_lines),
        "combo_lines": list(result.combo_lines),
        "triggered_combo_ids": list(result.triggered_combo_ids),
        "warnings": list(result.warnings),
    }

# === STAGE 6 基礎素質預計算 / API 序列化結束 ===


# === STAGE 7 正式版核心 Runtime 開始 ===

# 由 apply_core_stage7.py 根據使用者目前已驗證的
# Desktop 原始碼產生一次。這些是唯讀 parser / data map；每次 request 專屬狀態
# 仍留在 CalculationContext，不會存放在這裡。
CORE_STATIC_DEPENDENCY_VALUES: dict[str, Any] = {'class_map': {0: '一般', 1: '首領', 2: '監護人'},
 'custom_sort_orders': {'增傷詞條': ['ATK',
                                 'MATK',
                                 'P.ATK',
                                 'S.MATK',
                                 '屬性 的',
                                 '小型',
                                 '中型',
                                 '大型',
                                 '全種族',
                                 '型怪',
                                 '全屬性',
                                 '對象',
                                 '階級',
                                 '距離',
                                 '防禦',
                                 '技能',
                                 '詠唱'],
                        'ROCalculator輸入': ['STR',
                                           'AGI',
                                           'VIT',
                                           'INT',
                                           'DEX',
                                           'LUK',
                                           'POW',
                                           'STA',
                                           'WIS',
                                           'SPL',
                                           'CON',
                                           'CRT',
                                           '技能',
                                           'CRI',
                                           'P.ATK',
                                           'S.MATK',
                                           'ATK',
                                           '全種族',
                                           '型怪',
                                           '小型',
                                           '中型',
                                           '大型',
                                           '階級',
                                           '全屬性',
                                           '對象',
                                           '魔法傷害',
                                           '爆擊傷害',
                                           'C.RATE',
                                           '距離']},
 'effect_map': {41: 'ATK',
                45: 'DEF',
                47: 'MDEF',
                49: 'HIT',
                50: 'FLEE',
                51: '完全迴避',
                52: 'CRI',
                54: 'ASPD',
                103: 'STR',
                104: 'AGI',
                105: 'VIT',
                106: 'INT',
                107: 'DEX',
                108: 'LUK',
                109: 'MHP',
                110: 'MSP',
                111: 'MHP%',
                112: 'MSP%',
                113: 'HP自然恢復%',
                114: 'SP自然恢復%',
                140: 'MATK%',
                167: '攻擊後延遲',
                200: 'MATK',
                207: 'ATK%',
                234: 'POW',
                235: 'STA',
                236: 'WIS',
                237: 'SPL',
                238: 'CON',
                239: 'CRT',
                242: 'P.ATK',
                243: 'S.MATK',
                244: 'RES',
                245: 'MRES',
                253: 'C.RATE',
                254: 'H.PLUS',
                301: '(2轉以下)攻擊後延遲',
                302: '(2轉以下)ASPD'},
 'element_map': {0: '無屬性',
                 1: '水屬性',
                 2: '地屬性',
                 3: '火屬性',
                 4: '風屬性',
                 5: '毒屬性',
                 6: '聖屬性',
                 7: '暗屬性',
                 8: '念屬性',
                 9: '不死屬性',
                 10: '全屬性',
                 999: '（不使用）'},
 'excluded_stat_names': {'武器類型', '防具等級', '武器等級'},
 'race_map': {0: '無形',
              1: '不死',
              2: '動物',
              3: '植物',
              4: '昆蟲',
              5: '魚貝',
              6: '惡魔',
              7: '人形',
              8: '天使',
              9: '龍族',
              10: '玩家（人類）',
              11: '玩家（貓族）',
              9999: '全種族'},
 'size_map': {0: '小型', 1: '中型', 2: '大型'},
 'stat_name_sets': {'armor': ['DEF',
                              'STR',
                              'INT',
                              'VIT',
                              'DEX',
                              'AGI',
                              'LUK',
                              '未知7',
                              '未知8',
                              'MDEF',
                              '防具等級',
                              'POW',
                              'SPL',
                              'STA',
                              'WIS',
                              'CON',
                              'CRT'],
                    'Mweapon': ['武器屬性',
                                '武器類型',
                                '武器ATK',
                                '武器MATK',
                                'STR',
                                'INT',
                                'VIT',
                                'DEX',
                                'AGI',
                                'LUK',
                                '武器等級',
                                'POW',
                                'SPL',
                                'STA',
                                'WIS',
                                'CON',
                                'CRT'],
                    'Rweapon': ['武器類型',
                                '武器ATK',
                                'STR',
                                'INT',
                                'VIT',
                                'DEX',
                                'AGI',
                                'LUK',
                                '武器等級',
                                'POW',
                                'SPL',
                                'STA',
                                'WIS',
                                'CON',
                                'CRT'],
                    'ammo': ['屬性', '箭矢/彈藥ATK'],
                    'Cannonball': ['屬性', '砲彈ATK']},
 'unit_map': {0: '玩家', 1: '魔物'},
 'weapon_type_map': {0: '空手',
                     1: '短劍',
                     2: '單手劍',
                     3: '雙手劍',
                     4: '單手矛',
                     5: '雙手矛',
                     6: '單手斧',
                     7: '雙手斧',
                     8: '鈍器',
                     10: '單手仗',
                     12: '拳套',
                     13: '樂器',
                     14: '鞭子',
                     15: '書',
                     16: '拳刃',
                     23: '雙手仗',
                     11: '弓',
                     17: '左輪手槍',
                     18: '來福槍',
                     19: '格林機關槍',
                     20: '霰彈槍',
                     21: '榴彈槍',
                     22: '風魔飛鏢'}}


@dataclass(frozen=True)
class CoreRuntimeBundle:
    """供多個 Desktop / Web 計算共用、以唯讀為主的正式版 runtime。"""

    core: ROItemCore
    data: EquipmentCalculationData
    data_dir: str
    include_kro: bool = False


def _runtime_read_text(path: Any, *, required: bool = True) -> str:
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        if required:
            raise FileNotFoundError(f"Core runtime 缺少資料檔：{p}")
        return ""
    # utf-8-sig 可同時接受含 BOM 與一般 UTF-8 檔案。
    return p.read_text(encoding="utf-8-sig")


def _runtime_load_python_variable(path: Any, var_name: str) -> Any:
    from pathlib import Path
    import runpy

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Core runtime 缺少資料檔：{p}")
    namespace = runpy.run_path(str(p))
    if var_name not in namespace:
        raise AttributeError(f"{p} 裡找不到變數：{var_name}")
    return namespace[var_name]


def _runtime_load_skill_map(path: Any) -> dict[int, str]:
    from pathlib import Path
    import csv

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Core runtime 缺少技能清單：{p}")

    result: dict[int, str] = {}
    with p.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "ID" not in reader.fieldnames or "Name" not in reader.fieldnames:
            raise ValueError(f"skillneme.csv 缺少 ID/Name 欄位：{p}")
        for row in reader:
            try:
                skill_id = int(str(row.get("ID", "")).strip())
            except (TypeError, ValueError):
                continue
            name = str(row.get("Name", "") or "").strip()
            if name:
                result[skill_id] = name
    return result


def _runtime_prefix_combiitem_ids(content: str, prefix: Any) -> str:
    """Desktop KRO Combiitem-ID 前綴規則的 Core 版本。"""
    if prefix is None:
        return content
    prefix_text = str(prefix).strip()
    if not prefix_text:
        return content
    if not prefix_text.isdigit():
        raise ValueError("combiitem_id_prefix 必須是整數或只包含數字的字串")

    inline_pattern = re.compile(
        r"(\bCombiitem\s*=\s*\{)([^{}]*)(\})",
        re.DOTALL,
    )

    def replace_inline_list(match):
        head, body, tail = match.groups()

        def replace_id(id_match):
            return prefix_text + id_match.group(1)

        body = re.sub(r"(?<![\w.])(\d+)(?![\w.])", replace_id, body)
        return head + body + tail

    content = inline_pattern.sub(replace_inline_list, content)
    section_match = re.search(r"(?m)^Combiitem\s*=\s*\{", content)
    if not section_match:
        return content

    open_brace = content.find("{", section_match.start(), section_match.end())
    if open_brace < 0:
        return content

    chars = list(content)
    replacements: list[tuple[int, int, str]] = []
    depth = 0
    i = open_brace + 1
    quote = None
    line_comment = False
    block_comment = False

    while i < len(content):
        ch = content[i]
        nxt = content[i + 1] if i + 1 < len(content) else ""

        if line_comment:
            if ch == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            if ch == "]" and nxt == "]":
                block_comment = False
                i += 2
            else:
                i += 1
            continue
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch == "-" and nxt == "-":
            if content[i + 2:i + 4] == "[[":
                block_comment = True
                i += 4
            else:
                line_comment = True
                i += 2
            continue
        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
            i += 1
            continue
        if ch == "}":
            if depth == 0:
                break
            depth -= 1
            i += 1
            continue
        if depth == 0 and ch == "[":
            key_match = re.match(r"\[(\d+)\]\s*=\s*\{", content[i:])
            if key_match:
                number_start = i + 1
                number_end = number_start + len(key_match.group(1))
                replacements.append(
                    (number_start, number_end, prefix_text + key_match.group(1))
                )
        i += 1

    for start, end, replacement in reversed(replacements):
        chars[start:end] = replacement
    return "".join(chars)


def _runtime_merge_equipment_text(
    target: dict[int, str],
    content: str,
    *,
    overwrite: bool,
    combiitem_id_prefix: Any = None,
    verbose: bool = False,
) -> None:
    if combiitem_id_prefix is not None:
        content = _runtime_prefix_combiitem_ids(content, combiitem_id_prefix)
    blocks = parse_equipment_blocks(content, verbose=verbose)
    for item_id, block in blocks.items():
        if item_id not in target or overwrite:
            target[item_id] = block


def build_production_core_runtime(
    data_dir: Any = "data",
    *,
    include_kro: bool = False,
    verbose: bool = False,
) -> CoreRuntimeBundle:
    """由共用專案 data/ 建立正式版 ROItemCore runtime。

    Runtime 載入不依賴 Qt，也不會匯入 ItemSearchApp.py。此處回傳的物件以唯讀為主，
    可供多個 HTTP request 共用；但每個 request 仍必須建立自己的 CalculationContext。
    """
    from pathlib import Path

    data_path = Path(data_dir).resolve()
    if not data_path.is_dir():
        raise FileNotFoundError(f"找不到 data 目錄：{data_path}")

    iteminfo_path = data_path / "iteminfo_new.lua"
    user_iteminfo_path = data_path / "User_iteminfo_new.lua"
    equipment_path = data_path / "EquipmentProperties.lua"
    user_equipment_path = data_path / "User_EquipmentProperties.lua"
    kro_iteminfo_path = data_path / "KRO_itemInfo_true.lua"
    kro_equipment_path = data_path / "KRO_equipmentproperties.lua"
    skill_entries_path = data_path / "all_skill_entries.py"
    job_dict_path = data_path / "job_dict.py"
    skillbuff_path = data_path / "skillbuff.lua"
    skill_names_path = data_path / "skillneme.csv"

    # 與 Desktop 載入順序一致：TWRO 基底 -> User 覆蓋 -> 視設定略過 KRO。
    parsed_items = parse_lub_file(iteminfo_path, verbose=verbose)
    if user_iteminfo_path.exists():
        parsed_items = parse_lub_file(
            user_iteminfo_path,
            existing_items=parsed_items,
            duplicate_mode="overwrite",
            verbose=verbose,
        )
    if include_kro:
        parsed_items = parse_lub_file(
            kro_iteminfo_path,
            existing_items=parsed_items,
            duplicate_mode="skip",
            verbose=verbose,
        )

    equipment_data: dict[int, str] = {}
    _runtime_merge_equipment_text(
        equipment_data,
        _runtime_read_text(equipment_path),
        overwrite=True,
        verbose=verbose,
    )
    if user_equipment_path.exists():
        _runtime_merge_equipment_text(
            equipment_data,
            _runtime_read_text(user_equipment_path),
            overwrite=True,
            verbose=verbose,
        )
    if include_kro:
        _runtime_merge_equipment_text(
            equipment_data,
            _runtime_read_text(kro_equipment_path),
            overwrite=False,
            combiitem_id_prefix=1,
            verbose=verbose,
        )

    parsed_items = resolve_name_conflicts(parsed_items, equipment_data)
    skill_entries = _runtime_load_python_variable(
        skill_entries_path,
        "all_skill_entries",
    )
    job_dict = _runtime_load_python_variable(job_dict_path, "job_dict")
    skill_map = _runtime_load_skill_map(skill_names_path)
    skillbuff_text = _runtime_read_text(skillbuff_path)

    dependency_values: dict[str, Any] = {}
    dynamic_values: dict[str, Any] = {
        "skill_map": skill_map,
    }
    for name in CORE_LUA_DEPENDENCY_NAMES:
        if name in dynamic_values:
            dependency_values[name] = dynamic_values[name]
        elif name in CORE_STATIC_DEPENDENCY_VALUES:
            dependency_values[name] = CORE_STATIC_DEPENDENCY_VALUES[name]
        else:
            raise CoreDependencyError(
                "production runtime 無法建立 Lua parser dependency: " + name
            )

    dependencies = CoreDependencies(
        values=dependency_values,
        function_defs={},
    )
    dependencies.validate(CORE_LUA_DEPENDENCY_NAMES)

    data = EquipmentCalculationData(
        parsed_items=parsed_items,
        equipment_data=equipment_data,
        skill_entries=skill_entries,
        skillbuff_text=skillbuff_text,
        skill_map=skill_map,
        unit_map=dict(CORE_STATIC_DEPENDENCY_VALUES.get("unit_map", {})),
        size_map=dict(CORE_STATIC_DEPENDENCY_VALUES.get("size_map", {})),
        effect_map=dict(CORE_STATIC_DEPENDENCY_VALUES.get("effect_map", {})),
        custom_sort_orders=dict(
            CORE_STATIC_DEPENDENCY_VALUES.get("custom_sort_orders", {})
        ),
        job_dict=job_dict,
        stat_name_sets=dict(
            CORE_STATIC_DEPENDENCY_VALUES.get("stat_name_sets", {})
        ),
    )
    core = ROItemCore(dependencies=dependencies)
    return CoreRuntimeBundle(
        core=core,
        data=data,
        data_dir=str(data_path),
        include_kro=bool(include_kro),
    )


def fork_core_dependencies(dependencies: CoreDependencies) -> CoreDependencies:
    """共用唯讀 map，但讓每個 request 擁有獨立的 function_defs。"""
    return CoreDependencies(
        values=dependencies.values,
        function_defs={},
    )

# === STAGE 7 正式版核心 Runtime 結束 ===


# =========================================================
# 對外核心介面
# =========================================================


class ROItemCore:
    """Desktop 與未來 FastAPI 程式共用的小型穩定入口。"""

    def __init__(
        self,
        data: CoreData | None = None,
        dependencies: CoreDependencies | None = None,
    ):
        self.data = data or CoreData()
        self.dependencies = dependencies or CoreDependencies()

    def calculate_stat_points(self, level: int, job_id: int) -> int:
        return calculate_stat_points(level, job_id)

    def raising_stats(self, stat_str: str) -> int:
        return raising_stats(stat_str)

    def new_context(self, **kwargs: Any) -> CalculationContext:
        """為每個 request 建立全新的計算 context。"""
        return CalculationContext(**kwargs)

    def parse_item_file(
        self,
        filename: str | os.PathLike[str],
        existing_items: dict[int, dict[str, Any]] | None = None,
        duplicate_mode: str = "skip",
        *,
        verbose: bool = True,
    ) -> dict[int, dict[str, Any]]:
        return parse_lub_file(
            filename,
            existing_items,
            duplicate_mode,
            verbose=verbose,
        )

    def parse_item_text(
        self,
        content: str,
        existing_items: dict[int, dict[str, Any]] | None = None,
        duplicate_mode: str = "skip",
    ) -> dict[int, dict[str, Any]]:
        return parse_lub_text(content, existing_items, duplicate_mode)

    def parse_equipment_text(self, content: str) -> dict[int, str]:
        return parse_equipment_blocks(content, verbose=False)

    def parse_effects(
        self,
        block_text: str,
        refine_inputs: dict[int, int],
        get_values: dict[int, Any],
        grade: Any,
        unit_map: dict,
        size_map: dict,
        effect_map: dict,
        *,
        context: CalculationContext | None = None,
        dependencies: CoreDependencies | None = None,
        hide_unrecognized: bool = False,
        hide_physical: bool = False,
        hide_magical: bool = False,
        current_location_slot: int | None = None,
    ) -> list[str]:
        """透過共用 Core parser 解析單一裝備 Lua block。"""
        try:
            parser = parse_lua_effects_with_variables
        except NameError as exc:
            raise RuntimeError(
                "Lua parser 尚未注入 ro_core.py；請先執行 apply_core_stage3.py"
            ) from exc
        return parser(
            block_text,
            refine_inputs,
            get_values,
            grade,
            unit_map,
            size_map,
            effect_map,
            hide_unrecognized=hide_unrecognized,
            hide_physical=hide_physical,
            hide_magical=hide_magical,
            current_location_slot=current_location_slot,
            context=context or self.new_context(),
            dependencies=dependencies or self.dependencies,
        )


    def calculate_equipment_effects(
        self,
        request: EquipmentEffectRequest,
        data: EquipmentCalculationData,
        *,
        context: CalculationContext | None = None,
        dependencies: CoreDependencies | None = None,
    ) -> EquipmentEffectResult:
        """執行共用 Stage 5 裝備計算器。"""
        return calculate_equipment_effects(
            request,
            data,
            context=context or self.new_context(),
            dependencies=dependencies or self.dependencies,
        )


__all__ = [
    "RO_CORE_VERSION",
    "CalculationContext",
    "CoreDependencyError",
    "CoreDependencies",
    "CORE_LUA_DEPENDENCY_NAMES",
    "CoreData",
    "ROItemCore",
    "calculate_stat_points",
    "raising_stats",
    "parse_lub_text",
    "parse_lub_file",
    "resolve_name_conflicts",
    "parse_equipment_blocks",
    "parse_lua_effects_with_variables",
    "EquipmentSlotInput",
    "EquipmentEffectRequest",
    "EffectContribution",
    "EffectTotal",
    "EquipmentEffectResult",
    "normalize_effect_key",
    "try_extract_effect",
    "filter_effects",
    "add_effect_lines",
    "extract_combi_ids",
    "extract_combo_items",
    "build_effect_totals",
    "format_effect_dict",
    "EquipmentCalculationData",
    "calculate_equipment_effects",
    "BASE_STAT_NAMES",
    "BASE_STAT_GIDS",
    "BaseEquipmentStatResult",
    "precompute_base_equipment_stats",
    "equipment_effect_request_from_dict",
    "equipment_effect_result_to_dict",
    "CORE_STATIC_DEPENDENCY_VALUES",
    "CoreRuntimeBundle",
    "build_production_core_runtime",
    "fork_core_dependencies",
]

# === STAGE 13 WEB 附魔 / Lapine 工具核心 ===
# 純標準函式庫 helper；此區塊不要依賴任何 framework：
# 不使用 FastAPI、Pydantic、PySide6。
from collections import defaultdict as _stage13_defaultdict
import json as _stage13_json
import os as _stage13_os
import random as _stage13_random
import re as _stage13_re
from typing import Any as _Stage13Any, Mapping as _Stage13Mapping


STAGE13_ELEMENT_MAP = {
    0: "無屬性",
    1: "水屬性",
    2: "地屬性",
    3: "火屬性",
    4: "風屬性",
    5: "毒屬性",
    6: "聖屬性",
    7: "暗屬性",
    8: "念屬性",
    9: "不死屬性",
    10: "全屬性",
    999: "（不使用）",
}
STAGE13_RACE_MAP = {
    0: "無形",
    1: "不死",
    2: "動物",
    3: "植物",
    4: "昆蟲",
    5: "魚貝",
    6: "惡魔",
    7: "人形",
    8: "天使",
    9: "龍族",
    10: "玩家（人類）",
    11: "玩家（貓族）",
    9999: "全種族",
}
STAGE13_SIZE_MAP = {0: "小型", 1: "中型", 2: "大型"}
STAGE13_CLASS_MAP = {0: "一般", 1: "首領", 2: "監護人"}

_STAGE13_ENCHANT_RUNTIME_CACHE = {}
_STAGE13_LAPINE_RUNTIME_CACHE = {}


def _stage13_file_signature(paths):
    signature = []
    for path in paths:
        try:
            stat = _stage13_os.stat(path)
            signature.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            signature.append((str(path), None, None))
    return tuple(signature)


def get_stage13_calculation_meta():
    """回傳可安全 JSON 化、供 Web 計算器使用的 parser 目標 map。"""
    def rows(mapping):
        return [{"value": int(key), "label": str(value)} for key, value in mapping.items()]
    return {
        "elements": rows(STAGE13_ELEMENT_MAP),
        "races": rows(STAGE13_RACE_MAP),
        "sizes": rows(STAGE13_SIZE_MAP),
        "classes": rows(STAGE13_CLASS_MAP),
        "extended_stat_gids": {
            "POW": 255,
            "STA": 256,
            "WIS": 257,
            "SPL": 258,
            "CON": 259,
            "CRT": 260,
        },
    }


def _stage13_read_text(path):
    encodings = ("utf-8-sig", "utf-8", "cp950", "big5", "cp936", "cp932", "latin1")
    last_error = None
    for encoding in encodings:
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except (UnicodeDecodeError, OSError) as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise OSError(f"Unable to read file: {path}")


def _stage13_item_lookup(parsed_items, item_id):
    item = (parsed_items or {}).get(item_id)
    if item is None:
        item = (parsed_items or {}).get(str(item_id))
    return item if isinstance(item, dict) else {}


def _stage13_item_display(parsed_items, item_id, fallback=""):
    info = _stage13_item_lookup(parsed_items, int(item_id))
    return str(info.get("name") or fallback or f"ID:{item_id}")


def _stage13_item_id_from_raw(raw_name, itemdb, parsed_items):
    raw = str(raw_name or "").strip()
    if not raw:
        return None
    item_id = (itemdb or {}).get(raw)
    if item_id is not None:
        try:
            return int(item_id)
        except (TypeError, ValueError):
            pass
    for candidate_id, info in (parsed_items or {}).items():
        if not isinstance(info, dict):
            continue
        if raw in {
            str(info.get("name") or "").strip(),
            str(info.get("base_name") or "").strip(),
            str(info.get("kr_name") or "").strip(),
        }:
            try:
                return int(candidate_id)
            except (TypeError, ValueError):
                return None
    return None


def _stage13_resolve_raw_name(raw_name, itemdb, parsed_items):
    item_id = _stage13_item_id_from_raw(raw_name, itemdb, parsed_items)
    if item_id is None:
        return str(raw_name or "")
    return _stage13_item_display(parsed_items, item_id, str(raw_name or ""))


# ---------------------------------------------------------------------------
# EnchantList.lua 附魔資料
# ---------------------------------------------------------------------------

def parse_stage13_itemdb_name_tbl(filename):
    if not _stage13_os.path.isfile(filename):
        return {}
    content = _stage13_read_text(filename)
    pattern = r'(?:\["([^"]+)"\]|([A-Za-z0-9_]+))\s*=\s*(\d+)'
    result = {}
    for match in _stage13_re.finditer(pattern, content):
        key1, key2, value = match.groups()
        key = key1 or key2
        if key:
            result[key] = int(value)
    return result


def _stage13_enchant_slot_default():
    return {
        "enchants": [],
        "perfect": [],
        "upgrade": [],
        "perfect_upgrade": [],
        "random_upgrade": [],
    }


def parse_stage13_enchant_list(filename):
    """不依賴 Qt、且與目前 Desktop enchant.py 資料結構一致的 parser。"""
    if not _stage13_os.path.isfile(filename):
        return {}
    content = _stage13_read_text(filename)
    tables = _stage13_re.split(
        r"Table\[(\d+)\]\s*=\s*CreateEnchantInfo\(\s*\)",
        content,
    )
    if len(tables) <= 1:
        return {}

    parsed = {}
    for index in range(1, len(tables), 2):
        table_id = int(tables[index])
        body = tables[index + 1]
        parsed[table_id] = {
            "slot_order": [],
            "target_items": [],
            "reset": None,
            "slots": {},
        }
        slot_order = _stage13_re.search(r"SetSlotOrder\((.*?)\)", body)
        if slot_order:
            parsed[table_id]["slot_order"] = [
                int(value.strip())
                for value in slot_order.group(1).split(",")
                if value.strip().isdigit()
            ]
        parsed[table_id]["target_items"] = _stage13_re.findall(
            r'AddTargetItem(?:_Duplicate)?\("([^"]+)"\)',
            body,
        )
        reset = _stage13_re.search(
            r"SetReset\((true|false)\s*,\s*(\d+)\s*,\s*(\d+)"
            r"(?:\s*,\s*((?:\{.*?\})+))?",
            body,
            _stage13_re.DOTALL,
        )
        if reset:
            raw_materials = reset.group(4) or ""
            parsed[table_id]["reset"] = {
                "enable": reset.group(1) == "true",
                "reset_rate": int(reset.group(2)),
                "enchant_rate": int(reset.group(3)),
                "materials": [
                    (name, int(count))
                    for name, count in _stage13_re.findall(
                        r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}',
                        raw_materials,
                    )
                ],
            }

    requires = _stage13_re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:SetRequire'
        r'\(\s*(\d+)(?:\s*,\s*((?:\{[^}]+\}\s*,?\s*)*))?\s*\)',
        content,
    )
    for raw_tid, raw_sid, raw_zeny, mats_raw in requires:
        tid, sid, zeny = int(raw_tid), int(raw_sid), int(raw_zeny)
        if tid not in parsed:
            continue
        parsed[tid]["slots"].setdefault(sid, _stage13_enchant_slot_default())
        parsed[tid]["slots"][sid]["require"] = {
            "zeny": zeny,
            "materials": [
                (name, int(count))
                for name, count in _stage13_re.findall(
                    r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}',
                    mats_raw or "",
                )
            ],
        }

    enchants = _stage13_re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:SetEnchant'
        r'\(\s*(\d+)\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*\)',
        content,
    )
    for raw_tid, raw_sid, raw_grade, name, raw_rate in enchants:
        tid, sid = int(raw_tid), int(raw_sid)
        if tid not in parsed:
            continue
        parsed[tid]["slots"].setdefault(sid, _stage13_enchant_slot_default())
        parsed[tid]["slots"][sid]["enchants"].append(
            (int(raw_grade), name, int(raw_rate))
        )

    perfects = _stage13_re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:AddPerfectEnchant'
        r'\(\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*((?:\{.*?\})+)\)',
        content,
        _stage13_re.DOTALL,
    )
    for raw_tid, raw_sid, name, raw_zeny, mats_raw in perfects:
        tid, sid = int(raw_tid), int(raw_sid)
        if tid not in parsed:
            continue
        parsed[tid]["slots"].setdefault(sid, _stage13_enchant_slot_default())
        parsed[tid]["slots"][sid]["perfect"].append({
            "name": name,
            "zeny": int(raw_zeny),
            "materials": [
                (mat, int(count))
                for mat, count in _stage13_re.findall(
                    r'\{\s*"([^"]*)"\s*,\s*(\d+)\s*\}',
                    mats_raw,
                )
            ],
        })

    upgrades = _stage13_re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:AddUpgradeEnchant'
        r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*((?:\{.*?\})+)\)',
        content,
        _stage13_re.DOTALL,
    )
    for raw_tid, raw_sid, source, target, raw_zeny, mats_raw in upgrades:
        tid, sid = int(raw_tid), int(raw_sid)
        if tid not in parsed:
            continue
        parsed[tid]["slots"].setdefault(sid, _stage13_enchant_slot_default())
        parsed[tid]["slots"][sid]["upgrade"].append({
            "from": source,
            "to": target,
            "zeny": int(raw_zeny),
            "materials": [
                (mat, int(count))
                for mat, count in _stage13_re.findall(
                    r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}',
                    mats_raw,
                )
            ],
        })

    perfect_upgrades = _stage13_re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:AddPerfectUpgradeEnchant'
        r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*((?:\{.*?\})+)\)',
        content,
        _stage13_re.DOTALL,
    )
    for raw_tid, raw_sid, source, target, raw_zeny, mats_raw in perfect_upgrades:
        tid, sid = int(raw_tid), int(raw_sid)
        if tid not in parsed:
            continue
        parsed[tid]["slots"].setdefault(sid, _stage13_enchant_slot_default())
        parsed[tid]["slots"][sid]["perfect_upgrade"].append({
            "from": source,
            "to": target,
            "zeny": int(raw_zeny),
            "materials": [
                (mat, int(count))
                for mat, count in _stage13_re.findall(
                    r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}',
                    mats_raw,
                )
            ],
        })

    random_requires = _stage13_re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:SetRandomUpgradeRequire'
        r'\(\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*((?:\{[^}]+\}\s*,?\s*)+)\)',
        content,
    )
    for raw_tid, raw_sid, source, raw_zeny, mats_raw in random_requires:
        tid, sid = int(raw_tid), int(raw_sid)
        if tid not in parsed:
            continue
        parsed[tid]["slots"].setdefault(sid, _stage13_enchant_slot_default())
        parsed[tid]["slots"][sid].setdefault("random_require", {})[source] = {
            "zeny": int(raw_zeny),
            "materials": [
                (mat, int(count))
                for mat, count in _stage13_re.findall(
                    r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}',
                    mats_raw,
                )
            ],
        }

    random_upgrades = _stage13_re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:AddRandomUpgradeEnchant'
        r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*\)',
        content,
    )
    for raw_tid, raw_sid, source, target, raw_rate in random_upgrades:
        tid, sid = int(raw_tid), int(raw_sid)
        if tid not in parsed:
            continue
        parsed[tid]["slots"].setdefault(sid, _stage13_enchant_slot_default())
        requirement = (
            parsed[tid]["slots"][sid]
            .get("random_require", {})
            .get(source, {})
        )
        parsed[tid]["slots"][sid]["random_upgrade"].append({
            "from": source,
            "to": target,
            "rate": int(raw_rate),
            "zeny": int(requirement.get("zeny", 0) or 0),
            "materials": list(requirement.get("materials", []) or []),
        })

    return parsed


def _stage13_material_rows(materials, itemdb, parsed_items):
    rows = []
    for raw_name, raw_count in materials or []:
        item_id = _stage13_item_id_from_raw(raw_name, itemdb, parsed_items)
        rows.append({
            "raw_name": str(raw_name),
            "name": _stage13_resolve_raw_name(raw_name, itemdb, parsed_items),
            "item_id": item_id,
            "count": int(raw_count),
        })
    return rows


def _stage13_enchant_entry(entry_type, raw, itemdb, parsed_items, slot_info):
    result = {
        "type": entry_type,
        "rate_raw": None,
        "rate_percent": 100.0,
        "zeny": 0,
        "materials": [],
    }
    if entry_type == "enchant":
        grade, name, rate = raw
        result.update({
            "grade": int(grade),
            "raw_name": str(name),
            "name": _stage13_resolve_raw_name(name, itemdb, parsed_items),
            "output_name": _stage13_resolve_raw_name(name, itemdb, parsed_items),
            "rate_raw": int(rate),
            "rate_percent": int(rate) / 1000.0,
        })
        requirement = slot_info.get("require", {})
        result["zeny"] = int(requirement.get("zeny", 0) or 0)
        result["materials"] = _stage13_material_rows(
            requirement.get("materials", []), itemdb, parsed_items
        )
    elif entry_type == "perfect":
        result.update({
            "raw_name": str(raw.get("name") or ""),
            "name": _stage13_resolve_raw_name(raw.get("name"), itemdb, parsed_items),
            "output_name": _stage13_resolve_raw_name(raw.get("name"), itemdb, parsed_items),
            "zeny": int(raw.get("zeny", 0) or 0),
            "materials": _stage13_material_rows(raw.get("materials", []), itemdb, parsed_items),
        })
    else:
        source = raw.get("from")
        target = raw.get("to")
        result.update({
            "raw_from": str(source or ""),
            "raw_to": str(target or ""),
            "from_name": _stage13_resolve_raw_name(source, itemdb, parsed_items),
            "to_name": _stage13_resolve_raw_name(target, itemdb, parsed_items),
            "name": (
                f"{_stage13_resolve_raw_name(source, itemdb, parsed_items)}"
                f" → {_stage13_resolve_raw_name(target, itemdb, parsed_items)}"
            ),
            "output_name": _stage13_resolve_raw_name(target, itemdb, parsed_items),
            "zeny": int(raw.get("zeny", 0) or 0),
            "materials": _stage13_material_rows(raw.get("materials", []), itemdb, parsed_items),
        })
        if entry_type == "random_upgrade":
            rate = int(raw.get("rate", 0) or 0)
            result["rate_raw"] = rate
            result["rate_percent"] = rate / 1000.0
    return result


def build_stage13_enchant_runtime(data_dir, parsed_items):
    data_dir = _stage13_os.path.abspath(_stage13_os.fspath(data_dir))
    itemdb_path = _stage13_os.path.join(data_dir, "ItemDBNameTbl.lua")
    enchant_path = _stage13_os.path.join(data_dir, "EnchantList.lua")
    cache_key = (
        data_dir,
        id(parsed_items),
        _stage13_file_signature((itemdb_path, enchant_path)),
    )
    cached = _STAGE13_ENCHANT_RUNTIME_CACHE.get(cache_key)
    if cached is not None:
        return cached

    itemdb = parse_stage13_itemdb_name_tbl(itemdb_path)
    parsed = parse_stage13_enchant_list(enchant_path)
    target_map = {}
    for table_id, table in parsed.items():
        for raw_name in table.get("target_items", []) or []:
            item_id = _stage13_item_id_from_raw(raw_name, itemdb, parsed_items)
            if item_id is not None:
                target_map[int(item_id)] = int(table_id)
    runtime = {"itemdb": itemdb, "parsed": parsed, "target_map": target_map}
    _STAGE13_ENCHANT_RUNTIME_CACHE.clear()
    _STAGE13_ENCHANT_RUNTIME_CACHE[cache_key] = runtime
    return runtime


def search_stage13_enchant_targets(data_dir, parsed_items, query="", limit=100):
    runtime = build_stage13_enchant_runtime(data_dir, parsed_items)
    text = str(query or "").strip().casefold()
    rows = []
    for item_id, table_id in runtime["target_map"].items():
        info = _stage13_item_lookup(parsed_items, item_id)
        name = str(info.get("base_name") or info.get("name") or f"ID:{item_id}")
        display_name = str(info.get("name") or name)
        kr_name = str(info.get("kr_name") or "")
        haystack = f"{item_id} {name} {display_name} {kr_name}".casefold()
        if text and text not in haystack:
            continue
        rows.append({
            "item_id": item_id,
            "name": name,
            "display_name": display_name,
            "kr_name": kr_name,
            "table_id": table_id,
        })
    rows.sort(key=lambda row: (row["name"].casefold(), row["item_id"]))
    return rows[: max(1, min(int(limit), 500))]


def get_stage13_enchant_item(data_dir, parsed_items, item_id):
    runtime = build_stage13_enchant_runtime(data_dir, parsed_items)
    item_id = int(item_id)
    table_id = runtime["target_map"].get(item_id)
    if table_id is None:
        return None
    table = runtime["parsed"].get(table_id, {})
    itemdb = runtime["itemdb"]
    slots = []
    slot_order = list(table.get("slot_order", []) or [])
    existing_ids = set(table.get("slots", {}).keys())
    # Desktop 的 enchant.py 會使用 reversed(slot_order) 建立分頁。
    ordered = [sid for sid in reversed(slot_order) if sid in existing_ids]
    ordered.extend(sorted(existing_ids.difference(ordered), reverse=True))
    for slot_id in ordered:
        slot_info = table.get("slots", {}).get(slot_id, {}) or {}
        entries = []
        for entry in slot_info.get("enchants", []) or []:
            entries.append(_stage13_enchant_entry(
                "enchant", entry, itemdb, parsed_items, slot_info
            ))
        for entry in slot_info.get("perfect", []) or []:
            entries.append(_stage13_enchant_entry(
                "perfect", entry, itemdb, parsed_items, slot_info
            ))
        for entry in slot_info.get("upgrade", []) or []:
            entries.append(_stage13_enchant_entry(
                "upgrade", entry, itemdb, parsed_items, slot_info
            ))
        for entry in slot_info.get("perfect_upgrade", []) or []:
            entries.append(_stage13_enchant_entry(
                "perfect_upgrade", entry, itemdb, parsed_items, slot_info
            ))
        for entry in slot_info.get("random_upgrade", []) or []:
            entries.append(_stage13_enchant_entry(
                "random_upgrade", entry, itemdb, parsed_items, slot_info
            ))
        if entries:
            slots.append({
                "slot_id": int(slot_id),
                "entries": entries,
            })
    reset = table.get("reset")
    if isinstance(reset, dict):
        reset = {
            **reset,
            "materials": _stage13_material_rows(
                reset.get("materials", []), itemdb, parsed_items
            ),
        }
    info = _stage13_item_lookup(parsed_items, item_id)
    return {
        "item_id": item_id,
        "name": str(info.get("base_name") or info.get("name") or f"ID:{item_id}"),
        "display_name": str(info.get("name") or ""),
        "kr_name": str(info.get("kr_name") or ""),
        "table_id": int(table_id),
        "slot_order": [int(value) for value in slot_order],
        "slots": slots,
        "reset": reset,
    }


def _stage13_enchant_name_matches(current_name, raw_name, itemdb, parsed_items):
    current = str(current_name or "").strip().casefold()
    if not current:
        return False
    values = {
        str(raw_name or "").strip().casefold(),
        _stage13_resolve_raw_name(raw_name, itemdb, parsed_items).strip().casefold(),
    }
    return current in values


def _stage13_pick_enchant_candidate(candidates, generator):
    weighted = []
    total = 0
    for candidate in candidates:
        try:
            weight = max(0, int(candidate.get("rate", 0)))
        except (TypeError, ValueError):
            weight = 0
        if weight <= 0:
            continue
        weighted.append((candidate, weight))
        total += weight
    if not weighted or total <= 0:
        return None, None, max(100000, total)
    roll_range = max(100000, total)
    roll = generator.randrange(roll_range)
    if roll >= total:
        return None, roll, roll_range
    cumulative = 0
    for candidate, weight in weighted:
        cumulative += weight
        if roll < cumulative:
            return candidate, roll, roll_range
    return weighted[-1][0], roll, roll_range


def roll_stage13_enchant(data_dir, parsed_items, item_id, slot_id, current_enchant="", seed=None):
    runtime = build_stage13_enchant_runtime(data_dir, parsed_items)
    item_id, slot_id = int(item_id), int(slot_id)
    table_id = runtime["target_map"].get(item_id)
    if table_id is None:
        raise ValueError(f"物品 {item_id} 沒有 EnchantList 資料")
    slot_info = runtime["parsed"].get(table_id, {}).get("slots", {}).get(slot_id)
    if not isinstance(slot_info, dict):
        raise ValueError(f"第 {slot_id + 1} 洞沒有 EnchantList 資料")

    itemdb = runtime["itemdb"]
    candidates = []
    current = str(current_enchant or "").strip()
    if current:
        for entry in slot_info.get("random_upgrade", []) or []:
            if not _stage13_enchant_name_matches(
                current, entry.get("from"), itemdb, parsed_items
            ):
                continue
            rate = max(0, int(entry.get("rate", 0) or 0))
            if rate <= 0:
                continue
            candidates.append({
                "type": "random_upgrade",
                "rate": rate,
                "output_name": _stage13_resolve_raw_name(
                    entry.get("to"), itemdb, parsed_items
                ),
                "from_name": _stage13_resolve_raw_name(
                    entry.get("from"), itemdb, parsed_items
                ),
            })
    mode = "random_upgrade" if candidates else "enchant"
    if not candidates:
        merged = {}
        for grade, raw_name, raw_rate in slot_info.get("enchants", []) or []:
            rate = max(0, int(raw_rate))
            if rate <= 0:
                continue
            key = str(raw_name)
            row = merged.setdefault(key, {
                "type": "enchant",
                "rate": 0,
                "output_name": _stage13_resolve_raw_name(
                    raw_name, itemdb, parsed_items
                ),
            })
            row["rate"] += rate
        candidates = list(merged.values())

    generator = _stage13_random.Random(seed) if seed is not None else _stage13_random.SystemRandom()
    selected, roll, roll_range = _stage13_pick_enchant_candidate(candidates, generator)
    total = sum(max(0, int(row.get("rate", 0) or 0)) for row in candidates)
    public_candidates = []
    denominator = max(100000, total)
    for row in candidates:
        weight = max(0, int(row.get("rate", 0) or 0))
        public_candidates.append({
            **row,
            "effective_rate_percent": (
                min(100.0, weight * 100.0 / denominator)
                if denominator > 0 else 0.0
            ),
        })
    return {
        "success": selected is not None,
        "mode": mode,
        "item_id": item_id,
        "table_id": int(table_id),
        "slot_id": slot_id,
        "current_enchant": current,
        "roll": roll,
        "roll_range": roll_range,
        "candidates": public_candidates,
        "result": selected,
    }


# ---------------------------------------------------------------------------
# LapineUpgradeBox / 隨機選項機率表
# ---------------------------------------------------------------------------

def _stage13_skip_quoted(text, index):
    quote = text[index]
    index += 1
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        index += 1
        if char == quote:
            break
    return index


def _stage13_skip_comment(text, index):
    if text.startswith("--[[", index):
        end = text.find("]]", index + 4)
        return len(text) if end < 0 else end + 2
    if text.startswith("--", index):
        end = text.find("\n", index + 2)
        return len(text) if end < 0 else end + 1
    return index


def _stage13_find_matching_brace(text, open_index):
    if open_index < 0 or open_index >= len(text) or text[open_index] != "{":
        raise ValueError("open_index does not point to an opening brace")
    depth = 0
    index = open_index
    while index < len(text):
        if text.startswith("--", index):
            index = _stage13_skip_comment(text, index)
            continue
        char = text[index]
        if char in ('"', "'"):
            index = _stage13_skip_quoted(text, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError("Unbalanced Lua table braces")


def _stage13_decode_lua_string(value):
    result = str(value)
    replacements = {
        r"\\": "\\",
        r'\"': '"',
        r"\'": "'",
        r"\n": "\n",
        r"\r": "\r",
        r"\t": "\t",
    }
    for source, target in replacements.items():
        result = result.replace(source, target)
    return result


def _stage13_extract_scalar_int(block, field, default=0):
    match = _stage13_re.search(
        rf"\b{_stage13_re.escape(field)}\s*=\s*(-?\d+)",
        block,
    )
    return int(match.group(1)) if match else int(default)


def _stage13_extract_scalar_bool(block, field, default=False):
    match = _stage13_re.search(
        rf"\b{_stage13_re.escape(field)}\s*=\s*(true|false)",
        block,
        _stage13_re.I,
    )
    return match.group(1).lower() == "true" if match else bool(default)


def _stage13_extract_scalar_string(block, field, default=""):
    match = _stage13_re.search(
        rf'\b{_stage13_re.escape(field)}\s*=\s*"((?:\\.|[^"\\])*)"',
        block,
        _stage13_re.S,
    )
    return _stage13_decode_lua_string(match.group(1)) if match else default


def _stage13_extract_table_body(block, field):
    match = _stage13_re.search(
        rf"\b{_stage13_re.escape(field)}\s*=\s*\{{",
        block,
    )
    if not match:
        return ""
    open_index = match.end() - 1
    close_index = _stage13_find_matching_brace(block, open_index)
    return block[open_index + 1:close_index]


def _stage13_iter_named_target_blocks(targets_body):
    pattern = _stage13_re.compile(r'\[\s*"((?:\\.|[^"\\])*)"\s*\]\s*=\s*\{')
    index = 0
    depth = 0
    while index < len(targets_body):
        if targets_body.startswith("--", index):
            index = _stage13_skip_comment(targets_body, index)
            continue
        char = targets_body[index]
        if char in ('"', "'"):
            index = _stage13_skip_quoted(targets_body, index)
            continue
        if depth == 0:
            match = pattern.match(targets_body, index)
            if match:
                open_index = match.end() - 1
                close_index = _stage13_find_matching_brace(targets_body, open_index)
                yield (
                    _stage13_decode_lua_string(match.group(1)),
                    targets_body[open_index + 1:close_index],
                )
                index = close_index + 1
                continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        index += 1


def parse_stage13_lapine_upgrade_box(filename):
    if not _stage13_os.path.isfile(filename):
        return {}
    content = _stage13_read_text(filename)
    targets_match = _stage13_re.search(r"\btargets\s*=\s*\{", content)
    if not targets_match:
        raise ValueError("tblLapineUpgradeBox.targets was not found")
    targets_open = targets_match.end() - 1
    targets_close = _stage13_find_matching_brace(content, targets_open)
    targets_body = content[targets_open + 1:targets_close]
    target_pair_pattern = _stage13_re.compile(
        r'\{\s*"((?:\\.|[^"\\])*)"\s*,\s*(\d+)\s*\}',
        _stage13_re.S,
    )
    parsed = {}
    for key, block in _stage13_iter_named_target_blocks(targets_body):
        item_id = _stage13_extract_scalar_int(block, "ItemID", 0)
        if item_id <= 0:
            continue
        target_items_body = _stage13_extract_table_body(block, "TargetItems")
        target_items = [
            {
                "internal_name": _stage13_decode_lua_string(internal_name),
                "item_id": int(target_item_id),
            }
            for internal_name, target_item_id in target_pair_pattern.findall(
                target_items_body
            )
        ]
        parsed[key] = {
            "key": key,
            "item_id": item_id,
            "need_refine_min": _stage13_extract_scalar_int(block, "NeedRefineMin", 0),
            "need_refine_max": _stage13_extract_scalar_int(block, "NeedRefineMax", 20),
            "need_option_num_min": _stage13_extract_scalar_int(block, "NeedOptionNumMin", 0),
            "not_socket_enchant_item": _stage13_extract_scalar_bool(
                block, "NotSocketEnchantItem", False
            ),
            "need_source_string": _stage13_extract_scalar_string(
                block, "NeedSource_String", ""
            ),
            "target_items": target_items,
        }
    return parsed


def build_stage13_lapine_target_map(parsed):
    result = _stage13_defaultdict(list)
    for key, box in (parsed or {}).items():
        for target in box.get("target_items", []) or []:
            try:
                target_item_id = int(target.get("item_id"))
            except (TypeError, ValueError, AttributeError):
                continue
            row = dict(box)
            row["key"] = str(box.get("key") or key)
            row["matched_target"] = dict(target)
            result[target_item_id].append(row)
    for item_id in result:
        result[item_id].sort(
            key=lambda row: (int(row.get("item_id", 0)), str(row.get("key", "")))
        )
    return dict(result)


def _stage13_parse_enumvar_table(filename):
    if not _stage13_os.path.isfile(filename):
        return {}
    content = _stage13_read_text(filename)
    pattern = _stage13_re.compile(
        r'\[\s*EnumVAR\.([A-Za-z0-9_]+)\s*\[\s*1\s*\]\s*\]\s*=\s*'
        r'"((?:\\.|[^"\\])*)"',
        _stage13_re.S,
    )
    return {
        code: _stage13_decode_lua_string(raw)
        for code, raw in pattern.findall(content)
    }


def load_stage13_lapine_probability_store(filename):
    if not _stage13_os.path.isfile(filename):
        return {"version": 2, "tables": {}}
    try:
        with open(filename, "r", encoding="utf-8-sig") as handle:
            data = _stage13_json.load(handle)
    except (OSError, _stage13_json.JSONDecodeError):
        return {"version": 2, "tables": {}}
    if not isinstance(data, dict):
        return {"version": 2, "tables": {}}
    if not isinstance(data.get("tables"), dict):
        data["tables"] = {}
    return data


def _stage13_replace_percent_tokens(template, value_text):
    token = "\u0000PERCENT\u0000"
    rendered = str(template or "").replace("%%", token)
    rendered = rendered.replace("%d", str(value_text))
    return rendered.replace(token, "%").strip()


def _stage13_value_choices(value):
    if not isinstance(value, (list, tuple)):
        return []
    result = []
    for raw in value:
        try:
            number = int(raw)
        except (TypeError, ValueError):
            continue
        if number not in result:
            result.append(number)
    return result


def _stage13_preview_option(template, minimum, maximum, choices=None):
    choices = _stage13_value_choices(choices or [])
    if choices:
        value_text = "、".join(str(value) for value in choices)
    elif int(minimum) != int(maximum):
        value_text = f"{int(minimum)}～{int(maximum)}"
    else:
        value_text = str(int(minimum))
    return _stage13_replace_percent_tokens(template, value_text)


def build_stage13_lapine_runtime(data_dir, parsed_items):
    data_dir = _stage13_os.path.abspath(_stage13_os.fspath(data_dir))
    paths = (
        _stage13_os.path.join(data_dir, "lapineupgradebox.lub"),
        _stage13_os.path.join(data_dir, "lapine_random_options.json"),
        _stage13_os.path.join(data_dir, "AddRandomOptionNameTable.lua"),
        _stage13_os.path.join(data_dir, "EnchantName.lua"),
    )
    cache_key = (data_dir, id(parsed_items), _stage13_file_signature(paths))
    cached = _STAGE13_LAPINE_RUNTIME_CACHE.get(cache_key)
    if cached is not None:
        return cached

    parsed = parse_stage13_lapine_upgrade_box(paths[0])
    target_map = build_stage13_lapine_target_map(parsed)
    probability = load_stage13_lapine_probability_store(paths[1])
    option_names = _stage13_parse_enumvar_table(paths[2])
    enchant_names = _stage13_parse_enumvar_table(paths[3])
    runtime = {
        "parsed": parsed,
        "target_map": target_map,
        "probability": probability,
        "option_names": option_names,
        "enchant_names": enchant_names,
    }
    _STAGE13_LAPINE_RUNTIME_CACHE.clear()
    _STAGE13_LAPINE_RUNTIME_CACHE[cache_key] = runtime
    return runtime


def _stage13_lapine_profile_has_rows(profile):
    return (
        isinstance(profile, dict)
        and isinstance(profile.get("rows"), list)
        and any(
            isinstance(row, dict)
            and str(row.get("option_code") or "").strip()
            for row in profile.get("rows", [])
        )
    )


def search_stage13_lapine_targets(
    data_dir,
    parsed_items,
    query="",
    limit=100,
    show_all=False,
):
    runtime = build_stage13_lapine_runtime(data_dir, parsed_items)
    configured = {
        str(key)
        for key, profile in runtime["probability"].get("tables", {}).items()
        if _stage13_lapine_profile_has_rows(profile)
    }
    text = str(query or "").strip().casefold()
    rows = []
    for item_id, boxes in runtime["target_map"].items():
        visible = [
            box for box in boxes
            if show_all or str(box.get("key") or "") in configured
        ]
        if not visible:
            continue
        info = _stage13_item_lookup(parsed_items, item_id)
        name = str(info.get("base_name") or info.get("name") or f"ID:{item_id}")
        display_name = str(info.get("name") or name)
        kr_name = str(info.get("kr_name") or "")
        internals = [
            str(box.get("matched_target", {}).get("internal_name") or "")
            for box in visible
        ]
        haystack = " ".join(
            [str(item_id), name, display_name, kr_name, *internals]
        ).casefold()
        if text and text not in haystack:
            continue
        rows.append({
            "item_id": int(item_id),
            "name": name,
            "display_name": display_name,
            "kr_name": kr_name,
            "configured_box_count": sum(
                1 for box in boxes if str(box.get("key") or "") in configured
            ),
            "box_count": len(boxes),
        })
    rows.sort(key=lambda row: (row["name"].casefold(), row["item_id"]))
    return rows[: max(1, min(int(limit), 500))]


def _stage13_public_lapine_profile(profile, option_names, enchant_names):
    if not isinstance(profile, dict):
        return None
    groups = profile.get("groups", [])
    if isinstance(groups, dict):
        groups = [
            {"name": key, "probability": value}
            for key, value in groups.items()
        ]
    public_rows = []
    for row in profile.get("rows", []) or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("option_code") or "").strip()
        try:
            minimum = int(row.get("min_value", 0))
            maximum = int(row.get("max_value", minimum))
        except (TypeError, ValueError):
            minimum = maximum = 0
        choices = _stage13_value_choices(row.get("value_choices", []))
        public_rows.append({
            **row,
            "option_code": code,
            "min_value": minimum,
            "max_value": maximum,
            "value_choices": choices,
            "display_preview": _stage13_preview_option(
                option_names.get(code, code),
                minimum,
                maximum,
                choices,
            ),
            "lua_preview": _stage13_preview_option(
                enchant_names.get(code, ""),
                minimum,
                maximum,
                choices,
            ),
        })
    return {
        "title": str(profile.get("title") or ""),
        "box_item_id": profile.get("box_item_id"),
        "updated_at": profile.get("updated_at"),
        "groups": list(groups) if isinstance(groups, list) else [],
        "rows": public_rows,
    }


def get_stage13_lapine_item(
    data_dir,
    parsed_items,
    item_id,
    show_all=False,
):
    runtime = build_stage13_lapine_runtime(data_dir, parsed_items)
    item_id = int(item_id)
    boxes = runtime["target_map"].get(item_id, [])
    tables = runtime["probability"].get("tables", {})
    visible = []
    for box in boxes:
        key = str(box.get("key") or "")
        profile = tables.get(key)
        if not show_all and not _stage13_lapine_profile_has_rows(profile):
            continue
        source_id = int(box.get("item_id", 0) or 0)
        visible.append({
            "key": key,
            "source_item_id": source_id,
            "source_name": _stage13_item_display(
                parsed_items, source_id, key
            ),
            "need_refine_min": int(box.get("need_refine_min", 0) or 0),
            "need_refine_max": int(box.get("need_refine_max", 20) or 20),
            "need_option_num_min": int(box.get("need_option_num_min", 0) or 0),
            "not_socket_enchant_item": bool(
                box.get("not_socket_enchant_item", False)
            ),
            "need_source_string": str(box.get("need_source_string") or ""),
            "profile": _stage13_public_lapine_profile(
                profile,
                runtime["option_names"],
                runtime["enchant_names"],
            ),
        })
    info = _stage13_item_lookup(parsed_items, item_id)
    return {
        "item_id": item_id,
        "name": str(info.get("base_name") or info.get("name") or f"ID:{item_id}"),
        "display_name": str(info.get("name") or ""),
        "kr_name": str(info.get("kr_name") or ""),
        "boxes": visible,
    }


def _stage13_normalize_profile_groups(profile):
    groups = []
    seen = set()
    raw_groups = profile.get("groups", []) if isinstance(profile, dict) else []
    if isinstance(raw_groups, dict):
        raw_groups = [
            {"name": name, "probability": probability}
            for name, probability in raw_groups.items()
        ]
    if isinstance(raw_groups, list):
        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                continue
            name = str(
                raw_group.get("name") or raw_group.get("group") or ""
            ).strip()
            if not name or name in seen:
                continue
            try:
                probability = float(raw_group.get("probability", 100.0))
            except (TypeError, ValueError):
                probability = 100.0
            groups.append({"name": name, "probability": probability})
            seen.add(name)
    for row in profile.get("rows", []) if isinstance(profile, dict) else []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("group") or "1").strip() or "1"
        if name not in seen:
            groups.append({"name": name, "probability": 100.0})
            seen.add(name)
    if not groups:
        groups.append({"name": "1", "probability": 100.0})
    return groups


def roll_stage13_lapine(data_dir, parsed_items, item_id, table_key, seed=None):
    runtime = build_stage13_lapine_runtime(data_dir, parsed_items)
    item_id = int(item_id)
    key = str(table_key or "")
    boxes = runtime["target_map"].get(item_id, [])
    if not any(str(box.get("key") or "") == key for box in boxes):
        raise ValueError(f"物品 {item_id} 不支援 Lapine 資料 {key}")
    profile = runtime["probability"].get("tables", {}).get(key)
    if not _stage13_lapine_profile_has_rows(profile):
        raise ValueError(f"Lapine {key} 沒有有效機率表")

    generator = (
        _stage13_random.Random(seed)
        if seed is not None
        else _stage13_random.SystemRandom()
    )
    rows = [
        dict(row) for row in profile.get("rows", [])
        if isinstance(row, dict)
    ]
    groups = _stage13_normalize_profile_groups(profile)
    normalized = _stage13_defaultdict(list)

    for raw in rows:
        group = str(raw.get("group") or "1").strip() or "1"
        code = str(raw.get("option_code") or "").strip()
        try:
            probability = float(raw.get("probability", 0.0))
        except (TypeError, ValueError):
            probability = 0.0
        if probability <= 0 or not code:
            continue
        try:
            minimum = int(raw.get("min_value", 0))
            maximum = int(raw.get("max_value", minimum))
        except (TypeError, ValueError):
            minimum = maximum = 0
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        normalized[group].append({
            **raw,
            "group": group,
            "option_code": code,
            "probability": probability,
            "min_value": minimum,
            "max_value": maximum,
            "value_choices": _stage13_value_choices(
                raw.get("value_choices", [])
            ),
        })

    results = []
    attempts = []
    for group in groups:
        group_name = str(group.get("name") or "").strip()
        if not group_name:
            continue
        try:
            group_probability = float(group.get("probability", 100.0))
        except (TypeError, ValueError):
            group_probability = 100.0
        group_rows = normalized.get(group_name, [])
        if not group_rows:
            attempts.append({
                "group": group_name,
                "group_probability": group_probability,
                "success": False,
                "reason": "群組內沒有有效附魔列",
            })
            continue

        group_roll = float(generator.random()) * 100.0
        if group_roll >= group_probability:
            attempts.append({
                "group": group_name,
                "group_probability": group_probability,
                "group_roll": group_roll,
                "success": False,
                "reason": "群組未出現",
            })
            continue

        total = sum(float(row["probability"]) for row in group_rows)
        roll_limit = total if total > 100.0 + 1e-9 else 100.0
        option_roll = float(generator.random()) * roll_limit
        cumulative = 0.0
        selected = None
        for row in group_rows:
            cumulative += float(row["probability"])
            if option_roll < cumulative:
                selected = row
                break
        if selected is None:
            attempts.append({
                "group": group_name,
                "group_probability": group_probability,
                "group_roll": group_roll,
                "option_roll": option_roll,
                "option_roll_limit": roll_limit,
                "success": False,
                "reason": "組內未抽中任何詞條",
            })
            continue

        choices = selected.get("value_choices", [])
        value = (
            int(generator.choice(choices))
            if choices
            else int(generator.randint(
                int(selected["min_value"]),
                int(selected["max_value"]),
            ))
        )
        code = str(selected["option_code"])
        display_template = str(runtime["option_names"].get(code) or code)
        lua_template = str(runtime["enchant_names"].get(code) or "")
        result = {
            "group": group_name,
            "group_probability": group_probability,
            "group_roll": group_roll,
            "option_roll": option_roll,
            "option_roll_limit": roll_limit,
            "row_probability": float(selected["probability"]),
            "option_code": code,
            "value": value,
            "display_text": _stage13_replace_percent_tokens(
                display_template, str(value)
            ),
            "lua_effect": _stage13_replace_percent_tokens(
                lua_template, str(value)
            ),
            "success": True,
        }
        results.append(result)
        attempts.append(result)

    return {
        "success": bool(results),
        "item_id": item_id,
        "table_key": key,
        "results": results,
        "attempts": attempts,
        "lua_effect": "\n".join(
            str(row.get("lua_effect") or "").strip()
            for row in results
            if str(row.get("lua_effect") or "").strip()
        ),
    }

# === STAGE 17 共用傷害核心 ===
# 從目前 Desktop 語意抽出的、不依賴 Qt 的標準傷害流程。
import ast as _stage17_ast
import csv as _stage17_csv
import math as _stage17_math
import os as _stage17_os
import re as _stage17_re
from typing import Any as _Stage17Any

STAGE17_DAMAGE_TABLES = {1: [[100, 100, 100, 100, 100, 100, 100, 100, 90, 100], [100, 25, 100, 150, 90, 150, 100, 100, 100, 100], [100, 100, 25, 90, 150, 150, 100, 100, 100, 100], [100, 90, 150, 25, 100, 150, 100, 100, 100, 125], [100, 150, 90, 100, 25, 150, 100, 100, 100, 100], [100, 150, 150, 150, 150, 0, 75, 75, 75, 75], [100, 100, 100, 100, 100, 75, 0, 125, 100, 125], [100, 100, 100, 100, 100, 75, 125, 0, 100, 0], [90, 100, 100, 100, 100, 75, 90, 90, 125, 100], [100, 90, 100, 100, 100, 75, 125, 0, 100, 0]], 2: [[100, 100, 100, 100, 100, 100, 100, 100, 70, 100], [100, 0, 100, 175, 80, 150, 100, 100, 100, 100], [100, 100, 0, 80, 175, 150, 100, 100, 100, 100], [100, 80, 175, 0, 100, 150, 100, 100, 100, 150], [100, 175, 80, 100, 0, 150, 100, 100, 100, 100], [100, 150, 150, 150, 150, 0, 75, 75, 75, 50], [100, 100, 100, 100, 100, 75, 0, 150, 100, 150], [100, 100, 100, 100, 100, 75, 150, 0, 100, 0], [70, 100, 100, 100, 100, 75, 80, 80, 150, 125], [100, 80, 100, 100, 100, 50, 150, 0, 125, 0]], 3: [[100, 100, 100, 100, 100, 100, 100, 100, 50, 100], [100, 0, 100, 200, 70, 125, 100, 100, 100, 100], [100, 100, 0, 70, 200, 125, 100, 100, 100, 100], [100, 70, 200, 0, 100, 125, 100, 100, 100, 175], [100, 200, 70, 100, 0, 125, 100, 100, 100, 100], [100, 125, 125, 125, 125, 0, 50, 50, 50, 25], [100, 100, 100, 100, 100, 50, 0, 175, 100, 175], [100, 100, 100, 100, 100, 50, 175, 0, 100, 0], [50, 100, 100, 100, 100, 50, 70, 70, 175, 150], [100, 70, 100, 100, 100, 25, 175, 0, 150, 0]], 4: [[100, 100, 100, 100, 100, 100, 100, 100, 0, 100], [100, 0, 100, 200, 60, 125, 100, 100, 100, 100], [100, 100, 0, 60, 200, 125, 100, 100, 100, 100], [100, 60, 200, 0, 100, 125, 100, 100, 100, 200], [100, 200, 60, 100, 0, 125, 100, 100, 100, 100], [100, 125, 125, 125, 125, 0, 50, 50, 50, 0], [100, 100, 100, 100, 100, 50, 0, 200, 100, 200], [100, 100, 100, 100, 100, 50, 200, 0, 100, 0], [0, 100, 100, 100, 100, 50, 60, 60, 200, 175], [100, 60, 100, 100, 100, 0, 200, 0, 175, 0]]}
STAGE17_ELEMENT_MAP = {0: '無屬性', 1: '水屬性', 2: '地屬性', 3: '火屬性', 4: '風屬性', 5: '毒屬性', 6: '聖屬性', 7: '暗屬性', 8: '念屬性', 9: '不死屬性', 10: '全屬性', 999: '（不使用）'}
STAGE17_WEAPON_TYPE_SIZE_PENALTY = {0: [100, 100, 100], 1: [100, 75, 50], 2: [75, 100, 75], 3: [75, 75, 100], 4: [75, 75, 100], 5: [75, 75, 100], 6: [50, 75, 100], 7: [50, 75, 100], 8: [75, 100, 100], 10: [100, 100, 100], 11: [100, 100, 75], 12: [100, 100, 75], 13: [75, 100, 75], 14: [75, 100, 75], 15: [100, 100, 50], 16: [75, 100, 75], 17: [100, 100, 100], 18: [100, 100, 100], 19: [100, 100, 100], 20: [100, 100, 100], 21: [100, 100, 100], 22: [75, 75, 100], 23: [100, 100, 100]}

STAGE17_STAT_NAMES = (
    "STR", "AGI", "VIT", "INT", "DEX", "LUK",
    "POW", "STA", "WIS", "SPL", "CON", "CRT",
)
STAGE17_STAT_GIDS = {
    "STR": 32, "AGI": 33, "VIT": 34, "INT": 35, "DEX": 36, "LUK": 37,
    "POW": 255, "STA": 256, "WIS": 257, "SPL": 258, "CON": 259, "CRT": 260,
}
STAGE17_SIZE_NAMES = ["小型", "中型", "大型"]
STAGE17_ELEMENT_NAMES = [
    "無屬性", "水屬性", "地屬性", "火屬性", "風屬性",
    "毒屬性", "聖屬性", "暗屬性", "念屬性", "不死屬性", "全屬性",
]
# 這些效果名稱 map 必須與 Desktop 的 apply_all_damage_effects() 完全一致。
# UI 的目標 map 範圍更廣（例如玩家種族 / 守護者階級），但 Desktop
# 只會為下列名稱建立實際使用的傷害效果屬性。
STAGE17_RACE_DAMAGE_NAMES = ["無形", "不死", "動物", "植物", "昆蟲", "魚貝", "惡魔", "人形", "天使", "龍族"]
STAGE17_CLASS_DAMAGE_NAMES = ["一般", "首領"]
STAGE17_CLASS_DEF_NAMES = ["一般", "首領", "玩家"]
STAGE17_DEX_WEAPON_CLASSES = {11, 13, 14, 17, 18, 19, 20, 21}


def _stage17_number(value, default=0.0):
    try:
        if value is None or str(value).strip().lower() in {"", "nan", "none"}:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _stage17_int(value, default=0):
    try:
        if value is None or str(value).strip().lower() in {"", "nan", "none"}:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _stage17_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


# ==================== DEF 計算 ==================
def stage17_calc_final_def_damage(d_ef: float, reduction_percent: float) -> float:
    """
    根據原 Desktop / Excel 公式計算最終物理傷害比例。

    d_ef: 後 DEF 數值
    reduction_percent: DEF 破防百分比（例如 64 表示 64%）
    回傳: 傷害倍率（小數，例如 0.4222）
    """
    reduction = float(reduction_percent) / 100
    if reduction > 0.99:
        return 1.0
    adj = float(d_ef) - (float(d_ef) * reduction) - reduction
    if adj <= -399:
        adj = -399
    resistance = (4000 + adj) / (4000 + adj * 10)
    # 原 Desktop 註解：範圍限制在 -0.99~1。
    # 來源：https://forum.gamer.com.tw/C.php?bsn=4212&snA=440067&tnum=5&bPage=2
    return 1 if d_ef == 0 else max(resistance, -0.99) 


# ==================== MRES / MDEF 計算 ===================
# ==================== MDEF 計算 ==================
def stage17_calc_final_mdef_damage(mdef: float, reduction_percent: float) -> float:
    """
    根據原 Desktop / Excel 公式計算最終魔法傷害比例。

    mdef: 後 MDEF 數值
    reduction_percent: MDEF 破防百分比（例如 64 表示 64%）
    回傳: 傷害倍率（小數，例如 0.4222）
    """
    reduction = float(reduction_percent) / 100
    if reduction > 0.99:
        return 1.0
    adj = float(mdef) - (float(mdef) * reduction) - reduction
    if adj <= -99:
        adj = -99
    resistance = (1000 + adj) / (1000 + adj * 10)
    # 原 Desktop 註解：範圍限制在 -0.99~1。
    # 來源：https://forum.gamer.com.tw/C.php?bsn=4212&snA=440067&tnum=5&bPage=2
    return 1 if mdef == 0 else max(resistance, -0.99) 


# ==================== RES / MRES 計算 ==================
def stage17_calc_final_res_damage(mres: float, reduction_percent: float) -> float:
    reduction = float(reduction_percent) / 100
    if reduction > 0.99:
        return 1.0
    adj = float(mres) - (float(mres) * reduction) - reduction
    resistance = (2000 + adj) / (2000 + adj * 5)
    return min(resistance, 1.0)  # 保證不超過 1.0


# ========================== 精煉計算 =========================
def _stage17_weapon_refine(level, refine, grade, *, magic=False):
    """ATK / MATK 共用的武器精煉核心。

    原 Desktop 兩支函式的共同規則：
    - 1~4 階：每 +1 有固定加成；超過安定值後，每 +1 再給浮動加成（這裡取上限）。
    - 精煉 > 15：沿用舊邏輯，固定加成切換成 over16_bonus 對應值。
    - 5 階：依品級每 +1 固定 ATK/MATK，並每 +1 固定 +2 P.ATK/S.MATK。
    - magic=True 時使用原 MATK 的五階安定值設定；False 時使用 ATK 設定。
    """
    level = _stage17_int(level)
    refine = _stage17_int(refine)
    grade = _stage17_int(grade)
    if level == 0 or refine <= 0:
        return 0, 0, 0, 0

    # 每精煉 +1 增加 ATK / MATK。
    base_per_refine = {1: 2, 2: 3, 3: 5, 4: 7, 5: 0}
    # 超過安定值後，每 +1 額外「浮動」增加的上限值。
    extra_after_safe = {1: 3, 2: 5, 3: 8, 4: 14, 5: 0}
    # 精煉 16 以上使用的下一階額外加成。
    over16_bonus = {1: 3, 2: 5, 3: 7, 4: 10, 5: 0}
    # 安定值：原 MATK 五階為 0；ATK 五階為 4。
    safe_threshold = {1: 7, 2: 6, 3: 5, 4: 4, 5: 0 if magic else 4}
    # 五階各品級的每 +1 ATK / MATK（N / D / C / B / A）。
    grade_bonus = {0: 8.0, 1: 8.8, 2: 10.4, 3: 12.0, 4: 16.0}
    if level < 5:
        if level not in base_per_refine:
            return 0, 0, 0, 0
        # 固定加成：所有等級都算。
        base = refine * base_per_refine[level]
        # 浮動加成：只在超過安定值的精煉級數計算（取上限）。
        safe = safe_threshold[level]
        variance = max(0, refine - safe) * extra_after_safe[level]
        variance_min = 1  # 基礎最小值
        # 16 以上更換下一階額外加成；保留拆分前 Desktop 行為。
        if refine > 15:
            base = refine * over16_bonus[level]
        return base + variance, 0, variance, variance_min

    # 五階：依品級固定 ATK/MATK，並每 +1 固定 +2 P.ATK/S.MATK。
    per_refine = grade_bonus.get(grade, 0.0)
    return refine * per_refine, refine * 2, 0, 0


def stage17_calc_weapon_refine_atk(weapon_Level, weaponRefineR, weaponGradeR):
    """
    回傳： (ATK 總加成, P.ATK 總加成, 浮動上限, 浮動最小值)
    說明：
      1~4 階：每 +1 固定加成；超過安定值後，每 +1 額外給「浮動加成(這裡取上限)」；
              若精煉 > 15，則沿用舊版 over16_bonus 規則。
      5 階：依品級每 +1 固定 ATK，加上每 +1 固定 +2 P.ATK。
    """
    return _stage17_weapon_refine(weapon_Level, weaponRefineR, weaponGradeR, magic=False)


def stage17_calc_weapon_refine_matk(weapon_Level, weaponRefineR, weaponGradeR):
    """
    回傳： (MATK 總加成, S.MATK 總加成, 浮動上限, 浮動最小值)
    說明：
      1~4 階：每 +1 固定加成；超過安定值後，每 +1 額外給「浮動加成(取上限)」；
              若精煉 > 15，則沿用舊版 over16_bonus 規則。
      5 階：依品級每 +1 固定 MATK，加上每 +1 固定 +2 S.MATK。
    """
    return _stage17_weapon_refine(weapon_Level, weaponRefineR, weaponGradeR, magic=True)


# 查詢屬性倍率函數
def stage17_get_damage_multiplier(attacker_element: int, defender_element: int, level: int) -> int:
    attacker_element = _stage17_int(attacker_element)
    defender_element = _stage17_int(defender_element)
    level = _stage17_int(level, 1)
    if level not in STAGE17_DAMAGE_TABLES:
        raise ValueError("不支援的屬性等級（僅支援 Lv1~Lv4）")
    if attacker_element not in STAGE17_ELEMENT_MAP or defender_element not in STAGE17_ELEMENT_MAP:
        raise ValueError("屬性 ID 必須在 Desktop element_map 範圍內")
    return STAGE17_DAMAGE_TABLES[level][attacker_element][defender_element]


# 武器體型懲罰（物理）
def stage17_get_size_penalty(weapon_class: int, target_size: int) -> float:
    """根據武器類型與目標體型回傳懲罰倍率（小數，例如 1.0, 0.75）。"""
    penalties = STAGE17_WEAPON_TYPE_SIZE_PENALTY.get(_stage17_int(weapon_class), [100, 100, 100])
    target_size = _stage17_int(target_size)
    if 0 <= target_size < len(penalties):
        raw = float(penalties[target_size])
        # 目前 Desktop 表格存的是百分比（100/75/50）。下方分支
        # 也接受正規化後的測試 / 自訂表格（1.0/0.75/0.5），
        # 不會改變真正 Desktop 的既有語意。
        return raw if abs(raw) <= 1.5 else raw / 100.0
    return 1.0


def stage17_apply_stepwise(base, *items):
    """
    每層乘完取整，依據 mode 控制加 / 減 / 固定值：
    - mode = 1      → 加成百分比：乘 (1 + bonus / 100)
    - mode = 1.4    → 特殊加成百分比：乘 (1.4 + bonus / 100)
    - mode = 0      → 原始倍率：乘 (bonus / 100)
    - mode = -1     → 減傷百分比：乘 (1 - bonus / 100)
    - mode = None   → 固定扣值：value -= bonus
    - mode = "raw"  → 直接乘：value *= bonus（不除以 100）
    - mode = "+"    → 直接加：value += bonus

    base 可傳單值，或 (base, base_min) 雙值；後者會同步計算最大/最小傷害。
    """
    # base: 單值 或 (base, base_min)
    is_pair = isinstance(base, (tuple, list)) and len(base) == 2
    if is_pair:
        value, value_min = base
    else:
        value, value_min = base, None

    def apply_one(current, bonus, mode):
        current = float(current)
        bonus = float(bonus)
        if mode is None:
            return current - bonus
        if mode == "raw":
            return _stage17_math.floor(current * bonus + 1e-9)
        if mode == "+":
            return current + bonus
        if mode == 1:
            multiplier = 1 + bonus / 100
        elif mode == 1.4:
            multiplier = 1.4 + bonus / 100
        elif mode == -1:
            multiplier = 1 - bonus / 100
        else:
            multiplier = bonus / 100
        return _stage17_math.floor(current * multiplier + 1e-9)

    steps = []
    for item in items:
        if len(item) == 3:
            bonus, mode, name = item
            if is_pair and isinstance(bonus, (tuple, list)) and len(bonus) == 2:
                bonus_main, bonus_min = bonus
            else:
                bonus_main = bonus_min = bonus
        elif len(item) == 4:
            bonus_main, bonus_min, mode, name = item
        else:
            raise ValueError("damage step 格式錯誤")
        value = apply_one(value, bonus_main, mode)
        if is_pair:
            value_min = apply_one(value_min, bonus_min, mode)
        steps.append({"name": str(name), "value": bonus_main, "mode": mode})
    return ((value, value_min) if is_pair else value), steps


def _stage17_safe_eval(expression: str, variables: dict[str, _Stage17Any]):
    allowed_functions = {
        "floor": _stage17_math.floor,
        "ceil": _stage17_math.ceil,
        "trunc": _stage17_math.trunc,
    }
    tree = _stage17_ast.parse(str(expression), mode="eval")
    allowed_nodes = (
        _stage17_ast.Expression, _stage17_ast.BinOp, _stage17_ast.UnaryOp,
        _stage17_ast.Add, _stage17_ast.Sub, _stage17_ast.Mult, _stage17_ast.Div,
        _stage17_ast.FloorDiv, _stage17_ast.Mod, _stage17_ast.Pow,
        _stage17_ast.USub, _stage17_ast.UAdd, _stage17_ast.Constant,
        _stage17_ast.Name, _stage17_ast.Call, _stage17_ast.Load,
    )
    for node in _stage17_ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError(f"公式含不支援語法：{type(node).__name__}")
        if isinstance(node, _stage17_ast.Call):
            if not isinstance(node.func, _stage17_ast.Name) or node.func.id not in allowed_functions:
                raise ValueError("公式只允許 floor/ceil/trunc 函式")
    env = {**allowed_functions, **variables}
    return eval(compile(tree, "<stage17-formula>", "eval"), {"__builtins__": {}}, env)



def stage17_replace_gsklv_calls(formula, enabled_levels):
    text = _stage17_text(formula)
    levels = enabled_levels if isinstance(enabled_levels, dict) else {}
    return _stage17_re.sub(
        r"GSklv\((\d+)\)",
        lambda match: str(_stage17_int(levels.get(int(match.group(1)), 0))),
        text,
    )


def stage17_replace_gusklv_calls(formula, used_levels):
    text = _stage17_text(formula)
    levels = used_levels if isinstance(used_levels, dict) else {}
    return _stage17_re.sub(
        r"GUSklv\((\d+)\)",
        lambda match: str(_stage17_int(levels.get(int(match.group(1)), 0))),
        text,
    )


def stage17_replace_size_calls(formula, target_size):
    text = _stage17_text(formula)
    target_size = _stage17_int(target_size)

    def repl(match):
        values = [value.strip() for value in match.group(1).split(",")]
        if target_size < 0 or target_size >= len(values):
            raise ValueError(f"target_size={target_size} 超出 size() 範圍")
        return values[target_size]

    return _stage17_re.sub(r"size\(([^)]*)\)", repl, text)


def stage17_replace_custom_calls(formula, weapon_class):
    if not isinstance(formula, str):
        return formula
    weapon_class = _stage17_int(weapon_class)

    def repl(match):
        target_types = {
            _stage17_int(value)
            for value in match.group(1).split("|")
        }
        return match.group(2) if weapon_class in target_types else match.group(3)

    return _stage17_re.sub(
        r"WPon\(([\d|]+)\)([^:]+):([^:\)\s\+\-\*/]+)",
        repl,
        formula,
    )


def stage17_eval_formula_with_vars(formula, allowed_vars):
    """與 Desktop 相容的公式展開與求值。"""
    expanded = _stage17_text(formula)
    variables = allowed_vars if isinstance(allowed_vars, dict) else {}
    for name, value in variables.items():
        expanded = _stage17_re.sub(
            rf"\b{_stage17_re.escape(str(name))}\b",
            str(value),
            expanded,
        )
    try:
        result = _stage17_safe_eval(expanded, {})
    except (SyntaxError, NameError, ZeroDivisionError, TypeError, ValueError):
        return expanded, None
    return expanded, result


def _stage17_replace_calls(formula, *, target_size, weapon_class, enabled_levels, used_levels):
    text = stage17_replace_gsklv_calls(formula, enabled_levels)
    text = stage17_replace_gusklv_calls(text, used_levels)
    text = stage17_replace_size_calls(text, target_size)
    return stage17_replace_custom_calls(text, weapon_class)


def _stage17_parse_hits(value, skill_level, *, target_size, weapon_class, enabled_levels, used_levels):
    text = _stage17_replace_calls(
        value,
        target_size=target_size,
        weapon_class=weapon_class,
        enabled_levels=enabled_levels,
        used_levels=used_levels,
    ).strip()
    if not text:
        return 1
    text = _stage17_re.sub(r"\bSklv\b", str(_stage17_int(skill_level)), text)
    if not _stage17_re.fullmatch(r"[0-9+\-*/().\s%]+", text):
        return 1
    try:
        return int(_stage17_safe_eval(text.replace("/", "//"), {}))
    except Exception:
        return 1


def _stage17_csv_rows(data_dir):
    path = _stage17_os.path.join(_stage17_os.fspath(data_dir), "skillneme.csv")
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        for index, row in enumerate(_stage17_csv.DictReader(handle)):
            normalized = {str(key): _stage17_text(value) for key, value in row.items()}
            normalized["_source_index"] = index
            rows.append(normalized)
    return rows


def stage17_get_skill_row(data_dir, skill_id):
    target = str(_stage17_int(skill_id))
    for row in _stage17_csv_rows(data_dir):
        if _stage17_text(row.get("ID")) == target:
            return row
    return None


def search_stage17_damage_skills(data_dir, job_dict, job_id=0, query="", limit=500):
    rows = _stage17_csv_rows(data_dir)
    query_cf = _stage17_text(query).casefold()
    job_info = job_dict.get(job_id, job_dict.get(str(job_id), {})) if isinstance(job_dict, dict) else {}
    prefixes = {
        value.strip()
        for value in _stage17_text((job_info or {}).get("selectskill", "")).split("/")
        if value.strip()
    }
    results = []
    for row in rows:
        if not _stage17_text(row.get("Slv")):
            continue
        name = _stage17_text(row.get("Name"))
        code = _stage17_text(row.get("Code"))
        if query_cf:
            if query_cf not in f"{row.get('ID','')} {code} {name}".casefold():
                continue
        elif prefixes:
            code_prefix = code.split("_", 1)[0] if "_" in code else code
            if code_prefix not in prefixes:
                continue
        results.append({
            "skill_id": _stage17_int(row.get("ID")),
            "code": code,
            "name": name,
            "attack_type": (_stage17_text(row.get("attack_type")) or "physical").lower(),
            "default_level": _stage17_int(row.get("Slv"), 1),
            "formula": _stage17_text(row.get("Calculation")),
            "hits": _stage17_text(row.get("hits")) or "1",
            "element": _stage17_int(row.get("element"), 0),
            "critical_hit": _stage17_number(row.get("Critical_hit"), 0),
            "has_combo": bool(_stage17_text(row.get("combo")) and _stage17_text(row.get("combo_hits"))),
            "source_index": row["_source_index"],
        })
        if len(results) >= max(1, min(_stage17_int(limit, 500), 1000)):
            break
    return results


def _stage17_sum_effect(effect_dict, name, unit=""):
    return sum(
        float(value)
        for value, _source in effect_dict.get((str(name), str(unit)), [])
        if isinstance(value, (int, float))
    )


def _stage17_sum_skill_effect(effect_dict, skill_name, suffix):
    # Desktop 目前會在顯示字串中裝飾技能名稱；共用 runner
    # 透過比對實際語意片段來容忍這些外層格式，
    # 而不是依賴單一固定的顯示 token。
    target_name = str(skill_name or "")
    target_suffix = str(suffix or "")
    total = 0.0
    for key, values in (effect_dict or {}).items():
        if not isinstance(key, tuple) or len(key) != 2:
            continue
        label, unit = str(key[0]), str(key[1])
        if unit != "%" or target_name not in label or target_suffix not in label:
            continue
        for value, _source in values or []:
            if isinstance(value, (int, float)):
                total += float(value)
    return total



# === STAGE 21.24 DESKTOP / WEB 共用技能時間核心 ===
# 唯一計算來源，抽自 Desktop 的 ItemSearchApp.update_skill_delay_labels()。
# Desktop 只保留 QLabel / CastBar 顯示層；Web 與 Desktop 都呼叫這些
# 不依賴 Qt / FastAPI 的 helper，負責解析 skilldelaylist.lua 與時間計算。
_STAGE23_SKILL_DELAY_CACHE = {"path": None, "mtime_ns": None, "text": ""}


def _stage23_load_skill_delay_text(data_dir):
    from pathlib import Path

    path = Path(data_dir) / "skilldelaylist.lua"
    try:
        stat = path.stat()
    except OSError:
        return "", f"找不到 {path.name}"

    cache = _STAGE23_SKILL_DELAY_CACHE
    cache_path = str(path.resolve())
    if cache.get("path") == cache_path and cache.get("mtime_ns") == stat.st_mtime_ns:
        return str(cache.get("text") or ""), ""

    text = ""
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            text = path.read_text(encoding=encoding)
            last_error = None
            break
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except OSError as exc:
            return "", f"讀取 {path.name} 失敗：{exc}"

    if not text and last_error is not None:
        try:
            text = path.read_text(encoding="big5", errors="replace")
        except OSError as exc:
            return "", f"讀取 {path.name} 失敗：{exc}"

    cache.update({"path": cache_path, "mtime_ns": stat.st_mtime_ns, "text": text})
    return text, ""


def stage24_resolve_skill_code(skill_name, skill_map_all):
    """不依賴 UI、與 Desktop 相容的 Name -> Code 解析器。"""
    target_name = str(skill_name or "")
    for _skill_id, row in (skill_map_all or {}).items():
        if not isinstance(row, dict) or str(row.get("Name") or "") != target_name:
            continue
        code = row.get("Code") or row.get("SkillCode") or row.get("SkillNameCode")
        if code not in (None, ""):
            return str(code)
    return ""


def stage24_find_skill_delay_block(lua_text, skill_code):
    """使用 Desktop 的大括號語意，回傳一個 [SKID.CODE] Lua table block。"""
    if not lua_text or not skill_code:
        return None

    start_pat = re.compile(
        rf"\[\s*SKID\.{re.escape(str(skill_code))}\s*\]\s*=\s*\{{",
        re.MULTILINE,
    )
    match = start_pat.search(str(lua_text))
    if not match:
        return None

    open_index = match.end() - 1
    depth = 0
    for index in range(open_index, len(lua_text)):
        char = lua_text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return lua_text[open_index:index + 1]
    return None


def stage24_parse_skill_delay_array(block, field):
    """解析一個 Desktop 技能延遲 array；缺少或空欄位視為 [0]。"""
    match = re.search(
        rf"{re.escape(str(field))}\s*=\s*\{{([^}}]*)\}}",
        str(block or ""),
        re.MULTILINE,
    )
    if not match:
        return [0]
    numbers = re.findall(r"-?\d+", match.group(1))
    return [int(value) for value in numbers] if numbers else [0]


def stage24_format_delay_ms(values, skill_level):
    """Desktop 舊版 pick() 格式化邏輯，已搬到 Core。"""
    values = list(values or [0])
    if not values:
        values = [0]

    def ms_to_s(ms):
        return f"{float(ms) / 1000.0:.3f}".rstrip("0").rstrip(".")

    if skill_level is None:
        return "/".join(ms_to_s(value) for value in values)

    level = max(_stage17_int(skill_level, 1), 1)
    index = max(level - 1, 0)
    value = values[index] if index < len(values) else values[-1]
    return ms_to_s(value)


def _stage24_pick_display_ms(values, skill_level):
    values = list(values or [0])
    if not values:
        values = [0]
    level = max(_stage17_int(skill_level, 1), 1)
    index = max(level - 1, 0)
    return float(values[index] if index < len(values) else values[-1])


def _stage24_pick_desktop_runtime_ms(values, skill_level):
    """完整保留 Desktop CastBar / ASPD 的舊版索引方式。

    ItemSearchApp 過去在 label 文字使用 skill_level-1，但 CastBar / raw GCD 使用
    skill_level。Core 抽離期間保留此行為，確保 Stage 21.24 只是架構重構，
    而不是悄悄修改遊戲計算行為。
    """
    values = list(values or [0])
    if not values:
        values = [0]
    index = max(_stage17_int(skill_level, 0), 0)
    return float(values[index] if index < len(values) else values[-1])


def stage24_calculate_skill_timing_values(
    *,
    skill_name,
    lua_text,
    skill_level,
    skill_map_all=None,
    skill_code=None,
    equip_fixed_ms=0.0,
    equip_fixed_percent=0.0,
    base_stat=0.0,
    equip_variable_percent=0.0,
    equip_global_post_percent=0.0,
    equip_cooldown_ms=0.0,
    selected_variable_cast_ms=0.0,
):
    """Desktop / Web 共用的技能詠唱、後延遲與冷卻時間計算。

    這是從 Desktop ``update_skill_delay_labels()`` 抽出的非 UI 主體。
    所有延遲 array 的單位都是毫秒。

    ``base_stat`` 是 Desktop 使用的 ``DEX + INT/2`` 數值。
    裝備修正沿用既有效果 parser 已產生的正負號與單位。
    """
    code = str(skill_code or "").strip()
    if not code:
        code = stage24_resolve_skill_code(skill_name, skill_map_all)

    level = max(_stage17_int(skill_level, 1), 1)
    base_result = {
        "available": False,
        "error_code": "",
        "message": "",
        "skill_code": code,
        "level": level,
    }

    if not code:
        return {
            **base_result,
            "error_code": "skill_code_not_found",
            "message": "技能代碼找不到",
        }

    block = stage24_find_skill_delay_block(lua_text, code)
    if not block:
        return {
            **base_result,
            "error_code": "lua_skill_not_found",
            "message": f"skilldelaylist.lua 找不到 SKID.{code}",
        }

    fixed_raw = stage24_parse_skill_delay_array(block, "SkillCastFixedDelay")
    variable_raw = stage24_parse_skill_delay_array(block, "SkillCastStatDelay")
    global_post_raw = stage24_parse_skill_delay_array(block, "SkillGlobalPostDelay")
    cooldown_raw = stage24_parse_skill_delay_array(block, "SkillSinglePostDelay")

    base_stat_number = max(0.0, _stage17_number(base_stat, 0.0))
    stat_reduction_percent = (
        math.sqrt(base_stat_number / 265.0) * 100.0
        if base_stat_number > 0
        else 0.0
    )

    fixed_ms = [
        max(
            0.0,
            (float(value) + _stage17_number(equip_fixed_ms, 0.0))
            * ((100.0 + _stage17_number(equip_fixed_percent, 0.0)) / 100.0),
        )
        for value in fixed_raw
    ]
    variable_ms = [
        max(
            0.0,
            (float(value) + _stage17_number(selected_variable_cast_ms, 0.0))
            * ((100.0 - stat_reduction_percent) / 100.0)
            * ((100.0 + _stage17_number(equip_variable_percent, 0.0)) / 100.0),
        )
        for value in variable_raw
    ]
    global_post_ms = [
        max(
            0.0,
            float(value)
            * ((100.0 + _stage17_number(equip_global_post_percent, 0.0)) / 100.0),
        )
        for value in global_post_raw
    ]
    cooldown_ms = [
        max(0.0, float(value) + _stage17_number(equip_cooldown_ms, 0.0))
        for value in cooldown_raw
    ]

    selected = {
        "fixed_ms": _stage24_pick_display_ms(fixed_ms, level),
        "variable_ms": _stage24_pick_display_ms(variable_ms, level),
        "global_post_ms": _stage24_pick_display_ms(global_post_ms, level),
        "cooldown_ms": _stage24_pick_display_ms(cooldown_ms, level),
        "fixed_raw_ms": _stage24_pick_display_ms(fixed_raw, level),
        "variable_raw_ms": _stage24_pick_display_ms(variable_raw, level),
        "global_post_raw_ms": _stage24_pick_display_ms(global_post_raw, level),
        "cooldown_raw_ms": _stage24_pick_display_ms(cooldown_raw, level),
    }

    # 保留 Desktop 歷史上的 CastBar / ASPD-GCD 索引方式，不做變更。
    desktop_runtime = {
        "fixed_ms": _stage24_pick_desktop_runtime_ms(fixed_ms, skill_level),
        "variable_ms": _stage24_pick_desktop_runtime_ms(variable_ms, skill_level),
        "global_post_ms": _stage24_pick_desktop_runtime_ms(global_post_ms, skill_level),
        "cooldown_ms": _stage24_pick_desktop_runtime_ms(cooldown_ms, skill_level),
        "global_post_raw_ms": _stage24_pick_desktop_runtime_ms(global_post_raw, skill_level),
    }
    desktop_runtime["cast_total_ms"] = max(
        0.0,
        desktop_runtime["fixed_ms"] + desktop_runtime["variable_ms"],
    )

    return {
        **base_result,
        "available": True,
        "arrays": {
            "fixed_ms": fixed_ms,
            "variable_ms": variable_ms,
            "global_post_ms": global_post_ms,
            "cooldown_ms": cooldown_ms,
            "fixed_raw_ms": fixed_raw,
            "variable_raw_ms": variable_raw,
            "global_post_raw_ms": global_post_raw,
            "cooldown_raw_ms": cooldown_raw,
        },
        "selected": selected,
        "desktop_runtime": desktop_runtime,
        "display": {
            "fixed": stage24_format_delay_ms(fixed_ms, skill_level),
            "fixed_raw": stage24_format_delay_ms(fixed_raw, skill_level),
            "variable": stage24_format_delay_ms(variable_ms, skill_level),
            "variable_raw": stage24_format_delay_ms(variable_raw, skill_level),
            "global_post": stage24_format_delay_ms(global_post_ms, skill_level),
            "global_post_raw": stage24_format_delay_ms(global_post_raw, skill_level),
            "cooldown": stage24_format_delay_ms(cooldown_ms, skill_level),
            "cooldown_raw": stage24_format_delay_ms(cooldown_raw, skill_level),
        },
        "modifiers": {
            "equip_fixed_ms": round(_stage17_number(equip_fixed_ms, 0.0), 6),
            "equip_fixed_percent": round(_stage17_number(equip_fixed_percent, 0.0), 6),
            "base_stat": round(base_stat_number, 6),
            "stat_cast_reduction_percent": round(stat_reduction_percent, 6),
            "equip_variable_percent": round(_stage17_number(equip_variable_percent, 0.0), 6),
            "equip_global_post_percent": round(_stage17_number(equip_global_post_percent, 0.0), 6),
            "equip_cooldown_ms": round(_stage17_number(equip_cooldown_ms, 0.0), 6),
            "selected_variable_cast_ms": round(_stage17_number(selected_variable_cast_ms, 0.0), 6),
        },
    }


def stage24_extract_skill_timing_modifiers(effect_dict, skill_name):
    """一次抽出 Desktop 與 Web 共用的全部裝備時間修正。"""
    effect_dict = effect_dict or {}
    skill_name = str(skill_name or "")

    fixed_flat_seconds = _stage17_sum_effect(effect_dict, "固定詠唱時間", "秒")
    fixed_percent_values = [
        float(value)
        for value, _source in effect_dict.get(("固定詠唱時間", "%"), [])
        if isinstance(value, (int, float))
    ]
    # Desktop 語意：固定詠唱百分比不疊加；只採用
    # 負值中效果最強的一筆。
    fixed_percent = min(fixed_percent_values, default=0.0)
    variable_percent = _stage17_sum_effect(effect_dict, "變動詠唱時間", "%")
    global_post_percent = _stage17_sum_effect(effect_dict, "技能後延遲", "%")
    cooldown_flat_seconds = _stage17_sum_effect(
        effect_dict,
        f"技能【{skill_name}】冷卻時間",
        "秒",
    )
    selected_variable_flat_seconds = _stage17_sum_effect(
        effect_dict,
        f"技能【{skill_name}】變動詠唱時間",
        "秒",
    )

    return {
        "fixed_cast_flat_seconds": float(fixed_flat_seconds),
        "fixed_cast_percent": float(fixed_percent),
        "variable_cast_percent": float(variable_percent),
        "global_post_delay_percent": float(global_post_percent),
        "skill_cooldown_flat_seconds": float(cooldown_flat_seconds),
        "skill_variable_cast_flat_seconds": float(selected_variable_flat_seconds),
    }


def stage24_calculate_skill_timing_from_effects(
    *,
    skill_name,
    lua_text,
    skill_level,
    effect_dict,
    total_dex,
    total_int,
    skill_map_all=None,
    skill_code=None,
):
    """Desktop 與 Web 共用的高階時間計算入口。

    呼叫端提供已彙總的裝備效果 dictionary 與角色 DEX / INT；
    修正值抽取與全部時間公式都留在 Core。
    """
    modifiers = stage24_extract_skill_timing_modifiers(effect_dict, skill_name)
    shared = stage24_calculate_skill_timing_values(
        skill_name=skill_name,
        skill_map_all=skill_map_all,
        skill_code=skill_code,
        lua_text=lua_text,
        skill_level=skill_level,
        equip_fixed_ms=modifiers["fixed_cast_flat_seconds"] * 1000.0,
        equip_fixed_percent=modifiers["fixed_cast_percent"],
        base_stat=_stage17_number(total_dex, 0) + _stage17_number(total_int, 0) / 2.0,
        equip_variable_percent=modifiers["variable_cast_percent"],
        equip_global_post_percent=modifiers["global_post_delay_percent"],
        equip_cooldown_ms=modifiers["skill_cooldown_flat_seconds"] * 1000.0,
        selected_variable_cast_ms=modifiers["skill_variable_cast_flat_seconds"] * 1000.0,
    )
    shared["effect_modifiers"] = modifiers
    return shared


def calculate_stage23_skill_timing(*, data_dir, skill_row, skill_level, effect_dict, total_dex, total_int):
    """Web / API adapter，使用與 Desktop 完全相同的高階 Core 入口。"""
    row = skill_row if isinstance(skill_row, dict) else {}
    skill_name = _stage17_text(row.get("Name"))
    skill_code = (
        _stage17_text(row.get("Code"))
        or _stage17_text(row.get("SkillCode"))
        or _stage17_text(row.get("SkillNameCode"))
    )

    base_result = {
        "available": False,
        "source": "data/skilldelaylist.lua",
        "message": "",
        "skill_code": skill_code,
        "level": max(_stage17_int(skill_level, 1), 1),
    }
    if not skill_code:
        base_result["message"] = "技能沒有 Code，無法取得技能時間"
        return base_result

    lua_text, load_error = _stage23_load_skill_delay_text(data_dir)
    if load_error:
        base_result["message"] = load_error
        return base_result

    shared = stage24_calculate_skill_timing_from_effects(
        skill_name=skill_name,
        skill_code=skill_code,
        lua_text=lua_text,
        skill_level=skill_level,
        effect_dict=effect_dict,
        total_dex=total_dex,
        total_int=total_int,
    )
    if not shared.get("available"):
        return {
            **base_result,
            "message": str(shared.get("message") or "技能時間資料解析失敗"),
        }

    selected = shared["selected"]
    modifiers = shared["effect_modifiers"]

    def seconds(ms):
        return round(float(ms) / 1000.0, 6)

    return {
        **base_result,
        "available": True,
        "message": "",
        "fixed_cast_seconds": seconds(selected["fixed_ms"]),
        "variable_cast_seconds": seconds(selected["variable_ms"]),
        "cast_total_seconds": seconds(selected["fixed_ms"] + selected["variable_ms"]),
        "global_post_delay_seconds": seconds(selected["global_post_ms"]),
        "cooldown_seconds": seconds(selected["cooldown_ms"]),
        "raw": {
            "fixed_cast_seconds": seconds(selected["fixed_raw_ms"]),
            "variable_cast_seconds": seconds(selected["variable_raw_ms"]),
            "global_post_delay_seconds": seconds(selected["global_post_raw_ms"]),
            "cooldown_seconds": seconds(selected["cooldown_raw_ms"]),
        },
        "modifiers": {
            "fixed_cast_flat_seconds": round(modifiers["fixed_cast_flat_seconds"], 6),
            "fixed_cast_percent": round(modifiers["fixed_cast_percent"], 6),
            "variable_cast_percent": round(modifiers["variable_cast_percent"], 6),
            "stat_cast_reduction_percent": round(
                float(shared["modifiers"]["stat_cast_reduction_percent"]),
                6,
            ),
            "global_post_delay_percent": round(modifiers["global_post_delay_percent"], 6),
            "skill_cooldown_flat_seconds": round(modifiers["skill_cooldown_flat_seconds"], 6),
            "skill_variable_cast_flat_seconds": round(
                modifiers["skill_variable_cast_flat_seconds"],
                6,
            ),
        },
    }


# 提供給 Stage 21.23 舊程式 / 測試使用的向下相容內部 alias。
_stage23_find_skill_delay_block = stage24_find_skill_delay_block
_stage23_parse_delay_array = stage24_parse_skill_delay_array
_stage23_pick_delay_value = _stage24_pick_display_ms

def _stage17_effect_multiplier(effect_dict, category, index):
    index = _stage17_int(index)
    if category in {"D_size", "MD_size"}:
        if 0 <= index < len(STAGE17_SIZE_NAMES):
            prefix = "物理" if category == "D_size" else "魔法"
            return _stage17_sum_effect(effect_dict, f"對 {STAGE17_SIZE_NAMES[index]} 敵人的{prefix}傷害", "%")
        return 0
    if category in {"D_element", "MD_element"}:
        if 0 <= index < len(STAGE17_ELEMENT_NAMES):
            prefix = "物理" if category == "D_element" else "魔法"
            return _stage17_sum_effect(effect_dict, f"對 {STAGE17_ELEMENT_NAMES[index]} 對象的{prefix}傷害", "%")
        return 0
    if category in {"D_Damage", "MD_Damage"}:
        if 0 <= index < len(STAGE17_ELEMENT_NAMES):
            prefix = "物理" if category == "D_Damage" else "魔法"
            return _stage17_sum_effect(effect_dict, f"{STAGE17_ELEMENT_NAMES[index]} 的{prefix}傷害", "%")
        return 0
    if category in {"D_Race", "MD_Race"}:
        prefix = "物理" if category == "D_Race" else "魔法"
        race_name = "全種族" if index == 9999 else (STAGE17_RACE_DAMAGE_NAMES[index] if 0 <= index < len(STAGE17_RACE_DAMAGE_NAMES) else None)
        return _stage17_sum_effect(effect_dict, f"對 {race_name} 型怪的{prefix}傷害", "%") if race_name else 0
    if category in {"D_class", "MD_class"}:
        prefix = "物理" if category == "D_class" else "魔法"
        if 0 <= index < len(STAGE17_CLASS_DAMAGE_NAMES):
            return _stage17_sum_effect(effect_dict, f"對 {STAGE17_CLASS_DAMAGE_NAMES[index]} 階級的{prefix}傷害", "%")
        return 0
    if category in {"D_Race_def", "MD_Race_def"}:
        prefix = "物理" if category == "D_Race_def" else "魔法"
        race_name = "全種族" if index == 9999 else (STAGE17_RACE_DAMAGE_NAMES[index] if 0 <= index < len(STAGE17_RACE_DAMAGE_NAMES) else None)
        return _stage17_sum_effect(effect_dict, f"無視 {race_name} 型怪的{prefix}防禦", "%") if race_name else 0
    if category in {"D_class_def", "MD_class_def"}:
        prefix = "物理" if category == "D_class_def" else "魔法"
        if 0 <= index < len(STAGE17_CLASS_DEF_NAMES):
            return _stage17_sum_effect(effect_dict, f"無視 {STAGE17_CLASS_DEF_NAMES[index]} 階級的{prefix}防禦", "%")
        return 0
    if category in {"D_Race_res", "MD_Race_res"}:
        prefix = "物理" if category == "D_Race_res" else "魔法"
        race_name = "全種族" if index == 9999 else (STAGE17_RACE_DAMAGE_NAMES[index] if 0 <= index < len(STAGE17_RACE_DAMAGE_NAMES) else None)
        return _stage17_sum_effect(effect_dict, f"無視 {race_name} 型怪的{prefix}抗性", "%") if race_name else 0
    return 0


# === 核心去重階段 3：共用目標防禦係數 ===
def stage17_calculate_target_defense_factors(
    *,
    effect_dict,
    target_race,
    target_class,
    target_def,
    target_defc,
    target_res,
    target_mdef,
    target_mres,
    half_bypass_def=0,
    half_bypass_res=0,
):
    """計算 Desktop / Web 共用的 Stage 17 目標防禦 / 無視係數。

    此處刻意保留目前 Desktop 語意：
    - half_bypass_def 會讓 DEF 後倍率變成 1，並把 DEF 移到 DEF 前的固定扣除；
    - half_bypass_res 會強制物理 RES 無視達到 50% 上限；
    - RES / MRES 無視上限為 50%；DEF / MDEF 無視在這裡不設上限。
    """
    target_race = _stage17_int(target_race)
    target_class = _stage17_int(target_class)
    half_bypass_def = _stage17_int(half_bypass_def)
    half_bypass_res = _stage17_int(half_bypass_res)
    target_def = _stage17_number(target_def, 0)
    target_defc = _stage17_number(target_defc, 0)
    target_res = _stage17_number(target_res, 0)
    target_mdef = _stage17_number(target_mdef, 0)
    target_mres = _stage17_number(target_mres, 0)

    # 物理破防：種族 + 全種族 + 階級。
    def_reduction = (
        _stage17_effect_multiplier(effect_dict, "D_Race_def", target_race)
        + _stage17_effect_multiplier(effect_dict, "D_Race_def", 9999)
        + _stage17_effect_multiplier(effect_dict, "D_class_def", target_class)
    )
    # 魔法破防：種族 + 全種族 + 階級。
    mdef_reduction = (
        _stage17_effect_multiplier(effect_dict, "MD_Race_def", target_race)
        + _stage17_effect_multiplier(effect_dict, "MD_Race_def", 9999)
        + _stage17_effect_multiplier(effect_dict, "MD_class_def", target_class)
    )
    # RES：半無視 RES 時直接視為 50% 破抗；其餘取種族 + 全種族。
    res_reduction = 50 if half_bypass_res == 1 else (
        _stage17_effect_multiplier(effect_dict, "D_Race_res", target_race)
        + _stage17_effect_multiplier(effect_dict, "D_Race_res", 9999)
    )
    # MRES：魔法種族抗性 + 全種族抗性。
    mres_reduction = (
        _stage17_effect_multiplier(effect_dict, "MD_Race_res", target_race)
        + _stage17_effect_multiplier(effect_dict, "MD_Race_res", 9999)
    )
    # 原 Desktop 規則：RES / MRES 破抗上限 50%。
    res_reduction = min(res_reduction, 50)
    mres_reduction = min(mres_reduction, 50)

    # 半無視 DEF：後 DEF 乘區直接視為 1，並把後 DEF 併入前 DEF 減算。
    def_multiplier = (
        1.0
        if half_bypass_def == 1
        else stage17_calc_final_def_damage(target_def, def_reduction)
    )
    adjusted_defc = target_def + target_defc if half_bypass_def == 1 else target_defc
    mdef_multiplier = stage17_calc_final_mdef_damage(target_mdef, mdef_reduction)
    res_multiplier = stage17_calc_final_res_damage(target_res, res_reduction)
    mres_multiplier = stage17_calc_final_res_damage(target_mres, mres_reduction)

    return {
        "half_bypass_def": half_bypass_def,
        "half_bypass_res": half_bypass_res,
        "def_reduction": def_reduction,
        "mdef_reduction": mdef_reduction,
        "res_reduction": res_reduction,
        "mres_reduction": mres_reduction,
        "def_multiplier": def_multiplier,
        "mdef_multiplier": mdef_multiplier,
        "res_multiplier": res_multiplier,
        "mres_multiplier": mres_multiplier,
        "target_def": target_def,
        "target_defc": adjusted_defc,
        "target_res": target_res,
        "target_mdef": target_mdef,
        "target_mres": target_mres,
    }


def _stage17_slot_grade(request, slot_id):
    for slot in getattr(request, "slots", []) or []:
        if _stage17_int(getattr(slot, "slot_id", 0)) == slot_id:
            return _stage17_int(getattr(slot, "grade", 0))
    return 0


def _stage17_context_map(context, name):
    value = getattr(context, name, None)
    return value if isinstance(value, dict) else {}


def _stage17_used_levels(context):
    value = getattr(context, "used_skill_levels", None)
    return value if isinstance(value, dict) else {}


def _stage17_enabled_levels(context):
    value = getattr(context, "enabled_skill_levels", None)
    return value if isinstance(value, dict) else {}


def _stage17_build_variables(request, data, context, effect_dict, damage):
    variables = {}
    context_vars = getattr(context, "variables", {})
    if isinstance(context_vars, dict):
        variables.update({key: value for key, value in context_vars.items() if isinstance(value, (int, float))})
    get_values = getattr(request, "get_values", {}) or {}
    base_lv = _stage17_int(get_values.get(11, 0))
    job_lv = _stage17_int(get_values.get(12, 0))
    job_id = get_values.get(19, 0)
    job_info = data.job_dict.get(job_id, data.job_dict.get(str(job_id), {})) if isinstance(data.job_dict, dict) else {}
    job_bonus = (job_info or {}).get("TJobMaxPoint", []) or []
    variables.update({"BaseLv": base_lv, "JobLv": job_lv, "BLV": base_lv, "JLV": job_lv})
    base_equipment_stats = {
        stat: variables.get(f"base_equip_{stat}", 0)
        for stat in BASE_STAT_NAMES
    }
    stat_breakdown = calculate_stat_breakdown(
        get_values=get_values,
        job_bonus=job_bonus,
        effect_dict=effect_dict,
        base_equipment_stats=base_equipment_stats,
        integer_effects=True,
    )
    for stat in STAGE17_STAT_NAMES:
        values = stat_breakdown[stat]
        variables[f"base_{stat}"] = values["base"]
        variables[f"job_{stat}"] = values["job"]
        variables[f"equip_{stat}"] = values["equip"]
        variables[f"total_{stat}"] = values["total"]
        variables[f"base_equip_{stat}"] = values["base_equip"]
    variables["MHP"] = _stage17_int(damage.get("mhp", get_values.get(200, 0)))
    variables["MSP"] = _stage17_int(damage.get("msp", get_values.get(202, 0)))
    variables["MHP_NOW"] = _stage17_int(damage.get("mhp_now", variables["MHP"]))
    variables["MSP_NOW"] = _stage17_int(damage.get("msp_now", variables["MSP"]))
    special = damage.get("special", {}) if isinstance(damage, dict) else {}
    if not isinstance(special, dict):
        special = {}
    variables.setdefault("total_SRL", _stage17_number(special.get("total_srl", 0), 0))
    return variables


def _stage17_prepare_formula(raw_formula, *, variables, skill_level, target_size, weapon_class, enabled_levels, used_levels):
    text = _stage17_replace_calls(
        raw_formula,
        target_size=target_size,
        weapon_class=weapon_class,
        enabled_levels=enabled_levels,
        used_levels=used_levels,
    )
    eval_vars = dict(variables)
    eval_vars["Sklv"] = _stage17_int(skill_level)
    eval_vars["SLV"] = _stage17_int(skill_level)
    return text, eval_vars



def _stage17_special_values(special, *, attack_element, target_class, ranged):
    state = special if isinstance(special, dict) else {}
    attack_element = _stage17_int(attack_element)
    target_class = _stage17_int(target_class)

    wanzih = 1.0 if bool(state.get("wanzih")) and 2 <= attack_element <= 3 else 0.0
    poison_weak = 0.5 if bool(state.get("poison_weak")) and attack_element == 5 else 0.0
    magic_poison = 0.5 if bool(state.get("magic_poison")) else 0.0
    attribute_seal = (
        1.5
        if bool(state.get("attribute_seal")) and 1 <= attack_element <= 4
        else 1.0
    )

    sneak_checked = bool(state.get("sneak_attack"))
    sneak_raw = (
        1.30 if sneak_checked and target_class == 0
        else 1.15 if sneak_checked
        else 0.0
    )
    sneak_magic_percent = (
        30.0 if sneak_checked and target_class == 0
        else 15.0 if sneak_checked
        else 0.0
    )

    dark_checked = bool(state.get("dark_crow"))
    dark_raw = (
        2.50 if dark_checked and target_class == 0
        else 1.75 if dark_checked
        else 0.0
    )
    rush_raw = 1.50 if bool(state.get("rush_attack")) else 0.0
    spore_raw = 1.05 if bool(state.get("spore_attack")) else 0.0
    oleum_raw = 1.15 if bool(state.get("oleum_attack")) else 0.0

    melee_raw = max(1.0, sneak_raw + dark_raw + rush_raw)
    range_raw = max(1.0, sneak_raw + spore_raw + rush_raw + oleum_raw)

    return {
        "element_tolerance": 1.0 + wanzih + poison_weak + magic_poison,
        "db_element_tolerance": 1.0 + magic_poison,
        "magic_special_percent": sneak_magic_percent,
        "physical_special_raw": range_raw if ranged else melee_raw,
        "attribute_seal": attribute_seal,
        "lex_aeterna": 100.0 if bool(state.get("lex_aeterna")) else 0.0,
    }


def _stage17_calculate_one(*, formula, round_index, label, skill_hits, attack_element, row, base, monster, effect_dict, variables, context, request, special, bonus_add=0, bonus_step=0):
    weapon_type_map = _stage17_context_map(context, "weapon_type_map")
    weapon_level_map = _stage17_context_map(context, "weapon_level_map")
    weapon_atk_map = _stage17_context_map(context, "weapon_atk_map")
    weapon_matk_map = _stage17_context_map(context, "weapon_matk_map")
    enabled_levels = _stage17_enabled_levels(context)
    used_levels = _stage17_used_levels(context)
    weapon_class = _stage17_int(weapon_type_map.get(4, weapon_type_map.get("4", 0)))
    target_size = _stage17_int(monster.get("size", 1))
    target_element = _stage17_int(monster.get("element", 0))
    target_race = _stage17_int(monster.get("race", 0))
    target_class = _stage17_int(monster.get("class", 0))
    target_element_lv = max(1, min(4, _stage17_int(monster.get("element_lv", 1), 1)))

    special_values = _stage17_special_values(
        special,
        attack_element=attack_element,
        target_class=target_class,
        ranged=bool(base.get("ranged")),
    )

    raw_formula = _stage17_text(formula) or "0"
    add_expr = _stage17_text(bonus_add)
    step_val = _stage17_number(bonus_step, 0.0)
    if add_expr.startswith("*"):
        current_mult = _stage17_number(add_expr[1:] or 1, 1.0) + step_val * round_index
        raw_formula = f"({raw_formula}) * {current_mult}"
    elif add_expr or step_val:
        current_add = _stage17_number(add_expr, 0.0) + step_val * round_index
        if current_add:
            raw_formula = f"({raw_formula}) {'+' if current_add > 0 else ''} {current_add}"

    prepared, eval_vars = _stage17_prepare_formula(
        raw_formula,
        variables=variables,
        skill_level=base["skill_level"],
        target_size=target_size,
        weapon_class=weapon_class,
        enabled_levels=enabled_levels,
        used_levels=used_levels,
    )
    expanded_formula, formula_result = stage17_eval_formula_with_vars(
        prepared,
        eval_vars,
    )
    if formula_result is None:
        raise ValueError(f"技能公式無法計算：{expanded_formula}")
    skill_result = int(formula_result)
    if _stage17_int(used_levels.get(380, 0)) == 1:
        skill_result += 20

    special_raw = _stage17_text(row.get("skill_SpecialATK")) or "0"
    special_prepared, special_vars = _stage17_prepare_formula(
        special_raw,
        variables=variables,
        skill_level=base["skill_level"],
        target_size=target_size,
        weapon_class=weapon_class,
        enabled_levels=enabled_levels,
        used_levels=used_levels,
    )
    skill_special_atk = _stage17_int(_stage17_safe_eval(special_prepared, special_vars), 0)

    attack_type = base["attack_type"]
    use_skills = _stage17_sum_skill_effect(effect_dict, base["skill_name"], "傷害(裝備段)")
    passive_skill = _stage17_sum_skill_effect(effect_dict, base["skill_name"], "傷害(技能段)")

    if attack_type == "magic":
        output, steps = stage17_apply_stepwise(
            (base["magic_max"], base["magic_min"]),
            (base["matk_percent"], 1, "MATK%"),
            (_stage17_effect_multiplier(effect_dict, "MD_size", target_size), 1, "體型%"),
            (_stage17_effect_multiplier(effect_dict, "MD_element", target_element) + _stage17_effect_multiplier(effect_dict, "MD_element", 10), 1, "屬性敵人%"),
            (special_values["element_tolerance"], "raw", "屬性耐受性%"),
            (_stage17_effect_multiplier(effect_dict, "MD_Damage", attack_element) + _stage17_effect_multiplier(effect_dict, "MD_Damage", 10), 1, "屬性魔法%"),
            (_stage17_effect_multiplier(effect_dict, "MD_Race", target_race) + _stage17_effect_multiplier(effect_dict, "MD_Race", 9999), 1, "種族%"),
            (_stage17_effect_multiplier(effect_dict, "MD_class", target_class), 1, "階級%"),
            (base["target_monster_magic"], 1, "特定魔物增傷%"),
            (base["total_smatk"], 1, "SMATK"),
            (skill_result, 0, "技能倍率%"),
            (stage17_get_damage_multiplier(attack_element, target_element, target_element_lv), 0, "屬性倍率%"),
            (base["mres_multiplier"], "raw", "MRES減傷%"),
            (base["mdef_multiplier"], "raw", "MDEF減傷%"),
            (_stage17_number(monster.get("mdefc", 0)), None, "MDEF減算"),
            (use_skills, 1, "技能增傷%(裝備段)"),
            (passive_skill, 1, "技能增傷%(技能段)"),
            (special_values["magic_special_percent"], 1, "特殊魔法增傷"),
            (special_values["attribute_seal"], "raw", "紋章"),
            (special_values["lex_aeterna"], 1, "天怒"),
        )
        final_max, final_min = output
    elif attack_type == "physical":
        ranged = base["ranged"]
        near_far = base["range_damage"] if ranged else base["melee_damage"]
        delayed = base["range_damage"] if (ranged and base["delayed_ranged"]) else 0
        if ranged and weapon_class == 11:
            near_far += base["bow_atk"]
            if delayed:
                delayed += base["bow_atk"]
        if ranged and base["delayed_ranged"]:
            near_far = 0

        critical = base["critical_hit"]
        if critical < 0:
            critical_rate = critical_damage = hit_damage = 0
        elif critical == 0:
            critical_rate = critical_damage = 0
            hit_damage = base["hit_damage"]
        else:
            critical_damage = base["crit_damage"] * critical
            critical_rate = base["total_crate"] + 40
            hit_damage = 0

        atk_percent_sign_min = int(base["weapon_back_min"] * (base["atk_percent"] / 100))
        atk_percent_sign = int(base["weapon_back_max"] * (base["atk_percent"] / 100))
        first, steps1 = stage17_apply_stepwise(
            (base["weapon_back_max"], base["weapon_back_min"]),
            (_stage17_effect_multiplier(effect_dict, "D_Race", target_race) + _stage17_effect_multiplier(effect_dict, "D_Race", 9999), 1, "種族%"),
            (_stage17_effect_multiplier(effect_dict, "D_size", target_size), 1, "體型%"),
            (base["edp_attack"], 1, "致命塗毒%"),
            (_stage17_effect_multiplier(effect_dict, "D_element", target_element) + _stage17_effect_multiplier(effect_dict, "D_element", 10), 1, "屬性敵人%"),
            (_stage17_effect_multiplier(effect_dict, "D_class", target_class), 1, "階級%"),
            (base["target_monster_physical"], 1, "特定魔物增傷%"),
            (atk_percent_sign, atk_percent_sign_min, "+", "ATK%"),
            (special_values["element_tolerance"], "raw", "屬性耐受性%"),
        )
        first_max, first_min = first
        element_multiplier = stage17_get_damage_multiplier(attack_element, target_element, target_element_lv)
        first_min = _stage17_math.ceil(first_min * element_multiplier / 100)
        first_max = _stage17_math.ceil(first_max * element_multiplier / 100)
        mastery = 0 if weapon_class in STAGE17_DEX_WEAPON_CLASSES else base["weapon_mastery"]
        katar = base["katar_mastery"] if weapon_class not in STAGE17_DEX_WEAPON_CLASSES else 0
        output, steps2 = stage17_apply_stepwise(
            (first_max, first_min),
            (base["front_atk"], "+", "前ATK"),
            (base["kamui_atk"], "+", "神威ATK"),
            (base["total_patk"], 1, "PATK"),
            (base["cannonball_atk"] if base["skill_cannon"] else 0, "+", "砲彈ATK"),
            (mastery, "+", "武器修煉ATK"),
            (base["tk_power"], 1, "加油"),
            (base["sg_hate"], 1, "奇蹟/憎惡"),
            (hit_damage, 1, "命中增傷%"),
            (critical_damage, 1, "爆擊傷害%"),
            (near_far, 1, "近/遠傷%"),
            (skill_result, 0, "技能倍率%"),
            (katar, 1, "高階拳刃修煉"),
            (base["res_multiplier"], "raw", "RES減傷%"),
            (base["def_multiplier"], "raw", "DEF減傷%"),
            (_stage17_number(monster.get("defc", 0)), None, "DEF減算"),
            (base["aura_blade"], "+", "靈氣劍"),
            (delayed, 1, "後計算遠傷%"),
            (use_skills, 1, "技能增傷%(裝備段)"),
            (passive_skill, 1, "技能增傷%(技能段)"),
            (critical_rate, 1, "C.RATE"),
            (special_values["physical_special_raw"], "raw", "特殊物理增傷"),
            (special_values["attribute_seal"], "raw", "紋章"),
            (special_values["lex_aeterna"], 1, "天怒"),
        )
        final_max, final_min = output
        steps = steps1 + [{"name": "屬性倍率%", "value": element_multiplier, "mode": 0}] + steps2
    elif attack_type == "d_b":
        near_far = base["range_damage"] if base["ranged"] else base["melee_damage"]
        if base["ranged"] and weapon_class == 11:
            near_far += base["bow_atk"]
        output, steps = stage17_apply_stepwise(
            1,
            (skill_result, "raw", "技能倍率%"),
            (special_values["db_element_tolerance"], "raw", "屬性耐受性%"),
            (base["res_multiplier"], "raw", "RES減傷%"),
            (base["def_multiplier"], "raw", "DEF減傷%"),
            (_stage17_number(monster.get("defc", 0)), None, "DEF減算"),
            (use_skills, 1, "技能增傷%(裝備段)"),
            (passive_skill, 1, "技能增傷%(技能段)"),
            (near_far, 1, "近/遠傷%"),
            (stage17_get_damage_multiplier(attack_element, target_element, target_element_lv), 0, "屬性倍率%"),
        )
        final_max = output
        final_min = 0
    elif attack_type == "shield":
        final_min = final_max = 0
        steps = []
    else:
        raise ValueError(f"未知的攻擊類型: {attack_type}")

    final_min = _stage17_int(final_min + skill_special_atk)
    final_max = _stage17_int(final_max + skill_special_atk)
    damage_multiplier = _stage17_number(monster.get("damage_multiplier_percent", 100), 100) / 100
    betel = _stage17_number(monster.get("betelgeuse_reduction_percent", 0), 0)
    final_min = int(final_min * damage_multiplier)
    final_max = int(final_max * damage_multiplier)
    final_min = int(final_min * (1 - betel / 100))
    final_max = int(final_max * (1 - betel / 100))

    if skill_hits < 0:
        times = max(1, abs(_stage17_int(skill_hits)))
        by_hit_min = int(final_min / times)
        by_hit_max = int(final_max / times)
        total_min = by_hit_min * times
        total_max = by_hit_max * times
    else:
        times = max(1, _stage17_int(skill_hits, 1))
        by_hit_min = final_min
        by_hit_max = final_max
        total_min = final_min
        total_max = final_max

    return {
        "round": round_index + 1,
        "label": label,
        "formula": prepared,
        "formula_expanded": expanded_formula,
        "skill_result": skill_result,
        "damage_by_hit_min": by_hit_min,
        "damage_by_hit": by_hit_max,
        "total_damage_min": total_min,
        "total_damage": total_max,
        "times": times,
        "user_attack_element": attack_element,
        "steps": steps,
    }


def calculate_stage17_damage(*, request, data, context, effect_result, data_dir, damage):
    """拆分前 Desktop 傷害計算的 Qt-free 核心。

    計算順序仍依原本區塊：技能資料 → 武器/精煉 → PATK/SMATK → 武器基礎 ATK →
    體型/屬性與特殊技能 → DEF/RES/MDEF/MRES → 前後 ATK/MATK → 技能公式 →
    逐段增傷/減傷 → 多段傷害與顯示明細。
    """
    # === [1] 取得技能 row / 技能基本資料 ===
    skill_id = _stage17_int(damage.get("skill_id", 0))
    if skill_id <= 0:
        raise ValueError("請選擇傷害技能")
    row = stage17_get_skill_row(data_dir, skill_id)
    if row is None:
        raise ValueError(f"skillneme.csv 找不到技能 ID：{skill_id}")

    skill_name = _stage17_text(row.get("Name"))
    skill_level = _stage17_int(damage.get("skill_level", row.get("Slv", 1)), 1)
    attack_type = (_stage17_text(row.get("attack_type")) or "physical").lower()
    monster = dict(damage.get("monster", {}) or {})
    effect_dict = getattr(effect_result, "legacy_effect_dict", {}) or {}
    variables = _stage17_build_variables(request, data, context, effect_dict, damage)
    variables["Sklv"] = skill_level
    variables["SLV"] = skill_level

    # ========================== 武器 / 精煉資料 =========================
    weapon_type_map = _stage17_context_map(context, "weapon_type_map")
    weapon_level_map = _stage17_context_map(context, "weapon_level_map")
    weapon_atk_map = _stage17_context_map(context, "weapon_atk_map")
    weapon_matk_map = _stage17_context_map(context, "weapon_matk_map")
    weapon_class = _stage17_int(weapon_type_map.get(4, weapon_type_map.get("4", 0)))
    weapon_r_level = _stage17_int(weapon_level_map.get(4, weapon_level_map.get("4", 0)))
    weapon_l_level = _stage17_int(weapon_level_map.get(3, weapon_level_map.get("3", 0)))
    weapon_r_atk = _stage17_int(weapon_atk_map.get(4, weapon_atk_map.get("4", 0)))
    weapon_r_matk = _stage17_int(weapon_matk_map.get(4, weapon_matk_map.get("4", 0)))
    weapon_l_matk = _stage17_int(weapon_matk_map.get(3, weapon_matk_map.get("3", 0)))
    refine_inputs = getattr(request, "refine_inputs", {}) or {}
    refine_r = _stage17_int(refine_inputs.get(4, refine_inputs.get("4", 0)))
    refine_l = _stage17_int(refine_inputs.get(3, refine_inputs.get("3", 0)))
    grade_r = _stage17_slot_grade(request, 4)
    grade_l = _stage17_slot_grade(request, 3)

    # 武器 ATK / MATK 精煉計算；副手 ATK 本體不進主傷害，但 P.ATK / S.MATK 仍會加總。
    atk_refine, patk_refine, refine_over_atk, refine_over_atk_min = stage17_calc_weapon_refine_atk(weapon_r_level, refine_r, grade_r)
    _atk_refine_l, patk_refine_l, _roal, _roalm = stage17_calc_weapon_refine_atk(weapon_l_level, refine_l, grade_l)
    matk_refine, smatk_refine, refine_over_matk, refine_over_matk_min = stage17_calc_weapon_refine_matk(weapon_r_level, refine_r, grade_r)
    matk_refine_l, smatk_refine_l, refine_over_matk_l, refine_over_matk_l_min = stage17_calc_weapon_refine_matk(weapon_l_level, refine_l, grade_l)

    total_str = variables["total_STR"]
    total_dex = variables["total_DEX"]
    total_luk = variables["total_LUK"]
    total_pow = variables["total_POW"]
    total_int = variables["total_INT"]
    total_spl = variables["total_SPL"]
    total_con = variables["total_CON"]
    total_crt = variables["total_CRT"]
    base_lv = variables["BaseLv"]

    # P.ATK / S.MATK = 裝備 + 特性素質 + 主副手五階精煉。
    patk = _stage17_sum_effect(effect_dict, "P.ATK", "")
    smatk = _stage17_sum_effect(effect_dict, "S.MATK", "")
    total_patk = patk + int(total_pow / 3) + int(total_con / 5) + patk_refine + patk_refine_l
    total_smatk = smatk + int(total_spl / 3) + int(total_con / 5) + smatk_refine + smatk_refine_l
    variables["total_PATK"] = total_patk
    variables["total_SMATK"] = total_smatk

    atk_armor = _stage17_sum_effect(effect_dict, "ATK", "")
    matk_armor = _stage17_sum_effect(effect_dict, "MATK", "")
    atk_percent = _stage17_sum_effect(effect_dict, "ATK%", "%")
    matk_percent = _stage17_sum_effect(effect_dict, "MATK%", "%")
    ammo_atk = _stage17_sum_effect(effect_dict, "箭矢/彈藥ATK", "")
    cannonball = _stage17_sum_effect(effect_dict, "砲彈ATK", "")
    weapon_mastery = _stage17_sum_effect(effect_dict, "修煉ATK", "")
    kamui_atk = _stage17_sum_effect(effect_dict, "神威ATK", "")
    crit_damage = _stage17_sum_effect(effect_dict, "爆擊傷害", "%")
    hit_damage = _stage17_sum_effect(effect_dict, "物理命中傷害", "%")
    bow_atk = _stage17_sum_effect(effect_dict, "弓攻擊力", "%")
    crate = _stage17_sum_effect(effect_dict, "C.RATE", "")
    ignore_size = _stage17_sum_effect(effect_dict, "武器體型修正", "%")
    target_monster_physical = _stage17_sum_effect(effect_dict, "特定魔物物理增傷", "%")
    target_monster_magic = _stage17_sum_effect(effect_dict, "特定魔物魔法增傷", "%")
    melee_damage = _stage17_sum_effect(effect_dict, "近距離物理傷害", "%")
    range_damage = _stage17_sum_effect(effect_dict, "遠距離物理傷害", "%")

    # ========================== 武器基礎 ATK =========================
    # DEX 系武器與 STR 系武器使用不同主素質；Maximize Power 影響最小武器 ATK。
    used = _stage17_used_levels(context)
    enabled = _stage17_enabled_levels(context)
    maximize = _stage17_int(used.get(114, 0)) == 1
    primary = total_dex if weapon_class in STAGE17_DEX_WEAPON_CLASSES else total_str
    min_sign = 1 if maximize else -1
    weapon_base_min = weapon_r_atk * (1 + primary / 200 + min_sign * weapon_r_level * 0.05)
    weapon_base_max = weapon_r_atk * (1 + primary / 200 + weapon_r_level * 0.05)
    if weapon_class in STAGE17_DEX_WEAPON_CLASSES:
        refine_weapon_min = int(weapon_base_min + atk_refine - refine_over_atk)
        refine_weapon_max = int(weapon_base_max + atk_refine - refine_over_atk)
    else:
        refine_weapon_min = int(weapon_base_min + atk_refine + refine_over_atk_min - refine_over_atk)
        refine_weapon_max = int(weapon_base_max + atk_refine)

    # 武器體型修正；若裝備效果已達 100% 忽略體型，倍率固定為 1。
    target_size = _stage17_int(monster.get("size", 1))
    weapon_penalty = 1 if ignore_size >= 100 else stage17_get_size_penalty(weapon_class, target_size)
    refine_ammo_min = int(refine_weapon_min * weapon_penalty) + ammo_atk
    refine_ammo_max = int(refine_weapon_max * weapon_penalty) + ammo_atk
    target_element = _stage17_int(monster.get("element", 0))
    target_element_lv = max(1, min(4, _stage17_int(monster.get("element_lv", 1), 1)))
    edp = 1 + 0.25 * (stage17_get_damage_multiplier(5, target_element, target_element_lv) / 100) if _stage17_int(used.get(378, 0)) == 1 else 1
    magnum = 1 + 0.2 * (stage17_get_damage_multiplier(3, target_element, target_element_lv) / 100) if _stage17_int(used.get(7, 0)) == 1 else 1
    if _stage17_int(used.get(378, 0)) == 1:
        special_atk_min = int(refine_ammo_min * edp)
        special_atk_max = int(refine_ammo_max * edp)
    elif _stage17_int(used.get(7, 0)) == 1:
        special_atk_min = int(refine_ammo_min * magnum)
        special_atk_max = int(refine_ammo_max * magnum)
    else:
        special_atk_min, special_atk_max = int(refine_ammo_min), int(refine_ammo_max)

    # ========================== DEF / RES / MDEF / MRES =========================
    # 技能 row 內的 half_bypass_def / half_bypass_res 會在 共用防禦 helper 統一處理。
    target_race = _stage17_int(monster.get("race", 0))
    target_class = _stage17_int(monster.get("class", 0))
    half_bypass_def = _stage17_int(row.get("half_bypass_def", 0))
    half_bypass_res = _stage17_int(row.get("half_bypass_res", 0))
    target_def = _stage17_number(monster.get("def", 0), 0)
    target_mdef = _stage17_number(monster.get("mdef", 0), 0)
    target_res = _stage17_number(monster.get("res", 0), 0)
    target_mres = _stage17_number(monster.get("mres", 0), 0)
    target_defc = _stage17_number(monster.get("defc", 0), 0)
    defense_factors = stage17_calculate_target_defense_factors(
        effect_dict=effect_dict,
        target_race=target_race,
        target_class=target_class,
        target_def=target_def,
        target_defc=target_defc,
        target_res=target_res,
        target_mdef=target_mdef,
        target_mres=target_mres,
        half_bypass_def=half_bypass_def,
        half_bypass_res=half_bypass_res,
    )
    def_reduction = defense_factors["def_reduction"]
    mdef_reduction = defense_factors["mdef_reduction"]
    res_reduction = defense_factors["res_reduction"]
    mres_reduction = defense_factors["mres_reduction"]
    def_multiplier = defense_factors["def_multiplier"]
    mdef_multiplier = defense_factors["mdef_multiplier"]
    res_multiplier = defense_factors["res_multiplier"]
    mres_multiplier = defense_factors["mres_multiplier"]
    target_defc = defense_factors["target_defc"]
    # 浸透勁效果：依剩餘 DEF 轉成額外 ATK，並把前 DEF 減算清零。
    investigate = 0
    if _stage17_int(used.get(266, 0)) == 1:
        temp = int(100 - def_reduction)
        investigate = max(0, int(target_def / 2 + (target_def / 2) * (temp / 100)))
        target_defc = 0
    monster["defc"] = target_defc

    # 後 ATK（裝備 / 武器段）與前 ATK（素質段）。
    weapon_back_min = special_atk_min + atk_armor + investigate
    weapon_back_max = special_atk_max + atk_armor + investigate
    # 近傷前 ATK（STR 系）
    natk = int(base_lv / 4 + total_str + total_dex / 5 + total_luk / 3 + total_pow * 5)
    # 遠傷前 ATK（DEX 系：弓 / 槍 / 樂器 / 鞭等）
    fatk = int(base_lv / 4 + total_str / 5 + total_dex + total_luk / 3 + total_pow * 5)
    sevenwind = _stage17_int(used.get(425, 0)) == 1
    row_element = _stage17_int(row.get("element", 0), 0)
    attack_element = damage.get("attack_element", None)
    attack_element = row_element if attack_element is None else _stage17_int(attack_element, row_element)
    front_base = fatk if weapon_class in STAGE17_DEX_WEAPON_CLASSES else natk
    front_element = attack_element if sevenwind else 0
    front_atk = int(front_base * 2 * stage17_get_damage_multiplier(front_element, target_element, target_element_lv) / 100)

    # ========================== MATK 基礎區 =========================
    matkf = int(base_lv / 4) + int(total_int * 1.5) + int(total_dex / 5) + int(total_luk / 3) + int(total_spl * 5)
    magic_max_raw = matkf + ((matk_refine + matk_refine_l + weapon_r_matk + weapon_l_matk) * (1 + weapon_r_level * 0.1))
    if _stage17_int(used.get(2206, 0)) == 1:
        magic_min_raw = matkf + ((matk_refine + matk_refine_l + weapon_r_matk + weapon_l_matk + refine_over_matk_min + refine_over_matk_l_min - refine_over_matk - refine_over_matk_l) * (1 + weapon_r_level * 0.1))
    else:
        magic_min_raw = matkf + ((matk_refine + matk_refine_l + weapon_r_matk + weapon_l_matk + refine_over_matk_min + refine_over_matk_l_min - refine_over_matk - refine_over_matk_l) * (1 - weapon_r_level * 0.1))
    magic_power_lv = 10 if _stage17_int(used.get(366, 0)) == 1 else 0
    magic_min = int(magic_min_raw * (1 + magic_power_lv * 0.05) + matk_armor)
    magic_max = int(magic_max_raw * (1 + magic_power_lv * 0.05) + matk_armor)

    critical_raw = _stage17_text(row.get("Critical_hit"))
    if critical_raw:
        critical_expr, critical_vars = _stage17_prepare_formula(
            critical_raw, variables=variables, skill_level=skill_level,
            target_size=target_size, weapon_class=weapon_class,
            enabled_levels=enabled, used_levels=used,
        )
        critical_hit = float(_stage17_safe_eval(critical_expr, critical_vars))
    else:
        critical_hit = 0.0

    special_formula = _stage17_text(row.get("Special_Calculation"))
    trigger_special = False
    trigger_skillbuff = False
    monster_races = {_stage17_text(value) for value in _stage17_text(row.get("monster_race")).split(",") if _stage17_text(value)}
    if special_formula and str(target_race) in monster_races:
        trigger_special = True
    buff_ids = [_stage17_int(value) for value in _stage17_text(row.get("skill_buff")).split(",") if _stage17_text(value).isdigit()]
    if any(_stage17_int(used.get(skill, 0)) for skill in buff_ids):
        trigger_skillbuff = True
        if special_formula:
            trigger_special = True
    if trigger_skillbuff and _stage17_text(row.get("Special_Critical_hit")):
        critical_hit = _stage17_number(row.get("Special_Critical_hit"), critical_hit)

    if _stage17_int(used.get(444, 0)) == 1:
        critical_hit = 0.5

    ranged = _stage17_int(row.get("Rangedamage", 0)) == 1
    allowed_range_classes = {
        _stage17_int(value)
        for value in _stage17_text(row.get("special_wprange", 0)).split(",")
        if _stage17_text(value) and _stage17_int(value) != 0
    }
    if weapon_class and weapon_class in allowed_range_classes:
        ranged = True

    base = {
        "skill_name": skill_name,
        "skill_level": skill_level,
        "attack_type": attack_type,
        "weapon_class": weapon_class,
        "front_atk": front_atk,
        "weapon_back_min": weapon_back_min,
        "weapon_back_max": weapon_back_max,
        "magic_min": magic_min,
        "magic_max": magic_max,
        "atk_percent": atk_percent,
        "matk_percent": matk_percent,
        "total_patk": total_patk,
        "total_smatk": total_smatk,
        "cannonball_atk": cannonball,
        "weapon_mastery": weapon_mastery,
        "kamui_atk": kamui_atk,
        "crit_damage": crit_damage,
        "hit_damage": hit_damage,
        "bow_atk": bow_atk,
        "total_crate": crate + int(total_crt / 3),
        "target_monster_physical": target_monster_physical,
        "target_monster_magic": target_monster_magic,
        "melee_damage": melee_damage,
        "range_damage": range_damage,
        "ranged": ranged,
        "delayed_ranged": _stage17_int(row.get("Delayed_Rangedamage", 0)) == 1,
        "skill_cannon": _stage17_int(row.get("skill_cannon", 0)) == 1,
        "critical_hit": critical_hit,
        "def_multiplier": def_multiplier,
        "mdef_multiplier": mdef_multiplier,
        "res_multiplier": res_multiplier,
        "mres_multiplier": mres_multiplier,
        "edp_attack": 300 if _stage17_int(used.get(378, 0)) == 1 else 0,
        "katar_mastery": (_stage17_int(enabled.get(376, 0)) * 2 + 10) if weapon_class == 16 else 0,
        "tk_power": _stage17_int(enabled.get(424, 0)) * 20,
        "aura_blade": base_lv * (3 + _stage17_int(enabled.get(355, 0))) if _stage17_int(used.get(355, 0)) == 1 else 0,
        "sg_hate": 0,
    }
    if _stage17_int(used.get(434, 0)) == 1:
        if target_size == 2:
            base["sg_hate"] = min(int((total_str + total_dex + total_luk + base_lv) / 3), 75)
        else:
            base["sg_hate"] = min(int((total_dex + total_luk + base_lv) / 3), 75)

    warnings = []
    formula_override = _stage17_text(damage.get("formula_override"))
    special = damage.get("special", {})
    if not isinstance(special, dict):
        special = {}

    formula_tokens = " ".join([
        _stage17_text(row.get("Calculation")),
        _stage17_text(row.get("Special_Calculation")),
        _stage17_text(row.get("combo")),
        _stage17_text(row.get("combo_Special_Calculation")),
    ])
    if "total_SRL" in formula_tokens and not _stage17_number(special.get("total_srl", 0), 0):
        warnings.append("此技能公式使用 total_SRL；目前值為 0，可在特殊狀態欄手動設定。")
    if attack_type == "shield":
        warnings.append("shield 類型目前只回傳技能公式結果；Desktop 護盾專用顯示將在後續補齊。")
    formula_source = "special" if trigger_special and special_formula else "csv"
    formula = special_formula if trigger_special and special_formula else _stage17_text(row.get("Calculation"))
    if formula_override:
        formula = formula_override
        formula_source = "override"

    skill_hits = _stage17_parse_hits(
        row.get("hits", "1"), skill_level,
        target_size=target_size, weapon_class=weapon_class,
        enabled_levels=enabled, used_levels=used,
    )
    if skill_hits == 0:
        skill_hits = 1
    repeat = 1 if skill_hits < 0 else max(1, skill_hits)
    results = []
    for index in range(repeat):
        results.append(_stage17_calculate_one(
            formula=formula, round_index=index, label="main", skill_hits=skill_hits,
            attack_element=attack_element, row=row, base=base, monster=monster,
            effect_dict=effect_dict, variables=variables, context=context,
            request=request, special=special,
            bonus_add=row.get("bonus_add", ""), bonus_step=row.get("bonus_step", 0),
        ))

    combo_formula = _stage17_text(row.get("combo"))
    combo_hits_raw = _stage17_text(row.get("combo_hits"))
    if combo_formula and combo_hits_raw:
        combo_special = _stage17_text(row.get("combo_Special_Calculation"))
        if trigger_special and combo_special:
            combo_formula = combo_special
        combo_hits = _stage17_parse_hits(
            combo_hits_raw, skill_level,
            target_size=target_size, weapon_class=weapon_class,
            enabled_levels=enabled, used_levels=used,
        )
        combo_element = attack_element
        if _stage17_text(row.get("combo_element")):
            combo_element = _stage17_int(row.get("combo_element"), attack_element)
        combo_repeat = max(1, abs(combo_hits))
        for index in range(combo_repeat):
            results.append(_stage17_calculate_one(
                formula=combo_formula, round_index=index,
                label="combo (均分)" if combo_hits < 0 else "combo",
                skill_hits=combo_hits, attack_element=combo_element, row=row,
                base=base, monster=monster, effect_dict=effect_dict,
                variables=variables, context=context, request=request,
                special=special,
            ))

    # 比照 Desktop 對負 hit combo 的顯示 / 彙總語意：
    # compute_and_record_damage() 會建立重複且相同的分段紀錄，但
    # Desktop 結果 UI 只會把第一筆 split-combo 紀錄計算一次。
    combo_split_results = [
        item for item in results[1:]
        if item.get("label") == "combo (均分)"
        and _stage17_int(item.get("times", 1)) > 1
        and _stage17_int(item.get("damage_by_hit", 0)) * _stage17_int(item.get("times", 1))
            == _stage17_int(item.get("total_damage", 0))
    ]
    display_results = results
    if len(results) > 1 and combo_split_results:
        display_results = [results[0], combo_split_results[0]]

    total_min = sum(_stage17_int(item["total_damage_min"]) for item in display_results)
    total_max = sum(_stage17_int(item["total_damage"]) for item in display_results)
    # === STAGE 21.17 DESKTOP 傷害明細 ===
    breakdown_skill_result = (
        _stage17_number(
            display_results[0].get("skill_result", 0),
            0,
        )
        if display_results
        else 0
    )
    breakdown_element_multiplier = stage17_get_damage_multiplier(
        attack_element,
        target_element,
        target_element_lv,
    )
    breakdown_use_skills = _stage17_sum_skill_effect(
        effect_dict,
        skill_name,
        "傷害(裝備段)",
    )
    breakdown_passive_skill = _stage17_sum_skill_effect(
        effect_dict,
        skill_name,
        "傷害(技能段)",
    )
    breakdown_special = _stage17_special_values(
        special,
        attack_element=attack_element,
        target_class=target_class,
        ranged=bool(ranged),
    )

    if attack_type == "magic":
        damage_breakdown = {
            "mode": "magic",
            "label": "魔法",
            "rows": [
                {"key": "front_matk", "label": "前MATK", "value": matkf, "unit": ""},
                {
                    "key": "back_matk",
                    "label": "後MATK",
                    "value": (
                        matk_armor
                        + weapon_r_matk
                        + weapon_l_matk
                        + matk_refine
                        + matk_refine_l
                        - refine_over_matk
                        - refine_over_matk_l
                    ),
                    "unit": "",
                },
                {"key": "weapon_matk", "label": "武器MATK", "value": weapon_r_matk, "unit": ""},
                {"key": "armor_magic", "label": "裝備MATK+魔力", "value": magic_max, "unit": ""},
                {"key": "matk_percent", "label": "MATK%", "value": round(matk_percent), "unit": "%"},
                {
                    "key": "magic_size",
                    "label": "魔法體型",
                    "value": round(_stage17_effect_multiplier(effect_dict, "MD_size", target_size)),
                    "unit": "%",
                },
                {
                    "key": "magic_target_element",
                    "label": "魔法屬性敵人",
                    "value": round(
                        _stage17_effect_multiplier(effect_dict, "MD_element", target_element)
                        + _stage17_effect_multiplier(effect_dict, "MD_element", 10)
                    ),
                    "unit": "%",
                },
                {
                    "key": "element_tolerance",
                    "label": "屬性耐受性",
                    "value": round((breakdown_special["element_tolerance"] - 1.0) * 100),
                    "unit": "%",
                },
                {
                    "key": "element_magic",
                    "label": "屬性魔法",
                    "value": round(
                        _stage17_effect_multiplier(effect_dict, "MD_Damage", attack_element)
                        + _stage17_effect_multiplier(effect_dict, "MD_Damage", 10)
                    ),
                    "unit": "%",
                },
                {
                    "key": "magic_race",
                    "label": "魔法種族",
                    "value": round(
                        _stage17_effect_multiplier(effect_dict, "MD_Race", target_race)
                        + _stage17_effect_multiplier(effect_dict, "MD_Race", 9999)
                    ),
                    "unit": "%",
                },
                {
                    "key": "magic_class",
                    "label": "魔法階級",
                    "value": round(_stage17_effect_multiplier(effect_dict, "MD_class", target_class)),
                    "unit": "%",
                },
                {"key": "monster_damage", "label": "魔物增傷", "value": round(target_monster_magic), "unit": "%"},
                {"key": "smatk", "label": "S.MATK", "value": round(total_smatk), "unit": ""},
                {"key": "skill_multiplier", "label": "技能倍率", "value": breakdown_skill_result, "unit": "%"},
                {"key": "element_multiplier", "label": "屬性倍率", "value": breakdown_element_multiplier, "unit": "%"},
                {"key": "after_mdef", "label": "後MDEF", "value": target_mdef, "unit": ""},
                {
                    "key": "ignore_magic_class_def",
                    "label": "無視魔法階級防禦",
                    "value": round(_stage17_effect_multiplier(effect_dict, "MD_class_def", target_class)),
                    "unit": "%",
                },
                {
                    "key": "ignore_magic_race_def",
                    "label": "無視魔法種族防禦",
                    "value": round(
                        _stage17_effect_multiplier(effect_dict, "MD_Race_def", target_race)
                        + _stage17_effect_multiplier(effect_dict, "MD_Race_def", 9999)
                    ),
                    "unit": "%",
                },
                {
                    "key": "magic_after_def_damage",
                    "label": "魔法破防後傷害",
                    "value": mdef_multiplier * 100,
                    "unit": "%",
                    "digits": 2,
                },
                {"key": "front_mdef", "label": "前MDEF", "value": _stage17_number(monster.get("mdefc", 0), 0), "unit": ""},
                {"key": "mres", "label": "MRES", "value": target_mres, "unit": ""},
                {"key": "ignore_magic_res", "label": "無視魔法抗性", "value": mres_reduction, "unit": "%"},
                {
                    "key": "magic_after_res_damage",
                    "label": "魔法破抗性後傷害",
                    "value": mres_multiplier * 100,
                    "unit": "%",
                    "digits": 2,
                },
                {"key": "skill_equipment", "label": "技能增傷(裝備段)", "value": round(breakdown_use_skills), "unit": "%"},
                {"key": "skill_passive", "label": "技能增傷(技能段)", "value": round(breakdown_passive_skill), "unit": "%"},
            ],
        }
    elif attack_type == "physical":
        breakdown_weapon_l_atk = _stage17_int(
            weapon_atk_map.get(
                3,
                weapon_atk_map.get("3", 0),
            )
        )
        breakdown_dex_weapon = (
            weapon_class
            in STAGE17_DEX_WEAPON_CLASSES
        )
        breakdown_after_atk = (
            weapon_r_atk
            + atk_armor
            + atk_refine
            + investigate
            + kamui_atk
            + _atk_refine_l
            + breakdown_weapon_l_atk
        )
        if not breakdown_dex_weapon:
            breakdown_after_atk -= refine_over_atk

        breakdown_range_or_melee = (
            range_damage
            + (
                bow_atk
                if weapon_class == 11
                else 0
            )
            if ranged
            else melee_damage
        )
        breakdown_range_label = (
            "遠傷"
            if ranged
            else "近傷"
        )

        damage_breakdown = {
            "mode": "physical",
            "label": "物理",
            "rows": [
                {
                    "key": "front_atk_display",
                    "label": (
                        "前ATK (DEX系)"
                        if breakdown_dex_weapon
                        else "前ATK(STR系)"
                    ),
                    "value": fatk if breakdown_dex_weapon else natk,
                    "unit": "",
                },
                {
                    "key": "back_atk_display",
                    "label": (
                        "後ATK (DEX系)"
                        if breakdown_dex_weapon
                        else "後ATK(STR系)"
                    ),
                    "value": breakdown_after_atk,
                    "unit": "",
                },
                {"key": "weapon_atk", "label": "武器ATK", "value": weapon_r_atk, "unit": ""},
                {"key": "mastery_atk", "label": "修煉ATK", "value": weapon_mastery, "unit": ""},
                {"key": "atk_percent", "label": "物理ATK%", "value": round(atk_percent), "unit": "%"},
                {
                    "key": "physical_size",
                    "label": "物理體型",
                    "value": round(_stage17_effect_multiplier(effect_dict, "D_size", target_size)),
                    "unit": "%",
                },
                {
                    "key": "physical_race",
                    "label": "物理種族",
                    "value": round(
                        _stage17_effect_multiplier(effect_dict, "D_Race", target_race)
                        + _stage17_effect_multiplier(effect_dict, "D_Race", 9999)
                    ),
                    "unit": "%",
                },
                {
                    "key": "physical_class",
                    "label": "物理階級",
                    "value": round(_stage17_effect_multiplier(effect_dict, "D_class", target_class)),
                    "unit": "%",
                },
                {"key": "monster_damage", "label": "魔物增傷", "value": round(target_monster_physical), "unit": "%"},
                {"key": "patk", "label": "P.ATK", "value": round(total_patk), "unit": ""},
                {
                    "key": "physical_target_element",
                    "label": "物理屬性敵人",
                    "value": round(
                        _stage17_effect_multiplier(effect_dict, "D_element", target_element)
                        + _stage17_effect_multiplier(effect_dict, "D_element", 10)
                    ),
                    "unit": "%",
                },
                {"key": "physical_hit", "label": "物理命中", "value": round(hit_damage), "unit": "%"},
                {"key": "critical_damage", "label": "爆傷", "value": round(crit_damage), "unit": "%"},
                {
                    "key": "near_far",
                    "label": breakdown_range_label,
                    "value": round(breakdown_range_or_melee),
                    "unit": "%",
                },
                {"key": "crate", "label": "CRATE", "value": round(crate + int(total_crt / 3)), "unit": ""},
                {"key": "skill_multiplier", "label": "技能倍率", "value": breakdown_skill_result, "unit": "%"},
                {"key": "element_multiplier", "label": "屬性倍率", "value": breakdown_element_multiplier, "unit": "%"},
                {
                    "key": "weapon_size_penalty",
                    "label": "武器體型修正",
                    "value": weapon_penalty * 100,
                    "unit": "%",
                    "digits": 2,
                },
                {"key": "after_def", "label": "後DEF", "value": target_def, "unit": ""},
                {
                    "key": "ignore_class_def",
                    "label": "無視階級防禦",
                    "value": round(_stage17_effect_multiplier(effect_dict, "D_class_def", target_class)),
                    "unit": "%",
                },
                {
                    "key": "ignore_race_def",
                    "label": "無視種族防禦",
                    "value": round(
                        _stage17_effect_multiplier(effect_dict, "D_Race_def", target_race)
                        + _stage17_effect_multiplier(effect_dict, "D_Race_def", 9999)
                    ),
                    "unit": "%",
                },
                {
                    "key": "physical_after_def_damage",
                    "label": "物理破防後傷害",
                    "value": def_multiplier * 100,
                    "unit": "%",
                    "digits": 2,
                },
                {"key": "front_def", "label": "前DEF", "value": _stage17_number(monster.get("defc", 0), 0), "unit": ""},
                {"key": "res", "label": "RES", "value": target_res, "unit": ""},
                {"key": "ignore_physical_res", "label": "無視物理抗性", "value": res_reduction, "unit": "%"},
                {
                    "key": "physical_after_res_damage",
                    "label": "物理破抗性後傷害",
                    "value": res_multiplier * 100,
                    "unit": "%",
                    "digits": 2,
                },
                {"key": "skill_equipment", "label": "技能增傷(裝備段)", "value": round(breakdown_use_skills), "unit": "%"},
                {"key": "skill_passive", "label": "技能增傷(技能段)", "value": round(breakdown_passive_skill), "unit": "%"},
            ],
        }
    elif attack_type == "d_b":
        breakdown_range = (
            range_damage
            + (
                bow_atk
                if weapon_class == 11
                else 0
            )
        )
        damage_breakdown = {
            "mode": "d_b",
            "label": "特殊物理",
            "rows": [
                {"key": "range", "label": "遠傷", "value": round(breakdown_range), "unit": "%"},
                {"key": "skill_multiplier", "label": "技能倍率", "value": breakdown_skill_result, "unit": "%"},
                {"key": "element_multiplier", "label": "屬性倍率", "value": breakdown_element_multiplier, "unit": "%"},
                {"key": "skill_equipment", "label": "技能增傷(裝備段)", "value": round(breakdown_use_skills), "unit": "%"},
                {"key": "skill_passive", "label": "技能增傷(技能段)", "value": round(breakdown_passive_skill), "unit": "%"},
            ],
        }
    elif attack_type == "shield":
        damage_breakdown = {
            "mode": "shield",
            "label": "護盾",
            "rows": [
                {
                    "key": "shield_formula",
                    "label": "護盾可抵擋傷害",
                    "value": breakdown_skill_result,
                    "unit": "",
                },
            ],
        }
    else:
        damage_breakdown = {
            "mode": str(attack_type),
            "label": str(attack_type),
            "rows": [],
        }
    skill_timing = calculate_stage23_skill_timing(
        data_dir=data_dir,
        skill_row=row,
        skill_level=skill_level,
        effect_dict=effect_dict,
        total_dex=total_dex,
        total_int=total_int,
    )

    return {
        "coverage": "shared-desktop-standard-path",
        "display": {
            "critical_hit": critical_hit,
            "decay_hits": _stage17_int(row.get("decay_hits", 0)),
        },
        "skill": {
            "skill_id": skill_id,
            "name": skill_name,
            "code": _stage17_text(row.get("Code")),
            "level": skill_level,
            "attack_type": attack_type,
            "attack_element": attack_element,
            "formula": formula,
            "formula_source": formula_source,
            "hits": skill_hits,
        },
        "skill_timing": skill_timing,
        "monster": monster,
        "base": {
            "front_atk": front_atk,
            "weapon_atk_min": weapon_back_min,
            "weapon_atk_max": weapon_back_max,
            "magic_min": magic_min,
            "magic_max": magic_max,
            "total_patk": total_patk,
            "total_smatk": total_smatk,
            "def_multiplier": def_multiplier,
            "res_multiplier": res_multiplier,
            "mdef_multiplier": mdef_multiplier,
            "mres_multiplier": mres_multiplier,
        },
        "breakdown": damage_breakdown,
        "raw_segments": results,  # Phase 11：保留顯示前的 Stage17 分段資料
        "segments": display_results,
        "total_damage_min": total_min,
        "total_damage": total_max,
        "warnings": warnings,
    }

# === 核心去重階段 4+5：傷害 Request + 角色防禦 ===
@dataclass(frozen=True)
class Stage17DamageRequest:
    """包住既有 Stage 17 計算器、且不依賴 Qt / FastAPI 的 request 容器。"""

    request: object
    data: object
    context: object
    effect_result: object
    data_dir: str
    damage: dict


@dataclass(frozen=True)
class Stage17DamageResult:
    """不修改 calculate_stage17_damage() 的 typed 相容 wrapper。"""

    data: dict

    @property
    def total_damage(self):
        return self.data.get("total_damage", 0)

    @property
    def total_damage_min(self):
        return self.data.get("total_damage_min", 0)

    @property
    def segments(self):
        return self.data.get("segments", [])

    @property
    def breakdown(self):
        return self.data.get("breakdown", {})

    @property
    def raw_segments(self):
        return self.data.get("raw_segments", self.data.get("segments", []))

    @property
    def warnings(self):
        return self.data.get("warnings", [])

    def to_dict(self):
        return dict(self.data)


def calculate_stage17_damage_request(payload):
    """透過 UI / API 共用的單一 request / result 邊界執行 Stage 17 計算。"""
    if not isinstance(payload, Stage17DamageRequest):
        raise TypeError("payload must be Stage17DamageRequest")
    raw = calculate_stage17_damage(
        request=payload.request,
        data=payload.data,
        context=payload.context,
        effect_result=payload.effect_result,
        data_dir=payload.data_dir,
        damage=dict(payload.damage or {}),
    )
    return Stage17DamageResult(data=raw)


def _phase45_effect_sum(effect_dict, label, unit="%"):
    values = (effect_dict or {}).get((label, unit), [])
    total = 0
    for item in values:
        try:
            value = item[0] if isinstance(item, (tuple, list)) else item
            try:
                total += value
            except TypeError:
                total += float(value)
        except (TypeError, ValueError, IndexError):
            continue
    return total


def build_damage_effect_profile(effect_dict):
    """在不依賴 Qt / MainWindow 的情況下建立全部舊版輸出 / 承受傷害屬性。

    回傳的 ``legacy_attributes`` key 刻意與 ItemSearchApp.py 使用的名稱一致，
    讓唯一計算來源搬進 Core 的同時，Desktop 仍能保持向下相容。
    """
    effect_dict = effect_dict or {}
    attrs = {}

    def apply(prefix, names, template, indexes=None, body=False):
        for i, name in enumerate(names):
            idx = indexes[i] if indexes else i
            label = template.format(name)
            attr = f"{'body_' if body else ''}{prefix}_{idx}"
            attrs[attr] = _phase45_effect_sum(effect_dict, label, "%")

    # === 體型加成 / 抗性 ===
    size_names = ["小型", "中型", "大型"]
    for prefix in ("MD", "D"):
        kind = "魔法" if prefix == "MD" else "物理"
        apply(prefix + "_size", size_names, f"對 {{}} 敵人的{kind}傷害")
        apply(prefix + "_size", size_names, f"受到 {{}} 敵人的{kind}傷害", body=True)

    # === 屬性對象加成 / 抗性 ===
    elements = ["無屬性", "水屬性", "地屬性", "火屬性", "風屬性", "毒屬性", "聖屬性", "暗屬性", "念屬性", "不死屬性", "全屬性"]
    for prefix in ("MD", "D"):
        kind = "魔法" if prefix == "MD" else "物理"
        apply(prefix + "_element", elements, f"對 {{}} 對象的{kind}傷害")
        apply(prefix + "_element", elements, f"受到 {{}} 對象的{kind}傷害", body=True)
        # === 屬性來源加成 / 抗性（屬性攻擊） ===
        apply(prefix + "_Damage", elements, f"{{}} 的{kind}傷害")
        apply(prefix + "_Damage", elements, "對 {} 攻擊抗性", body=True)

    # === 種族加成 / 抗性 ===
    races = ["無形", "不死", "動物", "植物", "昆蟲", "魚貝", "惡魔", "人形", "天使", "龍族", "全種族"]
    race_indexes = list(range(10)) + [9999]
    for prefix in ("MD", "D"):
        kind = "魔法" if prefix == "MD" else "物理"
        apply(prefix + "_Race", races, f"對 {{}} 型怪的{kind}傷害", race_indexes)
        # 目前 Desktop 語意刻意讓 MD 與 D 使用相同的「受到種族傷害」標籤，
        # 因此去重重構期間也保留這個行為。
        apply(prefix + "_Race", races, "受到 {} 型怪的傷害", race_indexes, body=True)

    # === 階級加成 / 抗性 ===
    classes = ["一般", "首領"]
    for prefix in ("MD", "D"):
        kind = "魔法" if prefix == "MD" else "物理"
        apply(prefix + "_class", classes, f"對 {{}} 階級的{kind}傷害")
        apply(prefix + "_class", classes, f"受到 {{}} 階級的{kind}傷害", body=True)

    # === 無視階級防禦 ===
    class_def_names = ["一般", "首領", "玩家"]
    for prefix in ("MD", "D"):
        kind = "魔法" if prefix == "MD" else "物理"
        apply(prefix + "_class_def", class_def_names, f"無視 {{}} 階級的{kind}防禦")

    # === 無視種族防禦 / 抗性 ===
    for prefix in ("MD", "D"):
        kind = "魔法" if prefix == "MD" else "物理"
        apply(prefix + "_Race_def", races, f"無視 {{}} 型怪的{kind}防禦", race_indexes)
        apply(prefix + "_Race_res", races, f"無視 {{}} 型怪的{kind}抗性", race_indexes)

    attrs["body_MeleeAttackDamage"] = _phase45_effect_sum(effect_dict, "受到近距離物理傷害", "%")
    attrs["body_RangeAttackDamage"] = _phase45_effect_sum(effect_dict, "受到遠距離物理傷害", "%")

    return {
        "legacy_attributes": attrs,
        "body_melee": attrs["body_MeleeAttackDamage"],
        "body_range": attrs["body_RangeAttackDamage"],
    }


def calculate_character_defense_profile(
    *,
    effect_dict,
    base_level,
    total_agi,
    total_vit,
    total_dex,
    total_int,
    total_sta,
    total_wis,
    armor_def,
    armor_res,
    target_size,
    target_element,
    target_race,
    target_class,
    monster_attack_element,
):
    """Desktop 角色 DEF / MDEF / RES / MRES 減傷區塊的純 Core 版本。

    完整保留目前 Desktop 行為，包括魔法路徑使用「受到種族傷害」，以及最終魔法
    MDEF 倍率使用裝備 MDEF（不是前 MDEF）。若要改行為，之後應另外處理。
    """
    effect_dict = effect_dict or {}
    profile = build_damage_effect_profile(effect_dict)
    attrs = profile["legacy_attributes"]

    def attr(name, index):
        return float(attrs.get(f"{name}_{index}", 0) or 0)

    target_size = _stage17_int(target_size)
    target_element = _stage17_int(target_element)
    target_race = _stage17_int(target_race)
    target_class = _stage17_int(target_class)
    monster_attack_element = _stage17_int(monster_attack_element)

    body_size_phys = attr("body_D_size", target_size)
    body_size_magic = attr("body_MD_size", target_size)
    body_element_phys = attr("body_D_element", target_element) + attr("body_D_element", 10)
    body_element_magic = attr("body_MD_element", target_element) + attr("body_MD_element", 10)
    body_race_phys = attr("body_D_Race", target_race) + attr("body_D_Race", 9999)
    body_class_phys = attr("body_D_class", target_class)
    body_class_magic = attr("body_MD_class", target_class)
    body_attr_resist = attr("body_D_Damage", monster_attack_element) + attr("body_D_Damage", 10)
    body_melee_phys = float(profile["body_melee"] or 0)
    body_range_phys = float(profile["body_range"] or 0)

    body_def = _phase45_effect_sum(effect_dict, "DEF", "")
    body_mdef = _phase45_effect_sum(effect_dict, "MDEF", "")
    body_res = _phase45_effect_sum(effect_dict, "RES", "")
    body_mres = _phase45_effect_sum(effect_dict, "MRES", "")

    base_level = _stage17_number(base_level, 0)
    total_agi = _stage17_number(total_agi, 0)
    total_vit = _stage17_number(total_vit, 0)
    total_dex = _stage17_number(total_dex, 0)
    total_int = _stage17_number(total_int, 0)
    total_sta = _stage17_number(total_sta, 0)
    total_wis = _stage17_number(total_wis, 0)
    armor_def = _stage17_number(armor_def, 0)
    armor_res = _stage17_number(armor_res, 0)

    front_def = int(base_level / 2 + total_agi / 5 + total_vit / 2)
    after_def = int(armor_def + body_def)
    front_mdef = int(base_level / 4 + total_vit / 5 + total_dex / 5 + total_int)
    stat_res = int(total_sta + int(total_sta / 3) * 5)
    stat_mres = int(total_wis + int(total_wis / 3) * 5)
    total_res = int(stat_res + armor_res + body_res)
    total_mres = int(stat_mres + armor_res + body_mres)

    back_physical_multiplier = max(
        (1 + body_size_phys / 100)
        * (1 + body_element_phys / 100)
        * (1 + body_class_phys / 100)
        * (1 - body_attr_resist / 100),
        0,
    )
    res_multiplier = stage17_calc_final_res_damage(total_res, 0)
    def_multiplier = stage17_calc_final_def_damage(after_def, 0)
    mres_multiplier = stage17_calc_final_res_damage(total_mres, 0)
    mdef_multiplier = stage17_calc_final_mdef_damage(body_mdef, 0)

    full_melee_multiplier = max(
        (1 + body_race_phys / 100) * (1 + body_melee_phys / 100), 0
    ) * res_multiplier * def_multiplier
    full_range_multiplier = max(
        (1 + body_race_phys / 100) * (1 + body_range_phys / 100), 0
    ) * res_multiplier * def_multiplier
    full_magic_multiplier = max(
        (1 + body_size_magic / 100)
        * (1 + body_element_magic / 100)
        * (1 + body_class_magic / 100)
        * (1 - body_attr_resist / 100)
        * (1 + body_race_phys / 100),
        0,
    ) * mres_multiplier * mdef_multiplier

    return {
        "effect_profile": profile,
        "body_size_phys": body_size_phys,
        "body_size_magic": body_size_magic,
        "body_element_phys": body_element_phys,
        "body_element_magic": body_element_magic,
        "body_race_phys": body_race_phys,
        "body_class_phys": body_class_phys,
        "body_class_magic": body_class_magic,
        "body_attr_resist": body_attr_resist,
        "body_melee_phys": body_melee_phys,
        "body_range_phys": body_range_phys,
        "body_def": body_def,
        "body_mdef": body_mdef,
        "body_res": body_res,
        "body_mres": body_mres,
        "front_def": front_def,
        "after_def": after_def,
        "front_mdef": front_mdef,
        "stat_res": stat_res,
        "stat_mres": stat_mres,
        "total_res": total_res,
        "total_mres": total_mres,
        "back_physical_multiplier": back_physical_multiplier,
        "res_multiplier": res_multiplier,
        "def_multiplier": def_multiplier,
        "mres_multiplier": mres_multiplier,
        "mdef_multiplier": mdef_multiplier,
        "full_melee_multiplier": full_melee_multiplier,
        "full_range_multiplier": full_range_multiplier,
        "full_magic_multiplier": full_magic_multiplier,
    }


# === 核心去重階段 6：STAGE17 同結果驗證後切換 ===
def stage17_normalize_display_segments(segments):
    """把 legacy / Core 分段 list 正規化成 Desktop 顯示語意。"""
    rows = [dict(item) for item in (segments or []) if isinstance(item, dict)]
    if len(rows) <= 1:
        return rows

    combo_split = [
        item for item in rows[1:]
        if str(item.get("label", "")) == "combo (均分)"
        and _stage17_int(item.get("times", 1), 1) > 1
        and _stage17_int(item.get("damage_by_hit", 0)) * _stage17_int(item.get("times", 1), 1)
            == _stage17_int(item.get("total_damage", 0))
    ]
    if combo_split:
        return [rows[0], combo_split[0]]
    return rows


def stage17_compare_damage_parity(legacy_segments, core_result, *, numeric_tolerance=1e-6):
    """比較舊版 Desktop Stage17 結果與 Core render contract。

    刻意只比較會影響可見傷害結果的數值。若不一致，回傳診斷資訊而不是拋例外，
    讓 Desktop 可以安全保留舊版顯示路徑。
    """
    if hasattr(core_result, "to_dict"):
        core_result = core_result.to_dict()
    if not isinstance(core_result, dict):
        return {
            "ok": False,
            "mismatches": ["Core result is missing or is not a mapping"],
            "legacy_count": 0,
            "core_count": 0,
        }

    legacy = stage17_normalize_display_segments(legacy_segments)
    core = stage17_normalize_display_segments(core_result.get("segments", []))
    mismatches = []

    if core_result.get("coverage") != "shared-desktop-standard-path":
        mismatches.append(f"unsupported coverage={core_result.get('coverage')!r}")

    if len(legacy) != len(core):
        mismatches.append(f"segment count legacy={len(legacy)} core={len(core)}")

    int_fields = (
        "damage_by_hit_min",
        "damage_by_hit",
        "total_damage_min",
        "total_damage",
        "times",
        "user_attack_element",
    )
    for idx, (old, new) in enumerate(zip(legacy, core), start=1):
        old_label = str(old.get("label", ""))
        new_label = str(new.get("label", ""))
        if old_label != new_label:
            mismatches.append(f"segment {idx} label legacy={old_label!r} core={new_label!r}")
        for field in int_fields:
            old_value = _stage17_int(old.get(field, 0))
            new_value = _stage17_int(new.get(field, 0))
            if old_value != new_value:
                mismatches.append(
                    f"segment {idx} {field} legacy={old_value} core={new_value}"
                )
        old_skill = _stage17_number(old.get("skill_result", 0), 0)
        new_skill = _stage17_number(new.get("skill_result", 0), 0)
        if abs(old_skill - new_skill) > float(numeric_tolerance):
            mismatches.append(
                f"segment {idx} skill_result legacy={old_skill} core={new_skill}"
            )

    legacy_total_min = sum(_stage17_int(item.get("total_damage_min", 0)) for item in legacy)
    legacy_total_max = sum(_stage17_int(item.get("total_damage", 0)) for item in legacy)
    core_total_min = _stage17_int(core_result.get("total_damage_min", 0))
    core_total_max = _stage17_int(core_result.get("total_damage", 0))
    if legacy_total_min != core_total_min:
        mismatches.append(f"total_damage_min legacy={legacy_total_min} core={core_total_min}")
    if legacy_total_max != core_total_max:
        mismatches.append(f"total_damage legacy={legacy_total_max} core={core_total_max}")

    return {
        "ok": not mismatches,
        "mismatches": mismatches,
        "legacy_count": len(legacy),
        "core_count": len(core),
        "legacy_total_damage_min": legacy_total_min,
        "legacy_total_damage": legacy_total_max,
        "core_total_damage_min": core_total_min,
        "core_total_damage": core_total_max,
    }


# === STAGE 18 共用怪物查詢核心 ===
# Desktop 與 Web 共用的純標準函式庫怪物 helper。
# 此區塊不要依賴 PySide6 / FastAPI / 網路 I/O。

def stage18_decode_monster_element(element_code):
    """與 Desktop monster_lookup_dialog.decode_element() 行為一致。"""
    try:
        code = int(element_code)
    except (TypeError, ValueError):
        return 0, 1

    lv_a = code // 20
    rem = code % 20
    if rem in (0, 5, 10, 15) and 1 <= lv_a <= 4:
        return rem, lv_a

    lv_b = code // 20
    id_b = code % 20
    if 1 <= lv_b <= 4:
        return id_b, lv_b

    return 0, max(1, lv_a if lv_a > 0 else 1)


def stage18_load_monster_presets(data_dir):
    """依原始順序載入 data/monsters.json。"""
    from pathlib import Path
    import json

    path = Path(data_dir) / "monsters.json"
    if not path.is_file():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []

    if not isinstance(data, list):
        return []

    rows = []
    for source_index, raw in enumerate(data):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "") or "").strip()
        try:
            monster_id = int(raw.get("id"))
        except (TypeError, ValueError):
            continue
        if not name or monster_id <= 0:
            continue
        rows.append({
            "source_index": source_index,
            "name": name,
            "id": monster_id,
        })
    return rows


def stage18_monster_cache_path(data_dir, monster_id):
    from pathlib import Path
    return Path(data_dir) / "monster" / f"{int(monster_id)}.json"


def stage18_load_cached_monster_payload(data_dir, monster_id):
    """回傳原始 Divine-Pride 快取 payload；不存在則回傳 None。"""
    import json

    path = stage18_monster_cache_path(data_dir, monster_id)
    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def stage18_parse_monster_payload(data):
    """完全依照 Desktop 方式正規化 Divine-Pride 怪物 JSON。"""
    if not isinstance(data, dict):
        raise ValueError("monster payload 必須是 dict")

    stats = data.get("stats", {})
    if not isinstance(stats, dict):
        stats = {}

    attack_data = stats.get("attack") or {}
    if not isinstance(attack_data, dict):
        attack_data = {}

    mattack_data = stats.get("magicAttack") or {}
    if not isinstance(mattack_data, dict):
        mattack_data = {}

    name = str(data.get("name") or data.get("dbname", "") or "")

    def as_int(value, default=0):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return int(default)

    level = as_int(stats.get("level"))
    strength = as_int(stats.get("str"))
    vit = as_int(stats.get("vit"))
    intelligence = as_int(stats.get("int"))

    def_after = as_int(stats.get("defense"))
    mdef_after = as_int(stats.get("magicDefense"))

    def_before = int((level + vit) / 2)
    mdef_before = int(int(level / 4) + int(vit / 10) + int(intelligence / 5))

    element_id, element_lv = stage18_decode_monster_element(
        stats.get("element", 0)
    )

    front_atk = int(level + strength)
    combat_atk = as_int(attack_data.get("maximum"))
    front_matk = int(level + intelligence)
    combat_matk = as_int(mattack_data.get("maximum"))

    monster_id = 0
    for key in ("id", "monsterId", "monster_id"):
        if key not in data:
            continue
        try:
            monster_id = int(data.get(key))
        except (TypeError, ValueError):
            monster_id = 0
        if monster_id:
            break

    return {
        "monster_id": monster_id,
        "name": name,
        "level": level,
        "element_id": int(element_id),
        "element_lv": int(element_lv),
        "size_id": as_int(stats.get("scale")),
        "race_id": as_int(stats.get("race")),
        "class_id": as_int(stats.get("class")),
        "def_before": int(def_before),
        "mdef_before": int(mdef_before),
        "def_after": int(def_after),
        "mdef_after": int(mdef_after),
        "res": as_int(stats.get("res")),
        "mres": as_int(stats.get("mres")),
        "monster_f_atk": int(front_atk),
        "monster_c_atk": int(combat_atk),
        "monster_f_matk": int(front_matk),
        "monster_c_matk": int(combat_matk),
    }

# === STAGE 19 共用技能樹與 RRF 匯入核心 ===
# Desktop 與 Web 共用的純標準函式庫 helper。
# 此處不使用 PySide6 / FastAPI / subprocess / 網路 I/O。

STAGE19_RRF_GRADE_MAP = {0: "N", 1: "D", 2: "C", 3: "B", 4: "A"}

STAGE19_RRF_GROUP_NAME_MAP = {
    1: "頭下", 2: "右手(武器)", 3: "披肩", 4: "飾品右", 5: "鎧甲",
    6: "左手(盾牌)", 7: "鞋子", 8: "飾品左", 9: "頭上", 10: "頭中",
}

STAGE19_RRF_SHADOW_GROUP_NAME_MAP = {
    1: "服飾頭下", 2: "影子手套", 3: "服飾斗篷", 4: "影子耳環右",
    5: "影子鎧甲", 6: "影子盾牌", 7: "影子鞋子", 8: "影子墬子左",
    9: "服飾頭上", 10: "服飾頭中",
}

# source set -> 最終 state ID；會先移除符合的來源 state，
# 與 Desktop 在寫入平面 `buff` 欄位前使用的轉換方式一致。
STAGE19_RRF_EFST_COMBO_RULES = [
    ({241, 242, 243, 244, 245, 246}, {1641}, {1034, 685}),
    ({150, 151, 247, 248}, {796}, set()),
    ({150, 241}, {150, 271}, set()),
    ({247, 242}, {247, 272}, set()),
    ({151, 245}, {151, 275}, set()),
    ({248, 244}, {248, 274}, set()),
    ({249, 246}, {249, 276}, set()),
]


def _stage19_read_text_auto(path):
    from pathlib import Path
    path = Path(path)
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
        except OSError:
            return ""
    try:
        return path.read_text(encoding="big5", errors="replace")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# 技能樹
# ---------------------------------------------------------------------------

def stage19_parse_skill_tree_data(data):
    if not isinstance(data, dict):
        return {}
    body = data.get("Body", data)
    if not isinstance(body, list):
        return {}
    result = {}
    for entry in body:
        if not isinstance(entry, dict):
            continue
        job = str(entry.get("Job") or "").strip()
        if not job:
            continue
        inherit = entry.get("Inherit") or {}
        tree = entry.get("Tree") or []
        result[job] = {
            "inherit": dict(inherit) if isinstance(inherit, dict) else {},
            "tree": list(tree) if isinstance(tree, list) else [],
        }
    return result


def stage19_parse_skill_treeview_text(lua_text):
    import re
    result = {}
    pattern = re.compile(r"\[JOBID\.JT_([A-Z0-9_]+)\]\s*=\s*\{(.*?)\}", re.S)
    for jt_name, body in pattern.findall(str(lua_text or "")):
        job_key = "_".join(part.capitalize() for part in jt_name.lower().split("_"))
        pairs = re.findall(r"\[(\d+)\]\s*=\s*SKID\.([A-Z0-9_]+)", body)
        if pairs:
            result[job_key] = {code: int(index) for index, code in pairs}
    return result


def stage19_get_job_chain(job_key, job_dict):
    chain = []
    entry = None
    for _jid, info in (job_dict or {}).items():
        if isinstance(info, dict) and info.get("id_jobneme") == job_key:
            entry = info
            break
    if entry:
        for name in str(entry.get("id_jobneme_OL") or "").split("/"):
            name = name.strip()
            if name:
                chain.append(name)
    if job_key:
        chain.append(job_key)
    return chain


def stage19_split_job_chain_to_groups(job_chain):
    chain = list(job_chain or [])
    groups = []
    i = 0
    while i < len(chain):
        current = str(chain[i])
        if i + 1 < len(chain):
            nxt = str(chain[i + 1])
            if nxt.endswith("_H") and nxt[:-2] == current:
                groups.append([current, nxt])
                i += 2
                continue
        groups.append([current])
        i += 1
    return groups


def stage19_build_job_skill_map(job_name, job_skill_tree_raw, visited=None):
    if visited is None:
        visited = set()
    if job_name in visited:
        return {}
    visited.add(job_name)
    if job_name not in (job_skill_tree_raw or {}):
        return {}

    data = job_skill_tree_raw[job_name]
    result = {}
    inherit = data.get("inherit") or {}
    if isinstance(inherit, dict):
        for parent, use_it in inherit.items():
            if not use_it:
                continue
            parent_map = stage19_build_job_skill_map(parent, job_skill_tree_raw, visited)
            for code, info in parent_map.items():
                if info.get("Exclude"):
                    continue
                result.setdefault(code, dict(info))

    for row in data.get("tree", []) or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("Name") or "").strip()
        if code:
            result[code] = dict(row)
    return result


def stage19_compute_skill_depths(skill_map_job):
    depths = {}

    def dfs(code, stack=None):
        if code in depths:
            return depths[code]
        if stack is None:
            stack = set()
        if code in stack:
            return 0
        stack.add(code)
        info = (skill_map_job or {}).get(code, {})
        parents = []
        for req in info.get("Requires", []) or []:
            if isinstance(req, dict):
                parent = req.get("Name")
                if parent in skill_map_job:
                    parents.append(dfs(parent, stack))
        depth = max(parents) + 1 if parents else 0
        depths[code] = depth
        stack.remove(code)
        return depth

    for code in (skill_map_job or {}):
        dfs(code)
    return depths


def stage19_load_skill_csv_maps(data_dir):
    import csv
    from pathlib import Path
    path = Path(data_dir) / "skillneme.csv"
    code_to_id, code_to_name, id_to_name = {}, {}, {}
    if not path.is_file():
        return code_to_id, code_to_name, id_to_name
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                for row in csv.DictReader(handle):
                    try:
                        skill_id = int(row.get("ID", 0) or 0)
                    except (TypeError, ValueError):
                        continue
                    code = str(row.get("Code", "") or "").strip()
                    name = str(row.get("Name", "") or "").strip()
                    if code and skill_id > 0:
                        code_to_id[code] = skill_id
                        code_to_name[code] = name or code
                        id_to_name[skill_id] = name or code
            break
        except UnicodeDecodeError:
            continue
        except OSError:
            break
    return code_to_id, code_to_name, id_to_name


def stage19_find_job_entry(job_dict, job_id=None, job_key=None):
    if job_id is not None:
        try:
            numeric = int(job_id)
        except (TypeError, ValueError):
            numeric = None
        if numeric is not None:
            for key in (numeric, str(numeric)):
                info = (job_dict or {}).get(key)
                if isinstance(info, dict):
                    return key, info
            for key, info in (job_dict or {}).items():
                if not isinstance(info, dict):
                    continue
                pure = info.get("GetPureJob", []) or []
                if numeric in pure:
                    return key, info
    if job_key:
        for key, info in (job_dict or {}).items():
            if isinstance(info, dict) and info.get("id_jobneme") == job_key:
                return key, info
    return None, None


def _stage19_parse_points(raw):
    if isinstance(raw, str):
        source = raw.split("/")
    elif isinstance(raw, (list, tuple)):
        source = raw
    else:
        source = []
    result = []
    for value in source:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            result.append(0)
    return result


def stage19_build_skill_tree_payload(job_id, job_dict, job_skill_tree_raw, treeview_positions, code_to_id, code_to_name):
    _key, job_entry = stage19_find_job_entry(job_dict, job_id=job_id)
    if not job_entry:
        raise ValueError(f"找不到職業：{job_id}")
    job_key = str(job_entry.get("id_jobneme") or "").strip()
    if not job_key:
        raise ValueError(f"職業 {job_id} 沒有 id_jobneme")

    skill_map = stage19_build_job_skill_map(job_key, job_skill_tree_raw)
    chain = stage19_get_job_chain(job_key, job_dict)
    groups = stage19_split_job_chain_to_groups(chain)
    depths = stage19_compute_skill_depths(skill_map)
    point_values = _stage19_parse_points(job_entry.get("point"))
    job_index = {name: idx for idx, name in enumerate(chain)}

    region_max = []
    for group in groups:
        total = 0
        for name in group:
            idx = job_index.get(name)
            if idx is not None and idx < len(point_values):
                total += point_values[idx]
        region_max.append(total)

    skill_region = {}
    for region_index, group in enumerate(groups):
        for name in group:
            for code in (treeview_positions or {}).get(name, {}):
                if code in skill_map:
                    skill_region.setdefault(code, region_index)
    default_region = max(0, len(groups) - 1)
    for code in skill_map:
        skill_region.setdefault(code, default_region)

    positions = {}
    for name in chain[:-1]:
        for code, idx in (treeview_positions or {}).get(name, {}).items():
            positions.setdefault(code, int(idx))
    for code, idx in (treeview_positions or {}).get(job_key, {}).items():
        positions[code] = int(idx)

    nodes = []
    for source_index, (code, info) in enumerate(skill_map.items()):
        try:
            max_level = int(info.get("MaxLevel", 0) or 0)
        except (TypeError, ValueError):
            max_level = 0
        requires = []
        for req in info.get("Requires", []) or []:
            if not isinstance(req, dict):
                continue
            parent = str(req.get("Name") or "").strip()
            if not parent:
                continue
            try:
                level = int(req.get("Level", 1) or 1)
            except (TypeError, ValueError):
                level = 1
            requires.append({
                "code": parent,
                "level": level,
                "name": code_to_name.get(parent, parent),
            })
        nodes.append({
            "code": code,
            "skill_id": code_to_id.get(code),
            "name": code_to_name.get(code, code),
            "max_level": max_level,
            "quest_skill": bool(info.get("QuestSkill")),
            "requires": requires,
            "region": int(skill_region.get(code, default_region)),
            "depth": int(depths.get(code, 0)),
            "position": int(positions.get(code, 100000 + source_index)),
            "source_index": source_index,
        })
    nodes.sort(key=lambda row: (row["region"], row["position"], row["depth"], row["source_index"], row["code"]))

    labels = ["1轉", "2轉", "3轉", "4轉"]
    return {
        "job_id": int(job_id),
        "job_key": job_key,
        "job_name": str(job_entry.get("name") or job_key),
        "job_chain": chain,
        "groups": [
            {
                "index": idx,
                "jobs": group,
                "label": labels[idx] if idx < len(labels) else f"{idx + 1}區",
                "max_points": int(region_max[idx]) if idx < len(region_max) else 0,
            }
            for idx, group in enumerate(groups)
        ],
        "nodes": nodes,
    }


def stage19_build_enable_skill_note(levels_by_code, code_to_id):
    lines = []
    for code, raw_level in (levels_by_code or {}).items():
        try:
            level = int(raw_level)
        except (TypeError, ValueError):
            continue
        skill_id = code_to_id.get(code)
        if skill_id and level > 0:
            lines.append(f"EnableSkill({int(skill_id)}, {level})")
    return "\n".join(lines)


def stage19_parse_enable_skill_note(note, id_to_code):
    import re
    result = {}
    for raw_id, raw_level in re.findall(r"EnableSkill\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", str(note or "")):
        code = id_to_code.get(int(raw_id))
        if code:
            result[code] = int(raw_level)
    return result


def _stage19_skill_region_used(levels, nodes):
    node_by_code = {row["code"]: row for row in nodes}
    used = {}
    for code, raw in (levels or {}).items():
        node = node_by_code.get(code)
        if not node or node.get("quest_skill"):
            continue
        try:
            value = max(0, int(raw))
        except (TypeError, ValueError):
            continue
        region = int(node.get("region", 0))
        used[region] = used.get(region, 0) + value
    return used


def stage19_apply_skill_level_change(tree_payload, levels, code, target_level):
    nodes = list(tree_payload.get("nodes", []) or [])
    groups = list(tree_payload.get("groups", []) or [])
    node_by_code = {row["code"]: row for row in nodes}
    target = node_by_code.get(code)
    if not target:
        raise ValueError(f"技能不存在：{code}")
    if target.get("quest_skill"):
        return {"levels": dict(levels or {}), "message": "任務/靈魂習得技能不能用技能點直接修改。"}

    current = {}
    for node_code, raw in (levels or {}).items():
        node = node_by_code.get(node_code)
        if not node:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = 0
        current[node_code] = max(0, min(value, int(node.get("max_level", 0) or 0)))

    old = current.get(code, 0)
    desired = max(0, min(int(target_level), int(target.get("max_level", 0) or 0)))

    dependents = {row["code"]: [] for row in nodes}
    for row in nodes:
        for req in row.get("requires", []) or []:
            if req.get("code") in dependents:
                dependents[req["code"]].append(row["code"])

    if desired < old:
        current[code] = desired
        def invalidate(parent_code, visited=None):
            if visited is None:
                visited = set()
            if parent_code in visited:
                return
            visited.add(parent_code)
            for child_code in dependents.get(parent_code, []):
                if current.get(child_code, 0) <= 0:
                    continue
                child = node_by_code[child_code]
                if any(current.get(req["code"], 0) < int(req["level"]) for req in child.get("requires", []) or []):
                    current[child_code] = 0
                    invalidate(child_code, visited)
        invalidate(code)
        return {"levels": current, "message": ""}

    if desired == old:
        return {"levels": current, "message": ""}

    message = ""
    while current.get(code, 0) < desired:
        candidate = dict(current)

        def ensure_prerequisites(target_code, visited=None):
            if visited is None:
                visited = set()
            if target_code in visited:
                return
            visited.add(target_code)
            node = node_by_code.get(target_code, {})
            for req in node.get("requires", []) or []:
                parent_code = req["code"]
                ensure_prerequisites(parent_code, visited)
                parent = node_by_code.get(parent_code)
                if not parent:
                    continue
                wanted = min(int(req["level"]), int(parent.get("max_level", 0) or 0))
                if candidate.get(parent_code, 0) < wanted:
                    candidate[parent_code] = wanted

        ensure_prerequisites(code)
        target_region = int(target.get("region", 0))
        used_pre = _stage19_skill_region_used(candidate, nodes)
        locked = []
        for region in range(target_region):
            max_points = int(groups[region].get("max_points", 0) or 0) if region < len(groups) else 0
            if max_points > 0 and used_pre.get(region, 0) < max_points:
                locked.append(region)
        if locked:
            current = candidate
            message = "、".join(str(groups[i].get("label") or f"{i + 1}區") for i in locked) + " 點數尚未點滿，已先自動補可用前置。"
            break

        candidate[code] = candidate.get(code, 0) + 1
        used = _stage19_skill_region_used(candidate, nodes)
        if any(
            int(group.get("max_points", 0) or 0) > 0
            and used.get(index, 0) > int(group.get("max_points", 0) or 0)
            for index, group in enumerate(groups)
        ):
            message = "技能點不足，這次加點未套用。"
            break
        current = candidate

    return {"levels": current, "message": message}


# ---------------------------------------------------------------------------
# RRF replay dump 解析器
# ---------------------------------------------------------------------------

def stage19_rrf_parse_skillinfo_list_from_text(content):
    import re, string
    match = re.search(r"packet\s+HEADER_ZC_SKILLINFO_LIST[\s\S]*?\{([\s\S]*?)^\}\n\s*\n", str(content or ""), re.MULTILINE)
    if not match:
        return []
    hex_list = re.findall(r"\b([0-9A-Fa-f]{2})\b", match.group(1))
    allowed = set(string.ascii_uppercase + string.digits + "_")
    skills = []
    i = 0
    while i < len(hex_list) - 20:
        if hex_list[i] == "00" or hex_list[i + 1] == "00":
            i += 1
            continue
        name_start = i
        name_bytes = []
        j = i
        while j < len(hex_list) and hex_list[j] != "00":
            name_bytes.append(hex_list[j]); j += 1
        try:
            name = bytes.fromhex("".join(name_bytes)).decode("ascii", errors="ignore")
        except Exception:
            name = ""
        if len(name) < 3 or "_" not in name or any(ch not in allowed for ch in name):
            i += 1
            continue
        level = 0
        level_pos = name_start - 6
        if level_pos >= 0 and level_pos + 1 < len(hex_list):
            level = int(hex_list[level_pos], 16) + (int(hex_list[level_pos + 1], 16) << 8)
        skills.append((name, level))
        i = j + 1
    return skills


def _stage19_rrf_extract_hex_bytes(block):
    import re
    out = []
    for line in str(block or "").splitlines():
        line = re.sub(r"^\s*[0-9A-Fa-f]{4,}\s+", "", line.strip())
        out.extend(re.findall(r"\b([0-9A-Fa-f]{2})\b", line))
    return out


def stage19_rrf_extract_session_stats_from_text(content):
    import re
    content = str(content or "")
    result = {}
    for field in ("Job", "Level", "JobLevel", "Str", "Agi", "Vit", "Int", "Dex", "Luk"):
        match = re.search(r"\[Chunk Session\] Unparsed opcode " + re.escape(field) + r", Length=4\s+[^\{]*\{([^}]*)\}", content, re.DOTALL)
        if not match:
            continue
        values = []
        for line in match.group(1).splitlines():
            hexes = re.findall(r"\b([0-9A-Fa-f]{2})\b", line.strip())
            if len(hexes) >= 4:
                values.extend(hexes[-4:])
        if len(values) == 4:
            result[field] = int("".join(reversed(values)), 16)

    attr_map = {0xDB: "POW", 0xDC: "STA", 0xDD: "WIS", 0xDE: "SPL", 0xDF: "CON", 0xE0: "CRT"}
    for block in re.findall(r"packet HEADER_ZC_COUPLESTATUS.*?\{([^}]*)\}", content, re.DOTALL):
        values = re.findall(r"\b([0-9A-Fa-f]{2})\b", block)
        if len(values) < 8:
            continue
        attr_id = int(values[2], 16)
        if attr_id in attr_map:
            result[attr_map[attr_id]] = (int(values[7], 16) << 8) | int(values[6], 16)

    match = re.search(r"\[Chunk ReplayData\] Unparsed opcode Charactername, Length=64.*?Raw hex:[^\{]*\{([^}]*)\}", content, re.DOTALL)
    if match:
        values = []
        for line in match.group(1).splitlines():
            values.extend(re.findall(r"\b([0-9A-Fa-f]{2})\b", line.strip()))
        raw = bytes(int(value, 16) for value in values[:64]).split(b"\x00", 1)[0]
        result["Charactername"] = raw.decode("big5", errors="ignore")
    return result


def stage19_rrf_apply_efst_combo_ids(values, combo_rules=None):
    existing = {int(value) for value in values or []}
    matched, produced, new_ids = set(), set(), set()
    rules = combo_rules or STAGE19_RRF_EFST_COMBO_RULES
    for sources, targets, blockers in rules:
        sources, targets, blockers = set(sources), set(targets), set(blockers)
        if not sources.issubset(existing) or (blockers & existing):
            continue
        matched.update(sources)
        for target in targets:
            if target not in existing and target not in produced:
                produced.add(target); new_ids.add(target)
    return sorted((existing - matched) | new_ids)


def stage19_rrf_extract_efst_ids_from_text(content):
    import re
    content = str(content or "")
    values, seen = [], set()
    aid_match = re.search(r"\[Chunk Session\] Unparsed opcode Aid, Length=4[\s\S]*?\{([^}]*)\}", content, re.DOTALL)
    player_aid = None
    if aid_match:
        aid_hex = _stage19_rrf_extract_hex_bytes(aid_match.group(1))
        if len(aid_hex) >= 4:
            player_aid = "".join(x.lower() for x in aid_hex[:4])

    for block in re.findall(r"\[Chunk [^\]]+\] Unparsed opcode EfstInfo, Length=\d+[\s\S]*?\{([^}]*)\}", content, re.DOTALL):
        hex_list = _stage19_rrf_extract_hex_bytes(block)
        if len(hex_list) >= 2:
            value = int(hex_list[0], 16) | (int(hex_list[1], 16) << 8)
            if value not in seen:
                seen.add(value); values.append(value)

    if player_aid:
        for block in re.findall(r"packet\s+HEADER_ZC_MSG_STATE_CHANGE3[\s\S]*?\{([^}]*)\}", content, re.DOTALL):
            hex_list = _stage19_rrf_extract_hex_bytes(block)
            for index in range(max(0, len(hex_list) - 7)):
                if hex_list[index].lower() == "83" and hex_list[index + 1].lower() == "09":
                    value = int(hex_list[index + 2], 16) | (int(hex_list[index + 3], 16) << 8)
                    caster = "".join(x.lower() for x in hex_list[index + 4:index + 8])
                    if caster == player_aid and value not in seen:
                        seen.add(value); values.append(value)
                    break
    return stage19_rrf_apply_efst_combo_ids(values)


def stage19_rrf_load_enchant_json_map(data_dir):
    import re
    from pathlib import Path
    data_dir = Path(data_dir)
    enum_text = _stage19_read_text_auto(data_dir / "enumvar.lua")
    enchant_text = _stage19_read_text_auto(data_dir / "EnchantName.lua")
    id_to_key = {int(first): key for key, first, _second in re.findall(r"(\w+)\s*=\s*\{\s*(\d+)\s*,\s*(\d+)\s*\}", enum_text, re.MULTILINE)}
    key_to_format = {key: fmt for key, fmt in re.findall(r'\[EnumVAR\.([A-Z0-9_]+)\[1\]\]\s*=\s*"([^"]+)"', enchant_text)}
    return {enchant_id: key_to_format.get(key, "") for enchant_id, key in id_to_key.items()}


def _stage19_rrf_bytes_to_int_le(values):
    return int("".join(reversed(values)), 16) if values else 0


def stage19_rrf_parse_equipment_chunk_from_text(content, parsed_items, enchant_json_map, chunk_name="EquippedItems", group_map=None):
    import re
    group_map = group_map or STAGE19_RRF_GROUP_NAME_MAP
    flat, warnings = {}, []
    # Stage19 RRF 編碼修正：不要依賴 Unicode 箭頭字元。
    pattern = (
        r"\[Chunk Items\] Unparsed opcode "
        + re.escape(chunk_name)
        + r", Length=\d+[\s\S]{0,512}?\[[^\]]+\]\s*\{([\s\S]*?)^\s*\}"
    )
    match = re.search(pattern, str(content or ""), re.MULTILINE)
    if not match:
        return {"fields": flat, "warnings": warnings}

    hex_list = []
    for line in match.group(1).splitlines():
        line = re.sub(r"^\s*[0-9A-Fa-f]{4,}\s+", "", line)
        hex_list.extend(re.findall(r"([0-9A-Fa-f]{2})", line))

    starts = [i for i in range(len(hex_list) - 1) if hex_list[i].lower() == "19" and hex_list[i + 1].lower() == "01"]
    starts.append(len(hex_list))
    slot_tags = ["1901", "1b01", "1d01", "1c01", "1e01", "1f01", "2001", "2101", "2301", "2701", "2b01", "2201", "2401", "2501", "2601", "2801", "2901", "2a01", "2c01", "2d01", "1a01"]

    def has_all(group_bytes):
        for slot in slot_tags:
            a, b = slot[:2].lower(), slot[2:].lower()
            if not any(group_bytes[i].lower() == a and group_bytes[i + 1].lower() == b for i in range(len(group_bytes) - 1)):
                return False
        return True

    def item_name(item_id):
        info = (parsed_items or {}).get(item_id)
        if info is None:
            info = (parsed_items or {}).get(str(item_id))
        return str(info.get("name") or info.get("base_name") or f"[{item_id}]") if isinstance(info, dict) else f"[{item_id}]"

    locations = {}
    cursor, group_number = 0, 1
    while cursor < len(starts) - 1:
        start = starts[cursor]
        end_cursor = cursor + 1
        group_bytes = None
        while end_cursor < len(starts):
            candidate = hex_list[start:starts[end_cursor]]
            if has_all(candidate):
                group_bytes = candidate; break
            end_cursor += 1
        if group_bytes is None:
            cursor += 1; continue

        part = group_map.get(group_number, f"未知部位{group_number}")
        offsets = []
        for slot in slot_tags:
            a, b = slot[:2].lower(), slot[2:].lower()
            found = next((i for i in range(len(group_bytes) - 1) if group_bytes[i].lower() == a and group_bytes[i + 1].lower() == b), None)
            offsets.append(found)

        equip_id, equip_name = 0, ""
        for slot_index, offset in enumerate(offsets):
            if offset is None:
                continue
            next_offset = next((x for x in offsets[slot_index + 1:] if x is not None and x > offset), None)
            slot_bytes = group_bytes[offset:next_offset] if next_offset is not None else group_bytes[offset:]
            if len(slot_bytes) <= 6:
                continue
            slot_name = slot_tags[slot_index].upper()
            try:
                if slot_name == "2201":
                    ids = [_stage19_rrf_bytes_to_int_le(slot_bytes[6:9]), _stage19_rrf_bytes_to_int_le(slot_bytes[10:13]), _stage19_rrf_bytes_to_int_le(slot_bytes[14:17]), _stage19_rrf_bytes_to_int_le(slot_bytes[18:21])]
                    for index, card_id in enumerate(ids, 1):
                        flat[f"{part}_card{index}"] = item_name(card_id) if card_id else ""
                elif slot_name == "2301":
                    equip_id = _stage19_rrf_bytes_to_int_le(slot_bytes[6:9])
                    equip_name = item_name(equip_id) if equip_id else ""
                    flat[f"{part}_equip"] = equip_name
                elif slot_name == "2701":
                    flat[part] = str(int(slot_bytes[6], 16))
                elif slot_name == "2D01":
                    lua = []
                    for index in range(4):
                        id_index, value_index = 6 + index * 5, 8 + index * 5
                        if value_index >= len(slot_bytes): break
                        enchant_id, value = int(slot_bytes[id_index], 16), int(slot_bytes[value_index], 16)
                        if enchant_id == 0 and value == 0: continue
                        fmt = str((enchant_json_map or {}).get(enchant_id, "") or "")
                        if fmt: lua.append(fmt.replace("%d", str(value)))
                    flat[f"{part}_note"] = "\n".join(lua)
                elif slot_name == "2B01":
                    grade = int(slot_bytes[6], 16)
                    flat[f"{part}_階級"] = STAGE19_RRF_GRADE_MAP.get(grade, str(grade))
            except (IndexError, TypeError, ValueError):
                warnings.append(f"{chunk_name} / {part} / {slot_name} 解析失敗")

        if equip_id > 0:
            locations.setdefault(equip_id, []).append((part, equip_name))
        group_number += 1
        cursor = end_cursor

    for equip_id, places in locations.items():
        if len(places) > 1:
            warnings.append(f"裝備 ID {equip_id} 在多個部位重複：" + "、".join(f"{part}：{name}" for part, name in places) + "。請手動確認是否需清除其中一個。")
    return {"fields": flat, "warnings": warnings}


def stage19_build_rrf_desktop_json_from_dump_text(replay_text, data_dir, parsed_items, job_dict, default_json=None):
    import json
    from pathlib import Path
    data_dir = Path(data_dir)
    if default_json is None:
        path = data_dir / "default.json"
        try:
            default_json = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
        except (OSError, json.JSONDecodeError):
            default_json = {}
    output = dict(default_json or {})
    warnings = []

    code_to_id, _code_to_name, _id_to_name = stage19_load_skill_csv_maps(data_dir)
    prefix_to_id = {code[:23]: skill_id for code, skill_id in code_to_id.items()}
    skills = stage19_rrf_parse_skillinfo_list_from_text(replay_text)
    output["技能_note"] = "\n".join(
        f"EnableSkill({int(prefix_to_id[code[:23]])}, {int(level)})"
        for code, level in skills if code[:23] in prefix_to_id
    )

    session = stage19_rrf_extract_session_stats_from_text(replay_text)
    output["BaseLv"] = str(session.get("Level", ""))
    output["JobLv"] = str(session.get("JobLevel", ""))
    raw_job_id = session.get("Job")
    main_job_id, job_info = stage19_find_job_entry(job_dict, job_id=raw_job_id)
    output["JOB"] = str(job_info.get("name") or "") if job_info else ""
    for source, target in (("Str", "STR"), ("Agi", "AGI"), ("Vit", "VIT"), ("Int", "INT"), ("Dex", "DEX"), ("Luk", "LUK"), ("POW", "POW"), ("STA", "STA"), ("WIS", "WIS"), ("SPL", "SPL"), ("CON", "CON"), ("CRT", "CRT")):
        if source in session:
            output[target] = str(session[source])

    efst = stage19_rrf_extract_efst_ids_from_text(replay_text)
    output["buff"] = ",".join(str(value) for value in efst)
    enchant_map = stage19_rrf_load_enchant_json_map(data_dir)
    for chunk_name, group_map in (("EquippedItems", STAGE19_RRF_GROUP_NAME_MAP), ("EquippedShadowItems", STAGE19_RRF_SHADOW_GROUP_NAME_MAP)):
        parsed = stage19_rrf_parse_equipment_chunk_from_text(replay_text, parsed_items, enchant_map, chunk_name, group_map)
        output.update(parsed["fields"])
        warnings.extend(parsed["warnings"])

    return {
        "desktop_json": output,
        "meta": {
            "character_name": str(session.get("Charactername") or ""),
            "job_id": raw_job_id,
            "main_job_id": main_job_id,
            "job_name": str(job_info.get("name") or "") if job_info else "",
            "skill_count": len(skills),
            "buff_count": len(efst),
        },
        "warnings": warnings,
    }


# === STAGE 21.25 共用素質無詠核心 ===

def stage25_calculate_no_cast_status(
    *,
    total_dex,
    total_int,
    target=265,
):
    """Desktop 的素質無詠門檻計算，已搬到共用 Core。

    Desktop 歷史上使用：
        DEX + int(INT / 2) >= 265

    完整保留 INT 除 2 後取整的行為，確保 Desktop / Web 結果一致。
    """
    dex_part = _stage20_int(total_dex)
    int_total = _stage20_int(total_int)
    int_part = int(int_total / 2)
    target_value = max(0, _stage20_int(target, 265))
    score = dex_part + int_part
    gap = target_value - score
    reached = gap <= 0

    return {
        "target": int(target_value),
        "total_dex": int(dex_part),
        "total_int": int(int_total),
        "dex_part": int(dex_part),
        "int_part": int(int_part),
        "score": int(score),
        "gap": int(gap),
        "reached": bool(reached),
        "needed_dex": int(max(0, gap)),
        "needed_int": int(max(0, gap * 2)),
        "excess": int(max(0, -gap)),
    }


def stage25_calculate_no_cast_from_effects(
    *,
    base_dex,
    base_int,
    job_bonus,
    effect_dict,
    target=265,
):
    """Desktop / Web 共用的素質無詠高階入口。

    UI 呼叫端只提供角色 / job / 裝備原始輸入；job / 裝備 DEX / INT 彙總與
    265 門檻判斷都留在 Core。
    """
    bonuses = list(job_bonus or [])
    job_dex = _stage20_int(bonuses[4] if len(bonuses) > 4 else 0)
    job_int = _stage20_int(bonuses[3] if len(bonuses) > 3 else 0)
    equip_dex = _stage20_int(_stage20_sum_effect(effect_dict or {}, "DEX", ""))
    equip_int = _stage20_int(_stage20_sum_effect(effect_dict or {}, "INT", ""))

    base_dex_value = _stage20_int(base_dex)
    base_int_value = _stage20_int(base_int)
    total_dex = base_dex_value + job_dex + equip_dex
    total_int = base_int_value + job_int + equip_int

    result = stage25_calculate_no_cast_status(
        total_dex=total_dex,
        total_int=total_int,
        target=target,
    )
    result.update(
        {
            "base_dex": int(base_dex_value),
            "job_dex": int(job_dex),
            "equip_dex": int(equip_dex),
            "base_int": int(base_int_value),
            "job_int": int(job_int),
            "equip_int": int(equip_int),
        }
    )
    return result

# === STAGE 21.25 共用素質無詠核心結束 ===

# === STAGE 20 共用 HP / SP / ASPD 核心 ===
# Desktop 與 Web 共用的純標準函式庫 helper。

_STAGE20_STATUS_TABLE_CACHE = {}


def _stage20_number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _stage20_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return int(default)


def _stage20_sum_effect(effect_dict, name, unit=""):
    total = 0.0
    for value, _source in (effect_dict or {}).get((str(name), str(unit)), []):
        total += _stage20_number(value)
    return total


def _stage20_context_map(context, name):
    value = getattr(context, name, None)
    return value if isinstance(value, dict) else {}


def _stage20_map_get(mapping, key, default=0):
    if not isinstance(mapping, dict):
        return default
    if key in mapping:
        return mapping[key]
    text_key = str(key)
    if text_key in mapping:
        return mapping[text_key]
    return default


def stage20_load_job_status_tables(data_dir):
    """從 data/job_dict.py 載入 job_4th_hpsp 與 WPASPDdata。"""
    import ast
    from pathlib import Path

    path = Path(data_dir) / "job_dict.py"
    if not path.is_file():
        return {}, {}

    try:
        stat = path.stat()
        signature = (str(path.resolve()), int(stat.st_mtime_ns), int(stat.st_size))
    except OSError:
        signature = (str(path), 0, 0)

    cached = _STAGE20_STATUS_TABLE_CACHE.get(signature)
    if cached is not None:
        return cached

    try:
        text = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(text)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return {}, {}

    found = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if isinstance(node, ast.Assign):
            targets = node.targets
            value_node = node.value
        else:
            targets = [node.target]
            value_node = node.value

        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id not in {"job_4th_hpsp", "WPASPDdata"}:
                continue
            try:
                found[target.id] = ast.literal_eval(value_node)
            except (ValueError, TypeError, SyntaxError):
                found[target.id] = {}

    result = (
        found.get("job_4th_hpsp", {}) if isinstance(found.get("job_4th_hpsp", {}), dict) else {},
        found.get("WPASPDdata", {}) if isinstance(found.get("WPASPDdata", {}), dict) else {},
    )

    for old_key in list(_STAGE20_STATUS_TABLE_CACHE):
        if old_key[0] == signature[0] and old_key != signature:
            _STAGE20_STATUS_TABLE_CACHE.pop(old_key, None)
    _STAGE20_STATUS_TABLE_CACHE[signature] = result
    return result


# ===== 4轉職業 HP / SP 表 + 手動輸入共用計算 =====
def stage20_calculate_hpsp_values(
    *,
    job_base_hp,
    job_base_sp,
    base_vit,
    base_int,
    total_vit,
    total_int,
    hp_flat,
    sp_flat,
    hp_percent_bonus,
    sp_percent_bonus,
    mhp_input=0,
    msp_input=0,
    use_logout_values=False,
    hp_current_percent=100,
    sp_current_percent=100,
):
    """拆分前 Desktop HP/SP 算式，移除 Qt 後供 Desktop / Web 共用。

    - job_base_hp / job_base_sp：BaseLv 201~275 對應的四轉職業表基礎值。
    - mhp_input / msp_input：使用者手動輸入；若為 0 則回退職業表。
    - use_logout_values：輸入值若來自登出畫面，先反推尚未套 VIT / INT 的基礎值。
    - 裝備固定 HP/SP 也會先套用 HP% / SP%，再與基礎值合併。
    """
    import math

    job_base_hp = _stage20_number(job_base_hp)
    job_base_sp = _stage20_number(job_base_sp)
    base_vit = _stage20_number(base_vit)
    base_int = _stage20_number(base_int)
    total_vit = _stage20_number(total_vit)
    total_int = _stage20_number(total_int)
    hp_flat = _stage20_number(hp_flat)
    sp_flat = _stage20_number(sp_flat)
    hp_percent_bonus = _stage20_number(hp_percent_bonus)
    sp_percent_bonus = _stage20_number(sp_percent_bonus)
    mhp_input = _stage20_int(mhp_input)
    msp_input = _stage20_int(msp_input)

    adjusted_mhp_input = mhp_input
    adjusted_msp_input = msp_input

    # 登出畫面顯示值已包含 VIT / INT 倍率。勾選後先回推基礎值，
    # 並依原需求採無條件進位，之後再套用既有裝備與百分比加成。
    if use_logout_values:
        hp_stat_multiplier = 1 + (base_vit / 100)
        sp_stat_multiplier = 1 + (base_int / 100)
        if adjusted_mhp_input > 0 and hp_stat_multiplier > 0:
            adjusted_mhp_input = math.ceil(adjusted_mhp_input / hp_stat_multiplier)
        if adjusted_msp_input > 0 and sp_stat_multiplier > 0:
            adjusted_msp_input = math.ceil(adjusted_msp_input / sp_stat_multiplier)

    # 原 Desktop：固定 HP / SP 先吃對應百分比。
    hp_flat_scaled = hp_flat * (1 + hp_percent_bonus / 100)
    sp_flat_scaled = sp_flat * (1 + sp_percent_bonus / 100)
    hp_multiplier = (100 + total_vit) / 100
    sp_multiplier = (100 + total_int) / 100
    hp_percent_multiplier = 1 + hp_percent_bonus / 100
    sp_percent_multiplier = 1 + sp_percent_bonus / 100

    # 職業表基礎值與手動輸入值都使用相同 VIT / INT 與 HP% / SP% 公式。
    job_max_hp = int(job_base_hp * hp_multiplier * hp_percent_multiplier + hp_flat_scaled)
    job_max_sp = int(job_base_sp * sp_multiplier * sp_percent_multiplier + sp_flat_scaled)
    user_max_hp = int(adjusted_mhp_input * hp_multiplier * hp_percent_multiplier + hp_flat_scaled)
    user_max_sp = int(adjusted_msp_input * sp_multiplier * sp_percent_multiplier + sp_flat_scaled)

    # 使用者沒輸入或輸入 0 → 使用職業表。
    mhp = user_max_hp if adjusted_mhp_input > 0 else job_max_hp
    msp = user_max_sp if adjusted_msp_input > 0 else job_max_sp

    # HP / SP 滑桿只影響目前值，不改最大值。
    hp_pct = max(0, min(100, _stage20_int(hp_current_percent, 100)))
    sp_pct = max(0, min(100, _stage20_int(sp_current_percent, 100)))
    mhp_now = int(mhp * hp_pct / 100) if mhp > 0 else 0
    msp_now = int(msp * sp_pct / 100) if msp > 0 else 0

    return {
        "job_base_hp": _stage20_int(job_base_hp),
        "job_base_sp": _stage20_int(job_base_sp),
        "mhp_input": int(mhp_input),
        "msp_input": int(msp_input),
        "adjusted_mhp_input": int(adjusted_mhp_input),
        "adjusted_msp_input": int(adjusted_msp_input),
        "use_logout_values": bool(use_logout_values),
        "hp_flat": hp_flat,
        "sp_flat": sp_flat,
        "hp_percent_bonus": hp_percent_bonus,
        "sp_percent_bonus": sp_percent_bonus,
        "mhp": int(mhp),
        "msp": int(msp),
        "mhp_now": int(mhp_now),
        "msp_now": int(msp_now),
        "hp_current_percent": hp_pct,
        "sp_current_percent": sp_pct,
        "source_hp": "manual_logout" if mhp_input > 0 and use_logout_values else "manual_base" if mhp_input > 0 else "job_table",
        "source_sp": "manual_logout" if msp_input > 0 and use_logout_values else "manual_base" if msp_input > 0 else "job_table",
    }


# 攻速計算
def stage20_calc_aspd(
    wpasdp_data,
    job_id,
    agi,
    dex,
    *,
    weapon_type=None,
    has_shield=False,
    dual_wield=False,
    right_weapon_type=None,
    left_weapon_type=None,
    cat1_rate=0.0,
    cat1_flat=0.0,
    cat2_rate=0.0,
    cat2_flat=0.0,
    round_digits=3,
):
    """
    回傳：套完基礎 ASPD + 類別1 / 類別2 後的 ASPD，
    四捨五入到小數 round_digits 位（ROUND_HALF_UP）。

    這是拆分前 Desktop ``calc_aspd()`` 的同一套公式。
    """
    import math
    from decimal import Decimal, ROUND_HALF_UP

    def rate_to_decimal(value):
        # 允許傳 0.15 或 15（代表 15%）。
        value = _stage20_number(value)
        if value < 0:
            return value
        return value / 100.0 if value > 1 else value

    def round_half_up(value, digits):
        quant = Decimal("1").scaleb(-int(digits))
        return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))

    job_id = _stage20_int(job_id)
    if job_id in (wpasdp_data or {}):
        job_table = wpasdp_data[job_id]
    elif str(job_id) in (wpasdp_data or {}):
        job_table = wpasdp_data[str(job_id)]
    else:
        return "未選擇職業或該職業不支援此武器。"

    cat1_rate = rate_to_decimal(cat1_rate)
    cat2_rate = rate_to_decimal(cat2_rate)
    agi = _stage20_number(agi)
    dex = _stage20_number(dex)

    # --- 1) 先算基礎 ASPD ---
    if dual_wield:
        # 雙刀模式：左右手都要有可用的職業基礎 ASPD。
        if right_weapon_type is None or left_weapon_type is None:
            raise ValueError("dual_wield=True 時必須提供 right_weapon_type 與 left_weapon_type")
        base_r = _stage20_map_get(job_table, right_weapon_type, None)
        base_l = _stage20_map_get(job_table, left_weapon_type, None)
        if base_r is None or base_l is None:
            return "該職業不支援雙刀武器。"
        if _stage20_number(base_r) <= 0 or _stage20_number(base_l) <= 0:
            return "雙刀基礎ASPD <= 0"
        aspd = (
            _stage20_number(base_r)
            + (_stage20_number(base_l) - 194) / 4
            + math.sqrt(agi * 10.01 + dex * 11 / 60) * 1.04518
        )
    else:
        if weapon_type is None:
            raise ValueError("dual_wield=False 時必須提供 weapon_type")
        base = _stage20_map_get(job_table, weapon_type, None)
        if base is None:
            return "該職業不支援此武器。"
        base = _stage20_number(base)
        if base <= 0:
            return "基礎ASPD <= 0"

        stat_term = math.sqrt(agi * 10.09 + dex * 11 / 60)
        # 基礎 ASPD 145 以上採用係數。
        if base >= 145:
            stat_term *= (1 - (base - 144) / 50)
        # 盾牌修正通常為負數。
        shield_penalty = _stage20_number(_stage20_map_get(job_table, 50, 0)) if has_shield else 0.0
        aspd = base + stat_term + shield_penalty

    # --- 2) 類別1 ---
    aspd_1 = 200 - (200 - aspd) * (1 - cat1_rate) + _stage20_number(cat1_flat)
    # --- 3) 類別2 ---
    aspd_2 = 195 - (195 - aspd_1) * (1 - cat2_rate) + _stage20_number(cat2_flat)
    # --- 4) 小數第 3 位（或指定的位數） ---
    return round_half_up(aspd_2, round_digits)


# 將 HP / SP / ASPD / 素質無詠整理成同一份角色狀態結果。
def stage20_calculate_status(
    *,
    request,
    data,
    context,
    effect_result,
    data_dir,
    settings=None,
):
    settings = dict(settings or {})
    get_values = getattr(request, "get_values", {}) or {}
    effect_dict = getattr(effect_result, "legacy_effect_dict", {}) or {}

    job_id = _stage20_int(get_values.get(19, get_values.get("19", 0)))
    base_lv = _stage20_int(get_values.get(11, get_values.get("11", 0)))

    job_info = {}
    if isinstance(getattr(data, "job_dict", None), dict):
        job_info = data.job_dict.get(job_id, data.job_dict.get(str(job_id), {})) or {}
    job_bonus = job_info.get("TJobMaxPoint", []) or []
    stat_breakdown = calculate_stat_breakdown(
        get_values=get_values,
        job_bonus=job_bonus,
        effect_dict=effect_dict,
        integer_effects=True,
    )
    agi_values = stat_breakdown["AGI"]
    vit_values = stat_breakdown["VIT"]
    int_values = stat_breakdown["INT"]
    dex_values = stat_breakdown["DEX"]
    base_agi, job_agi, equip_agi, total_agi = (agi_values["base"], agi_values["job"], agi_values["equip"], agi_values["total"])
    base_vit, job_vit, equip_vit, total_vit = (vit_values["base"], vit_values["job"], vit_values["equip"], vit_values["total"])
    base_int, job_int, equip_int, total_int = (int_values["base"], int_values["job"], int_values["equip"], int_values["total"])
    base_dex, job_dex, equip_dex, total_dex = (dex_values["base"], dex_values["job"], dex_values["equip"], dex_values["total"])
    job_hpsp, wpasdp_data = stage20_load_job_status_tables(data_dir)

    # ===== 4轉職業 HP / SP 表（BaseLv 201~275） =====
    job_base_hp = 0
    job_base_sp = 0
    if 201 <= base_lv <= 275:
        row = job_hpsp.get(job_id, job_hpsp.get(str(job_id), {})) if isinstance(job_hpsp, dict) else {}
        if isinstance(row, dict):
            index = base_lv - 201
            hp_list = row.get("HP", []) or []
            sp_list = row.get("SP", []) or []
            if index < len(hp_list):
                job_base_hp = _stage20_int(hp_list[index])
            if index < len(sp_list):
                job_base_sp = _stage20_int(sp_list[index])

    # HP / SP 真正算式統一交給 共用 helper。
    hpsp = stage20_calculate_hpsp_values(
        job_base_hp=job_base_hp,
        job_base_sp=job_base_sp,
        base_vit=base_vit,
        base_int=base_int,
        total_vit=total_vit,
        total_int=total_int,
        hp_flat=_stage20_sum_effect(effect_dict, "MHP", ""),
        sp_flat=_stage20_sum_effect(effect_dict, "MSP", ""),
        hp_percent_bonus=_stage20_sum_effect(effect_dict, "MHP%", "%"),
        sp_percent_bonus=_stage20_sum_effect(effect_dict, "MSP%", "%"),
        mhp_input=settings.get("mhp_input", get_values.get(200, get_values.get("200", 0))),
        msp_input=settings.get("msp_input", get_values.get(202, get_values.get("202", 0))),
        use_logout_values=bool(settings.get("use_logout_hpsp", False)),
        hp_current_percent=settings.get("hp_percent", 100),
        sp_current_percent=settings.get("sp_percent", 100),
    )

    weapon_type_map = _stage20_context_map(context, "weapon_type_map")
    armor_weapon_map = _stage20_context_map(context, "armor_weapon_map")
    if not armor_weapon_map:
        armor_weapon_map = _stage20_context_map(context, "global_armor_weapon_map")

    # 主手 / 副手武器類型與盾牌狀態，沿用 Desktop slot：4=右手、3=左手。
    right_weapon_type = _stage20_map_get(weapon_type_map, 4, 0)
    left_weapon_type = _stage20_map_get(weapon_type_map, 3, 0)
    left_kind = _stage20_map_get(armor_weapon_map, 3, "")
    has_shield = left_kind == "armor"
    dual_wield = left_kind in ("Mweapon", "Rweapon")

    # ASPD 類別1 / 類別2：攻擊後延遲減少在公式中以負 rate 傳入。
    cat1_rate = -_stage20_sum_effect(effect_dict, "(2轉以下)攻擊後延遲", "%")
    cat1_flat = _stage20_sum_effect(effect_dict, "(2轉以下)ASPD", "")
    cat2_rate = -_stage20_sum_effect(effect_dict, "攻擊後延遲", "%")
    cat2_flat = _stage20_sum_effect(effect_dict, "ASPD", "")

    try:
        if dual_wield:
            aspd_value = stage20_calc_aspd(
                wpasdp_data,
                job_id=job_id,
                agi=total_agi,
                dex=total_dex,
                dual_wield=True,
                right_weapon_type=right_weapon_type,
                left_weapon_type=left_weapon_type,
                cat1_rate=cat1_rate,
                cat1_flat=cat1_flat,
                cat2_rate=cat2_rate,
                cat2_flat=cat2_flat,
            )
        else:
            aspd_value = stage20_calc_aspd(
                wpasdp_data,
                job_id=job_id,
                agi=total_agi,
                dex=total_dex,
                weapon_type=right_weapon_type,
                has_shield=has_shield,
                cat1_rate=cat1_rate,
                cat1_flat=cat1_flat,
                cat2_rate=cat2_rate,
                cat2_flat=cat2_flat,
            )
    except (TypeError, ValueError) as exc:
        aspd_value = str(exc)

    if isinstance(aspd_value, (int, float)):
        capped_int_aspd = min(193, int(aspd_value))
        denominator = 200 - capped_int_aspd
        attacks_per_second = 50 / denominator if denominator > 0 else None
        aspd = {
            "supported": True,
            "value": float(aspd_value),
            "attacks_per_second": attacks_per_second,
            "message": "",
            "mode": "dual" if dual_wield else "single",
            "has_shield": bool(has_shield),
            "right_weapon_type": _stage20_int(right_weapon_type),
            "left_weapon_type": _stage20_int(left_weapon_type),
            "cat1_rate": cat1_rate,
            "cat1_flat": cat1_flat,
            "cat2_rate": cat2_rate,
            "cat2_flat": cat2_flat,
        }
    else:
        aspd = {
            "supported": False,
            "value": None,
            "attacks_per_second": None,
            "message": str(aspd_value),
            "mode": "dual" if dual_wield else "single",
            "has_shield": bool(has_shield),
            "right_weapon_type": _stage20_int(right_weapon_type),
            "left_weapon_type": _stage20_int(left_weapon_type),
            "cat1_rate": cat1_rate,
            "cat1_flat": cat1_flat,
            "cat2_rate": cat2_rate,
            "cat2_flat": cat2_flat,
        }

    no_cast = stage25_calculate_no_cast_from_effects(
        base_dex=base_dex,
        base_int=base_int,
        job_bonus=job_bonus,
        effect_dict=effect_dict,
    )

    return {
        "hpsp": hpsp,
        "aspd": aspd,
        "no_cast": no_cast,
        "stats": {
            "base_agi": base_agi, "job_agi": job_agi, "equip_agi": equip_agi, "total_agi": total_agi,
            "base_dex": base_dex, "job_dex": job_dex, "equip_dex": equip_dex, "total_dex": total_dex,
            "base_vit": base_vit, "job_vit": job_vit, "equip_vit": equip_vit, "total_vit": total_vit,
            "base_int": base_int, "job_int": job_int, "equip_int": equip_int, "total_int": total_int,
        },
        "job": {
            "job_id": job_id,
            "base_lv": base_lv,
            "name": str(job_info.get("name", "") or ""),
            "hpsp_table_available": bool(job_base_hp or job_base_sp),
            "mhp_msp_display": bool(job_info.get("MHP_MSP", False)),
            "hpsp_input_widget": bool(job_info.get("HP_SP_widget", False)),
        },
    }

# === STAGE 21 裝備搜尋與雙手裝備核心 ===
# Desktop 與 Web 共用、不依賴 Qt / FastAPI 的 helper。

STAGE21_BLOCK_LEFT_WEAPON_TYPES = frozenset({
    3,   # 雙手劍
    5,   # 雙手矛
    7,   # 雙手斧
    11,  # 弓
    16,  # 拳刃
    17,  # 左輪手槍
    18,  # 來福槍
    19,  # 格林機關槍
    20,  # 霰彈槍
    21,  # 榴彈槍
    22,  # 風魔飛鏢
    23,  # 雙手杖
})


def _stage21_data_get(mapping, key, default=None):
    if not isinstance(mapping, dict):
        return default
    if key in mapping:
        return mapping[key]
    text_key = str(key)
    if text_key in mapping:
        return mapping[text_key]
    return default


def _stage21_description_lines(value):
    if isinstance(value, (list, tuple)):
        return [
            str(row)
            for row in value
            if str(row).strip()
        ]
    if value is None:
        return []
    text = str(value)
    return [text] if text.strip() else []


def stage21_extract_equipment_meta(block_text):
    """從單一裝備 block 抽出武器 Type / Stat metadata。

    Desktop stat 配置：
      Mweapon：Stat[1] = 武器類型
      Rweapon：Stat[0] = 武器類型
    """
    import re

    block = str(block_text or "")

    type_match = re.search(
        r'\bType\s*=\s*["\']([^"\']+)["\']',
        block,
    )
    equip_type = (
        type_match.group(1).strip()
        if type_match
        else ""
    )

    stat_match = re.search(
        r"\bStat\s*=\s*\{([^}]*)\}",
        block,
        re.S,
    )
    stat_values = []
    if stat_match:
        stat_values = [
            int(value)
            for value in re.findall(
                r"[-+]?\d+",
                stat_match.group(1),
            )
        ]

    weapon_type = None
    if equip_type == "Mweapon" and len(stat_values) > 1:
        weapon_type = int(stat_values[1])
    elif equip_type == "Rweapon" and stat_values:
        weapon_type = int(stat_values[0])

    return {
        "equip_type": equip_type,
        "weapon_type": weapon_type,
        "blocks_left_hand": (
            weapon_type in STAGE21_BLOCK_LEFT_WEAPON_TYPES
            if weapon_type is not None
            else False
        ),
    }


def stage21_build_equipment_item_summary(
    item_id,
    item_data,
    equipment_block,
):
    item_data = (
        item_data
        if isinstance(item_data, dict)
        else {}
    )
    item_id = int(item_id)

    name = str(
        item_data.get("name")
        or item_data.get("base_name")
        or f"[{item_id}]"
    )
    base_name = str(
        item_data.get("base_name")
        or name
    )
    descriptions = _stage21_description_lines(
        item_data.get("description", [])
    )
    meta = stage21_extract_equipment_meta(
        equipment_block
    )

    try:
        slot = int(item_data.get("slot", 0) or 0)
    except (TypeError, ValueError):
        slot = 0

    return {
        "item_id": item_id,
        "name": name,
        "base_name": base_name,
        "kr_name": str(
            item_data.get("kr_name", "") or ""
        ),
        "slot": slot,
        "is_equipment": True,
        "description_preview": (
            " ".join(descriptions)[:320]
        ),
        "equip_type": meta["equip_type"],
        "weapon_type": meta["weapon_type"],
        "blocks_left_hand": bool(
            meta["blocks_left_hand"]
        ),
    }


def stage21_search_equipment_items(
    parsed_items,
    equipment_data,
    query,
    *,
    offset=0,
    limit=50,
):
    """與目前 Desktop update_combobox() 語意一致。

    - query.strip().split()
    - 可搜尋文字 = Item ID + 名稱 + 合併後描述
    - 每個關鍵字都必須符合（AND）
    - 只保留存在於 equipment_data 的 ID
    - 結果依 Item ID 排序
    """
    keywords = str(query or "").strip().split()

    try:
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        offset = 0

    try:
        limit = max(1, min(500, int(limit)))
    except (TypeError, ValueError):
        limit = 50

    matches = []

    normalized_ids = []
    for raw_id in (parsed_items or {}).keys():
        try:
            normalized_ids.append(int(raw_id))
        except (TypeError, ValueError):
            continue

    for item_id in sorted(set(normalized_ids)):
        item = _stage21_data_get(
            parsed_items,
            item_id,
            {},
        )
        block = _stage21_data_get(
            equipment_data,
            item_id,
            None,
        )

        # 完整保留 Desktop 行為：只接受 equipment_data 內的 ID。
        if block is None:
            continue

        if not isinstance(item, dict):
            continue

        descriptions = _stage21_description_lines(
            item.get("description", [])
        )
        searchable_text = " ".join([
            str(item_id),
            str(item.get("name", "") or ""),
            " ".join(descriptions),
        ])

        if not all(
            keyword in searchable_text
            for keyword in keywords
        ):
            continue

        matches.append(
            stage21_build_equipment_item_summary(
                item_id,
                item,
                block,
            )
        )

    total = len(matches)
    return {
        "query": str(query or "").strip(),
        "keywords": keywords,
        "match_mode": "all",
        "search_fields": [
            "item_id",
            "name",
            "description",
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": matches[offset:offset + limit],
    }


def stage21_get_equipment_item(
    parsed_items,
    equipment_data,
    item_id,
):
    try:
        item_id = int(item_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("item_id 必須是整數") from exc

    item = _stage21_data_get(
        parsed_items,
        item_id,
        None,
    )
    block = _stage21_data_get(
        equipment_data,
        item_id,
        None,
    )

    if not isinstance(item, dict) or block is None:
        return None

    return stage21_build_equipment_item_summary(
        item_id,
        item,
        block,
    )

# === STAGE 21.9 備註編輯器核心 ===
# 由 apply_stage21_9.py 根據使用者目前的 Desktop 原始碼產生。
# 這裡只有資料；Web runtime 不會匯入 ItemSearchApp.py 或 PySide6。
STAGE21_9_FUNCTION_DEFS = {'EnableSkill': {'desc': '可使用技能', 'args': [{'name': '技能', 'map': 'skill_map'}, {'name': '等級', 'type': 'value'}]},
 'AddExtParam': {'desc': '增加基礎能力',
                 'args': [{'name': '無意義', 'map': '1'},
                          {'name': '能力', 'map': 'effect_map'},
                          {'name': '數值', 'type': 'value'}]},
 'SubExtParam': {'desc': '減少基礎能力',
                 'args': [{'name': '無意義', 'map': '1'},
                          {'name': '能力', 'map': 'effect_map'},
                          {'name': '數值', 'type': 'value'}]},
 'AddSpellDelay': {'desc': '增加技能後延遲', 'args': [{'name': '數值%', 'type': 'value'}]},
 'SubSpellDelay': {'desc': '減少技能後延遲', 'args': [{'name': '數值%', 'type': 'value'}]},
 'SubSpellCastTime': {'desc': '減少變動詠唱時間', 'args': [{'name': '數值%', 'type': 'value'}]},
 'AddSpellCastTime': {'desc': '增加變動詠唱時間', 'args': [{'name': '數值%', 'type': 'value'}]},
 'SubSFCTEquipAmount': {'desc': '減少固定詠唱時間',
                        'args': [{'name': '無意義', 'map': '0'},
                                 {'name': '數值ms', 'type': 'value'},
                                 {'name': '無意義', 'map': '0'}]},
 'AddSFCTEquipAmount': {'desc': '增加固定詠唱時間',
                        'args': [{'name': '無意義', 'map': '0'},
                                 {'name': '數值ms', 'type': 'value'},
                                 {'name': '無意義', 'map': '0'}]},
 'AddDamage_SKID': {'desc': '增加技能傷害(裝備段)',
                    'args': [{'name': '目標', 'map': 'unit_map'},
                             {'name': '技能', 'map': 'skill_map'},
                             {'name': '數值%', 'type': 'value'}]},
 'SubDamage_SKID': {'desc': '減少技能傷害(裝備段)',
                    'args': [{'name': '目標', 'map': 'unit_map'},
                             {'name': '技能', 'map': 'skill_map'},
                             {'name': '數值%', 'type': 'value'}]},
 'AddDamage_passive_SKID': {'desc': '增加技能傷害(技能段)',
                            'args': [{'name': '目標', 'map': 'unit_map'},
                                     {'name': '技能', 'map': 'skill_map'},
                                     {'name': '數值%', 'type': 'value'}]},
 'SubDamage_passive_SKID': {'desc': '減少技能傷害(技能段)',
                            'args': [{'name': '目標', 'map': 'unit_map'},
                                     {'name': '技能', 'map': 'skill_map'},
                                     {'name': '數值%', 'type': 'value'}]},
 'AddSkillDelay': {'desc': '增加技能固定冷卻', 'args': [{'name': '技能', 'map': 'skill_map'}, {'name': '數值%', 'type': 'value'}]},
 'SubSkillDelay': {'desc': '減少技能固定冷卻', 'args': [{'name': '技能', 'map': 'skill_map'}, {'name': '數值%', 'type': 'value'}]},
 '就說通用了你還產生！': {'desc': '----以上通用分隔線----', 'args': []},
 '就說以下魔法了你還產生！': {'desc': '--以下魔法增減分隔線--', 'args': []},
 'AddSkillMDamage': {'desc': '增加屬性魔法傷害',
                     'args': [{'name': '屬性', 'map': 'element_map'}, {'name': '數值%', 'type': 'value'}]},
 'SubSkillMDamage': {'desc': '減少屬性魔法傷害',
                     'args': [{'name': '屬性', 'map': 'element_map'}, {'name': '數值%', 'type': 'value'}]},
 'AddMDamage_Size': {'desc': '增加體型魔法傷害',
                     'args': [{'name': '目標', 'map': 'unit_map'},
                              {'name': '體型', 'map': 'size_map'},
                              {'name': '數值%', 'type': 'value'}]},
 'SubMDamage_Size': {'desc': '減少體型魔法傷害',
                     'args': [{'name': '目標', 'map': 'unit_map'},
                              {'name': '體型', 'map': 'size_map'},
                              {'name': '數值%', 'type': 'value'}]},
 'AddMdamage_Race': {'desc': '增加種族魔法傷害', 'args': [{'name': '種族', 'map': 'race_map'}, {'name': '數值%', 'type': 'value'}]},
 'SubMdamage_Race': {'desc': '減少種族魔法傷害', 'args': [{'name': '種族', 'map': 'race_map'}, {'name': '數值%', 'type': 'value'}]},
 'AddMDamage_Property': {'desc': '增加屬性對象魔法傷害',
                         'args': [{'name': '目標', 'map': 'unit_map'},
                                  {'name': '屬性', 'map': 'element_map'},
                                  {'name': '數值%', 'type': 'value'}]},
 'SubMDamage_Property': {'desc': '減少屬性對象魔法傷害',
                         'args': [{'name': '目標', 'map': 'unit_map'},
                                  {'name': '屬性', 'map': 'element_map'},
                                  {'name': '數值%', 'type': 'value'}]},
 'AddMdamage_Class': {'desc': '增加階級魔法傷害',
                      'args': [{'name': '階級', 'map': 'class_map'}, {'name': '數值%', 'type': 'value'}]},
 'SubMdamage_Class': {'desc': '減少階級魔法傷害',
                      'args': [{'name': '階級', 'map': 'class_map'}, {'name': '數值%', 'type': 'value'}]},
 'SetIgnoreMdefClass': {'desc': '無視階級魔法防禦',
                        'args': [{'name': '階級', 'map': 'class_map'}, {'name': '數值%', 'type': 'value'}]},
 'SetIgnoreMdefRace': {'desc': '無視種族魔法防禦',
                       'args': [{'name': '種族', 'map': 'race_map'}, {'name': '數值%', 'type': 'value'}]},
 'AddIgnore_MRES_RacePercent': {'desc': '無視種族魔法抗性',
                                'args': [{'name': '種族', 'map': 'race_map'}, {'name': '數值%', 'type': 'value'}]},
 'MonsterMAtkPercent': {'desc': '增加特定魔物魔法傷害', 'args': [{'name': '數值%', 'type': 'value'}]},
 'SubMonsterMAtkPercent': {'desc': '減少特定魔物魔法傷害', 'args': [{'name': '數值%', 'type': 'value'}]},
 '就說以上魔法了你還產生！': {'desc': '--以上魔法增減分隔線--', 'args': []},
 '就說以下物理了你還產生！': {'desc': '--以下物理增減分隔線--', 'args': []},
 'WeaponMasteryATK': {'desc': '修煉ATK', 'args': [{'name': '數值%', 'type': 'value'}]},
 'AddGuideAttack': {'desc': '誘導攻擊機率', 'args': [{'name': '數值%', 'type': 'value'}]},
 'AddDamage_HIT': {'desc': '增加物理命中傷害', 'args': [{'name': '目標', 'map': 'unit_map'}, {'name': '數值%', 'type': 'value'}]},
 'SubDamage_HIT': {'desc': '減少物理命中傷害', 'args': [{'name': '目標', 'map': 'unit_map'}, {'name': '數值%', 'type': 'value'}]},
 'AddMeleeAttackDamage': {'desc': '增加近距離物理傷害',
                          'args': [{'name': '目標', 'map': 'unit_map'}, {'name': '數值%', 'type': 'value'}]},
 'SubMeleeAttackDamage': {'desc': '減少近距離物理傷害',
                          'args': [{'name': '目標', 'map': 'unit_map'}, {'name': '數值%', 'type': 'value'}]},
 'AddRangeAttackDamage': {'desc': '增加遠距離物理傷害',
                          'args': [{'name': '目標', 'map': 'unit_map'}, {'name': '數值%', 'type': 'value'}]},
 'SubRangeAttackDamage': {'desc': '減少遠距離物理傷害',
                          'args': [{'name': '目標', 'map': 'unit_map'}, {'name': '數值%', 'type': 'value'}]},
 'AddDamage_CRI': {'desc': '增加爆擊傷害', 'args': [{'name': '目標', 'map': 'unit_map'}, {'name': '數值%', 'type': 'value'}]},
 'SubDamage_CRI': {'desc': '減少爆擊傷害', 'args': [{'name': '目標', 'map': 'unit_map'}, {'name': '數值%', 'type': 'value'}]},
 'AddDamage_Size': {'desc': '增加體型物理傷害',
                    'args': [{'name': '目標', 'map': 'unit_map'},
                             {'name': '體型', 'map': 'size_map'},
                             {'name': '數值%', 'type': 'value'}]},
 'SubDamage_Size': {'desc': '減少體型物理傷害',
                    'args': [{'name': '目標', 'map': 'unit_map'},
                             {'name': '體型', 'map': 'size_map'},
                             {'name': '數值%', 'type': 'value'}]},
 'RaceAddDamage': {'desc': '增加種族物理傷害', 'args': [{'name': '種族', 'map': 'race_map'}, {'name': '數值%', 'type': 'value'}]},
 'RaceSubDamage': {'desc': '減少種族物理傷害', 'args': [{'name': '種族', 'map': 'race_map'}, {'name': '數值%', 'type': 'value'}]},
 'AddDamage_Property': {'desc': '增加屬性對象物理傷害',
                        'args': [{'name': '目標', 'map': 'unit_map'},
                                 {'name': '屬性', 'map': 'element_map'},
                                 {'name': '數值%', 'type': 'value'}]},
 'SubDamage_Property': {'desc': '減少屬性對象物理傷害',
                        'args': [{'name': '目標', 'map': 'unit_map'},
                                 {'name': '屬性', 'map': 'element_map'},
                                 {'name': '數值%', 'type': 'value'}]},
 'ClassAddDamage': {'desc': '增加階級的物理傷害',
                    'args': [{'name': '階級', 'map': 'class_map'},
                             {'name': '目標', 'map': 'unit_map'},
                             {'name': '數值%', 'type': 'value'}]},
 'ClassSubDamage': {'desc': '減少階級的物理傷害',
                    'args': [{'name': '階級', 'map': 'class_map'},
                             {'name': '目標', 'map': 'unit_map'},
                             {'name': '數值%', 'type': 'value'}]},
 'SetIgnoreDefClass_Percent': {'desc': '無視階級物理防禦',
                               'args': [{'name': '階級', 'map': 'class_map'}, {'name': '數值%', 'type': 'value'}]},
 'SetIgnoreDefRace_Percent': {'desc': '無視種族物理防禦',
                              'args': [{'name': '種族', 'map': 'race_map'}, {'name': '數值%', 'type': 'value'}]},
 'AddIgnore_RES_RacePercent': {'desc': '無視種族物理抗性',
                               'args': [{'name': '種族', 'map': 'race_map'}, {'name': '數值%', 'type': 'value'}]},
 'MonsterAtkPercent': {'desc': '增加特定魔物物理傷害', 'args': [{'name': '數值%', 'type': 'value'}]},
 'SubMonsterAtkPercent': {'desc': '減少特定魔物物理傷害', 'args': [{'name': '數值%', 'type': 'value'}]},
 '': {'desc': '--以下取得角色能力--', 'args': []},
 'get': {'desc': '取得基礎能力', 'args': [{'name': '', 'type': 'var_select', 'map': 'stat_fields'}]},
 'GetRefineLevel': {'desc': '取得裝備精煉', 'args': [{'name': '', 'type': 'var_select', 'map': 'equip_sitetype'}]},
 'GetEquipGradeLevel': {'desc': '取得裝備階級', 'args': [{'name': '', 'type': 'var_select', 'map': 'equip_sitetype'}]},
 'GetEquipArmorLv': {'desc': '取得防具等級', 'args': [{'name': '', 'type': 'var_select', 'map': 'equip_sitetype'}]},
 'GetEquipWeaponLv': {'desc': '取得武器等級', 'args': [{'name': '', 'type': 'var_select', 'map': 'equip_sitetype'}]},
 'AddHealValue': {'desc': '增加治癒量', 'args': [{'name': '數值%', 'type': 'value'}]},
 'SubHealValue': {'desc': '減少治癒量', 'args': [{'name': '數值%', 'type': 'value'}]},
 'AddHealModifyPercent': {'desc': '增加被治癒量', 'args': [{'name': '數值%', 'type': 'value'}]},
 'SubHealModifyPercent': {'desc': '減少被治癒量', 'args': [{'name': '數值%', 'type': 'value'}]},
 'AddHPdrain': {'desc': '增加HP吸收', 'args': [{'name': '機率%', 'type': 'value'}, {'name': '吸收量%', 'type': 'value'}]},
 'SubHPdrain': {'desc': '減少HP吸收', 'args': [{'name': '機率%', 'type': 'value'}, {'name': '吸收量%', 'type': 'value'}]},
 'AddSPdrain': {'desc': '增加SP吸收', 'args': [{'name': '機率%', 'type': 'value'}, {'name': '吸收量%', 'type': 'value'}]},
 'SubSPdrain': {'desc': '減少SP吸收', 'args': [{'name': '機率%', 'type': 'value'}, {'name': '吸收量%', 'type': 'value'}]},
 'AddSPconsumption': {'desc': '增加SP消耗', 'args': [{'name': '數值%', 'type': 'value'}]},
 'SubSPconsumption': {'desc': '減少SP消耗', 'args': [{'name': '數值%', 'type': 'value'}]},
 'addspconsumption': {'desc': '增加指定技能SP消耗%',
                      'args': [{'name': '數值%', 'type': 'value'}, {'name': '技能', 'map': 'skill_map'}]},
 'subspconsumption': {'desc': '減少指定技能SP消耗%',
                      'args': [{'name': '數值%', 'type': 'value'}, {'name': '技能', 'map': 'skill_map'}]},
 'AddSkillSP': {'desc': '增加指定技能SP消耗', 'args': [{'name': '技能', 'map': 'skill_map'}, {'name': '數值', 'type': 'value'}]},
 'SubSkillSP': {'desc': '減少指定技能SP消耗', 'args': [{'name': '技能', 'map': 'skill_map'}, {'name': '數值', 'type': 'value'}]},
 'AddAttrTolerace': {'desc': '增加屬性攻擊抗性',
                     'args': [{'name': '屬性', 'map': 'element_map'}, {'name': '數值%', 'type': 'value'}]},
 'SubAttrTolerace': {'desc': '減少屬性攻擊抗性',
                     'args': [{'name': '屬性', 'map': 'element_map'}, {'name': '數值%', 'type': 'value'}]},
 'addattrtolerace': {'desc': '增加屬性物理攻擊抗性',
                     'args': [{'name': '屬性', 'map': 'element_map'}, {'name': '數值%', 'type': 'value'}]},
 'subattrtolerace': {'desc': '減少屬性物理攻擊抗性',
                     'args': [{'name': '屬性', 'map': 'element_map'}, {'name': '數值%', 'type': 'value'}]},
 'AddCRIPercent_Race': {'desc': '增加對種族CRI',
                        'args': [{'name': '種族', 'map': 'race_map'}, {'name': '數值%', 'type': 'value'}]},
 'SubCRIPercent_Race': {'desc': '減少對種族CRI',
                        'args': [{'name': '種族', 'map': 'race_map'}, {'name': '數值%', 'type': 'value'}]},
 'AddMeleeAttackReflect': {'desc': '增加近距離物理反射', 'args': [{'name': '數值%', 'type': 'value'}]},
 'SubMeleeAttackReflect': {'desc': '減少近距離物理反射', 'args': [{'name': '數值%', 'type': 'value'}]},
 'AddReflectMagic': {'desc': '增加魔法反射', 'args': [{'name': '數值%', 'type': 'value'}]},
 'SubReflectMagic': {'desc': '減少魔法反射', 'args': [{'name': '數值%', 'type': 'value'}]},
 'AddReflectTolerace': {'desc': '增加反射傷害耐性', 'args': [{'name': '數值%', 'type': 'value'}]},
 'SubReflectTolerace': {'desc': '減少反射傷害耐性', 'args': [{'name': '數值%', 'type': 'value'}]}}
STAGE21_9_FUNCTION_MAPS = {'stat_fields': {11: 'BaseLv',
                 12: 'JobLv',
                 19: 'JOB',
                 200: 'MHP',
                 202: 'MSP',
                 32: 'STR',
                 33: 'AGI',
                 34: 'VIT',
                 35: 'INT',
                 36: 'DEX',
                 37: 'LUK',
                 255: 'POW',
                 256: 'STA',
                 257: 'WIS',
                 258: 'SPL',
                 259: 'CON',
                 260: 'CRT',
                 263: '石碑開啟格數',
                 264: '石碑精煉'},
 'equip_sitetype': {10: '頭上',
                    11: '頭中',
                    12: '頭下',
                    2: '鎧甲',
                    4: '右手(武器)',
                    3: '左手(盾牌)',
                    5: '披肩',
                    6: '鞋子',
                    7: '飾品右',
                    8: '飾品左',
                    30: '影子鎧甲',
                    31: '影子手套',
                    32: '影子盾牌',
                    33: '影子鞋子',
                    34: '影子耳環右',
                    35: '影子墬子左'},
 'effect_map': {41: 'ATK',
                45: 'DEF',
                47: 'MDEF',
                49: 'HIT',
                50: 'FLEE',
                51: '完全迴避',
                52: 'CRI',
                54: 'ASPD',
                103: 'STR',
                104: 'AGI',
                105: 'VIT',
                106: 'INT',
                107: 'DEX',
                108: 'LUK',
                109: 'MHP',
                110: 'MSP',
                111: 'MHP%',
                112: 'MSP%',
                113: 'HP自然恢復%',
                114: 'SP自然恢復%',
                140: 'MATK%',
                167: '攻擊後延遲',
                200: 'MATK',
                207: 'ATK%',
                234: 'POW',
                235: 'STA',
                236: 'WIS',
                237: 'SPL',
                238: 'CON',
                239: 'CRT',
                242: 'P.ATK',
                243: 'S.MATK',
                244: 'RES',
                245: 'MRES',
                253: 'C.RATE',
                254: 'H.PLUS',
                301: '(2轉以下)攻擊後延遲',
                302: '(2轉以下)ASPD'},
 'element_map': {0: '無屬性',
                 1: '水屬性',
                 2: '地屬性',
                 3: '火屬性',
                 4: '風屬性',
                 5: '毒屬性',
                 6: '聖屬性',
                 7: '暗屬性',
                 8: '念屬性',
                 9: '不死屬性',
                 10: '全屬性',
                 999: '（不使用）'},
 'size_map': {0: '小型', 1: '中型', 2: '大型'},
 'race_map': {0: '無形',
              1: '不死',
              2: '動物',
              3: '植物',
              4: '昆蟲',
              5: '魚貝',
              6: '惡魔',
              7: '人形',
              8: '天使',
              9: '龍族',
              10: '玩家（人類）',
              11: '玩家（貓族）',
              9999: '全種族'},
 'unit_map': {0: '玩家', 1: '魔物'},
 'class_map': {0: '一般', 1: '首領', 2: '監護人'},
 'weapon_type_map': {0: '空手',
                     1: '短劍',
                     2: '單手劍',
                     3: '雙手劍',
                     4: '單手矛',
                     5: '雙手矛',
                     6: '單手斧',
                     7: '雙手斧',
                     8: '鈍器',
                     10: '單手仗',
                     12: '拳套',
                     13: '樂器',
                     14: '鞭子',
                     15: '書',
                     16: '拳刃',
                     23: '雙手仗',
                     11: '弓',
                     17: '左輪手槍',
                     18: '來福槍',
                     19: '格林機關槍',
                     20: '霰彈槍',
                     21: '榴彈槍',
                     22: '風魔飛鏢'}}
STAGE21_9_CONDITION_VALUE_DEFS = {'refine_current': {'label': '當前裝備精煉值', 'syntax': 'GetRefineLevel(GetLocation())', 'keywords': '精煉 refine'},
 'grade_current': {'label': '當前裝備階級', 'syntax': 'GetEquipGradeLevel(GetLocation())', 'keywords': '階級 grade'},
 'armor_lv_current': {'label': '當前防具等級', 'syntax': 'GetEquipArmorLv(GetLocation())', 'keywords': '防具等級 armor'},
 'weapon_lv_current': {'label': '當前武器等級', 'syntax': 'GetEquipWeaponLv(GetLocation())', 'keywords': '武器等級 weapon'},
 'weapon_class_current': {'label': '當前武器類型',
                          'syntax': 'GetWeaponClass(GetLocation())',
                          'keywords': '武器類型 weapon class'},
 'pet_relationship': {'label': '寵物親密度', 'syntax': 'GetPetRelationship()', 'keywords': '寵物 親密度 pet'},
 'base_lv': {'label': 'BaseLv', 'syntax': 'get(11)', 'keywords': 'BaseLv 基礎等級'},
 'job_lv': {'label': 'JobLv', 'syntax': 'get(12)', 'keywords': 'JobLv 職業等級'},
 'job': {'label': 'JOB', 'syntax': 'get(19)', 'keywords': '職業'},
 'str': {'label': 'STR', 'syntax': 'get(32)', 'keywords': 'STR'},
 'agi': {'label': 'AGI', 'syntax': 'get(33)', 'keywords': 'AGI'},
 'vit': {'label': 'VIT', 'syntax': 'get(34)', 'keywords': 'VIT'},
 'int': {'label': 'INT', 'syntax': 'get(35)', 'keywords': 'INT'},
 'dex': {'label': 'DEX', 'syntax': 'get(36)', 'keywords': 'DEX'},
 'luk': {'label': 'LUK', 'syntax': 'get(37)', 'keywords': 'LUK'},
 'pow': {'label': 'POW', 'syntax': 'get(255)', 'keywords': 'POW'},
 'sta': {'label': 'STA', 'syntax': 'get(256)', 'keywords': 'STA'},
 'wis': {'label': 'WIS', 'syntax': 'get(257)', 'keywords': 'WIS'},
 'spl': {'label': 'SPL', 'syntax': 'get(258)', 'keywords': 'SPL'},
 'con': {'label': 'CON', 'syntax': 'get(259)', 'keywords': 'CON'},
 'crt': {'label': 'CRT', 'syntax': 'get(260)', 'keywords': 'CRT'}}
STAGE21_9_CONDITION_OPERATORS = {'==': '等於', '~=': '不等於', '>=': '大於等於', '<=': '小於等於', '>': '大於', '<': '小於'}
STAGE21_9_CONTROL_FLOW_DEFS = {'if': {'display': 'if 條件 then', 'desc': '新增 IF 條件', 'template': 'if 條件 then\n    \nend'},
 'elseif': {'display': 'elseif 條件 then', 'desc': '新增 ELSEIF 條件', 'template': 'elseif 條件 then'},
 'else': {'display': 'else', 'desc': '新增 ELSE', 'template': 'else'},
 'end': {'display': 'end', 'desc': '結束條件', 'template': 'end'}}


def _stage21_9_function_arg_meta(arg, index):
    arg = dict(arg or {})
    name = str(arg.get("name", "") or "")
    map_name = str(arg.get("map", "") or "")
    type_name = str(arg.get("type", "") or "")

    fixed_value = None

    # 完整保留 Desktop FunctionSyntaxTextEdit 的 placeholder / 固定值規則。
    if map_name.isdigit():
        fixed_value = map_name
        placeholder = map_name
    elif name == "目標" and map_name == "unit_map":
        fixed_value = "1"
        placeholder = "1"
    elif type_name == "value":
        placeholder = "n"
    elif type_name == "var_select":
        placeholder = name or "變數"
    elif map_name:
        placeholder = name or map_name or "參數"
    else:
        placeholder = name or "參數"

    return {
        "index": int(index),
        "name": name,
        "map": map_name,
        "type": type_name,
        "fixed_value": fixed_value,
        "placeholder": placeholder,
    }


def stage21_9_note_function_catalog(query=""):
    query_text = str(query or "").strip().lower()
    rows = []

    for name, spec in STAGE21_9_FUNCTION_DEFS.items():
        desc = str(spec.get("desc", "") or "")
        args = [
            _stage21_9_function_arg_meta(arg, index)
            for index, arg in enumerate(spec.get("args", []) or [])
        ]

        separator = bool(
            str(name).startswith("就說")
            or "分隔線" in desc
        )

        syntax = (
            f"{name}("
            + ", ".join(arg["placeholder"] for arg in args)
            + ")"
        )

        haystack = " ".join(
            [
                str(name),
                desc,
                syntax,
                *[str(arg.get("name", "")) for arg in args],
            ]
        ).lower()

        if query_text and query_text not in haystack:
            continue

        rows.append(
            {
                "name": str(name),
                "desc": desc,
                "syntax": syntax,
                "separator": separator,
                "args": args,
            }
        )

    condition_values = [
        {
            "key": str(key),
            "label": str(spec.get("label", key)),
            "syntax": str(spec.get("syntax", "")),
            "keywords": str(spec.get("keywords", "")),
        }
        for key, spec in STAGE21_9_CONDITION_VALUE_DEFS.items()
    ]

    condition_operators = [
        {
            "value": str(value),
            "label": str(label),
        }
        for value, label in STAGE21_9_CONDITION_OPERATORS.items()
    ]

    control_flow = [
        {
            "key": str(key),
            "display": str(spec.get("display", key)),
            "desc": str(spec.get("desc", "")),
            "template": str(spec.get("template", key)),
        }
        for key, spec in STAGE21_9_CONTROL_FLOW_DEFS.items()
    ]

    return {
        "query": str(query or ""),
        "total": len(rows),
        "functions": rows,
        "condition_values": condition_values,
        "condition_operators": condition_operators,
        "control_flow": control_flow,
    }


def _stage21_9_map_label(value):
    if isinstance(value, dict):
        for key in (
            "Name",
            "name",
            "Label",
            "label",
            "Code",
            "code",
        ):
            candidate = value.get(key)
            if candidate not in (None, ""):
                return str(candidate)

    return str(value)


def stage21_9_note_function_map_options(
    map_name,
    *,
    dynamic_map=None,
    query="",
    limit=200,
):
    name = str(map_name or "")

    if name in {"skill_map", "skill_map_all"}:
        value_map = dynamic_map if isinstance(dynamic_map, dict) else {}
    else:
        value_map = STAGE21_9_FUNCTION_MAPS.get(name, {})

    if not isinstance(value_map, dict):
        value_map = {}

    items = list(value_map.items())

    if name in {"effect_map", "skill_map", "skill_map_all"}:
        items.sort(
            key=lambda item: _stage21_9_map_label(item[1]).lower()
        )

    query_text = str(query or "").strip().lower()
    matched = []

    for key, value in items:
        label = _stage21_9_map_label(value)
        haystack = f"{key} {label}".lower()

        if query_text and query_text not in haystack:
            continue

        matched.append(
            {
                "value": key,
                "label": label,
            }
        )

    try:
        limit_value = max(1, min(1000, int(limit)))
    except Exception:
        limit_value = 200

    return {
        "map_name": name,
        "query": str(query or ""),
        "total": len(matched),
        "options": matched[:limit_value],
    }


def stage21_9_parse_note_preview(
    block_text,
    refine_inputs,
    get_values,
    grade,
    unit_map,
    size_map,
    effect_map,
    *,
    current_location_slot=None,
    context=None,
    dependencies=None,
):
    """回傳 Desktop 風格的 note_ui 行，同時保持原始 Lua 不變。"""
    raw = str(block_text or "")

    if not raw.strip():
        return []

    if context is None:
        context = CalculationContext()

    context.bind_inputs(
        get_values=get_values or {},
        refine_inputs=refine_inputs or {},
        grade=grade,
    )

    if dependencies is None:
        dependencies = CoreDependencies()

    return parse_lua_effects_with_variables(
        raw,
        refine_inputs or {},
        get_values or {},
        grade,
        unit_map or {},
        size_map or {},
        effect_map or {},
        hide_unrecognized=False,
        hide_physical=False,
        hide_magical=False,
        current_location_slot=current_location_slot,
        context=context,
        dependencies=dependencies,
    )


# === STAGE 21.9 備註編輯器核心結束 ===

# === 核心去重階段 8：角色配裝模型 ===
# === 核心去重階段 16：角色配裝 Schema V2 ===
CHARACTER_BUILD_SCHEMA = "ROItemSearchApp.CharacterBuild"
CHARACTER_BUILD_VERSION = 2
CHARACTER_BUILD_META_KEY = "_roitemsearch_build"
CHARACTER_BUILD_COMBAT_KEY = "_roitemsearch_combat"


@dataclass
@dataclass
class CharacterBuild:
    """Desktop、Web 與比較工具共用、帶版本且不依賴 Qt 的配裝資料。

    Schema v2 把歷史上的平面專案欄位保留在 ``values``，並把暫時戰鬥控制項
    存在獨立 namespace 的 ``combat_state`` 物件。舊 v0 / v1 JSON 仍可讀取。
    ``to_legacy_dict()`` 刻意排除 v2 metadata / state，讓舊 Desktop 欄位套用程式繼續運作。
    """

    values: dict[str, Any] = field(default_factory=dict)
    combat_state: dict[str, Any] = field(default_factory=dict)
    schema: str = CHARACTER_BUILD_SCHEMA
    version: int = CHARACTER_BUILD_VERSION
    source_version: int = 0

    @classmethod
    def from_dict(cls, payload: Any) -> "CharacterBuild":
        if isinstance(payload, cls):
            return cls(
                values=dict(payload.values),
                combat_state=dict(payload.combat_state),
                schema=payload.schema,
                version=CHARACTER_BUILD_VERSION,
                source_version=payload.source_version,
            )
        if not isinstance(payload, dict):
            raise TypeError("CharacterBuild payload must be a mapping")

        values = dict(payload)
        metadata = values.pop(CHARACTER_BUILD_META_KEY, None)
        combat_state = values.pop(CHARACTER_BUILD_COMBAT_KEY, {})
        if combat_state is None:
            combat_state = {}
        if not isinstance(combat_state, dict):
            raise ValueError(f"{CHARACTER_BUILD_COMBAT_KEY} must be an object")

        source_version = 0
        schema = CHARACTER_BUILD_SCHEMA
        if metadata is not None:
            if not isinstance(metadata, dict):
                raise ValueError(f"{CHARACTER_BUILD_META_KEY} must be an object")
            schema = str(metadata.get("schema") or CHARACTER_BUILD_SCHEMA)
            if schema != CHARACTER_BUILD_SCHEMA:
                raise ValueError(f"Unsupported CharacterBuild schema: {schema}")
            try:
                source_version = int(metadata.get("version", 0) or 0)
            except (TypeError, ValueError) as exc:
                raise ValueError("Invalid CharacterBuild version") from exc
            if source_version < 0:
                raise ValueError("Invalid CharacterBuild version")
            if source_version > CHARACTER_BUILD_VERSION:
                raise ValueError(
                    f"CharacterBuild version {source_version} is newer than supported "
                    f"version {CHARACTER_BUILD_VERSION}"
                )

        return cls(
            values=values,
            combat_state=dict(combat_state),
            schema=CHARACTER_BUILD_SCHEMA,
            version=CHARACTER_BUILD_VERSION,
            source_version=source_version,
        )

    def with_combat_state(self, combat_state: Any) -> "CharacterBuild":
        if combat_state is None:
            combat_state = {}
        if not isinstance(combat_state, dict):
            raise TypeError("combat_state must be a mapping")
        return CharacterBuild(
            values=dict(self.values),
            combat_state=dict(combat_state),
            schema=CHARACTER_BUILD_SCHEMA,
            version=CHARACTER_BUILD_VERSION,
            source_version=self.source_version,
        )

    def merge_runtime_overrides(self, runtime_overrides: Any = None) -> dict[str, Any]:
        """合併已儲存的 v2 戰鬥狀態與呼叫端明確覆蓋值。

        明確傳入的 runtime 值優先。``special`` 逐 key 合併，因此呼叫端可以只覆蓋
        一個暫時 flag，而不會刪掉其他已儲存 flag。
        """
        merged = dict(self.combat_state or {})
        runtime = dict(runtime_overrides or {})
        saved_special = dict(merged.pop("special", {}) or {})
        runtime_special = runtime.pop("special", None)
        merged.update(runtime)
        if runtime_special is not None:
            saved_special.update(dict(runtime_special or {}))
        if saved_special:
            merged["special"] = saved_special
        return merged

    def to_legacy_dict(self) -> dict[str, Any]:
        """只回傳歷史上的平面專案 mapping。"""
        return dict(self.values)

    def to_dict(self, *, include_metadata: bool = True) -> dict[str, Any]:
        """使用 CharacterBuild schema v2 回傳可直接 JSON 化的 build payload。"""
        result = dict(self.values)
        result[CHARACTER_BUILD_COMBAT_KEY] = dict(self.combat_state or {})
        if include_metadata:
            result[CHARACTER_BUILD_META_KEY] = {
                "schema": CHARACTER_BUILD_SCHEMA,
                "version": CHARACTER_BUILD_VERSION,
            }
        return result


def normalize_character_build_payload(
    payload: Any,
    *,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """透過 CharacterBuild 正規化舊版或 Phase 8 專案資料。"""
    return CharacterBuild.from_dict(payload).to_dict(include_metadata=include_metadata)

# === 核心去重階段 12+13+14：角色配裝計算 + 防具精煉組合 ===

@dataclass(frozen=True)
class ArmorRefineSlotInput:
    """單一裝備位置、不依賴 Qt 的防具精煉輸入。"""

    part_name: str
    slot_id: int | str | None
    part_type: str = ""
    equipped: bool = False
    refine: int = 0
    armor_level: int = 0


@dataclass
class CharacterBuildCalculationResult:
    """Desktop、MultiCompare 與未來 Web 呼叫端共用的單一 Core 結果。"""

    build: CharacterBuild
    equipment_request: EquipmentEffectRequest
    effect_result: EquipmentEffectResult
    damage_result: Stage17DamageResult | None = None
    status: dict[str, Any] = field(default_factory=dict)
    stat_summary: dict[str, Any] = field(default_factory=dict)
    armor_bonus: dict[str, Any] = field(default_factory=dict)
    equipment_notes: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        damage = self.damage_result.to_dict() if self.damage_result is not None else None
        return {
            "build": self.build.to_dict(include_metadata=True),
            "damage": damage,
            "status": dict(self.status or {}),
            "stat_summary": dict(self.stat_summary or {}),
            "armor_bonus": dict(self.armor_bonus or {}),
            "equipment_notes": dict(self.equipment_notes or {}),
            "warnings": list(self.warnings or []),
            "equipment": {
                "combined_lines": list(getattr(self.effect_result, "combined_lines", []) or []),
                "combo_lines": list(getattr(self.effect_result, "combo_lines", []) or []),
                "triggered_combo_ids": list(getattr(self.effect_result, "triggered_combo_ids", []) or []),
                "warnings": list(getattr(self.effect_result, "warnings", []) or []),
            },
        }


def calculate_armor_set_refine_bonus(
    slots,
    *,
    exclude_parts=None,
    exclude_slots=None,
    exclude_types=None,
):
    """在不依賴 Qt / widget 的情況下加總防具精煉 DEF / RES。"""
    exclude_parts = set(exclude_parts or ())
    exclude_slots = set(exclude_slots or ())
    exclude_types = set(exclude_types or ())
    total_def = 0.0
    total_res = 0
    details = {}

    for raw in slots or ():
        if isinstance(raw, ArmorRefineSlotInput):
            item = raw
        elif isinstance(raw, dict):
            item = ArmorRefineSlotInput(**raw)
        else:
            raise TypeError("armor slots must be ArmorRefineSlotInput or dict")

        if item.part_name in exclude_parts:
            continue
        if item.slot_id in exclude_slots:
            continue
        if item.part_type in exclude_types:
            continue
        if not item.equipped:
            continue

        try:
            refine = int(item.refine)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{item.part_name} 的精煉值格式錯誤：{item.refine!r}") from exc
        try:
            armor_level = int(item.armor_level or 0)
        except (TypeError, ValueError):
            armor_level = 0
        if armor_level not in (1, 2):
            continue

        # Phase 1 是單件防具計算的唯一來源。
        bonus = calculate_armor_refine_bonus(refine, armor_level)
        total_def += float(bonus.get("DEF", 0) or 0)
        total_res += int(bonus.get("RES", 0) or 0)
        details[item.part_name] = {
            "slot": item.slot_id,
            "type": item.part_type,
            "refine": refine,
            "armor_level": armor_level,
            "DEF": bonus.get("DEF", 0),
            "RES": bonus.get("RES", 0),
        }

    return {"DEF": round(total_def, 1), "RES": int(total_res), "details": details}


def _character_build_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def _character_build_number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _character_build_text(value):
    return str(value or "").strip()


def _character_build_parse_buff_ids(raw_buff):
    if raw_buff is None:
        return set()
    if isinstance(raw_buff, (int, float)):
        return {str(int(raw_buff))}
    if isinstance(raw_buff, (list, tuple, set)):
        result = set()
        for value in raw_buff:
            text = _character_build_text(value)
            if text:
                result.add(text)
        return result
    text = _character_build_text(raw_buff)
    return {part.strip() for part in text.split(",") if part.strip()} if text else set()


def _character_build_exclusive_groups(raw):
    if not raw:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    try:
        return [str(part).strip() for part in raw if str(part).strip()]
    except TypeError:
        text = _character_build_text(raw)
        return [text] if text else []


def character_build_enabled_skill_names(raw_buff, skill_entries):
    """比照 Desktop apply_buff_to_skill_checkboxes()，包含互斥規則。"""
    target_ids = _character_build_parse_buff_ids(raw_buff)
    matched = []
    used_exclusive_groups = set()
    for name, info in (skill_entries or {}).items():
        info = info if isinstance(info, dict) else {}
        if not (_character_build_parse_buff_ids(info.get("buff")) & target_ids):
            continue
        groups = _character_build_exclusive_groups(info.get("exclusive"))
        if any(group in used_exclusive_groups for group in groups):
            continue
        matched.append(str(name))
        used_exclusive_groups.update(groups)
    return matched


def _character_build_resolve_job_id(raw_job, job_dict):
    if raw_job in (job_dict or {}):
        return raw_job
    text = _character_build_text(raw_job)
    if text:
        try:
            numeric = int(text)
            if numeric in (job_dict or {}):
                return numeric
            if str(numeric) in (job_dict or {}):
                return str(numeric)
        except ValueError:
            pass
        for job_id, info in (job_dict or {}).items():
            if _character_build_text((info or {}).get("name")) == text:
                return job_id
    return 0


def _character_build_grade_index(part_name, raw_grade, grade_index_maps=None):
    text = _character_build_text(raw_grade)
    per_part = (grade_index_maps or {}).get(part_name, {}) if isinstance(grade_index_maps, dict) else {}
    if isinstance(per_part, dict) and text in per_part:
        return _character_build_int(per_part[text], 0)
    normal = {"N": 0, "D": 1, "C": 2, "B": 3, "A": 4}
    if text.upper() in normal:
        return normal[text.upper()]
    try:
        return max(0, int(text))
    except (TypeError, ValueError):
        return 0


def character_build_to_equipment_request(
    build,
    *,
    data,
    stat_fields=None,
    refine_parts=None,
    grade_index_maps=None,
):
    """把已儲存的 CharacterBuild 資料轉成 Desktop 同樣使用、不依賴 Qt 的 request。"""
    if not isinstance(build, CharacterBuild):
        build = CharacterBuild.from_dict(build)
    values = build.to_legacy_dict()
    stat_fields = dict(stat_fields or STAGE21_9_FUNCTION_MAPS.get("stat_fields", {}))
    refine_parts = dict(refine_parts or {})

    get_values = {}
    for raw_gid, label in stat_fields.items():
        try:
            gid = int(raw_gid)
        except (TypeError, ValueError):
            gid = raw_gid
        raw = values.get(label, 0)
        if str(label) == "JOB":
            get_values[gid] = _character_build_resolve_job_id(raw, data.job_dict)
        else:
            get_values[gid] = _character_build_int(raw, 0)

    refine_inputs = {}
    slots = []
    for part_name, info in refine_parts.items():
        info = info if isinstance(info, dict) else {}
        slot_id = info.get("slot")
        refine = _character_build_int(values.get(part_name, values.get(f"{part_name}_refine", 0)), 0)
        refine_inputs[slot_id] = refine
        cards = [
            _character_build_text(values.get(f"{part_name}_card{i}", ""))
            for i in range(1, 5)
        ]
        slots.append(
            EquipmentSlotInput(
                part_name=str(part_name),
                slot_id=_character_build_int(slot_id, 0),
                equip_name=_character_build_text(values.get(f"{part_name}_equip", "")),
                grade=_character_build_grade_index(
                    part_name,
                    values.get(f"{part_name}_階級", 0),
                    grade_index_maps,
                ),
                cards=cards,
                note=_character_build_text(values.get(f"{part_name}_note", "")),
            )
        )

    enabled_skill_names = character_build_enabled_skill_names(
        values.get("buff", ""),
        data.skill_entries,
    )
    return EquipmentEffectRequest(
        get_values=get_values,
        refine_inputs=refine_inputs,
        slots=slots,
        enabled_skill_names=enabled_skill_names,
        hide_unrecognized=False,
        hide_physical=False,
        hide_magical=False,
        show_source=False,
        sort_mode="來源順序",
    )


def _character_build_find_skill_id(skill_name, skill_map):
    name = _character_build_text(skill_name)
    if not name:
        return None
    for skill_id, mapped_name in (skill_map or {}).items():
        if _character_build_text(mapped_name) == name:
            return _character_build_int(skill_id, skill_id)
    try:
        numeric = int(name)
    except ValueError:
        return None
    return numeric if numeric in (skill_map or {}) else None


def _character_build_damage_payload(values, data, runtime_overrides, status):
    runtime_overrides = dict(runtime_overrides or {})
    skill_id = runtime_overrides.get("skill_id")
    if skill_id is None:
        skill_id = _character_build_find_skill_id(values.get("skill_name"), data.skill_map)
    if skill_id is None:
        return None

    monster = {
        "size": _character_build_int(values.get("size", 1), 1),
        "element": _character_build_int(values.get("element", 0), 0),
        "element_lv": max(1, min(4, _character_build_int(values.get("element_lv", 1), 1))),
        "race": _character_build_int(values.get("race", 0), 0),
        "class": _character_build_int(values.get("class", 0), 0),
        "def": _character_build_int(values.get("def", 0), 0),
        "defc": _character_build_int(values.get("defc", 0), 0),
        "res": _character_build_int(values.get("res", 0), 0),
        "mdef": _character_build_int(values.get("mdef", 0), 0),
        "mdefc": _character_build_int(values.get("mdefc", 0), 0),
        "mres": _character_build_int(values.get("mres", 0), 0),
        "damage_multiplier_percent": _character_build_number(
            runtime_overrides.get("damage_multiplier_percent", 100), 100
        ),
        "betelgeuse_reduction_percent": _character_build_int(
            runtime_overrides.get("betelgeuse_reduction_percent", 0), 0
        ),
    }
    hpsp = (status or {}).get("hpsp", {}) if isinstance(status, dict) else {}
    payload = {
        "skill_id": _character_build_int(skill_id, 0),
        "monster": monster,
        "mhp": _character_build_int(runtime_overrides.get("mhp", hpsp.get("mhp", values.get("MHP", 0))), 0),
        "msp": _character_build_int(runtime_overrides.get("msp", hpsp.get("msp", values.get("MSP", 0))), 0),
        "mhp_now": _character_build_int(runtime_overrides.get("mhp_now", hpsp.get("mhp_now", 0)), 0),
        "msp_now": _character_build_int(runtime_overrides.get("msp_now", hpsp.get("msp_now", 0)), 0),
        "special": dict(runtime_overrides.get("special") or {}),
    }
    if runtime_overrides.get("skill_level") is not None:
        payload["skill_level"] = _character_build_int(runtime_overrides.get("skill_level"), 1)
    if runtime_overrides.get("attack_element") is not None:
        payload["attack_element"] = _character_build_int(runtime_overrides.get("attack_element"), 0)
    formula_override = _character_build_text(runtime_overrides.get("formula_override"))
    if formula_override:
        payload["formula_override"] = formula_override
    return payload


def calculate_character_build(
    build,
    *,
    runtime,
    stat_fields=None,
    refine_parts=None,
    grade_index_maps=None,
    runtime_overrides=None,
):
    """完整、不依賴 Qt 的 CharacterBuild -> 裝備 / 狀態 / 傷害計算 facade。"""
    if not isinstance(runtime, CoreRuntimeBundle):
        raise TypeError("runtime must be CoreRuntimeBundle")
    if not isinstance(build, CharacterBuild):
        build = CharacterBuild.from_dict(build)
    values = build.to_legacy_dict()
    runtime_overrides = build.merge_runtime_overrides(runtime_overrides)
    warnings = []

    request = character_build_to_equipment_request(
        build,
        data=runtime.data,
        stat_fields=stat_fields,
        refine_parts=refine_parts,
        grade_index_maps=grade_index_maps,
    )
    context = CalculationContext()
    dependencies = fork_core_dependencies(runtime.core.dependencies)
    effect_result = calculate_equipment_effects(
        request,
        runtime.data,
        context=context,
        dependencies=dependencies,
    )
    warnings.extend(list(getattr(effect_result, "warnings", []) or []))

    status = {}
    status_settings = {
        "mhp_input": _character_build_int(values.get("MHP", 0), 0),
        "msp_input": _character_build_int(values.get("MSP", 0), 0),
        "hp_percent": _character_build_int((runtime_overrides or {}).get("hp_percent", 100), 100),
        "sp_percent": _character_build_int((runtime_overrides or {}).get("sp_percent", 100), 100),
        "use_logout_hpsp": bool((runtime_overrides or {}).get("use_logout_hpsp", False)),
    }
    try:
        status = stage20_calculate_status(
            request=request,
            data=runtime.data,
            context=context,
            effect_result=effect_result,
            data_dir=runtime.data_dir,
            settings=status_settings,
        )
    except Exception as exc:
        warnings.append(f"角色狀態計算略過：{exc}")

    damage_payload = _character_build_damage_payload(values, runtime.data, runtime_overrides, status)
    damage_result = None
    if damage_payload is None:
        warnings.append("CharacterBuild 找不到可計算的技能；傷害結果略過。")
    else:
        try:
            damage_result = Stage17DamageResult(
                calculate_stage17_damage(
                    request=request,
                    data=runtime.data,
                    context=context,
                    effect_result=effect_result,
                    data_dir=runtime.data_dir,
                    damage=damage_payload,
                )
            )
            warnings.extend(list(damage_result.warnings or []))
        except Exception as exc:
            warnings.append(f"Stage17 傷害計算略過：{exc}")

    effect_dict = getattr(effect_result, "legacy_effect_dict", {}) or {}
    variables = _stage17_build_variables(
        request,
        runtime.data,
        context,
        effect_dict,
        damage_payload or {},
    )
    stat_summary = {
        "BaseLv": _character_build_int(variables.get("BaseLv", 0)),
        "JobLv": _character_build_int(variables.get("JobLv", 0)),
        "JOB": request.get_values.get(19, 0),
        "stats": {},
    }
    for stat in STAGE17_STAT_NAMES:
        stat_summary["stats"][stat] = {
            "base": _character_build_int(variables.get(f"base_{stat}", 0)),
            "job": _character_build_int(variables.get(f"job_{stat}", 0)),
            "equip": _character_build_int(variables.get(f"equip_{stat}", 0)),
            "base_equip": _character_build_int(variables.get(f"base_equip_{stat}", 0)),
            "total": _character_build_int(variables.get(f"total_{stat}", 0)),
        }

    refine_parts = dict(refine_parts or {})
    armor_slots = []
    for slot in request.slots:
        info = refine_parts.get(slot.part_name, {}) if isinstance(refine_parts, dict) else {}
        slot_id = getattr(slot, "slot_id", 0)
        armor_level = context.armor_level_map.get(
            slot_id,
            context.armor_level_map.get(str(slot_id), 0),
        )
        armor_slots.append(
            ArmorRefineSlotInput(
                part_name=slot.part_name,
                slot_id=slot_id,
                part_type=str((info or {}).get("type", "") or ""),
                equipped=bool(_character_build_text(slot.equip_name)),
                refine=request.refine_inputs.get(slot_id, 0),
                armor_level=_character_build_int(armor_level, 0),
            )
        )
    armor_bonus = calculate_armor_set_refine_bonus(armor_slots)

    # 無介面解析已儲存的自訂 Lua 備註，讓 MultiCompare 保持相同的
    # 可讀備註列，而不需要載入 QTextEdit / MainWindow。使用
    # 已預先計算好的 context，讓 GetEquip* helper 能讀到所選部位資料。
    equipment_notes = {}
    note_dependencies = fork_core_dependencies(runtime.core.dependencies)
    for slot in request.slots:
        raw_note = _character_build_text(getattr(slot, "note", ""))
        if not raw_note:
            equipment_notes[slot.part_name] = ""
            continue
        try:
            parsed_note = parse_lua_effects_with_variables(
                raw_note,
                request.refine_inputs,
                request.get_values,
                getattr(slot, "grade", 0),
                runtime.data.unit_map,
                runtime.data.size_map,
                runtime.data.effect_map,
                hide_unrecognized=True,
                hide_physical=False,
                hide_magical=False,
                current_location_slot=getattr(slot, "slot_id", None),
                context=context,
                dependencies=note_dependencies,
            )
            lines = [str(line).strip() for line in (parsed_note or []) if str(line).strip()]
            equipment_notes[slot.part_name] = "\n".join(lines) if lines else "（無可解析詞條）"
        except Exception as exc:
            warnings.append(f"{slot.part_name} 詞條解析略過：{exc}")
            equipment_notes[slot.part_name] = "（無可解析詞條）"

    return CharacterBuildCalculationResult(
        build=build,
        equipment_request=request,
        effect_result=effect_result,
        damage_result=damage_result,
        status=status,
        stat_summary=stat_summary,
        armor_bonus=armor_bonus,
        equipment_notes=equipment_notes,
        warnings=warnings,
    )
