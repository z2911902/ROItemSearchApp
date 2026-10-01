import sys
import math
from dataclasses import dataclass
from PySide6.QtCore import (
    Qt, QAbstractListModel, QModelIndex, QPersistentModelIndex, QSize, QPointF
)
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF, QFont, QFontMetrics, QImage
from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSpinBox,
    QListView, QTextEdit, QPushButton, QFrame, QStyledItemDelegate, QComboBox,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QGraphicsView, QGraphicsScene, QFileDialog
)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QStyledItemDelegate, QStyle, QComboBox
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter
initial_steps = [
    ("MATK%", 100),
    ("體型%", 100),
    ("屬性敵人%", 100),
    ("屬性魔法%", 100),
    ("種族%", 100),
    ("階級%", 100),
    ("SMATK", 100),
    ("技能倍率%", 200),
    ("MDEF減算", 25),
    ("魔力中毒", 50),
    ("技能增傷%(技能段)", 200),
    ("打擊虛數", 0.1),
    ("總傷害", 10),
]
NO_PLUS_ONE = {
    "技能倍率%",
    "打擊虛數",    
    "總傷害",
    "屬性倍率%",
    "綠光減傷%",
    "星座塔減傷%",    
}
VALUE_100 = {
    "特殊物理增傷",
}
RAW = {
    "MRES減傷%",
    "RES減傷%",
    "MDEF減傷%",
    "DEF減傷%",
    "紋章",
    "屬性耐受性%",
    "混傷BUFF",
}
ROUNDING_OPTIONS = ["INT", "ROUND", "CEIL", "FLOOR", "NONE"]


def apply_round(value: float, factor: float, mode: str, name: str) -> float:
    # 直接加減（特殊）
    if name in ("MDEF減算","DEF減算"):
        return value - factor
    if name in ("ATK%","前ATK","神威ATK","武器修煉ATK","砲彈ATK","靈氣劍"):
        return value + factor
    # 判斷要不要 +1

    if name in NO_PLUS_ONE:
        result = value * (factor/100)
    elif name in RAW:
        result = value * factor
    elif name in VALUE_100:
        result = value * factor
    else:
        result = value * (100 + factor) /100

    if mode == "INT":
        return int(result)
    if mode == "ROUND":
        return round(result)
    if mode == "CEIL":
        return math.ceil(result)
    if mode == "FLOOR":
        return math.floor(result)
    return result


def fmt(num):
    # 如果你確定都是整數
    return f"{int(num):,}"

    # 如果之後可能有小數，改用這行：
    # return f"{num:,.2f}"

@dataclass
class Step:
    name: str
    factor: float
    mode: str = "INT"
    result: float = 0.0


class StepModel(QAbstractListModel):
    def __init__(self, steps: list[Step]):
        super().__init__()
        self.steps = steps

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self.steps)

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return None
        s = self.steps[index.row()]

        if role in (Qt.DisplayRole,):
            # 列表顯示內容（你想怎麼排版都可以在 delegate 裡畫）
            return (s.name, s.factor, s.mode, s.result)

        if role == Qt.UserRole:
            return s
        if role == Qt.ToolTipRole:
            return getattr(s, "debug_tip", "") or None

        return None

    def setData(self, index: QModelIndex, value, role: int) -> bool:
        if not index.isValid():
            return False
        if role == Qt.EditRole:
            # 只允許改 mode
            if value in ROUNDING_OPTIONS:
                self.steps[index.row()].mode = value
                self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
                return True
        return False

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemIsDropEnabled
        return (
            Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsEditable
            | Qt.ItemIsDragEnabled
            | Qt.ItemIsDropEnabled
        )

    # ---- 讓 Qt 用「移動列」而不是刪/插（動畫更穩） ----
    def supportedDropActions(self):
        return Qt.MoveAction

    def supportedDragActions(self):
        return Qt.MoveAction

    def moveRows(
        self,
        sourceParent: QModelIndex,
        sourceRow: int,
        count: int,
        destinationParent: QModelIndex,
        destinationChild: int,
    ) -> bool:
        if count != 1:
            return False
        if sourceRow < 0 or sourceRow >= len(self.steps):
            return False
        if destinationChild < 0 or destinationChild > len(self.steps):
            return False

        # Qt 的 moveRows 規則：destinationChild 是「移動後插入的位置」
        if destinationChild == sourceRow or destinationChild == sourceRow + 1:
            return False

        self.beginMoveRows(sourceParent, sourceRow, sourceRow, destinationParent, destinationChild)

        step = self.steps.pop(sourceRow)
        # 如果往下移，pop 後 index 會少一個
        if destinationChild > sourceRow:
            destinationChild -= 1
        self.steps.insert(destinationChild, step)

        self.endMoveRows()
        return True

    # 計算後更新 result（只更新資料，不重建 UI）
    def set_results(self, results: list[float]):
        if len(results) != len(self.steps):
            return
        for i, r in enumerate(results):
            self.steps[i].result = r
        if self.steps:
            top = self.index(0, 0)
            bottom = self.index(len(self.steps) - 1, 0)
            self.dataChanged.emit(top, bottom, [Qt.DisplayRole])



REL_NAME_RATIO = 0.46
REL_OP_RATIO = 0.27
REL_RESULT_RATIO = 0.27


class RelationTreeWidget(QTreeWidget):
    """讓上方驗算樹與下方傷害列表使用同一組三欄位置。"""
    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = max(1, self.viewport().width())
        self.setColumnWidth(0, int(w * REL_NAME_RATIO))
        self.setColumnWidth(1, int(w * REL_OP_RATIO))
        self.setColumnWidth(2, max(80, w - self.columnWidth(0) - self.columnWidth(1)))


class StepDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        painter.save()

        name, factor, mode, result = index.data(Qt.DisplayRole)

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        r = option.rect
        left_pad = 10
        right_pad = 10
        total_w = max(1, r.width())
        name_w = int(total_w * REL_NAME_RATIO)
        op_w = int(total_w * REL_OP_RATIO)

        name_rect = r.adjusted(left_pad, 0, 0, 0)
        name_rect.setWidth(max(60, name_w - left_pad))

        factor_rect = r.adjusted(name_w, 0, 0, 0)
        factor_rect.setWidth(max(60, op_w))

        # mode 與運算符號放同一欄，避免上下區塊欄位錯位。
        mode_rect = factor_rect

        result_rect = r.adjusted(name_w + op_w, 0, -right_pad, 0)

        pen = option.palette.highlightedText().color() if (option.state & QStyle.State_Selected) else option.palette.text().color()
        painter.setPen(pen)

        painter.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft, str(name))
        if name in ("MDEF減算","DEF減算"):
            ftxt = f"- {factor}" 
        elif name in ("ATK%","前ATK","神威ATK","武器修煉ATK","砲彈ATK","靈氣劍"):
            ftxt = f"+ {factor}"
        elif name in (NO_PLUS_ONE):
            ftxt = f"× {round(factor,2)}%"
        elif name in (VALUE_100):
            ftxt = f"× {round(factor*100,2)}%"
        elif name in (RAW):
            ftxt = f"× {round(factor*100,2)}%"
        else:
            ftxt = f"× {round(100+factor,2)}%"
        op_text = f"{ftxt}  [{mode}]"
        painter.drawText(factor_rect, Qt.AlignVCenter | Qt.AlignLeft, op_text)
        painter.drawText(
            result_rect,
            Qt.AlignVCenter | Qt.AlignRight,
            f" {fmt(result)}"
        )

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(10, 30)

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItems(["INT", "ROUND", "CEIL", "FLOOR", "NONE"])
        return cb

    def setEditorData(self, editor, index):
        _, _, mode, _ = index.data(Qt.DisplayRole)
        editor.setCurrentText(mode)

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        r = option.rect
        total_w = max(1, r.width())
        x = r.left() + int(total_w * REL_NAME_RATIO)
        w = max(90, int(total_w * REL_OP_RATIO) - 8)
        editor.setGeometry(x, r.top() + 4, w, r.height() - 8)

