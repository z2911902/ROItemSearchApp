"""多裝備比對模組。

此模組只負責：
- 多專案檔 / 目前設定 Snapshot 建立
- CharacterBuild -> Core 計算結果整理
- 裝備、BUFF、詞條與差異顯示
- 獨立比對視窗 UI

實際傷害、角色狀態與防具精煉計算由 ro_core.calculate_character_build()
提供；MultiCompare 不再回寫 MainWindow 來取得比較結果。
"""

# === CORE DEDUP PHASE 15: LEGACY CLEANUP ===

# PHASE 13 JSON IMPORT HOTFIX
import json

import html
import os
import re
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# === CORE DEDUP PHASE 16: CHARACTER BUILD SCHEMA V2 ===
# === CORE DEDUP PHASE 12+13+14: HEADLESS MULTICOMPARE ===
from ro_core import (
    CharacterBuild as CoreCharacterBuild,
    calculate_character_build as core_calculate_character_build,
)


# ===== 裝備總效果固定排序 MAP =====
# 你可以直接在這裡寫死順序；數字越小越前面。
#
# 支援三種 key 寫法：
# 1. 完整列名："裝備總效果 / ATK [%]"
# 2. 效果名含單位："ATK [%]"
# 3. 純效果名："ATK"
#
# 支援 * 萬用字元：* 代表「任意長度、任意字元」。
# 例如：
# "裝備總效果 / *敵人的物理 [%]": 200,
# "裝備總效果 / *型怪的魔法傷害 [%]": 210,
# "*遠距離物理傷害*": 300,
#
# 完全相符的 MAP 規則優先於 * 規則。
# 如果同一列同時符合多個 * 規則，會採用排序數字最小的規則。
# 沒寫進 MAP 的效果會保持 Core 原本的解析順序，並排在 MAP 指定項目之後。
EQUIPMENT_EFFECT_ORDER_MAP = {
    "裝備總效果 / ATK": 20,
    "裝備總效果 / ATK% [%]": 21,
    "裝備總效果 / 武器ATK": 22,
    "裝備總效果 / 修煉ATK": 23,
    "裝備總效果 / MATK": 30,
    "裝備總效果 / MATK% [%]": 31,
    "裝備總效果 / DEF": 40,
    "裝備總效果 / RES": 50,
    "裝備總效果 / MDEF": 60,
    "裝備總效果 / MRES": 70,    
    "裝備總效果 / MHP": 80,    
    "裝備總效果 / MHP% [%]": 81,    
    "裝備總效果 / MSP": 90,    
    "裝備總效果 / MSP% [%]": 91,
    "裝備總效果 / STR": 150,
    "裝備總效果 / AGI": 151,
    "裝備總效果 / VIT": 152,
    "裝備總效果 / INT": 153,
    "裝備總效果 / DEX": 154,
    "裝備總效果 / LUK": 155,
    "裝備總效果 / POW": 156,
    "裝備總效果 / STA": 157,
    "裝備總效果 / WIS": 158,
    "裝備總效果 / SPL": 159,
    "裝備總效果 / CON": 160,
    "裝備總效果 / CRT": 161,
    "裝備總效果 / P.ATK": 170,
    "裝備總效果 / S.MATK": 171,
    "裝備總效果 / 近距離物理傷害 [%]": 182,
    "裝備總效果 / 遠距離物理傷害 [%]": 183,
    "裝備總效果 / *的魔法傷害 [%]": 190,
    "裝備總效果 / 對*敵人的物理傷害 [%]": 200,
    "裝備總效果 / 對*敵人的魔法傷害 [%]": 201,
    "裝備總效果 / 對*型怪的物理傷害 [%]": 202,
    "裝備總效果 / 對*型怪的魔法傷害 [%]": 203,
    "裝備總效果 / 對*對象的物理傷害 [%]": 204,
    "裝備總效果 / 對*對象的魔法傷害 [%]": 205,
    "裝備總效果 / 對*階級的物理傷害 [%]": 206,
    "裝備總效果 / 對*階級的魔法傷害 [%]": 207,
    "裝備總效果 / 技能* [%]": 300,
    "裝備總效果 / 物理命中傷害 [%]": 301,
    "裝備總效果 / CRI": 302,
    "裝備總效果 / 爆擊傷害 [%]": 303,
    "裝備總效果 / C.RATE": 304,
    "裝備總效果 / 誘導攻擊機率 [%]": 311,
    "裝備總效果 / HIT": 312,
    "裝備總效果 / 攻擊後延遲 [%]": 321,
    "裝備總效果 / 技能後延遲 [%]": 322,

    "裝備總效果 / 無視* [%]": 401,
    "裝備總效果 / 受到* [%]": 501,

    
}


def _parse_buff_ids(raw_buff):
    """把 buff 欄位正規化為 set[str]。"""
    if raw_buff is None:
        return set()
    if isinstance(raw_buff, (int, float)):
        return {str(int(raw_buff))}
    if isinstance(raw_buff, (list, tuple, set)):
        result = set()
        for value in raw_buff:
            if value is None:
                continue
            value = str(value).strip()
            if value:
                result.add(value)
        return result

    text = str(raw_buff).strip()
    if not text:
        return set()
    return {part.strip() for part in text.split(",") if part.strip()}


