from __future__ import annotations

import os
import re
import json
import random
import sys
import difflib
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QDoubleSpinBox,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class _NoWheelComboBox(QComboBox):
    """Editable combo box that never changes selection from the mouse wheel."""

    def wheelEvent(self, event):
        event.ignore()


class _NoWheelSpinBox(QSpinBox):
    """Integer spin box that ignores mouse-wheel input."""

    def wheelEvent(self, event):
        event.ignore()


class _NoWheelDoubleSpinBox(QDoubleSpinBox):
    """Decimal spin box that ignores mouse-wheel input."""

    def wheelEvent(self, event):
        event.ignore()


# -----------------------------------------------------------------------------
# lapineupgradebox.lub parser
# -----------------------------------------------------------------------------

def read_text_with_fallback(path: str) -> str:
    """Read the decompiled LUB file, preferring Taiwan RO's CP950 encoding."""
    encodings = ("utf-8-sig", "utf-8", "cp950", "big5", "cp936", "cp932", "latin1")
    last_error: Optional[Exception] = None
    for encoding in encodings:
        try:
            with open(path, "r", encoding=encoding) as handle:
                return handle.read()
        except (UnicodeDecodeError, OSError) as exc:
            last_error = exc

    if last_error:
        raise last_error
    raise OSError(f"Unable to read file: {path}")


