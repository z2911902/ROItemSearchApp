import sys
import math
from dataclasses import dataclass
from PySide6.QtCore import (
    Qt, QAbstractListModel, QModelIndex, QPersistentModelIndex, QSize
)
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSpinBox,
    QListView, QTextEdit, QPushButton, QFrame, QStyledItemDelegate, QComboBox
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



class StepDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index):
        painter.save()

        name, factor, mode, result = index.data(Qt.DisplayRole)

        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())

        r = option.rect
        left_pad = 10
        right_pad = 10

        name_rect = r.adjusted(left_pad, 0, 0, 0)
        name_rect.setWidth(140)

        factor_rect = r.adjusted(left_pad + 150, 0, 0, 0)
        factor_rect.setWidth(100)

        mode_rect = r.adjusted(left_pad + 130 + 100, 0, 0, 0)
        mode_rect.setWidth(150)

        result_rect = r.adjusted(0, 0, -right_pad, 0)
        result_rect.setLeft(r.right() - 200)

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
        painter.drawText(factor_rect, Qt.AlignVCenter | Qt.AlignLeft, ftxt)
        painter.drawText(mode_rect, Qt.AlignVCenter | Qt.AlignLeft, f"[{mode}]")
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
        x = r.left() + 10 + 125 + 100
        w = 110
        editor.setGeometry(x, r.top() + 6, w, r.height() - 12)

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


class DamageCalculator(QWidget):
    def __init__(self, matk=0, steps=None,atktype="physical"):
        super().__init__()
        self.setWindowTitle("(偵錯)計算歷程顯示")
        self.resize(450, 800)
        self._in_calculate = False
        root = QHBoxLayout(self)

        # 左邊
        left = QVBoxLayout()
        root.addLayout(left, 1)

        top_bar = QFrame()
        top_bar.setFrameShape(QFrame.StyledPanel)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 10, 10, 10)
        if atktype == "physical":
            top_layout.addWidget(QLabel("起始 ATK："))
        elif atktype == "d_b":
            top_layout.addWidget(QLabel("起始 ATK："))
        else:
            top_layout.addWidget(QLabel("起始 MATK："))

        self.matk_input = QSpinBox()
        self.matk_input.setRange(-10_000_000, 10_000_000)
        #self.matk_input.setValue(4266)
        self.matk_input.setValue(matk)
        self.matk_input.valueChanged.connect(self.calculate)
        top_layout.addWidget(self.matk_input)

        top_layout.addStretch(1)
        self.calc_btn = QPushButton("計算 / 重算")
        self.calc_btn.clicked.connect(self.calculate)
        top_layout.addWidget(self.calc_btn)

        left.addWidget(top_bar)

        hint = QLabel("🖱️ 直接拖曳排序")
        hint.setStyleSheet("opacity: 0.75;")
        left.addWidget(hint)

        # ListView + Model（關鍵：setAnimated(True)）
        self.view = LiveReorderListView()

        self.view.setProperty("animated", True)  # ✅ 拖曳/移動動畫
        self.view.setDragEnabled(True)
        self.view.setAcceptDrops(True)
        self.view.setDropIndicatorShown(True)
        self.view.setDefaultDropAction(Qt.MoveAction)
        self.view.setDragDropMode(QListView.InternalMove)
        self.view.setSelectionMode(QListView.SingleSelection)

        #self.model = StepModel([Step(n, f, "INT", 0.0) for n, f in initial_steps])
        if steps is None:
            self.model = StepModel(
                [Step(n, f, "INT", 0.0) for n, f in initial_steps]
            )
        else:
            #print(steps)
            self.model = StepModel([Step(n, f, "INT", 0.0) for n, f , *_ in steps])
        self.view.setModel(self.model)

        self.delegate = StepDelegate(self.view)
        self.view.setItemDelegate(self.delegate)

        # 拖曳後自動重算（rowsMoved 是 model 已經 moveRows 後的訊號）
        self.model.rowsMoved.connect(lambda *args: self.calculate())

        # 改 mode 後重算
        def on_model_data_changed(topLeft, bottomRight, roles):
            # roles 可能是 [] 或 None，所以要兼容
            if roles and (Qt.EditRole in roles):
                self.calculate()

        self.model.dataChanged.connect(on_model_data_changed)


        left.addWidget(self.view, 1)

        # 右邊 log
        right = QVBoxLayout()
        #root.addLayout(right, 1)

        #right.addWidget(QLabel("計算過程："))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        #right.addWidget(self.output, 1)

        self.calculate()

    def set_data(self, matk: int, steps):
        """外部更新資料用（matk + steps）"""
        self.matk_input.setValue(int(matk))

        # steps 用 tuple list：[(name, factor), ...]
        new_steps = [Step(n, f, "INT", 0.0) for (n, f) in steps]

        self.model.steps = new_steps
        self.model.layoutChanged.emit()

        self.calculate()

    def calculate(self):
        if getattr(self, "_in_calculate", False):
            return
        self._in_calculate = True
        try:
            val = float(self.matk_input.value())
            lines = [f"起始 MATK: {fmt(val)}"]

            results = []
            for s in self.model.steps:
                new_val = apply_round(val, s.factor, s.mode, s.name)
                results.append(new_val)

                if s.name in ("MDEF減算","DEF減算"):
                    lines.append(
                        f"{s.name} -{s.factor} [{s.mode}] → {fmt(new_val)}"
                    )
                else:
                    lines.append(
                        f"{s.name} ×{s.factor} [{s.mode}] → {fmt(new_val)}"
                    )
                val = new_val

            # ✅ 更新列表結果（這會 emit dataChanged，但不會再遞迴了）
            self.model.set_results(results)

            lines.append(f"\n🎯 最終傷害：{fmt(val)}")
            self.output.setPlainText("\n".join(lines))
        finally:
            self._in_calculate = False



if __name__ == "__main__":
    app = QApplication(sys.argv)
    #w = DamageCalculator()
    #w.show()
    sys.exit(app.exec())