class MultiCompareService:
    """主程式與多裝備比對視窗之間的資料/計算橋接層。

    context 由主程式注入，避免此模組反向 import 主程式造成 circular import。
    """

    def __init__(self, main_window, context=None):
        self.main_window = main_window
        self.context = dict(context or {})

    def update_context(self, context=None):
        if context:
            self.context.update(context)

    def _ctx(self, key, default=None):
        return self.context.get(key, default)

    @property
    def globals_map(self):
        mapping = self._ctx("globals_map", {})
        return mapping if isinstance(mapping, dict) else {}

    def translate(self, key, default=None, **kwargs):
        func = self._ctx("tr")
        if callable(func):
            try:
                return func(key, default, **kwargs)
            except Exception:
                pass
        return default if default is not None else key




    @staticmethod


    # === CORE DEDUP PHASE 10: MULTICOMPARE STRUCTURED CORE DAMAGE ===
    @staticmethod
    def _core_compare_number(value, default=0.0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _core_compare_format_number(value, digits=None):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value or "")
        if digits is not None:
            return f"{number:,.{int(digits)}f}"
        if number.is_integer():
            return f"{int(number):,}"
        return f"{number:,.2f}".rstrip("0").rstrip(".")

    @classmethod
    def _core_compare_entry(cls, value, *, unit="", digits=None, display=None, number=None):
        numeric = cls._core_compare_number(value) if number is None else cls._core_compare_number(number)
        if display is None:
            display = cls._core_compare_format_number(value, digits=digits)
            if unit:
                display = f"{display}{unit}"
        return {
            "display": str(display),
            "number": numeric,
            "suffix": str(unit or ""),
        }

    @classmethod
    def _core_compare_damage_range_entry(cls, minimum, maximum, *, critical=False):
        low = int(cls._core_compare_number(minimum))
        high = int(cls._core_compare_number(maximum))
        if critical:
            return cls._core_compare_entry(high, display=f"{high:,}", number=high)
        return cls._core_compare_entry(
            low,
            display=f"{low:,} ~ {high:,}",
            number=low,
        )


    def _collect_compare_core_damage_results(self, payload=None):
        """Convert Stage17 structured result into MultiCompare's existing row contract.

        The comparison table keeps the same {display, number, suffix} schema, but
        damage numbers and damage-breakdown rows come from Core rather than regex
        parsing the Desktop text box.
        """
        if hasattr(payload, "to_dict"):
            payload = payload.to_dict()
        if not isinstance(payload, dict):
            return {}, "core-unavailable"

        results = {}
        display_meta = payload.get("display", {}) if isinstance(payload.get("display"), dict) else {}
        critical = self._core_compare_number(display_meta.get("critical_hit", 0)) > 0
        decay_hits = int(self._core_compare_number(display_meta.get("decay_hits", 0)))

        skill = payload.get("skill", {}) if isinstance(payload.get("skill"), dict) else {}
        attack_type = str(skill.get("attack_type", "") or "").lower()
        segments = [
            dict(row) for row in (payload.get("segments") or [])
            if isinstance(row, dict)
        ]

        if attack_type == "shield":
            breakdown = payload.get("breakdown", {}) if isinstance(payload.get("breakdown"), dict) else {}
            for row in breakdown.get("rows", []) or []:
                if isinstance(row, dict) and row.get("key") == "shield_formula":
                    results[str(row.get("label") or "護盾可抵擋傷害")] = self._core_compare_entry(
                        row.get("value", 0),
                        unit=str(row.get("unit", "") or ""),
                        digits=row.get("digits"),
                    )
                    break
        elif segments:
            combo_split = (
                len(segments) > 1
                and str(segments[1].get("label", "")) == "combo (均分)"
            )
            if combo_split:
                main_seg = segments[0]
                combo_seg = segments[1]
                results["單次傷害"] = self._core_compare_damage_range_entry(
                    main_seg.get("damage_by_hit_min", 0),
                    main_seg.get("damage_by_hit", 0),
                    critical=critical,
                )
                results["打擊次數"] = self._core_compare_entry(
                    main_seg.get("times", 1),
                    display=f"{int(self._core_compare_number(main_seg.get('times', 1), 1))} 次",
                )
                results["主技能總傷害"] = self._core_compare_damage_range_entry(
                    main_seg.get("total_damage_min", 0),
                    main_seg.get("total_damage", 0),
                    critical=critical,
                )
                results["單次傷害(COMBO)"] = self._core_compare_damage_range_entry(
                    combo_seg.get("damage_by_hit_min", 0),
                    combo_seg.get("damage_by_hit", 0),
                    critical=critical,
                )
                results["打擊次數(COMBO)"] = self._core_compare_entry(
                    combo_seg.get("times", 1),
                    display=f"{int(self._core_compare_number(combo_seg.get('times', 1), 1))} 次",
                )
                results["總傷害(COMBO)"] = self._core_compare_damage_range_entry(
                    combo_seg.get("total_damage_min", 0),
                    combo_seg.get("total_damage", 0),
                    critical=critical,
                )
                results["總傷害"] = self._core_compare_damage_range_entry(
                    payload.get("total_damage_min", 0),
                    payload.get("total_damage", 0),
                    critical=critical,
                )
            elif len(segments) > 1:
                total_count = len(segments)
                for idx, seg in enumerate(segments, start=1):
                    results[f"第 {idx}/{total_count} 次傷害"] = self._core_compare_damage_range_entry(
                        seg.get("total_damage_min", 0),
                        seg.get("total_damage", 0),
                        critical=critical,
                    )
                results["總傷害"] = self._core_compare_damage_range_entry(
                    payload.get("total_damage_min", 0),
                    payload.get("total_damage", 0),
                    critical=critical,
                )
            else:
                seg = segments[0]
                results["單次傷害"] = self._core_compare_damage_range_entry(
                    seg.get("damage_by_hit_min", 0),
                    seg.get("damage_by_hit", 0),
                    critical=critical,
                )
                results["打擊次數"] = self._core_compare_entry(
                    seg.get("times", 1),
                    display=f"{int(self._core_compare_number(seg.get('times', 1), 1))} 次",
                )
                results["總傷害"] = self._core_compare_damage_range_entry(
                    seg.get("total_damage_min", 0),
                    seg.get("total_damage", 0),
                    critical=critical,
                )

            if decay_hits > 1:
                total_max = int(self._core_compare_number(payload.get("total_damage", 0)))
                results["遞增/減段數"] = self._core_compare_entry(
                    decay_hits,
                    display=f"{decay_hits} 段",
                )
                average = int(total_max / decay_hits)
                results["平均每段傷害"] = self._core_compare_entry(
                    average,
                    display=f"{average:,}",
                )

        breakdown = payload.get("breakdown", {}) if isinstance(payload.get("breakdown"), dict) else {}
        for row in breakdown.get("rows", []) or []:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label", "") or "").strip()
            if not label or row.get("key") == "shield_formula":
                continue
            results[label] = self._core_compare_entry(
                row.get("value", 0),
                unit=str(row.get("unit", "") or ""),
                digits=row.get("digits"),
            )

        return results, "core-character-build"


    # === CORE DEDUP PHASE 12+13+14: HEADLESS MULTICOMPARE ===
    def _core_build_runtime(self):
        # Data/runtime is immutable for one application session; reuse it across JSON
        # snapshots so a large compare batch does not reload skillbuff.lua every time.
        runtime = getattr(self, "_phase121314_core_runtime", None)
        if runtime is not None:
            return runtime
        factory = self._ctx("core_runtime_factory")
        if not callable(factory):
            raise RuntimeError("主程式缺少 Phase 12 Core runtime factory")
        runtime = factory()
        if runtime is None:
            raise RuntimeError("Core runtime factory 回傳空值")
        self._phase121314_core_runtime = runtime
        return runtime

    def _core_runtime_overrides(self, *, for_saved_build=False, build=None):
        collector = self._ctx("collect_character_calculation_runtime")
        raw = collector() if callable(collector) else {}
        raw = dict(raw or {})

        # 這些都是「顯示」選項，不是戰鬥計算條件。
        # 不讓它們進 Core，避免勾選隱藏物理/魔法後改變傷害計算。
        presentation_only_keys = {
            "hide_unrecognized",
            "hide_physical",
            "hide_magical",
            "hide_magic",
            "hide_physical_effects",
            "hide_magical_effects",
        }
        for key in presentation_only_keys:
            raw.pop(key, None)

        special = raw.get("special")
        if isinstance(special, dict):
            special = dict(special)
            for key in presentation_only_keys:
                special.pop(key, None)
            raw["special"] = special

        if for_saved_build and getattr(build, "combat_state", None):
            # Schema-v2 project files are self-contained.  Do not let the currently
            # open Desktop's transient controls overwrite the saved combat state.
            return {}
        if for_saved_build:
            # v0/v1 compatibility: these project files did not persist combat state,
            # so retain the historical fallback to current global/transient controls.
            raw.pop("skill_id", None)
            raw.pop("skill_level", None)
            raw.pop("formula_override", None)
            raw.pop("attack_element", None)
            special = dict(raw.get("special") or {})
            special.pop("total_srl", None)
            raw["special"] = special
        return raw

    def _calculate_character_build_core(self, build, *, for_saved_build=False):
        if not isinstance(build, CoreCharacterBuild):
            build = CoreCharacterBuild.from_dict(build)
        return core_calculate_character_build(
            build,
            runtime=self._core_build_runtime(),
            stat_fields=self._ctx("stat_fields", {}) or {},
            refine_parts=self._ctx("refine_parts", {}) or {},
            grade_index_maps=self._ctx("grade_index_maps", {}) or {},
            runtime_overrides=self._core_runtime_overrides(for_saved_build=for_saved_build, build=build),
        )

    def _collect_compare_equipment_from_build(self, build, calculation):
        values = build.to_legacy_dict() if hasattr(build, "to_legacy_dict") else dict(build or {})
        flat = {}
        for part, info in (self._ctx("refine_parts", {}) or {}).items():
            if part == "技能":
                continue
            flat[f"{part} / 裝備"] = str(values.get(f"{part}_equip", "") or "")
            if part in values:
                flat[f"{part} / 精煉"] = str(values.get(part, "") or "")
            grade_key = f"{part}_階級"
            if grade_key in values:
                flat[f"{part} / 階級"] = str(values.get(grade_key, "") or "")
            for i in range(1, 5):
                card_key = f"{part}_card{i}"
                if card_key in values:
                    flat[f"{part} / 卡片{i}"] = str(values.get(card_key, "") or "")
            note_key = f"{part}_note"
            if note_key in values:
                parsed_notes = getattr(calculation, "equipment_notes", {}) or {}
                flat[f"{part} / 詞條"] = str(parsed_notes.get(part, "") or "")
        request = getattr(calculation, "equipment_request", None)
        enabled = list(getattr(request, "enabled_skill_names", []) or [])
        flat["BUFF / 技能、料理"] = "\n".join(str(name) for name in enabled)
        return flat

    def _collect_compare_skill_from_core(self, build, calculation):
        values = build.to_legacy_dict() if hasattr(build, "to_legacy_dict") else dict(build or {})
        payload = calculation.damage_result.to_dict() if getattr(calculation, "damage_result", None) is not None else {}
        skill = payload.get("skill", {}) if isinstance(payload, dict) else {}
        name = str(skill.get("name", values.get("skill_name", "")) or "")
        level = skill.get("level", None)
        element_id = skill.get("attack_element", None)
        element_map = self._ctx("element_map", {}) or {}
        element_display = element_map.get(element_id, element_map.get(str(element_id), str(element_id if element_id is not None else "")))
        result = {
            "技能名稱": {"display": name, "number": None, "suffix": ""},
            "技能攻擊屬性": {"display": str(element_display), "number": None, "suffix": ""},
        }
        if level is not None:
            result["技能等級"] = self._core_compare_entry(level)
        return result

    @staticmethod
    def _core_effect_is_diagnostic(effect):
        """Core parser 的診斷/未辨識內容不應成為裝備效果比較列。"""
        # 優先尊重 Core 本身若已有結構化顯示旗標。
        for attr in ("hidden", "is_hidden", "display_hidden"):
            value = getattr(effect, attr, None)
            if isinstance(value, bool) and value:
                return True

        for attr in ("recognized", "is_recognized", "displayable", "is_displayable"):
            value = getattr(effect, attr, None)
            if isinstance(value, bool) and not value:
                return True

        meta = getattr(effect, "meta", None)
        if isinstance(meta, dict):
            if meta.get("hidden") is True:
                return True
            if meta.get("recognized") is False:
                return True
            if meta.get("displayable") is False:
                return True
            kind = str(meta.get("kind", "") or "").casefold()
            if kind in {"diagnostic", "debug", "unrecognized", "parser_warning"}:
                return True

        key = str(getattr(effect, "key", "") or "").strip()
        if not key:
            return True

        # Core/parser trace 行不是實際裝備能力。
        # ✅ 條件成立、❌ 條件不成立、📌 暫存變數、🟡 無法辨識等全部隱藏。
        diagnostic_markers = ("🟡", "❌", "✅", "📌", "⛔", "⚠️")
        if key.startswith(diagnostic_markers):
            return True

        # 舊版 Core 沒有結構化旗標時，用 parser 的診斷文字相容過濾。
        normalized = key.lstrip("🟡❌✅⛔⚠️📌🔸🔹 ").strip()
        diagnostic_starts = (
            "line解析 無法辨識",
            "一般變數 無法辨識",
            "if 條件成立",
            "if 條件不成立",
            "elseif 條件成立",
            "elseif 條件不成立",
            "else 條件成立",
            "已跳過（條件不成立）",
            "已跳過(條件不成立)",
            "無法計算",
            "無法辨識",
            "條件不成立",
            "條件成立",
        )
        if normalized.startswith(diagnostic_starts):
            return True

        # parser 暫存變數追蹤，例如 `temp1` =、`temp_all` =、temp = ...
        if re.match(r"^`[^`]+`\s*=", normalized):
            return True
        if re.match(r"^(?:temp|temp_all|temp\d+)\s*=", normalized, re.IGNORECASE):
            return True

        # 「可使用技能 / 可使用...」屬於功能授予資訊，
        # 不列入多裝備的數值效果比較。
        usable_prefixes = (
            "可使用",
            "可以使用",
            "可施放",
            "可以施放",
        )
        if normalized.startswith(usable_prefixes):
            return True

        return False

    def _collect_compare_effects_from_core(self, calculation):
        """把 Core 已解析的有效效果加入多裝備比對。

        注意：物理/魔法隱藏不在這裡做。
        Core 保留完整效果做傷害計算，MultiCompare 最後只隱藏顯示列。
        """
        effect_result = getattr(calculation, "effect_result", None)
        effects = list(getattr(effect_result, "effects", []) or [])
        result = {}

        for effect in effects:
            if self._core_effect_is_diagnostic(effect):
                continue

            key = str(getattr(effect, "key", "") or "").strip()
            if not key:
                continue

            unit = str(getattr(effect, "unit", "") or "")
            total = getattr(effect, "total", 0)
            contributions = list(getattr(effect, "entries", []) or [])

            label = f"裝備總效果 / {key}"
            if unit:
                label += f" [{unit}]"

            # 有效的非數值效果（可使用技能/旗標等）顯示「有」。
            all_zero_entries = bool(contributions)
            if all_zero_entries:
                for contribution in contributions:
                    if abs(self._core_compare_number(
                        getattr(contribution, "value", 0)
                    )) > 1e-12:
                        all_zero_entries = False
                        break

            is_flag_effect = (
                not unit
                and all_zero_entries
                and abs(self._core_compare_number(total)) <= 1e-12
            )

            if is_flag_effect:
                entry = {
                    "display": "有",
                    "number": None,
                    "suffix": "",
                }
            else:
                entry = self._core_compare_entry(total, unit=unit)

            # Tooltip 保留來源；這只是顯示資訊，不參與計算。
            source_lines = []
            for contribution in contributions:
                source = str(getattr(contribution, "source", "") or "").strip()
                if not source:
                    continue

                if is_flag_effect:
                    source_lines.append(f"{source}：有")
                    continue

                value = getattr(contribution, "value", 0)
                value_text = self._core_compare_format_number(value)
                if unit:
                    value_text += unit
                source_lines.append(f"{source}：{value_text}")

            if source_lines:
                entry["tooltip"] = "\n".join(source_lines)

            result[label] = entry

        return result

    def _collect_compare_monster_target_meta_from_build(self, build):
        """保存魔物體型/種族/屬性/階級，供顯示層過濾裝備效果。"""
        values = build.to_legacy_dict() if hasattr(build, "to_legacy_dict") else dict(build or {})

        def mapped(map_name, key, default=""):
            mapping = self._ctx(map_name, {}) or {}
            try:
                key_int = int(float(values.get(key, 0)))
            except (TypeError, ValueError):
                key_int = values.get(key, 0)
            return mapping.get(
                key_int,
                mapping.get(str(key_int), default if default != "" else str(key_int)),
            )

        return {
            "size": str(mapped("size_map", "size") or ""),
            "race": str(mapped("race_map", "race") or ""),
            "element": str(mapped("element_map", "element") or ""),
            "element_lv": str(values.get("element_lv", "1") or "1"),
            "class": str(mapped("class_map", "class") or ""),
        }

    def _collect_compare_monster_from_build(self, build):
        # 後面的 DEF / MDEF / RES 等欄位仍需從原始 build values 取得。
        values = build.to_legacy_dict() if hasattr(build, "to_legacy_dict") else dict(build or {})
        target = self._collect_compare_monster_target_meta_from_build(build)
        size = target.get("size", "")
        race = target.get("race", "")
        element = target.get("element", "")
        klass = target.get("class", "")
        element_lv = target.get("element_lv", "1")
        result = {
            "魔物 / 體種屬階": {
                "display": f"{size} /{race} /{element} Lv.{element_lv} /{klass}",
                "number": None,
                "suffix": "",
            }
        }
        for label, key in (
            ("魔物 / 後 DEF", "def"), ("魔物 / 前 DEF", "defc"), ("魔物 / RES", "res"),
            ("魔物 / 後 MDEF", "mdef"), ("魔物 / 前 MDEF", "mdefc"), ("魔物 / MRES", "mres"),
        ):
            result[label] = self._core_compare_entry(values.get(key, 0))
        return result

    def _collect_compare_character_from_core(self, calculation):
        summary = getattr(calculation, "stat_summary", {}) or {}
        result = {
            "角色等級 / BaseLv": self._core_compare_entry(summary.get("BaseLv", 0)),
            "角色等級 / JobLv": self._core_compare_entry(summary.get("JobLv", 0)),
        }
        stats = summary.get("stats", {}) if isinstance(summary, dict) else {}
        for stat in ("STR", "AGI", "VIT", "INT", "DEX", "LUK"):
            result[f"素質 / {stat}"] = self._core_compare_entry((stats.get(stat) or {}).get("total", 0))
        for stat in ("POW", "STA", "WIS", "SPL", "CON", "CRT"):
            result[f"特性素質 / {stat}"] = self._core_compare_entry((stats.get(stat) or {}).get("total", 0))

        status = getattr(calculation, "status", {}) or {}
        hpsp = status.get("hpsp", {}) if isinstance(status, dict) else {}
        if isinstance(hpsp, dict):
            for label, key in (
                ("角色狀態 / MHP", "mhp"), ("角色狀態 / MSP", "msp"),
                ("角色狀態 / 目前HP", "mhp_now"), ("角色狀態 / 目前SP", "msp_now"),
            ):
                if key in hpsp:
                    result[label] = self._core_compare_entry(hpsp.get(key, 0))
        aspd = status.get("aspd", {}) if isinstance(status, dict) else {}
        if isinstance(aspd, dict) and aspd.get("supported") and aspd.get("value") is not None:
            result["角色狀態 / ASPD"] = self._core_compare_entry(aspd.get("value"), digits=3)
            if aspd.get("attacks_per_second") is not None:
                result["角色狀態 / 每秒攻擊次數"] = self._core_compare_entry(aspd.get("attacks_per_second"), digits=4)
        no_cast = status.get("no_cast", {}) if isinstance(status, dict) else {}
        if isinstance(no_cast, dict):
            if "score" in no_cast:
                result["角色狀態 / 無詠唱素質值"] = self._core_compare_entry(no_cast.get("score", 0))
            if "gap" in no_cast:
                result["角色狀態 / 無詠唱差距"] = self._core_compare_entry(no_cast.get("gap", 0))

        armor = getattr(calculation, "armor_bonus", {}) or {}
        result["防具精煉 / DEF"] = self._core_compare_entry(armor.get("DEF", 0))
        result["防具精煉 / RES"] = self._core_compare_entry(armor.get("RES", 0))
        return result

    def _build_compare_snapshot_from_core(self, name, build, calculation, source=None):
        results = self._collect_compare_skill_from_core(build, calculation)
        damage_payload = (
            calculation.damage_result.to_dict()
            if getattr(calculation, "damage_result", None) is not None
            else None
        )
        core_damage_results, damage_source = self._collect_compare_core_damage_results(damage_payload)
        results.update(core_damage_results)

        # 傷害已由 Core 用完整效果算完；這裡只是加入可顯示的效果列。
        results.update(self._collect_compare_effects_from_core(calculation))

        results.update(self._collect_compare_monster_from_build(build))
        results.update(self._collect_compare_character_from_core(calculation))
        warnings = list(getattr(calculation, "warnings", []) or [])
        return {
            "name": str(name or "未命名"),
            "source": source,
            "equipment": self._collect_compare_equipment_from_build(build, calculation),
            "results": results,
            "monster_target": self._collect_compare_monster_target_meta_from_build(build),
            "result_text": "",
            "damage_result_source": damage_source,
            "core_warnings": warnings,
        }

    def create_current_compare_snapshot(self, name="目前設定"):
        """Calculate the current CharacterBuild directly in Core without recalculating MainWindow."""
        collect_build = getattr(self.main_window, "collect_character_build", None)
        if not callable(collect_build):
            raise RuntimeError("主程式缺少 Phase 8 collect_character_build()")
        build = collect_build()
        calculation = self._calculate_character_build_core(build, for_saved_build=False)
        return self._build_compare_snapshot_from_core(name, build, calculation, source="current")


    def create_json_compare_snapshot(self, file_path):
        """Project JSON -> CharacterBuild -> Core. MainWindow is never loaded or recalculated."""
        with open(file_path, "r", encoding="utf-8-sig") as fh:
            payload = json.load(fh)
        build = CoreCharacterBuild.from_dict(payload)
        calculation = self._calculate_character_build_core(build, for_saved_build=True)
        return self._build_compare_snapshot_from_core(Path(file_path).stem, build, calculation, source=file_path)