def find_lapine_upgrade_file(base_dir: str) -> Optional[str]:
    """Find the LUB file in the locations commonly used by ItemSearchApp."""
    candidates = (
        os.path.join(base_dir, "data", "lapineupgradebox.lub"),
        os.path.join(base_dir, "data", "LapineUpgradeBox.lub"),
        os.path.join(base_dir, "lapineupgradebox.lub"),
        os.path.join(base_dir, "LapineUpgradeBox.lub"),
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def _skip_quoted_string(text: str, index: int) -> int:
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


def _skip_comment(text: str, index: int) -> int:
    if text.startswith("--[[", index):
        end = text.find("]]", index + 4)
        return len(text) if end < 0 else end + 2
    if text.startswith("--", index):
        end = text.find("\n", index + 2)
        return len(text) if end < 0 else end + 1
    return index


def _find_matching_brace(text: str, open_index: int) -> int:
    """Return the matching closing brace while ignoring strings and Lua comments."""
    if open_index < 0 or open_index >= len(text) or text[open_index] != "{":
        raise ValueError("open_index does not point to an opening brace")

    depth = 0
    index = open_index
    while index < len(text):
        if text.startswith("--", index):
            index = _skip_comment(text, index)
            continue

        char = text[index]
        if char in ('"', "'"):
            index = _skip_quoted_string(text, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1

    raise ValueError("Unbalanced Lua table braces")


def _decode_lua_string(value: str) -> str:
    """Decode the small set of escapes used by the decompiled data file."""
    replacements = {
        r"\\": "\\",
        r'\"': '"',
        r"\'": "'",
        r"\n": "\n",
        r"\r": "\r",
        r"\t": "\t",
    }
    result = value
    for source, target in replacements.items():
        result = result.replace(source, target)
    return result


def _extract_scalar_int(block: str, field: str, default: int = 0) -> int:
    match = re.search(rf"\b{re.escape(field)}\s*=\s*(-?\d+)", block)
    return int(match.group(1)) if match else int(default)


def _extract_scalar_bool(block: str, field: str, default: bool = False) -> bool:
    match = re.search(rf"\b{re.escape(field)}\s*=\s*(true|false)", block, re.I)
    return match.group(1).lower() == "true" if match else bool(default)


def _extract_scalar_string(block: str, field: str, default: str = "") -> str:
    match = re.search(
        rf"\b{re.escape(field)}\s*=\s*\"((?:\\.|[^\"\\])*)\"",
        block,
        re.S,
    )
    return _decode_lua_string(match.group(1)) if match else default


def _extract_table_body(block: str, field: str) -> str:
    match = re.search(rf"\b{re.escape(field)}\s*=\s*\{{", block)
    if not match:
        return ""
    open_index = match.end() - 1
    close_index = _find_matching_brace(block, open_index)
    return block[open_index + 1:close_index]


def _iter_named_target_blocks(targets_body: str) -> Iterable[Tuple[str, str]]:
    """Yield top-level [\"key\"] = { ... } entries from the targets table."""
    entry_pattern = re.compile(r'\[\s*"((?:\\.|[^"\\])*)"\s*\]\s*=\s*\{')
    index = 0
    depth = 0

    while index < len(targets_body):
        if targets_body.startswith("--", index):
            index = _skip_comment(targets_body, index)
            continue

        char = targets_body[index]
        if char in ('"', "'"):
            index = _skip_quoted_string(targets_body, index)
            continue

        if depth == 0:
            match = entry_pattern.match(targets_body, index)
            if match:
                open_index = match.end() - 1
                close_index = _find_matching_brace(targets_body, open_index)
                yield _decode_lua_string(match.group(1)), targets_body[open_index + 1:close_index]
                index = close_index + 1
                continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        index += 1


def parse_lapine_upgrade_box(filename: str) -> Dict[str, Dict[str, Any]]:
    """
    Parse tblLapineUpgradeBox.targets.

    Returned structure:
        {
            key: {
                "key": str,
                "item_id": int,                 # enchant box/material item ID
                "need_refine_min": int,
                "need_refine_max": int,
                "need_option_num_min": int,
                "not_socket_enchant_item": bool,
                "need_source_string": str,
                "target_items": [
                    {"internal_name": str, "item_id": int}, ...
                ],
            }
        }
    """
    if not os.path.isfile(filename):
        raise FileNotFoundError(filename)

    content = read_text_with_fallback(filename)
    targets_match = re.search(r"\btargets\s*=\s*\{", content)
    if not targets_match:
        raise ValueError("tblLapineUpgradeBox.targets was not found")

    targets_open = targets_match.end() - 1
    targets_close = _find_matching_brace(content, targets_open)
    targets_body = content[targets_open + 1:targets_close]

    parsed: Dict[str, Dict[str, Any]] = {}
    target_pair_pattern = re.compile(
        r'\{\s*"((?:\\.|[^"\\])*)"\s*,\s*(\d+)\s*\}',
        re.S,
    )

    for key, block in _iter_named_target_blocks(targets_body):
        item_id = _extract_scalar_int(block, "ItemID", 0)
        if item_id <= 0:
            continue

        target_items_body = _extract_table_body(block, "TargetItems")
        target_items = [
            {
                "internal_name": _decode_lua_string(internal_name),
                "item_id": int(target_item_id),
            }
            for internal_name, target_item_id in target_pair_pattern.findall(target_items_body)
        ]

        parsed[key] = {
            "key": key,
            "item_id": item_id,
            "need_refine_min": _extract_scalar_int(block, "NeedRefineMin", 0),
            "need_refine_max": _extract_scalar_int(block, "NeedRefineMax", 20),
            "need_option_num_min": _extract_scalar_int(block, "NeedOptionNumMin", 0),
            "not_socket_enchant_item": _extract_scalar_bool(
                block, "NotSocketEnchantItem", False
            ),
            "need_source_string": _extract_scalar_string(block, "NeedSource_String", ""),
            "target_items": target_items,
        }

    return parsed


def build_target_item_map(
    parsed: Mapping[str, Mapping[str, Any]],
) -> Dict[int, List[Dict[str, Any]]]:
    """Build target equipment ItemID -> all compatible Lapine box records."""
    result: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for key, box in (parsed or {}).items():
        for target in box.get("target_items", []) or []:
            try:
                target_item_id = int(target.get("item_id"))
            except (TypeError, ValueError, AttributeError):
                continue

            record = dict(box)
            record["key"] = str(box.get("key") or key)
            record["matched_target"] = dict(target)
            result[target_item_id].append(record)

    for target_item_id in result:
        result[target_item_id].sort(key=lambda row: (int(row.get("item_id", 0)), row.get("key", "")))
    return dict(result)


def _coerce_item_id(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def build_item_name_index(item_data: Mapping[Any, Mapping[str, Any]]) -> Dict[str, List[int]]:
    """Index ItemSearchApp display names and internal names without losing duplicates."""
    index: Dict[str, List[int]] = defaultdict(list)
    for raw_item_id, item in (item_data or {}).items():
        item_id = _coerce_item_id(raw_item_id)
        if item_id is None or not isinstance(item, Mapping):
            continue

        names = {
            str(item.get("name") or "").strip(),
            str(item.get("kr_name") or "").strip(),
        }
        for name in names:
            if name and item_id not in index[name]:
                index[name].append(item_id)

    return dict(index)


def resolve_item_id_by_display_name(
    equipment_name: str,
    item_data: Mapping[Any, Mapping[str, Any]],
    name_index: Optional[Mapping[str, List[int]]] = None,
) -> Optional[int]:
    """Resolve the read-only equipment text used by ItemSearchApp back to an ItemID."""
    name = str(equipment_name or "").strip()
    if not name:
        return None

    explicit_id = re.search(r"\(ID\s*:\s*(\d+)\)\s*$", name, re.I)
    if explicit_id:
        item_id = int(explicit_id.group(1))
        if item_id in item_data or str(item_id) in item_data:
            return item_id

    index = name_index or build_item_name_index(item_data)
    candidates = list(index.get(name, []))
    if len(candidates) == 1:
        return candidates[0]

    # Backward compatibility for old presets saved before duplicate names gained an ID suffix.
    base_name = re.sub(r"\s*\(ID\s*:\s*\d+\)\s*$", "", name, flags=re.I)
    candidates = list(index.get(base_name, []))
    return candidates[0] if len(candidates) == 1 else None


def get_item_info(item_data: Mapping[Any, Mapping[str, Any]], item_id: int) -> Mapping[str, Any]:
    item = item_data.get(item_id)
    if item is None:
        item = item_data.get(str(item_id))
    return item if isinstance(item, Mapping) else {}


def get_item_display_name(
    item_data: Mapping[Any, Mapping[str, Any]],
    item_id: int,
    fallback: str = "",
) -> str:
    item = get_item_info(item_data, item_id)
    return str(item.get("name") or fallback or f"ID:{item_id}")



# -----------------------------------------------------------------------------
# Custom Lapine probability tables / random-option name and output format support
# -----------------------------------------------------------------------------

PROBABILITY_DATA_FILENAME = "lapine_random_options.json"
OPTION_NAME_TABLE_FILENAME = "AddRandomOptionNameTable.lua"
ENCHANT_NAME_TABLE_FILENAME = "EnchantName.lua"


def get_runtime_base_dir() -> str:
    """Return the application directory both in source and frozen builds."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _find_data_file(base_dir: str, filename: str) -> Optional[str]:
    candidates = (
        os.path.join(base_dir, "data", filename),
        os.path.join(base_dir, filename),
    )
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def find_random_option_name_table(base_dir: str) -> Optional[str]:
    return _find_data_file(base_dir, OPTION_NAME_TABLE_FILENAME)


def find_enchant_name_table(base_dir: str) -> Optional[str]:
    return _find_data_file(base_dir, ENCHANT_NAME_TABLE_FILENAME)


def _parse_enumvar_string_table(filename: str) -> Dict[str, str]:
    """Parse ``[EnumVAR.CODE[1]] = \"value\"`` entries from a Lua table."""
    if not os.path.isfile(filename):
        raise FileNotFoundError(filename)
    content = read_text_with_fallback(filename)
    pattern = re.compile(
        r'\[\s*EnumVAR\.([A-Za-z0-9_]+)\s*\[\s*1\s*\]\s*\]\s*=\s*'
        r'"((?:\\.|[^"\\])*)"',
        re.S,
    )
    result: Dict[str, str] = {}
    for code, raw_template in pattern.findall(content):
        result[code] = _decode_lua_string(raw_template)
    return result


def parse_random_option_name_table(filename: str) -> Dict[str, str]:
    """Parse EnumVAR code -> user-facing display template."""
    return _parse_enumvar_string_table(filename)


def parse_enchant_name_table(filename: str) -> Dict[str, str]:
    """Parse EnumVAR code -> ItemSearchApp Lua effect template."""
    return _parse_enumvar_string_table(filename)


def get_probability_data_path(base_dir: str) -> str:
    return os.path.join(base_dir, "data", PROBABILITY_DATA_FILENAME)


def _empty_probability_store() -> Dict[str, Any]:
    return {"version": 2, "tables": {}}


def load_probability_store(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return _empty_probability_store()
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _empty_probability_store()
    if not isinstance(data, dict):
        return _empty_probability_store()
    if not isinstance(data.get("tables"), dict):
        data["tables"] = {}
    data["version"] = max(2, int(data.get("version", 1) or 1))
    return data


def save_probability_store(path: str, store: Mapping[str, Any]) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    temp_path = f"{path}.tmp"
    payload = dict(store)
    payload["version"] = max(2, int(payload.get("version", 2) or 2))
    with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp_path, path)


def _replace_lua_percent_tokens(template: str, value_text: str) -> str:
    percent_token = "\u0000PERCENT\u0000"
    rendered = str(template or "").replace("%%", percent_token)
    rendered = rendered.replace("%d", str(value_text))
    return rendered.replace(percent_token, "%").strip()


def render_option_preview(template: str, minimum: int, maximum: int) -> str:
    """Render a ``%d`` placeholder as one value or a min-max range."""
    template = str(template or "")
    if not template:
        return ""
    value_text = str(int(minimum))
    if int(minimum) != int(maximum):
        value_text = f"{int(minimum)}～{int(maximum)}"
    return _replace_lua_percent_tokens(template, value_text)


def render_option_value(template: str, value: int) -> str:
    """Render one concrete display or Lua-effect value."""
    return _replace_lua_percent_tokens(str(template or ""), str(int(value)))


def format_probability_display(value: Any) -> str:
    """Display at most one decimal while keeping the stored numeric precision."""
    try:
        text = f"{float(value):.1f}"
    except (TypeError, ValueError):
        text = "0.0"
    return text.rstrip("0").rstrip(".")


def preview_probability_row(row: Mapping[str, Any], option_names: Mapping[str, str]) -> str:
    code = str(row.get("option_code") or "").strip()
    template = str(option_names.get(code) or "")
    if not template:
        return str(row.get("raw_effect") or code or "（未指定）")
    try:
        minimum = int(row.get("min_value", 0))
        maximum = int(row.get("max_value", minimum))
    except (TypeError, ValueError):
        minimum = maximum = 0
    return render_option_preview(template, minimum, maximum)


def preview_enchant_lua_row(row: Mapping[str, Any], enchant_names: Mapping[str, str]) -> str:
    code = str(row.get("option_code") or "").strip()
    template = str(enchant_names.get(code) or "")
    if not template:
        return "（EnchantName.lua 無對應格式）"
    try:
        minimum = int(row.get("min_value", 0))
        maximum = int(row.get("max_value", minimum))
    except (TypeError, ValueError):
        minimum = maximum = 0
    return render_option_preview(template, minimum, maximum)


def normalize_profile_groups(profile: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Return ordered group settings, migrating legacy row-only profiles in memory."""
    groups: List[Dict[str, Any]] = []
    seen = set()
    raw_groups = profile.get("groups", []) if isinstance(profile, Mapping) else []

    if isinstance(raw_groups, Mapping):
        raw_groups = [
            {"name": name, "probability": probability}
            for name, probability in raw_groups.items()
        ]

    if isinstance(raw_groups, list):
        for raw_group in raw_groups:
            if not isinstance(raw_group, Mapping):
                continue
            name = str(raw_group.get("name") or raw_group.get("group") or "").strip()
            if not name or name in seen:
                continue
            try:
                probability = float(raw_group.get("probability", 100.0))
            except (TypeError, ValueError):
                probability = 100.0
            groups.append({"name": name, "probability": probability})
            seen.add(name)

    rows = profile.get("rows", []) if isinstance(profile, Mapping) else []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            name = str(row.get("group") or "1").strip() or "1"
            if name not in seen:
                groups.append({"name": name, "probability": 100.0})
                seen.add(name)

    if not groups:
        groups.append({"name": "1", "probability": 100.0})
    return groups


def roll_grouped_probability_options(
    profile: Mapping[str, Any],
    option_names: Mapping[str, str],
    enchant_names: Mapping[str, str],
    rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    """Roll every configured group independently, then select one option inside it.

    Group probability controls whether the whole group appears.  If the group appears,
    the option percentages are evaluated only inside that group.  Therefore groups 1
    and 2 can be 100%, while group 3 can be (for example) 25% and simply produce no
    third enchant on the remaining 75% of attempts.
    """
    generator = rng or random.SystemRandom()
    rows = [dict(row) for row in (profile.get("rows", []) or []) if isinstance(row, Mapping)]
    groups = normalize_profile_groups(profile)

    normalized_rows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    missing_codes = set()
    for raw_row in rows:
        group_name = str(raw_row.get("group") or "1").strip() or "1"
        code = str(raw_row.get("option_code") or "").strip()
        try:
            probability = float(raw_row.get("probability", 0.0))
        except (TypeError, ValueError):
            probability = 0.0
        if probability <= 0:
            continue
        if not code:
            raise ValueError(f"群組「{group_name}」有機率大於 0% 但未指定 EnumVAR 的列。")
        if code not in enchant_names:
            missing_codes.add(code)
        try:
            minimum = int(raw_row.get("min_value", 0))
            maximum = int(raw_row.get("max_value", minimum))
        except (TypeError, ValueError):
            minimum = maximum = 0
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        row = dict(raw_row)
        row.update({
            "group": group_name,
            "option_code": code,
            "probability": probability,
            "min_value": minimum,
            "max_value": maximum,
        })
        normalized_rows[group_name].append(row)

    if missing_codes:
        raise ValueError(
            "以下 EnumVAR 在 EnchantName.lua 找不到主程式詞條格式："
            + "、".join(sorted(missing_codes))
        )
    if not normalized_rows:
        raise ValueError("目前機率表沒有大於 0% 的附魔項目。")

    results: List[Dict[str, Any]] = []
    attempts: List[Dict[str, Any]] = []
    for group in groups:
        group_name = str(group.get("name") or "").strip()
        if not group_name:
            continue
        try:
            group_probability = float(group.get("probability", 100.0))
        except (TypeError, ValueError):
            group_probability = 100.0
        if group_probability < 0 or group_probability > 100.0 + 1e-9:
            raise ValueError(f"群組「{group_name}」出現率必須介於 0% 到 100%。")

        group_rows = normalized_rows.get(group_name, [])
        if not group_rows:
            attempts.append({
                "group": group_name,
                "group_probability": group_probability,
                "group_roll": None,
                "success": False,
                "reason": "群組內沒有有效附魔列",
            })
            continue

        option_total = sum(float(row["probability"]) for row in group_rows)
        if option_total > 100.0 + 1e-9:
            raise ValueError(
                f"群組「{group_name}」的組內機率合計為 {option_total:g}%，超過 100%。"
            )

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

        option_roll = float(generator.random()) * 100.0
        cumulative = 0.0
        selected: Optional[Dict[str, Any]] = None
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
                "option_total": option_total,
                "success": False,
                "reason": "組內未抽中任何詞條",
            })
            continue

        value = int(generator.randint(int(selected["min_value"]), int(selected["max_value"])))
        code = str(selected["option_code"])
        display_template = str(option_names.get(code) or code)
        lua_template = str(enchant_names.get(code) or "")
        result = {
            "group": group_name,
            "group_probability": group_probability,
            "group_roll": group_roll,
            "option_roll": option_roll,
            "option_total": option_total,
            "row": selected,
            "option_code": code,
            "value": value,
            "display_text": render_option_value(display_template, value),
            "lua_effect": render_option_value(lua_template, value),
            "success": True,
        }
        results.append(result)
        attempts.append(result)

    return {
        "success": bool(results),
        "results": results,
        "attempts": attempts,
    }


class LapineProbabilityEditor(QDialog):
    """Create group probabilities and per-group random-option tables."""

    saved = Signal(str)
    COL_GROUP = 0
    COL_CODE = 1
    COL_MIN = 2
    COL_MAX = 3
    COL_RATE = 4
    COL_PREVIEW = 5
    COL_LUA = 6
    COL_NOTE = 7

    GROUP_COL_NAME = 0
    GROUP_COL_RATE = 1

    def __init__(
        self,
        probability_path: str,
        table_key: str,
        option_names: Mapping[str, str],
        enchant_names: Mapping[str, str],
        parent: Optional[QWidget] = None,
        box_item_id: int = 0,
        default_title: str = "",
    ):
        super().__init__(parent)
        self.probability_path = probability_path
        self.table_key = str(table_key or "").strip()
        self.option_names = dict(option_names or {})
        self.enchant_names = dict(enchant_names or {})
        self.box_item_id = int(box_item_id or 0)
        self.default_title = str(default_title or self.table_key)
        self.setWindowTitle("Lapine 附魔機率編輯器")
        self.resize(1280, 900)

        root = QVBoxLayout(self)
        meta = QFormLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("例如：英雄戰靴隨機附魔")
        meta.addRow("機率表名稱", self.title_edit)
        key_label = QLabel(self.table_key or "（未綁定 Lapine 鍵值）")
        key_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        meta.addRow("Lapine 鍵值", key_label)
        root.addLayout(meta)

        display_name_row = QHBoxLayout()
        self.name_table_status = QLabel()
        self.name_table_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.load_name_table_button = QPushButton("載入顯示名稱表")
        self.load_name_table_button.clicked.connect(self.choose_name_table)
        display_name_row.addWidget(self.name_table_status, 1)
        display_name_row.addWidget(self.load_name_table_button)
        root.addLayout(display_name_row)

        enchant_name_row = QHBoxLayout()
        self.enchant_table_status = QLabel()
        self.enchant_table_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.load_enchant_table_button = QPushButton("載入 EnchantName.lua")
        self.load_enchant_table_button.clicked.connect(self.choose_enchant_table)
        enchant_name_row.addWidget(self.enchant_table_status, 1)
        enchant_name_row.addWidget(self.load_enchant_table_button)
        root.addLayout(enchant_name_row)

        group_box = QGroupBox("群組出現率（每個群組獨立判定）")
        group_layout = QVBoxLayout(group_box)
        self.group_table = QTableWidget(0, 2)
        self.group_table.setHorizontalHeaderLabels(["群組名稱", "群組出現率(%)"])
        self.group_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.group_table.verticalHeader().setVisible(False)
        self.group_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.group_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.group_table.setMaximumHeight(180)
        group_layout.addWidget(self.group_table)
        group_buttons = QHBoxLayout()
        add_group_button = QPushButton("新增群組")
        add_group_button.clicked.connect(lambda: self.add_group({}))
        delete_group_button = QPushButton("刪除群組")
        delete_group_button.clicked.connect(self.delete_selected_groups)
        bulk_import_button = QPushButton("批次貼上資料")
        bulk_import_button.setToolTip(
            "貼上「內容 / 機率 / 備註」表格，自動建立群組分頁並配對 EnumVAR。"
        )
        bulk_import_button.clicked.connect(self.open_bulk_import_dialog)
        group_buttons.addWidget(add_group_button)
        group_buttons.addWidget(delete_group_button)
        group_buttons.addWidget(bulk_import_button)
        group_buttons.addStretch(1)
        group_layout.addLayout(group_buttons)
        root.addWidget(group_box)

        option_box = QGroupBox("群組內附魔詞條（每個群組使用獨立分頁）")
        option_layout = QVBoxLayout(option_box)
        self._group_tables: Dict[str, QTableWidget] = {}
        self._next_group_key = 1
        self.group_tabs = QTabWidget()
        self.group_tabs.setDocumentMode(True)
        self.group_tabs.setMovable(False)
        self.group_tabs.currentChanged.connect(self._on_group_tab_changed)
        option_layout.addWidget(self.group_tabs, 1)

        tool_row = QHBoxLayout()
        add_button = QPushButton("新增列")
        add_button.clicked.connect(lambda: self.add_row({}))
        duplicate_button = QPushButton("複製列")
        duplicate_button.clicked.connect(self.duplicate_selected_rows)
        delete_button = QPushButton("刪除列")
        delete_button.clicked.connect(self.delete_selected_rows)
        clear_button = QPushButton("清空目前群組")
        clear_button.clicked.connect(self.clear_rows)
        tool_row.addWidget(add_button)
        tool_row.addWidget(duplicate_button)
        tool_row.addWidget(delete_button)
        tool_row.addWidget(clear_button)
        tool_row.addStretch(1)
        self.total_rate_label = QLabel()
        tool_row.addWidget(self.total_rate_label)
        option_layout.addLayout(tool_row)
        root.addWidget(option_box, 1)

        self.group_table.itemChanged.connect(self._on_group_item_changed)
        self.group_table.cellClicked.connect(self._on_group_cell_clicked)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._load_existing_profile()
        self._update_name_table_status()
        self._update_probability_total()

    def _update_name_table_status(self):
        self.name_table_status.setText(
            f"AddRandomOptionNameTable：已載入 {len(self.option_names)} 個顯示名稱"
            if self.option_names else
            "AddRandomOptionNameTable：尚未載入"
        )
        self.enchant_table_status.setText(
            f"EnchantName.lua：已載入 {len(self.enchant_names)} 個主程式詞條格式"
            if self.enchant_names else
            "EnchantName.lua：尚未載入；隨機結果無法寫入主程式詞條"
        )

    def choose_name_table(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "選擇 AddRandomOptionNameTable.lua", "", "Lua files (*.lua *.lub);;All files (*)"
        )
        if not filename:
            return
        try:
            self.option_names = parse_random_option_name_table(filename)
        except Exception as exc:
            QMessageBox.warning(self, "載入失敗", f"無法解析顯示名稱表：\n{exc}")
            return
        self._reload_code_combos_and_previews()

    def choose_enchant_table(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "選擇 EnchantName.lua", "", "Lua files (*.lua *.lub);;All files (*)"
        )
        if not filename:
            return
        try:
            self.enchant_names = parse_enchant_name_table(filename)
        except Exception as exc:
            QMessageBox.warning(self, "載入失敗", f"無法解析 EnchantName.lua：\n{exc}")
            return
        self._reload_code_combos_and_previews()

    @staticmethod
    def _normalize_import_effect_text(text: Any) -> str:
        """Normalize pasted effect text and AddRandomOptionNameTable templates."""
        value = unicodedata.normalize("NFKC", str(text or ""))
        value = value.replace("％", "%").replace("＋", "+").replace("－", "-")
        # Common announcement wording differs slightly from the client table.
        value = value.replace("首領階級", "首領型").replace("首領級", "首領型")
        value = value.replace("減少攻擊後延遲", "攻擊後延遲-")
        value = value.replace("攻擊後延遲減少", "攻擊後延遲-")
        value = value.replace("，", ",").replace("),", ")")
        value = re.sub(r"\s+", "", value)
        return value.strip(",;；。").casefold()

    @classmethod
    def _import_effect_shape(cls, text: Any, is_template: bool = False) -> str:
        """Replace concrete values or Lua placeholders with one comparison token."""
        value = unicodedata.normalize("NFKC", str(text or ""))
        if is_template:
            percent_token = "\u0000PERCENT\u0000"
            value = value.replace("%%", percent_token)
            value = re.sub(
                r"%(?:[-+ #0]*\d*(?:\.\d+)?[diouxXeEfFgGcs])",
                "#",
                value,
            )
            value = value.replace(percent_token, "%")
        value = cls._normalize_import_effect_text(value)
        if not is_template:
            value = re.sub(
                r"\d+(?:\.\d+)?\s*[~～〜]\s*\d+(?:\.\d+)?",
                "#",
                value,
            )
            value = re.sub(r"\d+(?:\.\d+)?", "#", value)
        return value

    @staticmethod
    def _extract_import_value_range(effect_text: str) -> Tuple[int, int]:
        """Extract the first integer value or integer range from pasted effect text."""
        normalized = unicodedata.normalize("NFKC", str(effect_text or ""))
        range_match = re.search(
            r"(-?\d+(?:\.\d+)?)\s*[~～〜]\s*(-?\d+(?:\.\d+)?)",
            normalized,
        )
        if range_match:
            minimum = int(float(range_match.group(1)))
            maximum = int(float(range_match.group(2)))
            return (minimum, maximum) if minimum <= maximum else (maximum, minimum)

        values = re.findall(r"-?\d+(?:\.\d+)?", normalized)
        if values:
            value = int(float(values[-1]))
            return value, value
        return 0, 0

    @staticmethod
    def _parse_import_probability(text: Any) -> Optional[float]:
        match = re.search(r"-?\d+(?:\.\d+)?", str(text or "").replace(",", ""))
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    @staticmethod
    def _group_name_from_import_heading(text: Any) -> Optional[str]:
        """Resolve headings such as 固定附加第一欄隨機能力 to group name 1."""
        value = unicodedata.normalize("NFKC", str(text or "")).strip()
        if not value:
            return None
        chinese_numbers = {
            "一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
            "六": "6", "七": "7", "八": "8", "九": "9", "十": "10",
        }
        match = re.search(r"第\s*([一二三四五六七八九十]|\d+)\s*欄", value)
        if match:
            token = match.group(1)
            return chinese_numbers.get(token, token)

        stripped = re.sub(r"^[\-=—–_\s]+|[\-=—–_\s]+$", "", value)
        if "隨機能力" in stripped or "附魔" in stripped:
            stripped = re.sub(r"固定附加|隨機附加|隨機能力|附魔", "", stripped).strip()
            return stripped or None
        return None

    def _infer_import_option_code(self, effect_text: str) -> Tuple[str, float]:
        """Infer one EnumVAR from pasted effect text using exact/fuzzy template matching."""
        source_shape = self._import_effect_shape(effect_text)
        if not source_shape:
            return "", 0.0

        candidates: List[Tuple[float, str]] = []
        exact_codes: List[str] = []
        available_codes = sorted(set(self.option_names) & set(self.enchant_names))
        if not available_codes:
            available_codes = sorted(self.option_names)

        for code in available_codes:
            template_shape = self._import_effect_shape(
                self.option_names.get(code, ""), is_template=True
            )
            if not template_shape:
                continue
            if source_shape == template_shape:
                exact_codes.append(code)
                continue
            score = difflib.SequenceMatcher(None, source_shape, template_shape).ratio()
            if source_shape in template_shape or template_shape in source_shape:
                score += 0.08
            candidates.append((score, code))

        if len(exact_codes) == 1:
            return exact_codes[0], 1.0
        if len(exact_codes) > 1:
            return "", 1.0
        if not candidates:
            return "", 0.0

        candidates.sort(reverse=True)
        best_score, best_code = candidates[0]
        second_score = candidates[1][0] if len(candidates) > 1 else 0.0
        if best_score >= 0.78 and best_score - second_score >= 0.035:
            return best_code, min(best_score, 0.999)
        return "", best_score

    def _parse_bulk_import_text(self, text: str) -> Dict[str, Any]:
        """Parse copied TSV/text rows into groups and random-option records."""
        parsed_groups: List[Dict[str, Any]] = []
        rows: List[Dict[str, Any]] = []
        warnings: List[str] = []
        current_group = ""
        seen_groups = set()

        def ensure_group(name: str, probability: float = 100.0):
            group_name = str(name or "").strip() or "1"
            if group_name not in seen_groups:
                parsed_groups.append({"name": group_name, "probability": probability})
                seen_groups.add(group_name)
            return group_name

        for line_number, raw_line in enumerate(str(text or "").splitlines(), 1):
            line = raw_line.strip("\ufeff\r\n")
            if not line.strip():
                continue
            columns = [column.strip() for column in line.split("\t")]
            first = columns[0].strip() if columns else ""
            if not first:
                continue
            if first.casefold() in {"內容", "效果", "附魔名稱", "content"}:
                continue

            heading_group = self._group_name_from_import_heading(first)
            if heading_group is not None and (
                "隨機能力" in first or "附魔" in first or re.search(r"[-=]{3,}", first)
            ):
                heading_rate_match = re.search(
                    r"(\d+(?:\.\d+)?)\s*%", first
                )
                heading_probability = (
                    float(heading_rate_match.group(1)) if heading_rate_match else None
                )
                current_group = ensure_group(
                    heading_group,
                    100.0 if heading_probability is None else heading_probability,
                )
                continue

            probability_text = columns[1] if len(columns) >= 2 else ""
            probability = self._parse_import_probability(probability_text)
            if probability is None:
                # Also accept rows copied with spaces instead of tab characters.
                fallback = re.match(r"^(.*?)\s{2,}(\d+(?:\.\d+)?\s*%)\s*(.*)$", line)
                if fallback:
                    first = fallback.group(1).strip()
                    probability = self._parse_import_probability(fallback.group(2))
                    columns = [first, fallback.group(2), fallback.group(3).strip()]
            if probability is None:
                warnings.append(f"第 {line_number} 行：找不到機率，已略過「{first}」")
                continue
            if probability < 0 or probability > 100:
                warnings.append(f"第 {line_number} 行：機率不在 0～100%，已略過「{first}」")
                continue

            if not current_group:
                current_group = ensure_group(self._first_group_name() or "1", 100.0)
            minimum, maximum = self._extract_import_value_range(first)
            option_code, match_score = self._infer_import_option_code(first)
            note = columns[2].strip() if len(columns) >= 3 else ""
            if not option_code:
                marker = "未自動配對 EnumVAR"
                note = f"{note}｜{marker}" if note else marker
                warnings.append(f"第 {line_number} 行：無法配對 EnumVAR「{first}」")

            rows.append({
                "group": current_group,
                "option_code": option_code,
                "min_value": minimum,
                "max_value": maximum,
                "probability": probability,
                "raw_effect": first,
                "note": note,
                "match_score": match_score,
                "source_line": line_number,
            })

        if not parsed_groups and rows:
            ensure_group(self._first_group_name() or "1", 100.0)
        return {"groups": parsed_groups, "rows": rows, "warnings": warnings}

    @staticmethod
    def _table_has_only_blank_row(table: QTableWidget) -> bool:
        if table.rowCount() != 1:
            return False
        combo = table.cellWidget(0, LapineProbabilityEditor.COL_CODE)
        min_spin = table.cellWidget(0, LapineProbabilityEditor.COL_MIN)
        max_spin = table.cellWidget(0, LapineProbabilityEditor.COL_MAX)
        rate_spin = table.cellWidget(0, LapineProbabilityEditor.COL_RATE)
        note_item = table.item(0, LapineProbabilityEditor.COL_NOTE)
        return (
            (not isinstance(combo, QComboBox) or not combo.currentText().strip())
            and (not isinstance(min_spin, QSpinBox) or min_spin.value() == 0)
            and (not isinstance(max_spin, QSpinBox) or max_spin.value() == 0)
            and (not isinstance(rate_spin, QDoubleSpinBox) or rate_spin.value() == 0)
            and (note_item is None or not note_item.text().strip())
        )

    def _reset_groups_for_bulk_import(self):
        while self.group_tabs.count() > 0:
            page = self.group_tabs.widget(0)
            self.group_tabs.removeTab(0)
            if page is not None:
                page.deleteLater()
        self._group_tables.clear()
        self.group_table.blockSignals(True)
        self.group_table.setRowCount(0)
        self.group_table.blockSignals(False)

    def _find_group_table_by_name(self, group_name: str) -> Optional[QTableWidget]:
        requested = str(group_name or "").strip()
        for _key, existing_name, table in self._all_group_contexts():
            if existing_name == requested:
                return table
        return None

    def _apply_bulk_import(self, parsed: Mapping[str, Any], replace_existing: bool):
        groups = [dict(group) for group in (parsed.get("groups", []) or [])]
        rows = [dict(row) for row in (parsed.get("rows", []) or [])]
        if replace_existing:
            self._reset_groups_for_bulk_import()

        for group in groups:
            name = str(group.get("name") or "").strip() or "1"
            if self._find_group_table_by_name(name) is None:
                self.add_group(group, create_blank=False)

        if not groups and self.group_table.rowCount() == 0:
            self.add_group({"name": "1", "probability": 100.0}, create_blank=False)

        first_unmatched: Optional[Tuple[QTableWidget, int]] = None
        for row_data in rows:
            group_name = str(row_data.get("group") or "1").strip() or "1"
            table = self._find_group_table_by_name(group_name)
            if table is None:
                self.add_group({"name": group_name, "probability": 100.0}, create_blank=False)
                table = self._find_group_table_by_name(group_name)
            if table is None:
                continue
            if self._table_has_only_blank_row(table):
                table.setRowCount(0)
            target_row = table.rowCount()
            self.add_row(row_data, table=table, group_name=group_name)
            if not row_data.get("option_code") and first_unmatched is None:
                first_unmatched = (table, target_row)

        for _key, group_name, table in self._all_group_contexts():
            if table.rowCount() == 0:
                self.add_row({"group": group_name}, table=table, group_name=group_name)

        if first_unmatched is not None:
            table, row = first_unmatched
            for index in range(self.group_tabs.count()):
                page = self.group_tabs.widget(index)
                key = str(getattr(page, "_lapine_group_key", ""))
                if self._group_tables.get(key) is table:
                    self.group_tabs.setCurrentIndex(index)
                    break
            table.selectRow(row)
            note_item = table.item(row, self.COL_NOTE)
            if note_item is not None:
                table.scrollToItem(note_item)
        self._update_probability_total()

    def open_bulk_import_dialog(self, checked: bool = False):
        """Paste an announcement spreadsheet and import all groups in one operation."""
        dialog = QDialog(self)
        dialog.setWindowTitle("批次貼上附魔機率資料")
        dialog.resize(920, 680)
        layout = QVBoxLayout(dialog)

        instruction = QLabel(
            "可直接貼上 Excel／網頁複製的「內容、機率、備註」資料。"
            "程式會辨識第一欄、第二欄等分隔標題，建立群組分頁，並依 "
            "AddRandomOptionNameTable.lua 自動配對 EnumVAR 與數值範圍。"
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("匯入方式"))
        mode_combo = _NoWheelComboBox()
        mode_combo.addItems(["取代目前全部群組資料", "追加到現有群組"])
        mode_row.addWidget(mode_combo)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        editor = QPlainTextEdit()
        editor.setPlaceholderText(
            "內容\t機率\t備註\n"
            "---------------固定附加第一欄隨機能力---------------\n"
            "MHP + 500~2000\t7.000%\n"
            "MSP + 50~1000\t7.000%"
        )
        clipboard_text = QApplication.clipboard().text()
        if clipboard_text.strip():
            editor.setPlainText(clipboard_text)
        layout.addWidget(editor, 1)

        precision_note = QLabel(
            "機率欄位畫面維持一位小數；批次貼上的原始精度（例如 0.975%）會保留於資料中，"
            "手動修改該欄後才改用一位小數值。"
        )
        precision_note.setWordWrap(True)
        layout.addWidget(precision_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("解析並匯入")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        raw_text = editor.toPlainText()
        if not raw_text.strip():
            QMessageBox.information(self, "沒有資料", "請先貼上要匯入的資料。")
            return

        parsed = self._parse_bulk_import_text(raw_text)
        rows = list(parsed.get("rows", []) or [])
        if not rows:
            warnings = "\n".join(list(parsed.get("warnings", []) or [])[:12])
            QMessageBox.warning(
                self,
                "沒有可匯入資料",
                "未辨識到包含內容與機率的資料列。" + (f"\n\n{warnings}" if warnings else ""),
            )
            return

        self._apply_bulk_import(parsed, replace_existing=mode_combo.currentIndex() == 0)
        matched = sum(1 for row in rows if row.get("option_code"))
        unmatched = len(rows) - matched
        groups = list(parsed.get("groups", []) or [])
        warning_lines = list(parsed.get("warnings", []) or [])
        detail = (
            f"已匯入 {len(groups) or 1} 個群組、{len(rows)} 列；"
            f"自動配對 {matched} 列，未配對 {unmatched} 列。"
        )
        if unmatched:
            detail += "\n未配對列已選取並標記，請在 EnumVAR 欄手動選擇。"
        if warning_lines:
            detail += "\n\n" + "\n".join(warning_lines[:10])
            if len(warning_lines) > 10:
                detail += f"\n……另有 {len(warning_lines) - 10} 筆訊息。"
        QMessageBox.information(self, "批次匯入完成", detail)

    @staticmethod
    def _normalize_code_search_text(text: Any) -> str:
        """Normalize visible effect text for exact-match fallback resolution."""
        return re.sub(r"\s+", " ", str(text or "").casefold()).strip()

    @staticmethod
    def _option_template_to_search_label(template: str) -> str:
        """Turn a Lua printf template into a readable completion label."""
        value_token = "\u0000VALUE\u0000"
        percent_token = "\u0000PERCENT\u0000"
        text = str(template or "")
        text = text.replace("%%", percent_token)
        text = re.sub(
            r"%(?:[-+ #0]*\d*(?:\.\d+)?[diouxXeEfFgGcs])",
            value_token,
            text,
        )
        text = text.replace(value_token, "數值").replace(percent_token, "%")
        return re.sub(r"\s+", " ", text).strip()

    def _build_code_completion_data(self):
        """Build human-readable choices while keeping EnumVAR as the stored value."""
        labels: List[str] = []
        label_to_code: Dict[str, str] = {}
        description_to_codes: Dict[str, List[str]] = defaultdict(list)

        for code in sorted(set(self.option_names) | set(self.enchant_names)):
            description = self._option_template_to_search_label(
                self.option_names.get(code, "")
            )
            label = f"{description}  —  {code}" if description else code
            labels.append(label)
            label_to_code[label] = code
            if description:
                normalized = self._normalize_code_search_text(description)
                if code not in description_to_codes[normalized]:
                    description_to_codes[normalized].append(code)

        return labels, label_to_code, dict(description_to_codes)

    def _resolve_code_input(
        self,
        text: Any,
        combo: Optional[QComboBox] = None,
    ) -> str:
        """Resolve a completion label or exact description back to its EnumVAR code."""
        value = str(text or "").strip()
        if not value:
            return ""

        all_codes = sorted(set(self.option_names) | set(self.enchant_names))
        canonical_by_casefold = {code.casefold(): code for code in all_codes}
        canonical = canonical_by_casefold.get(value.casefold())
        if canonical:
            return canonical

        label_to_code = getattr(combo, "_lapine_label_to_code", {}) if combo else {}
        mapped = label_to_code.get(value) if isinstance(label_to_code, dict) else None
        if mapped:
            return str(mapped)

        # Also accept a copied completion label such as
        # "無屬性攻擊耐性+ 數值% — ATTR_TOLERACE_NOTHING".
        suffix_match = re.search(r"[—–-]\s*([A-Za-z0-9_]+)\s*$", value)
        if suffix_match:
            canonical = canonical_by_casefold.get(suffix_match.group(1).casefold())
            if canonical:
                return canonical

        description_to_codes = (
            getattr(combo, "_lapine_description_to_codes", {}) if combo else {}
        )
        normalized = self._normalize_code_search_text(value)
        exact_codes = (
            description_to_codes.get(normalized, [])
            if isinstance(description_to_codes, dict) else []
        )
        if len(exact_codes) == 1:
            return str(exact_codes[0])

        return value

    def _configure_code_combo(self, combo: QComboBox, code: str = ""):
        labels, label_to_code, description_to_codes = self._build_code_completion_data()
        combo._lapine_label_to_code = label_to_code
        combo._lapine_description_to_codes = description_to_codes

        combo.blockSignals(True)
        combo.clear()
        combo.addItems(labels)
        combo.setCurrentIndex(-1)
        combo.setEditText(self._resolve_code_input(code, combo))
        combo.blockSignals(False)

        line_edit = combo.lineEdit()
        if line_edit is not None:
            line_edit.setPlaceholderText("輸入中文效果或 EnumVAR 代碼...")

        completer = combo.completer()
        if isinstance(completer, QCompleter):
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            completer.setCompletionMode(QCompleter.PopupCompletion)
            # 輸入欄保持窄版，但搜尋結果清單保留足夠寬度顯示中文與代碼。
            popup = completer.popup()
            if popup is not None:
                popup.setMinimumWidth(460)

    def _commit_code_completion(self, combo: QComboBox, selected_text: str):
        code = self._resolve_code_input(selected_text, combo)
        if not code or code == str(selected_text or "").strip():
            return

        # QComboBox/QCompleter may write the visible label after activated is emitted.
        # Commit on the next event-loop cycle so the editor ends with the EnumVAR code.
        def apply_code():
            combo.setCurrentIndex(-1)
            combo.setEditText(code)

        QTimer.singleShot(0, apply_code)

    def _create_option_table(self) -> QTableWidget:
        """Create the option table used inside one group tab."""
        table = QTableWidget(0, 8)
        table.setHorizontalHeaderLabels([
            "群組", "EnumVAR", "最小值", "最大值", "組內機率(%)",
            "顯示預覽", "主程式詞條格式", "備註"
        ])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        # 群組由分頁決定，不需要在每一列重複顯示。
        table.setColumnHidden(self.COL_GROUP, True)
        header = table.horizontalHeader()
        for column in (self.COL_MIN, self.COL_MAX, self.COL_RATE):
            header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(self.COL_CODE, QHeaderView.Fixed)
        header.resizeSection(self.COL_CODE, 175)
        header.setSectionResizeMode(self.COL_PREVIEW, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_LUA, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_NOTE, QHeaderView.Stretch)
        return table

    def _new_group_key(self) -> str:
        key = f"group_{self._next_group_key}"
        self._next_group_key += 1
        return key

    def _group_key_for_row(self, row: int) -> str:
        item = self.group_table.item(row, self.GROUP_COL_NAME)
        return str(item.data(Qt.UserRole) or "") if item else ""

    def _group_name_for_key(self, group_key: str) -> str:
        for row in range(self.group_table.rowCount()):
            if self._group_key_for_row(row) == group_key:
                item = self.group_table.item(row, self.GROUP_COL_NAME)
                return item.text().strip() if item else ""
        return ""

    def _find_tab_index_by_key(self, group_key: str) -> int:
        for index in range(self.group_tabs.count()):
            page = self.group_tabs.widget(index)
            if str(getattr(page, "_lapine_group_key", "")) == group_key:
                return index
        return -1

    def _create_group_tab(self, group_key: str, group_name: str) -> QTableWidget:
        page = QWidget()
        page._lapine_group_key = group_key
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(4, 4, 4, 4)
        table = self._create_option_table()
        page_layout.addWidget(table)
        self._group_tables[group_key] = table
        title = group_name or f"群組 {self.group_tabs.count() + 1}"
        self.group_tabs.addTab(page, title)
        return table

    def _remove_group_tab(self, group_key: str):
        index = self._find_tab_index_by_key(group_key)
        if index >= 0:
            page = self.group_tabs.widget(index)
            self.group_tabs.removeTab(index)
            if page is not None:
                page.deleteLater()
        self._group_tables.pop(group_key, None)

    def _all_group_contexts(self) -> List[Tuple[str, str, QTableWidget]]:
        contexts: List[Tuple[str, str, QTableWidget]] = []
        for row in range(self.group_table.rowCount()):
            key = self._group_key_for_row(row)
            table = self._group_tables.get(key)
            if table is None:
                continue
            item = self.group_table.item(row, self.GROUP_COL_NAME)
            name = item.text().strip() if item else ""
            contexts.append((key, name, table))
        return contexts

    def _current_group_context(self) -> Optional[Tuple[str, str, QTableWidget]]:
        page = self.group_tabs.currentWidget()
        if page is None:
            return None
        key = str(getattr(page, "_lapine_group_key", ""))
        table = self._group_tables.get(key)
        if table is None:
            return None
        return key, self._group_name_for_key(key), table

    def _on_group_cell_clicked(self, row: int, _column: int):
        key = self._group_key_for_row(row)
        index = self._find_tab_index_by_key(key)
        if index >= 0:
            self.group_tabs.setCurrentIndex(index)

    def _on_group_tab_changed(self, _index: int):
        context = self._current_group_context()
        if context is not None:
            key, _name, _table = context
            for row in range(self.group_table.rowCount()):
                if self._group_key_for_row(row) == key:
                    self.group_table.selectRow(row)
                    break
        self._update_probability_total()

    def _on_group_item_changed(self, item: QTableWidgetItem):
        if item.column() != self.GROUP_COL_NAME:
            return
        key = str(item.data(Qt.UserRole) or "")
        if not key:
            return
        name = item.text().strip()
        tab_index = self._find_tab_index_by_key(key)
        if tab_index >= 0:
            self.group_tabs.setTabText(tab_index, name or f"群組 {item.row() + 1}")
        table = self._group_tables.get(key)
        if table is not None:
            for row in range(table.rowCount()):
                group_item = table.item(row, self.COL_GROUP)
                if group_item is not None:
                    group_item.setText(name)
        self._update_probability_total()

    def _reload_code_combos_and_previews(self):
        for _key, _name, table in self._all_group_contexts():
            for row in range(table.rowCount()):
                combo = table.cellWidget(row, self.COL_CODE)
                current = (
                    self._resolve_code_input(combo.currentText(), combo)
                    if isinstance(combo, QComboBox) else ""
                )
                if isinstance(combo, QComboBox):
                    self._configure_code_combo(combo, current)
                self._update_row_preview(row, table)
        self._update_name_table_status()

    def _load_existing_profile(self):
        store = load_probability_store(self.probability_path)
        profile = store.get("tables", {}).get(self.table_key, {})
        self.title_edit.setText(str(profile.get("title") or self.default_title))
        for group in normalize_profile_groups(profile):
            self.add_group(group, create_blank=False)
        for row_data in profile.get("rows", []) or []:
            if isinstance(row_data, Mapping):
                self.add_row(dict(row_data), group_name=str(row_data.get("group") or ""))
        for _key, group_name, table in self._all_group_contexts():
            if table.rowCount() == 0:
                self.add_row({"group": group_name}, table=table, group_name=group_name)
        if self.group_tabs.count() > 0:
            self.group_tabs.setCurrentIndex(0)

    def _first_group_name(self) -> str:
        item = self.group_table.item(0, self.GROUP_COL_NAME)
        return item.text().strip() if item and item.text().strip() else "1"

    def add_group(self, data: Mapping[str, Any], create_blank: bool = True):
        row = self.group_table.rowCount()
        group_key = self._new_group_key()
        name = str(data.get("name") or data.get("group") or row + 1)
        self.group_table.blockSignals(True)
        self.group_table.insertRow(row)
        name_item = QTableWidgetItem(name)
        name_item.setData(Qt.UserRole, group_key)
        self.group_table.setItem(row, self.GROUP_COL_NAME, name_item)
        rate_spin = self._new_probability_spin(data.get("probability", 100.0))
        self.group_table.setCellWidget(row, self.GROUP_COL_RATE, rate_spin)
        self.group_table.blockSignals(False)
        rate_spin.valueChanged.connect(
            lambda value, w=rate_spin: self._on_probability_spin_changed(w, value)
        )
        table = self._create_group_tab(group_key, name)
        self.group_tabs.setCurrentIndex(self._find_tab_index_by_key(group_key))
        self.group_table.selectRow(row)
        if create_blank:
            self.add_row({"group": name}, table=table, group_name=name)
        self._update_probability_total()

    def delete_selected_groups(self):
        rows = sorted({index.row() for index in self.group_table.selectedIndexes()}, reverse=True)
        if not rows:
            context = self._current_group_context()
            if context is not None:
                key = context[0]
                rows = [
                    row for row in range(self.group_table.rowCount())
                    if self._group_key_for_row(row) == key
                ]
        for row in rows:
            key = self._group_key_for_row(row)
            self._remove_group_tab(key)
            self.group_table.removeRow(row)
        if self.group_table.rowCount() == 0:
            self.add_group({"name": "1", "probability": 100.0})
        elif self.group_tabs.count() > 0:
            self.group_tabs.setCurrentIndex(min(self.group_tabs.currentIndex(), self.group_tabs.count() - 1))
        self._update_probability_total()

    def _get_group_data(self, row: int) -> Dict[str, Any]:
        name_item = self.group_table.item(row, self.GROUP_COL_NAME)
        rate_spin = self.group_table.cellWidget(row, self.GROUP_COL_RATE)
        return {
            "name": name_item.text().strip() if name_item else "",
            "probability": self._probability_spin_value(rate_spin) if isinstance(rate_spin, QDoubleSpinBox) else 100.0,
        }

    def _new_code_combo(self, code: str = "") -> QComboBox:
        combo = _NoWheelComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.setMinimumWidth(0)
        combo.setMaximumWidth(175)
        combo.setMaxVisibleItems(24)
        combo.setToolTip(
            "可輸入 AddRandomOptionNameTable.lua 的中文效果搜尋；"
            "選取後欄位會自動轉成 EnumVAR 代碼，儲存時也只保存代碼。"
        )
        self._configure_code_combo(combo, str(code or ""))

        # PySide6 exposes the text overload as textActivated rather than
        # QComboBox.activated[str].  Using textActivated also works when the
        # user opens the drop-down and clicks a human-readable effect label.
        combo.textActivated.connect(
            lambda selected, w=combo: self._commit_code_completion(w, selected)
        )
        completer = combo.completer()
        if isinstance(completer, QCompleter):
            completer.activated[str].connect(
                lambda selected, w=combo: self._commit_code_completion(w, selected)
            )
        return combo

    @staticmethod
    def _new_value_spin(value: Any = 0) -> QSpinBox:
        spin = _NoWheelSpinBox()
        spin.setRange(-999999999, 999999999)
        try:
            spin.setValue(int(value))
        except (TypeError, ValueError):
            spin.setValue(0)
        return spin

    @staticmethod
    def _new_probability_spin(value: Any = 0.0) -> QDoubleSpinBox:
        spin = _NoWheelDoubleSpinBox()
        spin.setRange(0.0, 100.0)
        spin.setDecimals(1)
        spin.setSingleStep(0.1)
        spin.setSuffix(" %")
        try:
            exact_value = float(value)
        except (TypeError, ValueError):
            exact_value = 0.0
        spin._lapine_exact_probability = exact_value
        spin.setValue(exact_value)
        if abs(exact_value - round(exact_value, 1)) > 1e-9:
            spin.setToolTip(
                f"批次匯入原始機率：{exact_value:g}%。畫面顯示一位小數；"
                "手動修改後會改用畫面值。"
            )
        return spin

    @staticmethod
    def _probability_spin_value(spin: Any) -> float:
        if not isinstance(spin, QDoubleSpinBox):
            return 0.0
        try:
            return float(getattr(spin, "_lapine_exact_probability"))
        except (TypeError, ValueError, AttributeError):
            return float(spin.value())

    def _on_probability_spin_changed(self, spin: QDoubleSpinBox, value: float):
        spin._lapine_exact_probability = float(value)
        spin.setToolTip("")
        self._update_probability_total()

    def add_row(
        self,
        data: Mapping[str, Any],
        table: Optional[QTableWidget] = None,
        group_name: Optional[str] = None,
    ):
        if table is None and group_name:
            requested_group = str(group_name).strip()
            for _key, existing_name, existing_table in self._all_group_contexts():
                if existing_name == requested_group:
                    table = existing_table
                    group_name = existing_name
                    break
        if table is None:
            context = self._current_group_context()
            if context is None:
                self.add_group({"name": "1", "probability": 100.0})
                context = self._current_group_context()
            if context is None:
                return
            _key, current_name, table = context
            group_name = group_name or current_name
        group_name = str(group_name or data.get("group") or self._first_group_name())

        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, self.COL_GROUP, QTableWidgetItem(group_name))
        combo = self._new_code_combo(str(data.get("option_code") or ""))
        table.setCellWidget(row, self.COL_CODE, combo)
        min_spin = self._new_value_spin(data.get("min_value", 0))
        max_spin = self._new_value_spin(data.get("max_value", data.get("min_value", 0)))
        rate_spin = self._new_probability_spin(data.get("probability", 0.0))
        table.setCellWidget(row, self.COL_MIN, min_spin)
        table.setCellWidget(row, self.COL_MAX, max_spin)
        table.setCellWidget(row, self.COL_RATE, rate_spin)

        for column in (self.COL_PREVIEW, self.COL_LUA):
            preview = QTableWidgetItem()
            preview.setFlags(preview.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, column, preview)
        note = str(data.get("note") or data.get("raw_effect") or "")
        table.setItem(row, self.COL_NOTE, QTableWidgetItem(note))
        table.item(row, self.COL_NOTE).setData(Qt.UserRole, str(data.get("raw_effect") or ""))

        combo.currentTextChanged.connect(lambda _text, w=combo: self._update_row_preview_by_widget(w))
        min_spin.valueChanged.connect(lambda _value, w=min_spin: self._update_row_preview_by_widget(w))
        max_spin.valueChanged.connect(lambda _value, w=max_spin: self._update_row_preview_by_widget(w))
        rate_spin.valueChanged.connect(
            lambda value, w=rate_spin: self._on_probability_spin_changed(w, value)
        )
        self._update_row_preview(row, table)
        self._update_probability_total()

    def _row_for_widget(self, widget: QWidget) -> Tuple[Optional[QTableWidget], int]:
        for _key, _name, table in self._all_group_contexts():
            for row in range(table.rowCount()):
                for column in (self.COL_CODE, self.COL_MIN, self.COL_MAX, self.COL_RATE):
                    if table.cellWidget(row, column) is widget:
                        return table, row
        return None, -1

    def _update_row_preview_by_widget(self, widget: QWidget):
        table, row = self._row_for_widget(widget)
        if table is not None and row >= 0:
            self._update_row_preview(row, table)

    def _update_row_preview(self, row: int, table: Optional[QTableWidget] = None):
        if table is None:
            context = self._current_group_context()
            table = context[2] if context is not None else None
        if table is None or row < 0 or row >= table.rowCount():
            return
        combo = table.cellWidget(row, self.COL_CODE)
        min_spin = table.cellWidget(row, self.COL_MIN)
        max_spin = table.cellWidget(row, self.COL_MAX)
        code = (
            self._resolve_code_input(combo.currentText(), combo)
            if isinstance(combo, QComboBox) else ""
        )
        minimum = min_spin.value() if isinstance(min_spin, QSpinBox) else 0
        maximum = max_spin.value() if isinstance(max_spin, QSpinBox) else minimum
        raw_item = table.item(row, self.COL_NOTE)
        raw_effect = raw_item.data(Qt.UserRole) if raw_item else ""

        display_template = self.option_names.get(code, "")
        display_text = (
            render_option_preview(display_template, minimum, maximum)
            if display_template else str(raw_effect or code or "（未知代碼）")
        )
        display_item = table.item(row, self.COL_PREVIEW)
        display_item.setText(display_text)
        display_item.setToolTip(display_template or "此代碼不在 AddRandomOptionNameTable.lua 中")

        lua_template = self.enchant_names.get(code, "")
        lua_text = (
            render_option_preview(lua_template, minimum, maximum)
            if lua_template else "（EnchantName.lua 無對應格式）"
        )
        lua_item = table.item(row, self.COL_LUA)
        lua_item.setText(lua_text)
        lua_item.setToolTip(lua_template or "隨機後無法匯入主程式詞條")

    def _get_row_data(
        self,
        row: int,
        table: Optional[QTableWidget] = None,
        group_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if table is None:
            context = self._current_group_context()
            if context is None:
                return {}
            _key, current_name, table = context
            group_name = group_name or current_name
        note_item = table.item(row, self.COL_NOTE)
        combo = table.cellWidget(row, self.COL_CODE)
        min_spin = table.cellWidget(row, self.COL_MIN)
        max_spin = table.cellWidget(row, self.COL_MAX)
        rate_spin = table.cellWidget(row, self.COL_RATE)
        return {
            "group": str(group_name or "").strip(),
            "option_code": (
                self._resolve_code_input(combo.currentText(), combo)
                if isinstance(combo, QComboBox) else ""
            ),
            "min_value": min_spin.value() if isinstance(min_spin, QSpinBox) else 0,
            "max_value": max_spin.value() if isinstance(max_spin, QSpinBox) else 0,
            "probability": self._probability_spin_value(rate_spin) if isinstance(rate_spin, QDoubleSpinBox) else 0.0,
            "raw_effect": str(note_item.data(Qt.UserRole) or "") if note_item else "",
            "note": note_item.text().strip() if note_item else "",
        }

    def _update_probability_total(self):
        totals: Dict[str, float] = {}
        for _key, group_name, table in self._all_group_contexts():
            total = 0.0
            for row in range(table.rowCount()):
                spin = table.cellWidget(row, self.COL_RATE)
                if isinstance(spin, QDoubleSpinBox):
                    total += self._probability_spin_value(spin)
            totals[group_name or "（未命名）"] = total

        context = self._current_group_context()
        if context is None:
            self.total_rate_label.setText("尚無群組")
            return
        _key, current_name, _table = context
        current_total = totals.get(current_name or "（未命名）", 0.0)
        self.total_rate_label.setText(
            f"目前群組「{current_name or '未命名'}」組內合計：{current_total:.1f}%"
        )

    def delete_selected_rows(self):
        context = self._current_group_context()
        if context is None:
            return
        _key, group_name, table = context
        rows = sorted({index.row() for index in table.selectedIndexes()}, reverse=True)
        for row in rows:
            table.removeRow(row)
        if table.rowCount() == 0:
            self.add_row({"group": group_name}, table=table, group_name=group_name)
        self._update_probability_total()

    def duplicate_selected_rows(self):
        context = self._current_group_context()
        if context is None:
            return
        _key, group_name, table = context
        rows = sorted({index.row() for index in table.selectedIndexes()})
        for row in rows:
            self.add_row(
                self._get_row_data(row, table, group_name),
                table=table,
                group_name=group_name,
            )

    def clear_rows(self):
        context = self._current_group_context()
        if context is None:
            return
        _key, group_name, table = context
        answer = QMessageBox.question(
            self,
            "清空目前群組",
            f"確定要清除群組「{group_name or '未命名'}」的所有附魔詞條嗎？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        table.setRowCount(0)
        self.add_row({"group": group_name}, table=table, group_name=group_name)

    def save_and_accept(self):
        groups = [self._get_group_data(row) for row in range(self.group_table.rowCount())]
        group_names = [group["name"] for group in groups]
        if any(not name for name in group_names):
            QMessageBox.warning(self, "群組未完成", "群組名稱不可留空。")
            return
        if len(set(group_names)) != len(group_names):
            QMessageBox.warning(self, "群組重複", "群組名稱不可重複。")
            return

        rows: List[Dict[str, Any]] = []
        for _key, group_name, table in self._all_group_contexts():
            for row_index in range(table.rowCount()):
                row_data = self._get_row_data(row_index, table, group_name)
                if row_data.get("option_code") or row_data.get("note"):
                    rows.append(row_data)
        if not rows:
            QMessageBox.information(self, "無資料", "請至少建立一列附魔資料。")
            return

        missing_group_rows = [
            index + 1 for index, row in enumerate(rows)
            if not row.get("group") or row.get("group") not in set(group_names)
        ]
        if missing_group_rows:
            QMessageBox.warning(
                self, "群組不存在",
                "以下詞條列指定的群組不存在：" + "、".join(map(str, missing_group_rows)),
            )
            return

        empty_codes = [index + 1 for index, row in enumerate(rows) if not row.get("option_code")]
        if empty_codes:
            QMessageBox.warning(
                self, "代碼未完成",
                "以下列尚未指定 EnumVAR 代碼：" + "、".join(map(str, empty_codes)),
            )
            return

        invalid_ranges = [
            index + 1 for index, row in enumerate(rows)
            if int(row.get("min_value", 0)) > int(row.get("max_value", 0))
        ]
        if invalid_ranges:
            QMessageBox.warning(
                self, "範圍錯誤",
                "以下列的最小值大於最大值：" + "、".join(map(str, invalid_ranges)),
            )
            return

        totals: Dict[str, float] = defaultdict(float)
        for row in rows:
            totals[str(row.get("group"))] += float(row.get("probability", 0.0) or 0.0)
        overflow = [f"{name}={total:g}%" for name, total in totals.items() if total > 100.0 + 1e-9]
        if overflow:
            QMessageBox.warning(
                self, "組內機率超過 100%",
                "以下群組的組內機率合計超過 100%：" + "、".join(overflow),
            )
            return

        missing_formats = sorted({
            str(row.get("option_code")) for row in rows
            if float(row.get("probability", 0.0) or 0.0) > 0
            and str(row.get("option_code")) not in self.enchant_names
        })
        if missing_formats:
            QMessageBox.warning(
                self, "缺少主程式詞條格式",
                "以下代碼在 EnchantName.lua 中沒有對應格式，無法隨機後匯入：\n"
                + "\n".join(missing_formats),
            )
            return

        store = load_probability_store(self.probability_path)
        store.setdefault("tables", {})[self.table_key] = {
            "title": self.title_edit.text().strip() or self.default_title,
            "box_item_id": self.box_item_id,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "groups": groups,
            "rows": rows,
        }
        try:
            save_probability_store(self.probability_path, store)
        except OSError as exc:
            QMessageBox.warning(self, "儲存失敗", f"無法寫入機率檔：\n{exc}")
            return
        self.saved.emit(self.table_key)
        self.accept()


# -----------------------------------------------------------------------------
# PySide6 viewer
# -----------------------------------------------------------------------------

class LapineUpgradeUI(QWidget):
    """LapineUpgradeBox viewer with an EnchantUI-like left list/right tabs layout."""

    randomEnchantApplyRequested = Signal(str, object)

    def __init__(
        self,
        lapine_data: Mapping[str, Mapping[str, Any]],
        item_data: Mapping[Any, Mapping[str, Any]],
        initial_target_item_id: Optional[int] = None,
        initial_equipment_name: str = "",
        target_part_name: str = "",
        base_dir: Optional[str] = None,
    ):
        super().__init__()
        self.parsed = dict(lapine_data or {})
        self.items = item_data or {}
        self.target_map = build_target_item_map(self.parsed)
        self.target_part_name = str(target_part_name or "")
        self.initial_equipment_name = str(initial_equipment_name or "")
        self.current_target_item_id: Optional[int] = None
        self.target_context_item_id: Optional[int] = None
        self.base_dir = str(base_dir or get_runtime_base_dir())
        self.probability_data_path = get_probability_data_path(self.base_dir)
        self.option_name_table_path = find_random_option_name_table(self.base_dir)
        self.enchant_name_table_path = find_enchant_name_table(self.base_dir)
        try:
            self.option_names = (
                parse_random_option_name_table(self.option_name_table_path)
                if self.option_name_table_path else {}
            )
        except Exception as exc:
            print(f"⚠️ AddRandomOptionNameTable 載入失敗：{exc}")
            self.option_names = {}
        try:
            self.enchant_names = (
                parse_enchant_name_table(self.enchant_name_table_path)
                if self.enchant_name_table_path else {}
            )
        except Exception as exc:
            print(f"⚠️ EnchantName.lua 載入失敗：{exc}")
            self.enchant_names = {}

        self.setWindowTitle("Lapine Upgrade Viewer")
        root_layout = QHBoxLayout(self)

        left_layout = QVBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜尋裝備名稱、ItemID 或內部名稱...")
        self.search_box.textChanged.connect(self.refresh_item_list)
        left_layout.addWidget(self.search_box)

        self.list_items = QListWidget()
        self.list_items.currentItemChanged.connect(self._on_current_item_changed)
        left_layout.addWidget(self.list_items, 1)
        root_layout.addLayout(left_layout)

        right_layout = QVBoxLayout()
        self.target_hint_label = QLabel()
        self.target_hint_label.setWordWrap(True)
        right_layout.addWidget(self.target_hint_label)

        self.summary_label = QLabel()
        summary_font = QFont(self.summary_label.font())
        summary_font.setBold(True)
        self.summary_label.setFont(summary_font)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        right_layout.addWidget(self.summary_label)

        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self._sync_current_random_button)
        right_layout.addWidget(self.tabs, 1)
        root_layout.addLayout(right_layout, 1)

        # 最右側固定顯示隨機附魔 LOG。每次按下隨機附魔都會留下
        # 群組判定、抽中詞條、實際數值，以及是否已寫回主程式。
        self.random_attempt_count = 0
        self.random_log_panel = QGroupBox("隨機附魔 LOG")
        self.random_log_panel.setMinimumWidth(380)
        self.random_log_panel.setMaximumWidth(440)
        random_log_layout = QVBoxLayout(self.random_log_panel)

        self.random_enchant_button = QPushButton("隨機附魔")
        self.random_enchant_button.setEnabled(False)
        self.random_enchant_button.setToolTip(
            "請先選擇有機率表的 Lapine 分頁。抽選後會依群組出現率與組內機率產生附魔。"
        )
        self.random_enchant_button.clicked.connect(self._roll_current_random_enchant)
        random_log_layout.addWidget(self.random_enchant_button)

        random_log_header = QHBoxLayout()
        self.random_log_summary = QLabel("本次附魔：尚未執行")
        self.random_log_summary.setWordWrap(True)
        self.random_log_summary.setStyleSheet("font-weight: bold;")
        random_log_header.addWidget(self.random_log_summary, 1)

        self.clear_random_log_button = QPushButton("清空 LOG")
        self.clear_random_log_button.clicked.connect(self.clear_random_log)
        random_log_header.addWidget(self.clear_random_log_button)
        random_log_layout.addLayout(random_log_header)

        self.random_log_view = QPlainTextEdit()
        self.random_log_view.setReadOnly(True)
        self.random_log_view.setPlaceholderText("本次與歷次隨機附魔結果會顯示在這裡。")
        random_log_layout.addWidget(self.random_log_view, 1)
        root_layout.addWidget(self.random_log_panel)

        self._list_rows = self._build_list_rows()
        self.refresh_item_list("")
        self.set_target_context(
            self.target_part_name,
            initial_target_item_id,
            self.initial_equipment_name,
        )

    def _current_probability_context(self):
        """取得目前 Lapine 分頁所對應的機率表與結果元件。"""
        page = self.tabs.currentWidget()
        if page is None:
            return None

        box = getattr(page, "_lapine_box", None)
        result_label = getattr(page, "_lapine_result_label", None)
        if not isinstance(box, Mapping) or result_label is None:
            return None
        return page, box, result_label

    def _sync_current_random_button(self, _index: int = -1):
        """依目前分頁的機率表更新右側隨機附魔按鈕狀態。"""
        button = getattr(self, "random_enchant_button", None)
        if button is None:
            return

        context = self._current_probability_context()
        if context is None:
            button.setEnabled(False)
            button.setToolTip("目前沒有可隨機附魔的 Lapine 分頁。")
            return

        _page, box, _result_label = context
        table_key = str(box.get("key") or "")
        store = load_probability_store(self.probability_data_path)
        profile = store.get("tables", {}).get(table_key, {})
        rows = [
            row for row in (profile.get("rows", []) or [])
            if isinstance(row, Mapping)
        ]
        valid_rows = any(
            float(row.get("probability", 0.0) or 0.0) > 0
            for row in rows
        )

        source_item_id = int(box.get("item_id", 0) or 0)
        source_name = get_item_display_name(
            self.items, source_item_id, str(box.get("key") or "Lapine")
        )
        button.setEnabled(valid_rows and bool(self.enchant_names))
        if not self.enchant_names:
            button.setToolTip("找不到 EnchantName.lua，無法將結果匯入主程式詞條。")
        elif not valid_rows:
            button.setToolTip(f"{source_name} 尚未建立有效的附魔機率表。")
        else:
            button.setToolTip(
                f"對目前分頁「{source_name}」進行隨機附魔；"
                "先判定各群組是否出現，再於群組內抽選一條。"
            )

    def _roll_current_random_enchant(self, checked: bool = False):
        """由右側 LOG 上方按鈕執行目前分頁的隨機附魔。"""
        context = self._current_probability_context()
        if context is None:
            QMessageBox.information(self, "無法隨機附魔", "目前沒有可用的 Lapine 分頁。")
            return
        _page, box, result_label = context
        self._roll_random_enchant(box, result_label)

    def clear_random_log(self, checked: bool = False):
        """清除右側隨機附魔紀錄。"""
        self.random_attempt_count = 0
        self.random_log_view.clear()
        self.random_log_summary.setText("本次附魔：尚未執行")

    def _append_random_log(self, title: str, lines: Iterable[str]):
        """新增一筆可複製的附魔紀錄，並更新本次結果摘要。"""
        self.random_attempt_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        header = f"===== 第 {self.random_attempt_count} 次｜{timestamp}｜{title} ====="
        body_lines = [str(line) for line in lines if str(line).strip()]
        block = "\n".join([header, *body_lines])
        if self.random_log_view.toPlainText().strip():
            self.random_log_view.appendPlainText("")
        self.random_log_view.appendPlainText(block)
        self.random_log_summary.setText(
            f"本次附魔：第 {self.random_attempt_count} 次｜{title}"
        )
        scroll_bar = self.random_log_view.verticalScrollBar()
        QTimer.singleShot(0, lambda bar=scroll_bar: bar.setValue(bar.maximum()))

    def _log_random_outcome(
        self,
        box: Mapping[str, Any],
        outcome: Mapping[str, Any],
        apply_note: str = "",
    ):
        """把一次群組隨機附魔的完整結果寫到最右側 LOG。"""
        results = list(outcome.get("results", []) or [])
        attempts = list(outcome.get("attempts", []) or [])
        source_item_id = int(box.get("item_id", 0) or 0)
        source_name = get_item_display_name(
            self.items, source_item_id, str(box.get("key") or "Lapine")
        )

        lines = [
            f"附魔資料：{source_name} [{source_item_id}]",
            #f"資料鍵值：{str(box.get('key') or '')}",
        ]
        if self.target_part_name:
            lines.append(f"主程式部位：{self.target_part_name}")
        if self.initial_equipment_name:
            lines.append(f"目標裝備：{self.initial_equipment_name}")

        for attempt in attempts:
            group_name = str(attempt.get("group") or "")
            group_rate = float(attempt.get("group_probability", 0.0) or 0.0)
            group_roll = attempt.get("group_roll")
            group_roll_text = (
                "—" if group_roll is None else f"{float(group_roll):.4f}"
            )
            if attempt.get("success"):
                row = attempt.get("row") or {}
                lines.append(
                    f"[成功] 群組 {group_name}：{attempt.get('display_text')} "
                    #f"[{attempt.get('option_code')}]"
                )
                # lines.append(
                #     f"  群組 {group_roll_text}/{group_rate:g}%｜"
                #     f"組內 {float(attempt.get('option_roll', 0.0)):.4f}/"
                #     f"{float(row.get('probability', 0.0) or 0.0):g}%｜"
                #     f"值 {attempt.get('value')}"
                # )
                # lua_effect = str(attempt.get("lua_effect") or "").strip()
                # if lua_effect:
                #     lines.append(f"  寫入格式：{lua_effect}")
            # else:
            #     lines.append(
            #         f"[未附上] 群組 {group_name}：{attempt.get('reason')} "
            #         f"（群組 {group_roll_text}/{group_rate:g}%）"
            #     )

        if apply_note:
            lines.append(f"套用狀態：{apply_note}")
        self._append_random_log(
            "成功" if results else "沒有產生附魔",
            lines,
        )

    def _build_list_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for target_item_id, boxes in self.target_map.items():
            fallback = ""
            internal_names: List[str] = []
            for box in boxes:
                matched = box.get("matched_target", {})
                internal = str(matched.get("internal_name") or "")
                if internal and internal not in internal_names:
                    internal_names.append(internal)
                if not fallback:
                    fallback = internal

            display_name = get_item_display_name(self.items, target_item_id, fallback)
            rows.append(
                {
                    "item_id": int(target_item_id),
                    "display_name": display_name,
                    "internal_names": internal_names,
                    "search_text": " ".join(
                        [display_name, str(target_item_id), *internal_names]
                    ).casefold(),
                }
            )

        rows.sort(key=lambda row: (row["display_name"].casefold(), row["item_id"]))
        return rows

    def refresh_item_list(self, keyword: str = ""):
        keyword = str(keyword or "").strip().casefold()
        selected_id = self.current_target_item_id

        self.list_items.blockSignals(True)
        self.list_items.clear()
        selected_item: Optional[QListWidgetItem] = None

        for row in self._list_rows:
            if keyword and keyword not in row["search_text"]:
                continue
            item = QListWidgetItem(f'{row["display_name"]}  [{row["item_id"]}]')
            item.setData(Qt.UserRole, row["item_id"])
            item.setToolTip("\n".join(row["internal_names"]))
            self.list_items.addItem(item)
            if selected_id == row["item_id"]:
                selected_item = item

        self.list_items.blockSignals(False)

        if selected_item is not None:
            self.list_items.setCurrentItem(selected_item)
        elif self.list_items.count() > 0:
            self.list_items.setCurrentRow(0)
        else:
            self._show_target(None)

    def set_target_context(
        self,
        part_name: str = "",
        target_item_id: Optional[int] = None,
        equipment_name: str = "",
    ):
        self.target_part_name = str(part_name or "")
        self.initial_equipment_name = str(equipment_name or "")
        self.target_context_item_id = _coerce_item_id(target_item_id)

        if self.target_part_name:
            equipment_text = (
                f"；目前裝備：{self.initial_equipment_name}"
                if self.initial_equipment_name else ""
            )
            self.target_hint_label.setText(
                f"主畫面目標：{self.target_part_name}{equipment_text}。"
                "下方分頁列出可作用於此裝備的 Lapine 附魔箱／材料。"
            )
        else:
            self.target_hint_label.setText(
                "未鎖定主畫面部位；左側可瀏覽所有 LapineUpgradeBox 目標裝備。"
            )

        if target_item_id is not None:
            if not self.select_target_by_id(target_item_id):
                self.list_items.setCurrentRow(-1)
                self._show_target(None)
        elif self.target_part_name:
            self.list_items.setCurrentRow(-1)
            self._show_target(None)

    def select_target_by_id(self, target_item_id: Any) -> bool:
        item_id = _coerce_item_id(target_item_id)
        if item_id is None:
            return False

        for row in range(self.list_items.count()):
            item = self.list_items.item(row)
            if _coerce_item_id(item.data(Qt.UserRole)) == item_id:
                self.list_items.setCurrentItem(item)
                self.list_items.scrollToItem(item)
                return True

        # The current search may hide it; clear the filter and retry once.
        if self.search_box.text():
            self.search_box.clear()
            for row in range(self.list_items.count()):
                item = self.list_items.item(row)
                if _coerce_item_id(item.data(Qt.UserRole)) == item_id:
                    self.list_items.setCurrentItem(item)
                    self.list_items.scrollToItem(item)
                    return True
        return False

    def _on_current_item_changed(
        self,
        current: Optional[QListWidgetItem],
        _previous: Optional[QListWidgetItem],
    ):
        target_item_id = current.data(Qt.UserRole) if current else None
        self._show_target(_coerce_item_id(target_item_id))

    def _show_target(self, target_item_id: Optional[int]):
        self.tabs.clear()
        self.current_target_item_id = target_item_id

        if target_item_id is None or target_item_id not in self.target_map:
            self.summary_label.setText("沒有符合的 LapineUpgradeBox 資料。")
            return

        boxes = self.target_map[target_item_id]
        target_name = get_item_display_name(self.items, target_item_id)
        self.summary_label.setText(
            f"目標裝備：{target_name}  [ItemID: {target_item_id}]｜可用資料：{len(boxes)} 組"
        )

        for box in boxes:
            self.tabs.addTab(
                self._create_box_tab(target_item_id, box),
                self._box_tab_title(box),
            )
        self._sync_current_random_button()

    def _box_tab_title(self, box: Mapping[str, Any]) -> str:
        source_item_id = int(box.get("item_id", 0) or 0)
        source_name = get_item_display_name(
            self.items, source_item_id, str(box.get("key") or "Lapine")
        )
        return f"{source_name} [{source_item_id}]"

    def _create_box_tab(self, selected_target_id: int, box: Mapping[str, Any]) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        source_item_id = int(box.get("item_id", 0) or 0)
        source_name = get_item_display_name(
            self.items, source_item_id, str(box.get("key") or "")
        )

        info_group = QGroupBox("Lapine 附魔資料")
        form = QFormLayout(info_group)
        form.addRow("資料鍵值", self._selectable_label(str(box.get("key") or "")))
        form.addRow(
            "附魔箱／材料",
            self._selectable_label(f"{source_name}  [ItemID: {source_item_id}]")
        )
        form.addRow(
            "精煉需求",
            self._selectable_label(
                f'+{int(box.get("need_refine_min", 0))} ～ '
                f'+{int(box.get("need_refine_max", 20))}'
            ),
        )
        form.addRow(
            "最低隨機詞條數",
            self._selectable_label(str(int(box.get("need_option_num_min", 0)))),
        )
        form.addRow(
            "禁止洞附魔物品",
            self._selectable_label(
                "是" if bool(box.get("not_socket_enchant_item")) else "否"
            ),
        )
        form.addRow(
            "來源說明",
            self._selectable_label(str(box.get("need_source_string") or "（無）")),
        )
        #layout.addWidget(info_group)
        layout.addWidget(self._create_probability_group(box, page))

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["ItemID", "物品名稱", "內部名稱"])
        targets = list(box.get("target_items", []) or [])
        table.setRowCount(len(targets))
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)

        for row, target in enumerate(targets):
            target_item_id = int(target.get("item_id", 0) or 0)
            internal_name = str(target.get("internal_name") or "")
            display_name = get_item_display_name(
                self.items, target_item_id, internal_name
            )
            values = (str(target_item_id), display_name, internal_name)
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if target_item_id == selected_target_id:
                    font = QFont(cell.font())
                    font.setBold(True)
                    cell.setFont(font)
                table.setItem(row, column, cell)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        #layout.addWidget(table, 1)
        return page


    def _create_probability_group(
        self,
        box: Mapping[str, Any],
        owner_page: Optional[QWidget] = None,
    ) -> QGroupBox:
        group = QGroupBox("自訂附魔機率")
        layout = QVBoxLayout(group)
        button_row = QHBoxLayout()
        status_label = QLabel()
        status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        edit_button = QPushButton("建立／編輯機率表")
        reload_button = QPushButton("重新載入")
        button_row.addWidget(status_label, 1)
        button_row.addWidget(edit_button)
        button_row.addWidget(reload_button)
        layout.addLayout(button_row)

        result_label = QLabel("尚未進行隨機附魔。")
        result_label.setWordWrap(True)
        result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        result_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(result_label)

        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels([
            "群組", "群組出現率", "附魔名稱", "組內機率"
        ])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.setMinimumHeight(150)
        layout.addWidget(table)

        if owner_page is not None:
            owner_page._lapine_box = box
            owner_page._lapine_result_label = result_label
            owner_page._lapine_probability_table = table
            owner_page._lapine_probability_status_label = status_label

        edit_button.clicked.connect(
            lambda: self._open_probability_editor(box, table, status_label, None)
        )
        reload_button.clicked.connect(
            lambda: (
                self._refresh_probability_table(box, table, status_label, None),
                self._sync_current_random_button(),
            )
        )
        self._refresh_probability_table(box, table, status_label, None)
        return group

    def _refresh_probability_table(
        self,
        box: Mapping[str, Any],
        table: QTableWidget,
        status_label: QLabel,
        random_button: Optional[QPushButton] = None,
    ):
        table_key = str(box.get("key") or "")
        store = load_probability_store(self.probability_data_path)
        profile = store.get("tables", {}).get(table_key, {})
        rows = [row for row in (profile.get("rows", []) or []) if isinstance(row, Mapping)]
        groups = normalize_profile_groups(profile)
        group_probability = {
            str(group.get("name") or ""): float(group.get("probability", 100.0) or 0.0)
            for group in groups
        }

        table.setRowCount(len(rows))
        per_group_total: Dict[str, float] = defaultdict(float)
        missing_format_count = 0
        for row_index, row_data in enumerate(rows):
            try:
                minimum = int(row_data.get("min_value", 0))
                maximum = int(row_data.get("max_value", minimum))
            except (TypeError, ValueError):
                minimum = maximum = 0
            try:
                probability = float(row_data.get("probability", 0.0))
            except (TypeError, ValueError):
                probability = 0.0
            group_name = str(row_data.get("group") or "1").strip() or "1"
            per_group_total[group_name] += probability
            code = str(row_data.get("option_code") or "")
            if probability > 0 and code not in self.enchant_names:
                missing_format_count += 1
            values = (
                group_name,
                f"{format_probability_display(group_probability.get(group_name, 100.0))}%",
                preview_probability_row(row_data, self.option_names),
                f"{format_probability_display(probability)}%",
            )
            for column, value in enumerate(values):
                table.setItem(row_index, column, QTableWidgetItem(value))

        if rows:
            title = str(profile.get("title") or table_key)
            group_text = "；".join(
                f"{group.get('name')} 出現 {format_probability_display(group.get('probability', 100.0))}%/組內 {format_probability_display(per_group_total.get(str(group.get('name')), 0.0))}%"
                for group in groups
            )
            extra = f"｜EnchantName 缺少 {missing_format_count} 列" if missing_format_count else ""
            status_label.setText(
                f"{title}｜{len(groups)} 組／{len(rows)} 列｜{group_text}{extra}"
            )
        else:
            status_label.setText("尚未建立機率表。")

        if random_button is not None:
            valid_rows = any(
                float(row.get("probability", 0.0) or 0.0) > 0
                for row in rows
            )
            random_button.setEnabled(valid_rows and bool(self.enchant_names))
            if not self.enchant_names:
                random_button.setToolTip("找不到 EnchantName.lua，無法將結果匯入主程式詞條。")

    def _roll_random_enchant(
        self,
        box: Mapping[str, Any],
        result_label: QLabel,
    ):
        table_key = str(box.get("key") or "")
        store = load_probability_store(self.probability_data_path)
        profile = store.get("tables", {}).get(table_key, {})
        try:
            outcome = roll_grouped_probability_options(
                profile, self.option_names, self.enchant_names
            )
        except ValueError as exc:
            message = str(exc)
            self._append_random_log(
                "失敗",
                [
                    f"資料鍵值：{table_key}",
                    f"原因：{message}",
                ],
            )
            QMessageBox.warning(self, "無法隨機附魔", message)
            return

        results = list(outcome.get("results", []) or [])
        attempts = list(outcome.get("attempts", []) or [])
        if not results:
            detail = "；".join(
                f"群組 {attempt.get('group')}：{attempt.get('reason')}"
                for attempt in attempts
            )
            result_label.setText(f"隨機結果：沒有產生任何附魔。{detail}")
            self._log_random_outcome(box, outcome, "未寫入主程式")
            return

        can_apply = bool(
            self.target_part_name
            and self.target_context_item_id is not None
            and self.current_target_item_id == self.target_context_item_id
        )
        if can_apply:
            # 只傳送本次抽中的詞條函式本體；主程式不建立任何舊版包裝。
            self.randomEnchantApplyRequested.emit(self.target_part_name, results)
            apply_note = f"已套用至「{self.target_part_name}」詞條"
        elif self.target_part_name:
            apply_note = "目前瀏覽的裝備不是主畫面鎖定裝備，只顯示結果"
        else:
            apply_note = "尚未鎖定主畫面部位，只顯示結果"

        result_parts = []
        for result in results:
            row = result.get("row") or {}
            result_parts.append(
                f"群組 {result.get('group')}：{result.get('display_text')}"
                f"［{result.get('option_code')}］"
                f"（群組 Roll {float(result.get('group_roll', 0.0)):.4f} / "
                f"組內 Roll {float(result.get('option_roll', 0.0)):.4f} / "
                f"該列 {float(row.get('probability', 0.0) or 0.0):g}%）"
            )
        missed_groups = [
            f"群組 {attempt.get('group')}：{attempt.get('reason')}"
            for attempt in attempts if not attempt.get("success")
        ]
        missed_note = "；未產生：" + "、".join(missed_groups) if missed_groups else ""
        result_label.setText(
            "隨機結果：" + "｜".join(result_parts) + missed_note + "；" + apply_note
        )
        self._log_random_outcome(box, outcome, apply_note)

    def _open_probability_editor(
        self,
        box: Mapping[str, Any],
        table: QTableWidget,
        status_label: QLabel,
        random_button: Optional[QPushButton] = None,
    ):
        if not self.option_names:
            filename = self.option_name_table_path
            if not filename:
                filename, _ = QFileDialog.getOpenFileName(
                    self,
                    "選擇 AddRandomOptionNameTable.lua",
                    self.base_dir,
                    "Lua files (*.lua *.lub);;All files (*)",
                )
            if filename:
                try:
                    self.option_names = parse_random_option_name_table(filename)
                    self.option_name_table_path = filename
                except Exception as exc:
                    QMessageBox.warning(self, "顯示名稱表載入失敗", str(exc))

        if not self.enchant_names:
            filename = self.enchant_name_table_path
            if not filename:
                filename, _ = QFileDialog.getOpenFileName(
                    self,
                    "選擇 EnchantName.lua",
                    self.base_dir,
                    "Lua files (*.lua *.lub);;All files (*)",
                )
            if filename:
                try:
                    self.enchant_names = parse_enchant_name_table(filename)
                    self.enchant_name_table_path = filename
                except Exception as exc:
                    QMessageBox.warning(self, "EnchantName 載入失敗", str(exc))

        source_item_id = int(box.get("item_id", 0) or 0)
        source_name = get_item_display_name(
            self.items, source_item_id, str(box.get("key") or "Lapine")
        )
        editor = LapineProbabilityEditor(
            self.probability_data_path,
            str(box.get("key") or ""),
            self.option_names,
            self.enchant_names,
            parent=self,
            box_item_id=source_item_id,
            default_title=source_name,
        )
        editor.saved.connect(
            lambda _key: (
                self._refresh_probability_table(box, table, status_label, None),
                self._sync_current_random_button(),
            )
        )
        if editor.exec() == QDialog.DialogCode.Accepted:
            self.option_names = dict(editor.option_names)
            self.enchant_names = dict(editor.enchant_names)
            self._refresh_probability_table(box, table, status_label, None)
            self._sync_current_random_button()


    @staticmethod
    def _selectable_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Parse lapineupgradebox.lub")
    parser.add_argument("path")
    args = parser.parse_args()

    data = parse_lapine_upgrade_box(args.path)
    target_map = build_target_item_map(data)
    print(f"Lapine boxes: {len(data)}")
    print(f"Target item IDs: {len(target_map)}")
    print(f"Target references: {sum(len(v) for v in target_map.values())}")
