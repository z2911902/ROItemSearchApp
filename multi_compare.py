"""多裝備比對模組。

此模組只負責：
- 多專案檔 / 目前設定 Snapshot 建立
- 裝備、BUFF、詞條的比對資料整理
- 計算結果解析與差異顯示
- 獨立比對視窗 UI

實際傷害計算不在這裡重做；每個 Snapshot 都回呼主程式既有的
``trigger_total_effect_update()``，確保計算核心只有一份。
"""

import html
import json
import os
import re
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
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

    def collect_project_state_data(self):
        """把目前主畫面收成與專案檔相同的資料格式，不寫檔。"""
        main = self.main_window
        data = {}

        for key, field in main.input_fields.items():
            if isinstance(field, QComboBox):
                data[key] = field.currentText()
            else:
                data[key] = field.text()

        for part, info in main.refine_inputs_ui.items():
            data[f"{part}_equip"] = info["equip"].text()
            for i, card_input in enumerate(info["cards"]):
                data[f"{part}_card{i+1}"] = card_input.text()
            if "note" in info:
                data[f"{part}_note"] = info["note"].toPlainText()

        data["skill_name"] = main.skill_box.currentText()

        skill_data = main.skill_box.currentData()
        if not isinstance(skill_data, (str, int, float, bool, type(None))):
            skill_data = str(skill_data)
        attack_element_data = main.attack_element_box.currentData()
        if not isinstance(attack_element_data, (str, int, float, bool, type(None))):
            attack_element_data = str(attack_element_data)

        data["_compare_runtime"] = {
            "skill_filter": main.skill_filter_input.text(),
            "skill_name": main.skill_box.currentText(),
            "skill_data": skill_data,
            "skill_lv": main.skill_LV_input.text(),
            "skill_hits": main.skill_hits_input.text(),
            "skill_formula": main.skill_formula_input.text(),
            "attack_element_data": attack_element_data,
            "special_checkboxes": {
                key: checkbox.isChecked()
                for key, checkbox in main.special_checkboxes.items()
            },
        }

        data["size"] = main.size_box.currentIndex()
        data["element"] = main.element_box.currentIndex()
        data["race"] = main.race_box.currentIndex()
        data["class"] = main.class_box.currentIndex()
        data["mdef"] = main.mdef_input.text()
        data["mdefc"] = main.mdefc_input.text()
        data["mres"] = main.mres_input.text()
        data["def"] = main.def_input.text()
        data["defc"] = main.defc_input.text()
        data["res"] = main.res_input.text()
        data["element_lv"] = main.element_lv_input.text()

        all_skill_entries = self._ctx("all_skill_entries", {}) or {}
        buff_ids = []
        for name, checkbox in main.skill_checkboxes.items():
            if not checkbox.isChecked():
                continue
            entry = all_skill_entries.get(name, {})
            raw_buff = entry.get("buff") if isinstance(entry, dict) else None
            buff_ids.extend(sorted(_parse_buff_ids(raw_buff)))
        data["buff"] = ",".join(
            sorted(set(buff_ids), key=lambda x: int(x) if x.isdigit() else x)
        )
        return data

    def restore_project_state_data(self, data, recalculate=True):
        """使用主程式既有 load_saved_inputs 流程還原批次比較前狀態。"""
        main = self.main_window
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(prefix="ro_compare_restore_", suffix=".json")
            os.close(fd)
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            runtime = data.get("_compare_runtime", {}) if isinstance(data, dict) else {}
            main.load_saved_inputs(temp_path)
            main.refresh_skill_list()

            if isinstance(runtime, dict) and runtime:
                saved_filter = str(runtime.get("skill_filter", ""))
                main.skill_filter_input.setText(saved_filter)

                saved_skill_data = runtime.get("skill_data")
                saved_skill_name = str(runtime.get("skill_name", "") or "")
                index = main.skill_box.findData(saved_skill_data)
                if index == -1 and saved_skill_name:
                    index = main.skill_box.findText(saved_skill_name)

                skill_map = self._ctx("skill_map", {}) or {}
                if index == -1 and saved_skill_name:
                    for skill_id, display_name in skill_map.items():
                        if str(display_name) == saved_skill_name:
                            main.skill_box.addItem(display_name, skill_id)
                            index = main.skill_box.count() - 1
                            break

                if index != -1:
                    main.skill_box.setCurrentIndex(index)

                main.skill_LV_input.setText(str(runtime.get("skill_lv", main.skill_LV_input.text())))
                main.skill_hits_input.setText(str(runtime.get("skill_hits", main.skill_hits_input.text())))
                main.skill_formula_input.setText(str(runtime.get("skill_formula", main.skill_formula_input.text())))

                attack_element_data = runtime.get("attack_element_data")
                attack_index = main.attack_element_box.findData(attack_element_data)
                if attack_index != -1:
                    main.attack_element_box.setCurrentIndex(attack_index)

                for key, checked in runtime.get("special_checkboxes", {}).items():
                    checkbox = main.special_checkboxes.get(key)
                    if checkbox is not None:
                        checkbox.setChecked(bool(checked))

            if recalculate:
                main._last_calc_state = None
                main.trigger_total_effect_update()
                QApplication.processEvents()
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _build_compare_parse_context(self):
        """建立詞條解析所需的目前能力值與各部位精煉值。"""
        main = self.main_window
        stat_fields = self._ctx("stat_fields", {}) or {}
        refine_parts = self._ctx("refine_parts", {}) or {}

        get_values = {}
        for gid, label in stat_fields.items():
            widget = main.input_fields.get(label)
            if widget is None:
                get_values[gid] = 0
            elif isinstance(widget, QComboBox):
                get_values[gid] = widget.currentData()
            else:
                try:
                    get_values[gid] = int(widget.text())
                except (TypeError, ValueError):
                    get_values[gid] = 0

        refine_inputs = {}
        for part_name, info in refine_parts.items():
            slot_id = info["slot"]
            widget = main.input_fields.get(part_name)
            try:
                refine_inputs[slot_id] = int(widget.text()) if widget is not None else 0
            except (TypeError, ValueError):
                refine_inputs[slot_id] = 0
        return refine_inputs, get_values

    def _parse_compare_note_text(self, part, ui, refine_inputs, get_values):
        """把 Snapshot 中 Lua 詞條轉成可讀文字。"""
        note_widget = ui.get("note")
        if note_widget is None:
            return ""
        raw_text = note_widget.toPlainText().strip()
        if not raw_text:
            return ""

        g = self.globals_map
        mutable_names = (
            "global_weapon_level_map",
            "global_weapon_atk_map",
            "global_weapon_matk_map",
            "global_weapon_type_map",
            "enabled_skill_levels",
            "Use_skill_levels",
        )
        mutable_globals = [g.get(name) for name in mutable_names]
        mutable_globals = [target for target in mutable_globals if isinstance(target, dict)]
        backups = [dict(target) for target in mutable_globals]

        try:
            parser = self._ctx("parse_lua_effects_with_variables")
            if not callable(parser):
                raise RuntimeError("缺少 parse_lua_effects_with_variables")

            refine_parts = self._ctx("refine_parts", {}) or {}
            grade_widget = ui.get("grade")
            grade = grade_widget.currentIndex() if grade_widget is not None else 0
            slot_id = refine_parts.get(part, {}).get("slot")
            parsed_results = parser(
                block_text=raw_text,
                refine_inputs=refine_inputs,
                get_values=get_values,
                grade=grade,
                unit_map=self._ctx("unit_map", {}) or {},
                size_map=self._ctx("size_map", {}) or {},
                effect_map=self._ctx("effect_map", {}) or {},
                hide_unrecognized=True,
                hide_physical=False,
                hide_magical=False,
                current_location_slot=slot_id,
            )
            parsed_lines = [str(line).strip() for line in parsed_results if str(line).strip()]
            if parsed_lines:
                return "\n".join(parsed_lines)
        except Exception as exc:
            print(f"⚠️ 多裝備比對詞條解析失敗 [{part}]：{exc}")
        finally:
            for target, backup in zip(mutable_globals, backups):
                target.clear()
                target.update(backup)

        note_ui = ui.get("note_ui")
        if note_ui is not None:
            parsed_fallback = note_ui.toPlainText().strip()
            if parsed_fallback and "Add" not in parsed_fallback and "Sub" not in parsed_fallback:
                return parsed_fallback
        return "（無可解析詞條）"

    def _collect_compare_equipment(self):
        main = self.main_window
        flat = {}
        refine_inputs, get_values = self._build_compare_parse_context()

        for part, ui in main.refine_inputs_ui.items():
            if part == "技能":
                continue
            flat[f"{part} / 裝備"] = ui["equip"].text()
            if "refine" in ui:
                flat[f"{part} / 精煉"] = ui["refine"].text()
            if "grade" in ui:
                flat[f"{part} / 階級"] = ui["grade"].currentText()
            for i, card in enumerate(ui.get("cards", []), 1):
                flat[f"{part} / 卡片{i}"] = card.text()
            if "note" in ui:
                flat[f"{part} / 詞條"] = self._parse_compare_note_text(
                    part, ui, refine_inputs, get_values
                )

        buff_names = [
            str(name)
            for name, checkbox in getattr(main, "skill_checkboxes", {}).items()
            if checkbox.isChecked()
        ]
        flat["BUFF / 技能、料理"] = "\n".join(buff_names)
        return flat

    @staticmethod
    def _parse_compare_result_text(text):
        result = {}
        skip_keys = {"技能公式", "技能說明"}
        for line in str(text or "").splitlines():
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            key = key.strip()
            if not key or key in skip_keys:
                continue
            display = val.strip()
            clean = display.replace(",", "")
            match = re.search(r"[-]?\d+(?:\.\d+)?", clean)
            if not match:
                continue
            try:
                number = float(match.group(0))
            except ValueError:
                number = None
            result[key] = {
                "display": display,
                "number": number,
                "suffix": "%" if "%" in display else "",
            }
        return result

    def _collect_compare_skill_results(self):
        main = self.main_window
        skill_name = main.skill_box.currentText().strip() if hasattr(main, "skill_box") else ""
        try:
            skill_lv = int(main.skill_LV_input.text())
            skill_lv_display = f"{skill_lv:,}"
            skill_lv_number = float(skill_lv)
        except (AttributeError, TypeError, ValueError):
            raw_lv = main.skill_LV_input.text().strip() if hasattr(main, "skill_LV_input") else ""
            skill_lv_display = raw_lv
            skill_lv_number = None
        return {
            "技能名稱": {"display": skill_name, "number": None, "suffix": ""},
            "技能等級": {"display": skill_lv_display, "number": skill_lv_number, "suffix": ""},
        }

    def _collect_compare_character_results(self):
        main = self.main_window
        g = self.globals_map
        results = {}

        def add_value(key, value):
            try:
                number = float(value)
                display = f"{int(number):,}" if number.is_integer() else f"{number:,.2f}"
            except (TypeError, ValueError):
                number = None
                display = str(value or "")
            results[key] = {"display": display, "number": number, "suffix": ""}

        for field_name in ("BaseLv", "JobLv"):
            field = main.input_fields.get(field_name)
            raw = field.text() if field is not None else g.get(field_name, 0)
            add_value(f"角色等級 / {field_name}", raw)

        for stat in ("STR", "AGI", "VIT", "INT", "DEX", "LUK"):
            field = main.input_fields.get(stat)
            fallback = field.text() if field is not None else 0
            add_value(f"素質 / {stat}", g.get(f"total_{stat}", fallback))

        for stat in ("POW", "STA", "WIS", "SPL", "CON", "CRT"):
            field = main.input_fields.get(stat)
            fallback = field.text() if field is not None else 0
            add_value(f"特性素質 / {stat}", g.get(f"total_{stat}", fallback))
        return results

    def _build_compare_snapshot(self, name, source=None):
        main = self.main_window
        result_text = main.custom_calc_box.toPlainText()
        results = self._collect_compare_skill_results()
        parsed_results = self._parse_compare_result_text(result_text)
        parsed_results.pop("使用技能", None)
        parsed_results.pop("技能名稱", None)
        parsed_results.pop("技能等級", None)
        results.update(parsed_results)
        results.update(self._collect_compare_character_results())
        return {
            "name": str(name or "未命名"),
            "source": source,
            "equipment": self._collect_compare_equipment(),
            "results": results,
            "result_text": result_text,
        }

    def create_current_compare_snapshot(self, name="目前設定"):
        """走主程式原本完整計算後建立目前設定 Snapshot。"""
        main = self.main_window
        auto_compare = bool(
            hasattr(main, "auto_compare_checkbox")
            and main.auto_compare_checkbox.isChecked()
        )
        if hasattr(main, "auto_compare_checkbox"):
            main.auto_compare_checkbox.setChecked(False)
        try:
            main._last_calc_state = None
            main.trigger_total_effect_update()
            QApplication.processEvents()
            return self._build_compare_snapshot(name, source="current")
        finally:
            if hasattr(main, "auto_compare_checkbox"):
                main.auto_compare_checkbox.setChecked(auto_compare)
                if auto_compare:
                    try:
                        main.compare_with_base()
                    except Exception:
                        pass

    def create_json_compare_snapshot(self, file_path):
        """專案檔 -> 原本 UI 載入 -> 原本 trigger_total_effect_update -> Snapshot。"""
        main = self.main_window
        main.load_saved_inputs(file_path)
        main.refresh_skill_list()
        main._last_calc_state = None
        main.trigger_total_effect_update()
        QApplication.processEvents()
        return self._build_compare_snapshot(Path(file_path).stem, source=file_path)


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
        self.status_label = QLabel("")

        toolbar.addWidget(self.update_current_button)
        toolbar.addWidget(self.add_json_button)
        toolbar.addWidget(self.remove_json_button)
        toolbar.addWidget(self.clear_json_button)
        toolbar.addSpacing(16)
        toolbar.addWidget(self.show_current_checkbox)
        toolbar.addWidget(self.only_diff_checkbox)
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
        self.equipment_title_label = QLabel("裝備差異")
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
        self.equipment_section_layout.addWidget(self.equipment_table, 1)

        # ===== 計算結果區塊：與裝備差異可分別展開 / 收起 =====
        self.result_section_widget = QWidget()
        self.result_section_layout = QVBoxLayout(self.result_section_widget)
        self.result_section_layout.setContentsMargins(0, 0, 0, 0)

        result_header = QHBoxLayout()
        result_header.setContentsMargins(0, 0, 0, 0)
        self.result_title_label = QLabel("計算結果(以最左側的結果比對)")
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
        # 記住使用者最後一次在兩區皆展開時拖出的比例；收合再展開時恢復。
        self._compare_splitter_sizes = [540, 360]
        QTimer.singleShot(0, lambda: self.compare_splitter.setSizes(self._compare_splitter_sizes))

        self.update_current_button.clicked.connect(self.refresh_current_snapshot)
        self.add_json_button.clicked.connect(self.add_json_files)
        self.remove_json_button.clicked.connect(self.remove_selected_json)
        self.clear_json_button.clicked.connect(self.clear_jsons)
        self.show_current_checkbox.toggled.connect(self.refresh_tables)
        self.only_diff_checkbox.toggled.connect(self.refresh_tables)
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

        # 批次計算會暫時把主畫面切換成各專案檔，最後一定還原進入批次前的狀態。
        restore_state = self.service.collect_project_state_data()
        auto_compare = bool(
            hasattr(self.main_window, "auto_compare_checkbox")
            and self.main_window.auto_compare_checkbox.isChecked()
        )

        try:
            if hasattr(self.main_window, "auto_compare_checkbox"):
                self.main_window.auto_compare_checkbox.setChecked(False)

            for i, path in enumerate(paths, 1):
                self.status_label.setText(f"計算 {i}/{len(paths)}：{Path(path).name}")
                QApplication.processEvents()

                snapshot = self.service.create_json_compare_snapshot(path)

                # 同一路徑再次加入時更新，不建立重複欄位。
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
        finally:
            restore_error = None
            try:
                self.status_label.setText("正在恢復主畫面...")
                QApplication.processEvents()
                self.service.restore_project_state_data(restore_state, recalculate=True)
            except Exception as exc:
                restore_error = exc
                print(f"⚠️ 多裝備比對後恢復主畫面失敗：{exc}")
            finally:
                if hasattr(self.main_window, "auto_compare_checkbox"):
                    self.main_window.auto_compare_checkbox.setChecked(auto_compare)
                    if auto_compare:
                        try:
                            self.main_window.compare_with_base()
                        except Exception:
                            pass

            if restore_error is not None:
                QMessageBox.warning(
                    self,
                    "多裝備比對",
                    f"專案檔已完成處理，但恢復主畫面時發生錯誤：\n{restore_error}",
                )

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
        if not snapshots:
            for table in (self.equipment_table, self.result_table):
                table.clear()
                table.setRowCount(0)
                table.setColumnCount(0)
            return

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

    def _refresh_result_table(self, snapshots):
        keys = self._ordered_keys(snapshots, "results")

        # 無論 Snapshot 建立順序如何，都固定把角色基本資料排在比對結果後段：
        # 先顯示傷害 / 增傷等主要計算結果，再顯示等級、六圍、特性素質。
        character_prefixes = ("角色等級 / ", "素質 / ", "特性素質 / ")
        main_keys = [key for key in keys if not key.startswith(character_prefixes)]
        character_keys = [key for key in keys if key.startswith(character_prefixes)]
        keys = main_keys + character_keys

        hide_same = self.only_diff_checkbox.isChecked() and len(snapshots) > 1

        visible_keys = []
        always_show_keys = {"技能名稱", "技能等級"}
        for key in keys:
            values = [s.get("results", {}).get(key, {}).get("display", "") for s in snapshots]
            # 技能名稱 / 技能等級是本次比較的基本上下文，即使勾選「只顯示差異」
            # 且各欄內容完全相同，也固定保留在計算結果最前面。
            if key not in always_show_keys and hide_same and len(set(values)) <= 1:
                continue
            visible_keys.append(key)

        self._setup_table(self.result_table, snapshots, len(visible_keys))

        for row, key in enumerate(visible_keys):
            label_item = QTableWidgetItem(key)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            self.result_table.setItem(row, 0, label_item)

            all_display = [s.get("results", {}).get(key, {}).get("display", "") for s in snapshots]
            is_diff = len(set(all_display)) > 1

            for col, snap in enumerate(snapshots, 1):
                entry = snap.get("results", {}).get(key)
                display = "" if not entry else entry.get("display", "")
                diff_text = None
                higher = None

                # 所有右側欄位都固定與「最左側實際顯示的 Snapshot」比較。
                # 有顯示「目前設定」時，以目前設定為基準；未顯示時，
                # snapshots[0] 就是第一個專案檔，因此自然改以第一個專案檔為基準。
                # 右側數值較高 -> 括號內綠字；較低 -> 括號內紅字。
                if col > 1 and entry:
                    base_snap = snapshots[0]
                    base_entry = base_snap.get("results", {}).get(key)
                    if base_entry:
                        old_num = base_entry.get("number")
                        new_num = entry.get("number")
                        if old_num is not None and new_num is not None and old_num != new_num:
                            diff = new_num - old_num
                            suffix = entry.get("suffix", "")
                            higher = new_num > old_num

                            if "傷害" in key and old_num != 0:
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
                    label.setToolTip(entry.get("display", ""))
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