class DragCheckListWidget(QListWidget):
    """支援從前方 checkbox 區按住左鍵，拖過多列連續勾選/取消。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._check_drag_active = False
        self._check_drag_state = Qt.Unchecked
        self._check_drag_last_row = -1
        self.check_drag_finished_callback = None

    @staticmethod
    def _mouse_event_pos(event):
        try:
            return event.position().toPoint()
        except Exception:
            return event.pos()

    def is_check_drag_active(self):
        return bool(self._check_drag_active)

    def _is_checkbox_zone(self, item, pos):
        if item is None:
            return False
        rect = self.visualItemRect(item)
        if not rect.isValid():
            return False

        # checkbox 通常位於列最左側；依字體高度保留足夠的 HiDPI 點擊寬度。
        checkbox_zone_width = max(34, self.fontMetrics().height() + 18)
        return (
            rect.top() <= pos.y() <= rect.bottom()
            and rect.left() <= pos.x() <= rect.left() + checkbox_zone_width
        )

    def _apply_drag_state_to_item(self, item):
        if item is None:
            return
        row = self.row(item)
        if row < 0 or row == self._check_drag_last_row:
            return

        self._check_drag_last_row = row
        self.setCurrentItem(item)
        if item.checkState() != self._check_drag_state:
            item.setCheckState(self._check_drag_state)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = self._mouse_event_pos(event)
            item = self.itemAt(pos)
            if self._is_checkbox_zone(item, pos):
                # 第一格目前沒勾 -> 整段都勾；目前已勾 -> 整段都取消。
                self._check_drag_active = True
                self._check_drag_state = (
                    Qt.Unchecked
                    if item.checkState() == Qt.Checked
                    else Qt.Checked
                )
                self._check_drag_last_row = -1
                self._apply_drag_state_to_item(item)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._check_drag_active and (event.buttons() & Qt.LeftButton):
            item = self.itemAt(self._mouse_event_pos(event))
            self._apply_drag_state_to_item(item)
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._check_drag_active and event.button() == Qt.LeftButton:
            self._check_drag_active = False
            self._check_drag_last_row = -1
            callback = self.check_drag_finished_callback
            if callable(callback):
                callback()
            event.accept()
            return

        super().mouseReleaseEvent(event)


class MultiCompareDialog(QDialog):
    """獨立的多裝備 / 多專案檔計算結果比對視窗。"""

    def __init__(self, service):
        # 不把主畫面設成 Qt parent，讓它成為真正獨立的頂層視窗。
        # main_window 仍保留 Python 參照，供 Snapshot / 專案檔計算使用。
        super().__init__(None)
        self.service = service
        self.main_window = service.main_window
        self.current_snapshot = None
        self.json_snapshots = []

        # 計算結果自訂過濾：沒有勾選時顯示全部；有勾選時只顯示勾選項目。
        self._result_filter_selected_keys = set()
        self._result_filter_available_keys = []
        self._result_filter_dialog = None
        self._result_filter_search = None
        self._result_filter_list = None
        self._rebuilding_result_filter_list = False

        self.setWindowTitle("多裝備比對")
        self.resize(1500, 900)
        # 使用標準桌面視窗標題列：最小化 / 最大化(還原) / 關閉。
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        root = QVBoxLayout(self)

        # ===== 固定在最上方的操作列 =====
        # 使用獨立 QWidget，而不是直接把 QHBoxLayout 丟進帶 stretch 的 root。
        # 這樣即使下方兩個表格都收起，操作列也不會被剩餘空間推到視窗中間。
        self.toolbar_widget = QWidget()
        self.toolbar_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        toolbar = QHBoxLayout(self.toolbar_widget)
        toolbar.setContentsMargins(0, 0, 0, 0)

        self.update_current_button = QPushButton("更新目前設定")
        self.add_json_button = QPushButton("加入專案檔...")
        self.remove_json_button = QPushButton("移除選擇")
        self.clear_json_button = QPushButton("清空專案檔")

        self.show_current_checkbox = QCheckBox("顯示目前設定")
        # 主程式已有命名/已載入專案時才預設顯示「目前設定」；
        # 若仍是「未命名」，避免空白基準佔掉最左側欄位。
        self.show_current_checkbox.setChecked(self._main_window_has_named_project())
        self.only_diff_checkbox = QCheckBox("只顯示差異")
        self.only_diff_checkbox.setChecked(True)
        self.baseline_monster_target_checkbox = QCheckBox("只顯示基準魔物的體種屬階")
        self.baseline_monster_target_checkbox.setChecked(False)
        self.baseline_monster_target_checkbox.setToolTip(
            "以選定的比對基準魔物過濾體型 / 種族 / 屬性 / 階級限定效果；"
            "同時統一顯示基準魔物的體種屬階。"
            "只影響表格顯示，不改寫 Snapshot，也不重新計算傷害。"
        )
        self.result_filter_button = QPushButton("選擇過濾")
        self.result_filter_button.setToolTip(
            "搜尋並勾選計算結果項目。沒有勾選時顯示全部；"
            "有勾選時只顯示勾選項目。勾選項目會自動置頂。"
            "支援按住左側勾選框拖曳連續勾選/取消。"
        )

        # 計算結果不再固定與最左欄比較；使用者可指定任一可見 Snapshot
        # 作為比對基準。也支援直接點擊上下表格的欄標題切換基準。
        self.compare_base_label = QLabel("比對基準：")
        self.compare_base_combo = QComboBox()
        self.compare_base_combo.setMinimumWidth(180)
        self.status_label = QLabel("")

        toolbar.addWidget(self.update_current_button)
        toolbar.addWidget(self.add_json_button)
        toolbar.addWidget(self.remove_json_button)
        toolbar.addWidget(self.clear_json_button)
        toolbar.addSpacing(16)
        toolbar.addWidget(self.show_current_checkbox)
        toolbar.addWidget(self.only_diff_checkbox)
        toolbar.addWidget(self.baseline_monster_target_checkbox)
        toolbar.addWidget(self.result_filter_button)
        toolbar.addSpacing(16)
        toolbar.addWidget(self.compare_base_label)
        toolbar.addWidget(self.compare_base_combo)
        toolbar.addStretch(1)
        toolbar.addWidget(self.status_label)
        root.addWidget(self.toolbar_widget, 0, Qt.AlignTop)

        # 下方內容獨立成一個可伸縮區域。操作列不參與這裡的高度分配。
        self.compare_content_widget = QWidget()
        self.compare_content_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.compare_content_layout = QVBoxLayout(self.compare_content_widget)
        self.compare_content_layout.setContentsMargins(0, 0, 0, 0)

        # ===== 裝備差異區塊：標題旁提供獨立展開 / 收起 =====
        self.equipment_section_widget = QWidget()
        self.equipment_section_layout = QVBoxLayout(self.equipment_section_widget)
        self.equipment_section_layout.setContentsMargins(0, 0, 0, 0)

        equipment_header = QHBoxLayout()
        equipment_header.setContentsMargins(0, 0, 0, 0)
        self.equipment_title_label = QLabel("裝備差異（可選擇比對基準）")
        self.equipment_toggle_button = QToolButton()
        self.equipment_toggle_button.setText("▲ 收起")
        self.equipment_toggle_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        equipment_header.addWidget(self.equipment_title_label)
        equipment_header.addWidget(self.equipment_toggle_button)
        equipment_header.addStretch(1)
        self.equipment_section_layout.addLayout(equipment_header)

        self.equipment_table = QTableWidget()
        self.equipment_table.setAlternatingRowColors(True)
        self.equipment_table.setWordWrap(True)
        # 上下兩張表都使用像素水平捲動，確保同步時欄位能精準對齊。
        self.equipment_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.equipment_section_layout.addWidget(self.equipment_table, 1)

        # ===== 計算結果區塊：與裝備差異可分別展開 / 收起 =====
        self.result_section_widget = QWidget()
        self.result_section_layout = QVBoxLayout(self.result_section_widget)
        self.result_section_layout.setContentsMargins(0, 0, 0, 0)

        result_header = QHBoxLayout()
        result_header.setContentsMargins(0, 0, 0, 0)
        self.result_title_label = QLabel("計算結果（可選擇比對基準）")
        self.result_toggle_button = QToolButton()
        self.result_toggle_button.setText("▲ 收起")
        self.result_toggle_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        result_header.addWidget(self.result_title_label)
        result_header.addWidget(self.result_toggle_button)
        result_header.addStretch(1)
        self.result_section_layout.addLayout(result_header)

        self.result_table = QTableWidget()
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setWordWrap(False)
        # 與裝備表一致使用像素水平捲動，兩區滑動時維持相同 X 偏移。
        self.result_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.result_section_layout.addWidget(self.result_table, 1)

        # ===== 可拖曳的上下分隔線 =====
        # 裝備差異與計算結果放進垂直 QSplitter，使用者可直接拖曳中間分隔線
        # 任意調整兩區高度；不再以固定 3:2 stretch 鎖住比例。
        self.compare_splitter = QSplitter(Qt.Vertical)
        self.compare_splitter.setChildrenCollapsible(False)
        self.compare_splitter.setHandleWidth(8)
        self.compare_splitter.addWidget(self.equipment_section_widget)
        self.compare_splitter.addWidget(self.result_section_widget)
        self.compare_splitter.setStretchFactor(0, 3)
        self.compare_splitter.setStretchFactor(1, 2)
        self.compare_content_layout.addWidget(self.compare_splitter, 1)

        # 兩區都收起時，讓最下方 spacer 吃掉剩餘高度，確保工具列與兩個標題
        # 仍固定在視窗最上方。只要任一區展開，splitter 就重新取得全部可用高度。
        self.compare_content_layout.addStretch(0)
        root.addWidget(self.compare_content_widget, 1)

        # 兩張表格使用同一組欄寬。除了自動計算外，手動拖曳任一表格欄寬時
        # 也會即時同步到另一張表，避免上下欄位對不齊。
        self._equipment_expanded = True
        self._result_expanded = True
        self._syncing_compare_column_widths = False
        self._syncing_compare_horizontal_scroll = False
        # 記住使用者最後一次在兩區皆展開時拖出的比例；收合再展開時恢復。
        self._compare_splitter_sizes = [100, 100]
        QTimer.singleShot(0, lambda: self.compare_splitter.setSizes(self._compare_splitter_sizes))

        self.update_current_button.clicked.connect(self.refresh_current_snapshot)
        self.add_json_button.clicked.connect(self.add_json_files)
        self.remove_json_button.clicked.connect(self.remove_selected_json)
        self.clear_json_button.clicked.connect(self.clear_jsons)
        self.show_current_checkbox.toggled.connect(self.refresh_tables)
        self.only_diff_checkbox.toggled.connect(self.refresh_tables)
        self.baseline_monster_target_checkbox.toggled.connect(self.refresh_tables)
        self.result_filter_button.clicked.connect(self._open_result_filter_dialog)
        self.compare_base_combo.currentIndexChanged.connect(self.refresh_tables)
        self.equipment_table.horizontalHeader().sectionClicked.connect(
            self._set_compare_base_from_column
        )
        self.result_table.horizontalHeader().sectionClicked.connect(
            self._set_compare_base_from_column
        )
        self.equipment_toggle_button.clicked.connect(self._toggle_equipment_section)
        self.result_toggle_button.clicked.connect(self._toggle_result_section)
        self.equipment_table.horizontalHeader().sectionResized.connect(
            lambda logical, old_size, new_size: self._mirror_compare_column_width(
                self.equipment_table, self.result_table, logical, new_size
            )
        )
        self.result_table.horizontalHeader().sectionResized.connect(
            lambda logical, old_size, new_size: self._mirror_compare_column_width(
                self.result_table, self.equipment_table, logical, new_size
            )
        )

        # 水平捲軸雙向同步：不論滑動上方或下方表格，另一張表都維持相同 X 位置。
        self.equipment_table.horizontalScrollBar().valueChanged.connect(
            lambda value: self._mirror_compare_horizontal_scroll(
                self.equipment_table, self.result_table, value
            )
        )
        self.result_table.horizontalScrollBar().valueChanged.connect(
            lambda value: self._mirror_compare_horizontal_scroll(
                self.result_table, self.equipment_table, value
            )
        )

        # 主程式「隱藏物理 / 隱藏魔法」只控制 MultiCompare 的效果列顯示。
        # 切換時只刷新表格，不重新計算 Snapshot / Core 傷害。
        connected_effect_filter_checkboxes = set()
        for kind in ("physical", "magical"):
            checkbox = self._find_main_effect_filter_checkbox(kind)
            if checkbox is None or id(checkbox) in connected_effect_filter_checkboxes:
                continue
            connected_effect_filter_checkboxes.add(id(checkbox))
            if hasattr(checkbox, "stateChanged"):
                try:
                    checkbox.stateChanged.connect(self.refresh_tables)
                except Exception:
                    pass

        self.refresh_current_snapshot()

    def _main_window_has_named_project(self):
        """主畫面目前是否不是「未命名」狀態。

        一般專案檔開啟/儲存後 current_file 會有值；RRF 等暫存匯入流程
        可能會把 current_file 清成 None，但視窗標題仍已有檔名，所以再以
        主視窗標題補判斷一次。
        """
        main = self.main_window
        if main is None:
            return False

        if getattr(main, "current_file", None):
            return True

        try:
            title = str(main.windowTitle() or "").strip()
        except Exception:
            title = ""

        if not title:
            return False

        unnamed_tokens = {"未命名"}
        try:
            translated = str(self.service.translate("filename.unnamed", "未命名") or "").strip()
            if translated:
                unnamed_tokens.add(translated)
        except Exception:
            pass

        return not any(token and token in title for token in unnamed_tokens)

    def sync_show_current_from_main_window(self):
        """每次開啟比對視窗時，依主程式是否已命名同步顯示目前設定。"""
        should_show = self._main_window_has_named_project()
        self.show_current_checkbox.setChecked(should_show)
        return should_show

    def _section_collapsed_height(self, section_widget):
        """取得區塊只剩標題列時需要保留的高度。"""
        try:
            height = section_widget.minimumSizeHint().height()
        except Exception:
            height = 0
        return max(30, int(height))

    def _set_compare_section_expanded(self, section, expanded):
        """切換區塊；兩區展開時由 QSplitter 讓使用者自由拖曳高度。"""
        expanded = bool(expanded)

        # 在收起任一區之前，先記住使用者目前手動拉出的上下比例。
        if (
            self._equipment_expanded
            and self._result_expanded
            and hasattr(self, "compare_splitter")
        ):
            sizes = self.compare_splitter.sizes()
            if len(sizes) >= 2 and sizes[0] > 0 and sizes[1] > 0:
                self._compare_splitter_sizes = sizes[:2]

        if section == "equipment":
            self._equipment_expanded = expanded
            self.equipment_table.setVisible(expanded)
            self.equipment_toggle_button.setText("▲ 收起" if expanded else "▼ 展開")
            section_widget = self.equipment_section_widget
        elif section == "result":
            self._result_expanded = expanded
            self.result_table.setVisible(expanded)
            self.result_toggle_button.setText("▲ 收起" if expanded else "▼ 展開")
            section_widget = self.result_section_widget
        else:
            return

        # 收起時只保留標題列；展開時解除高度上限，交回 splitter 控制。
        if expanded:
            section_widget.setMaximumHeight(16777215)
            section_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            collapsed_height = self._section_collapsed_height(section_widget)
            section_widget.setMaximumHeight(collapsed_height)
            section_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        section_widget.updateGeometry()

        if hasattr(self, "compare_splitter"):
            equipment_header_h = self._section_collapsed_height(self.equipment_section_widget)
            result_header_h = self._section_collapsed_height(self.result_section_widget)

            if self._equipment_expanded and self._result_expanded:
                # 兩區都展開：恢復使用者最後一次拖曳比例，之後可繼續任意拉動。
                self.compare_splitter.setMaximumHeight(16777215)
                self.compare_content_layout.setStretch(0, 1)
                self.compare_content_layout.setStretch(1, 0)
                QTimer.singleShot(0, lambda: self.compare_splitter.setSizes(self._compare_splitter_sizes))
            elif self._equipment_expanded:
                self.compare_splitter.setMaximumHeight(16777215)
                self.compare_content_layout.setStretch(0, 1)
                self.compare_content_layout.setStretch(1, 0)
                self.compare_splitter.setSizes([10000, result_header_h])
            elif self._result_expanded:
                self.compare_splitter.setMaximumHeight(16777215)
                self.compare_content_layout.setStretch(0, 1)
                self.compare_content_layout.setStretch(1, 0)
                self.compare_splitter.setSizes([equipment_header_h, 10000])
            else:
                # 兩區皆收起：splitter 只保留兩個標題列，高度其餘交給底部 spacer。
                max_height = equipment_header_h + result_header_h + self.compare_splitter.handleWidth()
                self.compare_splitter.setMaximumHeight(max_height)
                self.compare_splitter.setSizes([equipment_header_h, result_header_h])
                self.compare_content_layout.setStretch(0, 0)
                self.compare_content_layout.setStretch(1, 1)

        if hasattr(self, "compare_content_widget"):
            self.compare_content_widget.updateGeometry()

    def _toggle_equipment_section(self):
        self._set_compare_section_expanded("equipment", not self._equipment_expanded)

    def _toggle_result_section(self):
        self._set_compare_section_expanded("result", not self._result_expanded)

    def _mirror_compare_horizontal_scroll(self, source_table, target_table, value):
        """水平捲動任一表格時，同步另一張表的 X 偏移位置。"""
        if self._syncing_compare_horizontal_scroll:
            return

        self._syncing_compare_horizontal_scroll = True
        try:
            target_scrollbar = target_table.horizontalScrollBar()
            if target_scrollbar.value() != value:
                target_scrollbar.setValue(value)
        finally:
            self._syncing_compare_horizontal_scroll = False

    def _mirror_compare_column_width(self, source_table, target_table, logical_index, new_size):
        """使用者手動調整任一表格欄寬時，同步另一張表的同一欄。"""
        if self._syncing_compare_column_widths:
            return
        if logical_index < 0 or logical_index >= target_table.columnCount():
            return

        self._syncing_compare_column_widths = True
        try:
            if target_table.columnWidth(logical_index) != new_size:
                target_table.setColumnWidth(logical_index, new_size)
        finally:
            self._syncing_compare_column_widths = False

    def _sync_compare_table_widths(self):
        """取上下兩張表每一欄需要的最大寬度，並套用到兩張表。"""
        column_count = min(
            self.equipment_table.columnCount(),
            self.result_table.columnCount(),
        )
        if column_count <= 0:
            return

        self._syncing_compare_column_widths = True
        try:
            for col in range(column_count):
                width = max(
                    self.equipment_table.columnWidth(col),
                    self.result_table.columnWidth(col),
                )
                self.equipment_table.setColumnWidth(col, width)
                self.result_table.setColumnWidth(col, width)
        finally:
            self._syncing_compare_column_widths = False

    @staticmethod
    def _snapshot_compare_key(snapshot):
        """取得 Snapshot 在「比對基準」下拉選單中的穩定識別值。"""
        source = snapshot.get("source") if isinstance(snapshot, dict) else None
        if source:
            return str(source)
        return str(snapshot.get("name", "未命名")) if isinstance(snapshot, dict) else ""

    def _refresh_compare_base_combo(self, snapshots):
        """同步可選基準清單，並盡量保留使用者原本選擇。"""
        previous_key = self.compare_base_combo.currentData()

        self.compare_base_combo.blockSignals(True)
        try:
            self.compare_base_combo.clear()
            for snap in snapshots:
                self.compare_base_combo.addItem(
                    str(snap.get("name", "未命名")),
                    self._snapshot_compare_key(snap),
                )

            selected_index = -1
            if previous_key is not None:
                selected_index = self.compare_base_combo.findData(previous_key)
            if selected_index < 0 and snapshots:
                selected_index = 0
            if selected_index >= 0:
                self.compare_base_combo.setCurrentIndex(selected_index)
        finally:
            self.compare_base_combo.blockSignals(False)

        self.compare_base_combo.setEnabled(bool(snapshots))

    def _current_compare_base_index(self, snapshots):
        """回傳目前選定基準在 snapshots 中的索引；找不到時回傳 0。"""
        if not snapshots:
            return -1
        selected_key = self.compare_base_combo.currentData()
        for index, snap in enumerate(snapshots):
            if self._snapshot_compare_key(snap) == selected_key:
                return index
        return 0

    def _set_compare_base_from_column(self, logical_index):
        """直接點擊表格欄標題時，把該 Snapshot 設成比對基準。"""
        if logical_index is None or logical_index < 1:
            return
        combo_index = logical_index - 1
        if 0 <= combo_index < self.compare_base_combo.count():
            self.compare_base_combo.setCurrentIndex(combo_index)

    def _all_snapshots(self):
        result = []
        if self.show_current_checkbox.isChecked() and self.current_snapshot is not None:
            result.append(self.current_snapshot)
        result.extend(self.json_snapshots)
        return result

    def _selected_json_index(self):
        """由目前可見表格欄位找到對應的 json_snapshots index。"""
        visible_snapshots = self._all_snapshots()
        candidates = [
            self.equipment_table.currentColumn(),
            self.result_table.currentColumn(),
        ]
        for col in candidates:
            # 第 0 欄固定是「項目」，第 1 欄起依目前勾選狀態排列 Snapshot。
            if col is None or col < 1:
                continue
            snapshot_index = col - 1
            if not 0 <= snapshot_index < len(visible_snapshots):
                continue

            selected_snapshot = visible_snapshots[snapshot_index]
            # 「目前設定」不能用移除專案檔功能刪除。
            if selected_snapshot is self.current_snapshot or selected_snapshot.get("source") == "current":
                continue

            for idx, json_snapshot in enumerate(self.json_snapshots):
                if selected_snapshot is json_snapshot:
                    return idx
                if selected_snapshot.get("source") == json_snapshot.get("source"):
                    return idx
        return None

    def refresh_current_snapshot(self):
        try:
            self.status_label.setText("正在更新目前設定...")
            QApplication.processEvents()
            self.current_snapshot = self.service.create_current_compare_snapshot("目前設定")
            self.refresh_tables()
            self.status_label.setText("目前設定已更新")
        except Exception as exc:
            self.status_label.setText("更新失敗")
            QMessageBox.critical(self, "多裝備比對", f"更新目前設定失敗：\n{exc}")

    def add_json_files(self):
        default_dir = os.path.join(os.getcwd(), "裝備")
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "選擇要比較的專案檔",
            default_dir,
            "專案檔 (*.json)",
        )
        if not paths:
            return

        # Phase 13: JSON comparison is headless. It no longer loads/restores MainWindow.
        try:
            for i, path in enumerate(paths, 1):
                self.status_label.setText(f"計算 {i}/{len(paths)}：{Path(path).name}")
                QApplication.processEvents()
                snapshot = self.service.create_json_compare_snapshot(path)
                replaced = False
                for idx, old in enumerate(self.json_snapshots):
                    if old.get("source") == path:
                        self.json_snapshots[idx] = snapshot
                        replaced = True
                        break
                if not replaced:
                    self.json_snapshots.append(snapshot)
        except Exception as exc:
            QMessageBox.critical(self, "多裝備比對", f"專案檔比對計算失敗：\n{exc}")

        self.refresh_tables()
        self.status_label.setText(f"已載入 {len(self.json_snapshots)} 個專案檔")


    def remove_selected_json(self):
        idx = self._selected_json_index()
        if idx is None:
            QMessageBox.information(self, "多裝備比對", "請先在表格中點選要移除的專案檔欄位。")
            return
        self.json_snapshots.pop(idx)
        self.refresh_tables()

    def clear_jsons(self):
        self.json_snapshots.clear()
        self.refresh_tables()
        self.status_label.setText("專案檔已清空")

    @staticmethod
    def _ordered_keys(snapshots, field_name):
        seen = set()
        ordered = []
        for snap in snapshots:
            for key in snap.get(field_name, {}).keys():
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        return ordered

    @staticmethod
    def _equipment_effect_order_pattern_matches(pattern, value):
        """EQUIPMENT_EFFECT_ORDER_MAP 的 * 代表任意長度、任意字元。

        除了 * 以外，其餘字元都當作普通文字，不使用 regex 特殊語法。
        """
        pattern = str(pattern or "")
        value = str(value or "")

        if "*" not in pattern:
            return pattern == value

        regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
        return re.match(regex, value, flags=re.DOTALL) is not None

    @classmethod
    def _equipment_effect_order_rank(cls, key):
        """讀取 EQUIPMENT_EFFECT_ORDER_MAP。

        支援：
        - 完整列名
        - 效果名含單位
        - 純效果名
        - * 萬用字元

        完全相符優先；同時符合多個 * 時採用最小 rank。
        """
        prefix = "裝備總效果 / "
        key = str(key or "")
        effect_label = key[len(prefix):] if key.startswith(prefix) else key
        effect_without_unit = re.sub(r"\s*\[[^\]]*\]\s*$", "", effect_label).strip()

        candidates = (key, effect_label, effect_without_unit)

        # 1. 先找完全相符，保留原本行為，而且精確規則優先。
        for candidate in candidates:
            if candidate in EQUIPMENT_EFFECT_ORDER_MAP:
                try:
                    return float(EQUIPMENT_EFFECT_ORDER_MAP[candidate])
                except (TypeError, ValueError):
                    return 0.0

        # 2. 再找含 * 的規則。
        wildcard_ranks = []
        for pattern, rank in EQUIPMENT_EFFECT_ORDER_MAP.items():
            pattern = str(pattern or "")
            if "*" not in pattern:
                continue

            matched = any(
                cls._equipment_effect_order_pattern_matches(pattern, candidate)
                for candidate in candidates
            )
            if not matched:
                continue

            try:
                wildcard_ranks.append(float(rank))
            except (TypeError, ValueError):
                wildcard_ranks.append(0.0)

        if wildcard_ranks:
            return min(wildcard_ranks)

        return None

    @classmethod
    def _ordered_result_keys(cls, keys):
        """計算結果預設順序。

        1. 原本計算順序（排除下列特殊群組）
        2. 角色等級
        3. 素質
        4. 特性素質
        5. 裝備總效果（最後，內部可由 EQUIPMENT_EFFECT_ORDER_MAP 寫死）
        """
        original = list(keys or [])
        main_keys = []
        level_keys = []
        stat_keys = []
        trait_keys = []
        effect_rows = []

        for index, key in enumerate(original):
            if str(key).startswith("裝備總效果 / "):
                effect_rows.append((index, key))
            elif str(key).startswith("角色等級 / "):
                level_keys.append(key)
            elif str(key).startswith("素質 / "):
                stat_keys.append(key)
            elif str(key).startswith("特性素質 / "):
                trait_keys.append(key)
            else:
                main_keys.append(key)

        # 有寫 MAP 的裝備效果優先依 MAP；沒寫的維持 Core 原始順序並排在後面。
        def effect_sort(item):
            original_index, key = item
            rank = cls._equipment_effect_order_rank(key)
            if rank is None:
                return (1, original_index, original_index)
            return (0, rank, original_index)

        sorted_effects = [key for _idx, key in sorted(effect_rows, key=effect_sort)]
        return main_keys + level_keys + stat_keys + trait_keys + sorted_effects

    def _update_result_filter_button_text(self):
        count = len(self._result_filter_selected_keys)
        if count:
            self.result_filter_button.setText(f"選擇過濾 ({count})")
        else:
            self.result_filter_button.setText("選擇過濾")

    def _result_filter_matching_keys(self, search_text=None):
        """回傳目前搜尋條件下的選項；已勾選仍保持置頂。"""
        if search_text is None:
            search_text = (
                self._result_filter_search.text()
                if self._result_filter_search is not None
                else ""
            )
        query = str(search_text or "").strip().casefold()

        ordered = list(self._result_filter_available_keys)
        selected = [key for key in ordered if key in self._result_filter_selected_keys]
        unselected = [key for key in ordered if key not in self._result_filter_selected_keys]
        display_keys = selected + unselected

        if query:
            display_keys = [
                key for key in display_keys
                if query in str(key).casefold()
            ]
        return display_keys

    def _rebuild_result_filter_list(self, search_text=None):
        if self._result_filter_list is None:
            return

        display_keys = self._result_filter_matching_keys(search_text)

        self._rebuilding_result_filter_list = True
        try:
            self._result_filter_list.clear()
            for key in display_keys:
                item = QListWidgetItem(str(key))
                item.setData(Qt.UserRole, key)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.Checked if key in self._result_filter_selected_keys else Qt.Unchecked
                )
                self._result_filter_list.addItem(item)
        finally:
            self._rebuilding_result_filter_list = False


    def _on_result_filter_item_changed(self, item):
        if self._rebuilding_result_filter_list or item is None:
            return
        key = item.data(Qt.UserRole)
        if not key:
            return

        if item.checkState() == Qt.Checked:
            self._result_filter_selected_keys.add(key)
        else:
            self._result_filter_selected_keys.discard(key)

        self._update_result_filter_button_text()

        # 連續拖曳勾選期間不能立刻重建清單，否則項目會因「勾選置頂」
        # 在滑鼠下方重排，導致拖曳中斷。滑鼠放開後一次 refresh 即可。
        if (
            self._result_filter_list is not None
            and hasattr(self._result_filter_list, "is_check_drag_active")
            and self._result_filter_list.is_check_drag_active()
        ):
            return

        # 一般單點/鍵盤勾選仍立即刷新並把已勾項目置頂。
        self.refresh_tables()

    def _finish_result_filter_drag_selection(self):
        """滑鼠拖曳勾選結束後，一次刷新表格並把勾選項目置頂。"""
        self._update_result_filter_button_text()
        self.refresh_tables()

    def _clear_result_filter_selection(self):
        self._result_filter_selected_keys.clear()
        self._update_result_filter_button_text()
        self.refresh_tables()

    def _open_result_filter_dialog(self):
        if self._result_filter_dialog is None:
            dialog = QDialog(self)
            dialog.setWindowTitle("選擇過濾")
            dialog.resize(620, 680)
            dialog.setAttribute(Qt.WA_DeleteOnClose, False)

            layout = QVBoxLayout(dialog)
            hint = QLabel(
                "沒有勾選＝全部顯示；有勾選＝只顯示勾選項目。"
                "勾選中的項目會自動置頂。"
            )
            layout.addWidget(hint)

            self._result_filter_search = QLineEdit()
            self._result_filter_search.setPlaceholderText("搜尋計算結果項目...")
            self._result_filter_search.setClearButtonEnabled(True)
            layout.addWidget(self._result_filter_search)

            drag_hint = QLabel(
                "可從左側勾選框按住滑鼠，往上/下拖曳連續勾選或取消"
            )
            layout.addWidget(drag_hint)

            self._result_filter_list = DragCheckListWidget()
            self._result_filter_list.setAlternatingRowColors(True)
            self._result_filter_list.check_drag_finished_callback = (
                self._finish_result_filter_drag_selection
            )
            layout.addWidget(self._result_filter_list, 1)

            buttons = QHBoxLayout()
            clear_button = QPushButton("清除勾選")
            close_button = QPushButton("關閉")
            buttons.addWidget(clear_button)
            buttons.addStretch(1)
            buttons.addWidget(close_button)
            layout.addLayout(buttons)

            self._result_filter_search.textChanged.connect(self._rebuild_result_filter_list)
            self._result_filter_list.itemChanged.connect(self._on_result_filter_item_changed)
            clear_button.clicked.connect(self._clear_result_filter_selection)
            close_button.clicked.connect(dialog.close)
            self._result_filter_dialog = dialog

        self._rebuild_result_filter_list()
        self._result_filter_dialog.show()
        self._result_filter_dialog.raise_()
        self._result_filter_dialog.activateWindow()
        if self._result_filter_search is not None:
            self._result_filter_search.setFocus()

    def _setup_table(self, table, snapshots, row_count):
        headers = ["項目"] + [snap.get("name", "未命名") for snap in snapshots]
        table.clear()
        table.setRowCount(row_count)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(False)

        # 先給合理的最小寬度；內容填完後 _auto_resize_table() 會再依實際文字放大。
        table.setColumnWidth(0, 190)
        for col in range(1, len(headers)):
            table.setColumnWidth(col, 220)

    @staticmethod
    def _auto_resize_table(table):
        """依完整文字自動放大欄寬，不截斷裝備名稱 / BUFF / 詞條。"""
        table.resizeColumnsToContents()
        table.resizeRowsToContents()

        for col in range(table.columnCount()):
            minimum = 190 if col == 0 else 220
            width = max(minimum, table.columnWidth(col))

            # result table 的差異欄位可能使用 QLabel rich text，Qt 的
            # resizeColumnsToContents 不一定會把 cellWidget sizeHint 算進去，這裡補算。
            for row in range(table.rowCount()):
                widget = table.cellWidget(row, col)
                if widget is not None:
                    try:
                        width = max(width, widget.sizeHint().width() + 24)
                    except Exception:
                        pass
            table.setColumnWidth(col, width)

    @staticmethod
    def _make_result_label(display, diff_text=None, higher=None, bold=False):
        """結果 cell：只有括號內差異值上色，右欄較高綠色、較低紅色。"""
        import html

        label = QLabel()
        label.setTextFormat(Qt.RichText)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setMargin(3)

        base_html = html.escape(str(display or ""))
        if bold:
            base_html = f"<b>{base_html}</b>"

        if diff_text is not None and higher is not None:
            color = "#198754" if higher else "#dc3545"
            diff_html = html.escape(str(diff_text))
            # 括號本身維持一般顏色，只將括號內的差異文字染色。
            base_html += f'&nbsp;&nbsp;(<span style="color:{color};">{diff_html}</span>)'

        label.setText(base_html)
        return label

    def refresh_tables(self):
        snapshots = self._all_snapshots()
        self._refresh_compare_base_combo(snapshots)
        if not snapshots:
            self.result_title_label.setText("計算結果（可選擇比對基準）")
            self._result_filter_available_keys = []
            if self._result_filter_dialog is not None:
                self._rebuild_result_filter_list()
            for table in (self.equipment_table, self.result_table):
                table.clear()
                table.setRowCount(0)
                table.setColumnCount(0)
            return

        base_index = self._current_compare_base_index(snapshots)
        base_name = snapshots[base_index].get("name", "未命名") if base_index >= 0 else "未命名"
        self.equipment_title_label.setText(f"裝備差異（比對基準：{base_name}；可點欄名切換）")        
        self.result_title_label.setText(f"計算結果（比對基準：{base_name}；可點欄名切換）")

        # 自動重算欄寬期間先暫停「手動拖曳同步」，讓上下兩張表各自算出
        # 真正需要的內容寬度；最後再取兩者最大值統一套用。
        self._syncing_compare_column_widths = True
        try:
            self._refresh_equipment_table(snapshots)
            self._refresh_result_table(snapshots)
        finally:
            self._syncing_compare_column_widths = False

        self._sync_compare_table_widths()

    def _refresh_equipment_table(self, snapshots):
        keys = self._ordered_keys(snapshots, "equipment")
        hide_same = self.only_diff_checkbox.isChecked() and len(snapshots) > 1

        visible_keys = []
        for key in keys:
            # 「技能」是程式內部的自訂部位，不列入裝備比較，也不提供顯示開關。
            # BUFF 會由 Snapshot 另外加入，仍正常顯示。
            if key.startswith("技能 / "):
                continue

            values = [str(s.get("equipment", {}).get(key, "")) for s in snapshots]
            if hide_same and len(set(values)) <= 1:
                continue
            visible_keys.append(key)

        self._setup_table(self.equipment_table, snapshots, len(visible_keys))

        for row, key in enumerate(visible_keys):
            label_item = QTableWidgetItem(key)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            self.equipment_table.setItem(row, 0, label_item)

            values = [str(s.get("equipment", {}).get(key, "")) for s in snapshots]
            is_diff = len(set(values)) > 1
            for col, value in enumerate(values, 1):
                # 不做任何長度截斷；詞條 / BUFF 保留完整解析文字。
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setToolTip(value)
                if is_diff:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.equipment_table.setItem(row, col, item)

        self._auto_resize_table(self.equipment_table)

    def _find_main_effect_filter_checkbox(self, kind):
        """先找常見 attribute，找不到就直接依 checkbox 顯示文字辨識。"""
        main = self.main_window
        if main is None:
            return None

        attr_candidates = {
            "physical": (
                "hide_physical_checkbox",
                "hide_physical_effect_checkbox",
                "hide_physical_effects_checkbox",
            ),
            "magical": (
                "hide_magical_checkbox",
                "hide_magic_checkbox",
                "hide_magical_effect_checkbox",
                "hide_magical_effects_checkbox",
            ),
        }

        for attr_name in attr_candidates.get(kind, ()):
            checkbox = getattr(main, attr_name, None)
            if checkbox is not None and hasattr(checkbox, "isChecked"):
                return checkbox

        expected = "隱藏物理" if kind == "physical" else "隱藏魔法"
        try:
            for checkbox in main.findChildren(QCheckBox):
                try:
                    if expected in str(checkbox.text() or ""):
                        return checkbox
                except Exception:
                    continue
        except Exception:
            pass

        return None

    def _main_effect_display_hide_flags(self):
        """取得主程式效果顯示選項；只供 MultiCompare UI 使用。"""
        physical_checkbox = self._find_main_effect_filter_checkbox("physical")
        magical_checkbox = self._find_main_effect_filter_checkbox("magical")

        try:
            hide_physical = bool(
                physical_checkbox is not None and physical_checkbox.isChecked()
            )
        except Exception:
            hide_physical = False

        try:
            hide_magical = bool(
                magical_checkbox is not None and magical_checkbox.isChecked()
            )
        except Exception:
            hide_magical = False

        return hide_physical, hide_magical

    @staticmethod
    def _effect_row_damage_category(key):
        """只分類裝備總效果列；傷害計算列永遠不會被此功能隱藏。"""
        prefix = "裝備總效果 / "
        key = str(key or "")
        if not key.startswith(prefix):
            return None

        label = key[len(prefix):]
        upper = label.upper()

        # 先判斷魔法，避免 MATK 因包含 ATK 被誤判成物理。
        magical_text_keywords = ("魔法", "變動詠唱", "固定詠唱", "詠唱")
        magical_tokens = ("MATK", "S.MATK", "MDEF", "MRES")
        if any(keyword in label for keyword in magical_text_keywords):
            return "magical"
        for token in magical_tokens:
            pattern = r"(?<![A-Z0-9_.])" + re.escape(token) + r"(?![A-Z0-9_.])"
            if re.search(pattern, upper):
                return "magical"

        physical_text_keywords = (
            "物理", "近距離", "遠距離", "爆擊", "暴擊", "武器", "誘導攻擊",
        )
        physical_tokens = ("P.ATK", "ATK", "CRI", "C.RATE", "HIT")
        if any(keyword in label for keyword in physical_text_keywords):
            return "physical"
        for token in physical_tokens:
            pattern = r"(?<![A-Z0-9_.])" + re.escape(token) + r"(?![A-Z0-9_.])"
            if re.search(pattern, upper):
                return "physical"

        return None

    def _hide_result_row_by_main_effect_filter(self, key):
        """只隱藏效果顯示列；總傷害/單次傷害等 Core 計算結果不受影響。"""
        hide_physical, hide_magical = self._main_effect_display_hide_flags()
        if not hide_physical and not hide_magical:
            return False

        category = self._effect_row_damage_category(key)
        if category == "physical" and hide_physical:
            return True
        if category == "magical" and hide_magical:
            return True
        return False

    @staticmethod
    def _normalized_monster_target_value(value):
        return re.sub(r"\s+", "", str(value or "")).casefold()

    @classmethod
    def _effect_matches_baseline_monster_target(cls, key, base_snap):
        """只過濾明確限定體型/種族/屬性/階級的裝備效果；不碰傷害計算。"""
        prefix = "裝備總效果 / "
        key = str(key or "")
        if not key.startswith(prefix):
            return True

        label = key[len(prefix):]
        label = re.sub(r"\s*\[[^\]]*\]\s*$", "", label).strip()
        compact = re.sub(r"\s+", "", label)
        compact_fold = compact.casefold()

        target = dict((base_snap or {}).get("monster_target") or {})

        # 相容舊 snapshot：從顯示文字回推
        if not target:
            display = str(
                (base_snap or {})
                .get("results", {})
                .get("魔物 / 體種屬階", {})
                .get("display", "")
                or ""
            )
            parts = [part.strip() for part in display.split("/")]
            if len(parts) >= 4:
                element_part = re.sub(
                    r"\s*Lv\.\s*\d+.*$",
                    "",
                    parts[2],
                    flags=re.IGNORECASE,
                ).strip()
                target = {
                    "size": parts[0],
                    "race": parts[1],
                    "element": element_part,
                    "class": parts[3],
                }

        target_size = cls._normalized_monster_target_value(target.get("size"))
        target_race = cls._normalized_monster_target_value(target.get("race"))
        target_element = cls._normalized_monster_target_value(target.get("element"))
        target_class = cls._normalized_monster_target_value(target.get("class"))

        # 體型
        size_terms = ("小型", "中型", "大型")
        mentioned_sizes = {term for term in size_terms if term in compact}
        if mentioned_sizes:
            normalized_sizes = {
                cls._normalized_monster_target_value(term)
                for term in mentioned_sizes
            }
            if target_size not in normalized_sizes:
                return False

        # 種族
        race_terms = (
            "無形", "不死", "動物", "植物", "昆蟲",
            "魚貝", "惡魔", "人形", "天使", "龍族",
        )
        mentioned_races = set()
        for term in race_terms:
            if term not in compact:
                continue
            if term == "不死":
                element_only = (
                    ("不死屬性" in compact or "不死屬" in compact)
                    and not any(
                        token in compact
                        for token in ("不死種族", "不死族", "不死怪", "不死魔物")
                    )
                )
                if element_only:
                    continue
            mentioned_races.add(term)

        race_context = (
            "種族" in compact
            or "怪" in compact
            or "魔物" in compact
            or "對象" in compact
            or compact.startswith("對")
        )
        if mentioned_races and race_context:
            normalized_races = {
                cls._normalized_monster_target_value(term)
                for term in mentioned_races
            }
            if target_race not in normalized_races:
                return False

        # 屬性：只處理「對某屬性目標」類，避免把火屬性技能增傷誤當目標限定
        element_aliases = {
            "無": ("無屬性", "無屬"),
            "水": ("水屬性", "水屬"),
            "地": ("地屬性", "地屬"),
            "火": ("火屬性", "火屬"),
            "風": ("風屬性", "風屬"),
            "毒": ("毒屬性", "毒屬"),
            "聖": ("聖屬性", "聖屬"),
            "暗": ("暗屬性", "暗屬"),
            "念": ("念屬性", "念屬"),
            "不死": ("不死屬性", "不死屬"),
        }

        mentioned_elements = set()
        for canonical, aliases in element_aliases.items():
            for alias in aliases:
                if (
                    re.search(rf"對{re.escape(alias)}(?:對象|怪|魔物|敵)?", compact)
                    or re.search(rf"{re.escape(alias)}(?:對象|怪|魔物|敵)", compact)
                ):
                    mentioned_elements.add(canonical)
                    break

        if mentioned_elements:
            baseline_element = None
            for canonical, aliases in element_aliases.items():
                candidates = (canonical,) + aliases
                if any(
                    cls._normalized_monster_target_value(candidate) == target_element
                    for candidate in candidates
                ):
                    baseline_element = canonical
                    break
            if baseline_element not in mentioned_elements:
                return False

        # 階級
        mentioned_classes = set()
        if "首領" in compact or "boss" in compact_fold:
            mentioned_classes.add("boss")
        if (
            "一般階級" in compact
            or "普通階級" in compact
            or "一般怪" in compact
            or "普通怪" in compact
        ):
            mentioned_classes.add("normal")

        if mentioned_classes:
            baseline_class = None
            if "首領" in target_class or "boss" in target_class:
                baseline_class = "boss"
            elif (
                "一般" in target_class
                or "普通" in target_class
                or "normal" in target_class
            ):
                baseline_class = "normal"

            if baseline_class is not None and baseline_class not in mentioned_classes:
                return False

        return True

    def _refresh_result_table(self, snapshots):
        # 預設：原本計算順序 -> 角色等級 -> 素質 -> 特性素質 -> 裝備總效果最後。
        # 裝備總效果內部順序由檔案最上方 EQUIPMENT_EFFECT_ORDER_MAP 控制。
        keys = self._ordered_result_keys(self._ordered_keys(snapshots, "results"))

        # 「選擇過濾」的選項就是本頁全部計算結果，順序與表格預設一致。
        self._result_filter_available_keys = list(keys)
        available_set = set(keys)
        self._result_filter_selected_keys.intersection_update(available_set)
        self._update_result_filter_button_text()
        if self._result_filter_dialog is not None:
            self._rebuild_result_filter_list()

        hide_same = self.only_diff_checkbox.isChecked() and len(snapshots) > 1
        base_index = self._current_compare_base_index(snapshots)
        base_snap = snapshots[base_index] if 0 <= base_index < len(snapshots) else snapshots[0]
        show_baseline_monster_target = self.baseline_monster_target_checkbox.isChecked()
        monster_target_key = "魔物 / 體種屬階"

        visible_keys = []
        always_show_keys = {"技能名稱", "技能等級", "技能攻擊屬性"}
        if show_baseline_monster_target:
            always_show_keys.add(monster_target_key)
        for key in keys:
            # 只把「裝備總效果 / ...」列依主 UI 選項隱藏。
            # 傷害結果本身仍由完整效果計算且保持顯示。
            if self._hide_result_row_by_main_effect_filter(key):
                continue

            # 勾選「只顯示基準魔物的體種屬階」時，
            # 其他體型 / 種族 / 屬性 / 階級限定效果不顯示。
            # 只做 UI 過濾，不重新計算傷害。
            if (
                show_baseline_monster_target
                and not self._effect_matches_baseline_monster_target(key, base_snap)
            ):
                continue

            # 自訂「選擇過濾」：沒有勾選時不限制；有勾選時只保留勾選項目。
            if (
                self._result_filter_selected_keys
                and key not in self._result_filter_selected_keys
            ):
                continue

            values = [s.get("results", {}).get(key, {}).get("display", "") for s in snapshots]
            # 技能名稱 / 技能等級 / 技能攻擊屬性是本次比較的基本上下文。
            # 勾選「只顯示基準魔物的體種屬階」時，該列也固定保留。
            if key not in always_show_keys and hide_same and len(set(values)) <= 1:
                continue
            visible_keys.append(key)

        self._setup_table(self.result_table, snapshots, len(visible_keys))

        for row, key in enumerate(visible_keys):
            label_item = QTableWidgetItem(key)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            self.result_table.setItem(row, 0, label_item)

            if key == monster_target_key and show_baseline_monster_target:
                baseline_entry = base_snap.get("results", {}).get(key, {})
                all_display = [baseline_entry.get("display", "") for _snapshot in snapshots]
            else:
                all_display = [
                    s.get("results", {}).get(key, {}).get("display", "")
                    for s in snapshots
                ]
            is_diff = len(set(all_display)) > 1

            for col, snap in enumerate(snapshots, 1):
                if key == monster_target_key and show_baseline_monster_target:
                    entry = base_snap.get("results", {}).get(key)
                else:
                    entry = snap.get("results", {}).get(key)
                display = "" if not entry else entry.get("display", "")
                diff_text = None
                higher = None

                # 每一欄都與使用者選定的 Snapshot 比較；基準欄本身不顯示差值。
                # 因此基準可以是目前設定、第一個專案檔，也可以是中間/最右側任一欄。
                # 相對基準數值較高 -> 括號內綠字；較低 -> 括號內紅字。
                snapshot_index = col - 1
                if snapshot_index != base_index and entry:
                    base_entry = base_snap.get("results", {}).get(key)
                    if base_entry:
                        old_num = base_entry.get("number")
                        new_num = entry.get("number")
                        if old_num is not None and new_num is not None and old_num != new_num:
                            diff = new_num - old_num
                            suffix = entry.get("suffix", "")
                            higher = new_num > old_num

                            # 「裝備總效果 / ... [%]」本身已是百分比數值，
                            # 差異直接用百分點相減：
                            # 94% -> 113% 顯示 +19%，不是相對成長率 +20.21%。
                            is_equipment_percent_effect = (
                                str(key).startswith("裝備總效果 / ")
                                and suffix == "%"
                            )

                            if is_equipment_percent_effect:
                                if abs(diff - round(diff)) < 1e-9:
                                    diff_text = f"{int(round(diff)):+,}%"
                                else:
                                    diff_text = f"{diff:+.2f}%"
                            elif "傷害" in key and old_num != 0:
                                pct = diff / old_num * 100.0
                                diff_text = f"{pct:+.2f}%"
                            else:
                                if abs(diff - round(diff)) < 1e-9:
                                    number_text = f"{int(round(diff)):+,}"
                                else:
                                    number_text = f"{diff:+.2f}"
                                diff_text = f"{number_text}{suffix}"

                label = self._make_result_label(
                    display,
                    diff_text=diff_text,
                    higher=higher,
                    bold=is_diff,
                )
                if entry:
                    label.setToolTip(entry.get("tooltip") or entry.get("display", ""))
                self.result_table.setCellWidget(row, col, label)

        self._auto_resize_table(self.result_table)


def open_multi_compare_window(main_window, context=None):
    """建立/顯示獨立多裝備比對視窗。

    主程式只需要呼叫這個入口；計算與比較細節留在本模組。
    """
    service = getattr(main_window, "_multi_compare_service", None)
    if not isinstance(service, MultiCompareService):
        service = MultiCompareService(main_window, context)
        main_window._multi_compare_service = service
    else:
        service.update_context(context)

    dialog = getattr(main_window, "multi_compare_window", None)
    if dialog is None:
        dialog = MultiCompareDialog(service)
        main_window.multi_compare_window = dialog

        def _clear_dialog_ref(*_args):
            if getattr(main_window, "multi_compare_window", None) is dialog:
                main_window.multi_compare_window = None

        dialog.destroyed.connect(_clear_dialog_ref)
    else:
        dialog.service.update_context(context)
        dialog.sync_show_current_from_main_window()

    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog


__all__ = [
    "MultiCompareService",
    "MultiCompareDialog",
    "open_multi_compare_window",
]
