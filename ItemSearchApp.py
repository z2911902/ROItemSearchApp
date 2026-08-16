#部分資料取自ROCalculator,搜尋 ROCalculator 可以知道哪些有使用
Version = "v0.7.1-260815"
Server_area = "TwRO"

import sys, builtins, time
import os
import json
from PySide6.QtCore import QThread, Signal, Qt, QMetaObject, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QPlainTextEdit, QLabel
import enchant #載入附魔工具
import lapine_upgrade #載入 LapineUpgradeBox 附魔工具
import skill_tree #載入技能樹
import reform_viewer #載入改造工具
from rrf_to_App import run_rrf_main#載入rrf轉換
from monster_lookup_dialog import MonsterLookupDialog#查詢怪物
from RRF_compile_damage_view import MainUI#載入RRF傷害計算器
from Damage_view import DamageCalculator
from multi_compare import open_multi_compare_window
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone

import requests

#介面縮放倍率設定 0.5~3倍
DEFAULT_UI_SCALE_FACTOR = 1.0
UI_SCALE_FACTOR_MIN = 0.5
UI_SCALE_FACTOR_MAX = 3.0


def get_app_base_dir():
    """取得程式根目錄；打包後使用 exe 所在目錄。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_config_path():
    """回傳共用設定檔路徑。"""
    data_dir = os.path.join(get_app_base_dir(), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "config.json")


def normalize_ui_scale_factor(value, default=DEFAULT_UI_SCALE_FACTOR) -> float:
    """將設定值轉為可用的 Qt 縮放倍率，避免無效值造成啟動異常。"""
    try:
        scale = float(value)
    except (TypeError, ValueError):
        return float(default)

    if not UI_SCALE_FACTOR_MIN <= scale <= UI_SCALE_FACTOR_MAX:
        return float(default)
    return scale


def load_config_data() -> dict:
    """讀取 config.json；檔案不存在或格式錯誤時回傳空設定。"""
    try:
        with open(get_config_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def get_startup_ui_scale_factor(argv=None) -> float:
    """取得啟動縮放倍率；命令列 x倍率 優先於 config.json。"""
    argv = argv or sys.argv

    # 保留舊用法，並支援 x1.25、x1.5、x2 等倍率。
    for arg in argv[1:]:
        if not isinstance(arg, str) or not arg.lower().startswith("x"):
            continue
        try:
            return normalize_ui_scale_factor(float(arg[1:]))
        except (TypeError, ValueError):
            continue

    cfg = load_config_data()
    return normalize_ui_scale_factor(
        cfg.get("ui_scale_factor", DEFAULT_UI_SCALE_FACTOR)
    )


def format_ui_scale_factor(scale: float) -> str:
    """輸出適合 QT_SCALE_FACTOR 與 JSON 使用的精簡數字字串。"""
    return f"{normalize_ui_scale_factor(scale):g}"


class LangManager:
    """Simple JSON language-pack loader for user-facing UI text."""
    current_lang = "zh_TW"
    fallback_lang = "zh_TW"
    translations = {}
    fallback_translations = {}

    @classmethod
    def _base_dir(cls):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    @classmethod
    def _read_lang_file(cls, lang_code):
        path = os.path.join(cls._base_dir(), "lang", f"{lang_code}.json")
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return json.load(f)
        except Exception as e:
            print(f"語言包載入失敗：{path}，{e}")
            return {}

    @classmethod
    def load(cls, lang_code="zh_TW"):
        cls.current_lang = lang_code or cls.fallback_lang
        cls.fallback_translations = cls._read_lang_file(cls.fallback_lang)
        cls.translations = cls._read_lang_file(cls.current_lang)

    @classmethod
    def tr(cls, key, default=None, **kwargs):
        text = cls.translations.get(
            key,
            cls.fallback_translations.get(key, default if default is not None else key)
        )
        try:
            return text.format(**kwargs)
        except Exception:
            return text


def tr(key, default=None, **kwargs):
    return LangManager.tr(key, default, **kwargs)


LangManager.load("zh_TW")


class InitWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(str)
    done_signal = Signal(object)
    
    def __init__(self, app_instance=None):
        super().__init__()
        self.app_instance = app_instance  # 接收主程式的物件

    def run(self):
        original_print = builtins.print

        def custom_print(*args, **kwargs):
            msg = " ".join(str(a) for a in args)
            end = kwargs.get("end", "\n")

            if end == "\r":
                self.progress_signal.emit(msg)
            else:
                self.log_signal.emit(msg)

            # ✅ 同時即時印出（不等事件迴圈）
            original_print(*args, **kwargs, flush=True)


        builtins.print = custom_print

        try:
            #print("開始載入資料...")
            data = None
            if self.app_instance:
                mode = "online_only"
                if self.app_instance and hasattr(self.app_instance, "get_update_mode"):
                    mode = self.app_instance.get_update_mode() or "online_only"
                data = self.app_instance.dataloading(mode=mode)

            #print("載入完成！")
            self.done_signal.emit(data) 
        except Exception as e:
            print(f"初始化發生錯誤：{e}")
        finally:
            builtins.print = original_print


from PySide6.QtWidgets import QProgressDialog, QMessageBox, QDialog
from recompile_service import RecompileService


class LoadingDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(tr("window.loading"))
        self.resize(500, 200)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        self.label = QLabel(tr("label.loading"))
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)

        layout.addWidget(self.label)
        layout.addWidget(self.text)

    def append_text(self, msg: str):
        self.text.appendPlainText(msg)

    def update_progress(self, msg: str):
        self.label.setText(msg)



import os
import subprocess

def compile_ui_files(ui_dir="UI"):
    """
    將 ui_dir 資料夾下的所有 .ui 檔案轉換成 .py
    """
    for file in os.listdir(ui_dir):
        if file.endswith(".ui"):
            ui_path = os.path.join(ui_dir, file)
            py_path = os.path.splitext(ui_path)[0] + ".py"

            # 呼叫 pyside6-uic
            cmd = ["pyside6-uic", ui_path, "-o", py_path]
            print(f"[UI] 轉換 {ui_path} → {py_path}")
            try:
                subprocess.run(cmd, check=True, shell=True)
            except Exception as e:
                print(f"[UI] 轉換失敗: {e}")

# === 主程式執行前，先自動轉換 UI ===
#compile_ui_files() #應該是不會再用這個了 先註解掉

import importlib.util
import sys
import re
import subprocess
import os
import json
import math
from collections import defaultdict

# === STAGE 17 DESKTOP CORE DAMAGE PRIMITIVES ===
from ro_core import (
    stage17_calc_final_def_damage as _core_stage17_calc_final_def_damage,
    stage17_calc_final_mdef_damage as _core_stage17_calc_final_mdef_damage,
    stage17_calc_final_res_damage as _core_stage17_calc_final_res_damage,
    stage17_calculate_target_defense_factors as _core_stage17_calculate_target_defense_factors,
    stage17_calc_weapon_refine_atk as _core_stage17_calc_weapon_refine_atk,
    stage17_calc_weapon_refine_matk as _core_stage17_calc_weapon_refine_matk,
    stage17_get_damage_multiplier as _core_stage17_get_damage_multiplier,
    stage17_get_size_penalty as _core_stage17_get_size_penalty,
    stage17_apply_stepwise as _core_stage17_apply_stepwise,
    stage17_eval_formula_with_vars as _core_stage17_eval_formula_with_vars,
    stage17_replace_custom_calls as _core_stage17_replace_custom_calls,
    stage17_replace_gsklv_calls as _core_stage17_replace_gsklv_calls,
    stage17_replace_gusklv_calls as _core_stage17_replace_gusklv_calls,
    stage17_replace_size_calls as _core_stage17_replace_size_calls,
)
# === STAGE 21.24 DESKTOP/WEB SHARED SKILL TIMING CORE ===
from ro_core import (
    stage24_calculate_skill_timing_from_effects as _core_stage24_calculate_skill_timing_from_effects,
    stage25_calculate_no_cast_from_effects as _core_stage25_calculate_no_cast_from_effects,
)

import pandas as pd
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QPoint, QEvent, QPropertyAnimation, QEasingCurve, QUrl
from PySide6.QtGui import QFont ,QAction,QIntValidator,QPalette, QColor, QTextCursor, QDesktopServices, QPainter, QPen
from sympy import sympify, symbols, Symbol
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLineEdit, QLabel,QGroupBox, QToolButton,QSizePolicy,
    QComboBox, QTextEdit, QMessageBox, QHBoxLayout, QScrollArea, QCheckBox, QMenuBar, QFileDialog,
    QPushButton, QTabWidget, QFormLayout, QSpinBox  ,QDoubleSpinBox  ,QFrame , QGridLayout,QDialog, QListWidget, QButtonGroup,QSlider,
    QCompleter, QTableWidget, QTableWidgetItem, QSplitter,
)

from decimal import Decimal, ROUND_HALF_UP
# === STAGE 20 DESKTOP SHARED STATUS CORE ===
from ro_core import (
    stage20_calc_aspd as _core_stage20_calc_aspd,
    stage20_calculate_hpsp_values as _core_stage20_calculate_hpsp_values,
)
from ro_core import (
    CalculationContext,
    ROItemCore,
    calculate_stat_points,
    raising_stats,
    parse_lub_file as core_parse_lub_file,
    resolve_name_conflicts,
    parse_equipment_blocks as core_parse_equipment_blocks,
    CoreDependencies,
    CORE_LUA_DEPENDENCY_NAMES,
    parse_lua_effects_with_variables as core_parse_lua_effects_with_variables,
    EquipmentSlotInput,
    EquipmentEffectRequest,
    filter_effects as core_filter_effects,
    normalize_effect_key as core_normalize_effect_key,
    try_extract_effect as core_try_extract_effect,
    extract_combi_ids as core_extract_combi_ids,
    extract_combo_items as core_extract_combo_items,
    format_effect_dict as core_format_effect_dict,
    EquipmentCalculationData,
    calculate_equipment_effects as core_calculate_equipment_effects,
    precompute_base_equipment_stats as core_precompute_base_equipment_stats,
    calculate_armor_refine_bonus as core_calculate_armor_refine_bonus,
    get_total_tstat_points as core_get_total_tstat_points,
    calculate_tstat_total_used as core_calculate_tstat_total_used,
    calculate_stat_breakdown as core_calculate_stat_breakdown,
    STAGE21_BLOCK_LEFT_WEAPON_TYPES,
    Stage17DamageRequest as CoreStage17DamageRequest,
    calculate_stage17_damage_request as core_calculate_stage17_damage_request,
    build_damage_effect_profile as core_build_damage_effect_profile,
    calculate_character_defense_profile as core_calculate_character_defense_profile,

    stage17_compare_damage_parity as core_stage17_compare_damage_parity,

)

# === CORE DEDUP PHASE 8: CHARACTER BUILD ADAPTER ===
from ro_core import CharacterBuild as CoreCharacterBuild
from datetime import datetime

# === 條件輸入：上方條件產生器與下方 FunctionSyntaxTextEdit 共用 ===
# syntax 保持 Lua/RO 資料原始格式，parser 端已有 if / elseif / else / end 支援。
CONDITION_VALUE_DEFS = {
    "refine_current": {"label": "當前裝備精煉值", "syntax": "GetRefineLevel(GetLocation())", "keywords": "精煉 refine"},
    "grade_current": {"label": "當前裝備階級", "syntax": "GetEquipGradeLevel(GetLocation())", "keywords": "階級 grade"},
    "armor_lv_current": {"label": "當前防具等級", "syntax": "GetEquipArmorLv(GetLocation())", "keywords": "防具等級 armor"},
    "weapon_lv_current": {"label": "當前武器等級", "syntax": "GetEquipWeaponLv(GetLocation())", "keywords": "武器等級 weapon"},
    "weapon_class_current": {"label": "當前武器類型", "syntax": "GetWeaponClass(GetLocation())", "keywords": "武器類型 weapon class"},
    "pet_relationship": {"label": "寵物親密度", "syntax": "GetPetRelationship()", "keywords": "寵物 親密度 pet"},
    "base_lv": {"label": "BaseLv", "syntax": "get(11)", "keywords": "BaseLv 基礎等級"},
    "job_lv": {"label": "JobLv", "syntax": "get(12)", "keywords": "JobLv 職業等級"},
    "job": {"label": "JOB", "syntax": "get(19)", "keywords": "職業"},
    "str": {"label": "STR", "syntax": "get(32)", "keywords": "STR"},
    "agi": {"label": "AGI", "syntax": "get(33)", "keywords": "AGI"},
    "vit": {"label": "VIT", "syntax": "get(34)", "keywords": "VIT"},
    "int": {"label": "INT", "syntax": "get(35)", "keywords": "INT"},
    "dex": {"label": "DEX", "syntax": "get(36)", "keywords": "DEX"},
    "luk": {"label": "LUK", "syntax": "get(37)", "keywords": "LUK"},
    "pow": {"label": "POW", "syntax": "get(255)", "keywords": "POW"},
    "sta": {"label": "STA", "syntax": "get(256)", "keywords": "STA"},
    "wis": {"label": "WIS", "syntax": "get(257)", "keywords": "WIS"},
    "spl": {"label": "SPL", "syntax": "get(258)", "keywords": "SPL"},
    "con": {"label": "CON", "syntax": "get(259)", "keywords": "CON"},
    "crt": {"label": "CRT", "syntax": "get(260)", "keywords": "CRT"},
    #"skill_level": {"label": "技能等級（可改技能ID）", "syntax": "GetSkillLevel(技能ID)", "keywords": "技能 skill level"},
}

CONDITION_OPERATORS = {
    "==": "等於",
    "~=": "不等於",
    ">=": "大於等於",
    "<=": "小於等於",
    ">": "大於",
    "<": "小於",
}

CONTROL_FLOW_DEFS = {
    "if": {"display": "if 條件 then", "desc": "新增 IF 條件", "template": "if 條件 then\n    \nend"},
    "elseif": {"display": "elseif 條件 then", "desc": "新增 ELSEIF 條件", "template": "elseif 條件 then"},
    "else": {"display": "else", "desc": "新增 ELSE", "template": "else"},
    "end": {"display": "end", "desc": "結束條件", "template": "end"},
}

class NoWheelComboBox(QComboBox):#忽略滾輪的下拉式選單
    def wheelEvent(self, event):
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()

class FunctionSyntaxTextEdit(QTextEdit):
    """函數語法輸入框：支援函數名稱與 map 參數值下拉補完。"""
    COMPLETION_DESC_SEP = "  —  "
    PARAM_DESC_SEP = " = "

    def __init__(self, parent=None):
        super().__init__(parent)
        self._completer = None
        self._completion_kind = "function"  # function | param
        self._function_defs = {}
        self._function_items = []
        self._function_insert_map = {}
        self._function_templates = {}
        self._function_search_text = {}
        self._map_registry = {}
        self._control_insert_map = {}
        self._condition_value_insert_map = {}
        self._condition_operator_insert_map = {}
        self._condition_edit_part = None  # left | operator | right

        # 中文輸入法（IME）常走 inputMethodEvent，不一定會觸發 keyPressEvent。
        # 用 textChanged / cursorPositionChanged 統一延遲刷新，讓中文提交後也會即時更新候選清單。
        self._completion_refresh_timer = QTimer(self)
        self._completion_refresh_timer.setSingleShot(True)
        self._completion_refresh_timer.setInterval(0)
        self._completion_refresh_timer.timeout.connect(self._refresh_completion_popup)
        self.textChanged.connect(self._schedule_completion_refresh)
        self.cursorPositionChanged.connect(self._schedule_completion_refresh)

        # 參數泡泡框只是視覺層，底下仍保留原本純文字語法。
        self.textChanged.connect(self.viewport().update)
        self.cursorPositionChanged.connect(self.viewport().update)

        # 避免滑鼠按下後 cursorPositionChanged 立刻把 QCompleter popup 打開，
        # 導致 popup 搶走 mouseRelease，造成第一次點擊沒有完成整欄反白。
        self._param_mouse_pressed = False
        self._param_mouse_press_pos = None

    def set_map_registry(self, maps: dict):
        """提供 map 參數補完資料來源，例如 size_map、element_map、skill_map。"""
        self._map_registry = maps or {}

    # ---------- function template ----------
    def set_function_defs(self, defs: dict):
        """
        依 function_defs 建立函數補完清單。

        功能：
        - 輸入 Add / Sub / Race 等英文片段，可列出包含該片段的函數。
        - 選取函數後，插入可解析的語法模板。
        - 若參數來自 map，例如 size_map / element_map，會自動選取該參數並顯示
          「0 = 小型」「0 = 無屬性」這類下拉補完。
        """
        self._function_defs = defs or {}
        self._function_items = []
        self._function_insert_map = {}
        self._function_templates = {}
        self._function_search_text = {}
        self._control_insert_map = {}

        for func_name, spec in self._function_defs.items():
            template = self._build_function_template(func_name, spec)
            syntax = template["syntax"]
            desc = spec.get("desc", "")

            visible_arg_labels = [
                p["name"] for p in template["params"]
                if p.get("visible", True)
            ]

            detail_parts = []
            if desc:
                detail_parts.append(desc)
            if visible_arg_labels:
                detail_parts.append("參數：" + "、".join(visible_arg_labels))

            display = (
                f"{syntax}{self.COMPLETION_DESC_SEP}{'｜'.join(detail_parts)}"
                if detail_parts else syntax
            )

            self._function_items.append(display)
            self._function_insert_map[display] = func_name
            self._function_templates[func_name] = template
            self._function_search_text[display] = self._normalize_search_text(
                " ".join([
                    func_name,
                    syntax,
                    desc or "",
                    " ".join(visible_arg_labels),
                ])
            )

        # 控制流程與函數共用同一個 QCompleter，但插入方式分開處理。
        for keyword, spec in CONTROL_FLOW_DEFS.items():
            display = f"{spec['display']}{self.COMPLETION_DESC_SEP}{spec['desc']}"
            self._function_items.append(display)
            self._control_insert_map[display] = keyword
            self._function_search_text[display] = self._normalize_search_text(
                f"{keyword} {spec['display']} {spec['desc']} 條件"
            )

        # Python 使用者常打 elif；UI 接受它，但正式輸出一律轉成 Lua 的 elseif。
        elif_display = f"elif 條件 then{self.COMPLETION_DESC_SEP}ELSEIF 輸入別名"
        self._function_items.append(elif_display)
        self._control_insert_map[elif_display] = "elseif"
        self._function_search_text[elif_display] = self._normalize_search_text(
            "elif elseif 其他條件 ELSEIF 輸入別名"
        )

        self._function_items.sort(key=str.lower)

        # 有些內容可能在 function_defs 設定前就已經載入。
        # 現在 defs 已完整，立刻把舊的完整語法轉成 UI 精簡格式，
        # 所有固定值都保留在畫面文字中。
        raw_display_text = super().toPlainText()
        compact_text = self._rewrite_hidden_args(raw_display_text, compact=True)
        if compact_text != raw_display_text:
            super().setPlainText(compact_text)

    def _is_hidden_arg(self, arg: dict) -> bool:
        # 現在所有正式語法參數都保留在文字中，不再從 UI 隱藏。
        return False

    def _is_no_bubble_arg(self, arg: dict) -> bool:
        # 「無意義」參數仍顯示實際值，但不要畫成泡泡輸入框。
        return arg.get("name") == "無意義"

    def _is_fixed_visible_arg(self, arg: dict) -> bool:
        """有意義、要顯示，但值固定不可修改的參數。"""
        return arg.get("name") == "目標" and str(arg.get("map", "")) == "unit_map"

    def _hidden_arg_value(self, arg: dict) -> str:
        """與 on_function_changed / on_generate 的固定參數規則保持一致。"""
        map_name = str(arg.get("map", ""))
        if map_name == "unit_map":
            return "1"
        if map_name.isdigit():
            return map_name
        return "0"

    def _arg_placeholder(self, arg: dict) -> str:
        # 數字 map 代表固定值，例如 {"name": "無意義", "map": "1"}。
        # 文字要正常顯示 1，只是不替它畫泡泡。
        map_name = str(arg.get("map", ""))
        if map_name.isdigit():
            return map_name

        # 「目標」是有意義但固定的正式參數：UI 顯示實際固定值 1。
        if self._is_fixed_visible_arg(arg):
            return self._hidden_arg_value(arg)

        # 數值型參數不要開下拉式選單；模板直接顯示 n，讓使用者自行改成數字/公式。
        if arg.get("type") == "value":
            return "n"
        if arg.get("type") == "var_select":
            return arg.get("name", "變數")
        if "map" in arg:
            return arg.get("name", arg.get("map", "參數"))
        return arg.get("name", "參數")

    def _build_function_template(self, func_name: str, spec: dict) -> dict:
        args = spec.get("args", []) or []
        tokens = []
        param_meta = []

        # 所有參數文字都保留；「無意義」參數只是不畫泡泡框。
        for actual_index, arg in enumerate(args):
            if self._is_hidden_arg(arg):
                continue

            token = self._arg_placeholder(arg)
            tokens.append(token)
            param_meta.append({
                "index": actual_index,
                "display_index": len(param_meta),
                "name": arg.get("name", token),
                "map": arg.get("map"),
                "type": arg.get("type"),
                "visible": True,
                "token": token,
                "start": None,
                "end": None,
            })

        syntax = f"{func_name}({', '.join(tokens)})"

        # 計算每個可見參數在畫面語法中的相對位置。
        offset = len(func_name) + 1
        for i, meta in enumerate(param_meta):
            token = tokens[i]
            meta["start"] = offset
            meta["end"] = offset + len(token)
            offset += len(token)
            if i < len(tokens) - 1:
                offset += 2  # comma + space

        return {"syntax": syntax, "params": param_meta}

    def _args_for_display_call(self, func_name: str, arg_count: int):
        """
        依目前畫面上的參數數量判斷它是：
        - 新版精簡格式：隱藏固定參數
        - 舊版完整格式：仍包含固定參數

        這讓舊文字貼進來時也不會把參數對錯欄。
        """
        all_args = self._function_defs.get(func_name, {}).get("args", []) or []
        visible_args = [arg for arg in all_args if not self._is_hidden_arg(arg)]

        if len(all_args) != len(visible_args) and arg_count == len(all_args):
            return all_args
        return visible_args

    def _rewrite_hidden_args(self, text: str, *, compact: bool) -> str:
        """
        目前不再隱藏任何參數文字；保留此函式只為相容舊流程。
        """
        if not text or not getattr(self, "_function_defs", None):
            return str(text or "")

        pattern = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(")
        lines = str(text).splitlines(keepends=True)
        rewritten_lines = []

        for line in lines:
            pos = 0
            out = []

            while pos < len(line):
                match = pattern.search(line, pos)
                if not match:
                    out.append(line[pos:])
                    break

                func_name = match.group(1)
                if func_name not in self._function_defs:
                    out.append(line[pos:match.end()])
                    pos = match.end()
                    continue

                open_pos = match.end() - 1
                close_pos = self._matching_close_paren(line, open_pos)
                if close_pos is None:
                    out.append(line[pos:])
                    break

                ranges = self._split_top_level_arg_ranges(line, open_pos + 1, close_pos)
                values = [line[s:e].strip() for s, e in ranges]

                # Func() 會被切成一個空參數，先正規化成空陣列。
                if len(values) == 1 and values[0] == "":
                    values = []

                all_args = self._function_defs.get(func_name, {}).get("args", []) or []
                visible_args = [arg for arg in all_args if not self._is_hidden_arg(arg)]
                has_hidden = len(all_args) != len(visible_args)

                replacement = None

                if has_hidden and compact and len(values) == len(all_args):
                    compact_values = [
                        value
                        for arg, value in zip(all_args, values)
                        if not self._is_hidden_arg(arg)
                    ]
                    replacement = ", ".join(compact_values)

                elif has_hidden and not compact and len(values) == len(visible_args):
                    expanded_values = []
                    visible_index = 0

                    for arg in all_args:
                        if self._is_hidden_arg(arg):
                            expanded_values.append(self._hidden_arg_value(arg))
                        else:
                            if visible_index < len(values):
                                expanded_values.append(values[visible_index])
                            else:
                                expanded_values.append("")
                            visible_index += 1

                    replacement = ", ".join(expanded_values)

                out.append(line[pos:open_pos + 1])

                if replacement is None:
                    out.append(line[open_pos + 1:close_pos])
                else:
                    out.append(replacement)

                out.append(")")
                pos = close_pos + 1

            rewritten_lines.append("".join(out))

        return "".join(rewritten_lines)

    def toPlainText(self):
        """
        對程式其他地方仍回傳完整可解析語法。
        所有參數文字都會保留；「無意義」只是不畫泡泡框。
        """
        display_text = super().toPlainText()
        return self._rewrite_hidden_args(display_text, compact=False)

    def setPlainText(self, text):
        """載入舊的完整語法時，自動轉成不顯示固定參數的 UI 格式。"""
        display_text = self._rewrite_hidden_args(str(text or ""), compact=True)
        super().setPlainText(display_text)

    def insertFromMimeData(self, source):
        """貼上舊語法時也自動隱藏固定/無意義參數。"""
        if source is not None and source.hasText():
            cursor = self.textCursor()
            cursor.insertText(self._rewrite_hidden_args(source.text(), compact=True))
            self.setTextCursor(cursor)
            return
        super().insertFromMimeData(source)

    # ---------- search helpers ----------
    def _normalize_search_text(self, text: str) -> str:
        """搜尋用正規化：讓英文、數字、中文、全形符號都可比對。"""
        return (
            str(text or "")
            .casefold()
            .replace("％", "%")
            .replace("．", ".")
            .replace("　", " ")
            .strip()
        )

    def _filter_completion_items(self, items, prefix: str, search_text_map=None):
        """手動過濾項目，避免 QCompleter 只對字首或英文數字表現正常。"""
        keyword = self._normalize_search_text(prefix)
        if not keyword:
            return list(items)

        filtered = []
        for item in items:
            haystack = (search_text_map or {}).get(item)
            if haystack is None:
                haystack = self._normalize_search_text(item)
            if keyword in haystack:
                filtered.append(item)
        return filtered

    # ---------- generic completer helpers ----------
    def _new_completer(self, items):
        completer = QCompleter(items, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setWidget(self)
        completer.activated[str].connect(self.insert_completion)
        return completer

    def _hide_and_dispose_completer(self):
        """每次重建 completer 前先把舊 popup 關掉，避免多個下拉視窗殘留。"""
        if not self._completer:
            return

        try:
            popup = self._completer.popup()
            if popup:
                popup.hide()
                popup.close()
        except Exception:
            pass

        try:
            self._completer.activated[str].disconnect(self.insert_completion)
        except Exception:
            pass

        try:
            self._completer.setWidget(None)
            self._completer.deleteLater()
        except Exception:
            pass

        self._completer = None

    def _hide_completion_popup(self):
        if not self._completer:
            return
        try:
            popup = self._completer.popup()
            if popup:
                popup.hide()
                popup.close()
        except Exception:
            pass

    def _set_completer(self, items, kind: str, prefix: str):
        # 之前每輸入一個字母都 new 一個 QCompleter，舊 popup 沒被關閉就會殘留。
        # 所以這裡一定先關掉並釋放舊 completer，再建立新的。
        self._hide_and_dispose_completer()

        self._completion_kind = kind
        self._completer = self._new_completer(items)
        # 中文搜尋與「中文描述」搜尋已在呼叫端手動過濾；
        # 這裡固定清空 prefix，只負責顯示已過濾後的清單。
        self._completer.setCompletionPrefix("")

        if self._completer.completionModel().rowCount() == 0:
            self._hide_completion_popup()
            return

        self._completer.popup().setCurrentIndex(
            self._completer.completionModel().index(0, 0)
        )

        rect = self.cursorRect()
        rect.setWidth(
            self._completer.popup().sizeHintForColumn(0)
            + self._completer.popup().verticalScrollBar().sizeHint().width()
        )
        self._completer.complete(rect)

    def text_under_cursor(self):
        """取得游標前方正在輸入的關鍵字；支援中文，不只限英文 WordUnderCursor。"""
        cursor = self.textCursor()
        if cursor.hasSelection():
            return cursor.selectedText().replace("\u2029", "").strip()

        block_text = cursor.block().text()
        left_text = block_text[:cursor.positionInBlock()]
        # 抓取目前正在輸入的 token：排除空白與 Lua 參數分隔符即可。
        # 這比只列英文/數字更穩，中文、日文、韓文、技能名稱中的特殊字元都能參與搜尋。
        match = re.search(r"[^\s,()\[\]{};]+$", left_text)
        return match.group(0) if match else ""

    def _replace_current_token(self, insert_text: str):
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.insertText(insert_text)
            self.setTextCursor(cursor)
            return

        prefix = self.text_under_cursor()
        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(prefix))
        cursor.insertText(insert_text)
        self.setTextCursor(cursor)

    # ---------- parameter context ----------
    def _lookup_map(self, map_name: str):
        """依名稱取得 map；優先使用主程式傳入的 registry，再退回 globals。"""
        if not map_name or str(map_name).isdigit():
            return {}

        value_map = self._map_registry.get(map_name)
        if value_map is None:
            value_map = globals().get(map_name, {})

        # 技能表有時候是在 dataloading() 之後才載入；若 skill_map 還是空，嘗試從 skill_df 補回。
        if map_name == "skill_map" and not value_map:
            df = globals().get("skill_df")
            try:
                if df is not None and not df.empty and "ID" in df.columns and "Name" in df.columns:
                    value_map = dict(zip(df["ID"], df["Name"]))
            except Exception:
                pass

        return value_map if isinstance(value_map, dict) else {}

    def _skill_extra_text(self, skill_id):
        """技能補完除了中文名稱，也把 Code 等欄位放進搜尋字串。"""
        skill_all = self._lookup_map("skill_map_all")
        row = None
        for key in (skill_id, str(skill_id)):
            try:
                if key in skill_all:
                    row = skill_all.get(key)
                    break
            except Exception:
                pass
        if row is None:
            try:
                int_key = int(skill_id)
                row = skill_all.get(int_key)
            except Exception:
                row = None

        if isinstance(row, dict):
            parts = []
            for field in ("Code", "SkillCode", "SkillNameCode", "Name"):
                val = row.get(field)
                if val:
                    parts.append(str(val))
            return " ".join(parts)
        return ""

    def _map_items_with_search(self, map_name: str):
        """回傳 (顯示清單, 搜尋文字表)。顯示可讀，插入仍只插入等號前的數值。"""
        value_map = self._lookup_map(map_name)
        if not value_map:
            return [], {}

        items = list(value_map.items())
        if map_name in ("effect_map", "skill_map"):
            items = sorted(items, key=lambda item: str(item[1]))

        display_items = []
        search_text = {}
        for k, v in items:
            if map_name == "skill_map":
                extra = self._skill_extra_text(k)
                display = f"{k}{self.PARAM_DESC_SEP}{v}"
                # 若有技能 Code，顯示在後方，也納入搜尋；插入時仍只會取等號前的 ID。
                code = extra.split()[0] if extra else ""
                if code and code != str(v):
                    display = f"{display} ({code})"
                search_text[display] = self._normalize_search_text(f"{k} {v} {extra}")
            else:
                display = f"{k}{self.PARAM_DESC_SEP}{v}"
                search_text[display] = self._normalize_search_text(f"{k} {v}")
            display_items.append(display)

        return display_items, search_text

    def _map_items(self, map_name: str):
        # 保留舊呼叫介面：只需要知道是否有候選項時使用。
        return self._map_items_with_search(map_name)[0]

    def _current_function_context(self):
        """回傳目前游標所在的 function 與可見參數 context。"""
        cursor = self.textCursor()
        block_text = cursor.block().text()
        pos = cursor.positionInBlock()
        left_text = block_text[:pos]

        candidates = list(re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", left_text))
        if not candidates:
            return None

        match = None
        func_name = None
        for candidate in reversed(candidates):
            name = candidate.group(1)
            if name in self._function_defs:
                match = candidate
                func_name = name
                break

        if match is None:
            return None

        open_pos = match.end() - 1
        close_pos = self._matching_close_paren(block_text, open_pos)
        if close_pos is None:
            close_pos = len(block_text)

        if not (open_pos < pos <= close_pos):
            return None

        ranges = self._split_top_level_arg_ranges(block_text, open_pos + 1, close_pos)
        if len(ranges) == 1:
            s, e = ranges[0]
            if not block_text[s:e].strip():
                ranges = []

        if not ranges:
            return None

        arg_defs = self._args_for_display_call(func_name, len(ranges))

        target_index = None
        current_arg_text = ""

        for i, (start, end) in enumerate(ranges):
            raw_start, raw_end = start, end

            while start < end and block_text[start].isspace():
                start += 1
            while end > start and block_text[end - 1].isspace():
                end -= 1

            # 逗號後面的空白也視為下一個欄位，方便剛點進去就能判斷。
            if raw_start <= pos <= raw_end:
                target_index = i
                current_arg_text = block_text[start:end].strip()
                break

        if target_index is None or target_index >= len(arg_defs):
            return None

        arg = arg_defs[target_index]
        if self._is_hidden_arg(arg):
            return None

        return {
            "func_name": func_name,
            "arg_index": target_index,
            "arg": arg,
            "current_arg_text": current_arg_text,
        }

    def _show_param_completion_if_available(self):
        context = self._current_function_context()
        if not context:
            return False

        arg = context["arg"]

        # 固定且有意義的參數（例如目標=1）顯示在畫面上，
        # 但不允許用下拉選單改成其他值。
        if self._is_fixed_visible_arg(arg):
            self._hide_completion_popup()
            return True

        # 數值型參數只保留 n 佔位，不顯示任何下拉式選單，
        # 也不要掉回函數名稱補完，避免在 n/數值位置彈出無關候選。
        if arg.get("type") == "value":
            self._hide_completion_popup()
            return True

        map_name = arg.get("map")
        items, search_text_map = self._map_items_with_search(map_name)
        if not items:
            return False

        cursor = self.textCursor()
        prefix = self.text_under_cursor().strip()
        placeholder = arg.get("name", "").strip()

        # 只要整個參數目前是被選取狀態（例如滑鼠點進欄位後自動全選），
        # 就顯示完整 map 清單；開始輸入後 selection 會被取代，再依新文字過濾。
        if cursor.hasSelection() or prefix == placeholder:
            prefix = ""

        filtered_items = self._filter_completion_items(items, prefix, search_text_map)
        if not filtered_items:
            self._hide_completion_popup()
            return False

        self._set_completer(filtered_items, "param", prefix)
        return True

    # ---------- condition / control-flow completion ----------
    def _condition_completion_items(self):
        items = []
        search_text = {}
        self._condition_value_insert_map = {}
        for spec in CONDITION_VALUE_DEFS.values():
            display = f"{spec['syntax']}{self.COMPLETION_DESC_SEP}{spec['label']}"
            items.append(display)
            self._condition_value_insert_map[display] = spec["syntax"]
            search_text[display] = self._normalize_search_text(
                f"{spec['syntax']} {spec['label']} {spec.get('keywords', '')}"
            )
        return items, search_text

    def _condition_operator_items(self):
        items = []
        search_text = {}
        self._condition_operator_insert_map = {}
        for op, label in CONDITION_OPERATORS.items():
            display = f"{op}{self.COMPLETION_DESC_SEP}{label}"
            items.append(display)
            self._condition_operator_insert_map[display] = op
            search_text[display] = self._normalize_search_text(f"{op} {label}")
        return items, search_text

    def _condition_parts_from_line(self, block_text: str):
        """解析單行 if/elseif，回傳條件左右值/運算子的文字範圍。"""
        m = re.match(r"^(\s*)(if|elseif|elif)\b", block_text)
        if not m:
            return None

        keyword_end = m.end()
        # 只有剛打完 `if` 時，先保留控制流程補完；輸入空白後才進條件補完。
        if keyword_end >= len(block_text):
            return None
        if not block_text[keyword_end].isspace():
            return None

        tail = block_text[keyword_end:]
        then_m = re.search(r"\s+then\b", tail)
        cond_end = keyword_end + then_m.start() if then_m else len(block_text)
        raw_condition_end = cond_end
        cond_start = keyword_end
        while cond_start < cond_end and block_text[cond_start].isspace():
            cond_start += 1
        while cond_end > cond_start and block_text[cond_end - 1].isspace():
            cond_end -= 1

        ctx = {
            "keyword": "elseif" if m.group(2) == "elif" else m.group(2),
            "keyword_end": keyword_end,
            "condition_start": cond_start,
            "condition_end": cond_end,
            "raw_condition_end": raw_condition_end,
            "condition_text": block_text[cond_start:cond_end],
            "left": None,
            "operator": None,
            "right": None,
        }

        if cond_start >= cond_end:
            return ctx

        text = block_text[cond_start:cond_end]
        quote = None
        escaped = False
        depth = 0
        op_info = None
        operators = (">=", "<=", "==", "~=", ">", "<")
        i = 0
        while i < len(text):
            ch = text[i]
            if quote is not None:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
                i += 1
                continue
            if ch in ("'", '"'):
                quote = ch
                i += 1
                continue
            if ch in "([{":
                depth += 1
                i += 1
                continue
            if ch in ")]}" and depth > 0:
                depth -= 1
                i += 1
                continue
            if depth == 0:
                for op in operators:
                    if text.startswith(op, i):
                        op_info = (i, i + len(op), op)
                        break
                if op_info:
                    break
            i += 1

        def trim_range(start, end):
            while start < end and block_text[start].isspace():
                start += 1
            while end > start and block_text[end - 1].isspace():
                end -= 1
            return (start, end) if start < end else None

        if op_info:
            op_s, op_e, op = op_info
            abs_op_s = cond_start + op_s
            abs_op_e = cond_start + op_e
            ctx["left"] = trim_range(cond_start, abs_op_s)
            ctx["operator"] = (abs_op_s, abs_op_e)
            ctx["right"] = trim_range(abs_op_e, cond_end)
            ctx["operator_text"] = op
        else:
            ctx["left"] = trim_range(cond_start, cond_end)

        return ctx

    def _current_condition_context(self):
        cursor = self.textCursor()
        block_text = cursor.block().text()
        pos = cursor.positionInBlock()
        ctx = self._condition_parts_from_line(block_text)
        if not ctx:
            return None
        # 游標必須位於 if/elseif 的條件區；then 後面不接管函數補完。
        if pos < ctx["keyword_end"] or pos > max(ctx.get("raw_condition_end", ctx["condition_end"]), ctx["keyword_end"] + 1):
            return None
        ctx["cursor_pos"] = pos
        ctx["block_text"] = block_text
        return ctx

    def _condition_part_at_cursor(self, ctx):
        cursor = self.textCursor()
        block_base = cursor.block().position()
        sel_start = cursor.selectionStart() - block_base
        sel_end = cursor.selectionEnd() - block_base
        pos = cursor.positionInBlock()

        for part in ("left", "operator", "right"):
            rng = ctx.get(part)
            if not rng:
                continue
            start, end = rng
            if cursor.hasSelection() and sel_start == start and sel_end == end:
                return part
            if start <= pos <= end:
                return part
        return None

    def _show_condition_completion_if_available(self):
        ctx = self._current_condition_context()
        if not ctx:
            self._condition_edit_part = None
            return False

        cursor = self.textCursor()
        part = self._condition_edit_part or self._condition_part_at_cursor(ctx)
        condition_text = ctx.get("condition_text", "").strip()

        # 點擊/選取右值時只讓使用者直接輸入，不要掉回函數名稱補完。
        if part == "right":
            self._hide_completion_popup()
            return True

        if part == "operator":
            items, search_text = self._condition_operator_items()
            prefix = "" if cursor.hasSelection() else self.text_under_cursor().strip()
            filtered = self._filter_completion_items(items, prefix, search_text)
            if filtered:
                self._set_completer(filtered, "condition_operator", prefix)
            else:
                self._hide_completion_popup()
            return True

        known_syntax = {spec["syntax"] for spec in CONDITION_VALUE_DEFS.values()}

        # 尚未輸入條件，或正在編輯左值/「條件」placeholder -> 顯示條件來源。
        if (
            not condition_text
            or condition_text == "條件"
            or part == "left" and (cursor.hasSelection() or condition_text not in known_syntax)
            or self._condition_edit_part == "left"
        ):
            items, search_text = self._condition_completion_items()
            if cursor.hasSelection() or condition_text == "條件":
                prefix = ""
            else:
                prefix = self.text_under_cursor().strip() or condition_text
            filtered = self._filter_completion_items(items, prefix, search_text)
            if filtered:
                self._set_completer(filtered, "condition_value", prefix)
            else:
                self._hide_completion_popup()
            return True

        # 左值完整後，自動提示比較運算子。
        if not ctx.get("operator") and condition_text in known_syntax:
            items, search_text = self._condition_operator_items()
            self._set_completer(items, "condition_operator", "")
            return True

        # 已經進入 if/elseif 條件列時，不要顯示一般函數名稱補完。
        self._hide_completion_popup()
        return True

    def _iter_condition_bubble_ranges(self, block_text: str):
        """條件式的左值 / 比較符號 / 右值各自畫一個泡泡。"""
        ctx = self._condition_parts_from_line(block_text)
        if not ctx:
            return
        for part in ("left", "operator", "right"):
            rng = ctx.get(part)
            if rng:
                yield rng[0], rng[1], part

    def _select_condition_at_cursor(self, source_cursor=None):
        cursor = QTextCursor(source_cursor) if source_cursor is not None else self.textCursor()
        block_text = cursor.block().text()
        pos = cursor.positionInBlock()
        ctx = self._condition_parts_from_line(block_text)
        if not ctx:
            return False

        for part in ("left", "operator", "right"):
            rng = ctx.get(part)
            if not rng:
                continue
            start, end = rng
            if not (start <= pos <= end):
                continue
            block_base = cursor.block().position()
            select_cursor = QTextCursor(cursor)
            select_cursor.setPosition(block_base + start)
            select_cursor.setPosition(block_base + end, QTextCursor.KeepAnchor)
            self._condition_edit_part = part
            self.setTextCursor(select_cursor)
            QTimer.singleShot(0, self._show_condition_completion_if_available)
            self.viewport().update()
            return True
        return False

    def insert_control_block(self, keyword: str, condition: str = "條件"):
        """上方條件產生器與下方 completer 共用的控制流程插入方法。"""
        keyword = str(keyword or "").strip().lower()
        if keyword not in CONTROL_FLOW_DEFS:
            return

        cursor = self.textCursor()
        block_text = cursor.block().text()
        indent = re.match(r"\s*", block_text).group(0)

        # 若游標在現有文字中間，先換行，避免把 if 黏到函數後面。
        prefix_text = block_text[:cursor.positionInBlock()]
        need_leading_newline = bool(prefix_text.strip())

        # 如果是在既有 `... then` 後面新增 IF，視為巢狀 IF：
        # 保留 then，並自動多縮排一層。
        insert_indent = indent
        if keyword == "if" and re.search(r"\bthen\s*$", prefix_text, re.IGNORECASE):
            insert_indent = indent + "    "

        if keyword == "if":
            body_indent = insert_indent + "    "
            text = f"if {condition} then\n{body_indent}\n{insert_indent}end"
        elif keyword == "elseif":
            text = f"elseif {condition} then"
        else:
            text = keyword

        if need_leading_newline:
            text = "\n" + insert_indent + text

        inserted_start = cursor.position()
        cursor.insertText(text)
        self.setTextCursor(cursor)
        self._hide_completion_popup()

        # placeholder 模式：選取「條件」，立刻開條件來源候選。
        if condition == "條件" and keyword in ("if", "elseif"):
            doc_text = self.document().toPlainText()
            search_from = inserted_start
            cond_pos = doc_text.find("條件", search_from)
            if cond_pos >= 0:
                sel = self.textCursor()
                sel.setPosition(cond_pos)
                sel.setPosition(cond_pos + len("條件"), QTextCursor.KeepAnchor)
                self._condition_edit_part = "left"
                self.setTextCursor(sel)
                QTimer.singleShot(0, self._show_condition_completion_if_available)
                return

        # 上方直接產生完整 IF 時，把游標放到 then 下一行，方便繼續輸入函數。
        if keyword == "if" and condition != "條件":
            doc_text = self.document().toPlainText()
            target = doc_text.find("\n" + insert_indent + "    ", inserted_start)
            if target >= 0:
                c = self.textCursor()
                c.setPosition(target + 1 + len(insert_indent) + 4)
                self.setTextCursor(c)

    def _show_function_completion_if_available(self):
        prefix = self.text_under_cursor().strip()
        if len(prefix) < 1 or not self._function_items:
            self._hide_completion_popup()
            return False

        filtered_items = self._filter_completion_items(
            self._function_items,
            prefix,
            self._function_search_text,
        )
        if not filtered_items:
            self._hide_completion_popup()
            return False

        self._set_completer(filtered_items, "function", prefix)
        return True

    def _select_first_map_parameter(self, func_name: str, inserted_start: int):
        template = self._function_templates.get(func_name)
        if not template:
            return

        for meta in template.get("params", []):
            if not meta.get("visible", True):
                continue
            if self._map_items(meta.get("map")):
                cursor = self.textCursor()
                cursor.setPosition(inserted_start + meta["start"])
                cursor.setPosition(inserted_start + meta["end"], QTextCursor.KeepAnchor)
                self.setTextCursor(cursor)
                QTimer.singleShot(0, self._show_param_completion_if_available)
                return

    def _select_argument_at_cursor(self, source_cursor=None):
        """點進函數參數時，一次點擊就選取整個可見參數。"""
        cursor = QTextCursor(source_cursor) if source_cursor is not None else self.textCursor()

        block_text = cursor.block().text()
        pos = cursor.positionInBlock()
        left_text = block_text[:pos]

        candidates = list(re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", left_text))
        if not candidates:
            return False

        match = None
        func_name = None
        for candidate in reversed(candidates):
            name = candidate.group(1)
            if name in self._function_defs:
                match = candidate
                func_name = name
                break

        if match is None:
            return False

        open_pos = match.end() - 1
        close_pos = self._matching_close_paren(block_text, open_pos)
        if close_pos is None:
            close_pos = len(block_text)

        if not (open_pos < pos <= close_pos):
            return False

        ranges = self._split_top_level_arg_ranges(block_text, open_pos + 1, close_pos)
        if len(ranges) == 1:
            s, e = ranges[0]
            if not block_text[s:e].strip():
                return False

        arg_defs = self._args_for_display_call(func_name, len(ranges))

        for arg_index, (start, end) in enumerate(ranges):
            raw_start, raw_end = start, end

            while start < end and block_text[start].isspace():
                start += 1
            while end > start and block_text[end - 1].isspace():
                end -= 1

            if start >= end:
                continue

            # 點文字本身，或點到該參數左右緊鄰的空白，都視為同一個泡泡。
            if not (raw_start <= pos <= raw_end):
                continue

            if arg_index >= len(arg_defs):
                return False

            arg = arg_defs[arg_index]
            if self._is_hidden_arg(arg):
                return False

            # 「無意義」欄位只保留普通文字，不畫泡泡、也不做整欄反白。
            if self._is_no_bubble_arg(arg):
                self._hide_completion_popup()
                self.viewport().update()
                return True

            # 固定 1 要顯示，但不是可修改輸入欄。
            if self._is_fixed_visible_arg(arg):
                self._hide_completion_popup()
                self.viewport().update()
                return True

            select_cursor = QTextCursor(cursor)
            block_base = cursor.block().position()
            select_cursor.setPosition(block_base + start)
            select_cursor.setPosition(block_base + end, QTextCursor.KeepAnchor)
            self.setTextCursor(select_cursor)

            # map 欄位直接開完整候選；value 欄位只反白，輸入即可取代。
            QTimer.singleShot(0, self._show_param_completion_if_available)
            self.viewport().update()
            return True

        return False

    # ---------- bubble parameter rendering ----------
    def _matching_close_paren(self, text: str, open_pos: int):
        """找指定左括號對應的右括號；忽略字串內容，支援巢狀括號。"""
        depth = 0
        quote = None
        escaped = False

        for i in range(open_pos, len(text)):
            ch = text[i]

            if quote is not None:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
                continue

            if ch in ("'", '"'):
                quote = ch
                continue

            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return i

        return None

    def _split_top_level_arg_ranges(self, text: str, start: int, end: int):
        """把 function(...) 的最外層參數切成 (start, end) 範圍。"""
        ranges = []
        arg_start = start
        nested = 0
        quote = None
        escaped = False

        for i in range(start, end):
            ch = text[i]

            if quote is not None:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
                continue

            if ch in ("'", '"'):
                quote = ch
            elif ch in "([{":
                nested += 1
            elif ch in ")]}":
                nested = max(0, nested - 1)
            elif ch == "," and nested == 0:
                ranges.append((arg_start, i))
                arg_start = i + 1

        ranges.append((arg_start, end))
        return ranges

    def _iter_bubble_ranges(self, block_text: str):
        """只回傳可見參數的泡泡範圍；固定/無意義參數完全不畫。"""
        occupied_until = -1
        condition_ctx = self._condition_parts_from_line(block_text)
        condition_left = condition_ctx.get("left") if condition_ctx else None

        for match in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", block_text):
            # 條件左值本身由 condition bubble 接管，避免和函數參數泡泡重疊。
            if condition_left and condition_left[0] <= match.start() < condition_left[1]:
                continue
            func_name = match.group(1)
            if func_name not in self._function_defs:
                continue

            open_pos = match.end() - 1
            if open_pos < occupied_until:
                continue

            close_pos = self._matching_close_paren(block_text, open_pos)
            if close_pos is None:
                close_pos = len(block_text)

            ranges = self._split_top_level_arg_ranges(block_text, open_pos + 1, close_pos)
            if len(ranges) == 1:
                s, e = ranges[0]
                if not block_text[s:e].strip():
                    ranges = []

            arg_defs = self._args_for_display_call(func_name, len(ranges))

            for arg_index, (start, end) in enumerate(ranges):
                while start < end and block_text[start].isspace():
                    start += 1
                while end > start and block_text[end - 1].isspace():
                    end -= 1

                if start >= end or arg_index >= len(arg_defs):
                    continue

                arg = arg_defs[arg_index]
                if self._is_hidden_arg(arg):
                    continue

                # 無意義參數：值仍在 QTextEdit 裡正常顯示，只是不畫泡泡框。
                if self._is_no_bubble_arg(arg):
                    continue

                yield start, end, self._is_fixed_visible_arg(arg)

            occupied_until = close_pos + 1

    def _selection_matches_range(self, block, start: int, end: int):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return False

        block_base = block.position()
        return (
            cursor.selectionStart() == block_base + start
            and cursor.selectionEnd() == block_base + end
        )

    def _draw_parameter_bubbles(self):
        """在 QTextEdit 文字上方畫圓角參數框；文字本身仍是可直接編輯的純文字。"""
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.Antialiasing, True)

        palette = self.palette()
        accent = palette.color(QPalette.Highlight)
        disabled_color = palette.color(QPalette.Disabled, QPalette.Text)

        block = self.document().firstBlock()
        while block.isValid():
            block_text = block.text()

            bubble_ranges = list(self._iter_bubble_ranges(block_text))
            bubble_ranges.extend(
                (start, end, False)
                for start, end, _part in self._iter_condition_bubble_ranges(block_text)
            )

            for start, end, is_fixed in bubble_ranges:
                block_base = block.position()

                start_cursor = QTextCursor(self.document())
                start_cursor.setPosition(block_base + start)

                end_cursor = QTextCursor(self.document())
                end_cursor.setPosition(block_base + end)

                start_rect = self.cursorRect(start_cursor)
                end_rect = self.cursorRect(end_cursor)

                top = min(start_rect.top(), end_rect.top())
                bottom = max(start_rect.bottom(), end_rect.bottom())
                if bottom < 0 or top > self.viewport().height():
                    continue

                # 正常函數參數都在同一行；跨行時先不畫，避免畫成長框。
                if abs(start_rect.top() - end_rect.top()) > max(4, start_rect.height() // 2):
                    continue

                # 泡泡框只包「參數文字本身」。
                #
                # 以前左右各多加 4px：
                #     left  = start_rect.left() - 4
                #     right = end_rect.left() + 4
                # 在 `234,`、`14)` 這種沒有空白的語法裡，
                # 右側 padding 就會視覺上把逗號 / 右括號一起包進去。
                #
                # 現在右邊界刻意停在參數結尾游標之前，讓 , 和 ) 明確留在框外。
                left = start_rect.left()
                right = end_rect.left() - 2

                if right <= left:
                    value_text = block_text[start:end]
                    text_width = self.fontMetrics().horizontalAdvance(value_text)
                    right = left + max(4, text_width - 2)

                rect = start_rect.adjusted(0, 0, 0, 0)
                rect.setLeft(left)
                rect.setRight(right)
                rect.setTop(start_rect.top() - 1)
                rect.setBottom(start_rect.bottom() + 1)

                selected = self._selection_matches_range(block, start, end)

                if selected and not is_fixed:
                    fill = QColor("#3D9CFF")
                    fill.setAlpha(90)

                    border = QColor("#5AB0FF")
                    border.setAlpha(240)

                    pen = QPen(border, 1.5)

                elif is_fixed:
                    fill = QColor("#888888")
                    fill.setAlpha(25)

                    border = QColor("#888888")
                    border.setAlpha(100)

                    pen = QPen(border, 1.0)

                else:
                    fill = QColor("#5C7C99")
                    fill.setAlpha(45)

                    border = QColor("#87A8C4")
                    border.setAlpha(150)

                    pen = QPen(border, 1.0)

                painter.setPen(pen)
                painter.setBrush(fill)
                painter.drawRoundedRect(rect, 5, 5)

            block = block.next()

        painter.end()

    def paintEvent(self, event):
        # 先畫正常文字，再疊上半透明圓角泡泡。
        super().paintEvent(event)
        self._draw_parameter_bubbles()

    # ---------- insertion ----------
    def insert_completion(self, completion):
        if not self._completer or self._completer.widget() is not self:
            return

        if self._completion_kind == "param":
            # Popup 顯示「0 = 小型」，實際寫進語法只寫入 0。
            insert_text = completion.split(self.PARAM_DESC_SEP, 1)[0].strip()
            self._replace_current_token(insert_text)
            self._hide_completion_popup()
            return

        if self._completion_kind == "condition_value":
            insert_text = self._condition_value_insert_map.get(
                completion,
                completion.split(self.COMPLETION_DESC_SEP, 1)[0].strip(),
            )
            self._replace_current_token(insert_text)
            self._condition_edit_part = None
            self._hide_completion_popup()
            QTimer.singleShot(0, self._show_condition_completion_if_available)
            return

        if self._completion_kind == "condition_operator":
            insert_text = self._condition_operator_insert_map.get(
                completion,
                completion.split(self.COMPLETION_DESC_SEP, 1)[0].strip(),
            )
            self._replace_current_token(insert_text + " ")
            self._condition_edit_part = "right"
            self._hide_completion_popup()
            return

        # if / elseif / else / end 不是函數，使用控制流程模板。
        keyword = self._control_insert_map.get(completion)
        if keyword:
            # 重要：不要用 text_under_cursor() 的 selection 來決定刪除範圍。
            # 條件泡泡 / QCompleter 有可能讓 QTextCursor 還帶著 selection，
            # 若再用 KeepAnchor 往左移，會把前面的 `then` 一起選進去刪掉。
            #
            # 這裡改成只看「游標前方實際文字」，並用絕對位置精準刪除
            # 最後輸入的控制關鍵字。例：
            #     if A thenif|
            # 只刪除最後 2 個字元 `if`，`then` 永遠保留。
            cursor = self.textCursor()
            block = cursor.block()
            block_text = block.text()
            pos_in_block = cursor.positionInBlock()
            left_text = block_text[:pos_in_block]

            typed_keywords = [keyword]
            if keyword == "elseif":
                typed_keywords.append("elif")

            matched_keyword = None
            left_lower = left_text.lower()
            for typed_keyword in sorted(typed_keywords, key=len, reverse=True):
                if left_lower.endswith(typed_keyword.lower()):
                    matched_keyword = typed_keyword
                    break

            if matched_keyword:
                block_base = block.position()
                remove_end = block_base + pos_in_block
                remove_start = remove_end - len(matched_keyword)

                # 重建一個全新的 cursor，完全丟掉舊 selection/anchor。
                remove_cursor = QTextCursor(self.document())
                remove_cursor.setPosition(remove_start)
                remove_cursor.setPosition(remove_end, QTextCursor.KeepAnchor)
                remove_cursor.removeSelectedText()
                self.setTextCursor(remove_cursor)

            self.insert_control_block(keyword, "條件" if keyword in ("if", "elseif") else "")
            return

        # Popup 顯示「語法 — 中文說明/參數」，實際插入只插入語法模板。
        display_text = completion
        func_name = self._function_insert_map.get(display_text)
        if not func_name:
            syntax = completion.split(self.COMPLETION_DESC_SEP, 1)[0]
            func_name = syntax.split("(", 1)[0]
        else:
            syntax = self._function_templates[func_name]["syntax"]

        prefix = self.text_under_cursor()
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor, len(prefix))
        inserted_start = cursor.selectionStart()
        cursor.insertText(syntax)
        self.setTextCursor(cursor)
        self._hide_completion_popup()

        self._select_first_map_parameter(func_name, inserted_start)

    # ---------- refresh / input handling ----------
    def _schedule_completion_refresh(self):
        """排程刷新補完清單。

        英文/數字鍵盤輸入通常會進 keyPressEvent；中文輸入法則常在組字完成後
        透過 inputMethodEvent / textChanged 才更新文字。因此統一走這個 timer，
        可以避免中文候選清單必須重新 focus 才刷新。

        滑鼠左鍵按住期間不刷新 popup：
        否則 cursorPositionChanged 會在 mousePress 後立刻開啟 QCompleter，
        popup 可能搶走 mouseRelease，造成第一次點擊只關/開 popup、第二次才反白。
        """
        if not self.hasFocus():
            return

        if getattr(self, "_param_mouse_pressed", False):
            return

        self._completion_refresh_timer.start()

    def _refresh_completion_popup(self):
        if not self.hasFocus():
            self._hide_completion_popup()
            return

        # if / elseif 條件輸入優先於一般函數參數，避免 GetRefineLevel(...)
        # 在條件左值中被誤判為一般函數參數。
        if self._show_condition_completion_if_available():
            return

        # 再判斷是否正在一般函數參數內；若是 map 參數，顯示 map 值。
        if self._show_param_completion_if_available():
            return

        # 否則才顯示函數名稱 / 控制流程補完。
        self._show_function_completion_if_available()

    def inputMethodEvent(self, event):
        # 中文/日文/韓文 IME 組字提交後，主動刷新補完清單。
        super().inputMethodEvent(event)
        self._schedule_completion_refresh()

    def keyPressEvent(self, event):
        if self._completer and self._completer.popup().isVisible():
            if event.key() in (Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape, Qt.Key_Tab, Qt.Key_Backtab):
                event.ignore()
                return

        super().keyPressEvent(event)
        self._schedule_completion_refresh()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._param_mouse_pressed = True
            self._param_mouse_press_pos = event.position().toPoint()

            # 先停止尚未執行的 0ms refresh，也先收掉舊 popup。
            # 這是避免「第一次點擊被 completer 吃掉」的核心。
            self._completion_refresh_timer.stop()
            self._hide_completion_popup()
        else:
            self._param_mouse_press_pos = None

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        release_pos = event.position().toPoint()
        press_pos = getattr(self, "_param_mouse_press_pos", None)

        # 先讓 QTextEdit 完成原始的游標/拖曳處理。
        super().mouseReleaseEvent(event)

        if event.button() != Qt.LeftButton:
            return

        # 一定要先解除 guard，後面才允許重新開 completer。
        self._param_mouse_pressed = False

        if press_pos is None:
            self._schedule_completion_refresh()
            return

        app = QApplication.instance()
        drag_distance = app.startDragDistance() if app is not None else 4

        # 真正拖曳時保留使用者原本的文字選取，不強制整欄反白。
        if (release_pos - press_pos).manhattanLength() > drag_distance:
            self._schedule_completion_refresh()
            return

        # 用實際放開的位置重新算 cursor，不依賴 QTextEdit 此刻的 selection 狀態。
        click_cursor = self.cursorForPosition(release_pos)

        # 條件左值 / 運算子 / 右值優先整欄反白。
        if self._select_condition_at_cursor(click_cursor):
            return

        # 單擊成功命中一般函數參數 -> 立刻整欄反白。
        # _select_argument_at_cursor 內會自行排程 map 候選 popup。
        if self._select_argument_at_cursor(click_cursor):
            return

        # 點在函數名稱、括號、逗號等非參數位置才恢復一般補完刷新。
        self._schedule_completion_refresh()

    def leaveEvent(self, event):
        # 少數情況按住滑鼠後移出 editor 再放開，mouseRelease 可能不回來；
        # 避免 guard 一直卡住。
        self._param_mouse_pressed = False
        self._condition_edit_part = None
        super().leaveEvent(event)


enabled_skill_levels = {}  # 存放已啟用技能的等級
Use_skill_levels = {}#已啟用的技能id
global_weapon_level_map = {}#武器等級
global_armor_weapon_map = {}#裝備類型(防具武器)
global_armor_level_map = {}#防具等級
global_weapon_type_map = {}#武器類型
global_weapon_atk_map = {}#武器基礎攻擊力
global_weapon_matk_map = {}#武器基礎魔法攻擊力
function_defs = {}#公式變數字典
slot_item_id_map = {}#部位裝備的ID


def build_desktop_calculation_context():
    """Desktop -> Core 的暫時相容橋接。

    Mutable dict 保持原物件參考，所以 Stage 2 不會改變現有 Desktop parser
    對技能、武器/防具資料 map 的寫入副作用。Web 未來不使用此 helper，而是
    每個 request 自己建立 CalculationContext。
    """
    return CalculationContext.from_state(globals())
def build_desktop_core_dependencies():
    """Build read-mostly Lua parser dependencies from the existing Desktop state.

    This is a migration bridge only. Values are referenced, not deep-copied.
    Future Web code should construct CoreDependencies directly and must not
    import ItemSearchApp.py.
    """
    deps = CoreDependencies.from_state(
        globals(),
        required_names=CORE_LUA_DEPENDENCY_NAMES,
    )
    deps.validate(CORE_LUA_DEPENDENCY_NAMES)
    return deps


def register_function(name, desc, args, vars=None):
    if name in function_defs:
        return

    function_defs[name] = {
        "desc": desc,
        "args": args,
    }


def load_python_dict(path, var_name):
    """
    從外部 .py 檔載入指定變數。
    
    path: 外部 .py 檔案路徑
    var_name: 要讀取的 dict 變數名稱，例如 'all_skill_entries'
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"外部資料檔不存在: {path}")

    spec = importlib.util.spec_from_file_location("external_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, var_name):
        raise AttributeError(f"{path} 裡找不到變數: {var_name}")

    return getattr(module, var_name)


class DataRegistry:
    """
    用於統一管理所有外部 py 資料來源。
    key = 資料名稱（如：skill, job）
    value = {
        "path": 本地路徑,
        "var_name": py 裡的變數名稱,
        "default": 預設 fallback dict,
        "on_reload": 重新載入後要執行的 callback（例如 UI 更新）
    }
    """
    sources = {}

    loaded_data = {}   # 儲存已載入的資料，如：loaded_data["skill"] = {...}
    window = None   # 🔥 讓 UI 建好後再塞進來
    @classmethod
    def register(cls, key, path, var_name, default, on_reload=None):
        cls.sources[key] = {
            "path": path,
            "var_name": var_name,
            "default": default,
            "on_reload": on_reload,
        }

    @classmethod
    def load(cls, key):
        info = cls.sources[key]
        path = info["path"]
        var_name = info["var_name"]

        try:
            data = load_python_dict(path, var_name)
            cls.loaded_data[key] = data
            print(f"✓ 載入 {key} 成功")
        except Exception as e:
            print(f"⚠️ 載入 {key} 失敗，使用預設值：{e}")
            cls.loaded_data[key] = info["default"]

        return cls.loaded_data[key]

    @classmethod
    def reload_all(cls):
        print("=== 重新載入所有資料來源 ===")

        for key, info in cls.sources.items():
            cls.load(key)

            cb = info["on_reload"]
            if cb and cls.window:
                cb(cls.window)   # 把 window 實體傳進 callback



 # 註冊 all_skill_entries
DataRegistry.register(
    key="skills",
    path="data/all_skill_entries.py",
    var_name="all_skill_entries",
    default={},
    on_reload=lambda win: win.rebuild_skill_tab()  # UI 更新
)

# 註冊 job_dict
DataRegistry.register(
    key="jobs",
    path="data/job_dict.py",
    var_name="job_dict",
    default={
    0: {"id": "","id_jobneme": "","id_jobneme_OL": "","selectskill": "", "name": "沒有資料", "TJobMaxPoint": [0,0,0,0,0,0,0,0,0,0,0,0],"point":"0"}}, 
    on_reload=lambda win: win.reload_job_list()  # 職業列表更新
)

DataRegistry.register(
    key="jobHPSP",
    path="data/job_dict.py",
    var_name="job_4th_hpsp",
    default={},
    on_reload=lambda win: win.reload_job_list()  # 職業列表更新
)

DataRegistry.register(
    key="ASPD",
    path="data/job_dict.py",
    var_name="WPASPDdata",
    default={
    0: {0:144}},
    on_reload=lambda win: win.reload_job_list()  # 職業列表更新
)
# 外部py載入清單
DataRegistry.reload_all()#先讀取所有外部py並設定預設
all_skill_entries = DataRegistry.loaded_data["skills"]# 載入技能效果資料
job_dict  = DataRegistry.loaded_data["jobs"]#職業job_id
job_4th_hpsp = DataRegistry.loaded_data["jobHPSP"]#HPSP
WPASPDdata = DataRegistry.loaded_data["ASPD"]#攻速資料

stat_fields = {
    11: "BaseLv", 12: "JobLv", 19: "JOB", 200: "MHP", 202: "MSP",
    32: "STR", 33: "AGI", 34: "VIT", 35: "INT", 36: "DEX", 37: "LUK",
    255: "POW", 256: "STA", 257: "WIS", 258: "SPL", 259: "CON", 260: "CRT",
    263: "石碑開啟格數", 264: "石碑精煉"
}
default_values = {
    "BaseLv": 260,"STR": 1,"AGI": 1,"AGI": 1,"VIT": 1,"INT": 1,"DEX": 1,"LUK": 1,
    "POW": 0,"STA": 0,"WIS": 0,"SPL": 0,"CON": 0,"CRT": 0,
}

refine_parts = {
    # === 裝備部位 ===
    "頭上":   {"slot": 10, "type": "裝備"},
    "頭中":   {"slot": 11, "type": "裝備"},
    "頭下":   {"slot": 12, "type": "裝備"},
    "鎧甲":   {"slot": 2,  "type": "裝備"},
    "右手(武器)":   {"slot": 4,  "type": "裝備"},
    "投擲物品":   {"slot": 110,  "type": "裝備"},
    "左手(盾牌)":   {"slot": 3,  "type": "裝備"},
    "披肩":   {"slot": 5,  "type": "裝備"},
    "鞋子":   {"slot": 6,  "type": "裝備"},
    "飾品右": {"slot": 7,  "type": "裝備"},
    "飾品左": {"slot": 8,  "type": "裝備"},

    # === 影子裝備 ===
    "影子鎧甲":   {"slot": 30, "type": "影子"},
    "影子手套":   {"slot": 31, "type": "影子"},
    "影子盾牌":     {"slot": 32, "type": "影子"},
    "影子鞋子":   {"slot": 33, "type": "影子"},
    "影子耳環右": {"slot": 34, "type": "影子"},
    "影子墬子左": {"slot": 35, "type": "影子"},

    # === 服飾部位 ===
    "服飾頭上":   {"slot": 41, "type": "服飾"},
    "服飾頭中":   {"slot": 42, "type": "服飾"},
    "服飾頭下":   {"slot": 43, "type": "服飾"},
    "服飾斗篷":   {"slot": 44, "type": "服飾"},
            
    # === 石碑/寵物部位 === slot部位自定義，遊戲未定義此位置。
    "符文石碑":   {"slot": 100, "type": "石碑"},
    "寵物蛋":   {"slot": 101, "type": "寵物"},
    # === 技能欄位 === slot部位自定義，遊戲未定義此位置。
    "技能":   {"slot": 102, "type": "技能"},
}


equip_sitetype = {
    10 : "頭上",11: "頭中",12: "頭下",2: "鎧甲",4: "右手(武器)",3: "左手(盾牌)",5: "披肩",6: "鞋子",7: "飾品右",8: "飾品左",
    30: "影子鎧甲",31: "影子手套",32: "影子盾牌",33: "影子鞋子",34: "影子耳環右",35: "影子墬子左"
}

effect_map = {
    41: "ATK", 45: "DEF", 47: "MDEF", 49: "HIT", 50: "FLEE", 51: "完全迴避", 52: "CRI", 54: "ASPD",
    103: "STR", 104: "AGI", 105: "VIT", 106: "INT", 107: "DEX", 108: "LUK",
    109: "MHP", 110: "MSP", 111: "MHP%", 112: "MSP%", 113: "HP自然恢復%", 114: "SP自然恢復%",
    140: "MATK%", 167: "攻擊後延遲", 200: "MATK", 207: "ATK%",
    234: "POW", 235: "STA", 236: "WIS", 237: "SPL", 238: "CON", 239: "CRT",
    242: "P.ATK", 243: "S.MATK", 244: "RES", 245: "MRES",
    253: "C.RATE", 254: "H.PLUS",
    #非官方編碼 用於二轉以下的技能跟集中覺醒波色克藥水
    301: "(2轉以下)攻擊後延遲",302: "(2轉以下)ASPD"
}
element_map = {
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
    999: "（不使用）"
}

size_map = {
    0: "小型",
    1: "中型",
    2: "大型"
}

race_map = {
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
    9999: "全種族"
}

unit_map = {
    0: "玩家",
    1: "魔物"
}

class_map = {
    0: "一般",
    1: "首領",
    2: "監護人"
    #2: "玩家"
}




stat_name_sets  = {#裝備基礎編碼
    "armor": [
        "DEF", "STR", "INT", "VIT", "DEX", "AGI", "LUK", "未知7", "未知8",
        "MDEF", "防具等級", "POW", "SPL", "STA", "WIS", "CON", "CRT"
    ],
    "Mweapon": [
        "武器屬性", "武器類型", "武器ATK", "武器MATK", "STR", "INT", "VIT", "DEX", "AGI",
        "LUK", "武器等級", "POW", "SPL", "STA", "WIS", "CON", "CRT"
    ],
    "Rweapon": [
        "武器類型", "武器ATK", "STR", "INT", "VIT", "DEX", "AGI", "LUK", "武器等級",
         "POW", "SPL", "STA", "WIS", "CON", "CRT"
    ],
    "ammo": [
        "屬性", "箭矢/彈藥ATK"
    ],
    "Cannonball": [
        "屬性", "砲彈ATK"
    ]
}


weapon_type_map = { # WPon()

    0: "空手",1: "短劍", 2: "單手劍", 3: "雙手劍", 4: "單手矛", 5: "雙手矛",
    6: "單手斧", 7: "雙手斧", 8: "鈍器", 10: "單手仗", 12: "拳套",
    13: "樂器", 14: "鞭子", 15: "書", 16: "拳刃", 23: "雙手仗",
    11: "弓", 17: "左輪手槍", 18: "來福槍", 19: "格林機關槍",
    20: "霰彈槍", 21: "榴彈槍", 22: "風魔飛鏢"
}



weapon_class_codes = {#輸出用
    0: "Empty",# 空手
    1: "Daggers",  # 短劍
    2: "OneHandedSwords",  # 單手劍
    3: "TwoHandedSword",  # 雙手劍
    4: "Spears",  # 單手矛
    5: "Spears",  # 雙手矛
    6: "Axes",  # 單手斧
    7: "Axes",  # 雙手斧
    8: "Maces",  # 鈍器
    10: "Rods",  # 單手仗
    11: "Bows",  # 弓
    12: "Knuckles",  # 拳套
    13: "Instruments",  # 樂器
    14: "Whips",  # 鞭子
    15: "Books",  # 書
    16: "Katars",  # 拳刃
    17: "Pistol",  # 左輪手槍
    18: "Rifle",  # 來福槍
    19: "Gatling",  # 格林機關槍
    20: "Shotgun",  # 霰彈槍
    21: "Grenade",  # 榴彈槍
    22: "Shuriken",  # 風魔飛鏢
    23: "Rods",  # 雙手仗
}
#weapon_class
weapon_type_size_penalty = {#武器體型修正
    0: [100, 100, 100],# 空手
    1: [100, 75, 50],  # 短劍
    2: [75, 100, 75],  # 單手劍
    3: [75, 75, 100],  # 雙手劍
    4: [75, 75, 100],  # 單手矛
    5: [75, 75, 100],  # 雙手矛
    6: [50, 75, 100],  # 單手斧
    7: [50, 75, 100],  # 雙手斧
    8: [75, 100, 100],  # 鈍器
    10: [100, 100, 100],  # 單手仗
    11: [100, 100, 75],  # 弓
    12: [100, 100, 75],  # 拳套
    13: [75, 100, 75],  # 樂器
    14: [75, 100, 75],  # 鞭子
    15: [100, 100, 50],  # 書
    16: [75, 100, 75],  # 拳刃
    17: [100, 100, 100],  # 左輪手槍
    18: [100, 100, 100],  # 來福槍
    19: [100, 100, 100],  # 格林機關槍
    20: [100, 100, 100],  # 霰彈槍
    21: [100, 100, 100],  # 榴彈槍
    22: [75, 75, 100],  # 風魔飛鏢
    23: [100, 100, 100],  # 雙手仗

}




excluded_stat_names = {#過濾不顯示到效果
    "防具等級","武器等級","武器類型"
    }

# 定義多組排序規則
custom_sort_orders = {
    "增傷詞條": [
        "ATK",
        "MATK",
        "P.ATK",
        "S.MATK",
        "屬性 的",
        "小型",
        "中型",
        "大型",
        "全種族",
        "型怪",
        "全屬性",
        "對象",
        "階級",
        "距離",
        "防禦",
        "技能",
        "詠唱",
    ],
    "ROCalculator輸入": [
        "STR",
        "AGI",
        "VIT",
        "INT",
        "DEX",
        "LUK",
        "POW",
        "STA",
        "WIS",
        "SPL",
        "CON",
        "CRT",
        "技能",
        "CRI",
        "P.ATK",
        "S.MATK",
        "ATK",
        "全種族",
        "型怪",
        "小型",
        "中型",
        "大型",
        "階級",
        "全屬性",
        "對象",
        "魔法傷害",
        "爆擊傷害",
        "C.RATE",
        "距離",
    ],
}

def get_custom_sort_value(key, sort_mode):
    """依照指定 sort_mode 的順序表來決定排序位置"""
    order_list = custom_sort_orders.get(sort_mode, [])
    for idx, keyword in enumerate(order_list):
        if keyword in key:
            return idx
    return len(order_list)  # 沒找到的放最後


# 屬性倍率表（level, attacker, defender）

# Lv1 ~ Lv4 相剋表（依 element_map 順序）
damage_tables = {
    1: [ #無   水   地    火   風   毒    聖    暗   念  不死
        [100, 100, 100, 100, 100, 100, 100, 100,  90, 100],
        [100,  25, 100, 150,  90, 150, 100, 100, 100, 100],
        [100, 100,  25,  90, 150, 150, 100, 100, 100, 100],
        [100,  90, 150,  25, 100, 150, 100, 100, 100, 125],
        [100, 150,  90, 100,  25, 150, 100, 100, 100, 100],
        [100, 150, 150, 150, 150,   0,  75,  75,  75,  75],
        [100, 100, 100, 100, 100,  75,   0, 125, 100, 125],
        [100, 100, 100, 100, 100,  75, 125,   0, 100,   0],
        [ 90, 100, 100, 100, 100,  75,  90,  90, 125, 100],
        [100,  90, 100, 100, 100,  75, 125,   0, 100,   0],
    ],
    2: [ #無   水   地    火   風   毒    聖    暗   念  不死
        [100, 100, 100, 100, 100, 100, 100, 100,  70, 100],
        [100,   0, 100, 175,  80, 150, 100, 100, 100, 100],
        [100, 100,   0,  80, 175, 150, 100, 100, 100, 100],
        [100,  80, 175,   0, 100, 150, 100, 100, 100, 150],
        [100, 175,  80, 100,   0, 150, 100, 100, 100, 100],
        [100, 150, 150, 150, 150,   0,  75,  75,  75,  50],
        [100, 100, 100, 100, 100,  75,   0, 150, 100, 150],
        [100, 100, 100, 100, 100,  75, 150,   0, 100,   0],
        [ 70, 100, 100, 100, 100,  75,  80,  80, 150, 125],
        [100,  80, 100, 100, 100,  50, 150,   0, 125,   0],
    ],
    3: [ #無   水   地    火   風   毒    聖    暗   念  不死
        [100, 100, 100, 100, 100, 100, 100, 100,  50, 100],
        [100,   0, 100, 200,  70, 125, 100, 100, 100, 100],
        [100, 100,   0,  70, 200, 125, 100, 100, 100, 100],
        [100,  70, 200,   0, 100, 125, 100, 100, 100, 175],
        [100, 200,  70, 100,   0, 125, 100, 100, 100, 100],
        [100, 125, 125, 125, 125,   0,  50,  50,  50,  25],
        [100, 100, 100, 100, 100,  50,   0, 175, 100, 175],
        [100, 100, 100, 100, 100,  50, 175,   0, 100,   0],
        [ 50, 100, 100, 100, 100,  50,  70,  70, 175, 150],
        [100,  70, 100, 100, 100,  25, 175,   0, 150,   0],
    ],
    4: [ #無   水   地    火   風   毒    聖    暗   念  不死
        [100, 100, 100, 100, 100, 100, 100, 100,   0, 100],
        [100,   0, 100, 200,  60, 125, 100, 100, 100, 100],
        [100, 100,   0,  60, 200, 125, 100, 100, 100, 100],
        [100,  60, 200,   0, 100, 125, 100, 100, 100, 200],
        [100, 200,  60, 100,   0, 125, 100, 100, 100, 100],
        [100, 125, 125, 125, 125,   0,  50,  50,  50,   0],
        [100, 100, 100, 100, 100,  50,   0, 200, 100, 200],
        [100, 100, 100, 100, 100,  50, 200,   0, 100,   0],
        [  0, 100, 100, 100, 100,  50,  60,  60, 200, 175],
        [100,  60, 100, 100, 100,   0, 200,   0, 175,   0],
    ]
}


equipid_mapping = {#主程式equip to ROCalculator 轉換
    "equip_STR": "STR",
    "equip_AGI": "AGI",
    "equip_VIT": "VIT",
    "equip_INT": "INT",
    "equip_DEX": "DEX",
    "equip_LUK": "LUK",
    "equip_POW": "POW",
    "equip_STA": "STA",
    "equip_WIS": "WIS",
    "equip_SPL": "SPL",
    "equip_CON": "CON",
    "equip_CRT": "CRT",
    "Use_Skills": "SkillDamagePercent",
    "HP":"HP",
    "HPPercent":"HPPercent",
    "SP":"SP",
    "SPPercent":"SPPercent",
    "HPRegenPercent":"HPRegenPercent",
    "SPRegenPercent":"SPRegenPercent",

    #魔法
    "SMATK": "SMATK",
    "MATK_armor": "Matk",
    "MATK_percent": "MatkPercent",
    "RaceMatkPercent": "RaceMatkPercent",
    "SizeMatkPercent": "SizeMatkPercent",
    "LevelMatkPercent": "LevelMatkPercent",
    "ElementalMatkPercent": "ElementalMatkPercent",
    "ElementalMagicPercent": "ElementalMagicPercent",
    "target_monsterMDamage": "MonsterMatkPercent",

    #物理
    "PATK": "PATK",
    "CRATE":"CRIDR",
    "ATK_armor": "Atk",
    "ATK_percent": "AtkPercent",
    "RaceAtkPercent": "RaceAtkPercent",
    "SizeAtkPercent": "SizeAtkPercent",
    "LevelAtkPercent": "LevelAtkPercent",
    "ElementalAtkPercent": "ElementalAtkPercent",
    "Damage_CRI": "CriDamagePercent",
    "MeleeAttackDamage": "MeleeDamagePercent",
    "RangeAttackDamage": "RangedDamagePercent",
    "target_monsterDamage": "MonsterAtkPercent",
    "Damage_HIT": "HitAtkDamagePercent",
}

status_mapping = {#主程式status to ROCalculator 轉換
    "BaseLv": "Level",
    "JobLv": "JOBLevel",
    "job_idcore": "classid",
    "base_STR": "STR",
    "base_AGI": "AGI",
    "base_VIT": "VIT",
    "base_INT": "INT",
    "base_DEX": "DEX",
    "base_LUK": "LUK",
    "base_POW": "POW",
    "base_STA": "STA",
    "base_WIS": "WIS",
    "base_SPL": "SPL",
    "base_CON": "CON",
    "base_CRT": "CRT",
}

weapon_mapping = {#主程式weapon to ROCalculator 轉換
    "weapon_codes": ("type", "id"),
    "weapon_weapon_size0": ("type", "sizefix", "small"),
    "weapon_weapon_size1": ("type", "sizefix", "middle"),
    "weapon_weapon_size2": ("type", "sizefix", "large"),
    "weaponR_Level": ("level", "id"),
    "weaponGradeR": ("grade", "id"),
    "ATK_Mweapon": "ATK",
    "MATK_Mweapon": "MATK",
    "weaponRefineR": "refinelevel",
    "ammoATK": "ArrowATK"
}

SubWeapon_mapping = {#主程式Subweapon to ROCalculator 轉換
    "Subweapon_codes": ("type", "id"),
    "weaponL_Level": ("level", "id"),
    "weaponGradeL": ("grade", "id"),
    "MATK_MweaponL": "MATK",
    "weaponRefineL": "refinelevel"
}
SkillOption_mapping = {#主程式Subweapon to ROCalculator 轉換
    "WeaponMasteryATK": "WeaponMasteryATKInput",
}

from PySide6.QtCore import Qt, QElapsedTimer, QTimer
from PySide6.QtWidgets import QWidget
from PySide6 import QtGui

class CastBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # durations
        self._cast_ms = 1
        self._gcd_ms = 0
        self._cd_ms = 0

        # timers
        self._cast_elapsed = QElapsedTimer()
        self._gcd_elapsed = QElapsedTimer()
        self._cd_elapsed = QElapsedTimer()

        # progress
        self._cast_progress = 0.0
        self._gcd_progress = 0.0
        self._cd_progress = 0.0

        # state
        self._state = "idle"  # idle | cast | post

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.update)

        self.setFixedHeight(10)

    def start(self, cast_ms: int, gcd_ms: int = 0, cooldown_ms: int = 0):
        self._cast_ms = max(1, int(cast_ms))
        self._gcd_ms = max(0, int(gcd_ms))
        self._cd_ms = max(0, int(cooldown_ms))

        self._cast_elapsed.restart()
        self._cast_progress = 0.0

        self._gcd_progress = 0.0
        self._cd_progress = 0.0

        self._state = "cast"
        self._timer.start()
        self.update()

    def stop(self):
        self._timer.stop()
        self._state = "idle"
        self._cast_progress = 0.0
        self._gcd_progress = 0.0
        self._cd_progress = 0.0
        self.update()

    def _enter_post(self):
        """詠唱結束後：綠色滿格，開始跑 GCD / CD（覆蓋都要留下）"""
        self._state = "post"
        self._cast_progress = 1.0  # 綠色滿格保留

        # GCD：沒有時間也要直接蓋滿（照你「沒有就直接蓋上」的規則）
        if self._gcd_ms > 0:
            self._gcd_elapsed.restart()
            self._gcd_progress = 0.0
        else:
            self._gcd_progress = 1.0  # 直接 100% 淺藍覆蓋

        # CD：沒有時間也直接蓋滿
        if self._cd_ms > 0:
            self._cd_elapsed.restart()
            self._cd_progress = 0.0
        else:
            self._cd_progress = 1.0  # 直接 100% 灰色覆蓋

    def paintEvent(self, event):
        # ---------- update ----------
        if self._timer.isActive():
            if self._state == "cast":
                t = self._cast_elapsed.elapsed()
                self._cast_progress = min(1.0, t / self._cast_ms)
                if self._cast_progress >= 1.0:
                    self._enter_post()

            elif self._state == "post":
                # GCD progress
                if self._gcd_ms > 0 and self._gcd_progress < 1.0:
                    t = self._gcd_elapsed.elapsed()
                    self._gcd_progress = min(1.0, t / self._gcd_ms)
                    if self._gcd_progress >= 1.0:
                        self._gcd_progress = 1.0  # 跑完也留下

                # CD progress
                if self._cd_ms > 0 and self._cd_progress < 1.0:
                    t = self._cd_elapsed.elapsed()
                    self._cd_progress = min(1.0, t / self._cd_ms)
                    if self._cd_progress >= 1.0:
                        self._cd_progress = 1.0  # 跑完也留下

                # 都不動了就停 timer（覆蓋留著也不需要一直刷新）
                animating = (
                    (self._gcd_ms > 0 and self._gcd_progress < 1.0) or
                    (self._cd_ms > 0 and self._cd_progress < 1.0)
                )
                if not animating:
                    self._timer.stop()

        # ---------- paint ----------
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, False)

        rect = self.rect().adjusted(0, 0, -1, -1)

        # border
        p.setPen(QtGui.QPen(QtGui.QColor(120, 120, 120)))
        p.setBrush(Qt.NoBrush)
        p.drawRect(rect)

        # green: cast grows, post stays full
        if self._state == "cast":
            green_ratio = self._cast_progress
        elif self._state == "post":
            green_ratio = 1.0
        else:
            green_ratio = 0.0

        green_w = int(rect.width() * green_ratio)
        if green_w > 0:
            green_rect = rect.adjusted(1, 1, -(rect.width() - green_w) - 1, -1)
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(0, 200, 0))
            p.drawRect(green_rect)

        # GCD overlay: light-blue, LEFT -> RIGHT, stays when finished
        if self._state == "post" and self._gcd_progress > 0.0:
            w = int(rect.width() * self._gcd_progress)
            if w > 0:
                r = rect.adjusted(1, 1, -(rect.width() - w) - 1, -1)
                p.setPen(Qt.NoPen)
                p.setBrush(QtGui.QColor(0, 255, 255, 255))  # 淺藍半透明
                p.drawRect(r)

        # CD overlay: gray, LEFT -> RIGHT, stays when finished
        if self._state == "post" and self._cd_progress > 0.0:
            w = int(rect.width() * self._cd_progress)
            if w > 0:
                r = rect.adjusted(1, 1, -(rect.width() - w) - 1, -1)
                p.setPen(Qt.NoPen)
                p.setBrush(QtGui.QColor(0, 0, 0, 100))  # 灰色半透明
                p.drawRect(r)

        p.end()






from PySide6.QtWidgets import QDialog
from UI.ui_savemanager import Ui_SaveManagerDialog

class SaveManagerDialog(QDialog, Ui_SaveManagerDialog):#儲存裝被選則
    def __init__(self, part_name, save_list, on_delete, parent=None):
        super().__init__(parent)
        self.setupUi(self)   # 這裡載入 Designer 畫的 UI

        self.setWindowTitle(tr("window.save_manager", part_name=part_name))
        self.part_name = part_name
        self.save_list = save_list
        self.selected_save = None
        self.on_delete = on_delete

        self.listWidget.addItems(self.save_list)
        self.loadButton.clicked.connect(self.load_selected)
        self.deleteButton.clicked.connect(self.delete_selected)
        self.cancelButton.clicked.connect(self.reject)
        self.listWidget.itemDoubleClicked.connect(self.load_selected)


    def load_selected(self, item=None):
        if item:  # 如果是雙擊傳進來的 item
            self.selected_save = item.text()
            self.accept()
        else:  # 如果是按下按鈕呼叫
            current_item = self.listWidget.currentItem()
            if current_item:
                self.selected_save = current_item.text()
                self.accept()

    def delete_selected(self):
        current_item = self.listWidget.currentItem()
        if current_item:
            save_name = current_item.text()
            confirm = QMessageBox.question(
                self,
                tr("message.title.confirm_delete"),
                tr("message.confirm_delete_save", save_name=save_name),
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                # 👇 呼叫主程式的刪除邏輯
                self.on_delete(self.part_name, save_name)

                # 從清單移掉
                self.save_list.remove(save_name)
                self.listWidget.takeItem(self.listWidget.row(current_item))




# 特性點規律已集中到 ro_core；保留此 wrapper 避免既有 Desktop 呼叫受影響。
def get_total_tstat_points(level: int) -> int:
    return core_get_total_tstat_points(level)




skill_df = pd.DataFrame(columns=[#檔案不在使用硬編碼以防跳錯
    "ID","Code","Name","attack_type","Rangedamage","skill_cannon","Special_WPRange","Slv","Calculation","element","hits",
    "Critical_hit","combo","combo_element","combo_hits","Special_Calculation","combo_Special_Calculation",
    "monster_race","skill_buff","Special_Critical_hit","decay_hits","bonus_add","bonus_step"
])

# 初始化技能映射變數
skill_map = {}
skill_map_all = {}

def load_skill_map(filepath=None):
    global skill_map, skill_map_all, skill_df
    import skill_tree
    import pandas as pd
    import os

    # 若 filepath 沒指定 → 不做任何事
    if filepath is None:
        print("未指定路徑，使用預設空白技能列表。")
        return

    if not os.path.exists(filepath):
        print(f"{filepath} 找不到，保留空白技能列表。")
        return

    skill_df = pd.read_csv(filepath)

    # === ItemSearchApp 用 ===
    skill_map = dict(zip(skill_df["ID"], skill_df["Name"]))
    skill_map_all = skill_df.set_index("ID").to_dict(orient="index")

    # === skill_tree 用 ===
    skill_tree.skill_id_to_name = dict(zip(skill_df["ID"], skill_df["Name"]))
    skill_tree.skill_code_to_id = dict(zip(skill_df["Code"], skill_df["ID"]))
    skill_tree.skill_code_to_name = dict(zip(skill_df["Code"], skill_df["Name"]))


    print("技能列表載入成功")


load_skill_map() #讀取SKILL列表

import re

def update_skill_delay_labels(#技能延遲標籤更新
    skill_name: str,
    skill_map_all: dict,
    lua_text: str,
    fix_label,
    delay_label,
    cast_bar,
    skill_level,
    effect_dict,
    total_dex,
    total_int,
):
    """Stage 21.24: Desktop UI wrapper over the shared ro_core timing engine."""
    shared = _core_stage24_calculate_skill_timing_from_effects(
        skill_name=skill_name,
        skill_map_all=skill_map_all,
        lua_text=lua_text,
        skill_level=skill_level,
        effect_dict=effect_dict,
        total_dex=total_dex,
        total_int=total_int,
    )

    if not shared.get("available"):
        error_code = shared.get("error_code")
        if error_code == "skill_code_not_found":
            fix_label.setText(tr("message.skill_code_not_found"))
        elif error_code == "lua_skill_not_found":
            fix_label.setText(
                tr(
                    "message.lua_skill_not_found",
                    skill_code=shared.get("skill_code", ""),
                )
            )
        else:
            fix_label.setText(tr("message.skill_data_parse_failed"))
        delay_label.setText("")
        return 0.0

    display = shared["display"]
    fix_label.setText(
        tr(
            "label.cast_delay_info",
            fixed=display["fixed"],
            fixed_raw=display["fixed_raw"],
            stat=display["variable"],
            stat_raw=display["variable_raw"],
        )
    )
    delay_label.setText(
        tr(
            "label.post_delay_info",
            gpost=display["global_post"],
            gpost_raw=display["global_post_raw"],
            spost=display["cooldown"],
            spost_raw=display["cooldown_raw"],
        )
    )

    # Preserve the Desktop CastBar / ASPD-GCD legacy indexing exactly.
    runtime = shared["desktop_runtime"]
    cast_bar.start(
        int(runtime["cast_total_ms"]),
        int(runtime["global_post_ms"]),
        int(runtime["cooldown_ms"]),
    )
    return max(0.0, float(runtime["global_post_raw_ms"])) / 1000.0

#動態下拉式選單
import re
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QComboBox

class MultiComboField(QWidget):
    def __init__(self, options, parent=None):
        """
        options: list[(label, data)]
                 例如 [("無形",0),("不死",1),...,("龍族",9)]
                 可包含 ("", None) 作為空白選項
        """
        super().__init__(parent)
        self.options = options
        self.combos: list[QComboBox] = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self.box_layout = QHBoxLayout()
        self.box_layout.setContentsMargins(0, 0, 0, 0)
        self.box_layout.setSpacing(6)
        root.addLayout(self.box_layout)

        self.add_btn = QPushButton("+")
        self.add_btn.setFixedWidth(28)
        self.add_btn.clicked.connect(self.add_combo)
        root.addWidget(self.add_btn)

        # 預設先放一個下拉
        self.add_combo()

    def _make_combo(self) -> QComboBox:
        cb = QComboBox()
        for label, data in self.options:
            cb.addItem(label, data)
        return cb

    def add_combo(self, preset_data=None):
        cb = self._make_combo()
        if preset_data is not None:
            idx = cb.findData(preset_data)
            if idx < 0 and isinstance(preset_data, str):
                idx = cb.findText(preset_data)
            if idx >= 0:
                cb.setCurrentIndex(idx)
        self.box_layout.addWidget(cb)
        self.combos.append(cb)
        return cb

    def set_values(self, values):
        """values: 例如 [0,5,9] 或 ['無形','不死'] 或混合"""
        for cb in self.combos:
            cb.deleteLater()
        self.combos.clear()

        if not values:
            self.add_combo()
            return

        for v in values:
            self.add_combo(v)

    def get_values(self):
        """回傳去重後的 userData 陣列（忽略空白/None）"""
        vals = []
        for cb in self.combos:
            data = cb.currentData()
            if data is None or str(data) == "":
                continue
            vals.append(data)

        uniq, seen = [], set()
        for v in vals:
            if v not in seen:
                seen.add(v)
                uniq.append(v)
        return uniq

import requests

UPDATER_EXE = "update.exe"
TARGET_EXE = "ItemSearchApp.exe"
GITHUB_OWNER = "z2911902"
GITHUB_REPO = "ROItemSearchApp"

GITHUB_LATEST_RELEASE_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)

ZIP_URL_TEMPLATE = (
    "https://github.com/z2911902/ROItemSearchApp/releases/download/{ver}/ROItemSearchApp.zip"
)


def read_remote_version_github(timeout: int = 8) -> str:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ROItemSearchApp-Updater",
    }
    r = requests.get(GITHUB_LATEST_RELEASE_API, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    # tag_name 例如 "v1.2.3"
    return (data.get("tag_name") or "").strip()


def normalize_version(v: str) -> tuple[tuple[int, ...], int]:
    """
    'v0.1.22-260110' -> ((0, 1, 22), 260110)
    'v0.1.22'        -> ((0, 1, 22), 0)
    """
    v = v.strip().lstrip("vV")

    # 拆版本與日期（日期可有可無）
    if "-" in v:
        ver_part, date_part = v.split("-", 1)
    else:
        ver_part, date_part = v, "0"

    # 版本段：0.1.22
    ver_nums = tuple(int(x) for x in ver_part.split(".") if x.isdigit())

    # 日期段：只取前面的數字（避免後面夾字）
    m = re.match(r"(\d+)", date_part.strip())
    date_num = int(m.group(1)) if m else 0

    return ver_nums, date_num


def compare_versions(a: str, b: str) -> int:
    """
    回傳:
      1  表示 a > b
      0  表示 a == b
     -1  表示 a < b

    規則：
      先比主版本 (0,1,22)
      若相同再比日期 260110
    """
    (va, da) = normalize_version(a)
    (vb, db) = normalize_version(b)

    n = max(len(va), len(vb))
    va = va + (0,) * (n - len(va))
    vb = vb + (0,) * (n - len(vb))

    if va != vb:
        return (va > vb) - (va < vb)

    return (da > db) - (da < db)



import sys
import csv
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel, QComboBox,
    QFormLayout, QLineEdit, QPushButton, QMessageBox, QHBoxLayout
)
from PySide6.QtCore import Qt
skill_editor = None
class CSVEditor(QMainWindow):
    def center_to_parent(self):
        if self.parent():
            parent_geometry = self.parent().frameGeometry()
            parent_center = parent_geometry.center()
            this_geometry = self.frameGeometry()
            this_geometry.moveCenter(parent_center)
            self.move(this_geometry.topLeft())
        else:
            # 若沒有父視窗，就置中到螢幕中央
            screen = QApplication.primaryScreen().geometry()
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2
            self.move(x, y)

    def __init__(self, file_path, parent=None):
        super().__init__(parent)  # ✅ 把 parent 傳給 QMainWindow
        self.file_path = file_path
        self.setWindowTitle(tr("window.skill_editor"))
        self.resize(600, 600)
        self.center_to_parent()
        self.file_path = file_path

        # 主容器
        widget = QWidget()
        self.setCentralWidget(widget)
        main_layout = QVBoxLayout(widget)

        # === 搜尋 + 選擇 技能（同一行） ===
        search_name_layout = QHBoxLayout()

        search_label = QLabel(tr("label.search_skill"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(tr("placeholder.search_name"))
        self.search_box.textChanged.connect(self.filter_names)

        # 🔹 清空按鈕
        self.clear_search_button = QPushButton(tr("button.clear"))
        self.clear_search_button.setFixedWidth(50)
        self.clear_search_button.setToolTip(tr("tooltip.clear_search_text"))
        self.clear_search_button.clicked.connect(self.search_box.clear)

        name_label = QLabel(tr("label.select_skill"))
        self.name_combo = QComboBox()
        self.name_combo.setMinimumWidth(200)

        # 加入到同一行
        search_name_layout.addWidget(search_label)
        search_name_layout.addWidget(self.search_box)
        search_name_layout.addWidget(self.clear_search_button)
        search_name_layout.addSpacing(20)
        search_name_layout.addWidget(name_label)
        search_name_layout.addWidget(self.name_combo)
        search_name_layout.addStretch()

        main_layout.addLayout(search_name_layout)



        # === 欄位編輯區 ===
        self.form = QFormLayout()
        main_layout.addLayout(self.form)
        # 建立一個橫向排版
        button_layout = QHBoxLayout()

        # 儲存但不關閉
        self.save_only_button = QPushButton(tr("button.save_only"))
        self.save_only_button.clicked.connect(lambda: self.save_changes(close_after=False))
        button_layout.addWidget(self.save_only_button)

        # 儲存並關閉
        self.save_button = QPushButton(tr("button.save_and_close"))
        self.save_button.clicked.connect(lambda: self.save_changes(close_after=True))
        button_layout.addWidget(self.save_button)

        # 加到主layout（假設main_layout是垂直排版 QVBoxLayout）
        main_layout.addLayout(button_layout)

        # === 初始化資料 ===
        self.all_rows = []     # 存所有行
        self.filtered_rows = []  # 搜尋後顯示的行
        self.field_edits = {}

        # === 載入 CSV ===
        self.load_csv(file_path)
        self.name_combo.currentIndexChanged.connect(self.update_fields)

    def load_csv(self, file_path):
        """讀取 CSV 並初始化資料"""
        with open(file_path, newline='', encoding='utf-8-sig') as csvfile:
            reader = csv.reader(csvfile)
            rows = list(reader)

        if not rows:
            QMessageBox.warning(self, tr("message.title.error"), tr("message.csv_empty"))
            return

        self.headers = rows[0]
        self.data = rows[1:]

        # 找出 Name 欄位索引
        try:
            self.name_index = next(i for i, h in enumerate(self.headers) if h.lower() in ["name", "skillname"])
        except StopIteration:
            QMessageBox.warning(self, tr("message.title.error"), tr("message.csv_missing_name_column"))
            return

        # 將所有行資料加入
        self.all_rows = [row for row in self.data if len(row) > self.name_index]
        self.filtered_rows = self.all_rows.copy()

        # 填入所有 Name（允許重複）
        self.name_combo.clear()
        self.name_combo.addItems([row[self.name_index].strip() for row in self.filtered_rows])


        # === 欄位資訊（名稱 + 提示文字） ===
        header_info = {
            "ID": {
                "label": tr("skill_editor.field.id"),
                "tooltip": "技能在資料表中的唯一識別碼，通常不可修改。"
            },
            "Code": {
                "label": tr("skill_editor.field.code"),
                "tooltip": "內部使用的技能代碼，用於程式判斷。"
            },
            "attack_type": {
                "label": tr("skill_editor.field.attack_type"),
                "tooltip": "選擇攻擊類型：magic 為魔法攻擊，physical 為物理攻擊。"
            },
            "Slv": {
                "label": tr("skill_editor.field.skill_level"),
                "tooltip": "此欄可填入技能等級對應數值。(不輸入時不顯示在下拉式選單)"
            },
            "Calculation": {
                "label": tr("skill_editor.field.calculation"),
                "tooltip": "技能傷害或效果的計算公式，可使用 BaseLv、Sklv 等變數。"
            },
            "element": {
                "label": tr("skill_editor.field.element"),
                "tooltip": "屬性(無=0,水=1,地=2,火=3,風=4,毒=5,聖=6,暗=7,念=8,不死=9)"
            },
            "hits": {
                "label": tr("skill_editor.field.hits"),
                "tooltip": "技能打擊次數。(負值為總傷害/次數)"
            },
            "Critical_hit": {
                "label": tr("skill_editor.field.critical_hit"),
                "tooltip": "設定爆擊倍率，例如 0.5 代表半爆擊；設定命中增傷設定0；負數代表兩者不啟用。"
            },
            "combo": {
                "label": tr("skill_editor.field.combo"),
                "tooltip": "此技能觸發的下一個公式。"
            },
            "combo_element": {
                "label": tr("skill_editor.field.combo_element"),
                "tooltip": "連段技能的屬性。"
            },
            "combo_hits": {
                "label": tr("skill_editor.field.combo_hits"),
                "tooltip": "連段技能的打擊次數。(負值為總傷害/次數)"
            },
            "combo_Special_Calculation": {
                "label": tr("skill_editor.field.combo_special_calculation"),
                "tooltip": "觸發特殊條件下的技能公式，會覆蓋連段公式。"
            },
            "Special_Calculation": {
                "label": tr("skill_editor.field.special_calculation"),
                "tooltip": "觸發特殊條件下的技能公式，會覆蓋一般公式。"
            },
            "monster_race": {
                "label": tr("skill_editor.field.monster_race"),
                "tooltip": "怪物種族觸發特別公式。"
            },
            "skill_buff": {
                "label": tr("skill_editor.field.skill_buff"),
                "tooltip": "目前技能觸發的特殊技能 ID（例如狀態技能）。"
            },
            "Special_Critical_hit": {
                "label": tr("skill_editor.field.special_critical_hit"),
                "tooltip": "觸發特殊條件爆擊倍率，例如 0.5 代表半爆擊；設定命中增傷設定0；負數代表兩者不啟用。"
            },
            "decay_hits": {
                "label": tr("skill_editor.field.decay_hits"),
                "tooltip": "設定每段的遞增或遞減次數，例如 4 代表 4 段。"
            },
            "bonus_add": {
                "label": tr("skill_editor.field.bonus_add"),
                "tooltip": "起始加成（或乘數），可輸入 +800 或 *1。"
            },
            "bonus_step": {
                "label": tr("skill_editor.field.bonus_step"),
                "tooltip": "每段遞增/減的變化量，例如 -100 或 +0.1。"
            },
            "Rangedamage": {
                "label": tr("skill_editor.field.rangedamage"),
                "tooltip": "技能套用遠距傷害計算。"
            },
            "Delayed_Rangedamage": {
                "label": tr("skill_editor.field.delayed_rangedamage"),
                "tooltip": "遠距傷害移到def後計算。"
            },
            "half_bypass_def": {
                "label": tr("skill_editor.field.half_bypass_def"),
                "tooltip": "無視後DEF乘算，數字加算到前DEF。"
            },
            "half_bypass_res": {
                "label": tr("skill_editor.field.half_bypass_res"),
                "tooltip": "無視RES"
            },
            "special_wprange": {
                "label": tr("skill_editor.field.special_wprange"),
                "tooltip": "裝備該類型的武器自動轉換遠傷。"
            },
            "skill_SpecialATK": {
                "label": tr("skill_editor.field.skill_special_atk"),
                "tooltip": "綠光減傷前加算。"
            },
            "skill_cannon": {
                "label": tr("skill_editor.field.skill_cannon"),
                "tooltip": "計算公式加入砲彈ATK。"
            }

        }


        # 建立欄位編輯器
        for header in self.headers:
            if header.lower() == "name":
                continue

            # 取得中文名稱與提示文字
            info = header_info.get(header, {})
            display_name = info.get("label", header)
            tooltip_text = info.get("tooltip", "")

            label_title = QLabel(f"{display_name}：")

            # 有提示文字就加上 tooltip
            if tooltip_text:
                label_title.setToolTip(tooltip_text)

            # 建立編輯欄位（例：QLineEdit 或 QComboBox）
            if header.lower() == "attack_type":
                edit_field = QComboBox()                
                edit_field.addItem("物理", "physical")
                edit_field.addItem("魔法", "magic")
                edit_field.addItem("龍息", "d_b")
                edit_field.addItem("護盾", "shield")

            elif header.lower() in ("element","combo_element"):
                edit_field = QComboBox()
                element_options = [
                    ("", None),
                    ("無", 0), ("水", 1), ("地", 2), ("火", 3), ("風", 4),
                    ("毒", 5), ("聖", 6), ("暗", 7), ("念", 8), ("不死", 9),
                ]
                for label, code in element_options:
                    edit_field.addItem(label, code)
            
            elif header.lower() == "monster_race":
                race_options = [
                    ("", None),  # 空白
                    ("無形", 0), ("不死", 1), ("動物", 2), ("植物", 3), ("昆蟲", 4),
                    ("魚貝", 5), ("惡魔", 6), ("人形", 7), ("天使", 8), ("龍族", 9),
                ]
                edit_field = MultiComboField(race_options)

            elif header.lower() == "special_wprange":
                WPClass_options = [
                    ("", None),  # 空白
                    ("短劍", 1), ("單手劍", 2), ("雙手劍", 3), ("單手矛", 4),("雙手矛", 5),
                    ("單手斧", 6), ("雙手斧", 7), ("鈍器", 8), ("單手仗", 10), ("拳套", 12),
                    ("樂器", 13), ("鞭子", 14), ("書", 15),("拳刃", 16), ("雙手仗", 23),
                    ("弓", 11), ("左輪手槍", 17), ("來福槍", 18), ("格林機關槍", 19), ("霰彈槍", 20), ("榴彈槍", 21), ("風魔飛鏢", 22),
                ]
                edit_field = MultiComboField(WPClass_options)

            # ★★★ 用勾選框 ★★★
            elif header.lower() in ("rangedamage","half_bypass_def","half_bypass_res","skill_cannon","delayed_rangedamage"):
                edit_field = QCheckBox()
            else:
                edit_field = QLineEdit()
                if header.lower() in ["id", "code"]:
                    edit_field.setReadOnly(True)
                    edit_field.setStyleSheet("background-color: #f0f0f0; color: #666;")

            self.field_edits[header] = edit_field
            self.form.addRow(label_title, edit_field)

        if self.filtered_rows:
            self.update_fields(0)

    def filter_names(self, text):
        """模糊搜尋 Name"""
        self.filtered_rows = [row for row in self.all_rows if text.lower() in row[self.name_index].lower()]
        self.name_combo.clear()
        self.name_combo.addItems([row[self.name_index].strip() for row in self.filtered_rows])
        if self.filtered_rows:
            self.update_fields(0)
        else:
            for widget in self.field_edits.values():
                if isinstance(widget, QLineEdit):
                    widget.setText("")
                elif isinstance(widget, QComboBox):
                    widget.setCurrentIndex(-1)  # 清空選擇（沒有選項）


    def update_fields(self, index):
        if index < 0 or index >= len(self.filtered_rows):
            return
        row = self.filtered_rows[index]
        for i, header in enumerate(self.headers):
            key = header.strip().lower()
            if key == "name":
                continue
            if header in self.field_edits:
                value = row[i] if i < len(row) else ""
                widget = self.field_edits[header]

                # monster_race（MultiComboField，多值）
                #if isinstance(widget, MultiComboField) and key == "monster_race":
                if isinstance(widget, MultiComboField) and key in ("monster_race","special_wprange"):
                    txt = str(value).strip()
                    if not txt:
                        widget.set_values([])  # 顯示 1 個空白下拉
                    else:
                        import re
                        parts = re.split(r'[,\|;/\s]+', txt)
                        vals = []
                        for p in parts:
                            if not p:
                                continue
                            try:
                                vals.append(int(float(p)))   # 數字優先
                            except:
                                vals.append(p)               # 兼容舊中文
                        widget.set_values(vals)
                    continue

                # element（單值 QComboBox）
                if isinstance(widget, QComboBox) and key in ("element","combo_element"):
                    txt = str(value).strip()
                    if txt == "":
                        idx = widget.findData(None)  # 空白
                    else:
                        try:
                            num = int(float(txt))
                            idx = widget.findData(num)
                        except:
                            # 舊資料若是中文
                            idx = widget.findText(txt)
                    widget.setCurrentIndex(idx if idx >= 0 else widget.findData(None))
                    continue

                if isinstance(widget, QComboBox) and key == "attack_type":
                    txt = ("" if value is None else str(value)).strip()
                    if txt == "":
                        # 若下拉有空白選項
                        idx = widget.findData(None)
                        if idx < 0:
                            idx = widget.findText("")
                    else:
                        # 先找英文 userData（magic/physical）
                        idx = widget.findData(txt.lower())
                        if idx < 0:
                            # 舊資料可能是中文 → 映射到英文再找
                            zh2en = {"魔法": "magic", "物理": "physical", "龍息":"d_b" , "護盾":"shield"}
                            mapped = zh2en.get(txt)
                            if mapped:
                                idx = widget.findData(mapped)
                        if idx < 0:
                            # 最後相容：用顯示文字找
                            idx = widget.findText(txt)
                    widget.setCurrentIndex(idx if idx >= 0 else 0)
                    continue

                if isinstance(widget, QCheckBox) and key in ("rangedamage","half_bypass_def","half_bypass_res","skill_cannon","delayed_rangedamage"):
                    widget.setChecked(str(value).strip() in ("1", "true", "True"))
                    continue



                # 其它欄位照舊
                if isinstance(widget, QComboBox):
                    idx = widget.findText(str(value))
                    widget.setCurrentIndex(idx if idx >= 0 else 0)
                else:
                    widget.setText(str(value))





    def save_changes(self, close_after=True):
        index = self.name_combo.currentIndex()
        if index < 0 or index >= len(self.filtered_rows):
            QMessageBox.warning(self, tr("message.title.error"), tr("message.select_name_first"))
            return

        row = self.filtered_rows[index]
        for i, header in enumerate(self.headers):
            key = header.strip().lower()
            if key == "name":
                continue
            if header in self.field_edits:
                widget = self.field_edits[header]

                # 只讀跳過
                from PySide6.QtWidgets import QLineEdit, QComboBox
                if isinstance(widget, QLineEdit) and widget.isReadOnly():
                    continue

                # ✅ 強制規格：element / monster_race 只寫數字；沒選就空白
                if key in ("element","combo_element") and isinstance(widget, QComboBox):
                    data = widget.currentData()
                    new_value = "" if (data is None or str(data) == "") else str(int(data))

                elif key in ("monster_race","special_wprange") and hasattr(widget, "get_values"):
                    vals = widget.get_values()  # e.g. [0,5,9] 或 []
                    # 過濾成純數字字串
                    nums = []
                    for v in vals:
                        if v is None or str(v).strip() == "":
                            continue
                        try:
                            nums.append(str(int(v)))
                        except:
                            # 若意外拿到中文，直接忽略以避免寫中文
                            continue
                    new_value = ",".join(nums) if nums else ""

                # 其他欄位照舊；attack_type 依你規格存英文
                elif isinstance(widget, QComboBox) and key == "attack_type":
                    new_value = widget.currentData()  # "magic"/"physical"
                elif isinstance(widget, QComboBox):
                    new_value = widget.currentText()
                elif isinstance(widget, QCheckBox) and key in ("rangedamage","half_bypass_def","half_bypass_res","skill_cannon","delayed_rangedamage"):
                    new_value = "1" if widget.isChecked() else "0"

                else:
                    new_value = widget.text()

                if i < len(row):
                    row[i] = new_value
                else:
                    row.append(new_value)


        # 這裡很重要：要把這筆 row 寫回 self.data 對應的那一筆
        id_index = self.headers.index("ID")
        row_id = row[id_index]
        for i, drow in enumerate(self.data):
            if drow[id_index] == row_id:
                self.data[i] = row[:]  # 或用 copy()
                break

        # 這裡才進行存檔，寫 self.data
        try:
            with open(self.file_path, "w", newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(self.headers)
                writer.writerows(self.data)
            load_skill_map("data/skillneme.csv")   # 重新載入技能列表
            if close_after:
                self.close()
        except Exception as e:
            QMessageBox.critical(self, tr("message.title.error"), tr("message.save_failed", error=e))
        # 讓主畫面即時看到變更，並選到當前編輯的技能
        self._refresh_and_select_in_main()


    def closeEvent(self, event):
        try:
            self._refresh_and_select_in_main()
        except Exception as e:
            print(f"[CSVEditor.closeEvent] 刷新/選取失敗：{e}")

        # 重新計算
        try:
            app = getattr(self, "app_instance", None)
            if app:
                setattr(app, "_last_calc_state", None)
                if hasattr(app, "trigger_total_effect_update"):
                    app.trigger_total_effect_update()
                elif hasattr(app, "replace_custom_calc_content"):
                    app.replace_custom_calc_content()
        except Exception as e:
            print(f"[CSVEditor.closeEvent] 重新計算失敗：{e}")

        super().closeEvent(event)


    def _refresh_and_select_in_main(self):
        """重建主畫面 skill_box，並用目前編輯列的 ID 精準選取。"""
        try:
            # 取出編輯器目前指到的那筆資料 ID
            idx_in_editor = self.name_combo.currentIndex()
            row_id = None
            if 0 <= idx_in_editor < len(self.filtered_rows):
                id_index = self.headers.index("ID")
                row = self.filtered_rows[idx_in_editor]
                if id_index < len(row):
                    row_id = row[id_index]

            app = getattr(self, "app_instance", None)
            if not app or not hasattr(app, "skill_box"):
                print("[CSVEditor] 找不到 app_instance 或 skill_box")
                return

            # 清除主畫面舊的關鍵字，避免被過濾掉
            if hasattr(app, "skill_filter_input"):
                app.skill_filter_input.blockSignals(True)
                app.skill_filter_input.clear()
                app.skill_filter_input.blockSignals(False)

            # 重建技能清單（需先把主畫面 filter_skills 掛到 self，前面你已做）
            if hasattr(app, "filter_skills"):
                app.filter_skills()

            # 用 ID（userData）精準選取；型別不一致時會嘗試轉型
            if row_id is not None:
                skill_box = app.skill_box
                idx = skill_box.findData(row_id)

                if idx == -1:
                    # 嘗試轉型再找
                    try_ids = []
                    try:
                        try_ids.append(int(row_id))
                    except:
                        pass
                    try_ids.append(str(row_id))
                    for cand in try_ids:
                        idx = skill_box.findData(cand)
                        if idx != -1:
                            break

                if idx != -1:
                    skill_box.setCurrentIndex(idx)
                else:
                    # 退而求其次，用名稱比對
                    name_txt = self.name_combo.currentText().strip()
                    name_idx = skill_box.findText(name_txt)
                    if name_idx != -1:
                        skill_box.setCurrentIndex(name_idx)
                    else:
                        print(f"[CSVEditor] skill_box 找不到 ID={row_id} 或名稱='{name_txt}'")

        except Exception as e:
            print(f"[CSVEditor] _refresh_and_select_in_main 失敗：{e}")



def open_skill_editor(app_instance=None):
    global skill_editor  

    if skill_editor is None or not skill_editor.isVisible():
        skill_editor = CSVEditor(r"data\skillneme.csv", parent=app_instance)
        skill_editor.app_instance = app_instance

        if app_instance:
            parent_pos = app_instance.pos()
            skill_editor.move(parent_pos.x() + 280,
                              parent_pos.y() + 75)

        skill_editor.show()
    else:
        skill_editor.raise_()
        skill_editor.activateWindow()

    # === 設定編輯器的 name_combo 下拉式 ===
    if app_instance and hasattr(app_instance, "skill_box"):
        try:
            skill_name = app_instance.skill_box.currentText().strip()
            if skill_name:
                idx = skill_editor.name_combo.findText(skill_name)
                if idx != -1:
                    skill_editor.name_combo.setCurrentIndex(idx)
                else:
                    print(f"[open_skill_editor] 編輯器內找不到技能：{skill_name}")
        except Exception as e:
            print(f"[open_skill_editor] 設定編輯器下拉式失敗：{e}")



class FileSelectionDialog(QDialog):#刪除清單
    """
    彈出多選檔案清單：
    files: [(檔名, 預設是否勾選)]
    base_path: 檔案所在資料夾
    """
    def __init__(self, files, base_path, parent=None, program_update_info=None):
        super().__init__(parent)
        self.program_update_info = program_update_info or {}
        self.has_program_update = bool(self.program_update_info.get("available"))

        self.setWindowTitle(tr("window.delete_files"))
        self.resize(500, 500)

        self.base_path = base_path
        self.checkboxes = []
        self.update_program_checkbox = None

        layout = QVBoxLayout(self)

        desc_lines = [tr("message.update_file_selection_tip")]
        if self.has_program_update:
            local_ver = self.program_update_info.get("local_ver", tr("label.current_version"))
            remote_ver = self.program_update_info.get("remote_ver", tr("label.latest_version"))
            desc_lines.append(tr("message.program_update_available", local_ver=local_ver, remote_ver=remote_ver))
        elif not files:
            desc_lines.append(tr("message.no_data_files_to_delete"))

        desc_label = QLabel("\n".join(desc_lines))
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        if self.has_program_update:
            local_ver = self.program_update_info.get("local_ver", tr("label.current_version"))
            remote_ver = self.program_update_info.get("remote_ver", tr("label.latest_version"))
            self.update_program_checkbox = QCheckBox(
                tr("checkbox.sync_program_update", local_ver=local_ver, remote_ver=remote_ver)
            )
            self.update_program_checkbox.setChecked(True)
            layout.addWidget(self.update_program_checkbox)

            release_url = self.program_update_info.get("release_url")
            if release_url:
                link = QLabel(tr("label.release_link_html", release_url=release_url))
                link.setOpenExternalLinks(True)
                layout.addWidget(link)

        # === scroll area ===
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        vbox = QVBoxLayout(content)

        for filename, default_checked in files:
            full_path = os.path.join(base_path, filename)
            if os.path.exists(full_path):
                mtime = datetime.fromtimestamp(os.path.getmtime(full_path))
                date_str = mtime.strftime("%Y-%m-%d %H:%M")
            else:
                date_str = tr("label.not_exists")

            cb = QCheckBox(f"{filename}    ({date_str})")
            cb.setChecked(default_checked)
            vbox.addWidget(cb)
            self.checkboxes.append((filename, cb))

        content.setLayout(vbox)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        # === bottom buttons ===
        btn_box = QHBoxLayout()
        if self.has_program_update and not files:
            ok_text = tr("button.update_program")
        elif self.has_program_update:
            ok_text = tr("button.delete_and_update")
        else:
            ok_text = tr("button.delete")

        ok_btn = QPushButton(ok_text)
        cancel_btn = QPushButton(tr("button.cancel"))

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

        btn_box.addWidget(ok_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

    def get_selected_files(self):
        """回傳使用者勾選的檔案名稱 list"""
        return [
            filename
            for filename, cb in self.checkboxes
            if cb.isChecked()
        ]

    def want_program_update(self):
        return bool(self.update_program_checkbox and self.update_program_checkbox.isChecked())





# Stage 3 Desktop -> Core Lua parser wrapper
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
):
    if context is None:
        context = build_desktop_calculation_context()

    return core_parse_lua_effects_with_variables(
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
        context=context,
        dependencies=build_desktop_core_dependencies(),
    )


def convert_description_to_html(description_lines):#視覺化說明欄
    html_lines = []
    color_stack = []

    for line in description_lines:
        result = ""
        i = 0
        while i < len(line):
            if line[i] == "^" and i + 6 < len(line):
                color_code = line[i+1:i+7]
                if re.fullmatch(r"[0-9a-fA-F]{6}", color_code):
                    result += f'<span style="color:#{color_code}">'
                    color_stack.append("</span>")
                    i += 7
                    continue
            result += line[i]
            i += 1

        # 關閉所有尚未關閉的 <span>
        while color_stack:
            result += color_stack.pop()
        html_lines.append(result)

    return "<br>".join(html_lines)

def decompile_lub(lub_path, output_path):
    """使用 luadec.exe 反編譯 LUB → LUA"""
    if not os.path.exists(lub_path):
        QMessageBox.critical(None, tr("message.title.error"), tr("message.lub_file_not_found", path=lub_path))
        return False

    try:
        with open(output_path, "w", encoding="utf-8") as out_file:
            subprocess.run(
                [r"APP\luadec.exe", lub_path],
                stdout=out_file,
                stderr=subprocess.PIPE,
                check=True
            )
        print(f"✨ LUB 已反編譯 -> {output_path}")
        return True

    except subprocess.CalledProcessError as e:
        QMessageBox.critical(None, tr("message.title.decompile_failed"), e.stderr.decode("utf-8", errors="ignore"))
        return False

    except FileNotFoundError:
        QMessageBox.critical(None, tr("message.title.error"), tr("message.luadec_not_found"))
        return False


def parse_lub_file(filename, existing_items=None, duplicate_mode="skip"):  # Desktop 相容 wrapper
    try:
        return core_parse_lub_file(
            filename,
            existing_items=existing_items,
            duplicate_mode=duplicate_mode,
        )
    except FileNotFoundError:
        # UI 顯示責任留在 Desktop；ro_core.py 不依賴 PySide6。
        QMessageBox.critical(
            None,
            tr("message.title.error"),
            tr("message.file_not_found", filename=filename),
        )
        return existing_items if existing_items is not None else {}


def load_skill_delay_lua(filename) -> str:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print("讀取 skilldelaylist.lua 失敗:", e)
        return ""


import json, os
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton

class PreferencesDialog(QDialog):
    def __init__(
        self,
        current_mode: str,
        current_api_key: str = "",
        current_ui_scale: float = DEFAULT_UI_SCALE_FACTOR,
        current_load_kro_data: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("window.preferences"))
        self.resize(360, 300)

        layout = QVBoxLayout(self)

        # 模式選單
        hl = QHBoxLayout()
        hl.addWidget(QLabel(tr("label.update_mode")))
        self.mode_combo = QComboBox()
        options = [
            ("線上來源", "online_only"),
            ("本機來源", "local_only"),
        ]
        for text, val in options:
            self.mode_combo.addItem(text, userData=val)

        idx = self.mode_combo.findData(current_mode or "online_only")
        self.mode_combo.setCurrentIndex(idx if idx >= 0 else 0)

        hl.addWidget(self.mode_combo)
        layout.addLayout(hl)
        
        # 說明
        tip = QLabel(tr("label.update_mode_tip"))
        tip.setWordWrap(True)
        layout.addWidget(tip)
        # KRO 裝備資料為選用來源；未勾選時不下載、不檢查也不載入兩個 KRO 檔案。
        self.load_kro_cb = QCheckBox(
            tr("checkbox.load_kro_equipment_data", "載入 KRO 裝備資料")
        )
        self.load_kro_cb.setChecked(bool(current_load_kro_data))
        self.load_kro_cb.setToolTip(
            tr(
                "tooltip.load_kro_equipment_data",
                "啟用後會下載並載入 KRO_itemInfo_true.lua 與 KRO_equipmentproperties.lua。",
            )
        )
        layout.addWidget(self.load_kro_cb)

        # 介面縮放倍率（Qt 需在 QApplication 建立前套用，因此下次啟動生效）
        scale_row = QHBoxLayout()
        scale_row.addWidget(QLabel(tr("label.ui_scale", "介面縮放")))
        self.ui_scale_combo = QComboBox()
        scale_options = [
            ("100%", 1.0),
            ("125%", 1.25),
            ("150%", 1.5),
            ("175%", 1.75),
            ("200%", 2.0),
        ]
        for text, value in scale_options:
            self.ui_scale_combo.addItem(text, userData=value)

        current_ui_scale = normalize_ui_scale_factor(current_ui_scale)
        scale_idx = self.ui_scale_combo.findData(current_ui_scale)
        if scale_idx < 0:
            custom_text = f"{current_ui_scale * 100:g}%"
            self.ui_scale_combo.addItem(custom_text, userData=current_ui_scale)
            scale_idx = self.ui_scale_combo.count() - 1
        self.ui_scale_combo.setCurrentIndex(scale_idx)
        scale_row.addWidget(self.ui_scale_combo)
        layout.addLayout(scale_row)

        scale_tip = QLabel(
            tr("label.ui_scale_tip", "變更縮放倍率後，重新啟動程式才會生效。")
        )
        scale_tip.setWordWrap(True)
        layout.addWidget(scale_tip)

        # ✅ 新增：API Key
        ak = QHBoxLayout()
        ak.addWidget(QLabel(tr("label.api_key")))
        self.api_edit = QLineEdit()
        self.api_edit.setPlaceholderText(tr("placeholder.api_key"))
        self.api_edit.setText(current_api_key or "")
        self.api_edit.setEchoMode(QLineEdit.EchoMode.Password)  # 預設隱藏
        ak.addWidget(self.api_edit)
        layout.addLayout(ak)

        self.show_key_cb = QCheckBox(tr("checkbox.show"))
        self.show_key_cb.toggled.connect(self._toggle_api_visible)
        layout.addWidget(self.show_key_cb)
        # 說明
        keytip = QLabel(tr("label.api_key_tip"))
        keytip.setWordWrap(True)
        layout.addWidget(keytip)


        # 按鈕
        btns = QHBoxLayout()
        ok_btn = QPushButton(tr("button.ok"))
        cancel_btn = QPushButton(tr("button.cancel"))
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(ok_btn)
        btns.addWidget(cancel_btn)
        layout.addLayout(btns)

    def _toggle_api_visible(self, checked: bool):
        self.api_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def selected_mode(self) -> str:
        return self.mode_combo.currentData()

    def api_key(self) -> str:
        return self.api_edit.text().strip()

    def selected_ui_scale(self) -> float:
        return normalize_ui_scale_factor(self.ui_scale_combo.currentData())

    def should_load_kro_data(self) -> bool:
        return self.load_kro_cb.isChecked()



class InternalDataInspectorDialog(QDialog):
    """只讀式內部資料查詢視窗。

    目的：讓使用者在 UI 上查看目前載入的 mapping、DataRegistry、技能/裝備狀態與主視窗 snapshot。
    注意：此視窗刻意不提供 eval / exec，也不允許修改資料，避免把 Debug 工具變成任意程式執行入口。
    """

    def __init__(self, data_provider, parent=None):
        super().__init__(parent)
        self.data_provider = data_provider
        self.setWindowTitle(tr("window.internal_data_inspector", "內部資料查詢"))
        self.resize(900, 650)

        layout = QVBoxLayout(self)

        control_row = QHBoxLayout()
        self.source_combo = QComboBox()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            tr("placeholder.internal_data_search", "輸入關鍵字或 key，例如 STR、技能名稱、job id...")
        )

        self.refresh_button = QPushButton(tr("button.refresh", "重新整理"))
        self.clear_button = QPushButton(tr("button.clear", "清空"))

        control_row.addWidget(QLabel(tr("label.data_source", "資料來源")))
        control_row.addWidget(self.source_combo, 1)
        control_row.addWidget(self.search_input, 2)
        control_row.addWidget(self.refresh_button)
        control_row.addWidget(self.clear_button)
        layout.addLayout(control_row)

        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.result_text, 1)

        self.status_label = QLabel("")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        self.refresh_button.clicked.connect(self.refresh_sources)
        self.clear_button.clicked.connect(self.search_input.clear)
        self.source_combo.currentIndexChanged.connect(self.render_current_source)
        self.search_input.textChanged.connect(self.render_current_source)

        self.refresh_sources()

    def refresh_sources(self):
        current = self.source_combo.currentText()
        try:
            self.sources = self.data_provider() or {}
        except Exception as e:
            self.sources = {tr("label.error", "錯誤"): {"error": str(e)}}

        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        self.source_combo.addItems(list(self.sources.keys()))
        if current:
            idx = self.source_combo.findText(current)
            if idx >= 0:
                self.source_combo.setCurrentIndex(idx)
        self.source_combo.blockSignals(False)
        self.render_current_source()

    def render_current_source(self):
        source_name = self.source_combo.currentText()
        data = self.sources.get(source_name, {})
        query = self.search_input.text().strip().lower()

        filtered = self._filter_data(data, query) if query else data
        safe_data = self._to_json_safe(filtered)

        try:
            text = json.dumps(safe_data, ensure_ascii=False, indent=2)
        except Exception:
            text = str(safe_data)

        self.result_text.setPlainText(text)
        self.status_label.setText(
            tr(
                "label.internal_data_status",
                "來源：{source}｜查詢：{query}｜結果長度：{length}",
                source=source_name or "-",
                query=query or tr("label.none", "無"),
                length=len(text),
            )
        )

    def _filter_data(self, data, query):
        """保留 key 或 value 文字中包含 query 的節點；巢狀 dict/list 會遞迴搜尋。"""
        if not query:
            return data

        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                key_match = query in str(k).lower()
                value_match = query in str(v).lower()
                child = self._filter_data(v, query) if isinstance(v, (dict, list, tuple, set)) else None

                if key_match or value_match:
                    result[k] = v
                elif child not in ({}, [], (), set(), None):
                    result[k] = child
            return result

        if isinstance(data, (list, tuple, set)):
            result = []
            for item in data:
                item_match = query in str(item).lower()
                child = self._filter_data(item, query) if isinstance(item, (dict, list, tuple, set)) else None

                if item_match:
                    result.append(item)
                elif child not in ({}, [], (), set(), None):
                    result.append(child)
            return result

        return data if query in str(data).lower() else None

    def _to_json_safe(self, obj, depth=0, max_depth=8):
        """把 Qt widget / DataFrame / set 等物件轉成可讀 JSON，並限制深度避免 UI 卡住。"""
        if depth > max_depth:
            return "..."

        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj

        if isinstance(obj, dict):
            return {
                str(k): self._to_json_safe(v, depth + 1, max_depth)
                for k, v in obj.items()
            }

        if isinstance(obj, (list, tuple)):
            return [self._to_json_safe(v, depth + 1, max_depth) for v in obj]

        if isinstance(obj, set):
            return [self._to_json_safe(v, depth + 1, max_depth) for v in sorted(obj, key=str)]

        if isinstance(obj, pd.DataFrame):
            return {
                "type": "DataFrame",
                "shape": list(obj.shape),
                "columns": [str(c) for c in obj.columns],
                "preview": obj.head(100).to_dict(orient="records"),
            }

        if isinstance(obj, pd.Series):
            return obj.head(100).to_dict()

        if hasattr(obj, "text") and callable(obj.text):
            try:
                return {"type": obj.__class__.__name__, "text": obj.text()}
            except Exception:
                pass

        if hasattr(obj, "currentText") and callable(obj.currentText):
            try:
                return {
                    "type": obj.__class__.__name__,
                    "currentText": obj.currentText(),
                    "currentData": obj.currentData() if hasattr(obj, "currentData") else None,
                }
            except Exception:
                pass

        return str(obj)


class ItemSearchApp(QWidget):

    def get_internal_data_snapshot(self):
        """收集目前 UI 與計算流程常用的只讀狀態，供 Debug 查詢視窗使用。"""
        snapshot = {
            "window": {
                "title": self.windowTitle(),
                "current_file": getattr(self, "current_file", None),
                "current_edit_part": getattr(self, "current_edit_part", None),
            },
            "input_fields": {},
            "selected_values": {},
            "equipment_effects": {
                "effect_dict_raw": getattr(self, "effect_dict_raw", {}),
                "base_equip_stats_raw": getattr(self, "base_equip_stats_raw", {}),
                "total_combined_raw": getattr(self, "total_combined_raw", []),
            },
            "skills": {
                "enabled_skill_levels": enabled_skill_levels,
                "Use_skill_levels": Use_skill_levels,
                "current_skill": self.skill_box.currentText() if hasattr(self, "skill_box") else None,
                "current_skill_id": self.skill_box.currentData() if hasattr(self, "skill_box") else None,
            },
            "weapon": {
                "global_weapon_level_map": global_weapon_level_map,
                "global_armor_weapon_map": global_armor_weapon_map,
                "global_armor_level_map": global_armor_level_map,
                "global_weapon_type_map": global_weapon_type_map,
                "global_weapon_atk_map": global_weapon_atk_map,
                "global_weapon_matk_map": global_weapon_matk_map,
                "slot_item_id_map": slot_item_id_map,
            },
        }

        for key, widget in getattr(self, "input_fields", {}).items():
            try:
                if hasattr(widget, "text") and callable(widget.text):
                    snapshot["input_fields"][key] = widget.text()
                elif hasattr(widget, "currentData") and callable(widget.currentData):
                    snapshot["input_fields"][key] = {
                        "currentText": widget.currentText() if hasattr(widget, "currentText") else None,
                        "currentData": widget.currentData(),
                    }
                else:
                    snapshot["input_fields"][key] = str(widget)
            except Exception as e:
                snapshot["input_fields"][key] = f"<讀取失敗: {e}>"

        # 常見下拉/輸入元件：有存在才收集，避免不同版本 UI 造成 AttributeError。
        for attr in [
            "name_field", "id_field", "skill_box", "function_selector",
            "job_combo", "weapon_combo", "monster_name_field"
        ]:
            if not hasattr(self, attr):
                continue
            widget = getattr(self, attr)
            try:
                if hasattr(widget, "currentText"):
                    snapshot["selected_values"][attr] = {
                        "currentText": widget.currentText(),
                        "currentData": widget.currentData() if hasattr(widget, "currentData") else None,
                    }
                elif hasattr(widget, "text"):
                    snapshot["selected_values"][attr] = widget.text()
                else:
                    snapshot["selected_values"][attr] = str(widget)
            except Exception as e:
                snapshot["selected_values"][attr] = f"<讀取失敗: {e}>"

        return snapshot

    def build_internal_data_sources(self):
        """Debug Inspector 的資料白名單。不要在這裡加入可執行函式入口。"""
        return {
            tr("debug_source.snapshot", "目前狀態 Snapshot"): self.get_internal_data_snapshot(),
            tr("debug_source.parsed_items", "物品列表"): self.parsed_items,
            tr("debug_source.equipment_data", "裝備效果"): self.equipment_data,
            tr("debug_source.data_registry", "料理 輔助技能"): DataRegistry.loaded_data,
            tr("debug_source.skills", "技能資料 skills"): DataRegistry.loaded_data.get("skills", {}),
            tr("debug_source.jobs", "職業資料 jobs"): DataRegistry.loaded_data.get("jobs", {}),
            tr("debug_source.job_hpsp", "職業 HP/SP jobHPSP"): DataRegistry.loaded_data.get("jobHPSP", {}),
            tr("debug_source.aspd", "攻速資料 ASPD"): DataRegistry.loaded_data.get("ASPD", {}),
            tr("debug_source.skill_map", "skill_map"): skill_map,
            tr("debug_source.skill_map_all", "skill_map_all"): skill_map_all,
            tr("debug_source.skill_df", "skill_df"): skill_df,
            tr("debug_source.function_defs", "公式 function_defs"): function_defs,
            tr("debug_source.effect_map", "效果代碼 effect_map"): effect_map,
            tr("debug_source.element_map", "屬性 element_map"): element_map,
            tr("debug_source.size_map", "體型 size_map"): size_map,
            tr("debug_source.race_map", "種族 race_map"): race_map,
            tr("debug_source.weapon_type_map", "武器類型 weapon_type_map"): weapon_type_map,
            tr("debug_source.damage_tables", "屬性倍率 damage_tables"): damage_tables,
            tr("debug_source.refine_parts", "部位 refine_parts"): refine_parts,
            tr("debug_source.equip_sitetype", "裝備位置 equip_sitetype"): equip_sitetype,
            tr("debug_source.equipid_mapping", "ROCalculator 裝備轉換 equipid_mapping"): equipid_mapping,
            tr("debug_source.status_mapping", "ROCalculator 狀態轉換 status_mapping"): status_mapping,
            tr("debug_source.weapon_mapping", "ROCalculator 武器轉換 weapon_mapping"): weapon_mapping,
        }

    def open_internal_data_inspector(self):
        """開啟只讀式內部資料查詢視窗。"""
        if not hasattr(self, "_internal_data_inspector") or self._internal_data_inspector is None:
            self._internal_data_inspector = InternalDataInspectorDialog(
                self.build_internal_data_sources,
                self,
            )

        self._internal_data_inspector.refresh_sources()
        self._internal_data_inspector.show()
        self._internal_data_inspector.raise_()
        self._internal_data_inspector.activateWindow()

    def _parse_buff_ids(self, raw_buff) -> set[str]:
        """把 buff 轉成 set[str]，支援 '244'、'10,12,244'、['1667','1668']"""
        if raw_buff is None:
            return set()

        if isinstance(raw_buff, (int, float)):
            return {str(int(raw_buff))}

        if isinstance(raw_buff, (list, tuple, set)):
            result = set()
            for x in raw_buff:
                if x is None:
                    continue
                s = str(x).strip()
                if s:
                    result.add(s)
            return result

        s = str(raw_buff).strip()
        if not s:
            return set()

        return {part.strip() for part in s.split(",") if part.strip()}

    def _build_part_nav_popup(self, visible_types):
        self.part_nav_popup = QFrame(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.part_nav_popup.hide()
        self.part_nav_popup.setObjectName("partNavPopup")
        self.part_nav_popup.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.part_nav_popup.setStyleSheet("""
            QFrame#partNavPopup {
                background: #2b2b2b;
                border: 1px solid #666;
                border-radius: 8px;
            }
            QFrame#partNavPopup QPushButton {
                padding: 6px 10px;
                text-align: center;
                min-width: 90px;
            }
        """)

        outer = QVBoxLayout(self.part_nav_popup)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        self.part_nav_buttons = []

        # 這裡排快速導航，依照遊戲順序
        custom_rows = [
            ["頭上", "頭中", "服飾頭上", "服飾頭中"],
            ["頭下", "鎧甲", "服飾頭下", "影子鎧甲"],
            ["右手(武器)", "左手(盾牌)", "影子手套", "影子盾牌"],
            [ "披肩", "鞋子", "服飾斗篷", "影子鞋子"],
            ["飾品右", "飾品左", "影子耳環右", "影子墬子左"],
            ["符文石碑", "寵物蛋", "技能", "投擲物品"],
        ]

        for row_parts in custom_rows:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(6)
            row_layout.addStretch()

            for part_name in row_parts:
                if part_name not in refine_parts:
                    continue
                if refine_parts[part_name]["type"] not in visible_types:
                    continue

                btn = QPushButton(part_name)
                btn.setCursor(Qt.PointingHandCursor)
                btn.clicked.connect(lambda _, p=part_name: self.scroll_to_equip_part(p))
                btn.installEventFilter(self)

                self.part_nav_buttons.append(btn)
                row_layout.addWidget(btn)

            row_layout.addStretch()
            outer.addLayout(row_layout)

            used_parts = {p for row in custom_rows for p in row}

            remaining_parts = [
                part_name
                for part_name, info in refine_parts.items()
                if info["type"] in visible_types and part_name not in used_parts
            ]

            if remaining_parts:
                custom_rows.append(remaining_parts)

        self.part_nav_popup.installEventFilter(self)

    def _show_part_nav_popup(self):
        if not getattr(self, "part_nav_button", None):
            return
        if not getattr(self, "part_nav_popup", None):
            return

        self.part_nav_hide_timer.stop()
        self.part_nav_popup.adjustSize()

        pos = self.part_nav_button.mapToGlobal(
            QPoint(0, self.part_nav_button.height() + 2)
        )

        self.part_nav_popup.move(pos)
        self.part_nav_popup.show()
        self.part_nav_popup.raise_()

    def _hide_part_nav_popup(self):
        if getattr(self, "part_nav_button", None) and self.part_nav_button.underMouse():
            return

        if getattr(self, "part_nav_popup", None):
            if self.part_nav_popup.underMouse():
                return

            for btn in getattr(self, "part_nav_buttons", []):
                if btn.underMouse():
                    return

            self.part_nav_popup.hide()

    def scroll_to_equip_part(self, part_name):
        part_ui = self.refine_inputs_ui.get(part_name)
        if not part_ui:
            return

        target = part_ui["container"]
        content_widget = self.equip_scroll.widget()

        y = target.mapTo(content_widget, QPoint(0, 0)).y()

        # 稍微留一點上邊距，避免貼太死
        target_y = max(0, y - 8)

        self._animate_scroll_to(target_y)
        self._flash_part_target(target)

        self.part_nav_popup.hide()

    def eventFilter(self, obj, event):
        watched = {getattr(self, "part_nav_button", None), getattr(self, "part_nav_popup", None)}
        for btn in getattr(self, "part_nav_buttons", []):
            watched.add(btn)

        if obj in watched:
            if event.type() == QEvent.Enter:
                self.part_nav_hide_timer.stop()
                if obj == self.part_nav_button:
                    self._show_part_nav_popup()

            elif event.type() == QEvent.Leave:
                self.part_nav_hide_timer.start(150)

        return super().eventFilter(obj, event)


    def _animate_scroll_to(self, target_value):
        scroll_bar = self.equip_scroll.verticalScrollBar()

        start_value = scroll_bar.value()
        end_value = max(scroll_bar.minimum(), min(target_value, scroll_bar.maximum()))
        distance = abs(end_value - start_value)

        if self.part_scroll_anim:
            self.part_scroll_anim.stop()

        self.part_scroll_anim = QPropertyAnimation(scroll_bar, b"value", self)
        self.part_scroll_anim.setStartValue(start_value)
        self.part_scroll_anim.setEndValue(end_value)

        duration = max(180, min(520, int(distance * 0.6)))
        self.part_scroll_anim.setDuration(duration)
        self.part_scroll_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.part_scroll_anim.start()


    def _flash_part_target(self, widget):
        old_style = widget.property("_old_style")
        if old_style is None:
            old_style = widget.styleSheet()
            widget.setProperty("_old_style", old_style)

        token = time.time_ns()
        widget.setProperty("_flash_token", token)

        flash_style = (old_style or "") + """
        background-color: rgba(100, 180, 255, 50);
        border: 2px solid #5aa9ff;
        border-radius: 8px;
        """

        widget.setStyleSheet(flash_style)

        def restore():
            try:
                if widget.property("_flash_token") == token:
                    widget.setStyleSheet(widget.property("_old_style") or "")
            except RuntimeError:
                pass

        QTimer.singleShot(1000, restore)


    def apply_buff_to_skill_checkboxes(self, raw_buff):
        target_buff_ids = self._parse_buff_ids(raw_buff)

        matched_names = []
        used_exclusive_groups = set()

        for name, data in all_skill_entries.items():
            skill_buff_ids = self._parse_buff_ids(data.get("buff"))

            # ✅ 只要有任一個 buff id 重疊，就算符合
            if not (skill_buff_ids & target_buff_ids):
                continue

            # exclusive 處理
            raw_exclusive = data.get("exclusive")
            groups = []
            if raw_exclusive:
                if isinstance(raw_exclusive, str):
                    groups = [g.strip() for g in raw_exclusive.split(",") if g.strip()]
                else:
                    groups = [str(g).strip() for g in raw_exclusive if str(g).strip()]

            if any(g in used_exclusive_groups for g in groups):
                continue

            matched_names.append(name)
            used_exclusive_groups.update(groups)

        matched_set = set(matched_names)

        for name, checkbox in self.skill_checkboxes.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(name in matched_set)
            checkbox.blockSignals(False)

        # 批次勾選時 signals 被暫停，需手動刷新分頁上的已勾選數量。
        self.update_skill_food_tab_checked_count()

# 附魔選擇後自動轉移至主視窗的相關欄位。 內容參考 https://github.com/z2911902/ROItemSearchApp/pull/3 

    def _load_enchant_tool_data(self):
        """載入並快取附魔工具資料，供按鈕顯示與工具視窗共用。"""
        if (
            self._enchant_data_cache is not None
            and self._enchant_itemdb_cache is not None
            and self._enchant_target_map_cache is not None
        ):
            return (
                self._enchant_data_cache,
                self._enchant_itemdb_cache,
                self._enchant_target_map_cache,
            )

        data_dir = os.path.join(get_app_base_dir(), "data")
        itemdb_path = os.path.join(data_dir, "ItemDBNameTbl.lua")
        enchant_path = os.path.join(data_dir, "EnchantList.lua")

        itemdb = enchant.parse_itemdb_name_tbl(itemdb_path)
        enchant_data = enchant.parse_enchant_list(enchant_path)
        target_map = enchant.build_enchant_target_map(
            enchant_data,
            self.parsed_items,
            itemdb,
            require_content=True,
        )

        self._enchant_itemdb_cache = itemdb
        self._enchant_data_cache = enchant_data
        self._enchant_target_map_cache = target_map
        return enchant_data, itemdb, target_map

    def _get_equipment_enchant_slots(self, equipment_name):
        """取得指定裝備實際可附魔的洞位 ID。"""
        equipment_name = str(equipment_name or "").strip()
        if not equipment_name:
            return set()

        try:
            enchant_data, _, target_map = self._load_enchant_tool_data()
        except Exception as exc:
            print(f"⚠️ 載入附魔資料失敗：{exc}")
            return set()

        table_id = target_map.get(equipment_name)
        if table_id is None:
            return set()

        return enchant.get_enchant_slot_ids(enchant_data.get(table_id, {}))

    def _equipment_has_enchant_content(self, equipment_name):
        return bool(self._get_equipment_enchant_slots(equipment_name))

    def _update_enchant_button_for_part(self, part_name, equipment_name=None):
        """只在該裝備實際可附魔的洞位旁顯示附魔按鈕。"""
        ui = getattr(self, "refine_inputs_ui", {}).get(part_name)
        if not ui:
            return

        equip_input = ui.get("equip")
        buttons = ui.get("enchant_buttons", [])
        if equip_input is None:
            return

        if equipment_name is None:
            equipment_name = equip_input.text()

        enchant_slots = self._get_equipment_enchant_slots(equipment_name)
        for slot_id, button in enumerate(buttons):
            visible = slot_id in enchant_slots
            button.setVisible(visible)
            button.setEnabled(visible)

    def _activate_equipment_edit_for_enchant(self, part_name):
        """由裝備列的附魔按鈕鎖定套用目標，效果等同點選該裝備欄。"""
        ui = getattr(self, "refine_inputs_ui", {}).get(part_name)
        if not ui:
            return False

        equipment_name = ui["equip"].text().strip()
        if not self._equipment_has_enchant_content(equipment_name):
            self._update_enchant_button_for_part(part_name, equipment_name)
            return False

        self.clear_current_edit()
        self.current_edit_part = f"{part_name} - 裝備"
        self.current_edit_label.setText(
            tr("label.current_part_detail", part=part_name, label="裝備")
        )
        self.unsync_button.setVisible(True)
        self.unsync_button2.setVisible(True)
        self.apply_to_note_button.setVisible(True)
        self.clear_field_button2.setVisible(True)
        self.apply_equip_button.setVisible(True)
        self.clear_field_button.setVisible(True)
        self.set_edit_lock(part_name, "裝備")
        ui["equip"].setStyleSheet("background-color: #ff0000;")
        self._set_enchant_tool_target(part_name, "裝備", equipment_name)
        return True

    def open_part_enchant_tool(self, part_name, slot_id=None):
        """從指定裝備洞位開啟附魔工具，並切到對應洞位分頁。"""
        if not self._activate_equipment_edit_for_enchant(part_name):
            return

        equipment_name = self.refine_inputs_ui[part_name]["equip"].text().strip()
        self.open_enchant_tool(
            target_part=part_name,
            initial_equipment=equipment_name,
            initial_slot_id=slot_id,
        )

    def _get_part_enchant_values(self, part_name):
        """取得主畫面指定部位四個附魔／卡片欄位目前文字。"""
        ui = getattr(self, "refine_inputs_ui", {}).get(part_name)
        if not ui:
            return ["", "", "", ""]
        values = [str(card.text() or "").strip() for card in ui.get("cards", [])[:4]]
        return values + [""] * (4 - len(values))

    def _sync_open_enchant_tool_context(self, part_name):
        """主畫面裝備或附魔欄變更時，同步已開啟附魔工具的隨機升階來源。"""
        window = getattr(self, "enchant_window", None)
        if window is None:
            return

        try:
            if getattr(window, "target_part_name", "") != part_name:
                return
            ui = getattr(self, "refine_inputs_ui", {}).get(part_name)
            if not ui:
                return
            window.set_target_context(
                part_name,
                ui["equip"].text().strip(),
                self._get_part_enchant_values(part_name),
            )
        except RuntimeError:
            self.enchant_window = None

    def _set_enchant_tool_target(self, part_name="", field_type="", equipment_name=""):
        """把主畫面目前紅底欄位同步到已開啟的附魔工具。"""
        window = getattr(self, "enchant_window", None)
        if window is None:
            return

        try:
            if field_type == "裝備" and part_name:
                window.set_target_context(
                    part_name,
                    equipment_name,
                    self._get_part_enchant_values(part_name),
                )
                if equipment_name:
                    window.select_item_by_name(equipment_name)
            else:
                window.set_target_context("", "", ["", "", "", ""])
        except RuntimeError:
            # Qt 物件已被關閉／刪除時不影響主程式。
            self.enchant_window = None

    def apply_enchant_from_tool(self, equipment_name, slot_id, enchant_name):
        """將附魔工具選到的附魔寫入紅底裝備之對應洞位。"""
        window = getattr(self, "enchant_window", None)

        def report(message, success=False):
            if window is not None:
                try:
                    window.set_apply_status(message, success)
                except RuntimeError:
                    pass

        current_edit = getattr(self, "current_edit_part", None)
        if not current_edit:
            report("請先在主畫面點選要套用的裝備名稱欄，使其顯示紅底。")
            return

        try:
            part_name, field_type = current_edit.rsplit(" - ", 1)
        except ValueError:
            report(f"無法解析目前編輯欄位：{current_edit}")
            return

        if field_type != "裝備":
            report("目前紅底欄位不是裝備名稱欄；請改點該部位的裝備欄。")
            return

        ui = self.refine_inputs_ui.get(part_name)
        if not ui:
            report(f"找不到主畫面部位：{part_name}")
            return

        try:
            slot_id = int(slot_id)
        except (TypeError, ValueError):
            report(f"無法辨識附魔洞位：{slot_id}")
            return

        cards = ui.get("cards", [])
        if not 0 <= slot_id < len(cards):
            report(f"{part_name} 沒有可寫入的第{slot_id + 1}洞。")
            return

        equipment_name = str(equipment_name or "").strip()
        enchant_name = str(enchant_name or "").strip()
        if not equipment_name or not enchant_name:
            report("裝備名稱或附魔名稱為空，無法套用。")
            return

        self.clear_global_state()
        self._last_calc_state = None

        # 選附魔清單中的裝備時，也同步更新主畫面的裝備名稱。
        ui["equip"].setText(equipment_name)
        cards[slot_id].setText(enchant_name)

        # 保留紅底目標，讓使用者可連續設定其他洞位。
        ui["equip"].setStyleSheet("background-color: #ff0000;")
        self.current_edit_label.setText(
            tr("label.current_part_detail", part=part_name, label="裝備")
        )

        self.trigger_total_effect_update()
        self._set_enchant_tool_target(part_name, "裝備", equipment_name)
        report(f"已加入「{part_name}」第{slot_id + 1}洞：{enchant_name}", True)

    def open_enchant_tool(self, checked=False, target_part=None, initial_equipment=None, initial_slot_id=None):#附魔工具
        # QAction.triggered 會傳入 checked；只有明確字串才視為指定部位。
        if target_part is None:
            target_part = ""
        if initial_equipment is None:
            initial_equipment = ""

        if not target_part:
            current_edit = getattr(self, "current_edit_part", None)
            if current_edit:
                try:
                    part_name, field_type = current_edit.rsplit(" - ", 1)
                    if field_type == "裝備" and part_name in self.refine_inputs_ui:
                        target_part = part_name
                        initial_equipment = self.refine_inputs_ui[part_name]["equip"].text().strip()
                except ValueError:
                    pass

        # 已開啟時直接切換套用目標，不重複建立視窗。
        window = getattr(self, "enchant_window", None)
        if window is not None:
            try:
                window.set_target_context(
                    target_part,
                    initial_equipment,
                    self._get_part_enchant_values(target_part) if target_part else ["", "", "", ""],
                )
                if initial_equipment:
                    window.select_item_by_name(initial_equipment)
                if initial_slot_id is not None:
                    window.select_slot_by_id(initial_slot_id)
                window.show()
                window.raise_()
                window.activateWindow()
                return
            except RuntimeError:
                self.enchant_window = None

        enchant_data, itemdb, _ = self._load_enchant_tool_data()

        self.enchant_window = enchant.EnchantUI(
            enchant_data,
            self.parsed_items,
            itemdb,
            initial_equipment_name=initial_equipment,
            target_part_name=target_part,
            initial_slot_id=initial_slot_id,
            initial_slot_enchants=(
                self._get_part_enchant_values(target_part)
                if target_part else ["", "", "", ""]
            ),
        )
        self.enchant_window.enchantApplyRequested.connect(self.apply_enchant_from_tool)
        self.enchant_window.setWindowTitle(tr("window.enchant_tool"))
        self.enchant_window.resize(1300, 600)
        #self.enchant_window.move(300, 200)出現視窗可能會超出畫面外，預留移動。
        self.enchant_window.show()


    # ------------------------------------------------------------------
    # LapineUpgradeBox：以 TargetItems 的 ItemID 對應主程式裝備 ItemID
    # ------------------------------------------------------------------
    def _load_lapine_upgrade_tool_data(self):
        """載入並快取 lapineupgradebox.lub 與裝備名稱索引。"""
        if self._lapine_upgrade_data_cache is None or self._lapine_target_map_cache is None:
            lapine_path = lapine_upgrade.find_lapine_upgrade_file(get_app_base_dir())
            if not lapine_path:
                raise FileNotFoundError(
                    "找不到 lapineupgradebox.lub；請放在程式根目錄或 data 資料夾。"
                )

            lapine_data = lapine_upgrade.parse_lapine_upgrade_box(lapine_path)
            target_map = lapine_upgrade.build_target_item_map(lapine_data)
            self._lapine_upgrade_data_cache = lapine_data
            self._lapine_target_map_cache = target_map

        item_count = len(getattr(self, "parsed_items", {}) or {})
        if (
            self._lapine_item_name_index_cache is None
            or self._lapine_item_index_size != item_count
        ):
            self._lapine_item_name_index_cache = lapine_upgrade.build_item_name_index(
                self.parsed_items
            )
            self._lapine_item_index_size = item_count

        return (
            self._lapine_upgrade_data_cache,
            self._lapine_target_map_cache,
            self._lapine_item_name_index_cache,
        )

    def _get_equipment_lapine_context(self, equipment_name):
        """回傳 (裝備 ItemID, 可用 Lapine 附魔箱清單)。"""
        equipment_name = str(equipment_name or "").strip()
        if not equipment_name:
            return None, []

        try:
            _, target_map, name_index = self._load_lapine_upgrade_tool_data()
        except Exception as exc:
            print(f"⚠️ 載入 LapineUpgradeBox 資料失敗：{exc}")
            return None, []

        item_id = lapine_upgrade.resolve_item_id_by_display_name(
            equipment_name,
            self.parsed_items,
            name_index,
        )
        if item_id is None:
            return None, []

        return item_id, list(target_map.get(item_id, []))

    def _update_lapine_upgrade_button_for_part(self, part_name, equipment_name=None):
        """TargetItems 包含目前裝備時，在詞條 box 右側上方顯示 Lapine 附魔按鈕。"""
        ui = getattr(self, "refine_inputs_ui", {}).get(part_name)
        if not ui:
            return

        equip_input = ui.get("equip")
        button = ui.get("lapine_upgrade_button")
        note_ui = ui.get("note_ui")
        if equip_input is None or button is None:
            return

        if equipment_name is None:
            equipment_name = equip_input.text()

        _, entries = self._get_equipment_lapine_context(equipment_name)
        visible = bool(entries)

        button.setVisible(visible)
        button.setEnabled(visible)

        # 右側固定保留 40px 按鈕欄，因此紅色詞條 BOX 維持 255px。
        if note_ui is not None:
            note_ui.setFixedWidth(255)

    def _activate_equipment_edit_for_lapine(self, part_name):
        """由詞條列按鈕鎖定目前裝備，並準備開啟 Lapine 檢視器。"""
        ui = getattr(self, "refine_inputs_ui", {}).get(part_name)
        if not ui:
            return False

        equipment_name = ui["equip"].text().strip()
        _, entries = self._get_equipment_lapine_context(equipment_name)
        if not entries:
            self._update_lapine_upgrade_button_for_part(part_name, equipment_name)
            return False

        self.clear_current_edit()
        self.current_edit_part = f"{part_name} - 裝備"
        self.current_edit_label.setText(
            tr("label.current_part_detail", part=part_name, label="裝備")
        )
        self.unsync_button.setVisible(True)
        self.unsync_button2.setVisible(True)
        self.apply_to_note_button.setVisible(True)
        self.clear_field_button2.setVisible(True)
        self.apply_equip_button.setVisible(True)
        self.clear_field_button.setVisible(True)
        self.set_edit_lock(part_name, "裝備")
        ui["equip"].setStyleSheet("background-color: #ff0000;")
        self._set_lapine_upgrade_tool_target(part_name, "裝備", equipment_name)
        return True

    def _set_lapine_upgrade_tool_target(self, part_name="", field_type="", equipment_name=""):
        """同步主畫面目前紅底裝備到已開啟的 Lapine 工具。"""
        window = getattr(self, "lapine_upgrade_window", None)
        if window is None:
            return

        try:
            if field_type == "裝備" and part_name:
                item_id, _ = self._get_equipment_lapine_context(equipment_name)
                window.set_target_context(part_name, item_id, equipment_name)
            else:
                window.set_target_context("", None, "")
        except RuntimeError:
            self.lapine_upgrade_window = None

    def _sync_open_lapine_upgrade_tool_context(self, part_name):
        """裝備名稱變更時，同步已開啟的 Lapine 工具。"""
        window = getattr(self, "lapine_upgrade_window", None)
        if window is None:
            return

        try:
            if getattr(window, "target_part_name", "") != part_name:
                return
            ui = getattr(self, "refine_inputs_ui", {}).get(part_name)
            if not ui:
                return
            equipment_name = ui["equip"].text().strip()
            item_id, _ = self._get_equipment_lapine_context(equipment_name)
            window.set_target_context(part_name, item_id, equipment_name)
        except RuntimeError:
            self.lapine_upgrade_window = None

    def _refresh_lapine_note_display(self, part_name):
        """立即依詞條 Lua 更新主畫面可見的詞條 box。"""
        ui = getattr(self, "refine_inputs_ui", {}).get(part_name)
        if not ui:
            return
        note_widget = ui.get("note")
        note_ui = ui.get("note_ui")
        if note_widget is None or note_ui is None:
            return
        try:
            parsed_results = parse_lua_effects_with_variables(
                block_text=note_widget.toPlainText(),
                refine_inputs={},
                get_values={},
                grade=0,
                unit_map=unit_map,
                size_map=size_map,
                effect_map=effect_map,
                hide_unrecognized=False,
            )
            output = "\n".join(parsed_results)
        except Exception as exc:
            output = f"⚠️ 錯誤：{exc}"
        note_ui.setPlainText(output)
        QTimer.singleShot(0, lambda w=note_ui: self.adjust_textedit_height(w))

    def apply_lapine_random_options_from_tool(self, part_name, random_results):
        """只寫入本次隨機附魔的詞條函式本體，不建立任何相容包裝。"""
        part_name = str(part_name or "").strip()
        ui = getattr(self, "refine_inputs_ui", {}).get(part_name)
        if not ui:
            return
        note_widget = ui.get("note")
        if note_widget is None:
            return

        if isinstance(random_results, dict):
            random_results = [random_results]
        if not isinstance(random_results, (list, tuple)):
            return

        valid_results = []
        effect_lines = []
        for result in random_results:
            if not isinstance(result, dict):
                continue
            lua_effect = str(result.get("lua_effect") or "").strip()
            if not lua_effect:
                continue
            lines = [
                line.strip()
                for line in lua_effect.splitlines()
                if line.strip()
            ]
            if not lines:
                continue
            valid_results.append(dict(result, lua_effect="\n".join(lines)))
            effect_lines.extend(lines)
        if not valid_results:
            return

        # 不在詞條中寫入 BEGIN/END、EnumVAR 註解或 LapineRandomOption 包裝。
        # 上一次由本工具加入的內容只存在 QWidget property；重新附魔時，僅在它仍位於
        # 詞條尾端且完整相符時移除，避免誤刪使用者手動建立的相同函式。
        previous_lines = note_widget.property("lapine_random_effect_lines") or []
        previous_lines = [str(line).strip() for line in previous_lines if str(line).strip()]
        current_lines = note_widget.toPlainText().splitlines()

        while current_lines and not current_lines[-1].strip():
            current_lines.pop()

        if previous_lines and len(current_lines) >= len(previous_lines):
            tail = [line.strip() for line in current_lines[-len(previous_lines):]]
            if tail == previous_lines:
                del current_lines[-len(previous_lines):]
                while current_lines and not current_lines[-1].strip():
                    current_lines.pop()

        if current_lines:
            current_lines.append("")
        current_lines.extend(effect_lines)

        note_widget.setProperty("lapine_random_effect_lines", list(effect_lines))
        note_widget.setPlainText("\n".join(current_lines))

        # textChanged 通常會刷新；再直接刷新一次，確保可見詞條立即更新。
        self._refresh_lapine_note_display(part_name)
        self.clear_global_state()
        self._last_calc_state = None
        self.trigger_total_effect_update()
        self._refresh_lapine_note_display(part_name)
        self._set_lapine_upgrade_tool_target(
            part_name, "裝備", ui.get("equip").text().strip() if ui.get("equip") else ""
        )
        summary = "、".join(
            str(result.get("display_text") or result.get("option_code") or "")
            for result in valid_results
        )
        print(f"✅ 已將 Lapine 隨機附魔套用至「{part_name}」詞條：{summary}")

    def open_part_lapine_upgrade_tool(self, part_name):
        """從指定部位詞條 box 右側上方的附魔按鈕開啟 Lapine 工具。"""
        if not self._activate_equipment_edit_for_lapine(part_name):
            return

        equipment_name = self.refine_inputs_ui[part_name]["equip"].text().strip()
        item_id, _ = self._get_equipment_lapine_context(equipment_name)
        self.open_lapine_upgrade_tool(
            target_part=part_name,
            initial_equipment=equipment_name,
            initial_item_id=item_id,
        )

    def open_lapine_upgrade_tool(
        self,
        checked=False,
        target_part=None,
        initial_equipment=None,
        initial_item_id=None,
    ):
        """開啟 LapineUpgradeBox 檢視器；介面採 EnchantUI 的左右欄／分頁配置。"""
        target_part = target_part or ""
        initial_equipment = initial_equipment or ""

        if not target_part:
            current_edit = getattr(self, "current_edit_part", None)
            if current_edit:
                try:
                    part_name, field_type = current_edit.rsplit(" - ", 1)
                    if field_type == "裝備" and part_name in self.refine_inputs_ui:
                        target_part = part_name
                        initial_equipment = self.refine_inputs_ui[part_name]["equip"].text().strip()
                except ValueError:
                    pass

        if initial_item_id is None and initial_equipment:
            initial_item_id, _ = self._get_equipment_lapine_context(initial_equipment)

        window = getattr(self, "lapine_upgrade_window", None)
        if window is not None:
            try:
                window.set_target_context(
                    target_part,
                    initial_item_id,
                    initial_equipment,
                )
                window.show()
                window.raise_()
                window.activateWindow()
                return
            except RuntimeError:
                self.lapine_upgrade_window = None

        try:
            lapine_data, _, _ = self._load_lapine_upgrade_tool_data()
        except Exception as exc:
            QMessageBox.warning(
                self,
                tr("message.title.notice", "提示"),
                f"無法開啟 附加功能附魔工具：\n{exc}",
            )
            return

        self.lapine_upgrade_window = lapine_upgrade.LapineUpgradeUI(
            lapine_data,
            self.parsed_items,
            initial_target_item_id=initial_item_id,
            initial_equipment_name=initial_equipment,
            target_part_name=target_part,
            base_dir=get_app_base_dir(),
        )
        self.lapine_upgrade_window.randomEnchantApplyRequested.connect(
            self.apply_lapine_random_options_from_tool
        )
        self.lapine_upgrade_window.setWindowTitle("附加功能附魔工具")
        # 最右側新增固定寬度的隨機附魔 LOG，視窗同步加寬，避免壓縮中間分頁。
        self.lapine_upgrade_window.resize(1480, 700)
        self.lapine_upgrade_window.show()

    def open_reform_tool(self):#改造工具
        # 載入所需資料
        item_data = self.parsed_items
        reform = reform_viewer.parse_reform_info("data/ItemReformSystem.lua")
        reform_item_list = reform_viewer.parse_reform_item_list("data/ItemReformSystem.lua")
        itemdb = reform_viewer.parse_itemdb_name_tbl("data/ItemDBNameTbl.lua")

        # 建立 UI
        self.reform_viewer_window = reform_viewer.ReformUI(reform, item_data, itemdb, reform_item_list)
        self.reform_viewer_window.setWindowTitle(tr("window.reform_tool"))
        self.reform_viewer_window.resize(700, 600)
        self.reform_viewer_window.show()

    def _set_combo_by_key(self, combo, key: int):
        idx = combo.findData(key)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def apply_monster_to_main_ui(self, m: dict):
        self._set_combo_by_key(self.size_box, m["size_id"])
        self._set_combo_by_key(self.element_box, m["element_id"])
        self.element_lv_input.setText(str(m["element_lv"]))
        self._set_combo_by_key(self.race_box, m["race_id"])
        self._set_combo_by_key(self.class_box, m["class_id"])

        self.defc_input.setText(f'{m["def_before"]}')
        self.mdefc_input.setText(f'{m["mdef_before"]}')
        self.def_input.setText(str(m["def_after"]))
        self.mdef_input.setText(str(m["mdef_after"]))

        self.res_input.setText(str(m["res"]))
        self.mres_input.setText(str(m["mres"]))

        self.monster_f_atk = str(m["monster_f_atk"])
        self.monster_c_atk = str(m["monster_c_atk"])
        self.monster_f_matk = str(m["monster_f_matk"])
        self.monster_c_matk = str(m["monster_c_matk"])


    def open_monster_lookup(self):
        dlg = MonsterLookupDialog(self)
        dlg.monsterSelected.connect(self.apply_monster_to_main_ui)
        dlg.monsterSelected.connect(lambda: (setattr(self, "_last_calc_state", None), self.trigger_total_effect_update()))
        dlg.exec()

    def open_rrfdamage_view(self):
        if self.rrfdamage_window is None:
            self.rrfdamage_window = MainUI()

        self.rrfdamage_window.show()
        self.rrfdamage_window.raise_()
        self.rrfdamage_window.activateWindow()


    def open_damage_calculator(self):
        if self.atktype in ("physical"):
            atk = self.ATK_ALL
        elif self.atktype in ("d_b"):
            atk = 100
        else:
            atk = self.MATK_ALL

        steps = self.steps
        atktype = self.atktype

        if self._damage_win is None:
            self._damage_win = DamageCalculator(matk=atk, steps=steps, atktype=atktype)
            self._damage_win.setAttribute(Qt.WA_DeleteOnClose, True)
            self._damage_win.destroyed.connect(lambda: setattr(self, "_damage_win", None))
        else:
            self._damage_win.set_data(atk, steps)

        # ✅ 以主視窗左上角(全域座標)為基準偏移
        offset = QPoint(430, 45)  # 偏移量
        base = self.mapToGlobal(QPoint(0, 0))  # 主視窗客戶區左上角的全域座標
        self._damage_win.move(base + offset)

        self._damage_win.show()
        self._damage_win.raise_()
        self._damage_win.activateWindow()



    def open_skill_tree(self):

        skill_tree.job_dict = job_dict
        skill_tree.load_skill_tree("data/skill_tree.yml")
        skill_tree.load_skill_treeview("data/skilltreeview.lub")

        self.skill_tree_window = skill_tree.SkillTreeWindow()

        # ★ 新增：把主視窗傳給技能樹視窗（這一行是關鍵）
        self.skill_tree_window.attach_main_window(self)

        job_id = self.input_fields["JOB"].currentData()
        job_key = job_dict[job_id]["id_jobneme"]

        # ★ 設定 callback
        self.skill_tree_window.on_close_callback = self.receive_skill_tree_result

        # ★ 設定職業（這會觸發 on_job_changed，但需要等 event-loop）
        idx = self.skill_tree_window.job_combo.findData(job_key)
        self.skill_tree_window.job_combo.setCurrentIndex(idx)

        # ---------------------------------------------------
        # ★ 在下一輪事件（Qt）再執行 restore → 此時 on_job_changed 已初始化完成
        # ---------------------------------------------------
        def do_restore():
            self.restore_skill_tree_levels()

            # ★ 套用技能等級
            self.skill_tree_window.tree_widget.refresh_levels(
                self.skill_tree_window.current_skill_map_job,
                self.skill_tree_window.current_levels
            )

            # ★ 重算點數
            self.skill_tree_window.recalc_region_used()
            self.skill_tree_window.update_points_label()

        QTimer.singleShot(0, do_restore)
        self.input_fields["JOB"].setEnabled(False)
        self.skill_btn.setEnabled(False)
        self.skill_tree_window.show()




    def receive_skill_tree_result(self, text):
        # ★ 將 SkillTree 回傳結果寫入 技能 note 欄位
        self.refine_inputs_ui["技能"]["note"].setPlainText(text)
        #self.refine_inputs_ui["技能"]["note_ui"].setPlainText(text)
        self.input_fields["JOB"].setEnabled(True)
        self.skill_btn.setEnabled(True)
        self.trigger_total_effect_update()



    def restore_skill_tree_levels(self):
        import re
        from skill_tree import skill_code_to_id

        note_widget = self.refine_inputs_ui["技能"]["note"]
        note = note_widget.toPlainText().strip()
        if not note:
            return

        matches = re.findall(r"EnableSkill\((\d+),\s*(\d+)\)", note)
        if not matches:
            return

        restored = {}

        # skill_code_to_id = { "SKIDNAME" : 1234 }
        for code, sid in skill_code_to_id.items():
            for sid2, lv in matches:
                if sid == int(sid2):
                    restored[code] = int(lv)

        if hasattr(self, "skill_tree_window"):
            self.skill_tree_window.current_levels = restored



    def update_window_title(self):
        filename = os.path.basename(self.current_file) if self.current_file else "未命名"
        self.setWindowTitle(tr("window.main_with_file", version=Version, filename=filename, Server_area=Server_area))
    
    def replace_custom_calc_content(self, *_args, render_output=True, force_recalc=False):
        # 特殊 CheckBox 狀態
        special_state = "|".join(
            f"{key}:{checkbox.isChecked()}"
            for key, checkbox in self.special_checkboxes.items()
        )
                        #轉成全域變數
        def get_effect_multiplier(category, index):
            return getattr(self, f"{category}_{index}", 0)
        
        result = []
        stat_names = ["STR", "AGI", "VIT", "INT", "DEX", "LUK",
                      "POW", "STA", "WIS", "SPL", "CON", "CRT"]

        # === 從 UI 中取 BaseLv 與 JobLv ===
        try:
            base_lv = int(self.input_fields["BaseLv"].text())
        except:
            base_lv = 0

        try:
            job_lv = int(self.input_fields["JobLv"].text())
        except:
            job_lv = 0

        globals()["BaseLv"] = base_lv
        globals()["JobLv"] = job_lv

        # === 從 UI 輸入 + 職業 + 裝備效果取各項能力加成 ===
        job_id = self.input_fields["JOB"].currentData()
        job_bonus = job_dict.get(job_id, {}).get("TJobMaxPoint", [])
        globals()["job_idcore"] = job_dict[job_id]["id"]#取得職業ID代號
        raw_effects = getattr(self, "effect_dict_raw", {})
        base_values = {}
        for stat in stat_names:
            try:
                base_values[stat] = self.input_fields[stat].text()
            except Exception:
                base_values[stat] = 0
        base_equipment_stats = {
            stat: globals().get(f"base_equip_{stat}", 0)
            for stat in stat_names
        }
        stat_breakdown = core_calculate_stat_breakdown(
            base_values=base_values,
            job_bonus=job_bonus,
            effect_dict=raw_effects,
            base_equipment_stats=base_equipment_stats,
        )
        for stat in stat_names:
            values = stat_breakdown[stat]
            globals()[f"base_{stat}"] = values["base"]
            globals()[f"job_{stat}"] = values["job"]
            globals()[f"equip_{stat}"] = values["equip"]
            globals()[f"base_equip_{stat}"] = values["base_equip"]
            globals()[f"total_{stat}"] = values["total"]

        #current_text = self.custom_calc_box.toPlainText()
        # 減傷計算分頁的目標欄位維持與傷害計算同步；初始化/讀檔/查怪時也能自動補齊。
        self._sync_damage_to_body_target_fields()

        skill_key = self.skill_box.currentData()
        skill_lv = int(self.skill_LV_input.text()) if self.skill_LV_input.text().isdigit() else 0

        
        # ✅ 裝備狀態（你可以根據實際來源換成 combo_effect_text.text() 之類的）
        equip_state = self.total_effect_text.toPlainText()
        # 目標設定選項
        size_key = self.size_box.currentData()
        element_key = self.element_box.currentData()
        race_key = self.race_box.currentData()
        class_key = self.class_box.currentData()
        element_lv_key = self.element_lv_input.text() or 1
        user_element_key = self.attack_element_box.currentData()
        damage_reduction_key = self.damage_reduction_combobox.currentIndex()
        MD_BETELGEUSE_data = int(self.MD_BETELGEUSE_total)
        #monsterDamage_key = self.monsterDamage_input.text() or "0"#指定魔物增傷UI
        # 整數輸入值（注意空字串要預設為 0）
        d_ef = self.def_input.text() or "0"
        defc = self.defc_input.text() or "0"
        res = self.res_input.text() or "0"
        mdef = self.mdef_input.text() or "0"
        mdefc = self.mdefc_input.text() or "0"
        mres = self.mres_input.text() or "0"
        skill_formula = self.skill_formula_input.text()
        weapon_class = global_weapon_type_map.get(4, 0)
        # 組合新的 state_key
        state_key = f"{weapon_class}|{MHP_NOW}|{MSP_NOW}|{BaseLv}|{Use_skill_levels}|{skill_formula}|{skill_key}|{skill_lv}|{equip_state}|{special_state}|{size_key}|{element_key}|{race_key}|{class_key}|{d_ef}|{defc}|{res}|{mdef}|{mdefc}|{mres}|{element_lv_key}|{user_element_key}|{total_STR}|{total_AGI}|{total_VIT}|{total_INT}|{total_DEX}|{total_LUK}|{total_POW}|{total_STA}|{total_WIS}|{total_SPL}|{total_CON}|{total_CRT}|{MD_BETELGEUSE_data}|{damage_reduction_key}"
        MD_BETELGEUSE_state_key = f"{size_key}|{element_key}|{race_key}|{class_key}|{element_lv_key}|{d_ef}|{defc}|{res}|{mdef}|{mdefc}|{mres}|{damage_reduction_key}"
        #print(f"{MD_BETELGEUSE_state_key}")

        MD_BETELGEUSE_set_key = "2|0|9|1|2|346|191|500|102|105|500|2"

        if MD_BETELGEUSE_state_key == MD_BETELGEUSE_set_key:
            self.MD_BETELGEUSE_label_def.setVisible(True)
            self.MD_BETELGEUSE_combo_def.setVisible(True)
            self.MD_BETELGEUSE_label_soul.setVisible(True)
            self.MD_BETELGEUSE_combo_soul.setVisible(True)
            self.MD_BETELGEUSE_label_total_title.setVisible(True)
            self.MD_BETELGEUSE_label_total.setVisible(True)
        else:
            self.MD_BETELGEUSE_label_def.setVisible(False)
            self.MD_BETELGEUSE_combo_def.setVisible(False)
            self.MD_BETELGEUSE_label_soul.setVisible(False)
            self.MD_BETELGEUSE_combo_soul.setVisible(False)
            self.MD_BETELGEUSE_label_total_title.setVisible(False)
            self.MD_BETELGEUSE_label_total.setVisible(False)
            # 計算流程內部重設 ComboBox 時不要再觸發另一輪計算。
            self.MD_BETELGEUSE_combo_def.blockSignals(True)
            self.MD_BETELGEUSE_combo_soul.blockSignals(True)
            try:
                self.MD_BETELGEUSE_combo_def.setCurrentIndex(0)
                self.MD_BETELGEUSE_combo_soul.setCurrentIndex(0)
            finally:
                self.MD_BETELGEUSE_combo_def.blockSignals(False)
                self.MD_BETELGEUSE_combo_soul.blockSignals(False)
            MD_BETELGEUSE_data = 0


        if not force_recalc and getattr(self, "_last_calc_state", None) == state_key:
            print("【⛔ 裝備效果沒有更動，跳過運算。】")
            return  # ⛔ 跳過重複運算

        # 預覽計算（render_output=False）不更新快取；
        # 最終真正輸出時才記錄狀態，避免第一輪把第二輪擋掉。
        if render_output:
            self._last_calc_state = state_key

        print("【🧠 執行 replace_custom_calc_content()】")
        # 原本你的公式解析邏輯

        #心神凝聚計算
        #print(f"base_equip_AGI{base_equip_AGI} base_AGI{base_AGI} job_AGI{job_AGI}")
        #print(f"base_equip_DEX{base_equip_DEX} base_DEX{base_DEX} job_DEX{job_DEX}")
        globals()["skill_focus_AGI"] = stat_breakdown["AGI"]["focus"]
        globals()["skill_focus_DEX"] = stat_breakdown["DEX"]["focus"]
        #======================取所有增傷資料到變數區=====================
        effect_dict = getattr(self, "effect_dict_raw", {})
        globals()["HP"] = sum(val for val, _ in effect_dict.get(("MHP", ""), []))
        globals()["HPPercent"] = sum(val for val, _ in effect_dict.get(("MHP%", "%"), []))
        globals()["SP"] = sum(val for val, _ in effect_dict.get(("MSP", ""), []))
        globals()["SPPercent"] = sum(val for val, _ in effect_dict.get(("MSP%", "%"), []))
        globals()["HPRegenPercent"] = sum(val for val, _ in effect_dict.get(("HP自然恢復%", "%"), []))
        globals()["SPRegenPercent"] = sum(val for val, _ in effect_dict.get(("SP自然恢復%", "%"), []))




        #print(f"hp:{HP} hp%:{HPPercent}sp:{SP} sp%:{SPPercent} h恢復{HPRegenPercent}s恢復 {SPRegenPercent}")
        #呼叫處理物理,魔法增傷,無視防禦 例:(對"小型"敵人的魔法傷害 +5%)
        self.apply_all_damage_effects(effect_dict)
        #主手武器類型(數字)
        weapon_class = global_weapon_type_map.get(4, 0)
        #副手武器類型(數字)
        Subweapon_class = global_weapon_type_map.get(3, 0)        
        #主手武器類型(代號)
        globals()["weapon_codes"] = weapon_class_codes.get(weapon_class, "?")
        #副手武器類型(數字)
        globals()["Subweapon_codes"] = 0 if Subweapon_class == 0 else 2
        #print(f"副手武器類型代號 {Subweapon_codes}")
        #裝備ATK(不含武器)
        globals()["ATK_armor"] = sum(val for val, _ in effect_dict.get(("ATK", ""), []))
        #修煉ATK
        globals()["WeaponMasteryATK"] = sum(val for val, _ in effect_dict.get(("修煉ATK", ""), []))
        #修煉ATK
        globals()["KamuiATK"] = sum(val for val, _ in effect_dict.get(("神威ATK", ""), []))
        #裝備MATK(不含武器)
        globals()["MATK_armor"] = sum(val for val, _ in effect_dict.get(("MATK", ""), []))
        #裝備ATK%
        globals()["ATK_percent"] = sum(val for val, _ in effect_dict.get(("ATK%", "%"), []))
        #裝備MATK%
        globals()["MATK_percent"] = sum(val for val, _ in effect_dict.get(("MATK%", "%"), []))
        #武器ATK
        #globals()["ATK_Mweapon"] = sum(val for val, _ in effect_dict.get(("武器ATK", ""), []))#捨棄ui資料，改成map資料
        globals()["ATK_Mweapon"] = global_weapon_atk_map.get(4, 0)#主手
        globals()["ATK_MweaponL"] = global_weapon_atk_map.get(3, 0)#副手
        #武器MATK
        #globals()["MATK_Mweapon"] = sum(val for val, _ in effect_dict.get(("武器MATK", ""), []))#捨棄ui資料，改成map資料
        globals()["MATK_Mweapon"] = global_weapon_matk_map.get(4, 0)#主手
        globals()["MATK_MweaponL"] = global_weapon_matk_map.get(3, 0)#副手
        #武器等級
        #globals()["weapon_Level"] = sum(val for val, _ in effect_dict.get(("武器等級", ""), []))#捨棄ui資料，改成map資料
        globals()["weaponR_Level"] = global_weapon_level_map.get(4, 0)#主手
        globals()["weaponL_Level"] = global_weapon_level_map.get(3, 0)#副手
        #print(f"武器等級R{weaponR_Level} L{weaponL_Level}")
        #箭矢彈藥ATK
        globals()["ammoATK"] = sum(val for val, _ in effect_dict.get(("箭矢/彈藥ATK", ""), []))
        #砲彈ATK
        globals()["CannonballATK"] = sum(val for val, _ in effect_dict.get(("砲彈ATK", ""), []))
        #武器精煉R右L左
        globals()["weaponRefineR"] = int(self.refine_inputs_ui["右手(武器)"]["refine"].text().strip() or 0)
        globals()["weaponRefineL"] = int(self.refine_inputs_ui["左手(盾牌)"]["refine"].text().strip() or 0)
        #武器階級R右L左
        globals()["weaponGradeR"] = int(self.refine_inputs_ui["右手(武器)"]["grade"].currentIndex())
        globals()["weaponGradeL"] = int(self.refine_inputs_ui["左手(盾牌)"]["grade"].currentIndex())
        #print(f"{weaponRefineR} {weaponRefineL} {weaponGradeR} {weaponGradeL}")
        globals()["PATK"] = sum(val for val, _ in effect_dict.get(("P.ATK", ""), []))
        globals()["SMATK"] = sum(val for val, _ in effect_dict.get(("S.MATK", ""), []))
        #print(f"S.MATK{SMATK}")
        #公式用
        
        SKILL_ASC_KATAR = (enabled_skill_levels.get(376,0) * 2) + 10 if weapon_class == 16 else 0#高階拳刃修煉
        #print(f"高階拳刃修煉 {SKILL_ASC_KATAR}")


        # 從下拉選單與欄位取得目標資訊
        target_size    = self.size_box.currentData()
        target_element = self.element_box.currentData()#複製到trigger_total_effect_update先取得
        monster_attack_element = self.monster_body_element_box.currentData()
        target_race    = self.race_box.currentData()
        target_class   = self.class_box.currentData()
        User_attack_element = self.attack_element_box.currentData()

        #輸出ROCalculator全域變數區 globals()[""] = 
        globals()["RaceMatkPercent"] = get_effect_multiplier('MD_Race', target_race) + get_effect_multiplier('MD_Race', 9999)#魔法種族
        globals()["SizeMatkPercent"] = get_effect_multiplier('MD_size', target_size)#魔法體型
        globals()["LevelMatkPercent"] = get_effect_multiplier('MD_class', target_class)#魔法階級
        globals()["ElementalMatkPercent"] = get_effect_multiplier('MD_element', target_element) + get_effect_multiplier('MD_element', 10)#魔法屬性對象
        globals()["ElementalMagicPercent"] = get_effect_multiplier('MD_Damage', User_attack_element) + get_effect_multiplier('MD_Damage', 10)#屬性魔法
        globals()["RaceAtkPercent"] = get_effect_multiplier('D_Race', target_race) + get_effect_multiplier('D_Race', 9999)#物理種族
        globals()["SizeAtkPercent"] = get_effect_multiplier('D_size', target_size)#物理體型
        globals()["LevelAtkPercent"] = get_effect_multiplier('D_class', target_class)#物理階級
        globals()["ElementalAtkPercent"] = get_effect_multiplier('D_element', target_element) + get_effect_multiplier('D_element', 10)#物理屬性對象
        globals()["target_monsterDamage"] = sum(val for val, _ in effect_dict.get((f"特定魔物物理增傷", "%"), []))
        globals()["target_monsterMDamage"] = sum(val for val, _ in effect_dict.get((f"特定魔物魔法增傷", "%"), []))

        
        #========================以上魔法增傷===================
        

        try:
            target_element_lv = int(self.element_lv_input.text() or 1)#目標屬性等級
        except ValueError:
            target_element_lv = 1
        try:
            target_def = int(self.def_input.text() or 0)
        except ValueError:
            target_def = 0
        try:
            target_defc = int(self.defc_input.text() or 0)
        except ValueError:
            target_defc = 0
        try:
            target_res = int(self.res_input.text() or 0)
        except ValueError:
            target_res = 0
        try:
            target_mdef = int(self.mdef_input.text() or 0)
        except ValueError:
            target_mdef = 0
        try:
            target_mdefc = int(self.mdefc_input.text() or 0)
        except ValueError:
            target_mdefc = 0
        try:
            target_mres = int(self.mres_input.text() or 0)
        except ValueError:
            target_mres = 0

        #=======取得目前有的技能等級如果沒有回傳0        
        def GSklv(skill_id):
            return enabled_skill_levels.get(skill_id, 0)  # 若沒有這個技能，預設回傳 0
        def GUSklv(skill_id):
            v = Use_skill_levels.get(skill_id, 0)  # 沒有就 0
            if isinstance(v, bool):
                return int(v)  # True->1, False->0
            return v

        #處理公式中的動態變數========================
        def replace_gsklv_calls(formula: str) -> str:
            return _core_stage17_replace_gsklv_calls(formula, enabled_skill_levels)
        def replace_gusklv_calls(formula: str) -> str:
            return _core_stage17_replace_gusklv_calls(formula, Use_skill_levels)

        def replace_size_calls(formula: str, target_size: int) -> str:
            return _core_stage17_replace_size_calls(formula, target_size)

        def replace_custom_calls(formula):
            global global_weapon_type_map
            return _core_stage17_replace_custom_calls(formula, global_weapon_type_map.get(4, 0))
        

        def eval_formula_with_vars(formula: str, allowed_vars: dict):
            return _core_stage17_eval_formula_with_vars(formula, allowed_vars)


        #=================== 特殊增傷ui取得/處理區===================
        #萬紫/震裂4
        skill_wanzih4_buff = 100/100 if self.special_checkboxes["wanzih_checkbox"].isChecked() and 2 <= User_attack_element <= 3 else 0
        #毒耐性弱化
        skill_poison_weak_buff = 50/100 if self.special_checkboxes["poison_weak_checkbox"].isChecked() and User_attack_element == 5 else 0
        #魔力中毒
        magic_poison_buff = 50/100 if self.special_checkboxes["magic_poison_checkbox"].isChecked() else 0
        #屬性紋章
        attribute_seal_buff = 1+50/100 if self.special_checkboxes["attribute_seal_checkbox"].isChecked() and 1 <= User_attack_element <= 4 else 1
        #潛擊
        is_sneak_checked = self.special_checkboxes["sneak_attack_checkbox"].isChecked()
        sneak_attack_buff = 1+30/100 if is_sneak_checked and target_class == 0 else 1+15/100 if is_sneak_checked else 0
        sneak_MDattack_buff = 30 if is_sneak_checked and target_class == 0 else 15 if is_sneak_checked else 0
        #致命塗毒
        EDP_attack = 300 if int(GUSklv(378)) == 1 else 0 #378
        #爪痕
        is_DARKCROW_checked = self.special_checkboxes["DARKCROW_attack_checkbox"].isChecked()
        DARKCROW_attack_buff = 1+150/100 if is_DARKCROW_checked and target_class == 0 else 1+75/100 if is_DARKCROW_checked else 0
        #撼動
        RUSH_attack_buff = 1+50/100 if self.special_checkboxes["RUSH_attack_checkbox"].isChecked() else 0
        #孢子
        SPORE_attack_buff = 1+5/100 if self.special_checkboxes["SPORE_attack_checkbox"].isChecked() else 0
        #聖油
        OLEUM_attack_buff = 1+15/100 if self.special_checkboxes["OLEUM_attack_checkbox"].isChecked() else 0
        #魔力增幅
        SKILL_HW_MAGICPOWER = 10 if int(GUSklv(366)) == 1 else 0  # 366
        #天怒
        PR_LEXAETERNA_buff = 100 if self.special_checkboxes["PR_LEXAETERNA_checkbox"].isChecked() else 0
        #鐵虎咆嘯
        #Use_skill_levels[5436] = True if self.special_checkboxes["SH_HOWLING_OF_CHUL_HO_checkbox"].isChecked() else 0
        #太陽和月亮和星星的融合 全部吃爆擊
        sg_mix = 0.5 if int(GUSklv(444)) == 1 else 0  # 444
        #溫暖風判段
        SEVENWIND = 1 if int(GUSklv(425)) == 1 else 0  # 425
        #加油
        tk_power = int(GSklv(424))*20  # 424
        #奇蹟/憎惡段
        SG_HATE = 1 if int(GUSklv(434)) == 1 else 0  # 434
        #靈氣劍
        LK_AURABLADE = base_lv * (3 + int(GSklv(355))) if int(GUSklv(355)) == 1 else 0  # 355
        """
        target_size       # 來自 體型 的數值
        target_element    # 屬性編號
        target_element_lv # 目標屬性等級
        target_race       # 種族代碼C
        target_class      # 階級代碼
        target_mdef       # 數字輸入 MDEF前
        target_mdefc      # 數字輸入 MDEF後
        target_mres       # 數字輸入 MRES
        User_attack_element #施展屬性
        """
        #=============參考動態變數自動抓技能%=(裝備段)==============
        # 從 skill_box 取得目前選中的技能名稱（顯示文字）
        selected_skill_name = self.skill_box.currentText()
        globals()["Use_Skills"] = sum(val for val, _ in effect_dict.get((f"技能【{selected_skill_name}】傷害(裝備段)", "%"), []))
        #=============參考動態變數自動抓技能%=(技能段)==============      
        passive_skill_buff = sum(val for val, _ in effect_dict.get((f"技能【{selected_skill_name}】傷害(技能段)", "%"), []))
        #=====================其他物理增傷/抗性========================
        globals()["MeleeAttackDamage"] = sum(val for val, _ in effect_dict.get((f"近距離物理傷害", "%"), []))
        globals()["RangeAttackDamage"] = sum(val for val, _ in effect_dict.get((f"遠距離物理傷害", "%"), []))
        globals()["body_MeleeAttackDamage"] = sum(val for val, _ in effect_dict.get((f"受到近距離物理傷害", "%"), []))
        globals()["body_RangeAttackDamage"] = sum(val for val, _ in effect_dict.get((f"受到遠距離物理傷害", "%"), []))
        globals()["Damage_CRI"] = sum(val for val, _ in effect_dict.get((f"爆擊傷害", "%"), []))
        globals()["Damage_HIT"] = sum(val for val, _ in effect_dict.get((f"物理命中傷害", "%"), []))
        globals()["BowAtk"] = sum(val for val, _ in effect_dict.get((f"弓攻擊力", "%"), []))
        globals()["CRATE"] = sum(val for val, _ in effect_dict.get((f"C.RATE", ""), []))   
        Ignore_size = sum(val for val, _ in effect_dict.get((f"武器體型修正", "%"), []))   
        if any("武器浸透勁效果" in key for (key, unit) in effect_dict.keys()):
            print("有武器浸透勁效果")
            Use_skill_levels[266] = True
        # === Stage 21.24: skill timing modifiers are aggregated in ro_core.py ===
        #ASPD計算
        atkaspd = -sum(val for val, _ in effect_dict.get(("(2轉以下)攻擊後延遲", "%"), []))
        #print(f"(2轉以下)攻擊後延遲減少：{atkaspd}%")
        aspdno = sum(val for val, _ in effect_dict.get(("(2轉以下)ASPD", ""), []))
        #print(f"(2轉以下)最終ASPD：{aspdno}")   
        atkaspd_2 = -sum(val for val, _ in effect_dict.get(("攻擊後延遲", "%"), []))        
        #print(f"攻擊後延遲減少：{atkaspd_2}%")
        aspdno_2 = sum(val for val, _ in effect_dict.get(("ASPD", ""), []))
        #print(f"最終ASPD：{aspdno_2}")        
        has_shield = True if global_armor_weapon_map.get(3, 0) == "armor" else False
        #print(f"副手拿盾：{has_shield}")
       
        if global_armor_weapon_map.get(3, 0) in ("Mweapon","Rweapon"):
            # 雙刀（右手/左手）
            #print("雙手模式")
            aspd = self.calc_aspd(
                WPASPDdata, job_id=job_id, agi=total_AGI, dex=total_DEX,
                dual_wield=True,
                right_weapon_type=global_weapon_type_map.get(4, 0),
                left_weapon_type=global_weapon_type_map.get(3, 0),
                cat1_rate=atkaspd, cat1_flat=aspdno,
                cat2_rate=atkaspd_2, cat2_flat=aspdno_2
            )
        else:
            #print("單手模式")
            # 一般（可持盾）
            aspd = self.calc_aspd(
                WPASPDdata, job_id=job_id, agi=total_AGI, dex=total_DEX,
                weapon_type=global_weapon_type_map.get(4, 0), has_shield=has_shield,
                cat1_rate=atkaspd, cat1_flat=aspdno,    # 15% + 2 點（也可用 0.15）
                cat2_rate=atkaspd_2, cat2_flat=aspdno_2
            )        

        
        gcdtotal_raw_s = update_skill_delay_labels(#更新固定變動冷卻後延數值
                skill_name=selected_skill_name,
                skill_map_all=skill_map_all,
                lua_text=self.lua_text,
                fix_label=self.fix_label,
                delay_label=self.Delay_label,
                cast_bar=self.cast_bar,
                skill_level=skill_lv,
                effect_dict=effect_dict,
                total_dex=total_DEX,
                total_int=total_INT,
            )
        

        if isinstance(aspd, (int, float)):            
            aspds = 50/(200-min(193,int(aspd)))
            if gcdtotal_raw_s <= 0:
                ASPD_GCD = 0
            else:
                ASPD_GCD = max(0,math.ceil((1 - ((1 / (50 / (200 - min(193,int(aspd))))) / gcdtotal_raw_s)) / 0.01))
            if render_output:
                self.ASPD_label.setText(tr("label.aspd_info", aspd=aspd, aspds=f"{aspds:.2f}", gcd=ASPD_GCD))
        else:
            if render_output:
                self.ASPD_label.setText(tr("label.aspd_weapon_not_supported"))

        #=======================技能欄公式====================
        #====================DEF計算==================
        def calc_final_def_damage(d_ef: float, reduction_percent: float) -> float:
            return _core_stage17_calc_final_def_damage(d_ef, reduction_percent)
        #====================MRES,MDEF計算===================
        #====================MDEF計算==================
        def calc_final_mdef_damage(mdef: float, reduction_percent: float) -> float:
            return _core_stage17_calc_final_mdef_damage(mdef, reduction_percent)
        #====================RES/MRES計算==================
        def calc_final_res_damage(mres: float, reduction_percent: float) -> float:
            return _core_stage17_calc_final_res_damage(mres, reduction_percent)
            
        # === [1] 取得技能 row
        skill_row = skill_df[skill_df["Name"] == selected_skill_name]
        if skill_row.empty:
            # 給一個「空內容但欄位齊全」的 Series
            skill_row = pd.Series({col: None for col in skill_df.columns})
        else:
            skill_row = skill_row.iloc[0]

        # 半無視 / DEF / MDEF / RES / MRES 已集中到 ro_core，Desktop 只保留變數相容層。
        half_bypass_def = int(skill_row["half_bypass_def"]) if pd.notna(skill_row.get("half_bypass_def")) else 0
        half_bypass_res = int(skill_row["half_bypass_res"]) if pd.notna(skill_row.get("half_bypass_res")) else 0
        defense_factors = _core_stage17_calculate_target_defense_factors(
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
        damage_nodef = defense_factors["def_multiplier"]
        Mdamage_nomdef = defense_factors["mdef_multiplier"]
        damage_nores = defense_factors["res_multiplier"]
        Mdamage_nomres = defense_factors["mres_multiplier"]
        target_defc = defense_factors["target_defc"]

        # 查詢屬性倍率函數
        def get_damage_multiplier(attacker_element: int, defender_element: int, level: int) -> int:
            return _core_stage17_get_damage_multiplier(attacker_element, defender_element, level)

        
        # 武器體型懲罰(物理)
        def get_size_penalty(weapon_class: int, target_size: int) -> float:
            return _core_stage17_get_size_penalty(weapon_class, target_size)



        #==========================精煉計算=========================
        #武器ATK精煉計算
        patk_refine_total = 0
        atk_refine_total, patk_refine_total, refineoveratk ,refineoveratk_min = self.calc_weapon_refine_atk(weaponR_Level, weaponRefineR, weaponGradeR)
        atk_refine_total_L, patk_refine_total_L, refineoveratk_L, refineoveratk_L_min = self.calc_weapon_refine_atk(weaponL_Level, weaponRefineL, weaponGradeL)#atk_refine_total_L 副手不計算ATK 只計算PATK
        #PATK(裝備+精煉+特性素質)
        globals()["total_PATK"] = PATK + int(total_POW/3) + int(total_CON/5) + patk_refine_total + patk_refine_total_L
        #武器MATK精煉計算
        smatk_refine_total = 0
        matk_refine_total, smatk_refine_total, refineovermatk, refineovermatk_min = self.calc_weapon_refine_matk(weaponR_Level, weaponRefineR, weaponGradeR)
        matk_refine_total_L, smatk_refine_total_L, refineovermatk_L ,refineovermatk_L_min = self.calc_weapon_refine_matk(weaponL_Level, weaponRefineL, weaponGradeL)
        #SMATK(裝備+精煉+特性素質)
        total_SMATK = SMATK + int(total_SPL/3) + int(total_CON/5) + smatk_refine_total + smatk_refine_total_L
        #============================魔法各增傷計算區============================


        def visual_length(s: str) -> int:
            """計算視覺寬度：全形字算2，半形算1"""
            width = 0
            for c in s:
                width += 2 if ord(c) > 255 else 1
            return width

        def pad_label(label: str, total_width: int = 22) -> str:
            """依據視覺寬度補空格，讓冒號後對齊"""
            space_count = total_width - visual_length(label)
            return label + " " * max(space_count, 0)
        

        #物理===================     
        #浸透勁效果
        def_reduction_temp = int(100-def_reduction) #總階級種族破防-浸透勁破防100% 
        WPINVESTIGATEATK = max(0,int((target_def/2) + (target_def/2)*(def_reduction_temp/100))) if GUSklv(266) == 1 else 0 
        target_defc = 0 if GUSklv(266) == 1 else target_defc
        #print(f"浸透勁效果後atk+{WPINVESTIGATEATK}")
        #近傷ATK
        #NATK = int(BaseLv/4) + int(total_STR) + int(total_DEX/5) + int(total_LUK/3) + int(total_POW*5)
        NATK = int((BaseLv/4) + (total_STR) + (total_DEX/5) + (total_LUK/3) + (total_POW*5))
        #遠傷ATK(弓槍樂器鞭子)
        #FATK = int(BaseLv/4) + int(total_STR/5) + int(total_DEX) + int(total_LUK/3) + int(total_POW*5)
        FATK = int((BaseLv/4) + (total_STR/5) + (total_DEX) + (total_LUK/3) + (total_POW*5))
        #後ATK (只給面板顯示不參與計算)
        AKTC = ATK_Mweapon + ATK_armor + atk_refine_total + WPINVESTIGATEATK
        #C.RATE
        total_CRATE = CRATE + int(total_CRT/3)


        if weapon_class in (11,13,14,17,18,19,20,21):#DEX系
            #武器基礎ATK(dex)
            if int(GUSklv(114)) == 1:
                BasicsWeaponATK_min = ATK_Mweapon * (1+ (total_DEX/200) + (weaponR_Level*0.05))
            else:
                BasicsWeaponATK_min = ATK_Mweapon * (1+ (total_DEX/200) - (weaponR_Level*0.05))

            BasicsWeaponATK = ATK_Mweapon * (1+ (total_DEX/200) + (weaponR_Level*0.05))
            
        else:#STR系
            #武器基礎ATK(STR)
            if int(GUSklv(114)) == 1:
                BasicsWeaponATK_min = ATK_Mweapon * (1+ (total_STR/200) + (weaponR_Level*0.05))
            else:
                BasicsWeaponATK_min = ATK_Mweapon * (1+ (total_STR/200) - (weaponR_Level*0.05))

            BasicsWeaponATK = ATK_Mweapon * (1+ (total_STR/200) + (weaponR_Level*0.05))
        
        #print(f"BasicsWeaponATK:{BasicsWeaponATK}")
        #精煉武器ATK
        if weapon_class in (11,13,14,17,18,19,20,21):#DEX系
            refineWeaponATK_min = int(BasicsWeaponATK_min + atk_refine_total - refineoveratk )
            refineWeaponATK = int(BasicsWeaponATK + atk_refine_total - refineoveratk)  
        else:#STR系
            refineWeaponATK_min = int(BasicsWeaponATK_min + atk_refine_total + refineoveratk_min - refineoveratk )
            refineWeaponATK = int(BasicsWeaponATK + atk_refine_total)  
        #print(f"refineWeaponATK:{refineWeaponATK}")

        #武器體型修正
        Weaponpunish = 1 if Ignore_size >= 100 else get_size_penalty(weapon_class, target_size)
        #取得武器小中大體型懲罰
        globals()["weapon_weapon_size0"] = get_size_penalty(weapon_class, 0)*100
        globals()["weapon_weapon_size1"] = get_size_penalty(weapon_class, 1)*100
        globals()["weapon_weapon_size2"] = get_size_penalty(weapon_class, 2)*100
        #奇蹟憎惡增傷處理 最大總和增傷75%
        if SG_HATE == 1:            
            if target_size == 2:
                SG_HATE_EXCEL = min(int((total_STR + total_DEX + total_LUK + base_lv) / 3), 75)
            else:
                SG_HATE_EXCEL = min(int((total_DEX + total_LUK + base_lv) / 3), 75)
        else:
            SG_HATE_EXCEL = 0

        #print(f"Ignore_size:{Ignore_size}") 
        #print(f"武器體型修正:{Weaponpunish}")   
        #(精煉武器ATK*體型懲罰)+箭矢彈藥ATK
        refineammoATK_min = int(refineWeaponATK_min * Weaponpunish) + ammoATK
        refineammoATK = int(refineWeaponATK * Weaponpunish) + ammoATK
        
        #怒爆或致命塗毒 1+(怒爆20%/致命塗毒25%)*屬性倍率 
        #致命塗毒
        EDP = 1 + 0.25 * (get_damage_multiplier(5, target_element, target_element_lv)/100) if int(GUSklv(378)) == 1 else 1
        #怒爆
        MAGNUM = 1 + 0.2 * (get_damage_multiplier(3, target_element, target_element_lv)/100) if int(GUSklv(7)) == 1 else 1
        #print(f"EDP:{EDP},MAGNUM:{MAGNUM}")
        # specialATK_min = int(refineammoATK_min * EDP * MAGNUM) 
        # specialATK = int(refineammoATK * EDP * MAGNUM)
        if int(GUSklv(378)) == 2 and int(GUSklv(7)) == 2:#測試用 應該是不會有
            specialATK_min = int(refineammoATK_min * EDP * MAGNUM) 
            specialATK = int(refineammoATK * EDP * MAGNUM) 
        elif int(GUSklv(378)) == 1:
            specialATK_min = int(refineammoATK_min * EDP) 
            specialATK = int(refineammoATK * EDP) 
        elif int(GUSklv(7)) == 1:
            specialATK_min = int(refineammoATK_min * MAGNUM)
            specialATK = int(refineammoATK * MAGNUM)
        else:
            specialATK_min = int(refineammoATK_min)
            specialATK = int(refineammoATK)

        #前素質總ATK
        if weapon_class in (11,13,14,17,18,19,20,21):#DEX系
            #ATKF = int((FATK*2) * (get_damage_multiplier(User_attack_element, target_element, target_element_lv)/100))
            if SEVENWIND == 1:#判斷暖風轉屬
                ATKF = int((FATK*2) * (get_damage_multiplier(User_attack_element, target_element, target_element_lv)/100)) #溫暖風轉屬
            else:
                ATKF = int((FATK*2) * (get_damage_multiplier(0, target_element, target_element_lv)/100)) #前段強制無屬 除非溫暖風轉屬
        else:#STR系
            if SEVENWIND == 1:#判斷暖風轉屬
                ATKF = int((NATK*2) * (get_damage_multiplier(User_attack_element, target_element, target_element_lv)/100)) #溫暖風轉屬
            else:
                ATKF = int((NATK*2) * (get_damage_multiplier(0, target_element, target_element_lv)/100)) #前段強制無屬 除非溫暖風轉屬
        
        #後武器總ATK
        ATKC_Mweapon_ALL_min = (specialATK_min + ATK_armor + WPINVESTIGATEATK) 
        ATKC_Mweapon_ALL = (specialATK + ATK_armor + WPINVESTIGATEATK) 
        self.ATK_ALL = ATKC_Mweapon_ALL
        #print(f"ATKC_Mweapon_ALL:{ATKC_Mweapon_ALL}")

        
        #魔法===================
        #前MATK
        MATKF = int(BaseLv/4) + int(total_INT*1.5) + int(total_DEX/5) + int(total_LUK/3) + int(total_SPL*5)
        #後MATK
        MATKC = MATK_armor + MATK_Mweapon + MATK_MweaponL + matk_refine_total + matk_refine_total_L
        #武器MATK
        if int(GUSklv(2206)) == 1:
            MATK_Mweapon_ALL_min = MATKF + ((matk_refine_total + matk_refine_total_L + MATK_Mweapon + MATK_MweaponL + refineovermatk_min + refineovermatk_L_min - refineovermatk - refineovermatk_L) * (1+(weaponR_Level*0.1)))
        else:
            MATK_Mweapon_ALL_min = MATKF + ((matk_refine_total + matk_refine_total_L + MATK_Mweapon + MATK_MweaponL + refineovermatk_min + refineovermatk_L_min - refineovermatk - refineovermatk_L) * (1-(weaponR_Level*0.1)))
        
        MATK_Mweapon_ALL = MATKF + ((matk_refine_total + matk_refine_total_L + MATK_Mweapon + MATK_MweaponL) * (1+(weaponR_Level*0.1)))
        #print(f"武器MATK:{MATK_Mweapon_ALL}")
        #裝備MATK+魔力增幅+武器MATK
        armorMATK_MAGICPOWER_min = int(MATK_Mweapon_ALL_min * (1+(SKILL_HW_MAGICPOWER*0.05)) + MATK_armor)
        armorMATK_MAGICPOWER = int(MATK_Mweapon_ALL * (1+(SKILL_HW_MAGICPOWER*0.05)) + MATK_armor)
        self.MATK_ALL = armorMATK_MAGICPOWER
        #print(f"裝備MATK+魔力增幅:{armorMATK_MAGICPOWER}")
        
        
        #======================取得技能欄公式======================    
        # === 取得技能等級輸入並設為全域
        text = self.skill_LV_input.text()
        globals()["Sklv"] = int(text) if text.lstrip('-').isdigit() else 0
        
        # === 取得使用者從 UI 下拉選單選擇的技能名稱
        #selected_skill_name = self.skill_box.currentText()#上面已經做過了
        #武器次數依照武器類型判斷
        skill_hits = self.skill_hits_input.text()#攻擊次數
        
        skill_hits = (replace_gusklv_calls(skill_hits))#替換使用技能參數
        expr = (replace_custom_calls(skill_hits))#替換武器類型

        def eval_hits(expr: str) -> int:
            # 某些技能 / 載入切換瞬間可能沒有 hits；預設視為 1 段，
            # 避免 eval("") 直接丟 SyntaxError，讓整個 JSON 比對/還原流程中斷。
            expr = str(expr or "").strip()
            if not expr:
                return 1

            # 只允許數字、四則、括號、小數點、空白、%（需要就留，不需要可拿掉）
            if not re.fullmatch(r"[0-9+\-*/().\s%]+", expr):
                raise ValueError(f"公式含不允許字元：{expr}")

            try:
                val = eval(expr, {"__builtins__": None}, {})  # 關掉 builtins
            except (SyntaxError, TypeError, ValueError, ZeroDivisionError) as exc:
                print(f"⚠️ 技能攻擊次數公式無法計算：{expr!r}，改用 1。原因：{exc}")
                return 1

            try:
                return int(val)  # 需要整數就轉 int（會截掉小數）
            except (TypeError, ValueError):
                return 1

       
        skill_hits = eval_hits(expr)#計算最終次數

        #print(f"技能攻擊次數: {skill_hits}")


        # [2] 根據種族選擇正確的公式，並同步 UI
        default_formula = str(skill_row["Calculation"]).strip()
        final_formula = default_formula
        globals()["SkillCode"] = str(skill_row["Code"]).strip()

        special_formula_ok = pd.notna(skill_row.get("Special_Calculation"))
        trigger_special = False
        trigger_skillbuff = False  # ✅ 新增：獨立記 skill_buff 是否命中

        # 先：種族判斷
        if special_formula_ok and pd.notna(skill_row.get("monster_race")):
            allowed_races = {r.strip() for r in str(skill_row["monster_race"]).split(",") if r.strip()}
            if str(target_race).strip() in allowed_races:
                trigger_special = True

        # 再：skill_buff 判斷
        if pd.notna(skill_row.get("skill_buff")):
            buff_ids = []
            for x in str(skill_row["skill_buff"]).split(","):
                x = x.strip()
                if x.isdigit():
                    buff_ids.append(int(x))

            if any(Use_skill_levels.get(bid, False) for bid in buff_ids):
                trigger_skillbuff = True
                # ✅ 原本特殊公式觸發規則照留：只有在 Special_Calculation 有資料時才會影響 trigger_special
                if special_formula_ok and (not trigger_special):
                    trigger_special = True   

        # 套用特殊公式
        if trigger_special and special_formula_ok:
            final_formula = str(skill_row["Special_Calculation"]).strip()

        # 爆擊傷害
        Critical_hit = float(replace_custom_calls(str(skill_row.get("Critical_hit")))) if pd.notna(skill_row.get("Critical_hit")) else 0.0

        # ✅ 新增：Special_Critical_hit 有資料 + skill_buff 命中 -> 取代 Critical_hit
        if trigger_skillbuff and pd.notna(skill_row.get("Special_Critical_hit")):
            Critical_hit = float(skill_row["Special_Critical_hit"])
        
        #天帝融合狀態
        if sg_mix == 0.5:
            Critical_hit = 0.5

        print(f"技能爆傷率：{Critical_hit}")


        # 同步更新 UI
        self.skill_formula_input.setText(final_formula)

        # [3] 最終使用使用者輸入
        user_input_formula = self.skill_formula_input.text().strip()
        if user_input_formula and user_input_formula != final_formula:
            formula_str = user_input_formula
        else:
            formula_str = final_formula

        def parse_hits(value, sklv):
            """
            解析 hits 或 combo_hits 欄位，支援負數與公式。
            範例： (Sklv/3)+4 會以整數除法處理為 (Sklv // 3) + 4
            """
            try:
                # 若為 int 或 float，直接轉
                if isinstance(value, (int, float)):
                    return int(value)

                # 去除空白後判斷是否為整數字串（包含負數）
                stripped = str(value).strip()
                if stripped.lstrip("-").isdigit():
                    return int(stripped)

                # 將 '/' 換成 '//' 確保整數除法
                safe_expr = stripped.replace("/", "//")

                # 建立 Symbol 並解析表達式
                Sklv = Symbol("Sklv")
                expr = sympify(safe_expr)
                result = expr.evalf(subs={Sklv: sklv}, chop=True)  # chop=True 可去除浮點誤差

                return int(result)
            except Exception as e:
                print(f"[⚠️ hits 解析錯誤] 原始值: {value}, 錯誤: {e}")
                return 1  # 預設安全值


        # === [4] 主段傷害計算（含多段與 bonus 加值設定）
        repeat_count = self.skill_hits_input.text()
        #武器次數依照武器類型判斷
        #repeat_count = int(replace_custom_calls(repeat_count))
        #print(f"repeat_count技能攻擊次數: {repeat_count}")
        bonus_add_raw = skill_row.get("bonus_add", "")
        if pd.isna(bonus_add_raw) or str(bonus_add_raw).strip() == "":
            bonus_add = 0
        else:
            bonus_add = str(bonus_add_raw).strip()

        bonus_step = float(skill_row["bonus_step"]) if pd.notna(skill_row.get("bonus_step")) else 0
        decay_hits = int(skill_row["decay_hits"]) if pd.notna(skill_row.get("decay_hits")) else 0 
        combo_element = int(skill_row["combo_elementg"]) if pd.notna(skill_row.get("combo_elementg")) else 0
        attack_type = str(skill_row.get("attack_type", "")).lower() if pd.notna(skill_row.get("attack_type")) else "physical"
        self.atktype = attack_type
        #技能遠傷判斷
        skill_Rangedamage = int(skill_row["Rangedamage"]) if pd.notna(skill_row.get("Rangedamage")) else 0 
        #技能遠傷判斷
        skill_delayed_Rangedamage = int(skill_row["Delayed_Rangedamage"]) if pd.notna(skill_row.get("Delayed_Rangedamage")) else 0 
        #技能砲彈ATK開關
        skill_cannon = int(skill_row["skill_cannon"]) if pd.notna(skill_row.get("skill_cannon")) else 0 
        #print(f"技能遠傷判斷: {skill_Rangedamage}")

        wpclass_skill_Rangedamage = skill_row.get("special_wprange", 0)

        # None / 空字串 / "nan" → 0
        if wpclass_skill_Rangedamage is None:
            wpclass_skill_Rangedamage = 0
        elif isinstance(wpclass_skill_Rangedamage, str):
            s = wpclass_skill_Rangedamage.strip()
            if s == "" or s.lower() == "nan":
                wpclass_skill_Rangedamage = 0
        else:
            # 數字型（含 numpy.float64）遇到 NaN → 0
            try:
                if math.isnan(float(wpclass_skill_Rangedamage)):
                    wpclass_skill_Rangedamage = 0
            except (TypeError, ValueError):
                pass

        #print(f"武器類型遠傷判斷代號: {wpclass_skill_Rangedamage}")

        allow = set()

        # 1) 單一數字：int / float（此時 NaN 已經被清成 0）
        if isinstance(wpclass_skill_Rangedamage, (int, float)):
            n = int(float(wpclass_skill_Rangedamage))
            if n != 0:
                allow.add(n)
        else:
            # 2) 多個數字字串： "1,5,6" / "8.0"
            for part in str(wpclass_skill_Rangedamage).split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    f = float(part)
                except ValueError:
                    continue
                if math.isnan(f):
                    continue
                if f.is_integer():
                    n = int(f)
                    if n != 0:
                        allow.add(n)


        # 最終判斷
        if weapon_class != 0 and weapon_class in allow:
            skill_Rangedamage = 1




        
        #print(f"攻擊模式：{attack_type}")
        

        
        # === CORE DEDUP PHASE 11: CORE-ONLY STAGE17 DAMAGE SEGMENTS ===
        # Core is now the only source for Stage17 damage/formula segment values.
        # Desktop keeps the existing legacy presenter below so text order/spacing stays unchanged.
        core_snapshot = self.refresh_core_stage17_snapshot()
        if core_snapshot is None:
            if render_output:
                self.skill_formula_result_input.setText("0%")
                error_text = self.last_core_damage_error or "Core Stage17 計算失敗"
                self.custom_calc_box.setPlainText(f"錯誤：{error_text}")
            return

        core_payload = core_snapshot.to_dict() if hasattr(core_snapshot, "to_dict") else dict(core_snapshot or {})
        results = [
            dict(item)
            for item in (core_payload.get("segments", []) or [])
            if isinstance(item, dict)
        ]
        raw_core_segments = [
            dict(item)
            for item in (core_payload.get("raw_segments", []) or [])
            if isinstance(item, dict)
        ]
        if not raw_core_segments:
            raw_core_segments = list(results)

        # Keep the original bottom formula section contract. raw_segments preserves
        # repeated/negative-hit formula rows even when display segments are normalized.
        bottom_result = []
        label_counts = {}
        for item in raw_core_segments:
            label_key = str(item.get("label", "main") or "main")
            label_counts[label_key] = label_counts.get(label_key, 0) + 1
        for item in raw_core_segments:
            label_key = str(item.get("label", "main") or "main")
            total_rounds = max(1, int(label_counts.get(label_key, 1) or 1))
            try:
                round_no = int(item.get("round", 1) or 1)
            except (TypeError, ValueError):
                round_no = 1
            formula_show = item.get("formula_expanded") or item.get("formula") or ""
            bottom_result.append(
                f"{pad_label('技能公式:')}[{round_no}/{total_rounds}] {formula_show}"
            )

        # Damage_view historically used the final legacy step list. Rebuild that list
        # from the final Core raw segment instead of recalculating damage in Desktop.
        self.steps = []
        step_source = raw_core_segments[-1] if raw_core_segments else (results[-1] if results else {})
        for step in (step_source.get("steps", []) or []):
            if not isinstance(step, dict):
                continue
            name = str(step.get("name", "") or "")
            value = step.get("value", 0)
            mode = step.get("mode")
            try:
                if mode == 1.4:
                    value = 40 + float(value)
            except (TypeError, ValueError):
                pass
            self.steps.append([name, value])

        core_monster = dict(core_payload.get("monster", {}) or {})
        try:
            self.steps.append(["綠光減傷%", float(core_monster.get("damage_multiplier_percent", 100) or 100)])
        except (TypeError, ValueError):
            pass
        try:
            betel_reduction = float(core_monster.get("betelgeuse_reduction_percent", 0) or 0)
            self.steps.append(["星座塔減傷%", 100 - betel_reduction])
        except (TypeError, ValueError):
            pass

        if results:
            if render_output:
                self.skill_formula_result_input.setText(f"{results[0]['skill_result']} %")
        else:
            if render_output:
                self.skill_formula_result_input.setText("0%")
                self.custom_calc_box.setPlainText("錯誤：無選擇職業、無技能公式、公式錯誤計算結果為0！")



         
        #=========================魔法各增傷計算顯示區=======================
        #print(f"前MATK: {MATKF} 後MATK:{MATKC} 武器MATK:{MATK_Mweapon} S.MATK:{total_SMATK}")  
        #print(f"打擊次數：{len(results)}")        
        result.append(f"{pad_label('使用技能:')}{selected_skill_name}")
        if not results:
            result.append("❌ 無法計算技能傷害，請檢查公式與變數")
            return

        # 預備總傷害合計
        all_total_damage_min = 0
        all_total_damage = 0

        if attack_type == "shield":            
            result.append(f"")
            result.append(f"{pad_label('護盾可抵擋傷害:')}{results[0]['skill_result']:,}")
            result.append(f"")
        else:
            # 判斷是否存在 combo 均分段（技能 times > 1 且每段是均分）
            combo_split_results = [r for r in results[1:] if r["times"] > 1 and r["damage_by_hit"] * r["times"] == r["total_damage"]]
            # === 情境：主技能 + combo 均分段 ===
            if len(results) > 1 and combo_split_results:
                # 顯示主技能段
                r = results[0]
                main_element_name = element_map.get(r["user_attack_element"], f"未知({r['user_attack_element']})")
                result.append(f"【{main_element_name}】==================主技能總傷害===========================")
                if Critical_hit > 0:#吃爆擊顯示最大值
                    result.append(f"單次傷害:     {r['damage_by_hit']:,}")
                    result.append(f"打擊次數:     {r['times']} 次")
                    result.append(f"主技能總傷害: {r['total_damage']:,}")
                else:
                    result.append(f"單次傷害:     {r['damage_by_hit_min']:,} ~ {r['damage_by_hit']:,}")
                    result.append(f"打擊次數:     {r['times']} 次")
                    result.append(f"主技能總傷害: {r['total_damage_min']:,} ~ {r['total_damage']:,}")
                all_total_damage_min += r['total_damage_min']
                all_total_damage += r['total_damage']

                # 顯示 combo 均分段（只取第一段為代表）
                r = combo_split_results[0]
                combo_main_element_name = element_map.get(r["user_attack_element"], f"未知({r['user_attack_element']})")
                combo_total_min = r["damage_by_hit_min"] * r["times"]
                combo_total = r["damage_by_hit"] * r["times"]
                result.append(f"【{combo_main_element_name}】===============COMBO 技能（均分）========================")
                if Critical_hit > 0:#吃爆擊顯示最大值
                    result.append(f"單次傷害(COMBO): {r['damage_by_hit']:,}")
                    result.append(f"打擊次數(COMBO): {r['times']} 次")
                    result.append(f"總傷害(COMBO):   {combo_total:,}")
                else:
                    result.append(f"單次傷害(COMBO): {r['damage_by_hit_min']:,} ~ {r['damage_by_hit']:,}")
                    result.append(f"打擊次數(COMBO): {r['times']} 次")
                    result.append(f"總傷害(COMBO):   {combo_total_min:,} ~ {combo_total:,}")
                all_total_damage_min += combo_total_min
                all_total_damage += combo_total

                # 顯示合計
                result.append(f" ")
                #result.append(f"============================總傷害合計=============================")
                if Critical_hit > 0:#吃爆擊顯示最大值
                    result.append(f"總傷害:  {all_total_damage:,}")
                else:
                    result.append(f"總傷害:  {all_total_damage_min:,} ~ {all_total_damage:,}")

            # === 正常多段技能（非均分）===
            elif len(results) > 1:
                result.append(f"【{element_map.get(User_attack_element, User_attack_element)}】===========以下總傷害數值（共 {len(results)} 次）====================")
                for idx, r in enumerate(results, start=1):
                    if Critical_hit > 0:#吃爆擊顯示最大值
                        result.append(f"第 {idx}/{len(results)} 次傷害: {r['total_damage']:,}")
                    else:
                        result.append(f"第 {idx}/{len(results)} 次傷害: {r['total_damage_min']:,} ~ {r['total_damage']:,}")
                    all_total_damage_min += r['total_damage_min']
                    all_total_damage += r['total_damage']
                    # result.append(f"------------------------------------------------------------------")
                if Critical_hit > 0:#吃爆擊顯示最大值
                    result.append(f"總傷害:  {all_total_damage:,}")
                else:
                    result.append(f"總傷害:  {all_total_damage_min:,} ~ {all_total_damage:,}")

            # === 單段技能 ===
            else:
                r = results[0]
                result.append(f"【{element_map.get(User_attack_element, User_attack_element)}】=================以下總傷害數值===========================")
                if Critical_hit > 0:#吃爆擊顯示最大值
                    result.append(f"單次傷害: {r['damage_by_hit']:,}")
                    result.append(f"打擊次數: {r['times']} 次")
                    result.append(f"總傷害:   {r['total_damage']:,}")
                else:
                    result.append(f"單次傷害: {r['damage_by_hit_min']:,} ~ {r['damage_by_hit']:,}")
                    result.append(f"打擊次數: {r['times']} 次")
                    result.append(f"總傷害:   {r['total_damage_min']:,} ~ {r['total_damage']:,}")

            # ✅ 加上 decay_hits 顯示處理
            decay_hits = int(skill_row["decay_hits"]) if pd.notna(skill_row.get("decay_hits")) else 0
            #print(f"遞增/減次數：{decay_hits}")
            if decay_hits > 1:
                avg_damage = int(all_total_damage / decay_hits)
                result.append(f"遞增/減段數: {decay_hits} 段")
                result.append(f"平均每段傷害: {avg_damage:,}")
                #result.append(f"總傷害:   {avg_damage * decay_hits:,}")

            if attack_type == "magic":
                self.def_label.setVisible(False)
                self.def_input.setVisible(False)
                self.defc_label.setVisible(False)
                self.defc_input.setVisible(False)
                self.res_label.setVisible(False)
                self.res_input.setVisible(False)
                self.mdef_label.setVisible(True)
                self.mdef_input.setVisible(True)
                self.mdefc_label.setVisible(True)
                self.mdefc_input.setVisible(True)
                self.mres_label.setVisible(True)
                self.mres_input.setVisible(True)
                result.append(f"=========================以下各增傷數值===========================")
                result.append(f"{pad_label('前MATK:')}{MATKF:,}")
                result.append(f"{pad_label('後MATK:')}{MATKC - refineovermatk - refineovermatk_L:,}")
                result.append(f"{pad_label('武器MATK:')}{MATK_Mweapon:,}")
                result.append(f"{pad_label('裝備MATK+魔力:')}{armorMATK_MAGICPOWER}")
                result.append(f"{pad_label('MATK%:')}{round(MATK_percent)}%")
                result.append(f"{pad_label('魔法體型:')}{round(get_effect_multiplier('MD_size', target_size))}%")
                result.append(f"{pad_label('魔法屬性敵人:')}{round(get_effect_multiplier('MD_element', target_element) + get_effect_multiplier('MD_element', 10))}%")
                result.append(f"{pad_label('屬性耐受性:')}{round((skill_wanzih4_buff + skill_poison_weak_buff + magic_poison_buff)*100)}%")
                result.append(f"{pad_label('屬性魔法:')}{round(get_effect_multiplier('MD_Damage', User_attack_element) + get_effect_multiplier('MD_Damage', 10))}%")
                result.append(f"{pad_label('魔法種族:')}{round(get_effect_multiplier('MD_Race', target_race) + get_effect_multiplier('MD_Race', 9999))}%")
                result.append(f"{pad_label('魔法階級:')}{round(get_effect_multiplier('MD_class', target_class))}%")
                result.append(f"{pad_label('魔物增傷:')}{round(target_monsterMDamage)}%")
                result.append(f"{pad_label('S.MATK:')}{round(total_SMATK)}")
                result.append(f"{pad_label('技能倍率:')}{results[0]['skill_result']}%")
                result.append(f"{pad_label('屬性倍率:')}{get_damage_multiplier(User_attack_element, target_element, target_element_lv)}%")
                result.append(f"{pad_label('後MDEF:')}{target_mdef}")
                result.append(f"{pad_label('無視魔法階級防禦:')}{round(get_effect_multiplier('MD_class_def', target_class))}%")
                result.append(f"{pad_label('無視魔法種族防禦:')}{round(get_effect_multiplier('MD_Race_def', target_race) + get_effect_multiplier('MD_Race_def', 9999))}%")
                result.append(f"{pad_label('魔法破防後傷害:')}{Mdamage_nomdef * 100:.2f}%")
                result.append(f"{pad_label('前MDEF:')}{target_mdefc}")
                result.append(f"{pad_label('MRES:')}{target_mres}")
                result.append(f"{pad_label('無視魔法抗性%:')}{mres_reduction}%")
                result.append(f"{pad_label('魔法破抗性後傷害:')}{Mdamage_nomres * 100:.2f}%")

            elif attack_type == "physical":
                self.def_label.setVisible(True)
                self.def_input.setVisible(True)
                self.defc_label.setVisible(True)
                self.defc_input.setVisible(True)
                self.res_label.setVisible(True)
                self.res_input.setVisible(True)
                self.mdef_label.setVisible(False)
                self.mdef_input.setVisible(False)
                self.mdefc_label.setVisible(False)
                self.mdefc_input.setVisible(False)
                self.mres_label.setVisible(False)
                self.mres_input.setVisible(False)
                result.append(f"=========================以下各增傷數值===========================")
                if weapon_class in (11,13,14,17,18,19,20,21):#DEX系
                    result.append(f"{pad_label('前ATK (DEX系):')}{FATK:,}")
                    result.append(f"{pad_label('後ATK (DEX系):')}{AKTC + KamuiATK + atk_refine_total_L + ATK_MweaponL:,}")
                else:#STR系
                    result.append(f"{pad_label('前ATK(STR系):')}{NATK:,}")
                    result.append(f"{pad_label('後ATK(STR系):')}{AKTC + KamuiATK + atk_refine_total_L + ATK_MweaponL - refineoveratk:,}")
                result.append(f"{pad_label('武器ATK:')}{ATK_Mweapon:,}")
                result.append(f"{pad_label('修煉ATK:')}{WeaponMasteryATK:,}")
                result.append(f"{pad_label('物理ATK%:')}{round(ATK_percent)}%")
                result.append(f"{pad_label('物理體型:')}{round(get_effect_multiplier('D_size', target_size))}%")
                result.append(f"{pad_label('物理種族:')}{round(get_effect_multiplier('D_Race', target_race) + get_effect_multiplier('D_Race', 9999))}%")
                result.append(f"{pad_label('物理階級:')}{round(get_effect_multiplier('D_class', target_class))}%")
                result.append(f"{pad_label('魔物增傷:')}{round(target_monsterDamage)}%")
                result.append(f"{pad_label('P.ATK:')}{round(total_PATK)}")
                result.append(f"{pad_label('物理屬性敵人:')}{round(get_effect_multiplier('D_element', target_element) + get_effect_multiplier('D_element', 10))}%")
                result.append(f"{pad_label('物理命中:')}{round(Damage_HIT)}%")
                result.append(f"{pad_label('爆傷:')}{round(Damage_CRI)}%")

                if skill_Rangedamage == 1:#遠傷判斷
                    if weapon_class == 11:
                        result.append(f"{pad_label('遠傷:')}{round(RangeAttackDamage + BowAtk)}%")
                    else:
                        result.append(f"{pad_label('遠傷:')}{round(RangeAttackDamage)}%")
                
                else:
                    result.append(f"{pad_label('近傷:')}{round(MeleeAttackDamage)}%")

                result.append(f"{pad_label('CRATE:')}{round(total_CRATE)}")
                result.append(f"{pad_label('技能倍率:')}{results[0]['skill_result']}%")
                result.append(f"{pad_label('屬性倍率:')}{get_damage_multiplier(User_attack_element, target_element, target_element_lv)}%")
                result.append(f"{pad_label('武器體型修正:')}{Weaponpunish*100}%")
                result.append(f"{pad_label('後DEF:')}{target_def}")
                result.append(f"{pad_label('無視階級防禦:')}{round(get_effect_multiplier('D_class_def', target_class))}%")
                result.append(f"{pad_label('無視種族防禦:')}{round(get_effect_multiplier('D_Race_def', target_race) + get_effect_multiplier('D_Race_def', 9999))}%")
                result.append(f"{pad_label('物理破防後傷害:')}{damage_nodef * 100:.2f}%")
                result.append(f"{pad_label('前DEF:')}{target_defc}")
                result.append(f"{pad_label('RES:')}{target_res}")
                result.append(f"{pad_label('無視物理抗性%:')}{res_reduction}%")
                result.append(f"{pad_label('物理破抗性後傷害:')}{damage_nores * 100:.2f}%")

            elif attack_type == "d_b":
                self.def_label.setVisible(True)
                self.def_input.setVisible(True)
                self.defc_label.setVisible(True)
                self.defc_input.setVisible(True)
                self.res_label.setVisible(True)
                self.res_input.setVisible(True)
                self.mdef_label.setVisible(False)
                self.mdef_input.setVisible(False)
                self.mdefc_label.setVisible(False)
                self.mdefc_input.setVisible(False)
                self.mres_label.setVisible(False)
                self.mres_input.setVisible(False)
                result.append(f"=========================以下各增傷數值===========================")

                if weapon_class == 11:
                    result.append(f"{pad_label('遠傷:')}{round(RangeAttackDamage + BowAtk)}%")
                else:
                    result.append(f"{pad_label('遠傷:')}{round(RangeAttackDamage)}%")
                #屬性耐性 龍之氣息 預設屬性火，可使用盧恩石轉屬，轉屬後一樣看火屬耐性(屬性*火耐性)
                #屬性耐性 龍之氣息-水 預設屬性水，可使用盧恩石轉屬，轉屬後一樣看水屬耐性(屬性*水耐性)
                result.append(f"{pad_label('技能倍率:')}{results[0]['skill_result']}%")
                result.append(f"{pad_label('屬性倍率:')}{get_damage_multiplier(User_attack_element, target_element, target_element_lv)}%")

            else:
                raise ValueError(f"未知的攻擊類型: {attack_type}")
            
                        
            result.append(f"{pad_label('技能增傷(裝備段):')}{round(Use_Skills)}%")
            result.append(f"{pad_label('技能增傷(技能段):')}{round(passive_skill_buff)}%")
            result.append(f"==================================================================")
            result.append(f"{pad_label('技能等級:')}{Sklv}")
            #result.append(f"{pad_label('技能公式:')}{results[0]['formula']}")
        
            if len(results) > 1 and combo_split_results:
                self.steps.append(["打擊虛數", (1/r["times"])*100])
                self.steps.append(["總傷害", r["times"]*100])
            elif len(results) > 1:
                #self.steps.append(("總傷害", r["times"]))
                pass
            else:
                self.steps.append(["打擊虛數", (1/r["times"])*100])
                self.steps.append(["總傷害", r["times"]*100])

        result.extend(bottom_result)#顯示前面儲存的公式
        if render_output:
            # 連續比較時先在記憶體產生比較結果，最後只更新 custom_calc_box 一次。
            final_output = result
            if self.auto_compare_checkbox.isChecked():
                compared_output = self.compare_with_base(
                    current_lines=result,
                    render=False,
                )
                if compared_output is not None:
                    final_output = compared_output

            self.custom_calc_box.setHtml(
                self.generate_highlighted_html(final_output)
            )

        # 減傷顯示：Qt 只負責取得防具精煉輸入，角色防禦/減傷公式集中到 Core。
        if Subweapon_class == 0:
            armor_result = self.get_total_armor_bonus(
                global_armor_level_map,
                exclude_slots={4,110,30,31,32,33,34,35,41,42,43,44,100,101,102},
            )
        else:
            armor_result = self.get_total_armor_bonus(
                global_armor_level_map,
                exclude_slots={4,3,110,30,31,32,33,34,35,41,42,43,44,100,101,102},
            )

        body_profile = core_calculate_character_defense_profile(
            effect_dict=effect_dict,
            base_level=base_lv,
            total_agi=total_AGI,
            total_vit=total_VIT,
            total_dex=total_DEX,
            total_int=total_INT,
            total_sta=total_STA,
            total_wis=total_WIS,
            armor_def=armor_result["DEF"],
            armor_res=armor_result["RES"],
            target_size=target_size,
            target_element=target_element,
            target_race=target_race,
            target_class=target_class,
            monster_attack_element=monster_attack_element,
        )
        self.last_core_character_defense = body_profile
        body_size_phys = body_profile["body_size_phys"]
        body_size_phys_m = body_profile["body_size_magic"]
        body_element_phys = body_profile["body_element_phys"]
        body_element_phys_m = body_profile["body_element_magic"]
        body_race_phys = body_profile["body_race_phys"]
        body_class_phys = body_profile["body_class_phys"]
        body_class_phys_m = body_profile["body_class_magic"]
        body_attr_resist = body_profile["body_attr_resist"]
        body_melee_phys = body_profile["body_melee_phys"]
        body_range_phys = body_profile["body_range_phys"]
        body_DEF = body_profile["body_def"]
        body_MDEF = body_profile["body_mdef"]
        body_RES = body_profile["body_res"]
        body_MRES = body_profile["body_mres"]
        f_def = body_profile["front_def"]
        c_def = body_profile["after_def"]
        f_mdef = body_profile["front_mdef"]
        stat_res = body_profile["stat_res"]
        stat_mres = body_profile["stat_mres"]
        total_res = body_profile["total_res"]
        total_mres = body_profile["total_mres"]
        c_atktotal = body_profile["back_physical_multiplier"]
        fc_melee_akttotal = body_profile["full_melee_multiplier"]
        fc_range_akttotal = body_profile["full_range_multiplier"]
        fc_magic_akttotal = body_profile["full_magic_multiplier"]

        body_results = []
        # body_results.append(f"===========================減傷顯示===========================")
        # body_results.append(f"{pad_label('體型:')}{size_map.get(target_size, target_size)}")
        # body_results.append(f"{pad_label('屬性:')}{element_map.get(target_element, target_element)} Lv{target_element_lv}")
        # body_results.append(f"{pad_label('種族:')}{race_map.get(target_race, target_race)}")
        # body_results.append(f"{pad_label('階級:')}{class_map.get(target_class, target_class)}")
        # body_results.append(f"==================================================================")
        body_results.append(f"===========================怪物能力===========================")
        body_results.append(f"{pad_label('ATK:')}{self.monster_f_atk} + {self.monster_c_atk}")
        body_results.append(f"{pad_label('MATK:')}{self.monster_f_matk} + {self.monster_c_matk}")
        # body_results.append(f"===========================計算===========================")
        # excelmfatk = (int(self.monster_f_atk) * (fc_melee_akttotal))
        # excelrfatk = (int(self.monster_f_atk) * (fc_range_akttotal))
        # excelcatk = (int(self.monster_c_atk) * (c_atktotal))
        # body_results.append(f"前ATK(近) = {self.monster_f_atk} * {fc_melee_akttotal*100:.0f} = {excelmfatk:.0f}")
        # body_results.append(f"前ATK(遠) = {self.monster_f_atk} * {fc_range_akttotal*100:.0f} = {excelrfatk:.0f}")
        # body_results.append(f"後ATK     = {self.monster_c_atk} * {c_atktotal*100:.0f} = {excelcatk:.0f}")
        body_results.append(f"===========================角色防禦===========================")
        body_results.append(f"{pad_label('DEF:')}{f_def} + {c_def}")
        body_results.append(f"{pad_label('MDEF:')}{f_mdef} + {body_MDEF}")
        body_results.append(f"{pad_label('RES:')}{total_res}")
        body_results.append(f"{pad_label('MRES:')}{total_mres}")
        body_results.append(f"=========================後段物理減傷=========================")
        body_results.append(f"{pad_label('受到體型物理傷害:')}{body_size_phys:.0f}%")
        body_results.append(f"{pad_label('受到屬性對象物理傷害:')}{body_element_phys:.0f}%")
        body_results.append(f"{pad_label('受到階級物理傷害:')}{body_class_phys:.0f}%")
        body_results.append(f"{pad_label('屬性物理攻擊傷害抗性:')}{body_attr_resist:.0f}%")
        body_results.append(f"總計：")
        body_results.append(f"{pad_label('　後段物理減免後傷害:')}{c_atktotal*100:.0f}% (數字越少傷害越低。)")
        body_results.append(f"=========================全段物理減傷=========================")
        body_results.append(f"{pad_label('受到種族物理傷害:')}{body_race_phys:.0f}%")
        body_results.append(f"{pad_label('受到近距離物理傷害:')}{body_melee_phys:.0f}%")
        body_results.append(f"{pad_label('受到遠距離物理傷害:')}{body_range_phys:.0f}%")        
        body_results.append(f"{pad_label('RES計算倍率:')}{body_profile['res_multiplier']*100:.2f}%")
        body_results.append(f"{pad_label('DEF計算倍率:')}{body_profile['def_multiplier']*100:.2f}%")
        body_results.append(f"總計：")
        body_results.append(f"{pad_label('　全段(近)減免後傷害:')}{fc_melee_akttotal*100:.0f}% (數字越少傷害越低。)")
        body_results.append(f"{pad_label('　全段(遠)減免後傷害:')}{fc_range_akttotal*100:.0f}% (數字越少傷害越低。)")
        body_results.append(f"=========================全段魔法減傷=========================")        
        body_results.append(f"{pad_label('受到種族魔法傷害:')}{body_race_phys:.0f}%")
        body_results.append(f"{pad_label('受到體型魔法傷害:')}{body_size_phys_m:.0f}%")
        body_results.append(f"{pad_label('受到屬性對象魔法傷害:')}{body_element_phys_m:.0f}%")
        body_results.append(f"{pad_label('受到階級魔法傷害:')}{body_class_phys_m:.0f}%")
        body_results.append(f"{pad_label('屬性魔法攻擊傷害抗性:')}{body_attr_resist:.0f}%")
        body_results.append(f"{pad_label('MRES計算倍率:')}{body_profile['mres_multiplier']*100:.2f}%")
        body_results.append(f"{pad_label('MDEF計算倍率:')}{body_profile['mdef_multiplier']*100:.2f}%")    
        body_results.append(f"總計：")    
        body_results.append(f"{pad_label('　魔法減免後傷害:')}{fc_magic_akttotal*100:.0f}% (數字越少傷害越低。)")



        if render_output:
            self.body_custom_calc_box.setHtml(
                self.generate_highlighted_html(body_results)
            )

        # Phase 11: Stage17 damage is Core-only; Desktop still owns text presentation.
        if render_output:
            self.last_core_damage_parity = {
                "ok": True,
                "mode": "core-only",
                "mismatches": [],
                "core_count": len(results),
                "core_total_damage_min": core_payload.get("total_damage_min", 0),
                "core_total_damage": core_payload.get("total_damage", 0),
            }
            self.stage17_core_parity_ok = True
            # Compatibility flag: Core owns values, not Desktop text rendering.
            self.stage17_core_render_active = False
            self.last_core_damage_error = None

    def _set_combo_data_blocked(self, combo, data):
        idx = combo.findData(data)
        if idx < 0:
            return
        old_state = combo.blockSignals(True)
        try:
            combo.setCurrentIndex(idx)
        finally:
            combo.blockSignals(old_state)

    def _set_line_text_blocked(self, line_edit, text):
        old_state = line_edit.blockSignals(True)
        try:
            line_edit.setText(str(text))
        finally:
            line_edit.blockSignals(old_state)

    def _sync_target_fields(self, source_prefix: str, target_prefix: str):
        if getattr(self, "_syncing_target_fields", False):
            return

        combo_pairs = [
            (f"{source_prefix}size_box", f"{target_prefix}size_box"),
            (f"{source_prefix}element_box", f"{target_prefix}element_box"),
            (f"{source_prefix}race_box", f"{target_prefix}race_box"),
            (f"{source_prefix}class_box", f"{target_prefix}class_box"),
        ]
        line_pairs = [
            (f"{source_prefix}element_lv_input", f"{target_prefix}element_lv_input"),
        ]

        names = [name for pair in combo_pairs + line_pairs for name in pair]
        if not all(hasattr(self, name) for name in names):
            return

        self._syncing_target_fields = True
        try:
            for src_name, dst_name in combo_pairs:
                self._set_combo_data_blocked(getattr(self, dst_name), getattr(self, src_name).currentData())
            for src_name, dst_name in line_pairs:
                self._set_line_text_blocked(getattr(self, dst_name), getattr(self, src_name).text())
        finally:
            self._syncing_target_fields = False

    def _sync_damage_to_body_target_fields(self):
        self._sync_target_fields("", "body_")

    def _sync_body_to_damage_target_fields(self):
        self._sync_target_fields("body_", "")

    def _on_damage_target_fields_changed(self):
        self._sync_damage_to_body_target_fields()
        setattr(self, "_last_calc_state", None)
        self.trigger_total_effect_update()

    def _on_body_target_fields_changed(self):
        self._sync_body_to_damage_target_fields()
        setattr(self, "_last_calc_state", None)
        self.trigger_total_effect_update()


    def _config_path(self):
        return get_config_path()

    def load_config(self):
        self.update_mode = "online_only"
        self.api_key = ""
        self.ui_scale_factor = DEFAULT_UI_SCALE_FACTOR
        self.load_kro_equipment_data = False

        cfg = load_config_data()
        self.update_mode = cfg.get("update_mode", self.update_mode)
        self.api_key = cfg.get("api_key", self.api_key)
        self.ui_scale_factor = normalize_ui_scale_factor(
            cfg.get("ui_scale_factor", self.ui_scale_factor)
        )

        kro_setting = cfg.get(
            "load_kro_equipment_data", self.load_kro_equipment_data
        )
        if isinstance(kro_setting, str):
            self.load_kro_equipment_data = kro_setting.strip().lower() in (
                "1", "true", "yes", "on"
            )
        else:
            self.load_kro_equipment_data = bool(kro_setting)

    def save_config(self):
        cfg = {
            "update_mode": getattr(self, "update_mode", "online_only"),
            "api_key": getattr(self, "api_key", ""),
            "ui_scale_factor": normalize_ui_scale_factor(
                getattr(self, "ui_scale_factor", DEFAULT_UI_SCALE_FACTOR)
            ),
            "load_kro_equipment_data": bool(
                getattr(self, "load_kro_equipment_data", False)
            ),
        }
        try:
            with open(self._config_path(), "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"儲存設定失敗：{e}")


    def get_update_mode(self) -> str:
        if not hasattr(self, "update_mode"):
            self.load_config()
        return self.update_mode or "online_only"

    def should_load_kro_equipment_data(self) -> bool:
        if not hasattr(self, "load_kro_equipment_data"):
            self.load_config()
        return bool(self.load_kro_equipment_data)


    def open_compile_set(self):
        self.load_config()
        previous_ui_scale = normalize_ui_scale_factor(
            getattr(self, "ui_scale_factor", DEFAULT_UI_SCALE_FACTOR)
        )
        previous_load_kro = self.should_load_kro_equipment_data()
        dlg = PreferencesDialog(
            current_mode=self.update_mode,
            current_api_key=getattr(self, "api_key", ""),
            current_ui_scale=previous_ui_scale,
            current_load_kro_data=previous_load_kro,
            parent=self
        )
        if dlg.exec() == QDialog.Accepted:
            self.update_mode = dlg.selected_mode()
            self.api_key = dlg.api_key()
            self.ui_scale_factor = dlg.selected_ui_scale()
            self.load_kro_equipment_data = dlg.should_load_kro_data()
            self.save_config()

            restart_messages = []
            if self.ui_scale_factor != previous_ui_scale:
                restart_messages.append(
                    tr(
                        "message.ui_scale_restart_required",
                        "介面縮放已儲存，請重新啟動程式以套用新倍率。",
                    )
                )
            if self.load_kro_equipment_data != previous_load_kro:
                restart_messages.append(
                    tr(
                        "message.kro_data_restart_required",
                        "KRO 裝備資料設定已儲存，請重新啟動程式以套用。",
                    )
                )

            if restart_messages:
                QMessageBox.information(
                    self,
                    tr("window.preferences"),
                    "\n".join(restart_messages),
                )



    def generate_highlighted_html(self, lines: list[str]) -> str:
        app = QApplication.instance()        
        if not app:
            raise RuntimeError("QApplication 尚未建立")

        palette = app.palette()
        window_color: QColor = palette.color(QPalette.Window)
        text_color: QColor = palette.color(QPalette.WindowText)

        # 根據亮度判斷主題
        # 若背景偏暗（亮度 < 128），則視為暗色模式
        brightness = (window_color.red() * 0.299 + window_color.green() * 0.587 + window_color.blue() * 0.114)
        dark_mode = brightness < 128

        if dark_mode:
            odd_color = "#FFFFFF"   # 白字
            even_color = "#AAAAAA"  # 灰字
        else:
            odd_color = "#000000"   # 黑字
            even_color = "#555555"  # 深灰字

        html_lines = []
        for i, line in enumerate(lines):
            color = even_color if i % 2 else odd_color
            html_lines.append(f'<span style="color:{color};">{line}</span>')

        html_result = (
            "<pre style='font-family: MingLiU; font-size: 11pt;'>\n"
            + "\n".join(html_lines)
            + "\n</pre>"
        )

        return html_result


        
    def apply_effect_mapping(self, effect_dict, prefix, names, key_template, index_override=None):
        for i, name in enumerate(names):
            idx = index_override[i] if index_override else i
            key = (key_template.format(name), "%")
            value = sum(val for val, _ in effect_dict.get(key, []))
            setattr(self, f"{prefix}_{idx}", value)

    def apply_body_effect_mapping(self, effect_dict, prefix, names, key_template, index_override=None):
        for i, name in enumerate(names):
            idx = index_override[i] if index_override else i
            key = (key_template.format(name), "%")
            value = sum(val for val, _ in effect_dict.get(key, []))
            setattr(self, f"body_{prefix}_{idx}", value)

    def apply_all_damage_effects(self, effect_dict):
        # Phase 4+5: mapping rules live in Core; keep legacy attributes for callers/UI.
        profile = core_build_damage_effect_profile(effect_dict)
        self.damage_effect_profile = profile
        for attr_name, value in profile["legacy_attributes"].items():
            setattr(self, attr_name, value)
        return profile

    def calc_weapon_refine_matk(self, weapon_Level, weaponRefineR, weaponGradeR):
        return _core_stage17_calc_weapon_refine_matk(weapon_Level, weaponRefineR, weaponGradeR)
        
    def calc_weapon_refine_atk(self, weapon_Level, weaponRefineR, weaponGradeR):
        return _core_stage17_calc_weapon_refine_atk(weapon_Level, weaponRefineR, weaponGradeR)

    def get_armor_bonus(self, refine: int, armor_level: int) -> dict:
        """Desktop compatibility wrapper; formula is owned by ro_core."""
        return core_calculate_armor_refine_bonus(refine, armor_level)

    def get_total_armor_bonus(
        self,
        armor_level_map: dict,
        exclude_parts=None,
        exclude_slots=None,
        exclude_types=None,
    ) -> dict:
        """從 UI 讀取所有部位精煉值，並加總防具精煉 DEF、RES。"""

        exclude_parts = set(exclude_parts or ())
        exclude_slots = set(exclude_slots or ())
        exclude_types = set(exclude_types or ())

        total_def = 0.0
        total_res = 0
        details = {}

        # 關鍵修正：slot/type 要從 refine_parts 取得
        for part_name, part_info in refine_parts.items():
            slot = part_info.get("slot")
            part_type = part_info.get("type")

            if part_name in exclude_parts:
                continue

            if slot in exclude_slots:
                continue

            if part_type in exclude_types:
                continue

            ui_data = self.refine_inputs_ui.get(part_name)
            if not ui_data:
                continue

            # 沒穿裝備時不計算
            equip_widget = ui_data.get("equip")
            if equip_widget is not None:
                if not equip_widget.text().strip():
                    continue

            refine_widget = ui_data.get("refine")
            if refine_widget is None:
                continue

            refine_text = refine_widget.text().strip()

            try:
                refine = int(refine_text or 0)
            except ValueError as exc:
                raise ValueError(
                    f"{part_name} 的精煉值格式錯誤：{refine_text!r}"
                ) from exc

            # 同時相容 int key 與 str key
            armor_level_raw = armor_level_map.get(
                slot,
                armor_level_map.get(str(slot), 0),
            )

            try:
                armor_level = int(armor_level_raw or 0)
            except (TypeError, ValueError):
                armor_level = 0

            if armor_level not in (1, 2):
                continue

            bonus = self.get_armor_bonus(
                refine=refine,
                armor_level=armor_level,
            )

            total_def += bonus["DEF"]
            total_res += bonus["RES"]

            details[part_name] = {
                "slot": slot,
                "type": part_type,
                "refine": refine,
                "armor_level": armor_level,
                "DEF": bonus["DEF"],
                "RES": bonus["RES"],
            }

        return {
            "DEF": round(total_def, 1),
            "RES": int(total_res),
            "details": details,
        }

    def update_note_widget_with_delay(self, widget: QTextEdit, text: str):
        widget.setPlainText(text)

        def adjust():
            # ✅ 強制文字寬度套入 layout
            widget.document().setTextWidth(widget.viewport().width())
            self.adjust_textedit_height(widget)

        # 雙層 QTimer 保證 Qt 已繪製完畢
        QTimer.singleShot(0, lambda: QTimer.singleShot(0, adjust))

    def adjust_textedit_height(self, text_edit: QTextEdit):
        doc = text_edit.document()

        # 🔧 強制 layout
        doc.setTextWidth(text_edit.viewport().width())
        doc.adjustSize()  # 👈 這個是 Qt layout 關鍵

        text_edit.updateGeometry()
        text_edit.update()

        # 重新取得 layout 後的尺寸
        line_count = doc.blockCount()
        doc_size = doc.size().toSize()

        #print(f"📝 [{text_edit.objectName()}] 目前行數：{line_count}")
        #print(f"📐 Document size: {doc_size.width()} x {doc_size.height()}")

        margin = 3
        min_height = 27
        max_height = 400
        new_height = max(min_height, min(doc_size.height() + margin, max_height))

        #print(f"🪄 設定高度為：{new_height}")
        text_edit.setFixedHeight(new_height)



    def on_function_text_changed(self):
        
        sender = self.sender()  # 取得是哪個 QTextEdit 被改了
        if not sender:
            return

        object_name = sender.objectName()  # 例如 "頭上-函數"
        if not object_name.endswith("-函數"):
            return

        part_name = object_name.replace("-函數", "")
        lua_code = sender.toPlainText()

        #print(f"🔍 偵測到 {object_name} 變動，內容：\n{lua_code}")

        try:
            results = parse_lua_effects_with_variables(
                block_text=lua_code,
                refine_inputs={},
                get_values={},
                grade=0,
                unit_map=unit_map,
                size_map=size_map,
                effect_map=effect_map,
                hide_unrecognized=False
            )
            output = "\n".join(results)
        except Exception as e:
            output = f"⚠️ 錯誤：{e}"

        # 尋找對應的 詞條 欄位，名稱是 part_name-詞條
        target_name = f"{part_name}-詞條"
        for v in self.refine_inputs_ui.values():
            if v.get("note_ui") and v["note_ui"].objectName() == target_name:
                v["note_ui"].setPlainText(output)
                QTimer.singleShot(0, lambda w=v["note_ui"]: self.adjust_textedit_height(w))
                break
        

    def handle_note_text_clicked(self, event, part_name, text_widget_ui ,text_widget):
        '''
        處理詞條文字被點擊的事件
        '''
        self.clear_current_edit()
        self.current_edit_part = f"{part_name} - 詞條"
        self.current_edit_widget = text_widget
        self.current_edit_label.setText(tr("label.current_part_value", value=self.current_edit_part))
        print(f"目前部位：{self.current_edit_part}")
        self.unsync_button.setVisible(True)
        self.apply_to_note_button.setVisible(True)
        self.clear_field_button2.setVisible(True)
        self.unsync_button2.setVisible(True)
        self.apply_equip_button.setVisible(True)
        self.clear_field_button.setVisible(True)

        self.set_edit_lock(part_name, "note")
        for v in self.refine_inputs_ui.values():
            if "note" in v:
                v["note"].setStyleSheet("")
        text_widget_ui.setStyleSheet("background-color: #ff0000;")

        self.result_output.setPlainText(text_widget.toPlainText())
        self.tab_widget.setCurrentIndex(self.function_tab_index)

        QTextEdit.mousePressEvent(text_widget, event)  # 保留原始點擊事件行為


    def update_function_autocomplete_maps(self):
        """同步下方語法輸入框的 map 補完資料，包含技能清單。"""
        if not hasattr(self, "result_output") or not hasattr(self.result_output, "set_map_registry"):
            return
        self.result_output.set_map_registry({
            "equip_sitetype": equip_sitetype,
            "stat_fields": stat_fields,
            "skill_map": skill_map,
            "skill_map_all": skill_map_all,
            "effect_map": effect_map,
            "element_map": element_map,
            "size_map": size_map,
            "race_map": race_map,
            "unit_map": unit_map,
            "class_map": class_map,
            "weapon_type_map": weapon_type_map,
        })

    def update_function_selector(self):
        self.function_selector.clear()
        for func_name, spec in function_defs.items():
            label = spec.get("desc", func_name)  # 顯示用中文描述
            self.function_selector.addItem(label, func_name)

        # 同步刷新下方語法輸入框的函數補完與 map 參數補完清單
        if hasattr(self, "result_output") and hasattr(self.result_output, "set_function_defs"):
            self.result_output.set_function_defs(function_defs)
            self.update_function_autocomplete_maps()

        if self.function_selector.count() > 0:
            self.function_selector.setCurrentIndex(0)
            self.on_function_changed()

            
    def on_tab_changed(self, index):
        if index == self.function_tab_index:
            self.update_function_selector()
            self.update_all_notes_from_functions()  # ⬅️ 加這一行

        self.tab_widget.adjustSize()

        QTimer.singleShot(50, lambda: (
            self.tab_widget.repaint(),
        ))

    def update_all_notes_from_functions(self):
        for part_name, widgets in self.refine_inputs_ui.items():
            function_widget = widgets.get("function")
            note_widget = widgets.get("note_ui")
            if not function_widget or not note_widget:
                continue

            lua_code = function_widget.toPlainText()

            try:
                results = parse_lua_effects_with_variables(
                    block_text=lua_code,
                    refine_inputs={},
                    get_values={},
                    grade=0,
                    unit_map=unit_map,
                    size_map=size_map,
                    effect_map=effect_map,
                    hide_unrecognized=False
                )
                output = "\n".join(results)
            except Exception as e:
                output = f"⚠️ 錯誤：{e}"

            self.update_note_widget_with_delay(note_widget, output)


    def clear_global_state(self):#清除全域武器裝備技能等級並預先匯入基礎值
        '''
        清除全域武器裝備技能等級並預先匯入基礎值
        '''
        #print("武器階級：", global_weapon_level_map)
        #print("防具階級：", global_armor_level_map)
        #print("武器類型：", global_weapon_type_map)
        #print("技能：", enabled_skill_levels)
        global_weapon_level_map.clear()
        global_armor_weapon_map.clear()
        global_armor_level_map.clear()
        global_weapon_type_map.clear()
        global_weapon_matk_map.clear()
        global_weapon_atk_map.clear()
        
        
        enabled_skill_levels.clear()
        Use_skill_levels.clear()
       # 你目前已知使用的 slot ID 範圍
        slot_ids = [10, 11, 12, 2, 4, 3, 5, 6, 7, 8,
                    30, 31, 32, 33, 34, 35, 41, 42, 43, 44]

        for slot in slot_ids:
            global_weapon_level_map[slot] = 0
            global_armor_weapon_map[slot] = 0
            global_armor_level_map[slot] = 0
            global_weapon_type_map[slot] = 0
            global_weapon_matk_map[slot] = 0
            global_weapon_atk_map[slot] = 0
        #self.update_combobox()

        #self.display_item_info()
        #self.display_all_effects()
        #self.update_all_notes_from_functions
        #self.replace_custom_calc_content
        #self.on_function_text_changed
        #print("清除完畢：============================")
        #print("武器階級：", global_weapon_level_map)
        #print("防具階級：", global_armor_level_map)
        #print("武器類型：", global_weapon_type_map)
        #print("技能：", enabled_skill_levels)

    def update_dex_int_half_note(self):#素質無詠計算
        """Stage 21.25: Desktop UI wrapper over shared ro_core no-cast Core."""
        raw_effects = getattr(self, "effect_dict_raw", {})
        try:
            base_dex = int(self.input_fields["DEX"].text())
        except Exception:
            base_dex = 0
        try:
            base_int = int(self.input_fields["INT"].text())
        except Exception:
            base_int = 0
        job_id = self.input_fields["JOB"].currentData()
        tjob_bonus = job_dict.get(job_id, {}).get("TJobMaxPoint", [])
        shared = _core_stage25_calculate_no_cast_from_effects(
            base_dex=base_dex,
            base_int=base_int,
            job_bonus=tjob_bonus,
            effect_dict=raw_effects,
        )
        gap = int(shared["gap"])
        status = "✅" if shared["reached"] else "⚠️ 未達標"
        if shared["reached"]:
            diff_text = f"　（超過：DEX {gap} 或 INT {gap * 2}）"
        else:
            diff_text = f"　（還差：DEX +{shared['needed_dex']} 或 INT +{shared['needed_int']}）"
        self.DEX_INT_265_label.setText(
            f"※素質無詠 {shared['dex_part']} + {shared['int_part']} = {shared['score']} {status}\n{diff_text}"
        )



    def calc_aspd(self,#攻速計算
        wpasdp_data: dict,
        job_id: int,
        agi: float,
        dex: float,
        *,
        # 一般模式用
        weapon_type: int | None = None,
        has_shield: bool = False,

        # 雙刀模式用
        dual_wield: bool = False,
        right_weapon_type: int | None = None,
        left_weapon_type: int | None = None,

        # 類別加成（rate 可傳 0.15 或 15 都可）
        cat1_rate: float = 0.0,
        cat1_flat: float = 0.0,
        cat2_rate: float = 0.0,
        cat2_flat: float = 0.0,

        # 最後四捨五入位數
        round_digits: int = 3,
    ) -> float:
        return _core_stage20_calc_aspd(
            wpasdp_data,
            job_id=job_id,
            agi=agi,
            dex=dex,
            weapon_type=weapon_type,
            has_shield=has_shield,
            dual_wield=dual_wield,
            right_weapon_type=right_weapon_type,
            left_weapon_type=left_weapon_type,
            cat1_rate=cat1_rate,
            cat1_flat=cat1_flat,
            cat2_rate=cat2_rate,
            cat2_flat=cat2_flat,
            round_digits=round_digits,
        )


    def safe_update_textbox(self, textbox, text):
        if textbox.toPlainText() == text:
            return

        scrollbar = textbox.verticalScrollBar()
        scroll_pos = scrollbar.value()

        textbox.setPlainText(text)

        scrollbar.setValue(scroll_pos)

    def toggle_equip_text_visibility(self):
        hidden = self.hide_unrecognized_checkbox.isChecked()
        self.equip_text.setVisible(not hidden)
        self.equip_text_label.setVisible(not hidden)
        self.combi_raw_text.setVisible(not hidden)
        
    def filter_effects(self, effects: list[str]) -> list[str]:
        return core_filter_effects(
            effects,
            hide_unrecognized=self.hide_unrecognized_checkbox.isChecked(),
            hide_physical=self.hide_physical_checkbox.isChecked(),
            hide_magical=self.hide_magical_checkbox.isChecked(),
        )
    
    def update_skill_food_tab_checked_count(self, *_args):
        """更新「增益技能／料理」分頁標題中的已勾選數量。"""
        tab_widget = getattr(self, "skill_food_tab_widget", None)
        tab_index = getattr(self, "skill_food_tab_index", None)
        if tab_widget is None or tab_index is None:
            return

        checked_count = sum(
            1 for checkbox in getattr(self, "skill_checkboxes", {}).values()
            if checkbox.isChecked()
        )
        base_title = tr("tab.buff_skill_food")
        tab_widget.setTabText(tab_index, f"{base_title} ({checked_count})")

    def filter_skill_list(self):
        keyword = self.skill_search_bar.text().strip().lower()

        for name, checkbox in self.skill_checkboxes.items():
            if keyword in name.lower() or keyword in all_skill_entries[name]["type"].lower():
                checkbox.show()
            else:
                checkbox.hide()


    
    def normalize_effect_key(self, key: str) -> str:
        return core_normalize_effect_key(key)

    def handle_exclusive_toggle(self, checkbox, group, checked):
        """處理 mutually exclusive 但允許取消的行為"""
        if checked:
            # 若這個 checkbox 被勾選，取消同組其他的
            for cb in self.exclusive_groups[group]:
                if cb is not checkbox:
                    cb.blockSignals(True)
                    cb.setChecked(False)
                    cb.blockSignals(False)
        else:
            # 若使用者取消勾選 → 不做任何事（允許取消）
            pass

        # 同組其他項目可能以 blockSignals 取消勾選，因此在此統一刷新數量。
        self.update_skill_food_tab_checked_count()


    def try_extract_effect(self, line: str):
        return core_try_extract_effect(line)
        
    def update_stat_bonus_display(self):
        '''
        素質加成顯示 = 基礎值 + 職業加成 + 裝備加成
        '''
        try:
            job_id = self.input_fields["JOB"].currentData()
            tjob_bonus = job_dict.get(job_id, {}).get("TJobMaxPoint", [])
            globals()["GetPureJob"] = job_dict.get(job_id, {}).get("GetPureJob", [])
            #print(f"職業系列id: {GetPureJob}")
            stat_names = ["STR", "AGI", "VIT", "INT", "DEX", "LUK", "POW", "STA", "WIS", "SPL", "CON", "CRT"]
            raw_effects = getattr(self, "effect_dict_raw", {})
            base_values = {}
            for stat in stat_names:
                try:
                    base_values[stat] = self.input_fields[stat].text()
                except Exception:
                    base_values[stat] = 0
            stat_breakdown = core_calculate_stat_breakdown(
                base_values=base_values,
                job_bonus=tjob_bonus,
                effect_dict=raw_effects,
            )

            for stat in stat_names:
                values = stat_breakdown[stat]
                base = values["base"]
                job = values["job"]
                equip = values["equip"]
                total = values["total"]
                job_equip = values["job_equip"]
                if stat in self.stat_bonus_labels:
                    self.stat_bonus_labels[stat].setFont(QFont("Consolas", 14))
                    if self.job_equip_checkbox.isChecked():
                        self.stat_bonus_labels[stat].setText(f"{base:>3} +{job_equip:>8} = {total:>3}")
                    else:
                        self.stat_bonus_labels[stat].setText(f"{base:>3} +{job:>3} +{equip:>3} = {total:>3}")
        except Exception as e:
            print("顯示職業加成錯誤：", e)


    def calculate_tstat_total_used(self):
        # UI only collects values; the point rule/summing is owned by ro_core.
        values = []
        for tstat in ["POW", "STA", "WIS", "SPL", "CON", "CRT"]:
            try:
                values.append(self.input_fields[tstat].text())
            except Exception:
                values.append(0)
        return core_calculate_tstat_total_used(values)

    def on_result_output_changed(self):
        if isinstance(self.result_output, QTextEdit):
            lua_code = self.result_output.toPlainText()
        else:
            lua_code = self.result_output.text()

        # === get(x) 對應 ===
        get_values = {}
        for stat_id, stat_name in stat_fields.items():
            try:
                get_values[stat_id] = int(self.input_fields[stat_name].text())
            except:
                get_values[stat_id] = 0

        # === refine_inputs: 所有部位 slot ➜ 精煉值 ===
        refine_inputs = {}
        for part_name, info in refine_parts.items():
            slot_id = info.get("slot")
            try:
                refine_inputs[slot_id] = self.refine_inputs_ui[part_name]["refine"].value()
            except:
                refine_inputs[slot_id] = 0

        # === 全域精煉 slot（GetLocation() 用）===
        try:
            current_location_slot = self.global_refine_input()
        except:
            current_location_slot = 0

        # === 全域階級（GetEquipGradeLevel(GetLocation()) 用）===
        try:
            grade = self.global_grade_combo.currentData()
        except:
            grade = 4

        try:
            results = parse_lua_effects_with_variables(
                block_text=lua_code,
                refine_inputs=refine_inputs,
                get_values=get_values,
                grade=grade,
                unit_map=unit_map,
                size_map=size_map,
                effect_map=effect_map,
                current_location_slot=current_location_slot  # ✅ 傳入現在位置 slot
            )
            results = self.filter_effects(results)
            explanation = "\n".join(results)
        except Exception as e:
            explanation = f"⚠️ 錯誤：{e}"

        self.syntax_result_box.setPlainText(explanation)




    def on_function_changed(self):
        map_registry = {#函數對應
            "equip_sitetype": equip_sitetype,
            "stat_fields": stat_fields,
            "skill_map": skill_map,
            "effect_map": effect_map,
        }
        self.skill_search_input.setVisible(False)
        func_name = self.function_selector.currentData()
        spec = function_defs.get(func_name, {})
        self.param_widgets.clear()

        while self.param_layout.count():
            item = self.param_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        row_layout = QHBoxLayout()

        for arg in spec.get("args", []):
            if arg.get("name") in ("無意義", "目標"):
                if arg.get("map") == "unit_map":
                    # 特殊情況：map 是 unit_map → 強制指定 1
                    self.param_widgets.append("1")
                elif "map" in arg and arg["map"].isdigit():
                    # 一般情況：map 本身就是數字字串
                    self.param_widgets.append(arg["map"])
                else:
                    # 其他情況：預設填 0
                    self.param_widgets.append("0")
                continue



            label = QLabel(arg["name"])
            row_layout.addWidget(label)
            if arg.get("type") == "var_select":

                # 🔹 變數名稱
                name_input = QLineEdit()
                name_input.setFixedWidth(100)
                name_input.setPlaceholderText(tr("placeholder.variable_name"))

                # 🔹 等號
                eq_label = QLabel("=")

                # 🔹 dropdown（原本的 map）
                combo = QComboBox()
                combo.setFixedWidth(120)

                value_map = map_registry.get(arg["map"], {})
                for k, v in value_map.items():
                    combo.addItem(v, k)

                # 🔹 排版（重點：dropdown 在 = 後）
                row_layout.addWidget(name_input)
                row_layout.addWidget(eq_label)
                row_layout.addWidget(combo)

                self.param_widgets.append((name_input, combo))
                continue


            if "map" in arg:
                if arg["map"].isdigit():
                    label_value = QLabel(tr("label.fixed_value", value=arg["map"]))
                    label_value.setObjectName("fixed")
                    self.param_widgets.append(arg["map"])
                    row_layout.addWidget(label_value)
                    row_layout.setFixedWidth(150)
                    
                elif arg["map"]:
                    if arg["map"] == "skill_map":
                        # ✅ 技能選單 + 外部搜尋框綁定
                        self.skill_search_input.setVisible(True)
                        combo = QComboBox()
                        combo.setFixedWidth(150)
                        combo.setEditable(False)

                        try:
                            value_map = eval(arg["map"])
                        except Exception:
                            value_map = {}
                            

                        all_items = list(value_map.items())
                        for k, v in all_items:
                            combo.addItem(v, k)

                        def filter_skill_combo():
                            keyword = self.skill_search_input.text().lower().strip()
                            combo.clear()
                            for k, v in all_items:
                                if keyword in v.lower() or keyword in str(k):
                                    combo.addItem(v, k)
                        try:
                            self.skill_search_input.textChanged.disconnect()
                        except TypeError:
                            pass
                        self.skill_search_input.textChanged.connect(filter_skill_combo)

                        self.param_widgets.append(combo)
                        row_layout.addWidget(combo)

                    else:
                        combo = QComboBox()
                        combo.setFixedWidth(150)
                        try:
                            value_map = eval(arg["map"])

                            if arg["map"] == "effect_map":
                                # 只有 effect_map 時才按名稱排序
                                items = sorted(value_map.items(), key=lambda item: item[1])
                            else:
                                items = value_map.items()

                            for k, v in items:
                                combo.addItem(v, k)

                        except Exception:
                            combo.addItem("（錯誤：找不到 map）", -1)
                        
                        self.param_widgets.append(combo)
                        row_layout.addWidget(combo)
                
            elif arg.get("type") == "value":
                spin = QSpinBox()
                spin.setRange(0, 999)
                spin.setFixedWidth(45)
                spin.setButtonSymbols(QSpinBox.NoButtons)
                spin.wheelEvent = lambda e: None
                self.param_widgets.append(spin)
                row_layout.addWidget(spin)

        row_widget = QWidget()
        row_widget.setLayout(row_layout)
        self.param_layout.addWidget(row_widget, alignment=Qt.AlignRight)




    

    def on_condition_left_activated(self, index):
        """上方條件來源選單選取中文項目後，編輯欄改顯示真正 Lua 語法。"""
        if not hasattr(self, "condition_left_combo"):
            return
        try:
            syntax = self.condition_left_combo.itemData(int(index))
        except Exception:
            syntax = None
        if syntax:
            self.condition_left_combo.setEditText(str(syntax))

    def on_condition_kind_changed(self, *_args):
        """ELSE / END 不需要左右值；IF / ELSEIF 才啟用條件輸入。"""
        if not hasattr(self, "condition_kind_combo"):
            return
        keyword = self.condition_kind_combo.currentData()
        enabled = keyword in ("if", "elseif")
        for widget_name in (
            "condition_left_combo",
            "condition_operator_combo",
            "condition_right_input",
        ):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setEnabled(enabled)

    def on_generate_condition(self):
        """從上方條件產生器插入 if / elseif / else / end 到同一個語法輸入框。"""
        if not hasattr(self, "result_output"):
            return

        keyword = str(self.condition_kind_combo.currentData() or "").strip().lower()
        if keyword not in CONTROL_FLOW_DEFS:
            return

        condition = ""
        if keyword in ("if", "elseif"):
            left = self.condition_left_combo.currentText().strip()
            op = str(self.condition_operator_combo.currentData() or "").strip()
            right = self.condition_right_input.text().strip()

            if not left:
                left = "條件"

            # 右值可留空，讓進階使用者直接輸入 truthy/falsy 表達式。
            condition = f"{left} {op} {right}".strip() if right else left

        self.result_output.insert_control_block(
            keyword,
            condition if keyword in ("if", "elseif") else "",
        )
        self.result_output.setFocus()

    def on_generate(self):
        func_name = self.function_selector.currentData()

        args = []
        var_defs = []

        for w in self.param_widgets:

            # 🔹 var_select（關鍵新增）
            if isinstance(w, tuple):
                name_input, combo = w

                var_name = name_input.text().strip()
                value = combo.currentData()

                # function 參數還是要保留
                args.append(str(value))

                # 如果有變數名稱 → 產生 assignment
                if var_name:
                    var_defs.append(f"{var_name} = {func_name}({value})")

            elif isinstance(w, QComboBox):
                args.append(str(w.currentData()))

            elif isinstance(w, QSpinBox):
                args.append(str(w.value()))

            elif isinstance(w, str):
                args.append(w)

        # 🔹 如果有變數 → 用變數式
        if var_defs:
            result = "\n".join(var_defs)
        else:
            result = f"{func_name}({', '.join(args)})"

        # ✅ append 到輸出
        existing = self.result_output.toPlainText()
        if existing.strip():
            new_text = existing + "\n" + result
        else:
            new_text = result

        self.result_output.setPlainText(new_text)

        self.result_output.verticalScrollBar().setValue(
            self.result_output.verticalScrollBar().maximum()
        )


    def get_program_update_info(self, show_error=False):
        try:
            local_ver = Version
            remote_ver = read_remote_version_github()
            if not remote_ver:
                raise RuntimeError("GitHub 回傳的 tag_name 為空（可能沒有 release）。")

            self._remote_version = remote_ver
            cmp_result = compare_versions(remote_ver, local_ver)
            return {
                "available": cmp_result > 0,
                "local_ver": str(local_ver),
                "remote_ver": str(remote_ver),
                "cmp_result": cmp_result,
                "release_url": f"https://github.com/z2911902/ROItemSearchApp/releases/tag/{remote_ver}",
            }
        except Exception as e:
            if show_error:
                QMessageBox.warning(self, tr("message.title.program_update_check_failed"), tr("message.program_update_check_failed", error=e))
            return {
                "available": False,
                "error": str(e),
            }



    def recompile(self, program_update_info=None):
        data_folder = os.path.join(os.getcwd(), "data")
        program_update_info = program_update_info or {}

        items = [
            ("EquipmentProperties.lua", "data/EquipmentProperties.lua"),
            ("iteminfo_new.lua",        "data/iteminfo_new.lua"),            
            ("EnchantList.lua",         "data/EnchantList.lua"),
            ("ItemDBNameTbl.lua",       "data/ItemDBNameTbl.lua"),
            ("ItemReformSystem.lua",    "data/ItemReformSystem.lua"),
            ("stateiconinfo.lua",         "data/stateiconinfo.lua"),
            ("EFSTIDs.lua",             "data/EFSTIDs.lua"),
            ("User_iteminfo_new.lua",        "data/User_iteminfo_new.lua"),
            ("User_EquipmentProperties.lua","data/User_EquipmentProperties.lua"),
            ("skill_tree.yml",          "data/skill_tree.yml"),
            ("skilltreeview.lub",       "data/skilltreeview.lub"),
            ("skillneme.csv",           "data/skillneme.csv"),
            ("skillbuff.lua",           "data/skillbuff.lua"),
            ("all_skill_entries.py",    "data/all_skill_entries.py"),
            ("job_dict.py",             "data/job_dict.py"),
            ("EnchantName.lua",         "data/EnchantName.lua"),
            ("lapine_random_options.json", "data/lapine_random_options.json"),
            ("lapineupgradebox.lub",       "data/lapineupgradebox.lub"),

        ]

        # 未啟用時不把 KRO 檔案放進更新清單，因此 UI 不顯示，也不會檢查。
        if self.should_load_kro_equipment_data():
            items.extend([
                ("KRO_itemInfo_true.lua", "data/KRO_itemInfo_true.lua"),
                ("KRO_equipmentproperties.lua", "data/KRO_equipmentproperties.lua"),
            ])

        # 建一次 service 重用：放成 self 屬性，避免被 GC
        if not hasattr(self, "_recompile_service"):
            self._recompile_service = RecompileService(self)

        svc = self._recompile_service

        progress = QProgressDialog(tr("progress.fetching_github_file_info"), tr("button.cancel"), 0, 0, self)
        progress.setWindowTitle(tr("window.please_wait"))
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

        progress.canceled.connect(svc.cancel)

        def on_progress(done, total):
            progress.setLabelText(tr("progress.fetching_file_info", done=done, total=total))

        def on_error(msg):
            progress.close()
            QMessageBox.critical(self, tr("message.title.error"), tr("message.github_info_failed", message=msg))

        def on_finished(files_to_delete):
            progress.close()
            has_program_update = bool(program_update_info.get("available"))

            if not files_to_delete and not has_program_update:
                cmp_result = program_update_info.get("cmp_result")
                if cmp_result == 0:
                    QMessageBox.information(
                        self,
                        tr("message.title.already_latest"),
                        tr("message.program_and_data_latest", version=program_update_info.get('local_ver', Version))
                    )
                elif cmp_result == -1:
                    QMessageBox.information(
                        self,
                        tr("message.title.local_version_newer"),
                        tr("message.local_version_newer", local_ver=program_update_info.get('local_ver', Version), remote_ver=program_update_info.get('remote_ver', tr("label.unknown")))
                    )
                else:
                    QMessageBox.information(self, tr("message.title.done"), tr("message.no_data_files_to_delete"))
                return

            dialog = FileSelectionDialog(
                files_to_delete,
                data_folder,
                self,
                program_update_info=program_update_info,
            )
            if dialog.exec() != QDialog.Accepted:
                return

            selected_files = dialog.get_selected_files()
            want_program_update = dialog.want_program_update()

            if not selected_files and not want_program_update:
                QMessageBox.information(self, tr("message.title.cancel"), tr("message.no_update_items_selected"))
                return

            try:
                for filename in selected_files:
                    path = os.path.join(data_folder, filename)
                    if os.path.exists(path):
                        os.remove(path)

                if want_program_update:
                    if selected_files:
                        QMessageBox.information(self, tr("message.title.done"), tr("message.data_deleted_prepare_program_update"))
                    self.do_update(program_update_info.get("remote_ver"))
                    return

                if selected_files:
                    QMessageBox.information(self, tr("message.title.done"), tr("message.files_deleted_restart"))
                    python = sys.executable
                    os.execl(python, python, *sys.argv)
                else:
                    QMessageBox.information(self, tr("message.title.done"), tr("message.no_data_files_to_delete"))
            except Exception as e:
                QMessageBox.critical(self, tr("message.title.error"), tr("message.generic_error", error=str(e)))

        # 避免重複連線：先斷再接（Qt/PySide 允許多次 connect，會重複觸發）
        try:
            svc.progress.disconnect()
            svc.error.disconnect()
            svc.finished.disconnect()
        except Exception:
            pass

        svc.progress.connect(on_progress)
        svc.error.connect(on_error)
        svc.finished.connect(on_finished)

        svc.start(
            data_folder=data_folder,
            items=items,
            owner="z2911902",
            repo="ROItemSearchApp",
            branch="main",
        )



    def update_total_effect_display(self):
        keyword = self.total_filter_input.text().strip()
        if not keyword:
            lines = self.total_combined_raw
        else:
            lines = [line for line in self.total_combined_raw if keyword in line]

        self.safe_update_textbox(self.total_effect_text, "\n".join(lines))
        
    #被動技能給予的狀態
    def apply_skill_buffs_into_effect_dict(self, skillbuff_path, enabled_skill_levels, refine_inputs, get_values, grade):
        def GSklv(skill_id):
            return enabled_skill_levels.get(skill_id, 0)  # 若沒有這個技能，預設回傳 0

        try:
            with open(skillbuff_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"❌ 無法讀取 skillbuff.lua：{e}")
            return {}

        effect_dict = {}
        for skill_id, level in enabled_skill_levels.items():
            pattern = rf"\[{skill_id}\]\s*=\s*\{{(.*?)\}}"
            match = re.search(pattern, content, re.DOTALL)
            if not match:
                continue

            block = match.group(1)
            #block = re.sub(rf"GSklv\({skill_id}\)", str(level), block)
            block = re.sub(
                r"GSklv\(\s*(\d+)\s*\)",
                lambda m: str(GSklv(int(m.group(1)))),
                block,
                flags=re.IGNORECASE
            )

            parsed_lines = parse_lua_effects_with_variables(
                block,
                refine_inputs,
                get_values,
                grade,
                unit_map,
                size_map,
                effect_map,
                hide_unrecognized=True
            )
            #print("DEBUG parsed_lines:", parsed_lines)

            skill_name = skill_map.get(skill_id, f"技能ID {skill_id}")
            source_str = f"技能：{skill_name} Lv.{level}"

            for line in parsed_lines:
                # 濾掉 parser 的 debug 行
                if line.startswith(("📌", "✅", "❌")):
                    continue
                # 嘗試匹配格式："S.MATK +5"、"固定詠唱時間 -1.0 秒"
                match = re.match(r"(.+?)\s*([+-]?\d+(?:\.\d+)?)(?:\s*([^\d\s]+))?$", line)
                if not match:
                    continue

                key, val_str, unit = match.groups()
                unit = unit or ""   # ✅ 關鍵：None -> ""
                try:
                    value = float(val_str)
                except:
                    continue

                display_value = int(value) if value.is_integer() else round(value, 1)

                effect_dict.setdefault((key.strip(), unit), []).append((display_value, source_str))

        return effect_dict




    # Stage 6 Core base-stat precompute
    def _sync_core_precompute_context_to_desktop(self, context):
        """Compatibility bridge only; calculation itself now lives in ro_core."""
        stat_names = (
            "STR", "AGI", "VIT", "INT", "DEX", "LUK",
            "POW", "STA", "WIS", "SPL", "CON", "CRT",
        )
        for stat in stat_names:
            globals()[f"base_{stat}"] = context.get(f"base_{stat}", 0)
            globals()[f"job_{stat}"] = context.get(f"job_{stat}", 0)
            globals()[f"base_equip_{stat}"] = context.get(f"base_equip_{stat}", 0)
        globals()["skill_focus_AGI"] = context.get("skill_focus_AGI", 0)
        globals()["skill_focus_DEX"] = context.get("skill_focus_DEX", 0)
        globals()["job_idcore"] = context.get("job_idcore", "")
        globals()["GetPureJob"] = context.pure_jobs
        self.base_equip_stats_raw = {
            stat: context.get(f"base_equip_{stat}", 0)
            for stat in stat_names
        }

    def _precompute_base_equipment_stats_for_lua(self):
        """Legacy Desktop method name kept as a thin Core wrapper."""
        request = getattr(self, "last_core_effect_request", None)
        if request is None:
            request = self.build_core_equipment_effect_request()

        context = build_desktop_calculation_context()
        data = EquipmentCalculationData(
            parsed_items=self.parsed_items,
            equipment_data=self.equipment_data,
            job_dict=job_dict,
            stat_name_sets=stat_name_sets,
        )
        result = core_precompute_base_equipment_stats(
            request,
            data,
            context=context,
            dependencies=build_desktop_core_dependencies(),
        )
        self._sync_core_precompute_context_to_desktop(context)
        return dict(result.base_equipment_stats)


    # Stage 4 Desktop effect-input snapshot
    # === CORE DEDUP PHASE 4+5: STAGE17 REQUEST/RESULT BRIDGE ===
    @staticmethod
    def _core_int_from_widget(widget, default=0):
        try:
            return int(float(widget.text()))
        except (AttributeError, TypeError, ValueError):
            return default

    def build_core_stage17_damage_request(self):
        """Build a Qt-free Stage17 request from the current Desktop snapshot.

        This bridge is intentionally separate from rendering for now: it creates a
        parity result that can be compared with the legacy Desktop path before the
        final cut-over removes the large orchestration block.
        """
        equipment_request = getattr(self, "last_core_effect_request", None)
        effect_result = getattr(self, "last_core_effect_result", None)
        if equipment_request is None or effect_result is None:
            return None

        core_context = build_desktop_calculation_context()
        core_skillbuff_text = ""
        skillbuff_path = os.path.join(get_app_base_dir(), "data", "skillbuff.lua")
        try:
            with open(skillbuff_path, "r", encoding="utf-8") as f:
                core_skillbuff_text = f.read()
        except OSError:
            pass

        core_data = EquipmentCalculationData(
            parsed_items=self.parsed_items,
            equipment_data=self.equipment_data,
            job_dict=job_dict,
            stat_name_sets=stat_name_sets,
            skill_entries=all_skill_entries,
            skillbuff_text=core_skillbuff_text,
            skill_map=skill_map,
            unit_map=unit_map,
            size_map=size_map,
            effect_map=effect_map,
            custom_sort_orders=custom_sort_orders,
        )

        special_checks = getattr(self, "special_checkboxes", {}) or {}

        def special_checked(name):
            widget = special_checks.get(name)
            return bool(widget is not None and widget.isChecked())

        damage = {
            "skill_id": self.skill_box.currentData(),
            "skill_level": self._core_int_from_widget(self.skill_LV_input, 1),
            "attack_element": self.attack_element_box.currentData(),
            "formula_override": self.skill_formula_input.text().strip() or None,
            "mhp": globals().get("MHP", 0),
            "msp": globals().get("MSP", 0),
            "mhp_now": globals().get("MHP_NOW", 0),
            "msp_now": globals().get("MSP_NOW", 0),
            "special": {
                "wanzih": special_checked("wanzih_checkbox"),
                "poison_weak": special_checked("poison_weak_checkbox"),
                "magic_poison": special_checked("magic_poison_checkbox"),
                "attribute_seal": special_checked("attribute_seal_checkbox"),
                "sneak_attack": special_checked("sneak_attack_checkbox"),
                "spore_attack": special_checked("SPORE_attack_checkbox"),
                "dark_crow": special_checked("DARKCROW_attack_checkbox"),
                "rush_attack": special_checked("RUSH_attack_checkbox"),
                "oleum_attack": special_checked("OLEUM_attack_checkbox"),
                "lex_aeterna": special_checked("PR_LEXAETERNA_checkbox"),
                "total_srl": globals().get("total_SRL", 0),
            },
            "monster": {
                "size": self.size_box.currentData(),
                "element": self.element_box.currentData(),
                "element_lv": self._core_int_from_widget(self.element_lv_input, 1),
                "race": self.race_box.currentData(),
                "class": self.class_box.currentData(),
                "def": self._core_int_from_widget(self.def_input, 0),
                "defc": self._core_int_from_widget(self.defc_input, 0),
                "res": self._core_int_from_widget(self.res_input, 0),
                "mdef": self._core_int_from_widget(self.mdef_input, 0),
                "mdefc": self._core_int_from_widget(self.mdefc_input, 0),
                "mres": self._core_int_from_widget(self.mres_input, 0),
                "damage_multiplier_percent": float(
                    str(self.damage_reduction_combobox.currentText()).replace("%", "") or 100
                ),
                "betelgeuse_reduction_percent": int(
                    getattr(self, "MD_BETELGEUSE_total", 0) or 0
                ),
            },
        }
        return CoreStage17DamageRequest(
            request=equipment_request,
            data=core_data,
            context=core_context,
            effect_result=effect_result,
            data_dir=os.path.join(get_app_base_dir(), "data"),
            damage=damage,
        )

    def refresh_core_stage17_snapshot(self):
        request = self.build_core_stage17_damage_request()
        self.last_core_damage_request = request
        self.last_core_damage_result = None
        self.last_core_damage_error = None
        if request is None:
            return None
        try:
            result = core_calculate_stage17_damage_request(request)
            self.last_core_damage_result = result
            return result
        except Exception as exc:
            # Shadow parity must never break the existing Desktop render path.
            self.last_core_damage_error = str(exc)
            return None

    # === CORE DEDUP PHASE 6: PARITY-GATED CORE RENDER ===
    @staticmethod
    def _format_core_stage17_value(value, digits=None):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if digits is not None:
            return f"{number:.{int(digits)}f}"
        if number.is_integer():
            return f"{int(number):,}"
        return f"{number:,.2f}".rstrip("0").rstrip(".")

    def build_core_stage17_output_lines(self, core_result, extra_lines=None):
        """Translate the Qt-free Core result into the existing Desktop text contract."""
        raw = core_result.to_dict() if hasattr(core_result, "to_dict") else dict(core_result or {})
        skill = dict(raw.get("skill", {}) or {})
        display = dict(raw.get("display", {}) or {})
        breakdown = dict(raw.get("breakdown", {}) or {})
        segments = [dict(item) for item in (raw.get("segments", []) or []) if isinstance(item, dict)]
        warnings = list(raw.get("warnings", []) or [])

        if not segments:
            raise ValueError("Core Stage17 result has no renderable segments")

        skill_name = str(skill.get("name", "") or "")
        attack_type = str(skill.get("attack_type", "") or "")
        critical_display = float(display.get("critical_hit", 0) or 0) > 0
        decay_hits = int(display.get("decay_hits", 0) or 0)
        lines = [f"使用技能: {skill_name}"]

        def fmt_damage(min_value, max_value):
            min_value = int(min_value or 0)
            max_value = int(max_value or 0)
            if critical_display:
                return f"{max_value:,}"
            return f"{min_value:,} ~ {max_value:,}"

        if attack_type == "shield":
            lines.append("")
            lines.append(f"護盾可抵擋傷害: {self._format_core_stage17_value(segments[0].get('skill_result', 0))}")
            lines.append("")
        else:
            combo_split = len(segments) == 2 and str(segments[1].get("label", "")) == "combo (均分)"
            if combo_split:
                main = segments[0]
                combo = segments[1]
                main_element = element_map.get(main.get("user_attack_element"), main.get("user_attack_element"))
                combo_element = element_map.get(combo.get("user_attack_element"), combo.get("user_attack_element"))
                lines.append(f"[{main_element}] ==================主技能總傷害===========================")
                lines.append(f"單次傷害:     {fmt_damage(main.get('damage_by_hit_min'), main.get('damage_by_hit'))}")
                lines.append(f"打擊次數:     {int(main.get('times', 1) or 1)} 次")
                lines.append(f"主技能總傷害: {fmt_damage(main.get('total_damage_min'), main.get('total_damage'))}")
                lines.append(f"[{combo_element}] ===============COMBO 技能（均分）========================")
                lines.append(f"單次傷害(COMBO): {fmt_damage(combo.get('damage_by_hit_min'), combo.get('damage_by_hit'))}")
                lines.append(f"打擊次數(COMBO): {int(combo.get('times', 1) or 1)} 次")
                lines.append(f"總傷害(COMBO):   {fmt_damage(combo.get('total_damage_min'), combo.get('total_damage'))}")
                lines.append("")
                lines.append(f"總傷害:  {fmt_damage(raw.get('total_damage_min'), raw.get('total_damage'))}")
            elif len(segments) > 1:
                attack_element = skill.get("attack_element")
                element_name = element_map.get(attack_element, attack_element)
                lines.append(f"[{element_name}] ===========以下總傷害數值（共 {len(segments)} 次）====================")
                for idx, item in enumerate(segments, start=1):
                    lines.append(
                        f"第 {idx}/{len(segments)} 次傷害: "
                        f"{fmt_damage(item.get('total_damage_min'), item.get('total_damage'))}"
                    )
                lines.append(f"總傷害:  {fmt_damage(raw.get('total_damage_min'), raw.get('total_damage'))}")
            else:
                item = segments[0]
                attack_element = item.get("user_attack_element", skill.get("attack_element"))
                element_name = element_map.get(attack_element, attack_element)
                lines.append(f"[{element_name}] =================以下總傷害數值===========================")
                lines.append(f"單次傷害: {fmt_damage(item.get('damage_by_hit_min'), item.get('damage_by_hit'))}")
                lines.append(f"打擊次數: {int(item.get('times', 1) or 1)} 次")
                lines.append(f"總傷害:   {fmt_damage(item.get('total_damage_min'), item.get('total_damage'))}")

            if decay_hits > 1:
                avg_damage = int(int(raw.get("total_damage", 0) or 0) / decay_hits)
                lines.append(f"遞增/減段數: {decay_hits} 段")
                lines.append(f"平均每段傷害: {avg_damage:,}")

            rows = list(breakdown.get("rows", []) or [])
            if rows:
                lines.append("=========================以下各增傷數值===========================")
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    label = str(row.get("label", row.get("key", "")) or "")
                    value = self._format_core_stage17_value(row.get("value", 0), row.get("digits"))
                    unit = str(row.get("unit", "") or "")
                    lines.append(f"{label}: {value}{unit}")
                lines.append("==================================================================")

        lines.append(f"技能等級: {int(skill.get('level', 0) or 0)}")
        if extra_lines:
            lines.extend(list(extra_lines))
        for warning in warnings:
            lines.append(f"⚠ Core: {warning}")
        return lines

    def render_core_stage17_result(self, core_result, *, extra_lines=None):
        lines = self.build_core_stage17_output_lines(core_result, extra_lines=extra_lines)
        raw = core_result.to_dict() if hasattr(core_result, "to_dict") else dict(core_result or {})
        segments = list(raw.get("segments", []) or [])
        if segments:
            self.skill_formula_result_input.setText(
                f"{self._format_core_stage17_value(segments[0].get('skill_result', 0))} %"
            )
        final_output = lines
        if self.auto_compare_checkbox.isChecked():
            compared_output = self.compare_with_base(current_lines=lines, render=False)
            if compared_output is not None:
                final_output = compared_output
        self.custom_calc_box.setHtml(self.generate_highlighted_html(final_output))
        return final_output

    def build_core_equipment_effect_request(self, get_values=None, refine_inputs=None):
        """Snapshot Qt controls into a Qt-free request object.

        Stage 4 records this request for parity/debugging.  The existing
        display_all_effects traversal remains in Desktop for now; Stage 5 can
        make Core consume this request without changing the request shape.
        """
        if get_values is None:
            get_values = {}
            for gid, label in stat_fields.items():
                widget = self.input_fields[label]
                if isinstance(widget, QComboBox):
                    get_values[gid] = widget.currentData()
                else:
                    try:
                        get_values[gid] = int(widget.text())
                    except (TypeError, ValueError):
                        get_values[gid] = 0

        if refine_inputs is None:
            refine_inputs = {}
            for label, info in refine_parts.items():
                slot_id = info["slot"]
                try:
                    refine_inputs[slot_id] = int(self.input_fields[label].text())
                except (TypeError, ValueError):
                    refine_inputs[slot_id] = 0

        slots = []
        for part_name, ui in self.refine_inputs_ui.items():
            slots.append(
                EquipmentSlotInput(
                    part_name=part_name,
                    slot_id=refine_parts[part_name]["slot"],
                    equip_name=ui["equip"].text().strip(),
                    grade=self.input_fields[f"{part_name}_階級"].currentIndex(),
                    cards=[card.text().strip() for card in ui.get("cards", [])],
                    note=(ui["note"].toPlainText().strip() if "note" in ui else ""),
                )
            )

        enabled_skill_names = [
            name
            for name, checkbox in self.skill_checkboxes.items()
            if checkbox.isChecked()
        ]

        return EquipmentEffectRequest(
            get_values=dict(get_values),
            refine_inputs=dict(refine_inputs),
            slots=slots,
            enabled_skill_names=enabled_skill_names,
            hide_unrecognized=self.hide_unrecognized_checkbox.isChecked(),
            hide_physical=self.hide_physical_checkbox.isChecked(),
            hide_magical=self.hide_magical_checkbox.isChecked(),
            show_source=self.show_combo_source_checkbox.isChecked(),
            sort_mode=self.sort_mode_combo.currentText(),
        )

    def display_all_effects(self):
        '''
        顯示所有部位的效果
        '''
        # Stage 4: pure combo-text parsing lives in ro_core.py
        extract_combi_ids = core_extract_combi_ids
        extract_combo_items = core_extract_combo_items



        get_values = {}
        for gid, label in stat_fields.items():
            widget = self.input_fields[label]
            if isinstance(widget, QComboBox):
                get_values[gid] = widget.currentData()
            else:
                try:
                    get_values[gid] = int(widget.text())
                except ValueError:
                    get_values[gid] = 0

        # 🔁 等所有 stat 欄位都建立後，再註冊 textChanged
        if (
            hasattr(self, "_update_stat_point_callback")
            and not getattr(self, "_stat_point_signals_connected", False)
        ):
            for attr in [
                "STR", "AGI", "VIT", "INT", "DEX", "LUK",
                "POW", "STA", "WIS", "SPL", "CON", "CRT",
                "BaseLv"
            ]:
                self.input_fields[attr].editingFinished.connect(
                    self._update_stat_point_callback
                )

            self._stat_point_signals_connected = True

        # 要更新顯示可以執行，但不要重複 connect
        if hasattr(self, "_update_stat_point_callback"):
            self._update_stat_point_callback()



        refine_inputs = {}

        for label, info in refine_parts.items():
            slot_id = info["slot"]
            try:
                refine_inputs[slot_id] = int(self.input_fields[label].text())
            except:
                refine_inputs[slot_id] = 0

        # Stage 4: keep a Qt-free snapshot for parity tests / future API calculator.
        self.last_core_effect_request = self.build_core_equipment_effect_request(
            get_values=get_values,
            refine_inputs=refine_inputs,
        )

        # Stage 5 Desktop -> Core equipment calculator
        # Keep the existing precompute on Desktop for now because it still reads
        # Qt controls / job UI. The actual equipment traversal below is Core-only.
        core_context = build_desktop_calculation_context()
        core_dependencies = build_desktop_core_dependencies()

        skillbuff_path = os.path.join("data", "skillbuff.lua")

        with open(skillbuff_path, "r", encoding="utf-8") as f:
            core_skillbuff_text = f.read()


        core_data = EquipmentCalculationData(
            parsed_items=self.parsed_items,
            equipment_data=self.equipment_data,
            job_dict=job_dict,
            stat_name_sets=stat_name_sets,
            skill_entries=all_skill_entries,
            skillbuff_text=core_skillbuff_text,
            skill_map=skill_map,
            unit_map=unit_map,
            size_map=size_map,
            effect_map=effect_map,
            custom_sort_orders=custom_sort_orders,
        )
        core_result = core_calculate_equipment_effects(
            self.last_core_effect_request,
            core_data,
            context=core_context,
            dependencies=core_dependencies,
        )
        self.last_core_effect_result = core_result
        self._sync_core_precompute_context_to_desktop(core_context)
        combined = list(core_result.combined_lines)
        combo_effects_all = list(core_result.combo_lines)
        effect_dict = core_result.legacy_effect_dict
        #self.total_effect_text.setPlainText("\n".join(combined))
        #self.combo_effect_text.setPlainText("\n".join(combo_effects_all))
        self.total_combined_raw = combined  # 儲存未過濾的總表行
        self.safe_update_textbox(self.total_effect_text, "\n".join(combined))
        self.safe_update_textbox(self.combo_effect_text, "\n".join(combo_effects_all))
        # 不論有沒有套裝效果、裝備或技能，一律記錄 effect_dict
        self.effect_dict_raw = effect_dict
        self.update_stat_bonus_display()
        #運算

        #self.replace_custom_calc_content()

    def set_part_visible(self, part_name, visible: bool):
        ui = self.refine_inputs_ui.get(part_name)
        if not ui:
            return

        # 隱藏時順便清空該部位
        if not visible:
            equip = ui.get("equip")
            if equip:
                equip.clear()

            refine = ui.get("refine")
            if refine:
                refine.setText("0")

            grade = ui.get("grade")
            if grade:
                grade.setCurrentIndex(0)

            for card in ui.get("cards", []):
                card.clear()

            note = ui.get("note")
            if note:
                note.clear()

            note_ui = ui.get("note_ui")
            if note_ui:
                note_ui.clear()


        container = ui.get("container")
        if container:
            container.setVisible(visible)

    def weapon_type_ui_control(self):
        '''
        根據武器類型控制相關 UI 的顯示與隱藏
        '''
        weapon_class = global_weapon_type_map.get(4, 0)
        #print(f"weapon_class:{weapon_class}")
        if weapon_class in STAGE21_BLOCK_LEFT_WEAPON_TYPES:                        
            self.set_part_visible("左手(盾牌)", False)
            self.clear_global_state()
            self.display_all_effects()
            #self.display_all_effects()
        else:
            self.set_part_visible("左手(盾牌)", True)

        

    def trigger_total_effect_update(self, *_):
        """使用者有修改時，只排程重算，不立刻阻塞 UI。"""

        # 完整計算期間，內部 setText/setCurrentIndex 產生的 signal 不再排第二輪。
        if getattr(self, "_calc_running", False):
            return

        if hasattr(self, "calc_status_label"):
            self.calc_status_label.setText("● 正在更新計算結果…")

        # 重新 start = debounce；短時間有多個 signal 時，只算最後一次。
        self._calc_timer.start()


    def _perform_total_effect_update(self):
        if getattr(self, "_calc_running", False):
            return

        self._calc_running = True
        try:
            globals()["target_element"] = self.element_box.currentData()

            self.display_all_effects()
            #self.display_item_info()
            self.weapon_type_ui_control()

            # 第一輪：需要先算出 HP/SP 等後續資料，但完全不更新結果 UI。
            self.replace_custom_calc_content(
                render_output=False,
                force_recalc=True,
            )

            self.update_dex_int_half_note()

            # 更新 HP / SP
            self.jobsphp_display()

            # 第二輪：所有資料確定後才輸出，而且只輸出這一次。
            self.replace_custom_calc_content(
                render_output=True,
                force_recalc=True,
            )

            self.update_total_effect_display()

            if hasattr(self, "calc_status_label"):
                self.calc_status_label.setText("✓ 已更新")

            # 等待計算完成後儲存比較基準
            if getattr(self, "_pending_save_compare_base", False):
                self._pending_save_compare_base = False
                self._save_compare_base_after_calc()

        except Exception:
            if hasattr(self, "calc_status_label"):
                self.calc_status_label.setText("⚠ 計算失敗")
            self._pending_save_compare_base = False
            raise
        finally:
            self._calc_running = False
        
        
        



    def parse_equipment_blocks(self, content):
        # 保留既有 method 介面，實際解析改由 Desktop/Web 共用 Core 執行。
        return core_parse_equipment_blocks(content)


    @staticmethod
    def _prefix_combiitem_ids(content: str, prefix):
        """只替 Combiitem 套裝 ID 加上字首，不修改一般 Item ID。"""
        if prefix is None:
            return content

        prefix_text = str(prefix).strip()
        if not prefix_text:
            return content
        if not prefix_text.isdigit():
            raise ValueError("combiitem_id_prefix 必須是整數或只包含數字的字串")

        # Item 區塊內的 Combiitem = { 2000000001, ... }
        # 這種清單本身不含巢狀大括號，因此不會誤吃最外層 Combiitem = { ... } 表。
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

        # 最外層 Combiitem 表中的 [2000000001] = { ... }。
        # 只處理該表第一層的鍵，避免改到 Item = { ... } 或函式內其他數字。
        section_pattern = re.compile(r"(?m)^Combiitem\s*=\s*\{")
        section_match = section_pattern.search(content)
        if not section_match:
            return content

        open_brace = content.find("{", section_match.start(), section_match.end())
        if open_brace < 0:
            return content

        chars = list(content)
        replacements = []
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
                    replacements.append((number_start, number_end, prefix_text + key_match.group(1)))

            i += 1

        for start, end, replacement in reversed(replacements):
            chars[start:end] = replacement

        return "".join(chars)


    def load_equipment_incremental(
        self,
        equipment_lua_path: str,
        *,
        overwrite: bool = True,
        combiitem_id_prefix=None,
    ):
        # 確保舊資料存在
        if not hasattr(self, "equipment_data") or self.equipment_data is None:
            self.equipment_data = {}

        with open(equipment_lua_path, "r", encoding="utf-8") as f:
            content = f.read()

        content = self._prefix_combiitem_ids(
            content,
            combiitem_id_prefix,
        )
        prefix_text = "" if combiitem_id_prefix is None else str(combiitem_id_prefix).strip()
        if prefix_text:
            print(f"🔢 Combiitem ID 已加上字首 {prefix_text}")

        new_blocks = self.parse_equipment_blocks(content)

        added = 0
        updated = 0
        skipped = 0

        for item_id, block in new_blocks.items():
            current = item_id + 1
            if (item_id >= 1000 and current % 1000 == 0):
                print(f"  → 處理中 {item_id+1} 筆", end="\r")
            if item_id not in self.equipment_data:
                self.equipment_data[item_id] = block
                added += 1
            else:
                if overwrite:
                    if self.equipment_data[item_id] != block:
                        self.equipment_data[item_id] = block
                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1

        print(f"✅ 增量更新完成：新增 {added} / 更新 {updated} / 跳過 {skipped} / 總計 {len(self.equipment_data)}")
        return {"added": added, "updated": updated, "skipped": skipped, "total": len(self.equipment_data)}



    def closeEvent(self, event):
        if getattr(self, "_skip_close_confirm", False):
            event.accept()
            return

        reply = QMessageBox.question(
            self,
            "確認關閉",
            "確定要關閉應用程式嗎？未儲存的變更將會遺失。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            compare_window = getattr(self, "multi_compare_window", None)
            if compare_window is not None:
                try:
                    compare_window.close()
                except Exception:
                    pass
            event.accept()
        else:
            event.ignore()
    
    def apply_character_build(self, build):
        if not isinstance(build, CoreCharacterBuild):
            build = CoreCharacterBuild.from_dict(build)
        saved_data = build.to_legacy_dict()
        self.last_character_build = build
        # 🔹 暫停所有 widget 的 signal
        for widget in self.findChildren(QWidget):
            widget.blockSignals(True)


        # input_fields 的 QComboBox 或 QLineEdit
        for key, val in saved_data.items():
            if key in self.input_fields:
                field = self.input_fields[key]
                if isinstance(field, QComboBox):
                    index = field.findText(val)
                    if index != -1:
                        field.setCurrentIndex(index)
                else:
                    field.setText(val)

        # 裝備與卡片欄位
        for part, info in self.refine_inputs_ui.items():
            equip_key = f"{part}_equip"
            if equip_key in saved_data:
                info["equip"].setText(saved_data[equip_key])
            for i in range(4):
                card_key = f"{part}_card{i+1}"
                if card_key in saved_data:
                    info["cards"][i].setText(saved_data[card_key])

        #怪物相關欄位
        self.size_box.setCurrentIndex(saved_data.get("size", 0))
        self.element_box.setCurrentIndex(saved_data.get("element", 0))
        self.race_box.setCurrentIndex(saved_data.get("race", 0))
        self.class_box.setCurrentIndex(saved_data.get("class", 0))
        self.def_input.setText(saved_data.get("def", "0"))
        self.defc_input.setText(saved_data.get("defc", "0"))
        self.res_input.setText(saved_data.get("res", "0"))
        self.mdef_input.setText(saved_data.get("mdef", "0"))
        self.mdefc_input.setText(saved_data.get("mdefc", "0"))
        self.mres_input.setText(saved_data.get("mres", "0"))
        self.element_lv_input.setText(saved_data.get("element_lv", "1"))
        
        # 🔹 恢復 signal
        for widget in self.findChildren(QWidget):
            widget.blockSignals(False)

        # 批次載入時 textChanged 被暫停，這裡補做各洞位附魔按鈕刷新。
        for part_name, info in self.refine_inputs_ui.items():
            self._update_enchant_button_for_part(part_name, info["equip"].text())
            self._update_lapine_upgrade_button_for_part(part_name, info["equip"].text())

        self.clear_global_state()
        # ===== 依 JSON buff 自動勾選技能/料理 =====
        if "buff" in saved_data:
            self.apply_buff_to_skill_checkboxes(saved_data.get("buff"))

        # 輸入空白並清空技能強制更新
        self.skill_filter_input.setText(" ")
        self.skill_filter_input.clear()
        # 技能欄位
        if "skill_name" in saved_data:
            saved_skill_name = str(saved_data.get("skill_name") or "").strip()
            index = self.skill_box.findText(saved_skill_name)

            # JSON 可能儲存的是透過搜尋選到的「非目前職業預設清單」技能。
            # 清空搜尋後該技能不一定存在於 skill_box；此時直接從完整 skill_map 補回，
            # 避免讀檔/多裝備比對還原時悄悄落到第一個技能。
            if index == -1 and saved_skill_name:
                for skill_id, display_name in skill_map.items():
                    if str(display_name) == saved_skill_name:
                        self.skill_box.addItem(display_name, skill_id)
                        index = self.skill_box.count() - 1
                        break

            if index != -1:
                self.skill_box.setCurrentIndex(index)
        # note 欄位最後處理
        for part, info in self.refine_inputs_ui.items():
            note_key = f"{part}_note"
            if note_key in saved_data and "note" in info:
                info["note"].setPlainText(saved_data[note_key])

    def load_saved_inputs(self, filename="saved_inputs.json"):
        if not os.path.exists(filename):
            return
        with open(filename, "r", encoding="utf-8") as f:
            raw_saved_data = json.load(f)
        build = CoreCharacterBuild.from_dict(raw_saved_data)
        self.apply_character_build(build)

        
    def save_preset(self, part):
        info = self.refine_inputs_ui[part]
        name = info["preset_input"].text().strip()
        if not name:
            QMessageBox.warning(self, tr("message.title.error"), tr("message.enter_save_name"))
            return
        data = {
            "equip": info["equip"].text(),
            "cards": [c.text() for c in info["cards"]],
            "note": info["note"].toPlainText(),
            "refine": info["refine"].text(),
            "grade": info["grade"].currentText()
        }

        path = os.path.join(self.preset_folder, f"{part}_{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # 儲存成功後清空名稱輸入欄位
        info["preset_input"].clear()
        
        self.refresh_presets(part)

    def load_preset(self, part, preset_name):
        info = self.refine_inputs_ui[part]

        # 直接用對話框選到的 preset_name，而不是 combo.currentText()
        name = preset_name
        if not name:
            return

        path = os.path.join(self.preset_folder, f"{part}_{name}.json")
        if not os.path.exists(path):
            return

        # 確認是否覆蓋
        if info["equip"].text() or any(c.text() for c in info["cards"]) or info["note"].toPlainText():
            reply = QMessageBox.question(
                self, "覆蓋確認",
                f"目前 {part} 已有資料，確定要覆蓋？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        
        info["preset_input"].setText(preset_name)#讀取檔名傳入名稱
        
        info["equip"].setText(data.get("equip", ""))
        for i in range(4):
            info["cards"][i].setText(data.get("cards", [""]*4)[i])
        info["note"].setPlainText(data.get("note", ""))

        # ✅ 這些也是保留
        info["refine"].setText(data.get("refine", "0"))
        grade = data.get("grade", "N")
        index = info["grade"].findText(grade)
        if index >= 0:
            info["grade"].setCurrentIndex(index)

        #self.display_item_info()
        self.trigger_total_effect_update()

    def delete_preset(self, part, name):
        if not name:
            return

        path = os.path.join(self.preset_folder, f"{part}_{name}.json")
        if os.path.exists(path):
            os.remove(path)

        # 刪掉後刷新一下清單（現在只是回傳清單，不會更新 combo）
        self.refresh_presets(part)


    def refresh_presets(self, part):
        files = os.listdir(self.preset_folder)
        names = [
            f[len(part)+1:-5]
            for f in files
            if f.startswith(part + "_") and f.endswith(".json")
        ]
        return sorted(names)

    def open_save_manager(self, part_name):
        save_list = self.refresh_presets(part_name)
        dialog = SaveManagerDialog(part_name, save_list, self.delete_preset, self)

        # 取得按鈕的螢幕座標
        button = self.refine_inputs_ui[part_name]["manage_btn"]
        global_pos = button.mapToGlobal(QPoint(0, 0))

        # 預設：放在按鈕右側
        x = global_pos.x() + button.width() + 10
        y = global_pos.y()

        # 取得母視窗範圍（相對螢幕的座標）
        parent_geom = self.geometry()
        parent_x, parent_y = parent_geom.x(), parent_geom.y()
        parent_width, parent_height = parent_geom.width(), parent_geom.height()

        # 對話框大小（已固定 300x400）
        dialog_width, dialog_height = dialog.width(), dialog.height()

        # ✅ 限制在母視窗範圍內
        if x + dialog_width > parent_x + parent_width:
            x = global_pos.x() - dialog_width - 50
        if y + dialog_height > parent_y + parent_height:
            y = parent_y + parent_height - dialog_height - 50
        if y < parent_y:  # 不要超出上邊界
            y = parent_y + 10

        # 移動到最終位置
        dialog.move(x, y)

        if dialog.exec():
            selected = dialog.selected_save
            if selected:
                self.load_preset(part_name, selected)










    def apply_selected_equip(self):

        if not self.current_edit_part:
            print("❌ 沒有選擇編輯部位")
            return

        selected_item = self.name_field.text().strip()
        if not selected_item:
            print("⚠️ 沒有選擇要套用的裝備")
            return

        part_name, field_type = self.current_edit_part.split(" - ")

        if part_name not in self.refine_inputs_ui:
            print(f"❌ 無法辨識部位：{part_name}")
            return

        ui = self.refine_inputs_ui[part_name]

        if field_type == "裝備":
            ui["equip"].setText(selected_item)
        elif field_type.startswith("卡片"):
            try:
                card_index = int(field_type[-1]) - 1
                if 0 <= card_index < 4:
                    ui["cards"][card_index].setText(selected_item)
                else:
                    print(f"❌ 卡片編號錯誤：{field_type}")
            except ValueError:
                print(f"❌ 無法解析卡片編號：{field_type}")
        else:
            print(f"❌ 不支援欄位類型：{field_type}")
            return
        

        # 計算統一由按鈕既有的 trigger_total_effect_update 排程處理。

    def apply_result_to_note(self):

        if not self.current_edit_part:
            print("❌ 沒有選擇編輯部位")
            return

        part_name, field_type = self.current_edit_part.split(" - ")
        print(f"目前部位:{part_name} 位置:{field_type}")
        if field_type != "詞條":
            print("⚠️ 當前非詞條欄 ，無法套用語法")
            return

        if part_name not in self.refine_inputs_ui:
            print(f"❌ 無法辨識部位：{part_name}")
            return

        note_widget = self.refine_inputs_ui[part_name].get("note")
        if note_widget:
            new_text = self.result_output.toPlainText().strip()
            note_widget.setPlainText(new_text)
            print(f"✅ 已將語法套用至「{part_name}」詞條欄")
        else:
            print(f"❌ 找不到 {part_name} 的詞條欄位")
        
        # 計算統一由按鈕既有的 trigger_total_effect_update 排程處理。




    def clear_selected_field(self):
        if not self.current_edit_part:
            print("❌ 沒有選擇編輯欄位")
            return

        part_name, field_type = self.current_edit_part.split(" - ")

        if part_name not in self.refine_inputs_ui:
            print(f"❌ 找不到部位：{part_name}")
            return

        ui = self.refine_inputs_ui[part_name]

        if field_type == "裝備":
            ui["equip"].clear()

        elif field_type.startswith("卡片"):
            try:
                idx = int(field_type[-1]) - 1
                if 0 <= idx < 4:
                    ui["cards"][idx].clear()
                else:
                    print("❌ 卡片欄位編號超出範圍")
            except ValueError:
                print("❌ 卡片欄位解析失敗")

        elif field_type == "詞條":
            if "note" in ui:
                ui["note"].clear()
            else:
                print(f"❌ 找不到詞條欄位於：{part_name}")

        else:
            print(f"❌ 不支援的欄位類型：{field_type}")
            return

        self.display_item_info()

        if field_type == "詞條":
            self.result_output.clear()



    def _get_multi_compare_context(self):
        """提供多裝備比對模組需要的主程式資料/解析器，不複製計算公式。"""
        return {
            "tr": tr,
            "globals_map": globals(),
            "all_skill_entries": all_skill_entries,
            "skill_map": skill_map,
            "stat_fields": stat_fields,
            "refine_parts": refine_parts,
            "parse_lua_effects_with_variables": parse_lua_effects_with_variables,
            "unit_map": unit_map,
            "size_map": size_map,
            "effect_map": effect_map,
        }

    def open_multi_compare(self):
        """開啟獨立多裝備比對模組視窗。"""
        return open_multi_compare_window(self, self._get_multi_compare_context())

    def save_compare_base(self):
        # 對比時自動啟用數值最大化
        self.auto_compare_checkbox.setChecked(False)
        self.skill_checkboxes["魔法省悟"].setChecked(True)
        self.skill_checkboxes["武器值最大化"].setChecked(True)

        # 告訴計算流程：
        # 這一次算完之後，要儲存比較基準
        self._pending_save_compare_base = True

        # 強制下一次一定重新計算
        self._last_calc_state = None

        # 排程計算
        self.trigger_total_effect_update()

    def _save_compare_base_after_calc(self):
        text = self.custom_calc_box.toPlainText()

        try:
            with open("compare_base.txt", "w", encoding="utf-8") as f:
                f.write(text)

            QMessageBox.information(
                self,
                tr("message.title.save_success"),
                tr("message.compare_baseline_saved")
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                tr("message.title.error"),
                f"比較基準儲存失敗：{e}"
            )

        finally:
            self.auto_compare_checkbox.setChecked(True)

    def compare_with_base(self, *_args, current_lines=None, render=True):
        import re

        def parse_block(text):
            d = {}
            for line in text.splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    val = val.strip().replace(",", "")
                    num = re.findall(r"[-]?\d+\.?\d*", val)
                    if num:
                        d[key.strip()] = val
            return d

        try:
            with open("compare_base.txt", "r", encoding="utf-8") as f:
                base_text = f.read()
        except FileNotFoundError:
            # 手動比較時提示；自動比較只略過，避免每次重算都跳視窗。
            if render:
                QMessageBox.warning(
                    self,
                    tr("message.title.error"),
                    tr("message.compare_baseline_not_found"),
                )
            return current_lines

        base = parse_block(base_text)
        if current_lines is None:
            current_lines = self.custom_calc_box.toPlainText().splitlines()
        else:
            current_lines = list(current_lines)

        def format_number(val_str):
            val = float(re.findall(r"[-]?\d+\.?\d*", val_str)[0])
            suffix = "%" if "%" in val_str else ""
            if val.is_integer():
                return f"{int(val):,}{suffix}"
            return f"{val:.2f}{suffix}"

        skip_compare_keys = {"技能公式", "技能說明"}

        new_output = []
        for line in current_lines:
            if ":" not in line:
                new_output.append(line)
                continue

            key_part, val_part = line.split(":", 1)
            key = key_part.strip()
            val_clean = val_part.strip().replace(",", "")

            if key in skip_compare_keys:
                new_output.append(line)
                continue

            if key in base:
                try:
                    old_val_str = base[key]
                    new_val_str = val_clean

                    old_val = float(re.findall(r"[-]?\d+\.?\d*", old_val_str)[0])
                    new_val = float(re.findall(r"[-]?\d+\.?\d*", new_val_str)[0])

                    if old_val != new_val:
                        diff = new_val - old_val
                        sign = "+" if diff > 0 else "-"
                        suffix = "%" if "%" in new_val_str else ""
                        old_fmt = format_number(old_val_str)
                        new_fmt = format_number(new_val_str)

                        if "傷害" in key:
                            percent_val = abs(diff / old_val * 100) if old_val else 0
                            diff_fmt = f"{sign}{int(abs(diff)):,} / {sign}{percent_val:.2f}%"
                        elif "技能倍率" in key:
                            percent_val = abs(diff / old_val * 100) if old_val else 0
                            diff_fmt = f"{sign}{int(abs(diff)):,}{suffix} / {sign}{percent_val:.2f}%"
                        else:
                            diff_fmt = f"{sign}{abs(diff):.0f}{suffix}"

                        arrow_str = f"{old_fmt} → {new_fmt}"
                        prefix = line[:line.index(":") + 1]
                        suffix_space = val_part[:len(val_part) - len(val_part.lstrip())]
                        new_output.append(
                            f"{prefix}{suffix_space}{arrow_str}  ({diff_fmt})"
                        )
                    else:
                        new_output.append(line)
                except Exception as e:
                    new_output.append(f"{line}  ⛔錯誤: {e}")
            else:
                new_output.append(line)

        if render:
            self.custom_calc_box.setHtml(
                self.generate_highlighted_html(new_output)
            )

        return new_output


    def dataloading(self, mode: str = "online_only"):
        """
        mode:
          - "online_only"   : 只用線上來源；但若本地已存在就不下載。缺檔才下載；失敗不回退本地
          - "local_only"    : 完全不碰網路；若缺檔才走本地解譯
        需求：專案中已定義 decompile_lub(), parse_lub_file(), self.parse_equipment_blocks()
        """
        import os, sys, re, subprocess, time
        from urllib.request import urlopen, Request
        from urllib.error import URLError, HTTPError

        self.current_file = None
        load_kro_data = self.should_load_kro_equipment_data()

        # === 線上來源（已整理好的 Lua） ===
        ONLINE_ITEMINFO_URL = "https://z2911902.github.io/ROItemSearchApp/data/iteminfo_new.lua"
        ONLINE_USER_ITEMINFO_URL = "https://z2911902.github.io/ROItemSearchApp/data/User_iteminfo_new.lua"
        ONLINE_EQUIP_URL    = "https://z2911902.github.io/ROItemSearchApp/data/EquipmentProperties.lua"
        ONLINE_User_EQUIP_URL    = "https://z2911902.github.io/ROItemSearchApp/data/User_EquipmentProperties.lua"
        ONLINE_KRO_ITEMINFO_URL = "https://z2911902.github.io/ROItemSearchApp/data/KRO_itemInfo_true.lua"
        ONLINE_KRO_EQUIP_URL = "https://z2911902.github.io/ROItemSearchApp/data/KRO_equipmentproperties.lua"
        ONLINE_EnchantList_URL = "https://z2911902.github.io/ROItemSearchApp/data/EnchantList.lua"
        ONLINE_ItemDBNameTbl_URL = "https://z2911902.github.io/ROItemSearchApp/data/ItemDBNameTbl.lua"
        ONLINE_ItemReformSystem_URL = "https://z2911902.github.io/ROItemSearchApp/data/ItemReformSystem.lua"
        ONLINE_skill_tree_URL = "https://z2911902.github.io/ROItemSearchApp/data/skill_tree.yml"
        ONLINE_skilltreeview_URL = "https://z2911902.github.io/ROItemSearchApp/data/skilltreeview.lub"
        ONLINE_skillneme_URL = "https://z2911902.github.io/ROItemSearchApp/data/skillneme.csv"
        ONLINE_skillbuff_URL = "https://z2911902.github.io/ROItemSearchApp/data/skillbuff.lua"
        ONLINE_skill_entries_URL = "https://z2911902.github.io/ROItemSearchApp/data/all_skill_entries.py"
        ONLINE_job_dict_URL = "https://z2911902.github.io/ROItemSearchApp/data/job_dict.py"
        ONLINE_EnchantName_URL = "https://z2911902.github.io/ROItemSearchApp/data/EnchantName.lua"
        ONLINE_stateiconinfo_URL = "https://z2911902.github.io/ROItemSearchApp/data/stateiconinfo.lua"
        ONLINE_EFSTIDs_URL = "https://z2911902.github.io/ROItemSearchApp/data/EFSTIDs.lua"
        ONLINE_lapine_random_options_URL = "https://z2911902.github.io/ROItemSearchApp/data/lapine_random_options.json"
        ONLINE_lapineupgradebox_URL = "https://z2911902.github.io/ROItemSearchApp/data/lapineupgradebox.lub"

        # === 路徑設定 ===
        if getattr(sys, 'frozen', False):
            BASE_DIR = os.path.dirname(sys.executable)
        else:
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))

        data_dir = os.path.join(BASE_DIR, "data")
        os.makedirs(data_dir, exist_ok=True)
        iteminfo_path      = os.path.join(data_dir, "iteminfo_new.lua")        
        user_iteminfo_path      = os.path.join(data_dir, "User_iteminfo_new.lua")
        kro_iteminfo_path      = os.path.join(data_dir, "KRO_itemInfo_true.lua")
        equipment_lua_path = os.path.join(data_dir, "EquipmentProperties.lua")
        user_equipment_lua_path = os.path.join(data_dir, "User_EquipmentProperties.lua")
        kro_equipment_lua_path = os.path.join(data_dir, "KRO_equipmentproperties.lua")
        EnchantList_path  = os.path.join(data_dir, "EnchantList.lua")
        ItemDBNameTbl_path  = os.path.join(data_dir, "ItemDBNameTbl.lua")
        ItemReformSystem_path  = os.path.join(data_dir, "ItemReformSystem.lua")
        skill_tree_path  = os.path.join(data_dir, "skill_tree.yml")
        skilltreeview_path  = os.path.join(data_dir, "skilltreeview.lub")
        skillneme_path  = os.path.join(data_dir, "skillneme.csv")        
        skillbuff_path  = os.path.join(data_dir, "skillbuff.lua")
        skill_entries_path  = os.path.join(data_dir, "all_skill_entries.py")
        job_dict_path  = os.path.join(data_dir, "job_dict.py")
        EnchantName_path  = os.path.join(data_dir, "EnchantName.lua")
        stateiconinfo_path  = os.path.join(data_dir, "stateiconinfo.lua")
        EFSTIDs_path  = os.path.join(data_dir, "EFSTIDs.lua")
        lapine_random_options_path = os.path.join(data_dir, "lapine_random_options.json")
        lapineupgradebox_path = os.path.join(data_dir, "lapineupgradebox.lub")
        

        # === 內嵌小工具 ===
        def _fmt_bytes(n: int) -> str:
            if n < 1024: return f"{n} B"
            if n < 1024**2: return f"{n/1024:.1f} KB"
            if n < 1024**3: return f"{n/1024**2:.2f} MB"
            return f"{n/1024**3:.2f} GB"

        def _progress_percent_line(done, total, speed_bps):
            if total and total > 0:
                percent = done / total * 100.0
                if speed_bps and speed_bps > 0:
                    eta = max(int((total - done) / speed_bps), 0)
                    return f"{percent:6.2f}%  { _fmt_bytes(done) } / { _fmt_bytes(total) }  { _fmt_bytes(int(speed_bps)) }/s  ETA {eta}s"
                else:
                    return f"{percent:6.2f}%  { _fmt_bytes(done) } / { _fmt_bytes(total) }"
            else:
                if speed_bps and speed_bps > 0:
                    return f"--.--%  { _fmt_bytes(done) } / ?  { _fmt_bytes(int(speed_bps)) }/s"
                else:
                    return f"--.--%  { _fmt_bytes(done) } / ?"

        def _download_with_progress(url: str, dest_path: str, timeout=30) -> bool:
            import time
            import ssl, certifi
            ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
            print(f"🌐 下載：{url}")
            req = Request(url, headers={"User-Agent": "ROItemSearchApp-Updater/1.2"})
            try:
                with urlopen(req, timeout=timeout) as resp:
                    # 取得 Content-Length（可能沒有）
                    try:
                        total = getattr(resp, "length", None) or int(resp.getheader("Content-Length") or 0)
                    except Exception:
                        total = 0

                    tmp = dest_path + ".tmp"
                    start = time.time()
                    done = 0
                    chunk = 64 * 1024  # 64KB

                    with open(tmp, "wb") as f:
                        while True:
                            data = resp.read(chunk)
                            if not data:
                                break
                            f.write(data)
                            done += len(data)

                            # 計算並用「同一行覆寫」呈現（與 parse_lub_file 的做法一致）
                            elapsed = max(time.time() - start, 1e-6)
                            speed = done / elapsed
                            line = _progress_percent_line(done, total, speed)
                            print(line, end="\r")  # 👈 只這行關鍵：同一行覆寫

                    #print()  # 👈 下載結束補一個換行

                    # 基本健檢：避免 404 HTML
                    try:
                        with open(tmp, "rb") as tf:
                            head = tf.read(4096).decode("utf-8", errors="ignore").lower()
                            if "<html" in head:
                                print("❌ 下載內容疑似 HTML 錯誤頁，放棄覆蓋")
                                try: os.remove(tmp)
                                except: pass
                                return False
                    except Exception as e:
                        print(f"⚠️ 健檢失敗（但檔案已下載）：{e}")

                    os.replace(tmp, dest_path)
                    print(f"✅ 已覆蓋：{os.path.relpath(dest_path, BASE_DIR)}  (總計 { _fmt_bytes(done) })")
                    return True

            except (URLError, HTTPError) as e:
                print(f"❌ 下載失敗：{e}")
            except Exception as e:
                print(f"❌ 下載例外：{e}")
            return False



        def _looks_like_file_quick(path: str) -> bool:
            """根據副檔名做快速檢查，避免把下載後的 HTML/錯誤當成合法檔案。"""
            ext = os.path.splitext(path)[1].lower()

            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read(4096).lower()
            except:
                return False

            # --- 檢查是否 HTML（常見錯誤：下載失敗 → 拿到 404 HTML 頁面）---
            if "<html" in txt or "<!doctype html" in txt:
                return False

            # --- 不同副檔名分類判斷 ---
            if ext in (".lua", ".lub"):
                # Lua / Lub
                return any(k in txt for k in ("return", "=", "{", "iteminfo", "equipmentproperties"))

            elif ext == ".yml":
                # YAML
                return any(c in txt for c in (":", "-", "true", "false"))

            elif ext == ".csv":
                # CSV
                return ("," in txt or ";" in txt) and "\n" in txt

            elif ext == ".json":
                # Lapine 隨機附魔機率表：確認不是錯誤頁，且符合讀取端需要的基本結構。
                try:
                    with open(path, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)
                    return isinstance(data, dict) and isinstance(data.get("tables"), dict)
                except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                    return False

            else:
                # 未知類型 → 保守返回 True（你可改成 False）
                return True

        def _try_online_for(targets):
            """targets: [(url, dest_path), ...]；回傳是否成功至少一個"""
            updated = False
            for url, dest in targets:
                ok = _download_with_progress(url, dest)
                if ok and not _looks_like_file_quick(dest):
                    print(f"⚠️ 線上檔案格式或內容不正確：{os.path.basename(dest)}")
                    try:
                        os.remove(dest)
                    except OSError:
                        pass
                    ok = False
                updated = updated or ok
            return updated

        # === 本地（GRF 解出/反編譯/整理）流程子函式（供回退/重建用） ===
        GRFCL_EXE    = os.path.join(BASE_DIR, "APP", "GrfCL.exe")
        GRF_PATH     = r"C:\Program Files (x86)\Gravity\RagnarokOnline\data.grf"
        UNLUAC_JAR   = os.path.join(BASE_DIR, "APP", "unluac.jar")        
        

        def extract_lub_from_grf(relative_path: str) -> bool:
            """從 GRF 解出指定 LUB 檔案。relative_path 必須像：
               data\\LuaFiles514\\Lua Files\\Enchant\\EnchantList.lub
            """
            if not os.path.exists(GRFCL_EXE):
                print(f"找不到 GrfCL.exe：{GRFCL_EXE}")
                return False

            print(f"📦 正在從 GRF 解壓：{relative_path}")
            result = subprocess.run([
                GRFCL_EXE,
                "-encoding", "949",
                "-open", GRF_PATH,
                "-extractFolder", ".",
                relative_path,
                "-exit"
            ], cwd=BASE_DIR, text=True)

            if result.returncode != 0:
                print("❌ 解壓失敗：")
                print(result.stderr)
                return False

            print("✅ 解壓完成")
            return True


        def run_unluac(lub_file, lua_file):
            os.makedirs(data_dir, exist_ok=True)
            with open(lua_file, "w", encoding="utf-8") as out:
                subprocess.run(["java", "-jar", UNLUAC_JAR, lub_file], stdout=out, stderr=subprocess.DEVNULL)

        def split_local_variables(code: str) -> str:
            pattern = re.compile(r'^(\s*)local\s+([\w\s,]+?)\s*=\s*([^\n]+)$', re.MULTILINE)
            def replacer(m):
                indent, var_str, val_str = m.group(1), m.group(2), m.group(3)
                vars_ = [v.strip() for v in var_str.split(',')]
                vals_ = [v.strip() for v in val_str.split(',')]
                lines = []
                for i, var in enumerate(vars_):
                    val = vals_[i] if i < len(vals_) else 'nil'
                    lines.append(f"{indent}local {var} = {val}")
                return '\n'.join(lines)
            return pattern.sub(replacer, code)

        def flatten_array_fields(code: str) -> str:
            pattern = re.compile(r'^(\s*)(\w+)\s*=\s*\{\s*\n((?:\s*\d+\s*,?\n)+)(\s*)\}', re.MULTILINE)
            def replacer(m):
                indent, key, values_block = m.group(1), m.group(2), m.group(3)
                values = [v.strip().strip(',') for v in values_block.strip().splitlines() if v.strip()]
                return f"{indent}{key} = {{ {', '.join(values)} }}"
            return pattern.sub(replacer, code)

        def remove_specific_blocks(code: str, block_names) -> str:
            for name in block_names:
                pattern = re.compile(rf'{name}\s*=\s*\{{.*?\n\}}', re.DOTALL)
                code = pattern.sub('', code)
            return code

        def clean_lua_format(lua_file: str):
            with open(lua_file, "r", encoding="utf-8") as f:
                code = f.read()
            code = split_local_variables(code)
            code = flatten_array_fields(code)
            code = remove_specific_blocks(code, ["SkillGroup", "RefiningBonus", "GradeBonus"])
            with open(lua_file, "w", encoding="utf-8") as f:
                f.write(code)


        def local_fill_missing():
            """本地方式補齊缺檔（有就不動）。"""

            # --- iteminfo_new.lub（使用 decompile_lub） ---
            if not os.path.exists(iteminfo_path):
                lub_path = r"C:\Program Files (x86)\Gravity\RagnarokOnline\System\iteminfo_new.lub"
                print(f"⚙️ 反編譯 {lub_path} → {iteminfo_path}")
                if not decompile_lub(lub_path, iteminfo_path):
                    print("❌ 反編譯 iteminfo 失敗")
                    return False
            else:
                print("✅ iteminfo_new.lua 已存在，略過反編譯")

            # --- EquipmentProperties.lub（使用 unluac） ---
            if not os.path.exists(equipment_lua_path):
                print("📦 解出 EquipmentProperties.lub...")
                equip_lub_rel = r"data\LuaFiles514\Lua Files\EquipmentProperties\EquipmentProperties.lub"
                if not extract_lub_from_grf(equip_lub_rel):
                    print("❌ 解壓 EquipmentProperties.lub 失敗")
                    return False

                # GRF 解出後實際 LUB 檔案位置
                equip_lub_src = os.path.join(BASE_DIR, equip_lub_rel)

                print("🧩 正在反編譯 unluac...")
                run_unluac(equip_lub_src, equipment_lua_path)

                print("🧹 正在整理 Lua 格式...")
                clean_lua_format(equipment_lua_path)
            else:
                print("✅ EquipmentProperties.lua 已存在")

            # --- EnchantList.lub（使用 decompile_lub） ---
            if not os.path.exists(EnchantList_path):
                print("📦 解出 EnchantList.lub...")
                ench_rel = r"data\LuaFiles514\Lua Files\Enchant\EnchantList.lub"
                if extract_lub_from_grf(ench_rel):
                    ench_src = os.path.join(BASE_DIR, ench_rel)
                    print("🧩 使用 luadec 反編譯 EnchantList...")
                    if not decompile_lub(ench_src, EnchantList_path):
                        print("❌ 反編譯 EnchantList 失敗")
                        return False
            else:
                print("✅ EnchantList.lua 已存在")

            # --- ItemReformSystem.lub（使用 decompile_lub） ---
            if not os.path.exists(ItemReformSystem_path):
                print("📦 解出 ItemReformSystem.lub...")
                ench_rel = r"data\LuaFiles514\Lua Files\ItemReform\ItemReformSystem.lub"
                if extract_lub_from_grf(ench_rel):
                    ench_src = os.path.join(BASE_DIR, ench_rel)
                    print("🧩 使用 luadec 反編譯 ItemReformSystem...")
                    if not decompile_lub(ench_src, ItemReformSystem_path):
                        print("❌ 反編譯 ItemReformSystem 失敗")
                        return False
            else:
                print("✅ ItemReformSystem.lua 已存在")

            # --- ItemDBNameTbl.lub（使用 unluac） ---
            if not os.path.exists(ItemDBNameTbl_path):
                print("📦 解出 ItemDBNameTbl.lub...")
                db_rel = r"data\LuaFiles514\Lua Files\ItemDBNameTbl.lub"
                if extract_lub_from_grf(db_rel):
                    db_src = os.path.join(BASE_DIR, db_rel)
                    print("🧩 使用 unluac 反編譯 ItemDBNameTbl...")
                    run_unluac(db_src, ItemDBNameTbl_path)
            else:
                print("✅ ItemDBNameTbl.lua 已存在")

            # --- stateiconinfo.lub（使用 decompile_lub） ---
            if not os.path.exists(stateiconinfo_path):
                print("📦 解出 stateiconinfo.lub...")
                ench_rel = r"data\LuaFiles514\Lua Files\stateicon\stateiconinfo.lub"
                if extract_lub_from_grf(ench_rel):
                    ench_src = os.path.join(BASE_DIR, ench_rel)
                    print("🧩 使用 luadec 反編譯 stateiconinfo...")
                    if not decompile_lub(ench_src, stateiconinfo_path):
                        print("❌ 反編譯 stateiconinfo 失敗")
                        return False
            else:
                print("✅ stateiconinfo.lua 已存在")

            # --- EFSTIDs.lub（使用 decompile_lub） ---
            if not os.path.exists(EFSTIDs_path):
                print("📦 解出 EFSTIDs.lub...")
                ench_rel = r"data\LuaFiles514\Lua Files\stateicon\EFSTIDs.lub"
                if extract_lub_from_grf(ench_rel):
                    ench_src = os.path.join(BASE_DIR, ench_rel)
                    print("🧩 使用 luadec 反編譯 EFSTIDs...")
                    if not decompile_lub(ench_src, EFSTIDs_path):
                        print("❌ 反編譯 EFSTIDs 失敗")
                        return False
            else:
                print("✅ EFSTIDs.lua 已存在")

            # --- 全部完成後刪除 GRF 解出來的暫存 LuaFiles514 ---
            temp_folder = os.path.join(BASE_DIR, "data", "LuaFiles514")
            if os.path.exists(temp_folder):
                try:
                    import shutil
                    shutil.rmtree(temp_folder)
                    print(f"🗑️ 已刪除暫存資料夾：{temp_folder}")
                except Exception as e:
                    print(f"⚠️ 刪除暫存資料夾失敗：{e}")
            return True



        # === 判斷缺檔 ===
        miss_item  = not os.path.exists(iteminfo_path)
        miss_User_item  = not os.path.exists(user_iteminfo_path)
        miss_equip = not os.path.exists(equipment_lua_path)
        miss_user_equip = not os.path.exists(user_equipment_lua_path)
        miss_kro_item = load_kro_data and not os.path.exists(kro_iteminfo_path)
        miss_kro_equip = load_kro_data and not os.path.exists(kro_equipment_lua_path)
        miss_EnchantList  = not os.path.exists(EnchantList_path)
        miss_ItemDBNameTbl  = not os.path.exists(ItemDBNameTbl_path)
        miss_ItemReformSystem  = not os.path.exists(ItemReformSystem_path)
        miss_skill_tree  = not os.path.exists(skill_tree_path)
        miss_skilltreeview  = not os.path.exists(skilltreeview_path)
        miss_skillneme = not os.path.exists(skillneme_path)
        miss_skillbuff = not os.path.exists(skillbuff_path)
        miss_skill_entries = not os.path.exists(skill_entries_path)
        miss_job_dict = not os.path.exists(job_dict_path)
        miss_EnchantName = not os.path.exists(EnchantName_path)
        miss_EFSTIDs = not os.path.exists(EFSTIDs_path)
        miss_stateiconinfo = not os.path.exists(stateiconinfo_path)
        miss_lapine_random_options = not os.path.exists(lapine_random_options_path)
        miss_lapineupgradebox = not os.path.exists(lapineupgradebox_path)

        
        


        # === 模式分流 ===
        if mode == "local_only":
            print(f"編譯方式 📖 本機模式")
            local_required_files = [
                iteminfo_path,
                equipment_lua_path,
                EnchantList_path,
                ItemDBNameTbl_path,
                ItemReformSystem_path,
                EFSTIDs_path,
                stateiconinfo_path,
            ]
            if not all(os.path.exists(path) for path in local_required_files):
                if not local_fill_missing():
                    print("❌ 本地補齊失敗")
                    return

            # KRO 檔案不是 TWRO GRF 的本地反編譯來源；啟用時必須已存在。
            if load_kro_data:
                kro_required_files = [kro_iteminfo_path, kro_equipment_lua_path]
                missing_kro_files = [
                    os.path.basename(path)
                    for path in kro_required_files
                    if not os.path.exists(path)
                ]
                if missing_kro_files:
                    print(
                        "❌ 本機模式缺少 KRO 資料檔："
                        + "、".join(missing_kro_files)
                    )
                    return
        else:
            print(f"編譯方式 ☁️ 線上模式")
            # 只線上：若本地已存在就不下載；只有缺檔才下載。失敗則停止。            
            targets = []
            if miss_item:  targets.append((ONLINE_ITEMINFO_URL, iteminfo_path))
            if miss_User_item:  targets.append((ONLINE_USER_ITEMINFO_URL, user_iteminfo_path))
            if miss_equip: targets.append((ONLINE_EQUIP_URL,    equipment_lua_path))
            if miss_user_equip: targets.append((ONLINE_User_EQUIP_URL,    user_equipment_lua_path))
            if miss_kro_item: targets.append((ONLINE_KRO_ITEMINFO_URL, kro_iteminfo_path))
            if miss_kro_equip: targets.append((ONLINE_KRO_EQUIP_URL, kro_equipment_lua_path))
            if miss_EnchantList: targets.append((ONLINE_EnchantList_URL,    EnchantList_path))
            if miss_ItemDBNameTbl: targets.append((ONLINE_ItemDBNameTbl_URL,    ItemDBNameTbl_path))
            if miss_ItemReformSystem: targets.append((ONLINE_ItemReformSystem_URL,    ItemReformSystem_path))
            if miss_skill_tree: targets.append((ONLINE_skill_tree_URL,    skill_tree_path))
            if miss_skilltreeview: targets.append((ONLINE_skilltreeview_URL,    skilltreeview_path))
            if miss_skillneme: targets.append((ONLINE_skillneme_URL,    skillneme_path))
            if miss_skillbuff: targets.append((ONLINE_skillbuff_URL,    skillbuff_path))
            if miss_skill_entries: targets.append((ONLINE_skill_entries_URL,    skill_entries_path))
            if miss_job_dict: targets.append((ONLINE_job_dict_URL,    job_dict_path))
            if miss_EnchantName: targets.append((ONLINE_EnchantName_URL,    EnchantName_path))
            if miss_EFSTIDs: targets.append((ONLINE_EFSTIDs_URL,    EFSTIDs_path))
            if miss_stateiconinfo: targets.append((ONLINE_stateiconinfo_URL,    stateiconinfo_path))
            if miss_lapine_random_options: targets.append((ONLINE_lapine_random_options_URL, lapine_random_options_path))
            if miss_lapineupgradebox: targets.append((ONLINE_lapineupgradebox_URL, lapineupgradebox_path))
            
            if targets:
                updated = _try_online_for(targets)
                if updated:
                    # ⭐⭐⭐ 下載完成 → 強制重新啟動 ⭐⭐⭐
                    print("🔄 線上資料已更新，重新啟動程式以避免舊快取造成錯誤...")

                    import sys, os
                    python = sys.executable
                    os.execv(python, [python] + sys.argv)
            # 下載後再檢查一次，若仍缺則停止（不回退本地）
            required_files = [
                iteminfo_path,
                user_iteminfo_path,
                equipment_lua_path,
                user_equipment_lua_path,
                EnchantList_path,
                ItemDBNameTbl_path,
                skill_tree_path,
                skilltreeview_path,
                skillneme_path,
                skillbuff_path,
                skill_entries_path,
                job_dict_path,
                EnchantName_path,
                EFSTIDs_path,
                stateiconinfo_path,
                lapine_random_options_path,
                lapineupgradebox_path,

            ]
            if load_kro_data:
                required_files.extend([
                    kro_iteminfo_path,
                    kro_equipment_lua_path,
                ])
            if not all(os.path.exists(path) for path in required_files):
                print("❌ online_only 模式：仍有檔案缺失，停止")
                return

        # === 載入（無論來源） ===

        print("📖 載入 TWRO物品列表 ...")
        self.parsed_items = parse_lub_file(iteminfo_path)
        print("📖 載入 自訂物品列表 ...")
        self.parsed_items = parse_lub_file(user_iteminfo_path, existing_items=self.parsed_items,duplicate_mode="overwrite")
        if load_kro_data:
            print("📖 載入 KRO物品列表 ...")
            self.parsed_items = parse_lub_file(
                kro_iteminfo_path,
                existing_items=self.parsed_items,
                duplicate_mode="skip",
            )
        print("📖 載入 TWRO物品效果...")
        with open(equipment_lua_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.equipment_data = self.parse_equipment_blocks(content)
        print("📖 載入 自定義物品效果...")
        self.load_equipment_incremental(user_equipment_lua_path,overwrite=True) 
        if load_kro_data:
            print("📖 載入 KRO物品效果...")
            self.load_equipment_incremental(
                kro_equipment_lua_path,
                overwrite=False,
                combiitem_id_prefix=1,
            )
        print("📖 載入 技能清單...")
        load_skill_map("data/skillneme.csv") #讀取SKILL列表
        self.update_function_autocomplete_maps()
        self.lua_text = load_skill_delay_lua("data/skilldelaylist.lua")#讀取技能延遲
        self.parsed_items = resolve_name_conflicts(self.parsed_items ,self.equipment_data)#重複物品名稱加上id

        # 物品資料有重新載入時，讓 GUI thread 下一次搜尋重建索引。
        # 這裡不直接碰 Qt Widget，只做 cache 失效標記。
        self._item_search_index_signature = None
        self._last_item_search_text = None

        return self.parsed_items

    def rebuild_skill_tab(self):
        """
        依照最新 all_skill_entries 重新生成技能/料理勾選區域
        （完全保留你原本 UI 的格式與邏輯）
        """

        # 1️⃣ 清除舊的 checkbox
        while self.skill_checkbox_layout.count():
            item = self.skill_checkbox_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        self.skill_checkboxes.clear()
        self.exclusive_groups.clear()

        # 2️⃣ 使用最新資料重建 UI
        from ItemSearchApp import DataRegistry
        all_skill_entries = DataRegistry.loaded_data["skills"]

        for name, data in all_skill_entries.items():

            checkbox = QCheckBox(f"{data['type']} {name}")
            self.skill_checkboxes[name] = checkbox
            self.skill_checkbox_layout.addWidget(checkbox)

            # 保留原本事件
            checkbox.stateChanged.connect(self.clear_global_state)
            checkbox.stateChanged.connect(self.trigger_total_effect_update)
            checkbox.stateChanged.connect(self.update_skill_food_tab_checked_count)


            # exclusive 群組（支援多組，例如 "food_str,food_agi"）
            if "exclusive" in data and data["exclusive"]:
                raw = data["exclusive"]

                # 允許：字串 "a,b,c" 或 list ["a","b","c"]
                if isinstance(raw, str):
                    groups = [g.strip() for g in raw.split(",") if g.strip()]
                else:
                    groups = [str(g).strip() for g in raw if str(g).strip()]

                for group in groups:
                    self.exclusive_groups.setdefault(group, []).append(checkbox)

                    checkbox.toggled.connect(
                        lambda checked, c=checkbox, g=group:
                        self.handle_exclusive_toggle(c, g, checked)
                    )

        self.update_skill_food_tab_checked_count()
        print("✓ Skill/料理區塊已根據最新資料重新生成")

    def reload_job_list(self):
        """
        依照 DataRegistry.loaded_data['jobs'] 重新填入 JOB 下拉選單
        """
        if "JOB" not in self.input_fields:
            return  # 尚未初始化 UI

        combo: QComboBox = self.input_fields["JOB"]
        combo.blockSignals(True)  # 避免觸發 change 事件

        combo.clear()

        jobs = DataRegistry.loaded_data.get("jobs", {})

        for job_id, job_info in sorted(jobs.items()):
            combo.addItem(job_info["name"], job_id)

        combo.blockSignals(False)
        print("✓ JOB 下拉選單已重新載入")




    def refresh_skill_list(self):
        # 搜尋字（只過濾，不排序）
        query = ""
        if hasattr(self, "skill_search_input"):
            query = self.skill_search_input.text().strip().lower()

        # 目前職業 skill id
        job_id = self.input_fields["JOB"].currentData()
        skill_job_id = job_dict.get(job_id, {}).get("id")

        job_skills = []
        other_skills = []

        # ❗ 關鍵：完全依 all_skill_entries 原始順序走
        for name, data in all_skill_entries.items():
            # 搜尋過濾（不改順序）
            if query:
                hay = f"{data.get('type','')} {name}".lower()
                if query not in hay:
                    continue

            ids = data.get("id", [])
            if isinstance(ids, str):
                ids = [ids]

            if skill_job_id in ids:
                job_skills.append(name)
            else:
                other_skills.append(name)

        # 清空 layout（不刪 checkbox）
        while self.skill_checkbox_layout.count():
            item = self.skill_checkbox_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # ===== 本職技能（原始順序）=====
        for name in job_skills:
            self.skill_checkbox_layout.addWidget(self.skill_checkboxes[name])

        # ===== 分隔線 =====
        if job_skills and other_skills:
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            line.setLineWidth(1)
            line.setStyleSheet("""
            QFrame {
                margin-top: 6px;
                margin-bottom: 6px;
            }
            """)
            self.skill_checkbox_layout.addWidget(line)

        # ===== 其他技能（原始順序）=====
        for name in other_skills:
            self.skill_checkbox_layout.addWidget(self.skill_checkboxes[name])







    def do_update(self, version=None):
        ver = (version or self._remote_version or "").strip()
        if not ver:
            QMessageBox.warning(self, tr("message.title.notice"), tr("message.no_program_update"))
            return
        zip_url = ZIP_URL_TEMPLATE.format(ver=ver)

        updater_path = os.path.join(os.getcwd(), UPDATER_EXE)
        if not os.path.exists(updater_path):
            QMessageBox.critical(self, tr("message.title.update_failed"), tr("message.updater_not_found", updater=UPDATER_EXE))
            return

        # 你要呼叫的格式：
        # update.exe  <zip_url>  ItemSearchApp.exe
        try:
            subprocess.Popen([updater_path, zip_url, TARGET_EXE], cwd=os.getcwd())
        except Exception as e:
            QMessageBox.critical(self, tr("message.title.update_failed"), tr("message.updater_start_failed", error=e))
            return

        # 更新器啟動後，主程式自己關掉比較乾淨（讓 updater 覆蓋檔案）
        self._skip_close_confirm = True
        self.close()

    def check_update(self):
        program_update_info = self.get_program_update_info(show_error=False)

        if program_update_info.get("error"):
            QMessageBox.warning(
                self,
                "主程式更新檢查失敗",
                f"無法檢查主程式版本，將只檢查資料更新：\n{program_update_info['error']}"
            )

        self.recompile(program_update_info=program_update_info)







    def __init__(self):
        
        #self.dataloading()#讀取並載入物品跟裝備能力
        
        super().__init__()
        self._skip_close_confirm = False
        self.setWindowTitle(tr("window.main"))
        self.current_edit_part = None  # 用來記錄目前正在編輯的部位名稱
        self.enchant_window = None
        self._enchant_data_cache = None
        self._enchant_itemdb_cache = None
        self._enchant_target_map_cache = None
        self.lapine_upgrade_window = None
        self._lapine_upgrade_data_cache = None
        self._lapine_target_map_cache = None
        self._lapine_item_name_index_cache = None
        self._lapine_item_index_size = -1
        # 把子視窗存成成員變數，避免被 Python 回收導致閃退/秒關
        self._damage_win = None
        self.preset_folder = "equip_presets"
        os.makedirs(self.preset_folder, exist_ok=True)
        self.rrfdamage_window = None
        self.multi_compare_window = None
        self.load_config()#讀取偏好設定

        
        # UI 元件初始化


        self.parsed_items = {}#預先初始化
        self.current_file = None # 尚未開啟任何檔案
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("placeholder.search_item"))

        # 物品搜尋最佳化：輸入期間只重啟 Timer，停止輸入後再真正搜尋。
        # 避免每打一字 / 刪一字都同步掃描完整物品資料並重建 QComboBox。
        self._item_search_timer = QTimer(self)
        self._item_search_timer.setSingleShot(True)
        self._item_search_timer.setInterval(120)
        self._item_search_timer.timeout.connect(self.update_combobox)
        self.search_input.textChanged.connect(self._schedule_item_search)

        # 搜尋字串預先索引；資料載入完成後會重建一次，後續搜尋直接比對索引。
        self._item_search_index = []
        self._item_search_index_signature = None
        self._last_item_search_text = None

        self.result_box = QComboBox()
        self.result_box.currentIndexChanged.connect(self.display_item_info)
        self.result_box.currentIndexChanged.connect(self.update_total_effect_display)#過濾總效果顯示

        self.divine_pride_button = QPushButton(
            tr("button.open_divine_pride", "開啟目前物品的 Divine Pride 連結")
        )
        self.divine_pride_button.setEnabled(False)
        self.divine_pride_button.setToolTip(
            tr("tooltip.open_divine_pride", "開啟目前選取物品的 Divine Pride 資料頁")
        )
        self.divine_pride_button.clicked.connect(
            self.open_selected_item_on_divine_pride
        )
        self.result_box.currentIndexChanged.connect(
            self.update_divine_pride_button
        )

        self.name_field = QLineEdit()
        self.name_field.setReadOnly(True)

        self.kr_name_field = QLineEdit()
        self.kr_name_field.setReadOnly(True)

        self.slot_field = QLineEdit()
        self.slot_field.setReadOnly(True)

        self.desc_text = QTextEdit()
        self.desc_text.setReadOnly(True)

        self.Combi_text = QTextEdit()
        self.Combi_text.setReadOnly(True)

        self.combi_raw_text = QTextEdit()
        self.desc_text.setReadOnly(True)

        self.equip_text = QTextEdit()
        self.equip_text.setReadOnly(True)

        self.sim_effect_label = QLabel(tr("label.effect_parse"))
        #self.sim_effect_text = QTextEdit()
        #self.sim_effect_text.setReadOnly(True)






        # 建立輸入欄位
        self.input_fields = {}

        # 三欄主視窗布局
        main_layout = QHBoxLayout()
        
        # ===== 左側：角色能力與裝備分頁 =====
        # 1. 建立分頁元件
        tab_widget = QTabWidget()
        tab_widget.setFixedWidth(340)
        # 2. 為每個分頁建立 ScrollArea → 放內容
        # === 分頁1：角色能力值 ===
        char_scroll = QScrollArea()
        char_scroll.setWidgetResizable(True)

        char_inner = QWidget()
        char_layout = QVBoxLayout(char_inner)
        char_scroll.setWidget(char_inner)

        # 角色能力值 + 勾選按鈕（同一行）
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("label.character_stats")))

        self.job_equip_checkbox = QCheckBox(tr("checkbox.merge_job_equipment_bonus"))  # ✅ 存成 self.xxx
        row.addWidget(self.job_equip_checkbox)
        self.job_equip_checkbox.toggled.connect(self.update_stat_bonus_display)

        row.addStretch()
        char_layout.addLayout(row)
        # 儲存加成顯示欄位
        self.stat_bonus_labels = {}

        for gid, label in stat_fields.items():
            # ✅ MHP / MSP 同一行 + 加滑桿（HP% / SP%）
            if label == "MHP":
                # 輸入值若來自角色登出畫面，先反推尚未套用 VIT / INT 倍率的基礎 HPSP。
                self.use_logout_hpsp_checkbox = QCheckBox("輸入的HP/SP 使用登出畫面的 HP/SP 數值")
                self.use_logout_hpsp_checkbox.setToolTip(
                    "勾選後，輸入的 MHP 會以 ceil(MHP / (1 + VIT / 100)) 回推；"
                    "MSP 會以 ceil(MSP / (1 + INT / 100)) 回推。"
                )
                char_layout.addWidget(self.use_logout_hpsp_checkbox)

                row_layout = QHBoxLayout()
                row_layout.setAlignment(Qt.AlignLeft)

                # --- MHP ---
                mhp_label = QLabel("MHP")
                mhp_label.setFixedWidth(50)
                row_layout.addWidget(mhp_label)

                mhp_field = QLineEdit()
                mhp_field.setPlaceholderText("MHP (get(200))")
                mhp_field.editingFinished.connect(self.trigger_total_effect_update)
                mhp_field.setMaximumWidth(100)
                self.input_fields["MHP"] = mhp_field
                row_layout.addWidget(mhp_field)

                # --- MSP ---
                msp_label = QLabel("MSP")
                msp_label.setFixedWidth(50)
                row_layout.addWidget(msp_label)

                msp_field = QLineEdit()
                msp_field.setPlaceholderText("MSP (get(202))")
                msp_field.editingFinished.connect(self.trigger_total_effect_update)
                msp_field.setMaximumWidth(100)
                self.input_fields["MSP"] = msp_field
                row_layout.addWidget(msp_field)

                char_layout.addLayout(row_layout)

                # ===== 滑桿區：HP% / SP% =====
                self.hp_percent_label = QLabel(tr("label.hp_percent_default"))
                char_layout.addWidget(self.hp_percent_label)

                self.hp_slider = QSlider(Qt.Horizontal)
                self.hp_slider.setRange(0, 100)
                self.hp_slider.setValue(100)
                char_layout.addWidget(self.hp_slider)

                self.sp_percent_label = QLabel(tr("label.sp_percent_default"))
                char_layout.addWidget(self.sp_percent_label)

                self.sp_slider = QSlider(Qt.Horizontal)
                self.sp_slider.setRange(0, 100)
                self.sp_slider.setValue(100)
                char_layout.addWidget(self.sp_slider)
                self.hp_sp_widgets = [
                    mhp_label,
                    mhp_field,
                    msp_label,
                    msp_field,
                    self.hp_percent_label,
                    self.hp_slider,
                    self.sp_percent_label,
                    self.sp_slider,
                    self.use_logout_hpsp_checkbox,
                ]
                self.MHP_MSP_widgets = [
                    self.hp_percent_label,
                    self.sp_percent_label,
                ]
                
                # ===== 4轉職業 HP/SP 表 =====
                self.jobhp = 0
                self.jobsp = 0

                def update_hp_sp_slider_visibility():
                    job_id = self.input_fields["JOB"].currentData()

                    job_info = job_dict.get(job_id, {})
                    widget = job_info.get("HP_SP_widget", False)
                    MHP_MSP = job_info.get("MHP_MSP", False)

                    for w in self.hp_sp_widgets:
                        w.setVisible(widget)
                    for w in self.MHP_MSP_widgets:
                        w.setVisible(MHP_MSP)

                

                def update_job_4th_hpsp_bonus():
                    job_id = self.input_fields["JOB"].currentData()

                    try:
                        base_lv = int(self.input_fields["BaseLv"].text())
                    except:
                        base_lv = None

                    self.jobhp = 0
                    self.jobsp = 0

                    if base_lv and 201 <= base_lv <= 275:#HP/SP表取得範圍
                        idx = base_lv - 201
                        job_table = job_4th_hpsp.get(job_id)

                        if job_table:
                            hp_list = job_table.get("HP", [])
                            sp_list = job_table.get("SP", [])
                            if idx < len(hp_list):
                                self.jobhp = hp_list[idx]
                            if idx < len(sp_list):
                                self.jobsp = sp_list[idx]
                

                def _safe_int(text):
                    try:
                        return int(text)
                    except:
                        return 0 
                
                def fmt_stat(prefix: str, now, maxv, pct,
                             prefix_w: int = 6,
                             value_w: int = 9,
                             pct_w: int = 4) -> str:
                    """
                    格式化狀態顯示字串（HP / SP）
                    全形字寬=2，半形字寬=1
                    """

                    def visual_length(s: str) -> int:
                        width = 0
                        for c in s:
                            width += 2 if ord(c) > 255 else 1
                        return width

                    def pad(text: str, total_width: int) -> str:
                        space_count = total_width - visual_length(text)
                        return text + " " * max(space_count, 0)

                    return (
                        pad(prefix, prefix_w)
                        + pad(str(now), value_w)
                        + "/ "
                        + pad(str(maxv), value_w)
                        + pad(f"{pct}%", pct_w)
                    )

                def update_hp_sp_slider_display():
                    update_job_4th_hpsp_bonus()
                    
                    mhp_input = _safe_int(self.input_fields["MHP"].text())
                    msp_input = _safe_int(self.input_fields["MSP"].text())
                    HP = globals().get("HP", 0)
                    SP = globals().get("SP", 0)
                    HPPercent = globals().get("HPPercent", 0)
                    SPPercent = globals().get("SPPercent", 0)
                    VIT = globals().get("total_VIT", 0)
                    INT = globals().get("total_INT", 0)
                    base_VIT = globals().get("base_VIT", 0)
                    base_INT = globals().get("base_INT", 0)

                    # 登出畫面顯示值已包含 VIT / INT 倍率。勾選後先回推基礎值，
                    # 並依需求採無條件進位，之後再套用既有裝備與百分比加成。
                    status = _core_stage20_calculate_hpsp_values(
                        job_base_hp=self.jobhp,
                        job_base_sp=self.jobsp,
                        base_vit=base_VIT,
                        base_int=base_INT,
                        total_vit=VIT,
                        total_int=INT,
                        hp_flat=HP,
                        sp_flat=SP,
                        hp_percent_bonus=HPPercent,
                        sp_percent_bonus=SPPercent,
                        mhp_input=mhp_input,
                        msp_input=msp_input,
                        use_logout_values=self.use_logout_hpsp_checkbox.isChecked(),
                        hp_current_percent=self.hp_slider.value(),
                        sp_current_percent=self.sp_slider.value(),
                    )
                    MHP = status["mhp"]
                    MSP = status["msp"]
                    MHP_NOW = status["mhp_now"]
                    MSP_NOW = status["msp_now"]
                    hp_pct = status["hp_current_percent"]
                    sp_pct = status["sp_current_percent"]
                    globals()["MHP"] = MHP
                    globals()["MSP"] = MSP
                    globals()["MHP_NOW"] = MHP_NOW
                    globals()["MSP_NOW"] = MSP_NOW


                    # self.hp_percent_label.setText(f"HP：{MHP_NOW} / {MHP}  {hp_pct}%")
                    # self.sp_percent_label.setText(f"SP：{MSP_NOW} / {MSP}  {sp_pct}%")
                    self.hp_percent_label.setText(fmt_stat("HP：", MHP_NOW, MHP, hp_pct))
                    self.sp_percent_label.setText(fmt_stat("SP：", MSP_NOW, MSP, sp_pct))

                    # self.hp_percent_label.setText(hp_text)
                    # self.sp_percent_label.setText(sp_text)
                    self.hp_percent_label.setStyleSheet(
                        "font-family: Consolas, Menlo, monospace;"
                        "font-size: 18px;"
                    )
                    self.sp_percent_label.setStyleSheet(
                        "font-family: Consolas, Menlo, monospace;"
                        "font-size: 18px;"
                    )

                    
                def jobsphp_display():
                    update_hp_sp_slider_visibility()
                    update_hp_sp_slider_display()

                self.jobsphp_display = jobsphp_display#註冊到全域函數

                # 連動：滑桿、以及 MHP/MSP 被改時都要更新顯示
                self.hp_slider.valueChanged.connect(update_hp_sp_slider_display)                
                self.sp_slider.valueChanged.connect(update_hp_sp_slider_display)
                self.input_fields["MHP"].editingFinished.connect(update_hp_sp_slider_display)
                self.input_fields["MSP"].editingFinished.connect(update_hp_sp_slider_display)
                self.use_logout_hpsp_checkbox.toggled.connect(update_hp_sp_slider_display)
                self.input_fields["JOB"].currentIndexChanged.connect(update_hp_sp_slider_display)
                

                self.input_fields["BaseLv"].editingFinished.connect(update_hp_sp_slider_display)


                update_hp_sp_slider_display()
                continue



            # ✅ 已經在 MHP 那邊做掉了，MSP 這輪跳過
            if label == "MSP":
                continue
            row_layout = QHBoxLayout()
            row_layout.setAlignment(Qt.AlignLeft)
            row_label = QLabel(label)
            row_label.setFixedWidth(50)  # 可自行調整寬度
            row_layout.addWidget(row_label)
            
            if label == "JOB":
                combo = QComboBox()
                for job_id, job_info in sorted(job_dict.items()):
                    combo.addItem(job_info["name"], job_id)
                combo.currentIndexChanged.connect(self.trigger_total_effect_update)         
                #combo.currentIndexChanged.connect(filter_skills) #移動到filter_skills後面註冊
                combo.setMaximumWidth(210)#調整寬度
                self.input_fields[label] = combo
                row_layout.addWidget(combo)
                # ★ 新增：技能樹按鈕
                self.skill_btn = QPushButton(tr("button.skill_table"))
                self.skill_btn.setFixedWidth(60)  # 控制按鈕大小
                self.skill_btn.clicked.connect(self.open_skill_tree)  # 呼叫你現有的技能樹視窗
                row_layout.addWidget(self.skill_btn)
            else:
                field = QLineEdit()
                if label in default_values:
                    field.setText(str(default_values[label]))
                field.setPlaceholderText(f"{label} (get({gid}))")
                field.editingFinished.connect(self.trigger_total_effect_update)
                field.setMaximumWidth(50)#調整寬度
                self.input_fields[label] = field
                row_layout.addWidget(field)
                
                stat_names = ["STR", "AGI", "VIT", "INT", "DEX", "LUK", "POW", "STA", "WIS", "SPL", "CON", "CRT"]#ROCalculator
                if label in stat_names:
                    bonus_label = QLabel("= ?")
                    bonus_label.setFixedWidth(160)
                    bonus_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    row_layout.addWidget(bonus_label)
                    self.stat_bonus_labels[label] = bonus_label
                    if label == "VIT":
                        self.input_fields["VIT"].editingFinished.connect(update_hp_sp_slider_display)
                    if label == "INT":
                        self.input_fields["INT"].editingFinished.connect(update_hp_sp_slider_display)
                
                if label == "JobLv":
                    bonus_label = QLabel(tr("label.reserved_unused"))
                    row_layout.addWidget(bonus_label)

                # ✅ 如果是 BaseLv，就加一個 QLabel 顯示素質點
                if label == "BaseLv":
                    self.stat_point_label = QLabel(tr("label.stat_points_empty"))
                    self.stat_point_label.setFixedWidth(180)
                    row_layout.addWidget(self.stat_point_label)

                    def update_stat_point():#取自ROCalculator
                        try:
                            lv = int(self.input_fields["BaseLv"].text())
                        except:
                            self.stat_point_label.setText(tr("label.stat_points_empty"))
                            return

                        # 直接從 JOB 下拉選單取得職業 ID
                        job_id = self.input_fields["JOB"].currentData()

                        # 計算素質點
                        total_pts = calculate_stat_points(lv, job_id)

                        used_pts = sum([
                            raising_stats(self.input_fields["STR"].text()),
                            raising_stats(self.input_fields["AGI"].text()),
                            raising_stats(self.input_fields["VIT"].text()),
                            raising_stats(self.input_fields["INT"].text()),
                            raising_stats(self.input_fields["DEX"].text()),
                            raising_stats(self.input_fields["LUK"].text())
                        ])
                        remain_pts = total_pts - used_pts
                        total_tpts = get_total_tstat_points(lv)
                        tstat_used = self.calculate_tstat_total_used()
                        tstat_remain = total_tpts - tstat_used

                        #self.stat_point_label.setText(f"（素質點：{total_pts} / 已用 {used_pts} / 剩餘 {remain_pts}｜特性點：{total_tpts} / 已用 {tstat_used} / 剩餘 {tstat_remain}）")
                        self.stat_point_label.setText(tr("label.remaining_stat_points", remain_pts=remain_pts, tstat_remain=tstat_remain))
                    # ❗ BaseLv 輸入時更新
                    field.textChanged.connect(update_stat_point)
                    self._update_stat_point_callback = update_stat_point  # ✅ 暫存回呼
                 # 🟣 隱藏「石碑」相關欄位
                if label in ["石碑開啟格數", "石碑精煉"]:
                    row_label.setVisible(False)
                    field.setVisible(False)
                    continue  # 不需要顯示在角色能力區     

            
            char_layout.addLayout(row_layout)
            char_layout.setAlignment(Qt.AlignTop)


        tab_widget.addTab(char_scroll, tr("tab.character_stats"))
        update_hp_sp_slider_visibility()
        
        def make_focus_func_focus(part_label, input_field, label_name):
            '''
            鎖定選擇的裝備、卡片、詞條欄位，如果為詞條就轉到函數分頁
            '''
            def focus(event):
                self.clear_current_edit()

                self.current_edit_part = f"{part_label} - {label_name}"
                self.current_edit_label.setText(tr("label.current_part_detail", part=part_label, label=label_name))
                self.unsync_button.setVisible(True)
                self.unsync_button2.setVisible(True)
                self.apply_to_note_button.setVisible(True)
                self.clear_field_button2.setVisible(True)
                self.apply_equip_button.setVisible(True)
                self.clear_field_button.setVisible(True)
                    
                self.set_edit_lock(part_label, label_name)
                input_field.setStyleSheet("background-color: #ff0000;")  # 紅
                self._set_enchant_tool_target(
                    part_label, label_name, input_field.text().strip()
                )
                self._set_lapine_upgrade_tool_target(
                    part_label, label_name, input_field.text().strip()
                )
                self.search_input.setFocus()  # ✅ 把焦點移到搜尋欄
                # ✅ 若不是詞條，就切回裝備查詢分頁
                if label_name != "note":
                    self.tab_widget.setCurrentIndex(self.search_tab_index)

                text = input_field.text().strip()
                if text:
                    # 維持原本操作方式：查詢欄保持空白，符合項目顯示完整清單，
                    # 再直接定位目前欄位中的裝備；不把物品名稱寫進搜尋欄。
                    self._select_item_in_search_by_name(text)
                else:
                    # 空欄位時清空查詢欄；若目前已是完整清單就不重建，避免無謂卡頓。
                    if hasattr(self, "_item_search_timer"):
                        self._item_search_timer.stop()
                    was_blocked = self.search_input.blockSignals(True)
                    try:
                        self.search_input.clear()
                    finally:
                        self.search_input.blockSignals(was_blocked)

                    self._ensure_item_search_index()
                    full_list_loaded = (
                        self.result_box.count() == len(self._item_search_index)
                        and len(getattr(self, "filtered_items", {})) == len(self._item_search_index)
                    )
                    if not full_list_loaded:
                        self._last_item_search_text = None
                        self.update_combobox(initial=True)


                QLineEdit.mousePressEvent(input_field, event)
            return focus
                

        # === 分頁2：裝備設定 ===
        equip_page = QWidget()
        self.equip_page = equip_page
        equip_page_layout = QVBoxLayout(equip_page)
        equip_page_layout.setContentsMargins(0, 0, 0, 0)
        equip_page_layout.setSpacing(6)

        # ===== 上方固定快速定位列（不跟著捲）=====
        top_row = QHBoxLayout()

        title_label = QLabel(tr("label.equipment_card_settings"))
        top_row.addWidget(title_label)
        top_row.addStretch()

        self.part_nav_button = QToolButton()
        self.part_nav_button.setText(tr("button.quick_part_nav"))
        self.part_nav_button.setCursor(Qt.PointingHandCursor)
        self.part_nav_button.installEventFilter(self)
        top_row.addWidget(self.part_nav_button)

        equip_page_layout.addLayout(top_row)

        self.part_scroll_anim = None

        self.part_nav_hide_timer = QTimer(self)
        self.part_nav_hide_timer.setSingleShot(True)
        self.part_nav_hide_timer.timeout.connect(self._hide_part_nav_popup)

        # ===== 下方可捲動區 =====
        equip_scroll = QScrollArea()
        equip_scroll.setWidgetResizable(True)

        equip_inner = QWidget()
        equip_layout = QVBoxLayout(equip_inner)
        equip_scroll.setWidget(equip_inner)

        self.equip_scroll = equip_scroll
        self.refine_inputs_ui = {}
        visible_types = ["裝備", "影子", "服飾", "石碑", "寵物", "技能"]

        self._build_part_nav_popup(visible_types)

        equip_page_layout.addWidget(equip_scroll)

        for part_name, info in refine_parts.items():
            if info["type"] not in visible_types:
                continue

            slot_id = info["slot"]

            # =========================
            # 每個部位一個總容器
            # =========================
            part_container = QWidget()
            part_layout = QVBoxLayout(part_container)
            part_layout.setContentsMargins(0, 0, 0, 0)
            part_layout.setSpacing(4)

            part_ui = {}
            part_ui["container"] = part_container

            # 部位標題
            part_label = QLabel(part_name)
            part_layout.addWidget(part_label)
            part_ui["label"] = part_label

            # ▶️ 儲存 / 載入 / 下拉 / 刪除控制列
            preset_row = QHBoxLayout()

            preset_name_input = QLineEdit()
            preset_name_input.setPlaceholderText(tr("placeholder.save_name"))
            preset_name_input.setFixedWidth(160)

            save_btn = QPushButton(tr("button.save"))
            save_btn.setFixedWidth(40)
            save_btn.clicked.connect(lambda _, p=part_name: self.save_preset(p))

            manage_btn = QPushButton(tr("button.load_equipment"))
            manage_btn.clicked.connect(lambda _, p=part_name: self.open_save_manager(p))
            part_ui["manage_btn"] = manage_btn

            preset_row.addWidget(preset_name_input)
            preset_row.addWidget(save_btn)
            preset_row.addWidget(manage_btn)

            part_layout.addLayout(preset_row)

            part_ui["preset_input"] = preset_name_input

            # ▶️ 裝備欄位 + 清空
            equip_container = QWidget()
            equip_row_layout = QHBoxLayout(equip_container)
            equip_row_layout.setContentsMargins(0, 0, 0, 0)

            equip_input = QLineEdit()
            equip_input.setReadOnly(True)

            if part_name == "符文石碑":
                equip_input.setPlaceholderText(tr("placeholder.rune_name"))
            elif part_name == "寵物蛋":
                equip_input.setPlaceholderText(tr("placeholder.pet_name"))
            elif part_name == "投擲物品":
                equip_input.setPlaceholderText(tr("placeholder.throwable_name"))
            else:
                equip_input.setPlaceholderText(tr("placeholder.equipment_name"))

            equip_input.setMinimumWidth(100)
            equip_input.mousePressEvent = make_focus_func_focus(part_name, equip_input, "裝備")

            lapine_upgrade_btn = QPushButton(tr("button.enchant", "附魔"))
            lapine_upgrade_btn.setFixedWidth(40)
            lapine_upgrade_btn.setToolTip(
                "開啟 附加能力附魔資料"
            )
            lapine_upgrade_btn.setVisible(False)
            lapine_upgrade_btn.clicked.connect(
                lambda _, p=part_name: self.open_part_lapine_upgrade_tool(p)
            )

            clear_equip_btn = QPushButton(tr("button.clear"))
            clear_equip_btn.setFixedWidth(40)
            clear_equip_btn.clicked.connect(self.clear_global_state)
            clear_equip_btn.clicked.connect(lambda _, field=equip_input: [field.clear(), self.trigger_total_effect_update()])

            equip_row_layout.addWidget(equip_input)
            equip_row_layout.addWidget(clear_equip_btn)

            # ▶️ 精煉欄位
            refine_input = QLineEdit()
            refine_input.setPlaceholderText(tr("placeholder.refine"))
            refine_input.setMaximumWidth(40)
            refine_input.setText("0")
            refine_input.editingFinished.connect(self.trigger_total_effect_update)
            equip_row_layout.addWidget(refine_input)

            # ▶️ 階級下拉
            grade_combo = NoWheelComboBox()
            if part_name == "符文石碑":
                grade_combo.addItems(["0", "1", "2", "3", "4", "5", "6"])
                grade_combo.setMaximumWidth(50)
            elif part_name == "寵物蛋":
                grade_combo.addItems([tr("pet.intimacy.very_unfamiliar"), tr("pet.intimacy.slightly_unfamiliar"), tr("pet.intimacy.normal"), tr("pet.intimacy.slightly_close"), tr("pet.intimacy.very_close")])
                grade_combo.setMaximumWidth(95)
            else:
                grade_combo.addItems(["N", "D", "C", "B", "A"])
                grade_combo.setMaximumWidth(50)

            grade_combo.currentIndexChanged.connect(self.trigger_total_effect_update)
            equip_row_layout.addWidget(grade_combo)

            part_layout.addWidget(equip_container)

            part_ui["equip"] = equip_input
            part_ui["lapine_upgrade_button"] = lapine_upgrade_btn
            part_ui["equip_container"] = equip_container
            part_ui["refine"] = refine_input
            part_ui["grade"] = grade_combo

            self.input_fields[part_name] = refine_input
            self.input_fields[f"{part_name}_階級"] = grade_combo

            # 🟢 特例：符文石碑 → 同步階級與精煉到 stat_fields
            if part_name == "符文石碑":

                def sync_stone_slots_delayed():
                    val_field = self.refine_inputs_ui["符文石碑"]["grade"]
                    grade_text = val_field.currentText().strip()
                    try:
                        grade_val = int(grade_text)
                    except ValueError:
                        grade_val = val_field.currentIndex()

                    stone_slot_field = self.input_fields.get("石碑開啟格數")
                    if stone_slot_field:
                        stone_slot_field.blockSignals(True)
                        stone_slot_field.setText(str(grade_val))
                        stone_slot_field.blockSignals(False)
                    self.trigger_total_effect_update()

                def sync_stone_slots(*_):
                    QTimer.singleShot(0, sync_stone_slots_delayed)

                def sync_stone_refine():
                    val_field = self.refine_inputs_ui["符文石碑"]["refine"]
                    text_val = val_field.text().strip()
                    try:
                        val = int(text_val)
                    except ValueError:
                        val = 0

                    stone_refine_field = self.input_fields.get("石碑精煉")
                    if stone_refine_field:
                        stone_refine_field.blockSignals(True)
                        stone_refine_field.setText(str(val))
                        stone_refine_field.blockSignals(False)
                    self.trigger_total_effect_update()

                grade_combo.currentIndexChanged.connect(sync_stone_slots)
                refine_input.textChanged.connect(sync_stone_refine)

            # ▶️ 卡片欄位們 + 清空按鈕
            card_inputs = []
            card_containers = []
            enchant_buttons = []

            for i in range(4):
                card_row_layout = QHBoxLayout()
                card_row_layout.setSpacing(0)
                card_row_layout.setContentsMargins(0, 0, 0, 0)

                card_input = QLineEdit()
                card_input.setReadOnly(True)
                card_input.setPlaceholderText(tr("placeholder.card", index=i+1))
                card_input.mousePressEvent = make_focus_func_focus(part_name, card_input, f"卡片{i+1}")

                enchant_slot_btn = QPushButton(tr("button.enchant", "附魔"))
                enchant_slot_btn.setFixedWidth(40)
                enchant_slot_btn.setToolTip(
                    tr(
                        "tooltip.open_equipment_enchant_slot",
                        "開啟此裝備第{slot}洞的附魔工具",
                        slot=i + 1,
                    )
                )
                enchant_slot_btn.setVisible(False)
                enchant_slot_btn.clicked.connect(
                    lambda _, p=part_name, sid=i: self.open_part_enchant_tool(p, sid)
                )

                clear_card_btn = QPushButton(tr("button.clear"))
                clear_card_btn.setFixedWidth(40)
                clear_card_btn.clicked.connect(self.clear_global_state)
                clear_card_btn.clicked.connect(lambda _, field=card_input: [field.clear(), self.trigger_total_effect_update()])

                card_row_layout.addWidget(card_input)
                card_row_layout.addWidget(enchant_slot_btn)
                card_row_layout.addWidget(clear_card_btn)

                card_container = QWidget()
                card_container.setLayout(card_row_layout)
                part_layout.addWidget(card_container)

                card_inputs.append(card_input)
                card_containers.append(card_container)
                enchant_buttons.append(enchant_slot_btn)

            # ▶️ 詞條欄位（多行文字）+ 清空
            note_text = QTextEdit()
            note_text.setPlaceholderText(tr("placeholder.lua_function"))
            note_text.setObjectName(f"{part_name}-函數")
            note_text.setFixedSize(260, 20)
            note_text.setContentsMargins(0, 0, 0, 0)
            note_text.setReadOnly(True)
            note_text.setVisible(False)
            note_text.textChanged.connect(self.on_function_text_changed)

            note_text_ui = QTextEdit()
            note_text_ui.setPlaceholderText(tr("placeholder.custom_option_effect"))
            note_text_ui.setObjectName(f"{part_name}-詞條")
            # 詞條列總寬固定為 300px；Lapine 按鈕顯示時只縮小詞條 box。
            note_text_ui.setFixedSize(255, 20)
            note_text_ui.setContentsMargins(0, 0, 0, 0)
            note_text_ui.setReadOnly(True)
            note_text_ui.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            note_text_ui.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            note_text_ui.mousePressEvent = lambda event, p=part_name, w=note_text_ui, u=note_text: self.handle_note_text_clicked(event, p, w, u)

            clear_note_btn = QPushButton(tr("button.clear"))
            clear_note_btn.setFixedWidth(40)
            clear_note_btn.clicked.connect(self.clear_global_state)
            clear_note_btn.clicked.connect(lambda _, field=note_text: [field.clear(), self.trigger_total_effect_update()])

            # 詞條區：
            # 左側 = 紅色詞條 BOX
            # 右側 = 按鈕上下排列：附魔在上、清空在下
            #
            #   ┌──────────────────────┐ [附魔]
            #   │ 詞條內容             │
            #   │                      │
            #   └──────────────────────┘ [清空]
            note_container = QWidget()
            note_container_layout = QHBoxLayout(note_container)
            note_container_layout.setContentsMargins(0, 0, 0, 0)
            note_container_layout.setSpacing(5)

            # 真正 Lua 文字欄仍保留，但本來就是隱藏的，不需要佔 layout 空間。
            note_container_layout.addWidget(note_text_ui)

            note_button_column = QWidget()
            note_button_column.setFixedWidth(40)
            note_button_layout = QVBoxLayout(note_button_column)
            note_button_layout.setContentsMargins(0, 0, 0, 0)
            note_button_layout.setSpacing(3)

            note_button_layout.addWidget(lapine_upgrade_btn, 0, Qt.AlignTop)
            note_button_layout.addStretch(1)
            note_button_layout.addWidget(clear_note_btn, 0, Qt.AlignBottom)

            note_container_layout.addWidget(note_button_column)
            note_container.setFixedWidth(300)

            part_layout.addWidget(note_container)

            part_ui["note"] = note_text
            part_ui["note_ui"] = note_text_ui
            part_ui["note_container"] = note_container
            part_ui["note_button_column"] = note_button_column
            part_ui["cards"] = card_inputs
            part_ui["card_containers"] = card_containers
            part_ui["enchant_buttons"] = enchant_buttons

            # 最後再把整個部位丟進主 layout
            equip_layout.addWidget(part_container)

            self.refine_inputs_ui[part_name] = part_ui
            equip_input.textChanged.connect(
                lambda text, p=part_name: self._update_enchant_button_for_part(p, text)
            )
            equip_input.textChanged.connect(
                lambda text, p=part_name: self._update_lapine_upgrade_button_for_part(p, text)
            )
            equip_input.textChanged.connect(
                lambda _text, p=part_name: self._sync_open_enchant_tool_context(p)
            )
            equip_input.textChanged.connect(
                lambda _text, p=part_name: self._sync_open_lapine_upgrade_tool_context(p)
            )
            for card_input in card_inputs:
                card_input.textChanged.connect(
                    lambda _text, p=part_name: self._sync_open_enchant_tool_context(p)
                )
            self._update_enchant_button_for_part(part_name, equip_input.text())
            self._update_lapine_upgrade_button_for_part(part_name, equip_input.text())
            self.refresh_presets(part_name)

            # 🟢 特例：符文石碑 / 寵物蛋 / 投擲物品 → 隱藏卡片與詞條欄位
            if part_name in ("符文石碑", "寵物蛋", "投擲物品"):
                for w in part_ui["card_containers"]:
                    w.setVisible(False)

                if "note_container" in part_ui:
                    part_ui["note_container"].setVisible(False)

                if part_name == "投擲物品":
                    part_ui["refine"].setVisible(False)
                    part_ui["grade"].setVisible(False)

                if part_name == "寵物蛋" and "refine" in part_ui:
                    part_ui["refine"].setVisible(False)

            # 技能只顯示詞條
            if part_name == "技能":
                part_ui["equip_container"].setVisible(False)

                for w in part_ui["card_containers"]:
                    w.setVisible(False)

                part_ui["refine"].setVisible(False)
                part_ui["grade"].setVisible(False)

        tab_widget.addTab(equip_page, tr("tab.equipment_settings"))
        
        # 建立 UI 時保存部位設定
        self.refine_parts = refine_parts

        # === 新增技能分頁（含搜尋） ===
        skill_page = QWidget()
        skill_layout = QVBoxLayout(skill_page)

        # 搜尋欄位
        search_layout = QHBoxLayout()
        search_label = QLabel(tr("label.search_skill_food"))
        self.skill_search_bar = QLineEdit()
        self.skill_search_bar.setPlaceholderText(tr("placeholder.search_skill_food"))
        self.skill_search_bar.textChanged.connect(self.filter_skill_list)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.skill_search_bar)
        skill_layout.addLayout(search_layout)

        # 技能清單區塊（可滾動）
        self.skill_checkbox_area = QWidget()
        self.skill_checkbox_layout = QVBoxLayout(self.skill_checkbox_area)
        self.skill_checkbox_layout.setAlignment(Qt.AlignTop)

        self.skill_checkboxes = {}
        self.exclusive_groups = {}   # { group_name: [checkbox1, checkbox2] }

        for name, data in all_skill_entries.items():
            checkbox = QCheckBox(f"{data['type']} {name}")
            self.skill_checkboxes[name] = checkbox

            #checkbox.stateChanged.connect(self.clear_global_state)
            checkbox.stateChanged.connect(self.trigger_total_effect_update)
            checkbox.stateChanged.connect(self.update_skill_food_tab_checked_count)

            # 判斷此技能是否有 exclusive 群組
            if "exclusive" in data:
                group = data["exclusive"]
                self.exclusive_groups.setdefault(group, []).append(checkbox)

                # 連接 "可取消" 的互斥控制函數
                checkbox.toggled.connect(
                    lambda checked, c=checkbox, g=group: self.handle_exclusive_toggle(c, g, checked)
                )


        # ✅ 建完後，用排序/搜尋規則把 checkbox 加到 layout
        self.refresh_skill_list()

        self.input_fields["JOB"].currentIndexChanged.connect(self.refresh_skill_list)#註冊下拉職業清單依照職業排序

            

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.skill_checkbox_area)

        # ✅ 讓技能清單填滿底部空間
        skill_layout.addWidget(scroll, stretch=1)

        # 加入主分頁，並保存分頁物件與索引供勾選數量即時更新。
        self.skill_food_tab_widget = tab_widget
        self.skill_food_tab_index = tab_widget.addTab(skill_page, tr("tab.buff_skill_food"))
        self.update_skill_food_tab_checked_count()



        # 先把 tab_widget 存起來（可選）
        self.tab_widget = tab_widget

        # ✅ 用一個容器把「tab + 狀態」上下包在一起
        left_panel = QWidget()
        left_panel.setFixedWidth(340)  

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # 上：三個分頁
        left_layout.addWidget(self.tab_widget, stretch=1)

        # 下：狀態區
        self.status_box = QGroupBox("攻速/詠唱顯示 [括弧內為技能需求秒數]")
        self.status_box.setMinimumHeight(100)  
        status_layout = QVBoxLayout(self.status_box)

        # self.status_label = QLabel("（狀態顯示區）")
        # self.status_label.setWordWrap(True)
        # status_layout.addWidget(self.status_label)
        # === 計算素質無詠 ===
        
        self.DEX_INT_265_label = QLabel(tr("label.instant_cast_calc"))
        status_layout.addWidget(self.DEX_INT_265_label)
        self.fix_label = QLabel("fix")
        status_layout.addWidget(self.fix_label)
        self.Delay_label = QLabel("Delay")
        status_layout.addWidget(self.Delay_label)
        self.ASPD_label = QLabel("ASPD")
        status_layout.addWidget(self.ASPD_label)
        self.cast_bar = CastBarWidget(self)#詠唱條
        status_layout.addWidget(self.cast_bar)
        left_layout.addWidget(self.status_box, stretch=0)

        # ✅ 只加 left_panel 進去
        main_layout.addWidget(left_panel, 2)


        

        # ===== 中間：裝備查詢區塊 =====
        # 建立 TabWidget
        self.tab_widget = QTabWidget()

        # ====== 原本裝備查詢頁 ======
        middle_widget = QWidget()
        middle_layout = QVBoxLayout(middle_widget)
        # ...原本裝備查詢內容塞進 middle_layout...
        middle_scroll = QScrollArea()
        middle_scroll.setWidgetResizable(True)
        middle_scroll.setWidget(middle_widget)
        middle_scroll.setFixedWidth(500)

        equip_tab = QWidget()
        equip_layout = QVBoxLayout(equip_tab)
        equip_layout.addWidget(middle_scroll)
        self.search_tab_index = self.tab_widget.addTab(equip_tab, tr("tab.equipment_search"))


        # ▶️ 編輯狀態 + 解除同步按鈕 + 全域精煉選單
        edit_status_layout = QHBoxLayout()
        self.current_edit_label = QLabel(tr("label.current_part"))

        self.unsync_button = QPushButton(tr("button.unlock"))
        self.unsync_button.setVisible(False)
        self.unsync_button.clicked.connect(self.clear_global_state)
        self.unsync_button.clicked.connect(self.clear_current_edit)
        self.unsync_button.clicked.connect(lambda: (setattr(self, "_last_calc_state", None), self.trigger_total_effect_update()))
        # ▶️ 套用按鈕
        self.apply_equip_button = QPushButton(tr("button.apply"))
        self.apply_equip_button.clicked.connect(self.clear_global_state)
        self.apply_equip_button.clicked.connect(self.apply_selected_equip)     
        self.apply_equip_button.clicked.connect(lambda: (setattr(self, "_last_calc_state", None), self.trigger_total_effect_update()))
        self.apply_equip_button.setVisible(False)
        
        self.clear_field_button = QPushButton(tr("button.clear"))
        self.clear_field_button.clicked.connect(self.clear_global_state)
        self.clear_field_button.clicked.connect(self.clear_selected_field)  
        self.clear_field_button.clicked.connect(lambda: (setattr(self, "_last_calc_state", None), self.trigger_total_effect_update()))
        self.clear_field_button.setVisible(False)


        # ✅ 全域精煉與階級欄位
        self.global_refine_input = QLineEdit()
        self.global_refine_input.setPlaceholderText(tr("placeholder.global_refine"))
        self.global_refine_input.setMaximumWidth(40)

        self.global_grade_combo = QComboBox()
        self.global_grade_combo.addItems(["N", "D", "C", "B", "A"])
        self.global_grade_combo.setMaximumWidth(50)
        self.global_refine_input.textChanged.connect(self.display_item_info)
        self.global_grade_combo.currentIndexChanged.connect(self.display_item_info)

        # 預設隱藏（只有在未編輯狀態時顯示）
        self.global_refine_input.setVisible(True)
        self.global_grade_combo.setVisible(True)

        
        # 擺進橫向排版
        edit_status_layout.addWidget(self.current_edit_label)
        edit_status_layout.addWidget(self.clear_field_button)
        edit_status_layout.addWidget(self.apply_equip_button)
        edit_status_layout.addWidget(self.unsync_button)
        edit_status_layout.addWidget(self.global_refine_input)
        edit_status_layout.addWidget(self.global_grade_combo)

        middle_layout.addLayout(edit_status_layout)
        def add_labeled_row(layout, label_text, widget, label_width=80):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setFixedWidth(label_width)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row.addWidget(label)
            row.addWidget(widget)
            layout.addLayout(row)

        # 使用函式新增橫向排列項目
        add_labeled_row(middle_layout, "查詢關鍵字", self.search_input)
        add_labeled_row(middle_layout, "符合項目", self.result_box)
        
        # 物品下拉選單右側提供 Divine Pride 外部資料連結。
        result_selector_widget = QWidget()
        result_selector_layout = QHBoxLayout(result_selector_widget)
        result_selector_layout.setContentsMargins(0, 0, 0, 0)
        result_selector_layout.setSpacing(6)
        middle_layout.addWidget(self.divine_pride_button)
        #add_labeled_row(middle_layout, "中文名稱", self.name_field)
        #add_labeled_row(middle_layout, "韓文名稱", self.kr_name_field)
        #add_labeled_row(middle_layout, "鑲嵌孔數", self.slot_field)
        #middle_layout.addWidget(QLabel("物品說明"))
        middle_layout.addWidget(self.desc_text)
        middle_layout.addWidget(QLabel(tr("label.set_list")))
        self.Combi_text.setFixedHeight(160)
        middle_layout.addWidget(self.Combi_text)
        self.btn_recompile = QPushButton(tr("button.recompile_items"))
        self.btn_recompile.clicked.connect(self.recompile)
        #middle_layout.addWidget(self.btn_recompile)
        #self.btn_recompile.setVisible(False)#重新編譯先隱藏

        # 限制寬度，但允許在範圍內隨視窗伸縮
        self.result_box.setMinimumWidth(220)
        self.result_box.setMaximumWidth(420)
        self.result_box.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed
        )

        # 不要讓最長的項目決定 ComboBox 的寬度
        self.result_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.result_box.setMinimumContentsLength(20)

        # 下拉清單文字過長時顯示 ...
        self.result_box.view().setTextElideMode(Qt.ElideRight)


        # ====== 技能指令分頁 ======
        function_tab = QWidget()
        function_layout = QVBoxLayout(function_tab)

        # 建立第1個橫向 layout（標籤 + 解鎖）
        edit_function_layout = QHBoxLayout()

        self.function_selector = QComboBox()
        self.function_selector.setMaximumWidth(200)
        self.update_function_selector()

        self.se_function = QLabel(tr("label.select_function"))
        self.unsync_button2 = QPushButton(tr("button.unlock"))
        self.unsync_button2.setVisible(False)
        self.unsync_button2.clicked.connect(self.clear_global_state)
        self.unsync_button2.clicked.connect(self.clear_current_edit)
        self.unsync_button2.clicked.connect(lambda: (setattr(self, "_last_calc_state", None), self.trigger_total_effect_update()))
        self.apply_to_note_button = QPushButton(tr("button.apply_to_option"))
        self.apply_to_note_button.setVisible(False)
        self.apply_to_note_button.clicked.connect(self.clear_global_state)
        self.apply_to_note_button.clicked.connect(self.apply_result_to_note)
        self.apply_to_note_button.clicked.connect(lambda: (setattr(self, "_last_calc_state", None), self.trigger_total_effect_update()))



        
        self.clear_field_button2 = QPushButton(tr("button.clear"))
        self.clear_field_button2.clicked.connect(self.clear_global_state)
        self.clear_field_button2.clicked.connect(self.clear_selected_field)
        self.clear_field_button2.clicked.connect(lambda: (setattr(self, "_last_calc_state", None), self.trigger_total_effect_update()))
        
        self.clear_field_button2.setVisible(False)

        # 🔍 建立全域技能搜尋欄位（放在你想要的位置）
        self.skill_search_input = QLineEdit()
        self.skill_search_input.setPlaceholderText(tr("placeholder.search_skill"))
        self.skill_search_input.setVisible(False)
        
        
        edit_function_layout.addWidget(self.se_function)
        edit_function_layout.addWidget(self.skill_search_input)
        edit_function_layout.addWidget(self.clear_field_button2)
        edit_function_layout.addWidget(self.apply_to_note_button)

        edit_function_layout.addWidget(self.unsync_button2)
        function_layout.addLayout(edit_function_layout)

        # ✅ 建立第2個橫向 layout（函數選單 + 參數欄位）
        edit_function_layout2 = QHBoxLayout()  # 你漏了這行

        edit_function_layout2.addWidget(self.function_selector)


        # ✅ 參數區改用 HBoxLayout
        self.param_layout = QHBoxLayout()
        self.param_widgets = []
        edit_function_layout2.addLayout(self.param_layout)

        function_layout.addLayout(edit_function_layout2)

        # ===== 條件產生器：與下方 FunctionSyntaxTextEdit 共用 CONDITION_* 定義 =====
        # 分成兩行，避免條件列把視窗橫向撐得太長。
        # 第一行：條件種類 + 左值
        # 第二行：比較運算子 + 右值 + 插入按鈕
        condition_layout = QVBoxLayout()
        condition_layout.setContentsMargins(0, 0, 0, 0)
        condition_layout.setSpacing(3)

        condition_row1 = QHBoxLayout()
        condition_row1.addWidget(QLabel("條件："))

        self.condition_kind_combo = QComboBox()
        self.condition_kind_combo.setFixedWidth(95)
        self.condition_kind_combo.addItem("IF", "if")
        self.condition_kind_combo.addItem("ELIF / ELSEIF", "elseif")
        self.condition_kind_combo.addItem("ELSE", "else")
        self.condition_kind_combo.addItem("END", "end")
        condition_row1.addWidget(self.condition_kind_combo)

        self.condition_left_combo = QComboBox()
        self.condition_left_combo.setEditable(True)
        self.condition_left_combo.setMinimumWidth(260)
        self.condition_left_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.condition_left_combo.setMinimumContentsLength(24)
        for spec in CONDITION_VALUE_DEFS.values():
            self.condition_left_combo.addItem(spec["label"], spec["syntax"])
        if self.condition_left_combo.count() > 0:
            self.condition_left_combo.setEditText(str(self.condition_left_combo.itemData(0)))
        condition_row1.addWidget(self.condition_left_combo, 1)
        #condition_layout.addLayout(condition_row1)#先隱藏 ui調整後再開啟

        # 從 == / >= / <= ... 開始換到第二行。
        condition_row2 = QHBoxLayout()

        self.condition_operator_combo = QComboBox()
        self.condition_operator_combo.setFixedWidth(115)
        for op, label in CONDITION_OPERATORS.items():
            self.condition_operator_combo.addItem(f"{op}  {label}", op)
        condition_row2.addWidget(self.condition_operator_combo)

        self.condition_right_input = QLineEdit()
        self.condition_right_input.setPlaceholderText("數值 / 變數 / 公式")
        self.condition_right_input.setMinimumWidth(120)
        condition_row2.addWidget(self.condition_right_input, 1)

        self.condition_gen_button = QPushButton("插入條件")
        condition_row2.addWidget(self.condition_gen_button)
        condition_layout.addLayout(condition_row2)

        #function_layout.addLayout(condition_layout)#先隱藏 ui調整後再開啟

        # 按鈕
        self.gen_button = QPushButton(tr("button.generate"))
        function_layout.addWidget(self.gen_button)
        # 結果輸出
        self.result_output = FunctionSyntaxTextEdit()
        self.result_output.set_function_defs(function_defs)
        self.update_function_autocomplete_maps()
        #self.result_output.setReadOnly(True)
        function_layout.addWidget(QLabel(tr("label.generated_syntax")))
        function_layout.addWidget(self.result_output)

        # 加入這段到合適 layout 中（中間區塊）
        self.syntax_result_label = QLabel(tr("label.syntax_parse_result"))
        self.syntax_result_box = QTextEdit()
        self.syntax_result_box.setReadOnly(True)

        function_layout.addWidget(self.syntax_result_label)
        function_layout.addWidget(self.syntax_result_box)

        # 分頁加入
        self.function_tab_index = self.tab_widget.addTab(function_tab, tr("tab.function_commands"))
        main_layout.addWidget(self.tab_widget)

        # 預先初始化一次

        





        # ===== 右側：模擬結果 + 裝備原始屬性 =====
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(right_widget)


        # ===== Timer =====
        self._calc_timer = QTimer(self)
        self._calc_timer.setSingleShot(True)
        self._calc_timer.setInterval(80)
        self._calc_timer.timeout.connect(self._perform_total_effect_update)


        # ===== 裝備原始內容 =====
        self.equip_text_label = QLabel(tr("label.raw_equipment_text"))
        right_layout.addWidget(self.equip_text_label)

        right_layout.addWidget(self.equip_text)
        self.equip_text.setFixedHeight(160)

        right_layout.addWidget(self.combi_raw_text)
        self.combi_raw_text.setFixedHeight(160)


        # ===== 效果解析 + 計算狀態，同一列 =====
        sim_effect_title_layout = QHBoxLayout()

        sim_effect_title_layout.addWidget(self.sim_effect_label)

        sim_effect_title_layout.addStretch()

        self.calc_status_label = QLabel("")
        self.calc_status_label.setMinimumWidth(120)
        self.calc_status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sim_effect_title_layout.addWidget(self.calc_status_label)

        right_layout.addLayout(sim_effect_title_layout)


        # === 效果解析分頁（兩個頁籤） ===
        self.sim_tabs = QTabWidget()
        right_layout.addWidget(self.sim_tabs)

        # 分頁1：單件裝備效果
        self.sim_effect_text = QTextEdit()
        self.sim_effect_text.setReadOnly(True)
        self.sim_tabs.addTab(self.sim_effect_text, tr("tab.current_equipment_effect"))

        # 分頁2：總合套裝效果
        self.combo_effect_text = QTextEdit()
        self.combo_effect_text.setReadOnly(True)
        self.sim_tabs.addTab(self.combo_effect_text, tr("tab.overall_set_effect"))
        
        
        # 建立 總效果分頁 的容器
        total_tab_layout = QVBoxLayout()
        total_filter_input_sort_mode_combo = QHBoxLayout()

        # 🔍 篩選輸入欄
        self.total_filter_input = QLineEdit()
        self.total_filter_input.setPlaceholderText(tr("placeholder.filter_total_effect"))
        self.total_filter_input.textChanged.connect(self.update_total_effect_display)        
        total_filter_input_sort_mode_combo.addWidget(self.total_filter_input)
        
        # 排序方式下拉選單
        self.sort_mode_combo = QComboBox()
        self.sort_mode_combo.addItems([
            "來源順序",          
            "依名稱",
            "增傷詞條",
            "ROCalculator輸入"
        ])
        self.sort_mode_combo.setCurrentText("增傷詞條")  # ✅ 預設選這個
        self.sort_mode_combo.currentIndexChanged.connect(self.trigger_total_effect_update)
        total_filter_input_sort_mode_combo.addWidget(self.sort_mode_combo)
        total_tab_layout.addLayout(total_filter_input_sort_mode_combo)
        
        # 📄 整體總效果文字框
        self.total_effect_text = QTextEdit()
        self.total_effect_text.setReadOnly(True)        
        total_tab_layout.addWidget(self.total_effect_text)

        # 將 layout 放進 QWidget，再加進分頁
        total_tab_widget = QWidget()
        total_tab_widget.setLayout(total_tab_layout)
        self.sim_tabs.addTab(total_tab_widget, tr("tab.overall_total_effect"))




        # 模擬效果隱藏選項
        self.hide_unrecognized_checkbox = QCheckBox(tr("checkbox.hide_unrecognized"))
        self.hide_unrecognized_checkbox.setChecked(True)  # 預設勾選
        
        self.hide_unrecognized_checkbox.stateChanged.connect(self.trigger_total_effect_update)
        #self.hide_unrecognized_checkbox.stateChanged.connect(self.display_item_info)
        #不控制裝備屬性原始內容顯示就註解掉下面那行
        self.hide_unrecognized_checkbox.stateChanged.connect(self.toggle_equip_text_visibility)
        right_layout.addWidget(self.hide_unrecognized_checkbox)
        
        # 效果解析下方
        self.hide_physical_checkbox = QCheckBox(tr("checkbox.hide_physical"))
        self.hide_magical_checkbox = QCheckBox(tr("checkbox.hide_magical"))
        
        self.hide_physical_checkbox.stateChanged.connect(self.trigger_total_effect_update)
        self.hide_magical_checkbox.stateChanged.connect(self.trigger_total_effect_update)
        #self.hide_physical_checkbox.stateChanged.connect(self.display_item_info)
        #self.hide_magical_checkbox.stateChanged.connect(self.display_item_info)
        # ✅ 套裝來源顯示勾選框
        self.show_combo_source_checkbox = QCheckBox(tr("checkbox.show_source"))
        self.show_combo_source_checkbox.setChecked(True)  # 預設勾選
        
        self.show_combo_source_checkbox.stateChanged.connect(self.trigger_total_effect_update)
        #self.show_combo_source_checkbox.stateChanged.connect(self.display_all_effects)

        # 減傷倍率下拉選單
        self.damage_reduction_label = QLabel(tr("label.damage_reduction"))
        self.damage_reduction_combobox = QComboBox()
        self.damage_reduction_combobox.addItems(["100%" ,"10%", "1%", "0.1%"])
        self.damage_reduction_combobox.setCurrentIndex(0)
        self.damage_reduction_combobox.currentIndexChanged.connect(self.trigger_total_effect_update)  # 有需要就綁定 signal

        
        

        checkbox_layout = QHBoxLayout()
        checkbox_layout.addWidget(self.hide_unrecognized_checkbox)
        checkbox_layout.addWidget(self.show_combo_source_checkbox)
        checkbox_layout.addWidget(self.hide_physical_checkbox)
        checkbox_layout.addWidget(self.hide_magical_checkbox)
        checkbox_layout.addWidget(self.damage_reduction_label)
        checkbox_layout.addWidget(self.damage_reduction_combobox)
        
        right_layout.addLayout(checkbox_layout)

        # 建立新分頁：傷害計算
        self.custom_calc_tab = QWidget()
        layout = QVBoxLayout(self.custom_calc_tab)

        # 多行文字框
        #self.custom_calc_box = QTextEdit()
        #layout.addWidget(self.custom_calc_box)
        
        # 多行文字框
        self.custom_calc_box = QTextEdit()
        monospace_font = QFont("MingLiU")  # 或你喜歡的等寬字體，例如 "Courier New"
        monospace_font.setStyleHint(QFont.Monospace)
        #monospace_font.setPointSize(11)  # 依你的 UI 調整字體大小
        self.custom_calc_box.setFont(monospace_font)

        layout.addWidget(self.custom_calc_box)

        
        
        
        def filter_skills():
            text = self.skill_filter_input.text().strip().lower()
            self.skill_box.blockSignals(True)  # 暫時停止訊號，避免重複觸發

            self.skill_box.clear()

            for key, display_name in skill_map.items():
                skill_data = skill_map_all.get(key)
                slv = skill_data.get("Slv") if skill_data else None
                code = skill_data.get("Code") if skill_data else None
                job_id = self.input_fields["JOB"].currentData()#取得職業ID
                skill_job_box = job_dict[job_id]["selectskill"]#取得職業ID技能代號(過濾用)

                # 以 '/' 分隔出多個職業前綴
                job_prefixes = set(skill_job_box.split('/'))
                #print(f"過濾的前置:{job_prefixes}，取得職業代號:{skill_job_box}，取得職業ID:{job_id}，取得code:{code}")
                # 無搜尋文字時，只顯示有 Slv 的技能
                if text == "":
                    # 過濾 Slv 為空、空字串、None、NaN 
                    #if pd.notna(slv) and str(slv).strip() != "":
                    #   self.skill_box.addItem(skill_map[key], key)

                    # 只過濾skill_job_box
                    #if code and '_' in code:
                    #    code_prefix = code.split('_')[0]
                    #    if code_prefix in job_prefixes:
                    #        self.skill_box.addItem(skill_map[key], key)

                    # 1. Slv 不能為空、空字串、None、NaN
                    # 2. code 必須有，且 '_' 分割後的前綴必須在職業前綴清單裡
                    if pd.notna(slv) and str(slv).strip() != "":
                        if code and '_' in code:
                            code_prefix = code.split('_')[0]
                            if code_prefix in job_prefixes:
                                self.skill_box.addItem(skill_map[key], key)
                else:
                    # 有搜尋時顯示所有技能（包含沒有 Slv）
                    if text in display_name.lower():
                        self.skill_box.addItem(display_name, key)

            self.skill_box.blockSignals(False)
            self.filter_skills = filter_skills

            # 若有項目，自動選第一個並更新顯示
            if self.skill_box.count() > 0:
                self.skill_box.setCurrentIndex(0)
                update_skill_formula_display()
            else:
                # 清空顯示
                self.skill_formula_result_input.setText("0%")
                self.skill_LV_input.setText("0")
                self.skill_hits_input.setText("")

        combo.currentIndexChanged.connect(filter_skills)#註冊JOB變更時過濾技能列表
        combo.currentIndexChanged.connect(update_stat_point)  # 更新職業是否擴充判斷總素質點
        combo.currentIndexChanged.connect(update_hp_sp_slider_visibility)#更新HPSP滑桿顯示

        
        skill_select_layout_top = QHBoxLayout()
        skill_select_layout_bottom = QHBoxLayout()

        # 技能過濾輸入欄
        self.skill_filter_input = QLineEdit()
        self.skill_filter_input.setPlaceholderText(tr("placeholder.filter_skill"))
        self.skill_filter_input.setFixedWidth(80)
        skill_select_layout_top.addWidget(self.skill_filter_input)

        # 🔹 清空按鈕
        self.clear_filter_button = QPushButton(tr("button.clear"))
        self.clear_filter_button.setFixedWidth(50)
        self.clear_filter_button.setToolTip(tr("tooltip.clear_filter"))
        self.clear_filter_button.clicked.connect(self.skill_filter_input.clear)
        skill_select_layout_top.addWidget(self.clear_filter_button)

        # 綁定過濾事件
        self.skill_filter_input.textChanged.connect(filter_skills)
        


        def update_skill_formula_display():
            current_data = self.skill_box.currentData()
            skill_data = skill_map_all.get(current_data)

            # 沒有資料時清空
            if not skill_data or not skill_data.get("Calculation"):
                self.skill_formula_result_input.setText("0%")
                self.skill_LV_input.setText("0")
                self.skill_hits_input.setText("")
                return

            # 技能公式
            formula = skill_data.get("Calculation", "")
            self.skill_formula_input.setText(str(formula))

            # 技能等級
            skill_lv_raw = skill_data.get("Slv", "")
            try:
                lv = float(skill_lv_raw)
                self.skill_LV_input.setText(f"{lv:.0f}")
            except:
                lv = 1
                self.skill_LV_input.setText("")

            # 打擊次數（支援公式 + 負數）
            skill_hits = skill_data.get("hits", "")
            try:
                expr = sympify(str(skill_hits))
                hits_result = int(expr.evalf(subs={"Sklv": lv}))
                self.skill_hits_input.setText(f"{hits_result}")
            except:
                self.skill_hits_input.setText(str(skill_hits))





            # 設定屬性下拉
            element_key = skill_data.get("element", "")
            index = self.attack_element_box.findData(element_key)
            if index != -1:
                self.attack_element_box.blockSignals(True)
                try:
                    self.attack_element_box.setCurrentIndex(index)
                finally:
                    self.attack_element_box.blockSignals(False)

            # 統一走 debounce 排程，只保留最後一次計算結果。
            self.trigger_total_effect_update()

        # 技能下拉選單
        self.skill_box = QComboBox()
        self.skill_box.setFixedWidth(160)

        for key in skill_map:
            skill_data = skill_map_all.get(key)
            slv = skill_data.get("Slv") if skill_data else None
            code = skill_data.get("Code") if skill_data else None
            job_id = self.input_fields["JOB"].currentData()#取得職業ID
            skill_job_box = job_dict[job_id]["selectskill"]#取得職業ID技能代號(過濾用)

            # 以 '/' 分隔出多個職業前綴
            job_prefixes = set(skill_job_box.split('/'))

            # 過濾 Slv 為空、空字串、None、NaN 
            #if pd.notna(slv) and str(slv).strip() != "":
            #   self.skill_box.addItem(skill_map[key], key)

            #過濾職業技能
            #if code and '_' in code:
            #    code_prefix = code.split('_')[0]
            #    if code_prefix in job_prefixes:
            #        self.skill_box.addItem(skill_map[key], key)

            # 1. Slv 不能為空、空字串、None、NaN
            # 2. code 必須有，且 '_' 分割後的前綴必須在職業前綴清單裡
            if pd.notna(slv) and str(slv).strip() != "":
                if code and '_' in code:
                    code_prefix = code.split('_')[0]
                    if code_prefix in job_prefixes:
                        self.skill_box.addItem(skill_map[key], key)

        # 綁定更新函式
        self.skill_box.currentIndexChanged.connect(update_skill_formula_display)


        skill_select_layout_top.addWidget(self.skill_box)

        # 技能等級
        self.skill_LV_input = QLineEdit()
        self.skill_LV_input.setPlaceholderText(tr("placeholder.skill_level"))
        #self.skill_LV_input.setReadOnly(True)
        self.skill_LV_input.setFixedWidth(40)
        skill_select_layout_top.addWidget(self.skill_LV_input)

        # 攻擊屬性
        self.attack_element_box = QComboBox()
        for key in range(0, 10):
            self.attack_element_box.addItem(element_map[key], key)
        self.attack_element_box.setFixedWidth(80)
        skill_select_layout_top.addWidget(self.attack_element_box)
        
        # 公式結果欄
        
        self.skill_hits_input = QLineEdit()
        self.skill_hits_input.setPlaceholderText(tr("placeholder.hit_count"))
        self.skill_hits_input.setText("1")
        self.skill_hits_input.setReadOnly(True)
        self.skill_hits_input.setFixedWidth(120)
        skill_select_layout_top.addWidget(self.skill_hits_input)


        # 技能公式欄
        self.skill_formula_input = QLineEdit()
        self.skill_formula_input.setPlaceholderText(tr("placeholder.skill_formula"))
        self.skill_formula_input.setFixedWidth(480)
        skill_select_layout_bottom.addWidget(self.skill_formula_input)

        # 公式結果欄
        self.skill_formula_result_input = QLineEdit()
        self.skill_formula_result_input.setPlaceholderText(tr("placeholder.formula_result"))
        self.skill_formula_result_input.setReadOnly(True)
        self.skill_formula_result_input.setFixedWidth(120)
        skill_select_layout_bottom.addWidget(self.skill_formula_result_input)
        

        
        layout.insertLayout(0, skill_select_layout_top)
        layout.insertLayout(1, skill_select_layout_bottom)
        
        # 建立水平區塊
        button_row = QHBoxLayout()

        # 多裝備比對
        self.multi_compare_button = QPushButton("多裝備比對")
        self.multi_compare_button.clicked.connect(self.open_multi_compare)
        button_row.addWidget(self.multi_compare_button)


        self.save_compare_button = QPushButton(tr("button.save_compare_baseline"))
        self.save_compare_button.clicked.connect(self.save_compare_base)

        button_row.addWidget(self.save_compare_button)

        # 中間新增勾選框
        self.auto_compare_checkbox = QCheckBox(tr("checkbox.continuous_compare"))
        button_row.addWidget(self.auto_compare_checkbox)
        

        self.compare_button = QPushButton(tr("button.run_compare"))
        self.compare_button.clicked.connect(self.compare_with_base)
        button_row.addWidget(self.compare_button)
        
        # self.reskill_map_button = QPushButton("重新載入技能表")
        # self.reskill_map_button.clicked.connect(load_skill_map)
        # self.reskill_map_button.clicked.connect(filter_skills)
        
        # button_row.addWidget(self.reskill_map_button)
        self.skillEditor_button = QPushButton(tr("button.edit_skill"))
        self.skillEditor_button.clicked.connect(lambda: open_skill_editor(self))
        button_row.addWidget(self.skillEditor_button)

        # 把這整排按鈕加進主 layout（通常是 QVBoxLayout）
        layout.addLayout(button_row)


        # 插入分隔線（放在第 2 行之後）
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.insertWidget(2, separator)
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.insertWidget(4, separator)

        # === 特殊效果勾選區塊 ===

        # 使用 QGridLayout 來自動排版，每行最多放 4 個
        special_checkbox_layout = QGridLayout()
        
        # 特殊效果增傷處理區
        self.special_checkboxes = {
            "wanzih_checkbox": QCheckBox(tr("buff.wanzih_peak4")),
            "poison_weak_checkbox": QCheckBox(tr("buff.poison_weak")),
            "magic_poison_checkbox": QCheckBox(tr("buff.magic_poison")),
            "attribute_seal_checkbox": QCheckBox(tr("buff.attribute_seal")),
            "sneak_attack_checkbox": QCheckBox(tr("buff.sneak_attack")),
            "SPORE_attack_checkbox": QCheckBox(tr("buff.spore_attack")),            
            "DARKCROW_attack_checkbox": QCheckBox(tr("buff.darkcrow_attack")),
            "RUSH_attack_checkbox": QCheckBox(tr("buff.rush_attack")),            
            "OLEUM_attack_checkbox": QCheckBox(tr("buff.oleum_attack")),
            "PR_LEXAETERNA_checkbox": QCheckBox(tr("buff.lexaeterna")),
            #"SH_HOWLING_OF_CHUL_HO_checkbox": QCheckBox("鐵虎咆嘯"),



            # 可在這裡繼續新增更多項目
        }


        # 加入 layout（最多每行 4 個）
        max_per_row = 5
        for index, (key, checkbox) in enumerate(self.special_checkboxes.items()):
            row = index // max_per_row
            col = index % max_per_row
            special_checkbox_layout.addWidget(checkbox, row, col)

        layout.addLayout(special_checkbox_layout)
        
        # ✅ 在這裡綁定觸發
        for checkbox in self.special_checkboxes.values():
            checkbox.stateChanged.connect(self.trigger_total_effect_update)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.insertWidget(6, separator)


        # === 建立目標設定區塊 ===
        target_layout = QHBoxLayout()

        # 建立下拉選單函式
        def make_combobox(label_text, options, visible_keys=None):
            sub_layout = QVBoxLayout()
            label = QLabel(label_text)
            box = QComboBox()
            
            if visible_keys is None:
                visible_keys = options.keys()
            
            for key in visible_keys:
                box.addItem(options[key], key)
            
            sub_layout.addWidget(label)
            sub_layout.addWidget(box)
            return sub_layout, box

        # 體型
        size_layout, self.size_box = make_combobox("體型", size_map)
        target_layout.addLayout(size_layout)

        # 屬性
        # 只顯示 element_map 前 10 個 key（0~9）
        visible_element_keys = [k for k in element_map if k <= 9]
        element_layout, self.element_box = make_combobox("屬性", element_map, visible_element_keys)
        target_layout.addLayout(element_layout)
        
        element_lv_input_layout = QVBoxLayout()
        element_lv_input_label = QLabel(tr("label.level"))
        self.element_lv_input = QLineEdit()
        self.element_lv_input.setFixedWidth(30)
        self.element_lv_input.setPlaceholderText("1")
        validator = QIntValidator(1, 4, self)
        self.element_lv_input.setValidator(validator)
        element_lv_input_layout.addWidget(element_lv_input_label)
        element_lv_input_layout.addWidget(self.element_lv_input)
        target_layout.addLayout(element_lv_input_layout)

        # 同樣方式套用在 race_map（假設你也要限制）
        visible_race_keys = [k for k in race_map if k <= 9]
        race_layout, self.race_box = make_combobox("種族", race_map, visible_race_keys)
        target_layout.addLayout(race_layout)


        # 階級
        visible_class_keys = [k for k in class_map if k <= 1]  # 依你需求調整
        class_layout, self.class_box = make_combobox("階級", class_map, visible_class_keys)
        target_layout.addLayout(class_layout)

        # MDEF / MRES 輸入欄

        
        defc_layout = QVBoxLayout()
        self.defc_label = QLabel(tr("label.front_def"))
        self.defc_input = QLineEdit()
        self.defc_input.setFixedWidth(60)
        self.defc_input.setPlaceholderText("0")
        self.mdefc_label = QLabel(tr("label.front_mdef"))
        self.mdefc_input = QLineEdit()
        self.mdefc_input.setFixedWidth(60)
        self.mdefc_input.setPlaceholderText("0")
        defc_layout.addWidget(self.defc_label)
        defc_layout.addWidget(self.defc_input)
        defc_layout.addWidget(self.mdefc_label)
        defc_layout.addWidget(self.mdefc_input)
        target_layout.addLayout(defc_layout)

        def_layout = QVBoxLayout()
        self.def_label = QLabel(tr("label.back_def"))
        self.def_input = QLineEdit()
        self.def_input.setFixedWidth(60)
        self.def_input.setPlaceholderText("0")
        self.mdef_label = QLabel(tr("label.back_mdef"))
        self.mdef_input = QLineEdit()
        self.mdef_input.setFixedWidth(60)
        self.mdef_input.setPlaceholderText("0")
        def_layout.addWidget(self.def_label)
        def_layout.addWidget(self.def_input)        
        def_layout.addWidget(self.mdef_label)
        def_layout.addWidget(self.mdef_input)
        target_layout.addLayout(def_layout)


        res_layout = QVBoxLayout()
        self.res_label = QLabel("RES")
        self.res_input = QLineEdit()
        self.res_input.setFixedWidth(60)
        self.res_input.setPlaceholderText("0")
        self.mres_label = QLabel("MRES")
        self.mres_input = QLineEdit()
        self.mres_input.setFixedWidth(60)
        self.mres_input.setPlaceholderText("0")
        res_layout.addWidget(self.res_label)
        res_layout.addWidget(self.res_input)
        res_layout.addWidget(self.mres_label)
        res_layout.addWidget(self.mres_input)
        target_layout.addLayout(res_layout)
        
        self.def_label.setVisible(False)
        self.def_input.setVisible(False)
        self.defc_label.setVisible(False)
        self.defc_input.setVisible(False)
        self.res_label.setVisible(False)
        self.res_input.setVisible(False)
        
        # 把整排放到主要 layout
        
        layout.addLayout(target_layout)
        
        # ComboBox 的綁定 修改觸發計算；同時同步到「減傷計算」分頁
        self.size_box.currentIndexChanged.connect(self._on_damage_target_fields_changed)
        self.element_box.currentIndexChanged.connect(self._on_damage_target_fields_changed)
        self.race_box.currentIndexChanged.connect(self._on_damage_target_fields_changed)
        self.class_box.currentIndexChanged.connect(self._on_damage_target_fields_changed)
        self.attack_element_box.currentIndexChanged.connect(self.trigger_total_effect_update)

        # LineEdit 的綁定（使用 editingFinished 避免每次打字都觸發）
        #self.monsterDamage_input.editingFinished.connect(self.replace_custom_calc_content)#指定魔物增傷UI
        self.element_lv_input.editingFinished.connect(self._on_damage_target_fields_changed)
        self.def_input.editingFinished.connect(self.trigger_total_effect_update)
        self.defc_input.editingFinished.connect(self.trigger_total_effect_update)
        self.res_input.editingFinished.connect(self.trigger_total_effect_update)
        self.mdef_input.editingFinished.connect(self.trigger_total_effect_update)
        self.mdefc_input.editingFinished.connect(self.trigger_total_effect_update)
        self.mres_input.editingFinished.connect(self.trigger_total_effect_update)

        MD_BETELGEUSE = QHBoxLayout()

        # 防禦星數
        self.MD_BETELGEUSE_label_def = QLabel(tr("label.betelgeuse_def_stars"))
        self.MD_BETELGEUSE_combo_def = QComboBox()
        self.MD_BETELGEUSE_combo_def.addItems([str(i) for i in range(0, 6)])   # 1~5
        self.MD_BETELGEUSE_label_def.setVisible(False)
        self.MD_BETELGEUSE_combo_def.setVisible(False)

        # 亡魂顆數
        self.MD_BETELGEUSE_label_soul = QLabel(tr("label.betelgeuse_souls"))
        self.MD_BETELGEUSE_combo_soul = QComboBox()
        self.MD_BETELGEUSE_combo_soul.addItems([str(i) for i in range(0, 11)])  # 1~10
        self.MD_BETELGEUSE_label_soul.setVisible(False)
        self.MD_BETELGEUSE_combo_soul.setVisible(False)

        # 總和顯示
        self.MD_BETELGEUSE_label_total_title = QLabel(tr("label.reduction_percent"))
        self.MD_BETELGEUSE_label_total = QLabel("0")   # 預設0
        self.MD_BETELGEUSE_label_total_title.setVisible(False)
        self.MD_BETELGEUSE_label_total.setVisible(False)

        def update_MD_BETELGEUSE_total():
            star = int(self.MD_BETELGEUSE_combo_def.currentText())
            soul = int(self.MD_BETELGEUSE_combo_soul.currentText())
            total = (star + soul) * 10
            self.MD_BETELGEUSE_total = min(total, 99)   # 最大值 99
            self.MD_BETELGEUSE_label_total.setText(f"{int(self.MD_BETELGEUSE_total)}%")

        # 綁定事件
        self.MD_BETELGEUSE_combo_def.currentIndexChanged.connect(update_MD_BETELGEUSE_total)
        self.MD_BETELGEUSE_combo_def.currentIndexChanged.connect(self.trigger_total_effect_update)

        self.MD_BETELGEUSE_combo_soul.currentIndexChanged.connect(update_MD_BETELGEUSE_total)
        self.MD_BETELGEUSE_combo_soul.currentIndexChanged.connect(self.trigger_total_effect_update)




        # 加到橫向排列
        MD_BETELGEUSE.addWidget(self.MD_BETELGEUSE_label_def)
        MD_BETELGEUSE.addWidget(self.MD_BETELGEUSE_combo_def)
        MD_BETELGEUSE.addSpacing(20)

        MD_BETELGEUSE.addWidget(self.MD_BETELGEUSE_label_soul)
        MD_BETELGEUSE.addWidget(self.MD_BETELGEUSE_combo_soul)
        MD_BETELGEUSE.addSpacing(20)

        MD_BETELGEUSE.addWidget(self.MD_BETELGEUSE_label_total_title)
        MD_BETELGEUSE.addWidget(self.MD_BETELGEUSE_label_total)

        # 加進主 layout
        layout.addLayout(MD_BETELGEUSE)

        # 初始化一次
        update_MD_BETELGEUSE_total()




        self.btn_open_monster_lookup = QPushButton(tr("button.lookup_monster"))
        self.btn_open_monster_lookup.clicked.connect(self.open_monster_lookup)
        layout.addWidget(self.btn_open_monster_lookup)
        # 新增按鈕
        self.replace_calc_button = QPushButton(tr("button.calculate"))
        self.replace_calc_button.clicked.connect(lambda: (setattr(self, "_last_calc_state", None), self.trigger_total_effect_update()))
        layout.addWidget(self.replace_calc_button)

        self.sim_tabs.addTab(self.custom_calc_tab, tr("tab.damage_calculation"))

        # 建立新分頁：減傷計算（與傷害計算目標欄位連動）
        # 初始化魔物攻擊值
        self.monster_f_atk = 0
        self.monster_c_atk = 0
        self.monster_f_matk = 0
        self.monster_c_matk = 0

        self.body_custom_calc_tab = QWidget()
        body_layout = QVBoxLayout(self.body_custom_calc_tab)
        self.btn_open_monster_lookup_2 = QPushButton(tr("button.lookup_monster"))
        self.btn_open_monster_lookup_2.clicked.connect(self.open_monster_lookup)
        body_layout.addWidget(self.btn_open_monster_lookup_2)

        body_target_layout = QHBoxLayout()

        body_size_layout, self.body_size_box = make_combobox("體型", size_map)
        body_target_layout.addLayout(body_size_layout)

        body_element_layout, self.body_element_box = make_combobox("屬性", element_map, visible_element_keys)
        body_target_layout.addLayout(body_element_layout)

        body_element_lv_input_layout = QVBoxLayout()
        body_element_lv_input_label = QLabel(tr("label.level"))
        self.body_element_lv_input = QLineEdit()
        self.body_element_lv_input.setFixedWidth(30)
        self.body_element_lv_input.setPlaceholderText("1")
        self.body_element_lv_input.setValidator(QIntValidator(1, 4, self))
        body_element_lv_input_layout.addWidget(body_element_lv_input_label)
        body_element_lv_input_layout.addWidget(self.body_element_lv_input)
        #body_target_layout.addLayout(body_element_lv_input_layout)

        body_race_layout, self.body_race_box = make_combobox("種族", race_map, visible_race_keys)
        body_target_layout.addLayout(body_race_layout)

        body_class_layout, self.body_class_box = make_combobox("階級", class_map, visible_class_keys)
        body_target_layout.addLayout(body_class_layout)

        monster_body_element_layout, self.monster_body_element_box = make_combobox("受攻擊屬性", element_map, visible_element_keys)
        body_target_layout.addLayout(monster_body_element_layout)

        body_layout.addLayout(body_target_layout)

        # 多行文字框：減傷計算輸出
        self.body_custom_calc_box = QTextEdit()
        self.body_custom_calc_box.setFont(monospace_font)
        body_layout.addWidget(self.body_custom_calc_box)

        # 初始化同步，並允許在減傷計算分頁修改後反向同步到傷害計算。
        self._sync_damage_to_body_target_fields()
        self.body_size_box.currentIndexChanged.connect(self._on_body_target_fields_changed)
        self.body_element_box.currentIndexChanged.connect(self._on_body_target_fields_changed)
        self.monster_body_element_box.currentIndexChanged.connect(self._on_body_target_fields_changed)
        self.body_race_box.currentIndexChanged.connect(self._on_body_target_fields_changed)
        self.body_class_box.currentIndexChanged.connect(self._on_body_target_fields_changed)
        self.body_element_lv_input.editingFinished.connect(self._on_body_target_fields_changed)

        self.sim_tabs.addTab(self.body_custom_calc_tab, tr("tab.damage_reduction", "減傷計算"))







        # ===== 合併三欄 =====
        #main_layout.addWidget(left_scroll, 2)#已分頁取代
        #main_layout.addWidget(middle_scroll, 3)
        main_layout.addWidget(right_scroll, 3)
        self.setLayout(main_layout)


        # 初始化下拉選單
        self.update_combobox(initial=True)
        self.current_edit_part = None  # 用來追蹤目前編輯哪個欄位

        #根據 checkbox 狀態隱藏或顯示
        self.toggle_equip_text_visibility()


        #讀取.json存檔 250611更動工具列讀取
        #self.load_saved_inputs()
        



        #讀取完先計算一次        
        
        #self.display_all_effects()
        



        # 初始顯示一次
        
        #self.update_dex_int_half_note()
        self.result_output.textChanged.connect(self.on_result_output_changed)
        self.gen_button.clicked.connect(self.on_generate)
        self.condition_gen_button.clicked.connect(self.on_generate_condition)
        self.condition_kind_combo.currentIndexChanged.connect(self.on_condition_kind_changed)
        self.condition_left_combo.activated.connect(self.on_condition_left_activated)
        self.on_condition_kind_changed()
        self.function_selector.currentIndexChanged.connect(self.on_function_changed)
        self.on_function_changed()
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
        # 綁定輸入欄事件（動態更新）
        #self.input_fields["DEX"].editingFinished.connect(self.update_dex_int_half_note)
        #self.input_fields["INT"].editingFinished.connect(self.update_dex_int_half_note)
        #self.hp_slider.valueChanged.connect(self.replace_custom_calc_content)                
        #self.sp_slider.valueChanged.connect(self.replace_custom_calc_content)
        self.hp_slider.valueChanged.connect(self.trigger_total_effect_update)
        self.sp_slider.valueChanged.connect(self.trigger_total_effect_update)
        self.unsync_button.clicked.connect(update_hp_sp_slider_display)
        self.unsync_button2.clicked.connect(update_hp_sp_slider_display)        
        self.apply_equip_button.clicked.connect(update_hp_sp_slider_display)
        self.apply_to_note_button.clicked.connect(update_hp_sp_slider_display)

        #開啟選單欄 
        self.update_window_title()
        self.setup_menu()
        
    
    def setup_menu(self):
        menubar = QMenuBar(self)

        # === 檔案選單 ===
        file_menu = menubar.addMenu(tr("menu.file"))

        open_action = QAction(tr("menu.open"), self)
        open_action.triggered.connect(self.open_project_file)
        file_menu.addAction(open_action)        

        open_rrf_action = QAction(tr("menu.import_rrf"), self)
        open_rrf_action.triggered.connect(self.open_rrf_and_import)
        file_menu.addAction(open_rrf_action)        

        save_action = QAction(tr("menu.save"), self)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        save_as_action = QAction(tr("menu.save_as"), self)
        save_as_action.triggered.connect(self.save_as_file)
        file_menu.addAction(save_as_action)

        ROC_save_as_action = QAction(tr("menu.save_as_roc"), self)
        ROC_save_as_action.triggered.connect(
            lambda checked=False: self.add_effects_from_variables("data/default.txt", equipid_mapping, status_mapping)
        )   

        file_menu.addAction(ROC_save_as_action)
        


        gamedata_menu = menubar.addMenu(tr("menu.tools"))
        # === 建立選單：傷害表 ===
        action_open_damage = QAction(tr("menu.damage_replay_tool"), self)
        action_open_damage.triggered.connect(self.open_rrfdamage_view)
        gamedata_menu.addAction(action_open_damage)


        # === 建立選單：附魔工具 ===
        enchant_action = QAction(tr("menu.enchant_tool"), self)
        enchant_action.triggered.connect(self.open_enchant_tool)

        gamedata_menu.addAction(enchant_action)

        # === 建立選單：Lapine 附魔工具 ===
        lapine_upgrade_action = QAction(
            tr("menu.lapine_upgrade_tool", "附加能力附魔工具"), self
        )
        lapine_upgrade_action.triggered.connect(self.open_lapine_upgrade_tool)
        gamedata_menu.addAction(lapine_upgrade_action)

        # === 建立選單：改造工具 ===
        reform_action = QAction(tr("menu.reform_tool"), self)
        reform_action.triggered.connect(self.open_reform_tool)

        gamedata_menu.addAction(reform_action)

        #多裝備比對
        multi_compare_action = QAction("多裝備比對工具", self)
        multi_compare_action.triggered.connect(self.open_multi_compare)
        gamedata_menu.addAction(multi_compare_action)

        # === 設定選單 ===
        settings_menu = menubar.addMenu(tr("menu.settings"))

        preferences_action = QAction(tr("menu.preferences"), self)
        preferences_action.triggered.connect(self.open_compile_set)
        settings_menu.addAction(preferences_action)
        
        menu_update = menubar.addMenu(tr("menu.update"))

        self.action_check_update = QAction(tr("menu.check_update"), self)
        self.action_do_update = QAction(tr("menu.update_now"), self)
        self.action_do_update.setEnabled(False)  # 預設不能按

        menu_update.addAction(self.action_check_update)
        #menu_update.addAction(self.action_do_update)

        self.action_check_update.triggered.connect(self.check_update)
        self.action_do_update.triggered.connect(self.do_update)

        menu_debug = menubar.addMenu(tr("menu.debug"))

        internal_data_action = QAction(tr("menu.internal_data_inspector", "內部資料查詢"), self)
        internal_data_action.triggered.connect(self.open_internal_data_inspector)
        menu_debug.addAction(internal_data_action)
        
        Damage_view_action = QAction(tr("menu.damage_history"), self)
        Damage_view_action.triggered.connect(self.open_damage_calculator)
        menu_debug.addAction(Damage_view_action)

        self._remote_version = None  # 存檢查到的遠端版本
        # # === 說明選單 ===
        # help_menu = menubar.addMenu("說明")

        # help_action = QAction("使用說明", self)
        # help_action.triggered.connect#(self.show_help)
        # help_menu.addAction(help_action)

        # about_action = QAction("關於", self)
        # about_action.triggered.connect#(self.show_about)
        # help_menu.addAction(about_action)
        
        # === 加入選單到主 layout ===
        self.layout().setMenuBar(menubar)
        


    def add_effects_from_variables(self, template_path, equipid_mapping, status_mapping):  # 直接輸出 .ROC
        import json, copy, os, base64
        from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

        # === 擷取類別或全域變數 ===
        context = globals()

        # === 讀取模板 JSON ===
        with open(template_path, "r", encoding="utf-8") as f:
            template = json.load(f)
        new_data = copy.deepcopy(template)

        # === 找到主手裝備的 effectlist ===
        equip_list = new_data.get("Equip", [])
        if not equip_list:
            QMessageBox.warning(self, tr("message.title.error"), tr("message.template_missing_equip"))
            return
        effect_list = equip_list[0].get("effectlist", [])

        # === 根據 equipid_mapping 新增效果到 Equip ===
        for var_name, effect_id in equipid_mapping.items():
            if var_name in context:
                value = context[var_name]
                if value == 0:
                    continue  # value 是 0 就略過，不輸出也不新增
                new_effect = {
                    "EffectNumber": value,
                    "EffectType": {"id": effect_id},
                    "Enable": True
                }
                effect_list.append(new_effect)
                print(f"✅ 已新增效果：{effect_id} = {value}")
            else:
                print(f"⚠️ 找不到變數：{var_name}，略過。")

        # === 根據 status_mapping 更新 Status ===
        status_data = new_data.get("Status", {})
        if status_data:
            for var_name, status_key in status_mapping.items():
                if var_name in context:
                    new_value = context[var_name]
                    old_value = status_data.get(status_key, None)
                    status_data[status_key] = new_value
                    print(f"🔄 Status[{status_key}] 從 {old_value} → {new_value}")
                else:
                    print(f"⚠️ 找不到變數：{var_name}（對應 Status[{status_key}]），略過。")
        else:
            print("⚠️ 模板中沒有 Status 區塊。")

        # === 根據 SkillOption_mapping 更新 SkillOption ===
        skillopt_data = new_data.get("SkillOption", None)
        if skillopt_data is None:
            # 模板沒有就建立
            new_data["SkillOption"] = {}
            skillopt_data = new_data["SkillOption"]

        if skillopt_data is not None:
            for var_name, skillopt_key in SkillOption_mapping.items():
                if var_name in context:
                    new_value = context[var_name]
                    old_value = skillopt_data.get(skillopt_key, None)
                    skillopt_data[skillopt_key] = new_value
                    print(f"🔄 SkillOption[{skillopt_key}] 從 {old_value} → {new_value}")
                else:
                    print(f"⚠️ 找不到變數：{var_name}（對應 SkillOption[{skillopt_key}]），略過。")
        else:
            print("⚠️ 模板中沒有 SkillOption 區塊。")

        # === 更新技能code ===
        if "Skill" in new_data and isinstance(new_data["Skill"], dict):
            old_value = new_data["Skill"].get("id", None)
            new_data["Skill"]["id"] = SkillCode
            print(f"🔄 Skill['id'] 從 {old_value} → {SkillCode}")
        else:
            print("⚠️ 模板中沒有 Skill 區塊或格式不正確")

        # === 根據 weapon_mapping 更新 Weapon===
        weapon_data = new_data.get("Weapon", {})
        if weapon_data:
            for var_name, weapon_key in weapon_mapping.items():
                if var_name in context:
                    new_value = context[var_name]

                    # 正規化成多層鍵列表
                    if isinstance(weapon_key, (tuple, list)):
                        keys = list(weapon_key)
                    else:
                        keys = [weapon_key]

                    # 先取舊值（不建立缺失的中間層）
                    cur = weapon_data
                    old_value = None
                    found = True
                    for k in keys[:-1]:
                        if isinstance(cur, dict) and k in cur:
                            cur = cur[k]
                        else:
                            found = False
                            break
                    if found and isinstance(cur, dict) and keys[-1] in cur:
                        old_value = cur[keys[-1]]

                    # 設定新值（必要時建立中間層）
                    cur = weapon_data
                    for k in keys[:-1]:
                        if k not in cur or not isinstance(cur[k], dict):
                            cur[k] = {}
                        cur = cur[k]
                    cur[keys[-1]] = new_value

                    path_str = "][".join(map(str, keys))
                    print(f"🔄 Weapon[{path_str}] 從 {old_value} → {new_value}")
                else:
                    print(f"⚠️ 找不到變數：{var_name}（對應 Weapon[{weapon_key}]），略過。")
        else:
            print("⚠️ 模板中沒有 Weapon 區塊。")


        # === 根據 SubWeapon_mapping 更新 SubWeapon ===
        subweapon_data = new_data.get("SubWeapon", {})
        if subweapon_data:
            for var_name, subweapon_key in SubWeapon_mapping.items():
                if var_name in context:
                    new_value = context[var_name]

                    # subweapon_key 可能是單層或雙層 key
                    if isinstance(subweapon_key, tuple) and len(subweapon_key) == 2:
                        first, second = subweapon_key
                        if first in subweapon_data and isinstance(subweapon_data[first], dict):
                            old_value = subweapon_data[first].get(second, None)
                            subweapon_data[first][second] = new_value
                            print(f"🔄 SubWeapon[{first}][{second}] 從 {old_value} → {new_value}")
                        else:
                            print(f"⚠️ SubWeapon 中沒有 {first} 層級，略過。")
                    else:
                        old_value = subweapon_data.get(subweapon_key, None)
                        subweapon_data[subweapon_key] = new_value
                        print(f"🔄 SubWeapon[{subweapon_key}] 從 {old_value} → {new_value}")
                else:
                    print(f"⚠️ 找不到變數：{var_name}（對應 SubWeapon[{subweapon_key}]），略過。")
        else:
            print("⚠️ 模板中沒有 SubWeapon 區塊。")


        # === 從視窗標題推斷檔名 ===
        full_title = self.windowTitle().strip() or tr("window.main_unnamed")
        if " - " in full_title:
            filename_part = full_title.split(" - ", 1)[1]
        else:
            filename_part = tr("filename.unnamed")

        for bad_char in '\\/:*?"<>|':
            filename_part = filename_part.replace(bad_char, "_")

        filename_part = os.path.splitext(filename_part)[0]
        suggested_filename = f"{filename_part}.roc"

        # === 顯示另存新檔 ===
        app = QApplication.instance() or QApplication([])
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog.save_roc_file"),
            suggested_filename,
            tr("dialog.filter_roc_file")
        )

        if not file_path:
            return

        # 確保副檔名正確
        if not file_path.lower().endswith(".roc"):
            file_path += ".roc"

        # === 直接轉成 base64 並寫出 ROC 檔 ===
        try:
            encoded = base64.b64encode(json.dumps(new_data, ensure_ascii=False).encode("utf-8")).decode("utf-8")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(encoded)
            print(f"✅ 已新增效果並更新 Status，直接輸出 ROC 檔：{file_path}")
        except Exception as e:
            QMessageBox.critical(self, tr("message.title.error"), tr("message.roc_save_failed", error=e))
            print(f"❌ 轉換失敗：{e}")





        
        
    def save_as_file(self):
        # 預設資料夾
        default_dir = os.path.join(os.getcwd(), "裝備")

        # 預設檔名
        full_title = self.windowTitle().strip() or tr("window.main_unnamed")
        if " - " in full_title:
            filename_part = full_title.split(" - ", 1)[1]
        else:
            filename_part = tr("filename.unnamed")

        # 路徑 + 檔名
        default_path = os.path.join(default_dir, filename_part)

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            tr("dialog.save_as"),
            default_path,          # ⭐ 關鍵在這
            "JSON Files (*.json)"
        )

        if file_path:
            if not file_path.lower().endswith(".json"):
                file_path += ".json"

            self.save_to_file(file_path)
            
    # === CORE DEDUP PHASE 8: CHARACTER BUILD ADAPTER ===
    def collect_character_build(self):
        data = {}

        # 儲存 input_fields
        for key, field in self.input_fields.items():
            if isinstance(field, QComboBox):
                data[key] = field.currentText()
            else:
                data[key] = field.text()

        # 儲存裝備與卡片欄位
        for part, info in self.refine_inputs_ui.items():
            data[f"{part}_equip"] = info["equip"].text()
            for i, card_input in enumerate(info["cards"]):
                data[f"{part}_card{i+1}"] = card_input.text()
            if "note" in info:
                data[f"{part}_note"] = info["note"].toPlainText()

        # 技能與怪物資訊整合
        data["skill_name"] = self.skill_box.currentText()
        data["size"] = self.size_box.currentIndex()
        data["element"] = self.element_box.currentIndex()
        data["race"] = self.race_box.currentIndex()
        data["class"] = self.class_box.currentIndex()
        data["mdef"] = self.mdef_input.text()
        data["mdefc"] = self.mdefc_input.text()
        data["mres"] = self.mres_input.text()
        data["def"] = self.def_input.text()
        data["defc"] = self.defc_input.text()
        data["res"] = self.res_input.text()
        data["element_lv"] = self.element_lv_input.text()

        # 技能 buff（把目前勾選的技能轉回 buff id）
        buff_ids = []
        for name, checkbox in self.skill_checkboxes.items():
            if not checkbox.isChecked():
                continue

            entry = all_skill_entries.get(name, {})
            raw_buff = entry.get("buff")
            buff_ids.extend(sorted(self._parse_buff_ids(raw_buff)))

        # 去重後存回字串
        data["buff"] = ",".join(sorted(set(buff_ids), key=lambda x: int(x) if x.isdigit() else x))

        build = CoreCharacterBuild.from_dict(data)
        self.last_character_build = build
        return build

    def save_to_file(self, file_path):
        build = self.collect_character_build()
        data = build.to_dict(include_metadata=True)
        self.last_character_build = build
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.current_file = file_path
            self.update_window_title()
        except Exception as e:
            QMessageBox.critical(self, tr("message.title.save_failed"), tr("message.file_save_failed", error=e))


    def save_file(self):
        if not self.current_file:
            self.save_as_file()  # 如果還沒指定檔案，就當成另存新檔
        else:
            self.save_to_file(self.current_file)


    def load_json_direct(self, file_path):
        try:
            self.skill_filter_input.clear()
            self.load_saved_inputs(file_path)
            #self.update_window_title()
            self.refresh_skill_list()
            self.trigger_total_effect_update()
        except Exception as e:
            QMessageBox.critical(self, tr("message.title.error"), tr("message.load_failed", error=str(e)))
        # ★★★ 讀取成功 → 刪除 JSON 檔 ★★★
        try:
            os.remove(file_path)
            print(f"已刪除暫存 JSON：{file_path}")
            name = file_path.replace("tmp", "").replace("\\", "")
            self.setWindowTitle(tr("window.main_with_file", version=Version, filename=name, Server_area=Server_area))
            self.current_file = None
        except Exception as e:
            print(f"刪除 JSON 失敗：{e}")

    def open_rrf_and_import(self):
        import subprocess, os, json

        # 執行 rrf_to_App.py
        #subprocess.run(["python", "rrf_to_App.py"])
        json_path = run_rrf_main(
            iteminfo_dict=self.parsed_items,
            sequipment_data=self.equipment_data,
        )
        if not json_path:
            return
        bridge_file = "tmp/rrf_output_path.txt"

        if not os.path.exists(bridge_file):
            QMessageBox.warning(self, tr("message.title.error"), tr("message.rrf_json_path_missing"))
            return

        # 讀出 JSON 檔案路徑
        with open(bridge_file, "r", encoding="utf-8") as f:
            json_path = f.read().strip()

        if not os.path.exists(json_path):
            QMessageBox.warning(self, tr("message.title.error"), tr("message.json_file_not_found", path=json_path))
            return

        # ★ 自動載入 JSON（不跳視窗）
        self.load_json_direct(json_path)


    def open_project_file(self):
        # 設定預設資料夾
        default_dir = os.path.join(os.getcwd(),"裝備")
    
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialog.select_project_file"),
            default_dir,  # ✅ 預設資料夾
            "JSON Files (*.json)"
        )
        if not file_path:
            return

        try:

            #self.skill_filter_input.clear()
            #self.clear_global_state()
            self.load_saved_inputs(file_path)
            self.current_file = file_path
            self.update_window_title()
            # self.display_all_effects()
            # self.replace_custom_calc_content()
            # self.update_dex_int_half_note()
            # self.jobsphp_display()
            self.refresh_skill_list()
            self.trigger_total_effect_update()


        except Exception as e:
            QMessageBox.critical(self, tr("message.title.error"), tr("message.load_failed", error=str(e)))



    def clear_current_edit(self):
        self.current_edit_part = None
        self.current_edit_label.setText(tr("label.current_part"))
        self.unsync_button.setVisible(False)
        self.apply_equip_button.setVisible(False)
        self.unsync_button2.setVisible(False)
        self.apply_to_note_button.setVisible(False)
        self.clear_field_button2.setVisible(False)
        self.clear_field_button.setVisible(False)

        for part_name, widgets in self.refine_inputs_ui.items():
            widgets["equip"].setEnabled(True)
            widgets["refine"].setEnabled(True)
            widgets["grade"].setEnabled(True)
            for card_input in widgets["cards"]:
                card_input.setEnabled(True)
            # ✅ 移除所有欄位的背景色
            widgets["equip"].setStyleSheet("")
            for card_input in widgets["cards"]:
                card_input.setStyleSheet("")
            widgets["note"].setStyleSheet("")
            widgets["note_ui"].setStyleSheet("")
            
        #self.display_item_info()
        #self.display_all_effects()
        #self.replace_custom_calc_content()

        self.global_refine_input.setVisible(True)
        self.global_grade_combo.setVisible(True)
        self._set_enchant_tool_target()
        self._set_lapine_upgrade_tool_target()





    def set_edit_lock(self, part_name, field_name):


        #self.display_item_info()
        self.global_refine_input.setVisible(False)
        self.global_grade_combo.setVisible(False)
        self.trigger_total_effect_update()


    def update_divine_pride_button(self, *_):
        """依目前下拉選項更新 Divine Pride 按鈕狀態。"""
        if not hasattr(self, "divine_pride_button"):
            return

        item_id = self.result_box.currentData()
        try:
            item_id = int(item_id)
        except (TypeError, ValueError):
            item_id = 0

        enabled = item_id > 0
        self.divine_pride_button.setEnabled(enabled)

        if enabled:
            self.divine_pride_button.setToolTip(
                f"開啟物品 ID {item_id} 的 Divine Pride 資料頁"
            )
        else:
            self.divine_pride_button.setToolTip(
                tr("tooltip.open_divine_pride", "請先選擇一個物品")
            )

    def open_selected_item_on_divine_pride(self):
        """使用系統預設瀏覽器開啟目前物品的 Divine Pride 頁面。"""
        item_id = self.result_box.currentData()
        try:
            item_id = int(item_id)
        except (TypeError, ValueError):
            QMessageBox.information(
                self,
                tr("message.title.notice", "提示"),
                tr("message.select_item_first", "請先選擇一個有效物品。"),
            )
            return

        url = QUrl(
            f"https://www.divine-pride.net/database/item/{item_id}"
        )
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(
                self,
                tr("message.title.notice", "提示"),
                tr(
                    "message.open_link_failed",
                    "無法開啟瀏覽器連結：{url}",
                    url=url.toString(),
                ),
            )

    def _schedule_item_search(self, *_args):
        """延遲物品搜尋，快速輸入 / Backspace 時只執行最後一次查詢。"""
        if hasattr(self, "_item_search_timer"):
            self._item_search_timer.start()

    def _item_search_source_signature_value(self):
        """取得搜尋來源的輕量版本標記，資料被重載時自動讓索引失效。"""
        parsed_items = getattr(self, "parsed_items", {}) or {}
        equipment_data = getattr(self, "equipment_data", {}) or {}
        return (
            id(parsed_items),
            len(parsed_items),
            id(equipment_data),
            len(equipment_data),
        )

    def rebuild_item_search_index(self):
        """預先建立物品搜尋字串，避免每個按鍵都重新 join description。"""
        parsed_items = getattr(self, "parsed_items", {}) or {}
        equipment_data = getattr(self, "equipment_data", {}) or {}

        search_index = []
        for item_id in sorted(parsed_items):
            if item_id not in equipment_data:
                continue

            item = parsed_items[item_id]
            name = str(item.get("name", ""))
            description = item.get("description", [])

            if isinstance(description, (list, tuple)):
                description_text = " ".join(str(x) for x in description)
            else:
                description_text = str(description or "")

            searchable_text = " ".join((
                str(item_id),
                name,
                description_text,
            )).casefold()

            # 顯示文字也一起 cache，搜尋時不要反覆格式化。
            display_text = f"{item_id} - {name}"
            search_index.append((item_id, item, searchable_text, display_text))

        self._item_search_index = search_index
        self._item_search_index_signature = self._item_search_source_signature_value()
        self._last_item_search_text = None

    def _ensure_item_search_index(self):
        current_signature = self._item_search_source_signature_value()
        if (
            getattr(self, "_item_search_index_signature", None) != current_signature
            or not hasattr(self, "_item_search_index")
        ):
            self.rebuild_item_search_index()

    def _select_item_in_search_by_name(self, item_name):
        """維持原本裝備欄定位方式：查詢欄清空，完整清單中直接選中指定裝備。"""
        name = str(item_name or "").strip()
        if not name:
            return False

        self._ensure_item_search_index()

        # 若前面有使用者輸入造成的 debounce，先取消，避免稍後覆蓋本次定位。
        if hasattr(self, "_item_search_timer"):
            self._item_search_timer.stop()

        target_item_id = None
        name_folded = name.casefold()

        # 從完整索引找出目前裝備，不依賴當下篩選結果。
        for item_id, item, _searchable_text, _display_text in self._item_search_index:
            if str(item.get("name", "")).strip().casefold() == name_folded:
                target_item_id = item_id
                break

        if target_item_id is None:
            return False

        # 維持舊版 UX：點已裝備欄位時搜尋欄是空白，不顯示物品名稱。
        search_was_blocked = self.search_input.blockSignals(True)
        try:
            self.search_input.clear()
        finally:
            self.search_input.blockSignals(search_was_blocked)

        # 如果目前本來就是完整清單，直接定位即可，不需要清空/重建整個 QComboBox。
        full_list_loaded = (
            self.result_box.count() == len(self._item_search_index)
            and len(getattr(self, "filtered_items", {})) == len(self._item_search_index)
        )
        if full_list_loaded:
            index = self.result_box.findData(target_item_id)
            if index >= 0:
                self.result_box.setCurrentIndex(index)
                return True

        # 否則立即恢復完整清單並選中該裝備，不等待 120ms debounce。
        self._last_item_search_text = None
        self.update_combobox(initial=True, preferred_item_id=target_item_id)
        return True

    def update_combobox(self, initial=False, preferred_item_id=None):
        """使用預建索引搜尋，並整批更新 QComboBox，避免逐字輸入造成 UI 卡頓。

        preferred_item_id 用於程式主動定位某件裝備時，確保搜尋結果完成後
        直接選中指定物品，而不是先跳到第一筆或沿用舊選擇。
        """
        self._ensure_item_search_index()

        keyword_text = self.search_input.text().strip().casefold()

        # 相同關鍵字不重建結果；initial=True 用於資料重載/初始化時強制刷新。
        if (
            not initial
            and getattr(self, "_last_item_search_text", None) == keyword_text
        ):
            return
        self._last_item_search_text = keyword_text

        keywords = keyword_text.split()
        previous_item_id = self.result_box.currentData()
        matches = []

        # 無論搜尋欄是否為空，都從完整索引建立結果；不限制前 500 筆。
        # 搜尋字串本身已在 rebuild_item_search_index() 預先建立，避免每次重組 description。
        for item_id, item, searchable_text, display_text in self._item_search_index:
            if keywords and not all(keyword in searchable_text for keyword in keywords):
                continue

            matches.append((item_id, item, display_text))

        self.filtered_items = {item_id: item for item_id, item, _ in matches}

        # clear()/addItem()/setCurrentIndex() 都可能觸發 currentIndexChanged；
        # 搜尋結果建置期間暫停 signal 與 repaint，完成後只刷新一次詳細資訊。
        was_blocked = self.result_box.blockSignals(True)
        updates_enabled = self.result_box.updatesEnabled()
        self.result_box.setUpdatesEnabled(False)

        try:
            self.result_box.clear()

            for item_id, _item, display_text in matches:
                self.result_box.addItem(display_text, item_id)

            if self.result_box.count() > 0:
                index = -1

                # 程式主動要求定位特定裝備時，以指定物品優先。
                if preferred_item_id is not None:
                    index = self.result_box.findData(preferred_item_id)

                # 一般文字搜尋則盡量保留使用者原本選取。
                if index < 0:
                    index = self.result_box.findData(previous_item_id)
                if index < 0:
                    index = 0

                self.result_box.setCurrentIndex(index)
        finally:
            self.result_box.blockSignals(was_blocked)
            self.result_box.setUpdatesEnabled(updates_enabled)
            self.result_box.update()

        # 批次更新完成後，只執行一次原本由 currentIndexChanged 負責的 UI 更新。
        if self.result_box.count() > 0:
            self.display_item_info()
            self.update_total_effect_display()
            self.update_divine_pride_button()
        else:
            self.update_divine_pride_button()


    def display_item_info(self, refine_override=None, grade_override=None):
        '''
        根據目前選取的物品，顯示其詳細資訊
        '''
        index = self.result_box.currentIndex()
        if index == -1:
            return
        item_id = self.result_box.currentData()
        item = self.filtered_items.get(item_id)
        if not item:
            return
        self.name_field.setText(item['name'])
        self.kr_name_field.setText(item['kr_name'])
        self.slot_field.setText(str(item['slot']))

        html = convert_description_to_html(item['description'])
        self.desc_text.setHtml(html)
        # 顯示裝備原始資料區塊（若有）
        if item_id in self.equipment_data:
            block_text = self.equipment_data[item_id]
            # === Combiitem → 顯示套裝需求（裝備名稱） ===
            # 需求：使用 Combiitem 裡的「套裝ID」去找對應套裝區塊，並解析其中 Item={...} 的需求裝備。
            def _extract_combi_ids(_block_text: str) -> list[int]:
                m = re.search(r"Combiitem\s*=\s*\{([^}]*)\}", _block_text)
                if not m:
                    return []
                ids: list[int] = []
                for x in m.group(1).split(','):
                    x = x.strip()
                    if x.isdigit():
                        ids.append(int(x))
                return ids

            def _extract_combo_items(_combo_text: str) -> list[int]:
                m = re.search(r"Item\s*=\s*\{([^}]*)\}", _combo_text)
                if not m:
                    return []
                out: list[int] = []
                for x in m.group(1).split(','):
                    x = x.strip()
                    if x.isdigit():
                        out.append(int(x))
                # 去重但保留順序
                seen = set()
                uniq = []
                for i in out:
                    if i not in seen:
                        seen.add(i)
                        uniq.append(i)
                return uniq

            combi_ids = _extract_combi_ids(block_text)
            combi_lines: list[str] = []
            if combi_ids:
                #combi_lines.append("========= Combiitem 套裝需求 =========")
                for combi_id in combi_ids:
                    combo_block = self.equipment_data.get(combi_id, "")
                    need_ids = _extract_combo_items(combo_block)

                    combo_name = self.parsed_items.get(combi_id, {}).get("name", f"套裝ID {combi_id}")
                    if not need_ids:
                        #combi_lines.append(f"🧩 {combo_name}（{combi_id}）：（找不到 Item={{...}}）")
                        combi_lines.append(f"🧩 {combo_name}：（找不到 Item={{...}}）")
                        continue

                    need_names = [self.parsed_items.get(iid, {}).get("name", f"ID:{iid}") for iid in need_ids]
                    #combi_lines.append(f"🧩 {combo_name}（{combi_id}）")
                    combi_lines.append(f"🧩 {combo_name}")
                    combi_lines.append("↳  需求：" + "、".join(need_names))
            if not combi_ids:
                self.combi_raw_text.clear()
            else:
                raw_blocks = []
                for cid in combi_ids:
                    combo_block = self.equipment_data.get(cid, "")
                    if combo_block:
                        raw_blocks.append(f"[{cid}] = {{\n{combo_block}\n}}")
                    else:
                        raw_blocks.append(f"[{cid}] 找不到資料")

                self.combi_raw_text.setPlainText("\n\n".join(raw_blocks))


            fullCombi_text = ("\n".join(combi_lines) if combi_lines else "")
            self.Combi_text.setPlainText(fullCombi_text)


            full_text = f"[{item_id}] = {{\n{block_text}\n}}"
            self.equip_text.setPlainText(full_text)
        else:
            self.equip_text.setPlainText("（此物品無對應裝備屬性資料）")
        # 模擬效果解析
        if item_id in self.equipment_data:
            # 偵測是否需要精煉欄位
            #self.refine_input.setVisible("GetRefineLevel(" in block_text)

            # 整理 get(...) 對應值
            get_values = {}
            for gid, label in stat_fields.items():
                widget = self.input_fields[label]
                if isinstance(widget, QComboBox):
                    get_values[gid] = widget.currentData()
                else:
                    try:
                        get_values[gid] = int(widget.text())
                    except ValueError:
                        get_values[gid] = 0

            # 整理 GetRefineLevel(...) 對應值
            refine_inputs = {}
            for label, info in refine_parts.items():
                slot_id = info["slot"]
                # 如果你原本使用 slot_id 做什麼，照樣用

                text = self.input_fields[label].text()
                try:
                    refine_inputs[slot_id] = int(text)
                except ValueError:
                    refine_inputs[slot_id] = 0

            # 裝備階級 GetEquipGradeLevel
            grade = 0
            if hasattr(self, "current_edit_part") and self.current_edit_part:
                part_name = self.current_edit_part.split(" - ")[0]
                key = f"{part_name}_階級"
                if key in self.input_fields:
                    grade = self.input_fields[key].currentIndex()
            
            hide_physical = self.hide_physical_checkbox.isChecked()
            hide_magical = self.hide_magical_checkbox.isChecked()
            hide_unrecognized = self.hide_unrecognized_checkbox.isChecked()
            # 抓目前裝備部位的 slot ID
            current_slot = None
            if self.current_edit_part:
                part_name = self.current_edit_part.split(" - ")[0]
                current_slot = refine_parts.get(part_name, {}).get("slot")
                grade = self.input_fields.get(f"{part_name}_階級", self.global_grade_combo).currentIndex()
            else:
                # ⬅️ 若沒選部位就用全域
                current_slot = None
                try:
                    refine_inputs[99] = int(self.global_refine_input.text())  # slot=99 為假設值
                except:
                    refine_inputs[99] = 0
                grade = self.global_grade_combo.currentIndex()


            # 呼叫新模擬效果解析器
            effects = parse_lua_effects_with_variables(
                block_text,
                refine_inputs,
                get_values,
                grade,
                unit_map,
                size_map,
                effect_map,
                hide_unrecognized,
                current_location_slot=current_slot or 99
            )


            hide_keywords = []
            if hide_physical:
                hide_keywords.append("物理")
            if hide_magical:
                hide_keywords.append("魔法")
                
            filtered_effects = self.filter_effects(effects)
            effect_dict = {}
            for line in filtered_effects:
                parsed = self.try_extract_effect(line)
                if parsed:
                    key, value, unit = parsed
                    key = self.normalize_effect_key(key)
                    #source_label = part_name  # or 卡片名稱 or 套裝來源

                    # 建立效果來源清單
                    #effect_dict.setdefault((key, unit), []).append((value, source_label))


                else:
                    continue  # 無法解析就略過，不佔用空間



            combined = []
            show_source = self.show_combo_source_checkbox.isChecked()
            for (key, unit), entries in sorted(effect_dict.items(), key=lambda x: x[0][0]):
                total = sum(val for val, _ in entries)
                if unit == "秒":
                    total = round(total, 1)
                    value_str = f"{total:+.1f}{unit}"
                else:
                    value_str = f"{total:+g}{unit}"

                if show_source:
                    for val, source in entries:
                        val_str = f"{val:+.1f}{unit}" if unit == "秒" else f"{val:+d}{unit}"
                        combined.append(f"{key} {val_str}  ← 〔{source}〕")
                    combined.append(f"🧮↳ {key} {value_str}  ← 〔總和〕🧮")
                else:
                    combined.append(f"{key} {value_str}")
    




            self.sim_effect_text.setPlainText("\n".join(combined))
            # 顯示結果
            self.sim_effect_text.setPlainText("\n".join(filtered_effects))
            
            self.display_all_effects()#這邊只顯示目前裝備效果 需要單獨處理 不然會影響最終顯示
            
            
        else:
            self.sim_effect_text.setPlainText("（無可解析效果）")
            

if __name__ == "__main__":
    # 必須在建立 QApplication 前設定縮放倍率
    startup_ui_scale = get_startup_ui_scale_factor(sys.argv)
    os.environ["QT_SCALE_FACTOR"] = format_ui_scale_factor(startup_ui_scale)

    app = QApplication(sys.argv)

    if len(sys.argv) > 1 and sys.argv[1] == "rrf":
        from RRF_compile_damage_view import MainUI

        window = MainUI()
        window.show()
        sys.exit(app.exec())

    # 保留參考，避免被 Python 回收
    loading = LoadingDialog()
    window = None
    worker = None

    # 先顯示小視窗
    loading.show()
    loading.raise_()
    loading.activateWindow()
    loading.repaint()

    # 強制 Qt 先處理視窗顯示事件
    app.processEvents()

    def start_initialization():
        global window, worker

        loading.update_progress("正在建立主程式介面...")
        loading.append_text("正在建立主程式介面...")
        app.processEvents()

        # QWidget 必須在主執行緒建立
        window = ItemSearchApp()
        DataRegistry.window = window

        loading.update_progress("正在載入資料...")
        loading.append_text("主介面建立完成，開始載入資料...")
        app.processEvents()

        worker = InitWorker(app_instance=window)

        worker.log_signal.connect(loading.append_text)
        worker.progress_signal.connect(loading.update_progress)
        worker.done_signal.connect(on_done)

        worker.start()

    def on_done(data):
        global window

        loading.update_progress("正在更新外部資料...")
        loading.append_text("載入外部 MAP...")
        app.processEvents()

        DataRegistry.reload_all()

        loading.update_progress("正在更新主介面...")
        loading.append_text("初始化完成，正在更新介面...")
        app.processEvents()

        window.parsed_items = data or {}
        # 資料載入完成後在 GUI thread 建立一次搜尋索引，再強制刷新初始清單。
        window.rebuild_item_search_index()
        window.update_combobox(initial=True)

        window.resize(1650, 900)
        window.show()
        window.raise_()
        window.activateWindow()

        QTimer.singleShot(1000, loading.close)

    # 先讓 Qt 事件迴圈開始，再執行後續初始化
    QTimer.singleShot(0, start_initialization)

    sys.exit(app.exec())


# 技能計算BUG觀察紀錄
# 毀滅彗星5等
# 技能%等級是否-1%
# 250 -0
# 251 -1
# 252 -0
# 253 -1
# 254 -0 
# 255 -1
# 256 
# 257 -1
# 258 
# 259 
# 260 -0