class LiveReorderListView(QListView):
    """拖曳時即時 moveRows，讓其他列自動讓位（像手機排序）"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._drag_row = None
        self._last_target = None
        self._throttle = QTimer(self)
        self._throttle.setSingleShot(True)
        self._throttle.setInterval(10)  # 降低抖動/太頻繁移動

    def startDrag(self, supportedActions):
        idx = self.currentIndex()
        self._drag_row = idx.row() if idx.isValid() else None
        self._last_target = None
        super().startDrag(supportedActions)
        self._drag_row = None
        self._last_target = None

    def dragMoveEvent(self, event):
        super().dragMoveEvent(event)

        if self._drag_row is None:
            return
        if self._throttle.isActive():
            return

        pos = event.position().toPoint()
        idx = self.indexAt(pos)

        # 滑到空白就當作最後
        if not idx.isValid():
            target = self.model().rowCount() - 1
        else:
            target = idx.row()

            # 更自然：看滑到 item 的上半/下半，決定插前或插後
            rect = self.visualRect(idx)
            threshold = rect.top() + rect.height() * 0.5
            if pos.y() > threshold:
                target += 1

        # 邊界修正
        rc = self.model().rowCount()
        target = max(0, min(target, rc))

        # 避免重複 move 造成抖動
        if target == self._drag_row or target == self._drag_row + 1:
            return
        if target == self._last_target:
            return

        self._last_target = target
        self._throttle.start()

        # 立刻搬資料列：這一步會觸發 view 動畫（如果 animated 開著）
        self.model().moveRows(QModelIndex(), self._drag_row, 1, QModelIndex(), target)

        # moveRows 後，拖曳中的 item row 會改變：更新追蹤位置
        if target > self._drag_row:
            self._drag_row = target - 1
        else:
            self._drag_row = target



# =============================================================================
# Core 起始 ATK / MATK 獨立驗算器
# =============================================================================
# 本區公式刻意獨立寫在 Damage_view.py，不能呼叫 ro_core 的計算 helper。
# ro_core 只提供 raw inputs；Core 最終值僅用來 compare。

DEBUG_DEX_WEAPON_CLASSES = {11, 13, 14, 17, 18, 19, 20, 21}
DEBUG_SIZE_PENALTY = {
    0: [100, 100, 100], 1: [100, 75, 50], 2: [75, 100, 75],
    3: [75, 75, 100], 4: [75, 75, 100], 5: [75, 75, 100],
    6: [50, 75, 100], 7: [50, 75, 100], 8: [75, 100, 100],
    10: [100, 100, 100], 11: [100, 100, 75], 12: [100, 100, 75],
    13: [75, 100, 75], 14: [75, 100, 75], 15: [100, 100, 50],
    16: [75, 100, 75], 17: [100, 100, 100], 18: [100, 100, 100],
    19: [100, 100, 100], 20: [100, 100, 100], 21: [100, 100, 100],
    22: [75, 75, 100], 23: [100, 100, 100],
}
DEBUG_RACE_NAMES = ["無形", "不死", "動物", "植物", "昆蟲", "魚貝", "惡魔", "人形", "天使", "龍族"]
DEBUG_CLASS_DEF_NAMES = ["一般", "首領", "玩家"]

# 物理特殊武器段只需要火 / 毒對目標屬性的倍率；仍在這裡獨立保存資料表，
# 不呼叫 ro_core.stage17_get_damage_multiplier()。
DEBUG_DAMAGE_TABLES = {
    1: {
        3: [100, 90, 150, 25, 100, 150, 100, 100, 100, 125],
        5: [100, 150, 150, 150, 150, 0, 75, 75, 75, 75],
    },
    2: {
        3: [100, 80, 175, 0, 100, 150, 100, 100, 100, 150],
        5: [100, 150, 150, 150, 150, 0, 75, 75, 75, 50],
    },
    3: {
        3: [100, 70, 200, 0, 100, 125, 100, 100, 100, 175],
        5: [100, 125, 125, 125, 125, 0, 50, 50, 50, 25],
    },
    4: {
        3: [100, 60, 200, 0, 100, 125, 100, 100, 100, 200],
        5: [100, 125, 125, 125, 125, 0, 50, 50, 50, 0],
    },
}


def _dnum(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _dint(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _fmt_debug(value):
    if value is None or value == "":
        return ""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(f - round(f)) < 1e-9:
        return f"{int(round(f)):,}"
    return f"{f:,.4f}".rstrip("0").rstrip(".")


def _effect_sum(effect_dict, name, unit=""):
    total = 0.0
    for value, _source in (effect_dict or {}).get((str(name), str(unit)), []) or []:
        if isinstance(value, (int, float)):
            total += float(value)
    return total


def _effect_entries(effect_dict, name, unit=""):
    """回傳 raw effect_dict 內的逐筆來源；只取原始值，不使用 Core 加總結果。"""
    rows = []
    for entry in (effect_dict or {}).get((str(name), str(unit)), []) or []:
        try:
            value, source = entry
        except (TypeError, ValueError):
            continue
        if isinstance(value, (int, float)):
            rows.append((float(value), str(source or "未標示來源")))
    return rows


def _debug_refine(level, refine, grade, *, magic=False):
    """Damage_view 自己的精煉公式；禁止呼叫 ro_core helper。"""
    level = _dint(level)
    refine = _dint(refine)
    grade = _dint(grade)
    if level == 0 or refine <= 0:
        return 0.0, 0.0, 0.0, 0.0

    base_per_refine = {1: 2, 2: 3, 3: 5, 4: 7, 5: 0}
    extra_after_safe = {1: 3, 2: 5, 3: 8, 4: 14, 5: 0}
    over16_bonus = {1: 3, 2: 5, 3: 7, 4: 10, 5: 0}
    safe_threshold = {1: 7, 2: 6, 3: 5, 4: 4, 5: 0 if magic else 4}
    grade_bonus = {0: 8.0, 1: 8.8, 2: 10.4, 3: 12.0, 4: 16.0}

    if level < 5:
        if level not in base_per_refine:
            return 0.0, 0.0, 0.0, 0.0
        base = refine * base_per_refine[level]
        safe = safe_threshold[level]
        variance = max(0, refine - safe) * extra_after_safe[level]
        variance_min = 1
        if refine > 15:
            base = refine * over16_bonus[level]
        return base + variance, 0.0, variance, variance_min

    per_refine = grade_bonus.get(grade, 0.0)
    return refine * per_refine, refine * 2, 0.0, 0.0


def _debug_size_penalty(weapon_class, target_size):
    values = DEBUG_SIZE_PENALTY.get(_dint(weapon_class), [100, 100, 100])
    idx = max(0, min(2, _dint(target_size, 1)))
    return values[idx] / 100.0


def _debug_element_multiplier(attacker_element, target_element, target_element_lv):
    lv = max(1, min(4, _dint(target_element_lv, 1)))
    attacker = _dint(attacker_element)
    target = max(0, min(9, _dint(target_element)))
    return DEBUG_DAMAGE_TABLES.get(lv, {}).get(attacker, [100] * 10)[target]


def _debug_def_reduction(effect_dict, target_race, target_class):
    race = _dint(target_race)
    cls = _dint(target_class)
    total = 0.0
    if 0 <= race < len(DEBUG_RACE_NAMES):
        total += _effect_sum(effect_dict, f"無視 {DEBUG_RACE_NAMES[race]} 型怪的物理防禦", "%")
    total += _effect_sum(effect_dict, "無視 全種族 型怪的物理防禦", "%")
    if 0 <= cls < len(DEBUG_CLASS_DEF_NAMES):
        total += _effect_sum(effect_dict, f"無視 {DEBUG_CLASS_DEF_NAMES[cls]} 階級的物理防禦", "%")
    return total


def _load_core_debug_raw():
    """只向 ro_core 取 raw inputs + final compare answer。"""
    try:
        import ro_core
        getter = getattr(ro_core, "get_last_damage_debug_raw", None)
        return getter() if callable(getter) else None
    except Exception:
        return None


def _row(label, delta="", result="", tip="", children=None, compare=None):
    return {
        "label": label,
        "delta": delta,
        "result": result,
        "tip": tip,
        "children": children or [],
        "compare": compare,
    }


def _independent_physical_front_atk(snapshot):
    """用 Core raw inputs 獨立重算物理前 ATK；不讀 Core 中間結果。"""
    if not isinstance(snapshot, dict):
        return 0, [], ""
    raw = snapshot.get("raw", {}) or {}
    stats = raw.get("stats", {}) or {}
    target = raw.get("target", {}) or {}
    used = raw.get("used_skills", {}) or {}

    base_lv = _dnum(raw.get("base_lv", 0))
    weapon_class = _dint(raw.get("weapon_class", 0))
    total_str = _dnum(stats.get("STR", 0))
    total_dex = _dnum(stats.get("DEX", 0))
    total_luk = _dnum(stats.get("LUK", 0))
    total_pow = _dnum(stats.get("POW", 0))

    dex_weapon = weapon_class in DEBUG_DEX_WEAPON_CLASSES
    parts = []
    if dex_weapon:
        terms = [
            ("BaseLv / 4", base_lv / 4, f"BaseLv={_fmt_debug(base_lv)}"),
            ("STR / 5", total_str / 5, f"STR={_fmt_debug(total_str)}"),
            ("DEX", total_dex, f"DEX={_fmt_debug(total_dex)}"),
            ("LUK / 3", total_luk / 3, f"LUK={_fmt_debug(total_luk)}"),
            ("POW × 5", total_pow * 5, f"POW={_fmt_debug(total_pow)}"),
        ]
        base_formula = "int(BaseLv/4 + STR/5 + DEX + LUK/3 + POW×5)"
    else:
        terms = [
            ("BaseLv / 4", base_lv / 4, f"BaseLv={_fmt_debug(base_lv)}"),
            ("STR", total_str, f"STR={_fmt_debug(total_str)}"),
            ("DEX / 5", total_dex / 5, f"DEX={_fmt_debug(total_dex)}"),
            ("LUK / 3", total_luk / 3, f"LUK={_fmt_debug(total_luk)}"),
            ("POW × 5", total_pow * 5, f"POW={_fmt_debug(total_pow)}"),
        ]
        base_formula = "int(BaseLv/4 + STR + DEX/5 + LUK/3 + POW×5)"

    running = 0.0
    for label, add, raw_tip in terms:
        running += add
        parts.append(_row(label, f"+ {_fmt_debug(add)}", running, raw_tip))
    front_base = int(running)

    doubled = front_base * 2
    parts.append(_row("前 ATK × 2", "× 2", doubled, f"{base_formula} = {_fmt_debug(front_base)}；再 ×2"))

    sevenwind = _dint(used.get(425, used.get("425", 0))) == 1
    row_element = _dint(raw.get("skill_row_element", 0), 0)
    override = raw.get("attack_element_override", None)
    attack_element = row_element if override is None else _dint(override, row_element)
    front_element = attack_element if sevenwind else 0
    em = _debug_element_multiplier(front_element, target.get("element", 0), target.get("element_lv", 1))
    front_atk = int(doubled * em / 100)
    parts.append(_row("前 ATK 屬性倍率", f"× {_fmt_debug(em)}%", front_atk,
                      f"七風={sevenwind}；攻擊屬性={front_element}；目標屬性={_dint(target.get('element',0))} Lv{_dint(target.get('element_lv',1))}"))
    tip = f"{base_formula} → ×2 → 屬性倍率 {_fmt_debug(em)}% → int(...)={_fmt_debug(front_atk)}"
    return front_atk, parts, tip



def _independent_special_damage_info(snapshot, step_name):
    """用 Core raw special 狀態獨立重算特殊增傷，並回傳實際來源。"""
    if not isinstance(snapshot, dict):
        return None

    raw = snapshot.get("raw", {}) or {}
    special = raw.get("special", {}) or {}
    target = raw.get("target", {}) or {}
    weapon_class = _dint(raw.get("weapon_class", 0))
    target_class = _dint(target.get("class", 0))

    # 只用 raw 技能設定自行判斷近/遠距。
    ranged = _dint(raw.get("skill_rangedamage", 0)) == 1
    allowed_range_classes = set()
    for value in str(raw.get("special_wprange", 0) or "").split(","):
        value = value.strip()
        if not value:
            continue
        try:
            wid = int(float(value))
        except (TypeError, ValueError):
            continue
        if wid != 0:
            allowed_range_classes.add(wid)
    if weapon_class and weapon_class in allowed_range_classes:
        ranged = True

    normal_target = target_class == 0
    target_label = "一般" if normal_target else "首領"

    if step_name == "特殊魔法增傷":
        enabled = bool(special.get("sneak_attack"))
        factor = 30.0 if enabled and normal_target else 15.0 if enabled else 0.0
        children = []
        if enabled:
            children.append(_row(
                "潛擊",
                f"+ {_fmt_debug(factor)}%",
                f"{_fmt_debug(factor)}%",
                f"raw special.sneak_attack=True；目標階級={target_label}"
            ))
        return {
            "factor": factor,
            "children": children,
            "tip": (
                "Damage_view 獨立驗算特殊魔法增傷\n"
                f"目標階級：{target_label}\n"
                f"Sneak Attack：{'啟用' if enabled else '未啟用'}\n"
                f"特殊魔法增傷：{_fmt_debug(factor)}%"
            ),
        }

    if step_name != "特殊物理增傷":
        return None

    components = []
    if bool(special.get("sneak_attack")):
        value = 1.30 if normal_target else 1.15
        components.append(("潛擊", value, f"目標階級={target_label}"))

    if not ranged and bool(special.get("dark_crow")):
        value = 2.50 if normal_target else 1.75
        components.append(("致命爪痕", value, f"近距離；目標階級={target_label}"))

    if bool(special.get("rush_attack")):
        components.append(("衝擊撼動", 1.50, "近/遠距皆套用"))

    if ranged and bool(special.get("spore_attack")):
        components.append(("爆炸孢子", 1.05, "遠距離"))

    if ranged and bool(special.get("oleum_attack")):
        components.append(("聖油洗禮", 1.15, "遠距離"))

    raw_sum = sum(value for _name, value, _note in components)
    factor = max(1.0, raw_sum)

    children = []
    running = 0.0
    for name, value, note in components:
        running += value
        children.append(_row(
            name,
            f"+ ×{_fmt_debug(value)}",
            f"Σ {_fmt_debug(running)}",
            f"{note}；raw special 啟用"
        ))

    source_text = (
        " + ".join(f"{name} ×{_fmt_debug(value)}" for name, value, _ in components)
        if components else
        "沒有啟用會進入目前近/遠距類型的特殊物理來源"
    )
    return {
        "factor": factor,
        "children": children,
        "tip": (
            "Damage_view 獨立驗算特殊物理增傷\n"
            f"攻擊距離：{'遠距離' if ranged else '近距離'}\n"
            f"目標階級：{target_label}\n"
            f"來源：{source_text}\n"
            f"公式：max(1.0, 來源倍率相加) = ×{_fmt_debug(factor)}"
        ),
    }



def _independent_element_tolerance_info(snapshot):
    """只用 Core raw special + raw 攻擊屬性重算屬性耐受性倍率與來源。"""
    if not isinstance(snapshot, dict):
        return None

    raw = snapshot.get("raw", {}) or {}
    special = raw.get("special", {}) or {}

    # 與 Core 的 raw input 選擇規則一致，但不讀 Core 算好的 element_tolerance。
    row_element = _dint(raw.get("skill_row_element", 0), 0)
    override = raw.get("attack_element_override", None)
    attack_element = row_element if override is None else _dint(override, row_element)

    element_names = {
        0: "無", 1: "水", 2: "地", 3: "火", 4: "風",
        5: "毒", 6: "聖", 7: "暗", 8: "念", 9: "不死",
    }
    element_label = element_names.get(attack_element, str(attack_element))

    components = []
    inactive_notes = []

    # wanzih：勾選且攻擊屬性為地(2) / 火(3)才生效，+100%。
    if bool(special.get("wanzih")):
        if 2 <= attack_element <= 3:
            components.append(("萬紫千紅", 1.00, f"攻擊屬性={element_label}({attack_element})，條件 2~3 成立"))
        else:
            inactive_notes.append(
                f"萬紫千紅：已啟用，但攻擊屬性={element_label}({attack_element})，需地/火屬性才生效"
            )

    # poison_weak：勾選且毒屬性(5)才生效，+50%。
    if bool(special.get("poison_weak")):
        if attack_element == 5:
            components.append(("毒屬性弱點", 0.50, "攻擊屬性=毒(5)，條件成立"))
        else:
            inactive_notes.append(
                f"毒屬性弱點：已啟用，但攻擊屬性={element_label}({attack_element})，需毒屬性才生效"
            )

    # magic_poison：勾選即生效，+50%。
    if bool(special.get("magic_poison")):
        components.append(("魔力中毒", 0.50, "啟用即生效"))

    # Core 公式是 1.0 + 各有效來源；RAW step 需要直接倍率，例如 2.5。
    bonus = sum(value for _name, value, _note in components)
    factor = 1.0 + bonus

    children = []
    running_bonus = 0.0
    for name, value, note in components:
        running_bonus += value
        children.append(_row(
            name,
            f"+ {_fmt_debug(value * 100)}%",
            f"累計 +{_fmt_debug(running_bonus * 100)}%",
            note,
        ))

    source_text = (
        " + ".join(f"{name} +{_fmt_debug(value * 100)}%" for name, value, _ in components)
        if components else
        "沒有生效的屬性耐受性來源"
    )
    tip_lines = [
        "Damage_view 獨立驗算屬性耐受性%",
        f"目前攻擊屬性：{element_label} ({attack_element})",
        f"生效來源：{source_text}",
    ]
    if inactive_notes:
        tip_lines.append("未生效來源：")
        tip_lines.extend(f"- {note}" for note in inactive_notes)
    tip_lines.append(
        f"公式：1.0 + {_fmt_debug(bonus)} = ×{_fmt_debug(factor)}（{_fmt_debug(factor * 100)}%）"
    )

    return {
        "factor": factor,
        "children": children,
        "tip": "\n".join(tip_lines),
    }


def build_independent_start_verification(snapshot, atktype):
    """完全由 Damage_view 用 raw inputs 重算起始 MAX；不讀 Core 中間答案。"""
    if not isinstance(snapshot, dict):
        return [], None, None
    raw = snapshot.get("raw", {}) or {}
    core_result = snapshot.get("core_result", {}) or {}
    stats = raw.get("stats", {}) or {}
    wr = raw.get("weapon_right", {}) or {}
    wl = raw.get("weapon_left", {}) or {}
    target = raw.get("target", {}) or {}
    used = raw.get("used_skills", {}) or {}
    effects = raw.get("effect_dict", {}) or {}

    base_lv = _dnum(raw.get("base_lv", 0))
    weapon_class = _dint(raw.get("weapon_class", 0))

    if str(atktype).lower() not in {"physical", "d_b"}:
        # ---------------- Magic MAX ----------------
        total_int = _dnum(stats.get("INT", 0))
        total_dex = _dnum(stats.get("DEX", 0))
        total_luk = _dnum(stats.get("LUK", 0))
        total_spl = _dnum(stats.get("SPL", 0))

        # 括號 1：前 MATK，各子項逐步加總。
        parts = [
            ("BaseLv / 4", int(base_lv / 4), f"int(BaseLv / 4)；BaseLv={_fmt_debug(base_lv)}"),
            ("INT × 1.5", int(total_int * 1.5), f"int(INT × 1.5)；INT={_fmt_debug(total_int)}"),
            ("DEX / 5", int(total_dex / 5), f"int(DEX / 5)；DEX={_fmt_debug(total_dex)}"),
            ("LUK / 3", int(total_luk / 3), f"int(LUK / 3)；LUK={_fmt_debug(total_luk)}"),
            ("SPL × 5", int(total_spl * 5), f"int(SPL × 5)；SPL={_fmt_debug(total_spl)}"),
        ]
        subtotal = 0
        children = []
        for label, add, tip in parts:
            subtotal += add
            children.append(_row(label, f"+ {_fmt_debug(add)}", subtotal, tip))
        matkf = subtotal
        rows = []

        # 基礎裝備 MATK：先把主／副手武器原始 MATK 明確列出，流程圖可追到最原始裝備值。
        base_weapon_matk = _dnum(wr.get("matk", 0)) + _dnum(wl.get("matk", 0))
        base_matk_children = [
            _row("右手武器 MATK", f"+ {_fmt_debug(wr.get('matk', 0))}", _dnum(wr.get("matk", 0)),
                 f"Core raw 右手武器 MATK={_fmt_debug(wr.get('matk', 0))}"),
            _row("左手武器 MATK", f"+ {_fmt_debug(wl.get('matk', 0))}", base_weapon_matk,
                 f"Core raw 左手武器 MATK={_fmt_debug(wl.get('matk', 0))}"),
        ]
        rows.append(_row("基礎裝備 MATK", f"+ {_fmt_debug(base_weapon_matk)}", base_weapon_matk,
                         "主手與副手武器原始 MATK 加總；尚未加入精煉。", base_matk_children))

        # 括號 2：武器 + 精煉 MATK 合計。
        r_refine, _r_smatk, _r_var, _r_vmin = _debug_refine(wr.get("level"), wr.get("refine"), wr.get("grade"), magic=True)
        l_refine, _l_smatk, _l_var, _l_vmin = _debug_refine(wl.get("level"), wl.get("refine"), wl.get("grade"), magic=True)
        weapon_parts = [
            ("右手精煉 MATK", r_refine, f"Damage_view 獨立精煉公式；武器Lv={_dint(wr.get('level'))}, 精煉={_dint(wr.get('refine'))}, 品級={_dint(wr.get('grade'))}"),
            ("左手精煉 MATK", l_refine, f"Damage_view 獨立精煉公式；武器Lv={_dint(wl.get('level'))}, 精煉={_dint(wl.get('refine'))}, 品級={_dint(wl.get('grade'))}"),
        ]
        weapon_sum = base_weapon_matk
        weapon_children = [_row("基礎裝備 MATK", f"+ {_fmt_debug(base_weapon_matk)}", weapon_sum, "承接上一個基礎裝備 MATK 小計")]
        for label, add, tip in weapon_parts:
            weapon_sum += add
            weapon_children.append(_row(label, f"+ {_fmt_debug(add)}", weapon_sum, tip))
        rows.append(_row(
            "武器 + 精煉 MATK",
            "",
            weapon_sum,
            "右手武器MATK + 左手武器MATK + 右手精煉MATK + 左手精煉MATK",
            weapon_children,
        ))

        weapon_level_factor = 1 + _dint(wr.get("level", 0)) * 0.1
        weapon_scaled = weapon_sum * weapon_level_factor
        rows.append(_row(
            "武器等級倍率",
            f"× {_fmt_debug(weapon_level_factor)}",
            weapon_scaled,
            f"武器段 × (1 + 右手武器等級 × 0.1)；右手武器等級={_dint(wr.get('level'))}",
        ))

        magic_raw = weapon_scaled + matkf
        rows.append(_row(
            "前 MATK",
            f"+ {_fmt_debug(matkf)}",
            magic_raw,
            "已套武器等級倍率的武器段 MATK + 前 MATK；此步結果即 MATK 原始 MAX",
            children,
        ))

        magic_power_lv = 10 if _dint(used.get(366, used.get("366", 0))) == 1 else 0
        magic_power_factor = 1 + magic_power_lv * 0.05
        after_magic_power = magic_raw * magic_power_factor
        rows.append(_row(
            "魔力增幅",
            f"× {_fmt_debug(magic_power_factor)}",
            after_magic_power,
            f"magic_power_lv={magic_power_lv}；倍率=1+Lv×0.05",
        ))

        matk_armor = _effect_sum(effects, "MATK", "")
        final_value = int(after_magic_power + matk_armor)
        rows.append(_row(
            "裝備 MATK",
            f"+ {_fmt_debug(matk_armor)}",
            final_value,
            "從 raw effect_dict 自行加總 ('MATK','')；最後 int(...) 與 Core 同規則",
        ))

        core_value = core_result.get("magic_max")
        rows.append(_row(
            "起始 MATK（MAX）",
            "",
            final_value,
            "Damage_view 獨立驗算結果；Core 結果只在此列做 compare，不參與上述計算。",
            compare=core_value,
        ))
        return rows, final_value, core_value

    # ---------------- Physical equipment ATK MAX only ----------------
    total_str = _dnum(stats.get("STR", 0))
    total_dex = _dnum(stats.get("DEX", 0))
    primary_name = "DEX" if weapon_class in DEBUG_DEX_WEAPON_CLASSES else "STR"
    primary = total_dex if weapon_class in DEBUG_DEX_WEAPON_CLASSES else total_str
    weapon_atk = _dnum(wr.get("atk", 0))
    weapon_level = _dint(wr.get("level", 0))

    # 物理前 ATK 不放在起始裝備 ATK 驗算主流程。
    # 它會在下方傷害流程真正出現「前ATK」的那一步才加入，
    # 並把 BaseLv/STR/DEX/LUK/POW/×2/屬性倍率掛成該節點的來源分支。
    rows = []

    # 基礎裝備 ATK：流程圖顯示 Core raw 的右手武器原始 ATK。
    rows.append(_row(
        "基礎裝備 ATK",
        f"+ {_fmt_debug(weapon_atk)}",
        weapon_atk,
        f"Core raw 右手武器原始 ATK={_fmt_debug(weapon_atk)}；尚未套主素質、武器等級、精煉與體型。",
    ))

    # 括號：1 + 主素質/200 + 武器Lv*0.05
    factor_children = []
    factor = 1.0
    factor_children.append(_row("基礎倍率", "+ 1", factor, "武器基礎 ATK 倍率起點"))
    p_add = primary / 200
    factor += p_add
    factor_children.append(_row(f"{primary_name} / 200", f"+ {_fmt_debug(p_add)}", factor, f"{primary_name}={_fmt_debug(primary)}"))
    lv_add = weapon_level * 0.05
    factor += lv_add
    factor_children.append(_row("武器等級 × 0.05", f"+ {_fmt_debug(lv_add)}", factor, f"右手武器等級={weapon_level}"))
    weapon_base_max = weapon_atk * factor
    rows.append(_row(
        "武器基礎倍率（MAX）",
        "",
        factor,
        "(1 + 主素質/200 + 武器等級×0.05)",
        factor_children,
    ))
    rows.append(_row(
        "武器基礎 ATK（MAX）",
        f"× {_fmt_debug(factor)}",
        weapon_base_max,
        f"武器原始ATK={_fmt_debug(weapon_atk)} × 基礎倍率",
    ))

    atk_refine, _patk_refine, refine_over, _refine_min = _debug_refine(wr.get("level"), wr.get("refine"), wr.get("grade"), magic=False)
    if weapon_class in DEBUG_DEX_WEAPON_CLASSES:
        refine_delta = atk_refine - refine_over
        refine_weapon_max = int(weapon_base_max + refine_delta)
        refine_tip = "DEX 系武器 MAX：int(武器基礎ATK + 精煉ATK - 浮動上限)"
    else:
        refine_delta = atk_refine
        refine_weapon_max = int(weapon_base_max + refine_delta)
        refine_tip = "STR 系武器 MAX：int(武器基礎ATK + 精煉ATK)"
    rows.append(_row(
        "精煉 ATK",
        f"+ {_fmt_debug(refine_delta)}",
        refine_weapon_max,
        refine_tip + f"；武器Lv={weapon_level}, 精煉={_dint(wr.get('refine'))}, 品級={_dint(wr.get('grade'))}",
    ))
    KOUKAI_on = _dint(used.get(3018, used.get("3018", 0))) == 1
    if KOUKAI_on:
        refine_weapon_max = int(refine_weapon_max * 2)
        rows.append(_row(
            "地符:剛塊",
            f"× 200%",
            refine_weapon_max,
            f"武器精煉後ATK加成",
        ))
    ignore_size = _effect_sum(effects, "武器體型修正", "%")
    size_penalty = 1.0 if ignore_size >= 100 else _debug_size_penalty(weapon_class, target.get("size", 1))
    after_size = int(refine_weapon_max * size_penalty)
    rows.append(_row(
        "武器體型修正",
        f"× {_fmt_debug(size_penalty)}",
        after_size,
        f"目標size={_dint(target.get('size',1))}；忽略體型效果={_fmt_debug(ignore_size)}%",
    ))

    ammo = _effect_sum(effects, "箭矢/彈藥ATK", "")
    after_ammo = after_size + ammo
    rows.append(_row("箭矢 / 彈藥 ATK", f"+ {_fmt_debug(ammo)}", after_ammo, "從 raw effect_dict 自行加總"))

    edp_on = _dint(used.get(378, used.get("378", 0))) == 1
    magnum_on = _dint(used.get(7, used.get("7", 0))) == 1
    special = int(after_ammo)
    if edp_on:
        em = _debug_element_multiplier(5, target.get("element", 0), target.get("element_lv", 1))
        factor2 = 1 + 0.25 * (em / 100)
        special = int(after_ammo * factor2)
        rows.append(_row("致命塗毒武器段", f"× {_fmt_debug(factor2)}", special, f"毒屬性倍率={em}%；1+0.25×倍率"))
    elif magnum_on:
        em = _debug_element_multiplier(3, target.get("element", 0), target.get("element_lv", 1))
        factor2 = 1 + 0.2 * (em / 100)
        special = int(after_ammo * factor2)
        rows.append(_row("怒爆武器段", f"× {_fmt_debug(factor2)}", special, f"火屬性倍率={em}%；1+0.2×倍率"))

    atk_armor = _effect_sum(effects, "ATK", "")
    after_armor = special + atk_armor
    rows.append(_row("裝備 ATK", f"+ {_fmt_debug(atk_armor)}", after_armor, "從 raw effect_dict 自行加總 ('ATK','')"))

    investigate = 0
    if _dint(used.get(266, used.get("266", 0))) == 1:
        def_reduction = _debug_def_reduction(effects, target.get("race", 0), target.get("class", 0))
        temp = int(100 - def_reduction)
        target_def = _dnum(target.get("def", 0))
        investigate = max(0, int(target_def / 2 + (target_def / 2) * (temp / 100)))
        after_armor += investigate
        rows.append(_row("浸透勁 ATK", f"+ {_fmt_debug(investigate)}", after_armor, f"DEF={_fmt_debug(target_def)}；物理破防={_fmt_debug(def_reduction)}%"))

    final_value = int(after_armor)
    core_value = core_result.get("weapon_atk_max")
    rows.append(_row(
        "裝備 ATK（MAX）",
        "",
        final_value,
        "Damage_view 獨立驗算結果；不包含前 ATK。Core 結果只供 compare。",
        compare=core_value,
    ))
    return rows, final_value, core_value



class FlowChartView(QGraphicsView):
    """獨立流程圖：主流程由上到下；括號/小計 children 固定列在左側。"""
    NODE_W = 230
    NODE_H = 78
    MAIN_GAP_Y = 68
    BRANCH_GAP_X = 92
    BRANCH_GAP_Y = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(QColor(28, 28, 28)))

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
            event.accept()
            return
        super().wheelEvent(event)

    def _add_arrow(self, x1, y1, x2, y2, branch=False):
        pen = QPen(QColor(145, 145, 145) if branch else QColor(205, 205, 205), 1.6)
        # 用折線讓左右分支不切過節點；主流程則維持直線向下。
        if branch:
            mid_x = (x1 + x2) / 2
            self._scene.addLine(x1, y1, mid_x, y1, pen)
            self._scene.addLine(mid_x, y1, mid_x, y2, pen)
            self._scene.addLine(mid_x, y2, x2, y2, pen)
            sx, sy = mid_x, y2
        else:
            self._scene.addLine(x1, y1, x2, y2, pen)
            sx, sy = x1, y1

        dx, dy = x2 - sx, y2 - sy
        length = max((dx * dx + dy * dy) ** 0.5, 1.0)
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        size = 8.0
        p1 = QPointF(x2, y2)
        p2 = QPointF(x2 - ux * size + px * size * 0.55, y2 - uy * size + py * size * 0.55)
        p3 = QPointF(x2 - ux * size - px * size * 0.55, y2 - uy * size - py * size * 0.55)
        poly = self._scene.addPolygon(QPolygonF([p1, p2, p3]), QPen(Qt.NoPen), QBrush(pen.color()))
        poly.setZValue(2)

    def _add_reference_arrow(self, source_box, target_box, label='', tip=''):
        """從上游基準節點沿主幹左側往下拉參考線，再右轉匯入目標節點。

        所有額外來源統一放在左側，避免流程圖左右兩邊同時出現來源造成閱讀混亂。
        用於像物理 ATK% 這種「在後面才套用，但基準值固定來自起始 ATK」的關係。
        """
        sx, sy, sw, sh = source_box
        tx, ty, tw, th = target_box
        pen = QPen(QColor(125, 145, 155), 1.4)

        # 固定走主幹左側：起始節點左緣 → 向左 → 向下 → 右轉進目標左緣。
        route_x = min(sx, tx) - 120
        start_x = sx
        start_y = sy + sh / 2
        end_x = tx
        end_y = ty + th / 2

        self._scene.addLine(start_x, start_y, route_x, start_y, pen)
        self._scene.addLine(route_x, start_y, route_x, end_y, pen)
        self._scene.addLine(route_x, end_y, end_x, end_y, pen)

        # 箭頭由左往右匯入目標節點。
        size = 8.0
        p1 = QPointF(end_x, end_y)
        p2 = QPointF(end_x - size, end_y - size * 0.55)
        p3 = QPointF(end_x - size, end_y + size * 0.55)
        poly = self._scene.addPolygon(
            QPolygonF([p1, p2, p3]), QPen(Qt.NoPen), QBrush(pen.color())
        )
        poly.setZValue(2)

        if label:
            font = QFont("Microsoft JhengHei UI", 9)
            label_item = self._scene.addText(str(label), font)
            label_item.setDefaultTextColor(QColor(180, 205, 215))
            # 標籤也固定在左側參考線旁，不佔用主流程右側。
            label_item.setPos(route_x - 4, (start_y + end_y) / 2 - 14)
            label_item.setToolTip(tip or '')

    def _add_node(self, x, y, title, op, result, tip='', kind='normal', width=None, height=None):
        title_font = QFont("Microsoft JhengHei UI", 10)
        title_font.setBold(True)
        detail_font = QFont("Microsoft JhengHei UI", 9)
        fm_title = QFontMetrics(title_font)
        fm_detail = QFontMetrics(detail_font)

        detail = ''
        if op and result not in ('', None):
            detail = f'{op}   →   {_fmt_debug(result)}'
        elif result not in ('', None):
            detail = f'→ {_fmt_debug(result)}'
        elif op:
            detail = str(op)

        auto_w = max(self.NODE_W, fm_title.horizontalAdvance(str(title)) + 32,
                     fm_detail.horizontalAdvance(detail) + 32)
        w = max(width or 0, auto_w)
        h = max(height or 0, self.NODE_H)

        if kind == 'start':
            fill = QColor(55, 70, 75)
        elif kind == 'damage':
            fill = QColor(48, 48, 48)
        elif kind == 'final':
            fill = QColor(65, 70, 55)
        elif kind == 'child':
            fill = QColor(42, 42, 42)
        elif kind == 'base':
            fill = QColor(52, 58, 68)
        else:
            fill = QColor(50, 50, 50)

        border = QPen(QColor(125, 125, 125), 1.2)
        rect = self._scene.addRect(x, y, w, h, border, QBrush(fill))
        rect.setToolTip(tip or '')

        title_item = self._scene.addText(str(title), title_font)
        title_item.setDefaultTextColor(QColor(245, 245, 245))
        title_item.setTextWidth(w - 18)
        title_item.setPos(x + 9, y + 7)
        title_item.setToolTip(tip or '')

        detail_item = self._scene.addText(detail, detail_font)
        detail_item.setDefaultTextColor(QColor(205, 205, 205))
        detail_item.setTextWidth(w - 18)
        detail_item.setPos(x + 9, y + 41)
        detail_item.setToolTip(tip or '')
        return (x, y, w, h)

    def _add_side_children(self, parent_box, children, group_top=None):
        """左側 children 依實際累加順序串成一條垂直鏈。

        規則：第一項 → 第二項 → ... → 最後一項，只有最後一項才右轉匯入主節點。
        這樣可以直接看出括號 / 小計內是依序計算，而不是多個節點同時灌入。
        """
        if not children:
            return parent_box[3]

        child_w = 230
        child_h = 72
        px, py, pw, ph = parent_box
        child_x = px - self.BRANCH_GAP_X - child_w

        stack_h = len(children) * child_h + (len(children) - 1) * self.BRANCH_GAP_Y
        used_h = max(stack_h, ph)
        # add_main 會讓 parent 與最後一個 child 大致同高；group_top 是整組的頂端。
        base_y = group_top if group_top is not None else py - max(0, stack_h - ph)

        child_boxes = []
        cy = base_y
        for child in children:
            cbox = self._add_node(
                child_x, cy,
                child.get('label', ''), child.get('delta', ''), child.get('result', ''),
                child.get('tip', ''), 'child', width=child_w, height=child_h,
            )
            child_boxes.append(cbox)
            cy += child_h + self.BRANCH_GAP_Y

        # 左側小計：由上往下逐步累加。
        for prev_child, next_child in zip(child_boxes, child_boxes[1:]):
            self._add_arrow(
                prev_child[0] + prev_child[2] / 2,
                prev_child[1] + prev_child[3],
                next_child[0] + next_child[2] / 2,
                next_child[1],
                False,
            )

        # 只有最後一個子項完成後，才向右匯入中間主節點。
        last = child_boxes[-1]
        self._add_arrow(
            last[0] + last[2], last[1] + last[3] / 2,
            px, py + ph / 2,
            True,
        )
        return used_h

    def render_full_image(self, scale=1.0):
        """把整張 scene 輸出成 QImage，不受目前視窗縮放或可視區域限制。"""
        bounds = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        if bounds.isEmpty():
            return QImage()

        scale = max(0.25, float(scale or 1.0))
        width = max(1, int(math.ceil(bounds.width() * scale)))
        height = max(1, int(math.ceil(bounds.height() * scale)))

        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(QColor(28, 28, 28))

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        target = image.rect()
        self._scene.render(painter, target, bounds)
        painter.end()
        return image

    def copy_full_image(self):
        """完整流程圖複製到系統剪貼簿，可直接貼到聊天、Word、Paint。"""
        image = self.render_full_image(scale=1.0)
        if image.isNull():
            return False
        QApplication.clipboard().setImage(image)
        return True

    def save_full_image(self, filename):
        """把整張流程圖直接存成 PNG。"""
        image = self.render_full_image(scale=1.0)
        if image.isNull():
            return False
        return image.save(str(filename), 'PNG')

    def set_flow(self, verify_rows, start_name, start_value, steps, final_damage=None, atk_percent_info=None):
        self._scene.clear()
        verify_rows = verify_rows or []
        steps = steps or []

        main_x = 520
        y = 40
        prev_box = None

        def add_main(title, op, result, tip='', kind='normal', children=None):
            nonlocal y, prev_box
            children = children or []
            group_top = y

            # 有子計算時，主節點與左側最後一個子項對齊；
            # 左側便能自然呈現「由上往下算完 → 最後右轉進主節點」。
            if children:
                child_h = 72
                stack_h = len(children) * child_h + (len(children) - 1) * self.BRANCH_GAP_Y
                box_y = group_top + max(0, stack_h - self.NODE_H)
            else:
                stack_h = self.NODE_H
                box_y = group_top

            box = self._add_node(main_x, box_y, title, op, result, tip, kind)
            if prev_box is not None:
                self._add_arrow(prev_box[0] + prev_box[2] / 2, prev_box[1] + prev_box[3],
                                box[0] + box[2] / 2, box[1])
            used_h = self._add_side_children(box, children, group_top=group_top)
            prev_box = box
            y = group_top + max(box_y + box[3] - group_top, used_h) + self.MAIN_GAP_Y
            return box

        # 1) Damage_view 獨立驗算主流程。
        for row in verify_rows:
            add_main(
                str(row.get('label', '')),
                str(row.get('delta', '') or ''),
                row.get('result', ''),
                str(row.get('tip', '') or ''),
                'normal',
                row.get('children', []) or [],
            )

        # 2) 驗算結果交給可拖曳傷害流程。
        # 保留起始節點座標；物理 ATK% 會另外從這裡拉一條「基準 ATK」參考線。
        start_box = add_main(
            start_name, '作為傷害流程輸入', start_value,
            'Damage_view 獨立驗算出的起始值；從此處開始套用下方可拖曳傷害步驟。',
            'start'
        )

        # 3) 目前拖曳順序的傷害步驟。
        for s in steps:
            name = getattr(s, 'name', '')
            factor = getattr(s, 'factor', '')
            mode = getattr(s, 'mode', '')
            result = getattr(s, 'result', '')
            if name in ('MDEF減算', 'DEF減算'):
                op = f'- {factor} [{mode}]'
            elif name in ('ATK%', '前ATK', '神威ATK', '武器修煉ATK', '砲彈ATK', '靈氣劍'):
                op = f'+ {factor} [{mode}]'
            elif name in NO_PLUS_ONE:
                op = f'× {round(factor, 2)}% [{mode}]'
            elif name in VALUE_100:
                op = f'× {round(factor * 100, 2)}% [{mode}]'
            elif name in RAW:
                op = f'× {round(factor * 100, 2)}% [{mode}]'
            else:
                op = f'× {round(100 + factor, 2)}% [{mode}]'

            tip = getattr(s, 'debug_tip', '') or f'目前拖曳排序中的傷害步驟：{name}'
            # 傷害步驟也可以帶自己的來源分支。
            # 例如物理「前ATK」會在實際加入傷害流程的位置，
            # 顯示 Damage_view 獨立驗算的 BaseLv/STR/DEX/LUK/POW/×2/屬性倍率。
            children = list(getattr(s, 'debug_children', []) or [])
            atk_reference = None
            if name == 'ATK%' and atk_percent_info:
                base_atk = atk_percent_info.get('base_atk', 0)
                total_percent = atk_percent_info.get('total_percent', 0)
                delta = atk_percent_info.get('delta', 0)
                # 流程圖中間欄直接顯示「ATK% 幾 %」以及實際換算出的加值。
                # 右側 result 仍維持這一步套用完成後的總結果。
                op = f'× {_fmt_debug(total_percent)}%  =  +{_fmt_debug(delta)} [{mode}]'
                tip = (
                    atk_percent_info.get('tip', tip)
                    + f'\n\n流程圖：{_fmt_debug(base_atk)} × {_fmt_debug(total_percent)}% '
                      f'= +{_fmt_debug(delta)}'
                )

                # 「前一步裝備 ATK」不是 ATK% 的子項；它的來源就是上方起始 ATK。
                # 額外來源統一沿左側向下延伸，再右轉匯入 ATK% 節點。
                children = []
                atk_reference = {
                    'base_atk': base_atk,
                    'percent': total_percent,
                    'delta': delta,
                }

            damage_box = add_main(name, op, result, tip, 'damage', children)

            if atk_reference is not None and start_box is not None:
                base_atk = atk_reference['base_atk']
                total_percent = atk_reference['percent']
                delta = atk_reference['delta']
                ref_tip = (
                    f'ATK% 固定以起始裝備 ATK {_fmt_debug(base_atk)} 為基準\n'
                    f'× {_fmt_debug(total_percent)}% → +{_fmt_debug(delta)}'
                )
                self._add_reference_arrow(
                    start_box, damage_box,
                    f'基準 ATK {_fmt_debug(base_atk)}',
                    ref_tip,
                )

        if final_damage is not None:
            add_main('最終傷害', '', final_damage,
                     'Damage_view 依目前拖曳順序計算出的最終傷害。', 'final')

        bounds = self._scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self._scene.setSceneRect(bounds)


class FlowChartWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle('Damage View 計算流程圖')
        self.resize(1180, 760)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        title = QLabel('計算流程圖（主流程：上 → 下；來源/小計：左側匯入主節點）')
        top.addWidget(title)
        top.addStretch(1)
        hint = QLabel('Ctrl + 滾輪：縮放　拖曳空白處：平移')
        hint.setStyleSheet('opacity: 0.7;')
        top.addWidget(hint)

        self.copy_btn = QPushButton('複製整張圖')
        self.copy_btn.setToolTip('把完整流程圖直接複製到剪貼簿，不只截目前看到的區域')
        self.copy_btn.clicked.connect(self.copy_flowchart_image)
        top.addWidget(self.copy_btn)

        self.save_btn = QPushButton('儲存 PNG')
        self.save_btn.setToolTip('把完整流程圖直接輸出成一張 PNG 圖片')
        self.save_btn.clicked.connect(self.save_flowchart_image)
        top.addWidget(self.save_btn)

        self.capture_status = QLabel('')
        self.capture_status.setStyleSheet('color: #9ec7a5; padding-left: 6px;')
        top.addWidget(self.capture_status)

        lay.addLayout(top)
        self.view = FlowChartView(self)
        lay.addWidget(self.view, 1)

    def copy_flowchart_image(self):
        if self.view.copy_full_image():
            self.capture_status.setText('已複製完整流程圖')
            QTimer.singleShot(2500, lambda: self.capture_status.setText(''))
        else:
            self.capture_status.setText('目前沒有可截圖的流程')

    def save_flowchart_image(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            '儲存完整流程圖',
            'Damage_View_Flowchart.png',
            'PNG 圖片 (*.png)'
        )
        if not filename:
            return
        if not filename.lower().endswith('.png'):
            filename += '.png'
        if self.view.save_full_image(filename):
            self.capture_status.setText('PNG 已儲存')
            QTimer.singleShot(2500, lambda: self.capture_status.setText(''))
        else:
            self.capture_status.setText('儲存失敗')

    def set_flow(self, verify_rows, start_name, start_value, steps, final_damage=None, atk_percent_info=None):
        self.view.set_flow(verify_rows, start_name, start_value, steps, final_damage, atk_percent_info)


class DamageCalculator(QWidget):
    def __init__(self, matk=0, steps=None, atktype="physical"):
        super().__init__()
        self.setWindowTitle("(偵錯)計算歷程顯示 / Core 獨立驗算")
        self.resize(450, 800)
        self._in_calculate = False
        self.atktype = atktype
        self.debug_snapshot = _load_core_debug_raw()
        self._last_verified_start = None
        self._last_verify_rows = []
        self._last_final_damage = None
        self._last_atk_percent_info = None
        self.flow_window = None

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        root.addLayout(left, 1)

        # 頂端只保留狀態與重算；起始值移到驗算區與拖曳區的接點。
        top_bar = QFrame()
        top_bar.setFrameShape(QFrame.StyledPanel)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 8, 10, 8)
        title = "物理 ATK 獨立驗算" if atktype in ("physical", "d_b") else "魔法 MATK 獨立驗算"
        top_layout.addWidget(QLabel(title))
        self.verify_status = QLabel("")
        top_layout.addWidget(self.verify_status)
        top_layout.addStretch(1)
        self.flow_btn = QPushButton("流程圖")
        self.flow_btn.clicked.connect(self.show_flowchart)
        top_layout.addWidget(self.flow_btn)
        self.calc_btn = QPushButton("計算 / 重算")
        self.calc_btn.clicked.connect(self.calculate)
        top_layout.addWidget(self.calc_btn)
        left.addWidget(top_bar)

        # 左→右關聯表頭：上下兩區皆使用同一欄位比例。
        relation_header = QFrame()
        relation_header.setFrameShape(QFrame.NoFrame)
        rh = QHBoxLayout(relation_header)
        rh.setContentsMargins(10, 2, 10, 2)
        h1 = QLabel("來源 / 項目  →")
        h2 = QLabel("本步運算  →")
        h3 = QLabel("結果")
        h3.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        rh.addWidget(h1, int(REL_NAME_RATIO * 100))
        rh.addWidget(h2, int(REL_OP_RATIO * 100))
        rh.addWidget(h3, int(REL_RESULT_RATIO * 100))
        relation_header.setStyleSheet("QLabel { font-weight: 600; padding: 3px 0; } QFrame { border-bottom: 1px solid #555; }")
        left.addWidget(relation_header)

        # 上半部：Damage_view 只用 Core raw inputs 自己重算。
        # 主流程由上往下；只有括號/小計內容以 children 顯示。
        self.verify_tree = RelationTreeWidget()
        self.verify_tree.setColumnCount(3)
        self.verify_tree.setHeaderHidden(True)
        self.verify_tree.setRootIsDecorated(True)
        self.verify_tree.setIndentation(18)
        self.verify_tree.setUniformRowHeights(True)
        self.verify_tree.setAlternatingRowColors(False)
        self.verify_tree.setFrameShape(QFrame.NoFrame)
        self.verify_tree.setSelectionMode(QTreeWidget.SingleSelection)
        self.verify_tree.setStyleSheet("""
            QTreeWidget { border: none; background: transparent; }
            QTreeWidget::item { height: 30px; }
        """)
        left.addWidget(self.verify_tree)

        # 起始 ATK/MATK 是「驗算區 → 傷害步驟」的連接點。
        self.start_bar = QFrame()
        self.start_bar.setFrameShape(QFrame.StyledPanel)
        sb = QHBoxLayout(self.start_bar)
        sb.setContentsMargins(10, 6, 10, 6)
        self.start_name = QLabel("起始 ATK" if atktype in ("physical", "d_b") else "起始 MATK")
        self.start_op = QLabel("↓ 作為下方第一步輸入")
        self.start_value = QLabel(_fmt_debug(matk))
        self.start_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.start_value.setStyleSheet("font-weight: 700;")
        sb.addWidget(self.start_name, int(REL_NAME_RATIO * 100))
        sb.addWidget(self.start_op, int(REL_OP_RATIO * 100))
        sb.addWidget(self.start_value, int(REL_RESULT_RATIO * 100))
        left.addWidget(self.start_bar)

        hint = QLabel("🖱️ 下方傷害步驟可直接拖曳排序")
        hint.setStyleSheet("opacity: 0.75;")
        left.addWidget(hint)

        self.view = LiveReorderListView()
        self.view.setProperty("animated", True)
        self.view.setDragEnabled(True)
        self.view.setAcceptDrops(True)
        self.view.setDropIndicatorShown(True)
        self.view.setDefaultDropAction(Qt.MoveAction)
        self.view.setDragDropMode(QListView.InternalMove)
        self.view.setSelectionMode(QListView.SingleSelection)

        if steps is None:
            self.model = StepModel([Step(n, f, "INT", 0.0) for n, f in initial_steps])
        else:
            self.model = StepModel([Step(n, f, "INT", 0.0) for n, f, *_ in steps])
        self.view.setModel(self.model)
        self.delegate = StepDelegate(self.view)
        self.view.setItemDelegate(self.delegate)
        self.model.rowsMoved.connect(lambda *args: self.calculate())

        def on_model_data_changed(topLeft, bottomRight, roles):
            if roles and (Qt.EditRole in roles):
                self.calculate()
        self.model.dataChanged.connect(on_model_data_changed)
        left.addWidget(self.view, 1)

        # 保留舊欄位做 API 相容，但不再讓它當 Damage_view 的驗算輸入。
        self.matk_input = QSpinBox(self)
        self.matk_input.setRange(-10_000_000, 10_000_000)
        self.matk_input.setValue(matk)
        self.matk_input.hide()

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.calculate()

    def _append_verify_item(self, parent, row):
        delta = str(row.get("delta", "") or "")
        result = _fmt_debug(row.get("result", ""))
        item = QTreeWidgetItem([str(row.get("label", "")), delta, result])
        item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
        tip = str(row.get("tip", "") or "")
        compare = row.get("compare", None)
        if compare is not None:
            calc = _dnum(row.get("result", 0))
            core = _dnum(compare)
            diff = calc - core
            tip = (tip + "\n" if tip else "") + f"Damage_view={_fmt_debug(calc)}；Core={_fmt_debug(core)}；差異={_fmt_debug(diff)}"
            if abs(diff) > 1e-9:
                item.setText(0, "⚠ " + item.text(0))
            else:
                item.setText(0, "✓ " + item.text(0))
        if tip:
            for col in range(3):
                item.setToolTip(col, tip)
        if parent is None:
            self.verify_tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        for child in row.get("children", []) or []:
            self._append_verify_item(item, child)
        # 只有括號/小計保留樹狀；主流程沒有額外階層。
        if row.get("children"):
            item.setExpanded(True)
        return item

    def refresh_verification(self):
        self.debug_snapshot = _load_core_debug_raw() or self.debug_snapshot
        self.verify_tree.clear()
        rows, own_value, core_value = build_independent_start_verification(self.debug_snapshot, self.atktype)
        self._last_verify_rows = rows or []
        if not rows:
            item = QTreeWidgetItem(["尚未取得 Core 原始取值", "", ""])
            item.setToolTip(0, "請先讓主程式完成一次 ro_core 傷害計算，再開啟此驗算視窗。")
            self.verify_tree.addTopLevelItem(item)
            self.verify_status.setText("未取得 raw inputs")
            return None, None
        for row in rows:
            self._append_verify_item(None, row)

        if core_value is None:
            self.verify_status.setText("無 Core compare 值")
        else:
            diff = _dnum(own_value) - _dnum(core_value)
            self.verify_status.setText("✓ 一致" if abs(diff) <= 1e-9 else f"⚠ 差異 {_fmt_debug(diff)}")

        self._last_verified_start = own_value
        if own_value is not None:
            self.start_value.setText(_fmt_debug(own_value))
            self.matk_input.blockSignals(True)
            self.matk_input.setValue(int(own_value))
            self.matk_input.blockSignals(False)
        return own_value, core_value

    def _physical_atk_percent_info(self, start_value):
        """
        只用 raw effect_dict 的逐筆來源重建 ATK%。
        Core 已加總的 atk_percent / ATK% 絕對加值一律不使用。
        """
        if self.atktype not in ("physical", "d_b"):
            return None
        snap = self.debug_snapshot or {}
        raw = snap.get("raw", {}) or {}
        effects = raw.get("effect_dict", {}) or {}
        entries = _effect_entries(effects, "ATK%", "%")

        total_percent = sum(value for value, _source in entries)
        base_atk = _dnum(start_value)
        delta = int(base_atk * (total_percent / 100.0))
        sources = [
            {
                "value": value,
                "source": source,
                "tip": f"raw effect_dict: {source} → ATK% +{_fmt_debug(value)}%",
            }
            for value, source in entries
        ]
        tip = (
            f"前一步裝備 ATK：{_fmt_debug(base_atk)}"
            + f"\nATK%：{_fmt_debug(total_percent)}%"
            + f"\n公式：int({_fmt_debug(base_atk)} × {_fmt_debug(total_percent)} / 100)"
            + f"\n本步加值：+{_fmt_debug(delta)}"
            + f"\n加回流程後：{_fmt_debug(base_atk + delta)}"
        )
        return {
            "base_atk": base_atk,
            "total_percent": total_percent,
            "delta": delta,
            "sources": sources,
            "tip": tip,
        }

    def _linked_physical_atk_percent_delta(self, start_value):
        info = self._physical_atk_percent_info(start_value)
        return None if info is None else info.get("delta")

    def _sync_flowchart(self):
        if self.flow_window is None:
            return
        try:
            self.flow_window.set_flow(
                self._last_verify_rows,
                self.start_name.text(),
                self._last_verified_start if self._last_verified_start is not None else self.matk_input.value(),
                self.model.steps,
                self._last_final_damage,
                self._last_atk_percent_info,
            )
        except RuntimeError:
            self.flow_window = None

    def show_flowchart(self):
        if self.flow_window is None:
            self.flow_window = FlowChartWindow(self)
        self._sync_flowchart()
        self.flow_window.show()
        self.flow_window.raise_()
        self.flow_window.activateWindow()

    def set_data(self, matk: int, steps):
        """保留舊呼叫；Core 傳入值只做相容，不再作為驗算器的起始輸入。"""
        self.matk_input.setValue(int(matk))
        self.model.steps = [Step(n, f, "INT", 0.0) for (n, f, *_) in steps]
        self.model.layoutChanged.emit()
        self.debug_snapshot = _load_core_debug_raw()
        self.calculate()

    def calculate(self):
        if getattr(self, "_in_calculate", False):
            return
        self._in_calculate = True
        try:
            own_value, _core_value = self.refresh_verification()

            # 下方傷害流程的起點直接採用 Damage_view 自己驗算出的起始值。
            # 若尚未取得 raw inputs，才退回舊 API 傳入值。
            val = float(own_value if own_value is not None else self.matk_input.value())
            self.start_value.setText(_fmt_debug(val))

            # 物理 ATK%：逐筆讀 raw effect_dict 來源，由 Damage_view 自己加總、再套到上方驗算 ATK。
            self._last_atk_percent_info = self._physical_atk_percent_info(val)
            linked_atk_delta = None if self._last_atk_percent_info is None else self._last_atk_percent_info.get("delta")
            linked_front_atk = None
            linked_front_tip = ""
            if self.atktype in ("physical", "d_b"):
                linked_front_atk, _front_children, linked_front_tip = _independent_physical_front_atk(self.debug_snapshot)

            lines = [f"Damage_view 起始值: {_fmt_debug(val)}"]
            results = []
            for s in self.model.steps:
                factor = s.factor
                if s.name == "前ATK" and linked_front_atk is not None:
                    factor = linked_front_atk
                    s.factor = factor
                    s.debug_tip = linked_front_tip
                    # 前 ATK 的來源只掛在「屬性倍率% → 前ATK → 神威ATK」
                    # 這個真正的傷害步驟上，不再提前放到流程圖最上方。
                    s.debug_children = list(_front_children or [])
                elif hasattr(s, "debug_children") and s.name != "ATK%":
                    s.debug_children = []
                if s.name == "ATK%" and linked_atk_delta is not None:
                    factor = linked_atk_delta
                    # 同步更新顯示欄，讓使用者看到實際 + 的數字。
                    s.factor = factor
                    info = self._last_atk_percent_info or {}
                    s.debug_tip = info.get("tip", "")
                    if info.get("sources"):
                        lines.append("ATK% 原始來源：")
                        for src in info.get("sources", []):
                            lines.append(f"  {src.get('source')}: +{_fmt_debug(src.get('value'))}%")
                        lines.append(f"  ATK% 合計: {_fmt_debug(info.get('total_percent'))}%")

                # 特殊物理 / 魔法增傷：
                # Core 只提供 raw special 狀態；倍率與來源由 Damage_view 自己重算。
                if s.name in ("特殊物理增傷", "特殊魔法增傷"):
                    special_info = _independent_special_damage_info(self.debug_snapshot, s.name)
                    if special_info is not None:
                        factor = special_info.get("factor", factor)
                        s.factor = factor
                        s.debug_tip = special_info.get("tip", "")
                        s.debug_children = list(special_info.get("children", []) or [])
                        lines.append(f"{s.name} 來源：")
                        if s.debug_children:
                            for child in s.debug_children:
                                lines.append(
                                    f"  {child.get('label')}: {child.get('delta')} "
                                    f"({child.get('tip', '')})"
                                )
                        else:
                            lines.append("  無額外來源")

                # 屬性耐受性：
                # 萬紫千紅 / 毒屬性弱點 / 魔力中毒都只從 raw special 重新判斷。
                # 不使用 Core 已算好的 special_values["element_tolerance"]。
                if s.name == "屬性耐受性%":
                    tolerance_info = _independent_element_tolerance_info(self.debug_snapshot)
                    if tolerance_info is not None:
                        factor = tolerance_info.get("factor", factor)
                        s.factor = factor
                        s.debug_tip = tolerance_info.get("tip", "")
                        s.debug_children = list(tolerance_info.get("children", []) or [])
                        lines.append("屬性耐受性% 來源：")
                        if s.debug_children:
                            for child in s.debug_children:
                                lines.append(
                                    f"  {child.get('label')}: {child.get('delta')} "
                                    f"({child.get('tip', '')})"
                                )
                        else:
                            lines.append("  無生效來源 → ×100%")

                new_val = apply_round(val, factor, s.mode, s.name)
                results.append(new_val)
                if s.name in ("MDEF減算", "DEF減算"):
                    lines.append(f"{s.name} -{factor} [{s.mode}] → {fmt(new_val)}")
                elif s.name in ("ATK%", "前ATK", "神威ATK", "武器修煉ATK", "砲彈ATK", "靈氣劍"):
                    lines.append(f"{s.name} +{factor} [{s.mode}] → {fmt(new_val)}")
                else:
                    lines.append(f"{s.name} ×{factor} [{s.mode}] → {fmt(new_val)}")
                val = new_val

            self.model.set_results(results)
            lines.append(f"\n🎯 最終傷害：{fmt(val)}")
            self.output.setPlainText("\n".join(lines))
            self._last_final_damage = val
            self._sync_flowchart()
        finally:
            self._in_calculate = False


if __name__ == "__main__":
    app = QApplication(sys.argv)
    #w = DamageCalculator()
    #w.show()
    sys.exit(app.exec())
