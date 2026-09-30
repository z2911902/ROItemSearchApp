import sys
import re
from collections import defaultdict
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QFileDialog, QLabel,
    QTreeWidget, QTreeWidgetItem, QHBoxLayout, QCheckBox, QProgressBar,
    QTableView, QSplitter, QAbstractItemView, QScrollBar, QSlider, QSizePolicy
)
from PySide6.QtCore import QObject, QThread, Signal, QAbstractTableModel, QModelIndex, QRectF
import time
import math
import colorsys
import bisect
import struct
from PySide6.QtCore import Qt
import os
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from PySide6.QtGui import QFontMetrics
import mplcursors
from PySide6.QtWidgets import QComboBox
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QSpinBox
from PySide6.QtGui import QColor, QPainter, QImage, QPen, QBrush
from PySide6.QtGui import QGuiApplication, QClipboard
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from PySide6.QtWidgets import QMessageBox
import threading
import multiprocessing as mp
import queue
from PySide6.QtWidgets import QHeaderView
from collections import defaultdict
from matplotlib.ticker import FuncFormatter, MultipleLocator
from matplotlib.widgets import SpanSelector
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
font_path = r"C:\Windows\Fonts\msjh.ttc"  # 微軟正黑體
from PySide6.QtGui import QKeySequence, QAction
from PySide6.QtWidgets import QMenu

# Pure-Python RRF parser: no RagnarokReplayExample.exe / copy.txt required.
from rrf_reader import RRFIncrementalReader

font = FontProperties(fname=font_path)
import traceback
plt.rcParams['font.family'] = font.get_name()
plt.rcParams['font.sans-serif'] = [font.get_name()]
plt.rcParams['axes.unicode_minus'] = False

import csv
SHOW_UNKNOWN_COUPLESTATUS = False  # True=顯示未知能力ID, False=隱藏不顯示
# 沒對應到 PAR_CHANGE_STAT_MAP 時，要不要顯示
SHOW_UNKNOWN_PAR_CHANGE = False  # True=顯示未知, False=隱藏

DROP_MATCH_TOLERANCE_MS = 20  

# 物品名稱高亮規則：key = 關鍵字/完整名稱, value = 底色
DROP_ITEM_HIGHLIGHT_MAP = {    
    1190: "#9999FF",#紫光
    1186: "#FF44AA",#卡片粉紅光
    1869: "#33CCFF",#裝備藍光
    1870: "#9999FF",#符文紫光
    1871: "#9999FF",#鑽石紫光
    2371: "#33CCFF",#原石類
    2372: "#33CCFF",#原石類
}
#要隱藏的狀態ID不顯示在歷程上
buffid = {46,49,89,112,131,665,993,1061}
#49 每次都會跟霸鞋一起消失，傷害比相同傷害之前少很多，可能是耐久度龜0或是最後一下?
#131 應該是怒爆或是致毒給的隱藏效果。
#993 好像是信件狀態?


COUPLESTATUS_STAT_MAP = {
    0x0D: "STR", 0x0E: "AGI", 0x0F: "VIT", 0x10: "INT", 0x11: "DEX", 0x12: "LUK",
    0xDB: "POW", 0xDC: "STA", 0xDD: "WIS", 0xDE: "SPL", 0xDF: "CON", 0xE0: "CRT",
}

PAR_CHANGE_STAT_MAP = {
    0x00: "移動速度",
    0x05: "HP",
    0x06: "MaxHP",
    0x07: "SP",
    0x08: "MaxSP",
    0x29: "前ATK",
    0x2A: "後ATK",
    0x2B: "後MATK",
    0x2C: "前MATK",
    0x2D: "前DEF",
    0x2E: "後DEF",        
    0x2F: "前MDEF",
    0x30: "後MDEF",
    0x31: "Hit",
    0xE1: "P.ATK",
    0xE2: "S.MATK",
    0xE3: "RES",
    0xE4: "MRES",
    0xE5: "H.PLUS",
    0xE6: "C.RATE",
    0xE8: "AP",
    0xE9: "MaxAP",
    0x32: "FLEE",
    0x34: "CRI",   

}


STAT_SKILL_NAMES = {"面板能力變動", "素質能力變動"}

FILTER_ALL = "全部"
FILTER_ALL_WITH_STAT = "全部(包含能力變動)"

# 普攻副手傷害使用的內部虛擬技能 ID。
# 必須和主手普攻(skill_id=0)分開，否則技能統計會把左右手重新合併。
NORMAL_ATTACK_LEFT_SKILL_ID = -1

skill_name_map = {}
item_name_map = {}
# === 手動對應錯誤或缺失的技能 ID ===
skill_display_map = {#左對應右
    2215: 2214,
    5219: 5218,
    5223: 5222,
    # 更多可自行擴充
}

# 變身維持秒數（單位：秒），key 用 monsterskin
# 例：3108 這種變身模式會維持 5 秒
TRANSFORM_DURATION_MAP = {
    3108: 5,#gt8
    1930: 7,#兔包
    # 之後要再補其他 monsterskin 就加在這裡
}

sid_groundskill_cache = {}   # key = sid, value = groundskill data

try:
    with open("data\\skillneme.csv", "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) >= 3:
                try:
                    skill_id = int(row[0])
                    skill_name = row[2]   # 第3欄是中文名稱
                    skill_name_map[skill_id] = skill_name
                except:
                    pass
except FileNotFoundError:
    skill_name_map = {}

def parse_lub_file(filename):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            content = file.read()
    except FileNotFoundError:
        return {}

    item_entries = re.findall(
        r"\[(\d+)\]\s*=\s*{(.*?)}(?=,\s*\[\d+\]|\s*$)",
        content,
        re.DOTALL
    )

    parsed_items = {}

    for item_id, body in item_entries:
        name_match = re.search(r'\bidentifiedDisplayName\b\s*=\s*"([^"]+)"', body)
        effect_match = re.search(r'\bEffectID\b\s*=\s*(\d+)', body)

        if name_match:
            parsed_items[int(item_id)] = {
                "name": name_match.group(1).strip(),
                "EffectID": int(effect_match.group(1)) if effect_match else None
            }

    return parsed_items


parsed_lub_items = parse_lub_file("data\\iteminfo_new.lua")
item_name_map = {item_id: data["name"] for item_id, data in parsed_lub_items.items()}
item_effect_map = {item_id: data["EffectID"] for item_id, data in parsed_lub_items.items()}

class MyNavigationToolbar(NavigationToolbar):
    def __init__(self, canvas, parent=None):
        super().__init__(canvas, parent)
        self._right_pan = False  # 是否正在右鍵拖曳

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self._right_pan = True
            self._pan_start(event)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._right_pan:
            self._pan_motion(event)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._right_pan:
            self._right_pan = False
            self._pan_end(event)
            return
        super().mouseReleaseEvent(event)


class LeftButtonPan:
    def __init__(self, canvas, toolbar):
        self.canvas = canvas
        self.toolbar = toolbar
        self.is_panning = False
        self.enabled = True

        # 綁定 canvas 事件
        canvas.mpl_connect("button_press_event", self.on_press)
        canvas.mpl_connect("motion_notify_event", self.on_move)
        canvas.mpl_connect("button_release_event", self.on_release)

    def on_press(self, event):
        if not self.enabled:
            return
        if event.button == 1 and event.inaxes:
            self.is_panning = True
            # Matplotlib 3.8 新名稱：press_pan
            self.toolbar.press_pan(event)

    def on_move(self, event):
        if not self.enabled:
            return
        if self.is_panning:
            # Matplotlib 3.8 新名稱：drag_pan
            self.toolbar.drag_pan(event)

    def on_release(self, event):
        if not self.enabled:
            self.is_panning = False
            return
        if event.button == 1 and self.is_panning:
            # Matplotlib 3.8 新名稱：release_pan
            self.toolbar.release_pan(event)
            self.is_panning = False


class DamageHUD(QWidget):
    """可拖曳・自動依內容縮放・右對齊數字・DPS 千分位整數"""
    def __init__(self):
        super().__init__()

        self.setWindowTitle("DPS HUD")
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.CustomizeWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        # ------- 背景 -------
        bg = QWidget()
        bg.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 20, 20, 180);
                border: 1px solid rgba(255, 255, 255, 50);
                border-radius: 4;
            }
            QTableWidget {
                font-size: 12px;
            }
            QHeaderView::section {
                font-size: 12px;
            }
            QTableWidget::item { padding-right: 4px; }
        """)
 
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(bg)

        # ------- 表格 -------
        self.table = QTableWidget(2, 3)
        self.table.setHorizontalHeaderLabels(["角色", "總傷害", "DPS(5秒平均)"])
        # 隱藏卷軸
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)


        bg_layout = QVBoxLayout(bg)
        bg_layout.setContentsMargins(6, 6, 6, 6)
        bg_layout.addWidget(self.table)

        self.drag_pos = None
        self.adjustSize()
        self.set_default_position()  
        self.show()

    def set_default_position(self):
        """HUD 預設顯示在螢幕中央上方。"""
        screen = QGuiApplication.primaryScreen().geometry()
        hud_w = self.width()
        hud_h = self.height()

        # 中央上方的位置
        x = (screen.width() - hud_w) // 2
        y = 0   # 距離上方 50px，可依喜好調整

        self.move(x, y)


    # ===========================
    #      滑鼠拖曳 HUD
    # ===========================
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.drag_pos:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

    # ===========================
    #  自動依內容縮放 HUD
    # ===========================
    def auto_resize(self, rows):
        """rows = 實際要顯示的行數"""
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

        # 計算寬度
        width = self.table.verticalHeader().width()
        for col in range(self.table.columnCount()):
            width += self.table.columnWidth(col)
        width += 22  # padding

        # 計算高度只顯示 row 數
        header_h = self.table.horizontalHeader().height()
        row_h = sum(self.table.rowHeight(i) for i in range(rows))

        height = header_h + row_h + 30  # padding 微調

        self.setFixedSize(width, height)

    # ===========================
    #        更新 HUD
    # ===========================
    def update_hud(self, top5):
        actual_rows = len(top5)

        for row in range(5):
            if row < actual_rows:
                r = top5[row]

                # --- 角色名稱後加兩格 ---
                name_display = r["name"] + "  "
                item_name = QTableWidgetItem(name_display)
                item_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)

                # --- 總傷害（千分位 + 兩格空白） ---
                total_display = "  " + f"{r['total']:,}"
                item_total = QTableWidgetItem(total_display)
                item_total.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                # --- DPS（整數千分位 + 兩格空白） ---
                dps_int = int(round(r["dps"]))
                dps_display = "  " + f"{dps_int:,}"
                item_dps = QTableWidgetItem(dps_display)
                item_dps.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                self.table.setItem(row, 0, item_name)
                self.table.setItem(row, 1, item_total)
                self.table.setItem(row, 2, item_dps)

            else:
                # 清空不用的行
                self.table.setItem(row, 0, QTableWidgetItem(""))
                self.table.setItem(row, 1, QTableWidgetItem(""))
                self.table.setItem(row, 2, QTableWidgetItem(""))

        # 高度依實際行數縮放
        rows_to_show = max(1, actual_rows)
        self.auto_resize(rows_to_show)

    def clear_hud(self):
        """清空 HUD 內容並縮到最小高度（1 行）"""
        for row in range(5):
            self.table.setItem(row, 0, QTableWidgetItem(""))
            self.table.setItem(row, 1, QTableWidgetItem(""))
            self.table.setItem(row, 2, QTableWidgetItem(""))

        # 強制縮到一行高度
        self.auto_resize(rows=1)





class RRFWorker(QObject):
    finished = Signal(dict)       # 成功解析後回傳 raw ReplayDelta
    failed = Signal(str)
    start_time = Signal(float)
    status_msg = Signal(dict)

    def __init__(self, rrf_path, reader):
        super().__init__()
        self.rrf_path = rrf_path
        self.reader = reader
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        if not self.running:
            return

        real_t0 = time.time()
        self.start_time.emit(real_t0)
        self.status_msg.emit({
            "status": "直接解析 RRF raw packet...",
            "progressbar": 5,
        })

        try:
            t0 = time.perf_counter()
            delta = self.reader.poll()
            elapsed = time.perf_counter() - t0

            if not self.running:
                return

            print(
                f"[RRF raw] mode={delta.mode}, new_packets={len(delta.packets)}, "
                f"reason={delta.reason}, 耗時 {elapsed:.3f} 秒"
            )
            self.finished.emit({
                "delta": delta,
                "elapsed": elapsed,
            })
            self.status_msg.emit({
                "status": "RRF raw 解析完成！",
                "progressbar": 20,
            })
        except Exception as e:
            self.failed.emit(str(e))


class RRFBackgroundWorker(QObject):
    """舊版相容殼。

    raw 版不再需要背景持續產生 copy.txt；真正更新由既有 auto_timer
    觸發 RRFWorker.poll()。保留類別只是避免舊 UI 呼叫點出錯。
    """
    progress = Signal(float)
    finished = Signal(str)

    def __init__(self, rrf_path):
        super().__init__()
        self.rrf_path = rrf_path
        self.running = True
        self.block = False

    def stop(self):
        self.running = False

    def run(self):
        # 不做任何 copy / subprocess；背景 EXE 轉檔已停用。
        self.running = False


def timestamp_to_sec_key(ts):
    # "+00:00:26:564" -> (0, 0, 26)
    h, m, s, ms = map(int, ts[1:].split(":"))
    return (h, m, s)




# 封包框架：共用
PACKET_BLOCK_RE = re.compile(
    r'\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+(\w+)\s*'
    r'\[0x[0-9A-Fa-f]+\s+\((\d+)\)\]\s*(.*?)^\}',
    re.MULTILINE | re.DOTALL
)

# 抓單行 HEX（新版 C# hexdump）
SINGLE_HEX_RE = re.compile(
    r'\[0x[0-9A-Fa-f]+\s+\(\d+\)\]\s*([0-9A-Fa-f]+)'
)

def extract_hex_from_block(block: str, size: int):
    """ 從單行 hex 中抽取完整 byte 清單 """
    m = SINGLE_HEX_RE.search(block)
    if not m:
        return []

    hexstr = m.group(1)  # 連續 HEX 字串

    # 每兩個字切一 byte
    return [hexstr[i:i+2] for i in range(0, len(hexstr), 2)][:size]


# ============================================================
# 工具：Little-endian 解碼
# ============================================================
def le_int(bs):
    if not bs:
        return 0
    return int("".join(reversed(bs)), 16)


def le_sint(bs):
    """Little-endian signed integer. Empty input returns 0."""
    if not bs:
        return 0
    raw = bytes(int(x, 16) for x in bs)
    return int.from_bytes(raw, byteorder="little", signed=True)


def _u8(h, off, default=0):
    return int(h[off], 16) if len(h) > off else default


def _u16(h, off, default=0):
    return le_int(h[off:off + 2]) if len(h) >= off + 2 else default


def _i16(h, off, default=0):
    return le_sint(h[off:off + 2]) if len(h) >= off + 2 else default


def _u32(h, off, default=0):
    return le_int(h[off:off + 4]) if len(h) >= off + 4 else default


def _i32(h, off, default=0):
    return le_sint(h[off:off + 4]) if len(h) >= off + 4 else default


def _packet_meta(hex_bytes):
    packet_id = _u16(hex_bytes, 0)
    return {
        "packet_id": packet_id,
        "packet_id_hex": f"0x{packet_id:04X}",
        "packet_size": len(hex_bytes),
        "raw_hex": " ".join(hex_bytes),
    }


def _decode_pos_dir(data):
    """Decode Ragnarok 3-byte packed position/direction."""
    if len(data) < 3:
        return {"x": 0, "y": 0, "dir": 0, "raw": " ".join(data)}
    p0, p1, p2 = (int(x, 16) for x in data[:3])
    x = (p0 << 2) | (p1 >> 6)
    y = ((p1 & 0x3F) << 4) | (p2 >> 4)
    direction = p2 & 0x0F
    return {"x": x, "y": y, "dir": direction, "raw": " ".join(data[:3])}


def _decode_move_data(data):
    """Decode Ragnarok 6-byte packed from/to movement coordinates."""
    if len(data) < 6:
        return {
            "from_x": 0, "from_y": 0, "to_x": 0, "to_y": 0,
            "sub_x": 0, "sub_y": 0, "raw": " ".join(data),
        }
    p = [int(x, 16) for x in data[:6]]
    from_x = (p[0] << 2) | (p[1] >> 6)
    from_y = ((p[1] & 0x3F) << 4) | (p[2] >> 4)
    to_x = ((p[2] & 0x0F) << 6) | (p[3] >> 2)
    to_y = ((p[3] & 0x03) << 8) | p[4]
    return {
        "from_x": from_x,
        "from_y": from_y,
        "to_x": to_x,
        "to_y": to_y,
        "sub_x": (p[5] >> 4) & 0x0F,
        "sub_y": p[5] & 0x0F,
        "raw": " ".join(data[:6]),
    }


# ============================================================
# EFST 狀態名稱解析
# 共用 extract_efstinfo_values 的資料結構：
#   id          = 數字狀態 ID
#   name        = stateiconinfo.lua 中 COLOR_TITLE_BUFF 的顯示名稱
#   efst_name   = EFSTIDs.lua 中的 EFST_* 常數名
#   descript    = stateiconinfo.lua 的描述文字
# ============================================================
_EFST_METADATA_CACHE = {}


def _read_text_auto(path):
    """依常見編碼讀取 Lua / replay 文字檔。"""
    for enc in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except FileNotFoundError:
            return ""

    try:
        with open(path, "r", encoding="big5", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _extract_lua_brace_block(text, start_brace_idx):
    """從指定的 { 開始，取出完整 Lua table，會略過字串內的大括號。"""
    depth = 0
    in_string = False
    escape = False

    for i in range(start_brace_idx, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start_brace_idx:i + 1]

    return None


def _clean_lua_string(value):
    """只處理 stateiconinfo 常見跳脫，不對中文做 unicode_escape。"""
    return (
        value
        .replace(r'\"', '"')
        .replace(r'\n', '\n')
        .replace(r'\t', '\t')
        .replace(r'\\', '\\')
        .strip()
    )


def _extract_dump_hex_bytes(block):
    """只抓 hexdump 地址欄後面的 byte，遇到 ASCII 欄立即停止。"""
    hex_list = []
    for line in block.splitlines():
        maddr = re.match(r'^\s*[0-9A-Fa-f]{4,}\s+(.*)$', line)
        if not maddr:
            continue

        for token in maddr.group(1).split():
            if re.fullmatch(r'[0-9A-Fa-f]{2}', token):
                hex_list.append(token)
            else:
                break
    return hex_list


def _load_efst_metadata(efst_ids_path="data/EFSTIDs.lua",
                        stateiconinfo_path="data/stateiconinfo.lua"):
    """建立狀態 ID -> COLOR_TITLE_BUFF 名稱/EFST 常數/描述的對照表。"""
    abs_ids = os.path.abspath(efst_ids_path)
    abs_icons = os.path.abspath(stateiconinfo_path)

    try:
        ids_mtime = os.path.getmtime(abs_ids)
    except OSError:
        ids_mtime = None
    try:
        icons_mtime = os.path.getmtime(abs_icons)
    except OSError:
        icons_mtime = None

    cache_key = (abs_ids, ids_mtime, abs_icons, icons_mtime)
    cached = _EFST_METADATA_CACHE.get(cache_key)
    if cached is not None:
        return cached

    efst_ids_content = _read_text_auto(abs_ids)
    stateicon_content = _read_text_auto(abs_icons)

    id_to_efst_name = {}
    efst_name_to_id = {}
    for efst_name, num in re.findall(
        r'\b(EFST_[A-Z0-9_]+)\s*=\s*(\d+)\s*,?',
        efst_ids_content
    ):
        status_id = int(num)
        id_to_efst_name[status_id] = efst_name
        efst_name_to_id[efst_name] = status_id

    metadata = {
        status_id: {
            "id": status_id,
            # 只有 stateiconinfo.lua 的 COLOR_TITLE_BUFF 才算顯示名稱。
            # 找不到標題時保持空字串，UI 僅顯示狀態 ID。
            "name": "",
            "efst_name": efst_name,
            "descript": [],
        }
        for status_id, efst_name in id_to_efst_name.items()
    }

    entry_pattern = re.compile(
        r'StateIconList\[EFST_IDs\.(EFST_[A-Z0-9_]+)\]\s*=\s*\{'
    )
    row_pattern = re.compile(
        r'\{\s*"((?:\\.|[^"\\])*)"\s*(?:,\s*([A-Z0-9_]+))?'
    )

    for match in entry_pattern.finditer(stateicon_content):
        efst_name = match.group(1)
        status_id = efst_name_to_id.get(efst_name)
        if status_id is None:
            continue

        table_block = _extract_lua_brace_block(stateicon_content, match.end() - 1)
        if not table_block:
            continue

        desc_match = re.search(r'\bdescript\s*=\s*\{', table_block)
        if not desc_match:
            continue

        desc_block = _extract_lua_brace_block(table_block, desc_match.end() - 1)
        if not desc_block:
            continue

        title = None
        descriptions = []
        for raw_text, color_token in row_pattern.findall(desc_block):
            line = _clean_lua_string(raw_text)
            if not line or line == "%s":
                continue

            descriptions.append(line)
            if color_token in ("COLOR_TITLE_BUFF","COLOR_TITLE_DEBUFF") and title is None:
                title = line

        info = metadata[status_id]
        info["descript"] = descriptions
        if title:
            info["name"] = title

    # 清掉同路徑的舊 mtime 快取，避免資料檔重載後累積。
    for old_key in list(_EFST_METADATA_CACHE):
        if old_key[0] == abs_ids and old_key[2] == abs_icons:
            del _EFST_METADATA_CACHE[old_key]
    _EFST_METADATA_CACHE[cache_key] = metadata
    return metadata


def extract_efstinfo_values(filepath=None,
                            efst_ids_path="data/EFSTIDs.lua",
                            stateiconinfo_path="data/stateiconinfo.lua",
                            *,
                            content=None,
                            include_status_changes=False):
    """
    解析 replay 中出現的 EFST ID，並回傳 COLOR_TITLE_BUFF 顯示名稱。

    content 可直接傳目前增量文字；未傳時才從 filepath 讀取。
    include_status_changes=True 時，另外納入：
      HEADER_ZC_MSG_STATE_CHANGE2（開始）
      HEADER_ZC_MSG_STATE_CHANGE（結束）
    這裡只建立 ID -> 名稱對照，不改變事件的開始/結束語意。
    """
    metadata = _load_efst_metadata(efst_ids_path, stateiconinfo_path)

    if content is None:
        if not filepath:
            return []
        content = _read_text_auto(filepath)

    results = []
    seen_ids = set()

    def append_unique(status_id):
        if status_id in seen_ids:
            return
        seen_ids.add(status_id)

        info = metadata.get(status_id)
        if info is None:
            efst_name = f"UNKNOWN_EFST_{status_id}"
            info = {
                "id": status_id,
                "name": "",
                "efst_name": efst_name,
                "descript": [],
            }
        results.append(dict(info))

    # 角色自己的 AID，供既有 STATE_CHANGE3 篩選使用。
    player_aid_hex = None
    aid_match = re.search(
        r"\[Chunk Session\] Unparsed opcode Aid, Length=4"
        r"[\s\S]*?\{([^}]*)\}",
        content,
        re.DOTALL,
    )
    if aid_match:
        aid_hex_list = _extract_dump_hex_bytes(aid_match.group(1))
        if len(aid_hex_list) >= 4:
            player_aid_hex = ''.join(x.lower() for x in aid_hex_list[:4])

    # 原本的 EfstInfo：前 2 bytes 是狀態 ID（little-endian）。
    efstinfo_matches = re.findall(
        r"\[Chunk [^\]]+\] Unparsed opcode EfstInfo, Length=\d+"
        r"[\s\S]*?\{([^}]*)\}",
        content,
        re.DOTALL,
    )
    for block in efstinfo_matches:
        hex_list = _extract_dump_hex_bytes(block)
        if len(hex_list) >= 2:
            append_unique(le_int(hex_list[0:2]))

    # 既有 STATE_CHANGE3：83 09 後 2 bytes 為狀態 ID，後 4 bytes 為 AID。
    if player_aid_hex:
        state3_matches = re.findall(
            r"packet\s+HEADER_ZC_MSG_STATE_CHANGE3"
            r"[\s\S]*?\{([^}]*)\}",
            content,
            re.DOTALL,
        )
        for block in state3_matches:
            hex_list = _extract_dump_hex_bytes(block)
            if len(hex_list) < 8:
                continue

            for i in range(len(hex_list) - 7):
                if hex_list[i:i + 2] != ["83", "09"] and [x.lower() for x in hex_list[i:i + 2]] != ["83", "09"]:
                    continue

                status_id = le_int(hex_list[i + 2:i + 4])
                caster_aid_hex = ''.join(x.lower() for x in hex_list[i + 4:i + 8])
                if caster_aid_hex == player_aid_hex:
                    append_unique(status_id)
                    break

    # 新的一般狀態封包：狀態 ID 固定在 [2:4]。
    if include_status_changes:
        status_pattern = re.compile(
            r'^\[(?:\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+'
            r'(?:HEADER_ZC_MSG_STATE_CHANGE2|HEADER_ZC_MSG_STATE_CHANGE)\s*$'
            r'\s*^\[0x[0-9A-Fa-f]+\s+\(\d+\)\]\s*\{\s*$'
            r'([\s\S]*?)^\}',
            re.MULTILINE,
        )
        for block in status_pattern.findall(content):
            hex_list = _extract_dump_hex_bytes(block)
            if len(hex_list) >= 4:
                append_unique(le_int(hex_list[2:4]))

    return results

# ============================================================
# 解析 [Chunk ReplayData] Unparsed opcode Charactername
# 取得：角色名稱（Big5 / cp950）
# ============================================================
def parse_replaydata_charactername(text):
    """
    回傳第一個找到的角色名稱字串，找不到回傳 None
    """
    pattern = re.compile(
        r'\[Chunk ReplayData\]\s+Unparsed opcode Charactername,[\s\S]*?'
        r'Raw hex:\s*\[0x[0-9A-Fa-f]+\s*\(\d+\)\]\s*\{\s*\n'
        r'([\s\S]*?)^}',           # 抓到這個 { ... } block
        re.MULTILINE
    )

    m = pattern.search(text)
    if not m:
        return None

    block = m.group(1)
    hex_bytes = re.findall(r'\b([0-9A-Fa-f]{2})\b', block)

    # 從第一個 byte 開始，抓到遇到 00 為止
    name_raw_bytes = []
    for h in hex_bytes:
        if h == '00':
            break
        name_raw_bytes.append(int(h, 16))

    raw = bytes(name_raw_bytes)

    # 這裡用 Big5 / cp950 解碼
    name = None
    for enc in ("cp950", "big5", "utf-8"):
        try:
            name = raw.decode(enc)
            break
        except Exception:
            continue

    if name is None:
        name = raw.decode("cp950", errors="replace")

    # debug 用
    #print(f"[ReplayData] Charactername = {name!r}")
    return name

def _decode_replaydata_mapname_block(block):
    hex_bytes = re.findall(r'\b([0-9A-Fa-f]{2})\b', block)
    name_raw_bytes = []
    for h in hex_bytes:
        if h == '00':
            break
        name_raw_bytes.append(int(h, 16))

    if not name_raw_bytes:
        return None

    raw = bytes(name_raw_bytes)
    try:
        return raw.decode("ascii")
    except Exception:
        return raw.decode("ascii", errors="replace")


def parse_replaydata_mapname(text):
    """回傳這段資料中最後一個 Mapname；切圖 replay 會以最新地圖為準。"""
    pattern = re.compile(
        r'\[Chunk ReplayData\]\s+Unparsed opcode Mapname,[\s\S]*?'
        r'Raw hex:\s*\[0x[0-9A-Fa-f]+\s*\(\d+\)\]\s*\{\s*\n'
        r'([\s\S]*?)^}',
        re.MULTILINE
    )

    matches = list(pattern.finditer(text))
    if not matches:
        return None
    return _decode_replaydata_mapname_block(matches[-1].group(1))


def parse_replaydata_map_changes(text):
    """
    解析 ReplayData 裡所有 Mapname，建立可供全域時間軸使用的地圖切換事件。

    Mapname metadata 本身通常沒有 [+hh:mm:ss:ms]，因此切圖時間以該 Mapname
    之後第一個 packet 的時間為準；若後面沒有 packet，則退回前一個 packet 時間。
    初始地圖沒有前置 packet 時視為 0 秒。
    """
    map_pattern = re.compile(
        r'\[Chunk ReplayData\]\s+Unparsed opcode Mapname,[\s\S]*?'
        r'Raw hex:\s*\[0x[0-9A-Fa-f]+\s*\(\d+\)\]\s*\{\s*\n'
        r'([\s\S]*?)^}',
        re.MULTILINE
    )
    packet_time_re = re.compile(
        r'^\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+',
        re.MULTILINE,
    )

    matches = list(map_pattern.finditer(text))
    if not matches:
        return []

    results = []
    last_name = None
    for idx, m in enumerate(matches):
        map_name = _decode_replaydata_mapname_block(m.group(1))
        if not map_name:
            continue

        next_map_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        after_segment = text[m.end():next_map_pos]
        next_packet = packet_time_re.search(after_segment)

        if next_packet:
            timestamp = next_packet.group(1)
            sec = _packet_timestamp_to_seconds(timestamp)
        else:
            # 找 Mapname 之前最後一個 packet timestamp。
            prev_packets = list(packet_time_re.finditer(text[:m.start()]))
            if prev_packets:
                timestamp = prev_packets[-1].group(1)
                sec = _packet_timestamp_to_seconds(timestamp)
            else:
                timestamp = "+00:00:00:000"
                sec = 0.0

        # 同一段 legacy metadata 可能重複輸出相同 Mapname；連續相同地圖只留一次。
        if map_name == last_name:
            continue
        results.append({
            "time": sec,
            "timestamp": timestamp,
            "map_name": map_name,
            "kind": "map_change",
        })
        last_name = map_name

    return results

# ============================================================
# 解析 [Chunk Session] Unparsed opcode Aid
# 取得：sid (4 bytes, 小端序)
# ============================================================
def parse_session_gid(text):
    """
    回傳第一個找到的 sid (int)，找不到回傳 None
    """
    pattern = re.compile(
        r'\[Chunk Session\]\s+Unparsed opcode Aid,[\s\S]*?'
        r'Raw hex:\s*\[0x[0-9A-Fa-f]+\s*\(\d+\)\]\s*\{\s*\n'
        r'([\s\S]*?)^}',
        re.MULTILINE
    )

    m = pattern.search(text)
    if not m:
        return None

    block = m.group(1)
    hex_bytes = re.findall(r'\b([0-9A-Fa-f]{2})\b', block)

    # 只需要前 4 個 byte：例 66 F9 DC 32
    gid_bytes = hex_bytes[:4]

    # 用你現有的 le_int（小端序）轉成整數
    sid = le_int(gid_bytes)

    #print(f"[Session] Aid raw = {' '.join(gid_bytes)}, sid(int) = {sid}")
    return sid



# ============================================================
# 解析 GROUND SKILL 區塊
# ============================================================
def parse_groundskill_blocks(text):
    t0_ground = time.perf_counter()
    pattern = re.compile(
        r'\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+(HEADER_ZC_NOTIFY_GROUNDSKILL)\s*'
        r'\[\s*0x[0-9A-Fa-f]+\s+\((\d+)\)\]\s*'
        r'\{\s*\n([\s\S]*?)^\}\s*$',
        re.MULTILINE
    )

    results = []

    for t, packet_name, size, block in pattern.findall(text):
        # 只抓地址行後的 HEX，不抓 ASCII（完全跟 SKILL2 / ACT3 同邏輯）
        hex_bytes = []
        for line in block.splitlines():
            m = re.match(r'^\s*[0-9A-Fa-f]{4}\s+(.*)$', line)
            if m:
                for token in m.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', token):
                        hex_bytes.append(token)
                    else:
                        break   # 遇到 ASCII → 本行停止

        results.append({
            "timestamp": t,
            "type": "GROUND",
            "hex": hex_bytes[:int(size)]
        })
    t1_ground = time.perf_counter()
    print(f"[groundskill] 解析耗時: {(t1_ground - t0_ground) * 1000:.3f} ms")
    return results

    

    
# ============================================================
# 解析 GroupInfo 區塊
# ============================================================
def parse_groupinfo_blocks(text):
    pattern = re.compile(
        r'\[Chunk GroupAndFriends\]\s+Unparsed opcode GroupInfo,[\s\S]*?'
        r'\[0x[0-9A-Fa-f]+\s*\(\d+\)\]\s*\{\s*\n'   # [0x000003D8 (984)] {
        r'([\s\S]*?)^}',                             # 抓到結尾那一行單獨的 }
        re.MULTILINE
    )

    results = []

    for block in pattern.findall(text):
        # 只抓地址行後面的 HEX，不抓 ASCII（跟 SKILL2 相同邏輯）
        hex_bytes = []
        for line in block.splitlines():
            m = re.match(r'^\s*[0-9A-Fa-f]{4}\s+(.*)$', line)
            if m:
                for token in m.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', token):
                        hex_bytes.append(token)
                    else:
                        break  # 遇到 ASCII → 本行停止

        results.append({
            "type": "GROUPINFO",
            "hex": hex_bytes
        })

    return results
# ============================================================
# 解析 GroupInfo 區塊
# ============================================================
def parse_act3_blocks(text):
    t0_act3 = time.perf_counter()
    pattern = re.compile(
        r'\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+(HEADER_ZC_NOTIFY_ACT3)\s*'
        r'\[\s*0x[0-9A-Fa-f]+\s+\((\d+)\)\]\s*'
        r'\{\s*\n([\s\S]*?)^\}\s*$',
        re.MULTILINE
    )

    results = []

    for t, packet_name, size, block in pattern.findall(text):
        # 只抓地址行後面的 HEX，不抓 ASCII（跟 SKILL2 相同邏輯）
        hex_bytes = []
        for line in block.splitlines():
            m = re.match(r'^\s*[0-9A-Fa-f]{4}\s+(.*)$', line)
            if m:
                for token in m.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', token):
                        hex_bytes.append(token)
                    else:
                        break  # 遇到 ASCII → 本行停止

        results.append({
            "timestamp": t,
            "type": "ACT3",
            "hex": hex_bytes[:int(size)]
        })
    t1_act3 = time.perf_counter()
    print(f"[act3] 解析耗時: {(t1_act3 - t0_act3) * 1000:.3f} ms")
    return results


def split_groupinfo_members(hex_bytes):
    members = []
    current = []

    for i in range(0, len(hex_bytes), 1):
        # FB 00 開始新一段資料
        if i + 1 < len(hex_bytes) and hex_bytes[i] == 'FB' and hex_bytes[i+1] == '00':
            # 若已有舊資料 → 儲存
            if current:
                members.append(current)
            current = []

        current.append(hex_bytes[i])

    if current:
        members.append(current)

    return members
    

def decode_act3(hex_bytes):
    """完整解碼普通攻擊封包 0x02E1 / 0x08C8。"""
    parsed = _packet_meta(hex_bytes)
    parsed.update({
        "skill_id": 0,
        "skill_name": "普通攻擊",
        "sid": _u32(hex_bytes, 2),
        "source_aid": _u32(hex_bytes, 2),
        "did": _u32(hex_bytes, 6),
        "target_did": _u32(hex_bytes, 6),
        "start_time": _u32(hex_bytes, 10),
        "attack_mt": _i32(hex_bytes, 14),
        "attacked_mt": _i32(hex_bytes, 18),
        "damage": _i32(hex_bytes, 22),
        "level": 1,
    })
    # 舊 UI 欄位名稱維持相容，但改為完整 4-byte 值。
    parsed["skill_delay"] = parsed["attack_mt"]
    parsed["global_delay"] = parsed["attacked_mt"]

    if len(hex_bytes) >= 34:  # 0x08C8
        parsed.update({
            "layout": "0x08C8",
            "is_sp_damage": _u8(hex_bytes, 26),
            "hit_count": _i16(hex_bytes, 27),
            "attack_type": _u8(hex_bytes, 29),
            "action": _u8(hex_bytes, 29),
            "damage2": _i32(hex_bytes, 30),
            "left_damage": _i32(hex_bytes, 30),
        })
        consumed = 34
    elif len(hex_bytes) >= 33:  # 0x02E1
        parsed.update({
            "layout": "0x02E1",
            "is_sp_damage": 0,
            "hit_count": _i16(hex_bytes, 26),
            "attack_type": _u8(hex_bytes, 28),
            "action": _u8(hex_bytes, 28),
            "damage2": _i32(hex_bytes, 29),
            "left_damage": _i32(hex_bytes, 29),
        })
        consumed = 33
    else:
        parsed.update({
            "layout": "truncated",
            "is_sp_damage": 0,
            "hit_count": 1,
            "attack_type": 0,
            "action": 0,
            "damage2": 0,
            "left_damage": 0,
        })
        consumed = len(hex_bytes)

    if parsed["hit_count"] <= 0:
        parsed["hit_count"] = 1
    if len(hex_bytes) > consumed:
        parsed["unparsed_tail_hex"] = " ".join(hex_bytes[consumed:])
    return parsed

def decode_group_member(member_hex):
    # SID (23~26 小端序)
    sid = le_int(member_hex[22:26])

    # 名字 (73~直到第一個 00/控制碼)
    name_bytes = []
    i = 72
    while i < len(member_hex):
        b = int(member_hex[i], 16)
        if b < 0x20:
            break
        name_bytes.append(b)
        i += 1

    raw = bytes(name_bytes)

    # 依序嘗試幾種常見編碼
    name = None
    for enc in ("big5", "cp950", "utf-8"):
        try:
            name = raw.decode(enc)
            break
        except Exception:
            continue

    # 全部失敗就用 big5 + replace，避免完全解不出名字
    if name is None:
        name = raw.decode("big5", errors="replace")

    #print(f"[GroupInfo] SID={sid}  Name={name}")
    return {
        "sid": sid,
        "name": name,
    }

    
def parse_groupinfo(text):
    blocks = parse_groupinfo_blocks(text)
    results = []

    for blk in blocks:
        members = split_groupinfo_members(blk["hex"])
        for m in members:
            decoded = decode_group_member(m)
            results.append(decoded)

    return results
    
def build_sid_to_name_map(text):
    t0_groupinfo = time.perf_counter()
    # ① 先用 GroupInfo 把所有隊友 SID → 名稱 建好
    groupinfo = parse_groupinfo(text)
    mapping = {}

    for g in groupinfo:
        mapping[g["sid"]] = g["name"]

    # ② 再用 ReplayData + Session 多補一個「來源角色」的 SID
    char_name = parse_replaydata_charactername(text)
    gid_sid   = parse_session_gid(text)

    if char_name is not None and gid_sid is not None:
        # 若 GroupInfo 已經有這個 sid 就不要覆蓋，當後備方案用
        if gid_sid not in mapping:
            mapping[gid_sid] = char_name
            # 小 typo 修正：應該是 mapping[gid_sid]
            # mapping[gid_sid] = char_name
            print(f"[SID Map] from ReplayData/Session: {gid_sid} -> {char_name}")
    t1_groupinfo = time.perf_counter()
    print(f"[GroupInfo] 解析耗時: {(t1_groupinfo - t0_groupinfo) * 1000:.3f} ms")
    return mapping

# ============================================================
# 解碼 GROUND SKILL 的 SID
# ============================================================

def decode_groundskill(hex_bytes):
    """完整解碼 ZC_NOTIFY_GROUNDSKILL (0x0117, 18 bytes)."""
    parsed = _packet_meta(hex_bytes)
    parsed.update({
        "skill_id": _u16(hex_bytes, 2),
        "sid": _u32(hex_bytes, 4),       # AID / source id
        "aid": _u32(hex_bytes, 4),
        "level": _i16(hex_bytes, 8),
        "x": _i16(hex_bytes, 10),
        "y": _i16(hex_bytes, 12),
        "start_time": _u32(hex_bytes, 14),
    })
    if len(hex_bytes) > 18:
        parsed["unparsed_tail_hex"] = " ".join(hex_bytes[18:])
    return parsed

# ============================================================
# 解析變身封包：HEADER_ZC_MSG_STATE_CHANGE3 / HEADER_ZC_MSG_STATE_CHANGE
# 注意：必須精確比對封包名稱，避免把 STATE_CHANGE2 誤判成 STATE_CHANGE。
# ============================================================
def parse_statechange3_blocks(text: str):
    t0 = time.perf_counter()

    lines = text.splitlines()
    results = []
    packet_re = re.compile(
        r'^\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+'
        r'(HEADER_ZC_MSG_STATE_CHANGE3|HEADER_ZC_MSG_STATE_CHANGE)\s*$'
    )

    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()
        packet_match = packet_re.match(line)

        if not packet_match:
            i += 1
            continue

        timestamp, packet_name = packet_match.groups()
        packet_kind = "STATE3" if packet_name.endswith("STATE_CHANGE3") else "STATE"

        # 下一行是 size 行，例如：[0x00000009 (9)] {
        i += 1
        if i >= n:
            break

        size_match = SIZE_RE.search(lines[i])
        if not size_match:
            i += 1
            continue

        size = int(size_match.group(1))
        hex_bytes = []
        i += 1

        while i < n:
            line2 = lines[i].strip()
            if line2.startswith("}"):
                break

            maddr = re.match(r'^\s*[0-9A-Fa-f]{4}\s+(.*)$', line2)
            if maddr:
                for token in maddr.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', token):
                        hex_bytes.append(token)
                        if len(hex_bytes) >= size:
                            break
                    else:
                        break

            if len(hex_bytes) >= size:
                break
            i += 1

        results.append({
            "timestamp": timestamp,
            "packet_kind": packet_kind,  # STATE3 或 STATE
            "hex": hex_bytes[:size],
        })
        i += 1

    print(f"[STATE_CHANGE3/STATE] 解析到 {len(results)} 筆，耗時: {(time.perf_counter() - t0) * 1000:.3f} ms")
    return results


# ============================================================
# 解碼變身 STATE_CHANGE3 / STATE_CHANGE（既有功能）
# ============================================================

def decode_statechange3(hex_bytes):
    """完整解碼 0x0983 STATE_CHANGE3；亦相容 0x0196 STATE_CHANGE 結束包。"""
    parsed = _packet_meta(hex_bytes)
    parsed.update({
        "type": _u16(hex_bytes, 2),
        "status_id": _u16(hex_bytes, 2),
        "sid": _u32(hex_bytes, 4),
        "aid": _u32(hex_bytes, 4),
        "state": _u8(hex_bytes, 8),
        "total_ms": 0,
        "left_ms": 0,
        "val1": 0,
        "val2": 0,
        "val3": 0,
    })

    if len(hex_bytes) >= 29:  # 0x0983
        parsed.update({
            "total_ms": _u32(hex_bytes, 9),
            "left_ms": _u32(hex_bytes, 13),
            "val1": _i32(hex_bytes, 17),
            "val2": _i32(hex_bytes, 21),
            "val3": _i32(hex_bytes, 25),
        })
        consumed = 29
    elif len(hex_bytes) >= 25:  # 0x043F style fallback
        parsed.update({
            "left_ms": _u32(hex_bytes, 9),
            "val1": _i32(hex_bytes, 13),
            "val2": _i32(hex_bytes, 17),
            "val3": _i32(hex_bytes, 21),
        })
        consumed = 25
    else:  # 0x0196: id + AID + state
        consumed = min(len(hex_bytes), 9)

    parsed["monsterskin"] = parsed["val1"] if parsed["val1"] > 0 else 0
    if parsed["type"] == 665:
        parsed["transform_event"] = "start" if parsed["monsterskin"] > 0 else "end"
    else:
        parsed["transform_event"] = None

    parsed.update({
        "skill_id": 0,
        "skill_name": "外觀變更",
        "did": 0,
        "damage": 0,
        "level": 0,
        "hit_count": 0,
        "skill_delay": 0,
        "global_delay": 0,
    })
    if len(hex_bytes) > consumed:
        parsed["unparsed_tail_hex"] = " ".join(hex_bytes[consumed:])
    return parsed


# ============================================================
# 解析一般狀態封包
#   HEADER_ZC_MSG_STATE_CHANGE2 = 狀態開始
#   HEADER_ZC_MSG_STATE_CHANGE  = 狀態結束
#
# 封包欄位（兩者共通）：
#   [0:2] packet id
#   [2:4] status id，2 bytes little-endian
#   [4:7] did，3 bytes little-endian
# ============================================================
def parse_status_change_blocks(text: str):
    t0 = time.perf_counter()

    lines = text.splitlines()
    results = []
    packet_re = re.compile(
        r'^\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+'
        r'(HEADER_ZC_MSG_STATE_CHANGE2|HEADER_ZC_MSG_STATE_CHANGE)\s*$'
    )

    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()
        packet_match = packet_re.match(line)

        if not packet_match:
            i += 1
            continue

        timestamp, packet_name = packet_match.groups()
        packet_kind = "START" if packet_name.endswith("STATE_CHANGE2") else "END"

        i += 1
        if i >= n:
            break

        size_match = SIZE_RE.search(lines[i])
        if not size_match:
            i += 1
            continue

        size = int(size_match.group(1))
        hex_bytes = []
        i += 1

        while i < n:
            line2 = lines[i].strip()
            if line2.startswith("}"):
                break

            maddr = re.match(r'^\s*[0-9A-Fa-f]{4}\s+(.*)$', line2)
            if maddr:
                for token in maddr.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', token):
                        hex_bytes.append(token)
                        if len(hex_bytes) >= size:
                            break
                    else:
                        break

            if len(hex_bytes) >= size:
                break
            i += 1

        packet = hex_bytes[:size]
        if len(packet) >= 7:
            results.append({
                "timestamp": timestamp,
                "packet_kind": packet_kind,  # START / END
                "size": size,
                "hex": packet,
            })

        i += 1

    print(f"[STATUS_CHANGE2/STATE_CHANGE] 解析到 {len(results)} 筆，耗時: {(time.perf_counter() - t0) * 1000:.3f} ms")
    return results




def decode_status_change(hex_bytes, packet_kind):
    """完整解碼一般狀態開始/結束封包。"""
    parsed = _packet_meta(hex_bytes)
    parsed.update({
        "status_id": _u16(hex_bytes, 2),
        "did": _u32(hex_bytes, 4),
        "aid": _u32(hex_bytes, 4),
        "state": _u8(hex_bytes, 8),
        "total_ms": 0,
        "left_ms": 0,
        "val1": 0,
        "val2": 0,
        "val3": 0,
    })

    # 0x0983: index.W AID.L state.B total.L left.L val1.L val2.L val3.L
    if len(hex_bytes) >= 29:
        parsed.update({
            "total_ms": _u32(hex_bytes, 9),
            "left_ms": _u32(hex_bytes, 13),
            "val1": _i32(hex_bytes, 17),
            "val2": _i32(hex_bytes, 21),
            "val3": _i32(hex_bytes, 25),
        })
        consumed = 29
    # 0x043F: index.W AID.L state.B left.L val1.L val2.L val3.L
    elif len(hex_bytes) >= 25:
        parsed.update({
            "left_ms": _u32(hex_bytes, 9),
            "val1": _i32(hex_bytes, 13),
            "val2": _i32(hex_bytes, 17),
            "val3": _i32(hex_bytes, 21),
        })
        consumed = 25
    else:
        consumed = min(len(hex_bytes), 9)

    is_start = packet_kind == "START"
    parsed["status_event"] = "start" if is_start else "end"
    parsed["status_event_name"] = "狀態開始" if is_start else "狀態結束"
    if len(hex_bytes) > consumed:
        parsed["unparsed_tail_hex"] = " ".join(hex_bytes[consumed:])
    return parsed




def decode_vanish(hex_bytes):
    """完整解碼 ZC_NOTIFY_VANISH: packet id + GID + type."""
    parsed = _packet_meta(hex_bytes)
    mode = _u8(hex_bytes, 6)
    parsed.update({
        "did": _u32(hex_bytes, 2),
        "gid": _u32(hex_bytes, 2),
        "mode": mode,
        "mode_name": {
            0: "out_of_sight",
            1: "died",
            2: "logged_out",
            3: "teleport",
            4: "trickdead",
        }.get(mode, f"unknown_{mode}"),
    })
    if len(hex_bytes) > 7:
        parsed["unparsed_tail_hex"] = " ".join(hex_bytes[7:])
    return parsed

def parse_vanish_blocks(text: str):
    """解析所有 ZC_NOTIFY_VANISH；不再只保留死亡(mode=1)。"""
    lines = text.splitlines()
    results = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()
        if "packet HEADER_ZC_NOTIFY_VANISH" not in line:
            i += 1
            continue

        packet_pos = i
        timestamp = line.split("]")[0][1:]
        i += 1
        if i >= n:
            break
        m = SIZE_RE.search(lines[i])
        if not m:
            i += 1
            continue
        size = int(m.group(1))

        i += 1
        hex_bytes = []
        while i < n:
            line2 = lines[i].strip()
            if line2.startswith("}"):
                break
            maddr = re.match(r'^\s*[0-9A-Fa-f]{4}\s+(.*)$', line2)
            if maddr:
                for token in maddr.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', token):
                        hex_bytes.append(token)
                        if len(hex_bytes) >= size:
                            break
                    else:
                        break
            if len(hex_bytes) >= size:
                break
            i += 1

        packet = hex_bytes[:size]
        if len(packet) >= 7:
            dec = decode_vanish(packet)
            results.append({
                "timestamp": timestamp,
                "size": size,
                "hex": packet,
                "did": dec["did"],
                "mode": dec["mode"],
                "mode_name": dec["mode_name"],
                "packet_pos": packet_pos,
            })
        i += 1
    return results

def parse_itemdrop_blocks(text: str):
    t0 = time.perf_counter()
    lines = text.splitlines()
    results = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()
        if "packet HEADER_物品掉落" not in line:
            i += 1
            continue

        packet_pos = i   # ★ 記住這筆掉落封包位置
        timestamp = line.split("]")[0][1:]

        i += 1
        if i >= n:
            break

        m = SIZE_RE.search(lines[i])
        if not m:
            continue
        size = int(m.group(1))

        i += 1
        hex_bytes = []
        while i < n:
            line2 = lines[i].strip()
            if line2.startswith("}"):
                break

            maddr = re.match(r'^\s*[0-9A-Fa-f]{4}\s+(.*)$', line2)
            if maddr:
                for token in maddr.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', token):
                        hex_bytes.append(token)
                        if len(hex_bytes) >= size:
                            break
                    else:
                        break

            if len(hex_bytes) >= size:
                break
            i += 1

        packet = hex_bytes[:size]
        if len(packet) >= 24 and packet[0:2] == ['DD', '0A']:
            results.append({
                "timestamp": timestamp,
                "size": size,
                "hex": packet,
                "packet_pos": packet_pos,   # ★ 新增
            })

        i += 1

    print(f"[itemdrop] 解析到 {len(results)} 筆，耗時: {(time.perf_counter() - t0) * 1000:.3f} ms")
    return results


def decode_itemdrop(hex_bytes):
    """完整解碼 0x0ADD ZC_ITEM_FALL_ENTRY4（目前 HEADER_物品掉落）。"""
    parsed = _packet_meta(hex_bytes)
    parsed.update({
        "item_aid": _u32(hex_bytes, 2),
        "item_id": _u32(hex_bytes, 6),
        "item_type": _u16(hex_bytes, 10),
        "is_identified": _u8(hex_bytes, 12),
        "x": _i16(hex_bytes, 13),
        "y": _i16(hex_bytes, 15),
        "sub_x": _u8(hex_bytes, 17),
        "sub_y": _u8(hex_bytes, 18),
        "amount": _i16(hex_bytes, 19),
        "show_drop_effect": _u8(hex_bytes, 21),
        "drop_effect_mode": _i16(hex_bytes, 22),
    })
    if len(hex_bytes) > 24:
        parsed["unparsed_tail_hex"] = " ".join(hex_bytes[24:])
    return parsed





# ============================================================
# 解析 HEADER_ZC_COUPLESTATUS（素質能力變動：STR/AGI/... + 4轉能力）
# ============================================================


def parse_couplestatus_blocks(text: str, checkbox):
    """
    支援這種格式（packet 行和 size 行分開）：
    [+00:00:38:132] packet HEADER_ZC_COUPLESTATUS
    [0x0000000E (14)] {
      0000  ...
    }
    """
    t0 = time.perf_counter()
    lines = text.splitlines()
    results = []

    i = 0
    n = len(lines)
    if checkbox:
        while i < n:
            line = lines[i].strip()

            if "packet HEADER_ZC_COUPLESTATUS" in line:
                # 取時間戳
                m_ts = re.match(r'^\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]', line)
                timestamp = m_ts.group(1) if m_ts else ""

                # size 可能在同一行或下一行（你提供的是下一行）
                size = None
                m = SIZE_RE.search(line)
                if m:
                    size = int(m.group(1))
                else:
                    j = i + 1
                    while j < n and j <= i + 3:
                        m2 = SIZE_RE.search(lines[j])
                        if m2:
                            size = int(m2.group(1))
                            i = j  # i 移到 size 那一行
                            break
                        j += 1

                if size is None:
                    i += 1
                    continue

                # 從 size 行的下一行開始收 hex
                i += 1
                hex_bytes = []

                while i < n:
                    line2 = lines[i].strip()
                    if line2.startswith("}"):
                        break

                    maddr = re.match(r'^\s*[0-9A-Fa-f]{4}\s+(.*)$', line2)
                    if maddr:
                        for token in maddr.group(1).split():
                            if re.fullmatch(r'[0-9A-Fa-f]{2}', token):
                                hex_bytes.append(token)
                                if len(hex_bytes) >= size:
                                    break
                            else:
                                break

                    if len(hex_bytes) >= size:
                        break

                    i += 1

                results.append({"timestamp": timestamp, "size": size, "hex": hex_bytes[:size]})

            i += 1

        print(f"[COUPLESTATUS] 解析到 {len(results)} 筆，耗時: {(time.perf_counter() - t0) * 1000:.3f} ms")
    return results



def decode_couplestatus(hex_bytes, show_unknown=SHOW_UNKNOWN_COUPLESTATUS):
    """完整解碼 0x0141 ZC_COUPLESTATUS。"""
    parsed = _packet_meta(hex_bytes)
    stat_id = _u32(hex_bytes, 2)
    base = _i32(hex_bytes, 6)
    plus = _i32(hex_bytes, 10)
    stat_name = COUPLESTATUS_STAT_MAP.get(stat_id)
    if stat_name is None:
        if not show_unknown:
            return None
        stat_name = f"0x{stat_id:08X}"
    parsed.update({
        "stat_id": stat_id,
        "status_type": stat_id,
        "stat_name": stat_name,
        "base": base,
        "default_status": base,
        "plus": plus,
        "plus_status": plus,
        "total": base + plus,
    })
    if len(hex_bytes) > 14:
        parsed["unparsed_tail_hex"] = " ".join(hex_bytes[14:])
    return parsed

def check_button_state(ui):
    return ui.Character_ability_changes_checkbox.isChecked()


# ============================================================
# 解析 HEADER_ZC_PAR_CHANGE（素質能力變動：ATK/MATK 類）
# ============================================================

def parse_par_change_blocks(text: str, checkbox ):
    """
    支援這種格式（packet 行和 size 行分開）：
    [+00:00:03:177] packet HEADER_ZC_PAR_CHANGE
    [0x00000008 (8)] {
      0000 ...
    }
    """
    t0 = time.perf_counter()
    lines = text.splitlines()
    results = []

    i = 0
    n = len(lines)
    if checkbox:
        while i < n:
            line = lines[i].strip()

            if "packet HEADER_ZC_PAR_CHANGE" in line:
                m_ts = re.match(r'^\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]', line)
                timestamp = m_ts.group(1) if m_ts else ""

                size = None
                m = SIZE_RE.search(line)
                if m:
                    size = int(m.group(1))
                else:
                    j = i + 1
                    while j < n and j <= i + 3:
                        m2 = SIZE_RE.search(lines[j])
                        if m2:
                            size = int(m2.group(1))
                            i = j
                            break
                        j += 1

                if size is None:
                    i += 1
                    continue

                i += 1
                hex_bytes = []

                while i < n:
                    line2 = lines[i].strip()
                    if line2.startswith("}"):
                        break

                    maddr = re.match(r'^\s*[0-9A-Fa-f]{4}\s+(.*)$', line2)
                    if maddr:
                        for token in maddr.group(1).split():
                            if re.fullmatch(r'[0-9A-Fa-f]{2}', token):
                                hex_bytes.append(token)
                                if len(hex_bytes) >= size:
                                    break
                            else:
                                break

                    if len(hex_bytes) >= size:
                        break

                    i += 1

                results.append({"timestamp": timestamp, "size": size, "hex": hex_bytes[:size]})

            i += 1

        print(f"[PAR_CHANGE] 解析到 {len(results)} 筆，耗時: {(time.perf_counter() - t0) * 1000:.3f} ms")
    return results




def decode_par_change(hex_bytes, show_unknown=None):
    """完整解碼 0x00B0 ZC_PAR_CHANGE: varID.W + count.L。"""
    if show_unknown is None:
        show_unknown = SHOW_UNKNOWN_PAR_CHANGE
    parsed = _packet_meta(hex_bytes)
    stat_id = _u16(hex_bytes, 2)
    value = _i32(hex_bytes, 4)
    stat_name = PAR_CHANGE_STAT_MAP.get(stat_id)
    if stat_name is None:
        if not show_unknown:
            return None
        stat_name = f"0x{stat_id:04X}"
    parsed.update({
        "stat_id": stat_id,
        "var_id": stat_id,
        "stat_name": stat_name,
        "value": value,
        "count": value,
    })
    if len(hex_bytes) > 8:
        parsed["unparsed_tail_hex"] = " ".join(hex_bytes[8:])
    return parsed



# ============================================================
# 解析 SKILL2 區塊
# ============================================================
# 建議：在模組層級預先 compile，避免每次呼叫都重新 compile

# 專門抓 size (33)
SIZE_RE = re.compile(r"\(\s*(\d+)\s*\)")

def parse_skill2_blocks(text: str):
    t0 = time.perf_counter()

    lines = text.splitlines()
    results = []

    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()

        # 找 skill2 開頭
        if "packet HEADER_ZC_NOTIFY_SKILL2" in line:

            # 抓 timestamp: [+00:00:00:429]
            timestamp = line.split("]")[0][1:]

            # 下一行必定是 size 行例如：
            # [0x00000021 (33)] {
            i += 1
            if i >= n:
                break

            size_line = lines[i].strip()

            m = SIZE_RE.search(size_line)
            if not m:
                #print("[WARNING] 無法從 size 行解析數字:", size_line)
                i += 1
                continue

            size = int(m.group(1))

            # hex 區塊
            hex_bytes = []
            i += 1

            while i < n:
                line2 = lines[i].strip()

                if line2.startswith("}"):
                    break  # 區塊結束

                # 例： "0000  DE 01 FD ..."
                if len(line2) > 4 and line2[:4].isalnum():
                    chunks = line2[4:].split()
                    hex_bytes.extend(chunks)
                    if len(hex_bytes) >= size:
                        break

                i += 1

            results.append({
                "timestamp": timestamp,
                "type": "SKILL2",
                "hex": hex_bytes[:size]
            })

        i += 1

    t1 = time.perf_counter()
    print(f"[skill2 FAST] 解析耗時: {(t1 - t0) * 1000:.3f} ms")

    return results

# ============================================================
# 解碼 SKILL2 欄位
# ============================================================

def decode_skill2(hex_bytes):
    """完整解碼 33-byte ZC_NOTIFY_SKILL2 / ZC_NOTIFY_SKILL layout。"""
    parsed = _packet_meta(hex_bytes)
    skill_id = _u16(hex_bytes, 2)
    display_id = skill_display_map.get(skill_id, skill_id)
    parsed.update({
        "skill_id": skill_id,
        "skill_name": skill_name_map.get(display_id, f"ID {display_id}"),
        "sid": _u32(hex_bytes, 4),
        "source_aid": _u32(hex_bytes, 4),
        "did": _u32(hex_bytes, 8),
        "target_did": _u32(hex_bytes, 8),
        "start_time": _u32(hex_bytes, 12),
        "attack_mt": _i32(hex_bytes, 16),
        "attacked_mt": _i32(hex_bytes, 20),
        "damage": _i32(hex_bytes, 24),
        "level": _i16(hex_bytes, 28),
        "hit_count": _i16(hex_bytes, 30),
        "action": _u8(hex_bytes, 32),
        "attack_type": _u8(hex_bytes, 32),
    })
    # 舊欄位名稱保留，但不再只取低 1/2 byte。
    parsed["skill_delay"] = parsed["attack_mt"]
    parsed["global_delay"] = parsed["attacked_mt"]
    if len(hex_bytes) > 33:
        parsed["unparsed_tail_hex"] = " ".join(hex_bytes[33:])
    return parsed


# ============================================================
# 合併：修正 SKILL2 的假 SID（<100000） + 快取避免重複搜尋
# ============================================================
def time_to_float(ts):
    # "+00:04:35:250"
    parts = ts[1:].split(":")
    h = int(parts[0])
    m = int(parts[1])
    s = int(parts[2])
    ms = int(parts[3])
    return h*3600 + m*60 + s + ms/1000.0

def timestamp_to_ms(ts):
    # "+00:00:26:564" -> 26564
    h, m, s, ms = map(int, ts[1:].split(":"))
    return (((h * 60 + m) * 60) + s) * 1000 + ms


def merge_with_true_sid(all_packets):
    import time
    t0 = time.perf_counter()
    # --------------------------
    # 你的原始程式碼開始
    # --------------------------

    GROUND_HISTORY = {}

    # 第一階段：先 decode 所有封包
    for pkt in all_packets:
        if pkt["type"] == "GROUND":
            pkt["decoded"] = decode_groundskill(pkt["hex"])
            pkt["decoded"]["skill_id"] = le_int(pkt["hex"][2:4])
        elif pkt["type"] == "SKILL2":
            pkt["decoded"] = decode_skill2(pkt["hex"])
        elif pkt["type"] == "ACT3":
            pkt["decoded"] = decode_act3(pkt["hex"])

    # 第二階段：順序掃描
    for pkt in all_packets:

        if pkt["decoded"] is None:
            continue

        t = time_to_float(pkt["timestamp"])

        if pkt["type"] == "GROUND":
            skill = pkt["decoded"]["skill_id"]
            sid   = pkt["decoded"]["sid"]

            if skill not in GROUND_HISTORY:
                GROUND_HISTORY[skill] = []

            GROUND_HISTORY[skill].append({
                "sid": sid,
                "time": t
            })

            if len(GROUND_HISTORY[skill]) > 20:
                GROUND_HISTORY[skill].pop(0)

        elif pkt["type"] == "SKILL2":
            sid = pkt["decoded"]["sid"]

            if sid < 100000:
                skill = pkt["decoded"]["skill_id"]

                if skill in GROUND_HISTORY:
                    candidates = [
                        g for g in GROUND_HISTORY[skill]
                        if g["time"] <= t
                    ]

                    if candidates:
                        true_sid = max(candidates, key=lambda x: x["time"])["sid"]
                        pkt["decoded"]["sid"] = true_sid

    # --------------------------
    # 你的原始程式碼結束
    # --------------------------
    t1 = time.perf_counter()
    print(f"[merge_with_true_sid] 解析耗時: {(t1 - t0)*1000:.3f} ms")

    return all_packets


# ============================================================
# 解析 HEADER_ZC_NOTIFY_MOVEENTRY11
# ============================================================

MOVEENTRY11_BLOCK_RE = re.compile(
    r'\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+(HEADER_ZC_NOTIFY_MOVEENTRY11)\s*'
    r'\[\s*0x[0-9A-Fa-f]+\s+\((\d+)\)\]\s*'
    r'\{\s*\n([\s\S]*?)^\}\s*$',
    re.MULTILINE
)

# 專門抓地址行與其後 HEX 區塊（不含 ASCII）
HEX_ONLY_RE = re.compile(
    r'^\s*'
    r'[0-9A-Fa-f]{4}'        # 0000 / 0010 / 0020
    r'\s+'
    r'('
    r'(?:[0-9A-Fa-f]{2}\s+)+'  # "DE 01 81 00 ... " 只抓這一段
    r')'
)

def parse_moveentry11_blocks(text):
    t0 = time.perf_counter()
    results = []

    for t, packet_name, size_str, block in MOVEENTRY11_BLOCK_RE.findall(text):
        size = int(size_str)
        hex_bytes = []

        for line in block.splitlines():
            m = HEX_ONLY_RE.match(line)
            if not m:
                continue

            # 該行全部 HEX bytes 已確認為合法格式，split 即可
            hex_bytes.extend(m.group(1).split())

            if len(hex_bytes) >= size:
                break  # 已讀滿 packet size 就不用繼續掃描

        results.append({
            "timestamp": t,
            "size": size,
            "hex": hex_bytes[:size]
        })

    t1 = time.perf_counter()
    print(f"[move entry] 解析耗時: {(t1 - t0) * 1000:.3f} ms")
    return results



# ============================================================
# Actor / monster 名稱清理
# ============================================================
# 已由實際 replay / 使用者確認的 DID 顯示名稱。
MONSTER_NAME_OVERRIDE = {
    34543: "生命寶石",
}

_INTERNAL_ACTOR_NAME_RE = re.compile(r"^#?(?:mk|le)_\d+$", re.IGNORECASE)


def _decode_actor_name(hex_bytes, start, size):
    """從 entry packet 的名稱欄位解 cp950，並在 NUL 結束。"""
    raw = bytes(int(b, 16) for b in hex_bytes[start:size])
    raw = raw.split(b"\x00", 1)[0]
    for enc in ("cp950", "big5", "utf-8"):
        try:
            return raw.decode(enc).strip()
        except UnicodeDecodeError:
            pass
    return raw.decode("cp950", errors="replace").strip()


def sanitize_actor_name(name, allow_internal=False):
    """清理 actor 名稱。

    一般 entry 仍排除 #mk_1 / #le_4 這類內部名稱，避免污染正常中文名稱；
    但 0x09FE 是 DID 名稱回查的重要來源，必要時允許保留內部名稱，
    這樣即使 replay 只提供 #mk_1，也能讓 09FE.AID 正確關聯傷害封包.DID。
    """
    if name is None:
        return None
    name = str(name).replace("\x00", "").strip()
    # 解碼錯誤的 replacement character 代表 offset/編碼不可信。
    if not name or "\ufffd" in name:
        return None
    # 控制字元不應出現在顯示名稱。
    if any(ord(ch) < 0x20 for ch in name):
        return None
    if not allow_internal:
        # #mk_10 / #le_4 等是腳本/內部 actor 名；一般來源仍不採用。
        if name.startswith("#") or _INTERNAL_ACTOR_NAME_RE.fullmatch(name):
            return None
    return name



def _decode_actor_entry11(hex_bytes, size, kind):
    """完整解碼目前程式使用的 2018+ actor entry layout。"""
    parsed = _packet_meta(hex_bytes)
    parsed["declared_size"] = size
    parsed.update({
        "object_type": _u8(hex_bytes, 4),
        "aid": _u32(hex_bytes, 5),
        "did": _u32(hex_bytes, 5),   # 舊程式把 AID 當作怪物識別 ID，保留相容名稱
        "gid": _u32(hex_bytes, 9),
        "speed": _i16(hex_bytes, 13),
        "body_state": _i16(hex_bytes, 15),
        "health_state": _i16(hex_bytes, 17),
        "effect_state": _i32(hex_bytes, 19),
        "job": _i16(hex_bytes, 23),
        "head": _u16(hex_bytes, 25),
        "weapon": _u32(hex_bytes, 27),
        "shield": _u32(hex_bytes, 31),
        "accessory": _u16(hex_bytes, 35),
    })

    if kind == "move":
        parsed.update({
            "move_start_time": _u32(hex_bytes, 37),
            "accessory2": _u16(hex_bytes, 41),
            "accessory3": _u16(hex_bytes, 43),
            "head_palette": _i16(hex_bytes, 45),
            "body_palette": _i16(hex_bytes, 47),
            "head_dir": _i16(hex_bytes, 49),
            "robe": _u16(hex_bytes, 51),
            "guild_id": _u32(hex_bytes, 53),
            "guild_emblem_ver": _i16(hex_bytes, 57),
            "honor": _i16(hex_bytes, 59),
            "virtue": _i32(hex_bytes, 61),
            "is_pk_mode": _u8(hex_bytes, 65),
            "sex": _u8(hex_bytes, 66),
        })
        movement = _decode_move_data(hex_bytes[67:73])
        parsed["move_data"] = movement
        parsed.update({
            "from_x": movement["from_x"], "from_y": movement["from_y"],
            "to_x": movement["to_x"], "to_y": movement["to_y"],
            "move_sub_x": movement["sub_x"], "move_sub_y": movement["sub_y"],
            "x_size": _u8(hex_bytes, 73),
            "y_size": _u8(hex_bytes, 74),
            "level": _i16(hex_bytes, 75),
            "font": _i16(hex_bytes, 77),
            "max_hp": _i32(hex_bytes, 79),
            "hp": _i32(hex_bytes, 83),
            "is_boss": _u8(hex_bytes, 87),
            "body": _u16(hex_bytes, 88),
        })
        name_start = 90
    else:
        parsed.update({
            "accessory2": _u16(hex_bytes, 37),
            "accessory3": _u16(hex_bytes, 39),
            "head_palette": _i16(hex_bytes, 41),
            "body_palette": _i16(hex_bytes, 43),
            "head_dir": _i16(hex_bytes, 45),
            "robe": _u16(hex_bytes, 47),
            "guild_id": _u32(hex_bytes, 49),
            "guild_emblem_ver": _i16(hex_bytes, 53),
            "honor": _i16(hex_bytes, 55),
            "virtue": _i32(hex_bytes, 57),
            "is_pk_mode": _u8(hex_bytes, 61),
            "sex": _u8(hex_bytes, 62),
        })
        pos = _decode_pos_dir(hex_bytes[63:66])
        parsed["pos_dir"] = pos
        parsed.update({
            "x": pos["x"], "y": pos["y"], "dir": pos["dir"],
            "x_size": _u8(hex_bytes, 66),
            "y_size": _u8(hex_bytes, 67),
        })
        if kind == "stand":
            parsed["state"] = _u8(hex_bytes, 68)
            parsed.update({
                "level": _i16(hex_bytes, 69),
                "font": _i16(hex_bytes, 71),
                "max_hp": _i32(hex_bytes, 73),
                "hp": _i32(hex_bytes, 77),
                "is_boss": _u8(hex_bytes, 81),
                "body": _u16(hex_bytes, 82),
            })
            name_start = 84
        else:  # new/spawn
            parsed.update({
                "level": _i16(hex_bytes, 68),
                "font": _i16(hex_bytes, 70),
                "max_hp": _i32(hex_bytes, 72),
                "hp": _i32(hex_bytes, 76),
                "is_boss": _u8(hex_bytes, 80),
                "body": _u16(hex_bytes, 81),
            })
            name_start = 83

    parsed["name"] = _decode_actor_name(hex_bytes, name_start, size)
    parsed["name_raw_hex"] = " ".join(hex_bytes[name_start:size])
    return parsed


def decode_moveentry11(hex_bytes, size):
    return _decode_actor_entry11(hex_bytes, size, "move")
# ============================================================
# 解析 HEADER_ZC_NOTIFY_STANDENTRY11
# ============================================================
def parse_standentry11_blocks(text):
    t0_stand = time.perf_counter()
    pattern = re.compile(
        r'\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+(HEADER_ZC_NOTIFY_STANDENTRY11)\s*'
        r'\[\s*0x[0-9A-Fa-f]+\s+\((\d+)\)\]\s*'
        r'\{\s*\n([\s\S]*?)^\}\s*$',
        re.MULTILINE
    )

    results = []
    for t, packet_name, size, block in pattern.findall(text):
        # 只抓地址行後面的 HEX，不抓 ASCII
        hex_bytes = []
        for line in block.splitlines():
            m = re.match(r'^\s*[0-9A-Fa-f]{4}\s+(.*)$', line)
            if m:
                for token in m.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', token):
                        hex_bytes.append(token)
                    else:
                        break  # 遇到 ASCII → 本行停止

        results.append({
            "timestamp": t,
            "size": int(size),
            "hex": hex_bytes[:int(size)]
        })
    t1_stand = time.perf_counter()
    print(f"[stand entry] 解析耗時: {(t1_stand - t0_stand) * 1000:.3f} ms")
    return results


def decode_standentry11(hex_bytes, size):
    return _decode_actor_entry11(hex_bytes, size, "stand")
# ============================================================
# 解析 HEADER_ZC_NOTIFY_NEWENTRY11
# ============================================================

def decode_newentry11(hex_bytes, size):
    return _decode_actor_entry11(hex_bytes, size, "new")
    
def parse_newentry11_blocks(text):
    """解析 NEWENTRY11 / 0x09FE。

    舊版只依 packet 標題 HEADER_ZC_NOTIFY_NEWENTRY11 判斷；RRF reader 若使用
    不同標題或未知名稱，同一個 0x09FE 封包就會漏掉。這裡改成直接檢查
    packet 內容前 2 bytes（little-endian opcode），只要是 FE 09 就視為 NEWENTRY11。
    """
    t0_new = time.perf_counter()
    lines = text.splitlines()
    results = []
    packet_re = re.compile(r'^\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+(\S+)\s*$')

    i = 0
    while i < len(lines):
        m = packet_re.match(lines[i].strip())
        if not m:
            i += 1
            continue

        timestamp, packet_name = m.groups()
        if i + 1 >= len(lines):
            break

        sm = SIZE_RE.search(lines[i + 1])
        if not sm:
            i += 1
            continue

        size = int(sm.group(1))
        j = i + 2
        hex_bytes = []
        while j < len(lines):
            row = lines[j].strip()
            if row.startswith("}"):
                break

            ma = re.match(r'^\s*[0-9A-Fa-f]{4,}\s+(.*)$', lines[j])
            if ma:
                for tok in ma.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', tok):
                        hex_bytes.append(tok.upper())
                        if len(hex_bytes) >= size:
                            break
                    else:
                        break
            if len(hex_bytes) >= size:
                break
            j += 1

        packet = hex_bytes[:size]
        if len(packet) >= 2 and _u16(packet, 0) == 0x09FE:
            results.append({
                "timestamp": timestamp,
                "size": size,
                "hex": packet,
                "packet_name": packet_name,
                "opcode": 0x09FE,
                "opcode_hex": "0x09FE",
            })

        i = max(i + 1, j)

    t1_new = time.perf_counter()
    print(f"[new entry / 0x09FE] 解析到 {len(results)} 筆，耗時: {(t1_new - t0_new) * 1000:.3f} ms")
    return results


def _packet_timestamp_to_seconds(ts):
    try:
        h, m, sec, ms = map(int, str(ts)[1:].split(":"))
        return h * 3600.0 + m * 60.0 + sec + ms / 1000.0
    except Exception:
        return 0.0


def _seconds_to_packet_timestamp(sec):
    """float 秒數轉成 replay 顯示用 +HH:MM:SS:mmm。"""
    total_ms = max(0, int(round(float(sec or 0.0) * 1000.0)))
    h, rem = divmod(total_ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"+{h:02d}:{m:02d}:{s:02d}:{ms:03d}"


# 09FD/09FE/09FF 的 objecttype 是 client-side actor 顯示類型，
# 不是 map.hpp 的 BL_PC/BL_MOB/BL_PET bitmask。
# rAthena clif_bl_type() 對新版 client 的實際值如下。
CLIENT_ACTOR_TYPE_NAMES = {
    0x00: "PC_TYPE",
    0x01: "NPC_TYPE",
    0x02: "ITEM_TYPE",
    0x03: "SKILL_TYPE",
    0x04: "UNKNOWN_TYPE",
    0x05: "NPC_MOB_TYPE",
    0x06: "NPC_EVT_TYPE",
    0x07: "NPC_PET_TYPE",
    0x08: "NPC_HOM_TYPE",
    0x09: "NPC_MERSOL_TYPE",
    0x0A: "NPC_ELEMENTAL_TYPE",
    0x0C: "NPC_MOB_NPC_TYPE",
    0x0D: "NPC_ABR_TYPE",
    0x0E: "NPC_BIONIC_TYPE",
}



def _decode_fixed_text_field(hex_bytes, start, length):
    """解固定長度的 RO 字串欄位；優先 cp950/big5。"""
    if not hex_bytes or start < 0 or start >= len(hex_bytes):
        return ""
    raw = bytes(int(x, 16) for x in hex_bytes[start:start + length])
    raw = raw.split(b"\x00", 1)[0]
    if not raw:
        return ""
    for enc in ("cp950", "big5", "utf-8", "ascii"):
        try:
            return raw.decode(enc).strip()
        except Exception:
            continue
    return raw.decode("cp950", errors="replace").strip()


def decode_guild_related_packet(hex_bytes):
    """完整解析會用到的公會名稱相關封包。"""
    opcode = _u16(hex_bytes, 0) if len(hex_bytes) >= 2 else 0
    parsed = _packet_meta(hex_bytes)
    if opcode in (0x0150, 0x01B6):
        parsed.update({
            "guild_id": _u32(hex_bytes, 2),
            "level": _i32(hex_bytes, 6),
            "user_num": _i32(hex_bytes, 10),
            "max_user_num": _i32(hex_bytes, 14),
            "user_average_level": _i32(hex_bytes, 18),
            "exp": _i32(hex_bytes, 22),
            "max_exp": _i32(hex_bytes, 26),
            "point": _i32(hex_bytes, 30),
            "honor": _i32(hex_bytes, 34),
            "virtue": _i32(hex_bytes, 38),
            "emblem_version": _i32(hex_bytes, 42),
            "guild_name": _decode_fixed_text_field(hex_bytes, 46, 24),
            "master_name": _decode_fixed_text_field(hex_bytes, 70, 24),
            "manage_land": _decode_fixed_text_field(hex_bytes, 94, 16),
        })
        if opcode == 0x01B6 and len(hex_bytes) >= 114:
            parsed["zeny"] = _i32(hex_bytes, 110)
        parsed["opcode_name"] = "ZC_GUILD_INFO2" if opcode == 0x01B6 else "ZC_GUILD_INFO"
        return parsed
    if opcode in (0x0195, 0x0A30):
        # 0x0A30 ZC_ACK_REQNAMEALL2 延續 0x0195 的前 102 bytes layout，
        # 並在尾端追加 4-byte title_id。
        parsed.update({
            "aid": _u32(hex_bytes, 2),
            "character_name": _decode_fixed_text_field(hex_bytes, 6, 24),
            "party_name": _decode_fixed_text_field(hex_bytes, 30, 24),
            "guild_name": _decode_fixed_text_field(hex_bytes, 54, 24),
            "position_name": _decode_fixed_text_field(hex_bytes, 78, 24),
            "opcode_name": "ZC_ACK_REQNAMEALL2" if opcode == 0x0A30 else "ZC_ACK_REQNAMEALL",
        })
        if opcode == 0x0A30 and len(hex_bytes) >= 106:
            parsed["title_id"] = _u32(hex_bytes, 102)
        return parsed
    if opcode == 0x016A:
        parsed.update({
            "guild_id": _u32(hex_bytes, 2),
            "guild_name": _decode_fixed_text_field(hex_bytes, 6, 24),
            "opcode_name": "ZC_REQ_JOIN_GUILD",
        })
        return parsed
    if opcode == 0x01B4:
        parsed.update({
            "aid": _u32(hex_bytes, 2),
            "guild_id": _u32(hex_bytes, 6),
            "emblem_version": _i16(hex_bytes, 10),
            "opcode_name": "ZC_CHANGE_GUILD",
        })
        return parsed
    return parsed


def parse_guild_name_info(text):
    """從 Replay 建立 GuildID→公會名與 AID→公會名/ID 對照。"""
    lines = text.splitlines()
    packet_re = re.compile(r'^\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+(\S+)\s*$')
    guild_id_to_name = {}
    aid_to_guild_name = {}
    aid_to_guild_id = {}
    self_guild_id = 0
    i = 0
    while i < len(lines):
        m = packet_re.match(lines[i].strip())
        if not m or i + 1 >= len(lines):
            i += 1
            continue
        sm = SIZE_RE.search(lines[i + 1])
        if not sm:
            i += 1
            continue
        size = int(sm.group(1))
        j = i + 2
        packet = []
        while j < len(lines):
            row = lines[j].strip()
            if row.startswith("}"):
                break
            ma = re.match(r'^\s*[0-9A-Fa-f]{4,}\s+(.*)$', lines[j])
            if ma:
                for tok in ma.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', tok):
                        packet.append(tok.upper())
                        if len(packet) >= size:
                            break
                    else:
                        break
            if len(packet) >= size:
                break
            j += 1
        packet = packet[:size]
        opcode = _u16(packet, 0) if len(packet) >= 2 else 0
        try:
            if opcode in (0x0150, 0x01B6) and len(packet) >= 70:
                gid = _u32(packet, 2)
                name = _decode_fixed_text_field(packet, 46, 24)
                if gid:
                    self_guild_id = gid
                    if name:
                        guild_id_to_name[gid] = name
            elif opcode in (0x0195, 0x0A30) and len(packet) >= 78:
                aid = _u32(packet, 2)
                name = _decode_fixed_text_field(packet, 54, 24)
                if aid and name:
                    aid_to_guild_name[aid] = name
            elif opcode == 0x016A and len(packet) >= 30:
                gid = _u32(packet, 2)
                name = _decode_fixed_text_field(packet, 6, 24)
                if gid and name:
                    guild_id_to_name[gid] = name
            elif opcode == 0x01B4 and len(packet) >= 12:
                aid = _u32(packet, 2)
                gid = _u32(packet, 6)
                if aid:
                    aid_to_guild_id[aid] = gid
        except Exception:
            pass
        i = max(i + 1, j)
    return {
        "guild_id_to_name": guild_id_to_name,
        "aid_to_guild_name": aid_to_guild_name,
        "aid_to_guild_id": aid_to_guild_id,
        "self_guild_id": self_guild_id,
    }


def minimap_category_from_client_object_type(object_type):
    """把 actor packet 的 client objecttype 轉成小地圖分類。

    注意：0x00 是 PC_TYPE；某些使用玩家 sprite 的 NPC/寵物/魔物也可能被
    client 當 PC_TYPE 傳送，因此這裡依封包能提供的最可靠類型分類。
    """
    t = int(object_type or 0) & 0xFF
    if t == 0x00:
        return "player"
    if t == 0x05:
        return "mob"
    if t in (0x06, 0x0C):
        return "npc"
    if t == 0x07:
        return "pet"
    if t in (0x08, 0x09, 0x0A, 0x0D, 0x0E):
        return "companion"
    if t == 0x01:
        return "npc"
    return "other"


def _decode_packet_map_name(hex_bytes, start=2, length=16):
    """解析 0x0091/0x0092/0x0AC7 內固定長度的 mapName。"""
    if not hex_bytes or len(hex_bytes) <= start:
        return ""
    raw = bytes(int(x, 16) for x in hex_bytes[start:start + length])
    raw = raw.split(b"\x00", 1)[0]
    if not raw:
        return ""
    for enc in ("ascii", "cp950", "big5", "utf-8"):
        try:
            return raw.decode(enc).strip()
        except Exception:
            continue
    return raw.decode("ascii", errors="replace").strip()


def parse_actor_map_events(text):
    """
    只為小地圖掃描位置事件，不依賴 RRF 顯示的 packet 標題。

    0x09FE: spawn/new entry，提供初始座標
    0x09FD: walking，提供 from/to 座標
    0x09FF: idle/stand，提供目前座標
    0x0087: ZC_NOTIFY_PLAYERMOVE，自身移動（09FD 不會送給自己）
    0x02EB/0x0A18: ZC_ACCEPT_ENTER，自身進圖初始座標
    0x0088: ZC_STOPMOVE，位置校正
    0x0091: ZC_NPCACK_MAPMOVE，同 map-server 切圖（含 mapName + 目標座標）
    0x0092/0x0AC7: ZC_NPCACK_SERVERMOVE，跨 map-server 切圖
    VANISH : 單位離開目前場景
    """
    lines = text.splitlines()
    packet_re = re.compile(r'^\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+(\S+)\s*$')
    results = []
    i = 0
    n = len(lines)

    while i < n:
        m = packet_re.match(lines[i].strip())
        if not m:
            i += 1
            continue

        timestamp, packet_name = m.groups()
        if i + 1 >= n:
            break
        sm = SIZE_RE.search(lines[i + 1])
        if not sm:
            i += 1
            continue

        size = int(sm.group(1))
        j = i + 2
        hex_bytes = []
        while j < n:
            row = lines[j].strip()
            if row.startswith("}"):
                break
            ma = re.match(r'^\s*[0-9A-Fa-f]{4,}\s+(.*)$', lines[j])
            if ma:
                for tok in ma.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', tok):
                        hex_bytes.append(tok.upper())
                        if len(hex_bytes) >= size:
                            break
                    else:
                        break
            if len(hex_bytes) >= size:
                break
            j += 1

        packet = hex_bytes[:size]
        opcode = _u16(packet, 0) if len(packet) >= 2 else 0
        t_sec = _packet_timestamp_to_seconds(timestamp)

        try:
            if opcode == 0x0091 and len(packet) >= 22:
                # ZC_NPCACK_MAPMOVE：最可靠的切圖來源，封包本身帶 replay timestamp。
                map_name = _decode_packet_map_name(packet, 2, 16)
                if map_name:
                    results.append({
                        "time": t_sec, "timestamp": timestamp, "kind": "map_change",
                        "opcode": opcode, "map_name": map_name, "map_change_source": "packet_0091",
                    })
                # 此包同時提供自身進入新圖後的位置。map_change 先加入，確保先清舊圖再放自己。
                results.append({
                    "time": t_sec, "timestamp": timestamp, "kind": "self_pos",
                    "opcode": opcode, "aid": 0, "gid": 0,
                    "self_event": True, "object_type": 0x00, "job": 0,
                    "name": "", "x": _u16(packet, 18), "y": _u16(packet, 20),
                })
            elif opcode in (0x0092, 0x0AC7) and len(packet) >= 22:
                # ZC_NPCACK_SERVERMOVE(_DOMAIN)：跨 map-server。
                # 目標 mapName / x / y 都在封包內，時間也比 ReplayData metadata 可靠。
                map_name = _decode_packet_map_name(packet, 2, 16)
                if map_name:
                    results.append({
                        "time": t_sec, "timestamp": timestamp, "kind": "map_change",
                        "opcode": opcode, "map_name": map_name, "map_change_source": "packet_servermove",
                    })
            elif opcode == 0x09FE:
                dec = decode_newentry11(packet, size)
                results.append({
                    "time": t_sec, "timestamp": timestamp, "kind": "spawn",
                    "opcode": opcode, "aid": dec.get("aid", 0), "gid": dec.get("gid", 0),
                    "guild_id": dec.get("guild_id", 0),
                    "object_type": dec.get("object_type", 0), "job": dec.get("job", 0),
                    "name": dec.get("name", ""), "x": dec.get("x", 0), "y": dec.get("y", 0),
                    "details": dict(dec),
                })
            elif opcode == 0x09FD:
                dec = decode_moveentry11(packet, size)
                results.append({
                    "time": t_sec, "timestamp": timestamp, "kind": "move",
                    "opcode": opcode, "aid": dec.get("aid", 0), "gid": dec.get("gid", 0),
                    "guild_id": dec.get("guild_id", 0),
                    "object_type": dec.get("object_type", 0), "job": dec.get("job", 0),
                    "name": dec.get("name", ""), "speed": abs(dec.get("speed", 0) or 0),
                    "move_start_time": dec.get("move_start_time", 0),
                    "from_x": dec.get("from_x", 0), "from_y": dec.get("from_y", 0),
                    "to_x": dec.get("to_x", 0), "to_y": dec.get("to_y", 0),
                    "details": dict(dec),
                })
            elif opcode == 0x09FF:
                dec = decode_standentry11(packet, size)
                results.append({
                    "time": t_sec, "timestamp": timestamp, "kind": "stand",
                    "opcode": opcode, "aid": dec.get("aid", 0), "gid": dec.get("gid", 0),
                    "guild_id": dec.get("guild_id", 0),
                    "object_type": dec.get("object_type", 0), "job": dec.get("job", 0),
                    "name": dec.get("name", ""), "x": dec.get("x", 0), "y": dec.get("y", 0),
                    "details": dict(dec),
                })
            elif opcode == 0x0087 and len(packet) >= 12:
                # 自己走路不會收到 09FD；server 以 ZC_NOTIFY_PLAYERMOVE 回覆自身。
                movement = _decode_move_data(packet[6:12])
                results.append({
                    "time": t_sec, "timestamp": timestamp, "kind": "move",
                    "opcode": opcode, "aid": 0, "gid": 0,
                    "self_event": True, "object_type": 0x00, "job": 0,
                    "name": "", "speed": 0,
                    "move_start_time": _u32(packet, 2),
                    "from_x": movement.get("from_x", 0), "from_y": movement.get("from_y", 0),
                    "to_x": movement.get("to_x", 0), "to_y": movement.get("to_y", 0),
                    "details": {
                        "packet_id": opcode, "packet_size": size,
                        "move_start_time": _u32(packet, 2), **movement,
                    },
                })
            elif opcode in (0x02EB, 0x0A18) and len(packet) >= 9:
                # ZC_ACCEPT_ENTER：進地圖時自己的初始位置。
                pos = _decode_pos_dir(packet[6:9])
                results.append({
                    "time": t_sec, "timestamp": timestamp, "kind": "self_pos",
                    "opcode": opcode, "aid": 0, "gid": 0,
                    "self_event": True, "object_type": 0x00, "job": 0,
                    "name": "", "x": pos.get("x", 0), "y": pos.get("y", 0),
                    "details": {"packet_id": opcode, "packet_size": size, **pos},
                })
            elif opcode == 0x0088 and len(packet) >= 10:
                # ZC_STOPMOVE：server 強制/校正單位座標。
                results.append({
                    "time": t_sec, "timestamp": timestamp, "kind": "stop",
                    "opcode": opcode, "aid": _u32(packet, 2), "gid": 0,
                    "x": _u16(packet, 6), "y": _u16(packet, 8),
                    "details": {
                        "packet_id": opcode, "packet_size": size,
                        "aid": _u32(packet, 2), "x": _u16(packet, 6), "y": _u16(packet, 8),
                    },
                })
            elif packet_name == "HEADER_ZC_NOTIFY_VANISH":
                dec = decode_vanish(packet)
                results.append({
                    "time": t_sec, "timestamp": timestamp, "kind": "vanish",
                    "opcode": opcode, "aid": dec.get("did", 0),
                    "mode": dec.get("mode", 0), "mode_name": dec.get("mode_name", ""),
                })
        except Exception:
            # 小地圖是附加功能；單一異常 actor packet 不應中斷傷害解析。
            pass

        i = max(i + 1, j)

    results.sort(key=lambda e: e.get("time", 0.0))
    return results


KNOWN_PACKET_NAMES = {
    "HEADER_ZC_NOTIFY_GROUNDSKILL",
    "HEADER_ZC_NOTIFY_SKILL2",
    "HEADER_ZC_NOTIFY_ACT3",
    "HEADER_ZC_MSG_STATE_CHANGE3",
    "HEADER_ZC_MSG_STATE_CHANGE2",
    "HEADER_ZC_MSG_STATE_CHANGE",
    "HEADER_ZC_COUPLESTATUS",
    "HEADER_ZC_PAR_CHANGE",
    "HEADER_ZC_NOTIFY_VANISH",
    "HEADER_物品掉落",
    "HEADER_ZC_NOTIFY_MOVEENTRY11",
    "HEADER_ZC_NOTIFY_STANDENTRY11",
    "HEADER_ZC_NOTIFY_NEWENTRY11",
}


def decode_known_packet_full(packet_name, hex_bytes, size=None):
    """依目前程式已辨識的封包標題 / opcode，回傳所有已知欄位。"""
    size = len(hex_bytes) if size is None else size
    opcode = _u16(hex_bytes, 0) if len(hex_bytes) >= 2 else 0

    # 2015-05-13+ actor packets：直接依 opcode 解碼，避免 RRF 標題不同而漏掉。
    if opcode == 0x09FE:
        parsed = decode_newentry11(hex_bytes, size)
        parsed["opcode_name"] = "ZC_NOTIFY_NEWENTRY / spawn_unit"
        return parsed
    if opcode == 0x09FD:
        parsed = decode_moveentry11(hex_bytes, size)
        parsed["opcode_name"] = "ZC_NOTIFY_MOVEENTRY / unit_walking"
        return parsed
    if opcode == 0x09FF:
        parsed = decode_standentry11(hex_bytes, size)
        parsed["opcode_name"] = "ZC_NOTIFY_STANDENTRY / idle_unit"
        return parsed

    if opcode in (0x0150, 0x01B6, 0x0195, 0x0A30, 0x016A, 0x01B4):
        return decode_guild_related_packet(hex_bytes)

    if packet_name == "HEADER_ZC_NOTIFY_GROUNDSKILL":
        return decode_groundskill(hex_bytes)
    if packet_name == "HEADER_ZC_NOTIFY_SKILL2":
        return decode_skill2(hex_bytes)
    if packet_name == "HEADER_ZC_NOTIFY_ACT3":
        return decode_act3(hex_bytes)
    if packet_name == "HEADER_ZC_MSG_STATE_CHANGE3":
        return decode_statechange3(hex_bytes)
    if packet_name == "HEADER_ZC_MSG_STATE_CHANGE2":
        return decode_status_change(hex_bytes, "START")
    if packet_name == "HEADER_ZC_MSG_STATE_CHANGE":
        return decode_status_change(hex_bytes, "END")
    if packet_name == "HEADER_ZC_COUPLESTATUS":
        return decode_couplestatus(hex_bytes, show_unknown=True)
    if packet_name == "HEADER_ZC_PAR_CHANGE":
        return decode_par_change(hex_bytes, show_unknown=True)
    if packet_name == "HEADER_ZC_NOTIFY_VANISH":
        return decode_vanish(hex_bytes)
    if packet_name == "HEADER_物品掉落":
        return decode_itemdrop(hex_bytes)
    if packet_name == "HEADER_ZC_NOTIFY_MOVEENTRY11":
        return decode_moveentry11(hex_bytes, size)
    if packet_name == "HEADER_ZC_NOTIFY_STANDENTRY11":
        return decode_standentry11(hex_bytes, size)
    if packet_name == "HEADER_ZC_NOTIFY_NEWENTRY11":
        return decode_newentry11(hex_bytes, size)
    return _packet_meta(hex_bytes)


def parse_all_known_packets_complete(text):
    """掃描目前程式已支援的 packet 標題，完整保留並解碼其欄位。"""
    t0 = time.perf_counter()
    lines = text.splitlines()
    results = []
    packet_re = re.compile(r'^\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+(\S+)\s*$')
    i = 0
    while i < len(lines):
        m = packet_re.match(lines[i].strip())
        if not m:
            i += 1
            continue
        timestamp, packet_name = m.groups()
        if i + 1 >= len(lines):
            break
        sm = SIZE_RE.search(lines[i + 1])
        if not sm:
            i += 1
            continue
        size = int(sm.group(1))
        j = i + 2
        hex_bytes = []
        while j < len(lines):
            row = lines[j].strip()
            if row.startswith("}"):
                break
            ma = re.match(r'^\s*[0-9A-Fa-f]{4,}\s+(.*)$', lines[j])
            if ma:
                for tok in ma.group(1).split():
                    if re.fullmatch(r'[0-9A-Fa-f]{2}', tok):
                        hex_bytes.append(tok.upper())
                        if len(hex_bytes) >= size:
                            break
                    else:
                        break
            if len(hex_bytes) >= size:
                break
            j += 1
        packet = hex_bytes[:size]
        opcode = _u16(packet, 0) if len(packet) >= 2 else 0

        # actor 0x09FD/09FE/09FF 額外直接依 opcode 辨識，避免標題名稱不同而漏掉。
        actor_opcode_name = {
            0x09FD: "HEADER_ZC_NOTIFY_MOVEENTRY11 (0x09FD)",
            0x09FE: "HEADER_ZC_NOTIFY_NEWENTRY11 (0x09FE)",
            0x09FF: "HEADER_ZC_NOTIFY_STANDENTRY11 (0x09FF)",
            0x0150: "ZC_GUILD_INFO (0x0150)",
            0x01B6: "ZC_GUILD_INFO2 (0x01B6)",
            0x0195: "ZC_ACK_REQNAMEALL (0x0195)",
            0x0A30: "ZC_ACK_REQNAMEALL2 (0x0A30)",
            0x016A: "ZC_REQ_JOIN_GUILD (0x016A)",
            0x01B4: "ZC_CHANGE_GUILD (0x01B4)",
        }.get(opcode)
        if packet_name not in KNOWN_PACKET_NAMES and actor_opcode_name is None:
            i = max(i + 1, j)
            continue

        decoded = decode_known_packet_full(packet_name, packet, size)
        display_packet_name = actor_opcode_name or packet_name

        # VANISH 各 mode 都保留在完整解析資料中；真正是否顯示由 UI 勾選控制。
        results.append({
            "timestamp": timestamp,
            "packet_name": display_packet_name,
            "source_packet_name": packet_name,
            "opcode": opcode,
            "opcode_hex": f"0x{opcode:04X}" if opcode else "",
            "declared_size": size,
            "captured_size": len(packet),
            "complete": len(packet) == size,
            "hex": packet,
            "decoded": decoded,
        })
        i = max(i + 1, j)
    print(f"[完整封包解析] {len(results)} 包，耗時: {(time.perf_counter()-t0)*1000:.3f} ms")
    return results


class PacketDecodeTableModel(QAbstractTableModel):
    """封包列表虛擬 Model：不建立每列 Widget/Item，只在 View 要畫面資料時回傳內容。"""
    HEADERS = ["時間", "封包", "長度 / 狀態", "Raw HEX"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records = []
        self._indices = []

    def set_records(self, records, visible_indices=None):
        self.beginResetModel()
        self._records = records or []
        if visible_indices is None:
            self._indices = list(range(len(self._records)))
        else:
            self._indices = list(visible_indices)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._indices)

    def columnCount(self, parent=QModelIndex()):
        return 4

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def record_at(self, row):
        if 0 <= row < len(self._indices):
            idx = self._indices[row]
            if 0 <= idx < len(self._records):
                return self._records[idx]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        rec = self.record_at(index.row())
        if not rec:
            return None
        col = index.column()
        if col == 0:
            value = rec.get("timestamp", "")
        elif col == 1:
            value = rec.get("packet_name", "")
        elif col == 2:
            status = "完整" if rec.get("complete") else "截斷"
            value = f'{rec.get("captured_size", 0)}/{rec.get("declared_size", 0)} bytes {status}'
        else:
            value = " ".join(rec.get("hex", []))
        return str(value)


class PacketDecodeFieldsModel(QAbstractTableModel):
    """單一封包完整解析欄位的虛擬 Model。選包時只替換目前內容。"""
    HEADERS = ["欄位", "值"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []

    @staticmethod
    def _flatten(value, prefix=""):
        rows = []
        if isinstance(value, dict):
            for key, subvalue in value.items():
                if key == "raw_hex":
                    continue
                path = f"{prefix}.{key}" if prefix else str(key)
                rows.extend(PacketDecodeFieldsModel._flatten(subvalue, path))
        elif isinstance(value, (list, tuple)):
            # byte/短陣列直接一列顯示，避免為大量 bytes 製造大量列。
            if len(value) <= 32 and all(not isinstance(v, (dict, list, tuple)) for v in value):
                rows.append((prefix, str(value)))
            else:
                for i, subvalue in enumerate(value):
                    path = f"{prefix}[{i}]"
                    rows.extend(PacketDecodeFieldsModel._flatten(subvalue, path))
        else:
            rows.append((prefix, "" if value is None else str(value)))
        return rows

    def set_record(self, rec):
        rows = []
        if rec:
            rows.extend([
                ("timestamp", rec.get("timestamp", "")),
                ("packet_name", rec.get("packet_name", "")),
                ("source_packet_name", rec.get("source_packet_name", "")),
                ("opcode_hex", rec.get("opcode_hex", "")),
                ("declared_size", rec.get("declared_size", 0)),
                ("captured_size", rec.get("captured_size", 0)),
                ("complete", rec.get("complete", False)),
            ])
            rows.extend(self._flatten(rec.get("decoded") or {}))
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def clear(self):
        self.set_record(None)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 2

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        if not (0 <= index.row() < len(self._rows)):
            return None
        field, value = self._rows[index.row()]
        return str(field if index.column() == 0 else value)

def normalize_item_name(s):
    return str(s).strip().lower()

def get_drop_highlight_color(effect_id):
    """
    傳入 EffectID，對應到顏色就回傳 QColor，否則回傳 None
    """
    if effect_id is None:
        return None

    color = DROP_ITEM_HIGHLIGHT_MAP.get(effect_id)
    if color:
        return QColor(color)

    return None

import hashlib
import os


def load_gat_navigation(path):
    """讀取 Ragnarok .gat 導航格。只保留小地圖需要的 terrain type。"""
    with open(path, "rb") as f:
        data = f.read()

    base = 0
    if data[:4] != b"GRAT":
        # 少數舊檔有一個 zero-byte prefix。
        if len(data) >= 5 and data[1:5] == b"GRAT":
            base = 1
        else:
            raise ValueError("不是有效的 GAT 檔（找不到 GRAT header）")

    if len(data) < base + 14:
        raise ValueError("GAT 檔案過短")

    major = data[base + 4]
    minor = data[base + 5]
    width = struct.unpack_from("<i", data, base + 6)[0]
    height = struct.unpack_from("<i", data, base + 10)[0]
    if width <= 0 or height <= 0 or width > 10000 or height > 10000:
        raise ValueError(f"GAT 尺寸異常：{width} x {height}")

    tile_off = base + 14
    required = tile_off + width * height * 20
    if len(data) < required:
        raise ValueError(
            f"GAT 資料不完整：需要 {required:,} bytes，實際 {len(data):,} bytes"
        )

    terrain = []
    water = []
    for idx in range(width * height):
        raw_type = struct.unpack_from("<I", data, tile_off + idx * 20 + 16)[0]
        # GAT 1.3 可能把水域旗標放在高位；底層 terrain type 保留低 31 位。
        terrain.append(raw_type & 0x7FFFFFFF)
        water.append(bool(raw_type & 0x80000000))

    return {
        "path": os.path.abspath(path),
        "version": f"{major}.{minor}",
        "width": width,
        "height": height,
        "terrain": terrain,
        "water": water,
    }



class MiniMapReplayEngine:
    """v2.14: 純 Python 小地圖計算核心，可安全放在獨立 process。

    Qt / QWidget 完全不會進到這裡。process 只保留 replay actor state、
    傷害時間索引，輸出一份小型 frame snapshot 給 GUI thread 畫。
    """
    def __init__(self):
        self.source_version = -1
        self.events = []
        self.damage_times = []
        self.damage_rows = []
        self.names = {}
        self.guild_names = {}
        self.guild_aid_names = {}
        self.self_sid = 0
        self.self_guild_id = 0
        self.self_guild_name = ""
        self._reset_state()

    def _reset_state(self):
        self.actor_state = {}
        self.recent_positions = {}
        self.event_cursor = 0
        self.state_time = -1.0
        self.active_map_name = ""

    def set_sources(self, payload):
        version = int(payload.get("version", 0) or 0)
        if version == self.source_version:
            return
        self.source_version = version
        self.events = list(payload.get("events") or [])
        self.names = dict(payload.get("names") or {})
        self.guild_names = {int(k): str(v) for k, v in dict(payload.get("guild_names") or {}).items() if int(k or 0)}
        self.guild_aid_names = {int(k): str(v) for k, v in dict(payload.get("guild_aid_names") or {}).items() if int(k or 0) and str(v)}
        self.self_sid = int(payload.get("self_sid", 0) or 0)
        self.self_guild_id = int(payload.get("self_guild_id", 0) or 0)
        self.self_guild_name = str(payload.get("self_guild_name") or self.guild_aid_names.get(self.self_sid, "") or self.guild_names.get(self.self_guild_id, ""))

        indexed = []
        for item in payload.get("damage_rows") or []:
            try:
                # (time, sid, did, damage, skill_name)
                t, sid, did, damage, skill = item
                damage = int(damage or 0)
                if damage < 0:
                    continue
                indexed.append((float(t), int(sid or 0), int(did or 0), damage, str(skill or "")))
            except Exception:
                continue
        indexed.sort(key=lambda x: x[0])
        self.damage_times = [x[0] for x in indexed]
        self.damage_rows = indexed
        self._reset_state()

    def _lookup_name(self, actor_id):
        try:
            actor_id = int(actor_id or 0)
        except Exception:
            actor_id = 0
        return self.names.get(actor_id) or (f"AID {actor_id}" if actor_id else "")

    def _apply_event(self, event):
        kind = event.get("kind")
        if kind == "map_change":
            self.actor_state = {}
            self.recent_positions = {}
            self.active_map_name = (event.get("map_name") or "").strip()
            return

        if event.get("self_event"):
            aid = int(self.self_sid or 0)
        else:
            aid = int(event.get("aid", 0) or 0)
        if not aid:
            return

        if kind == "vanish":
            remove_aid = aid if aid in self.actor_state else next((
                state_aid for state_aid, state in self.actor_state.items()
                if int(state.get("gid", 0) or 0) == aid
            ), None)
            if remove_aid is not None:
                state = self.actor_state.get(remove_aid) or {}
                x = float(state.get("x", 0.0) or 0.0)
                y = float(state.get("y", 0.0) or 0.0)
                move = state.get("move")
                if move:
                    mt = float(event.get("time", 0.0) or 0.0)
                    start = float(move.get("start", 0.0) or 0.0)
                    duration = max(0.001, float(move.get("duration", 0.001) or 0.001))
                    ratio = min(1.0, max(0.0, (mt - start) / duration))
                    x = move["from_x"] + (move["to_x"] - move["from_x"]) * ratio
                    y = move["from_y"] + (move["to_y"] - move["from_y"]) * ratio
                self.recent_positions[remove_aid] = {
                    "x": x, "y": y, "time": float(event.get("time", 0.0) or 0.0),
                    "name": state.get("name", ""),
                    "category": minimap_category_from_client_object_type(state.get("object_type", 0)),
                }
                self.actor_state.pop(remove_aid, None)
            return

        state = self.actor_state.get(aid, {"aid": aid})
        state["gid"] = event.get("gid", state.get("gid", 0))
        state["object_type"] = event.get("object_type", state.get("object_type", 0))
        state["job"] = event.get("job", state.get("job", 0))
        details_for_guild = event.get("details") if isinstance(event.get("details"), dict) else {}
        event_guild_id = int(event.get("guild_id", details_for_guild.get("guild_id", state.get("guild_id", 0))) or 0)
        if event_guild_id:
            state["guild_id"] = event_guild_id
        resolved_guild_name = (
            event.get("guild_name")
            or self.guild_aid_names.get(aid, "")
            or (self.self_guild_name if self.self_sid and aid == self.self_sid else "")
            or self.guild_names.get(int(state.get("guild_id", 0) or 0), "")
            or state.get("guild_name", "")
        )
        if resolved_guild_name:
            state["guild_name"] = resolved_guild_name
        if event.get("speed"):
            state["speed"] = abs(float(event.get("speed") or 0))
        raw_name = event.get("name")
        if raw_name:
            state["name"] = raw_name
        details = event.get("details")
        if isinstance(details, dict):
            merged_details = dict(state.get("details") or {})
            merged_details.update(details)
            state["details"] = merged_details
        state["last_event_kind"] = kind
        state["last_event_timestamp"] = event.get("timestamp", state.get("last_event_timestamp", ""))
        state["last_packet_opcode"] = int(event.get("opcode", state.get("last_packet_opcode", 0)) or 0)

        if kind in ("spawn", "stand", "self_pos", "stop"):
            state["x"] = float(event.get("x", state.get("x", 0)) or 0)
            state["y"] = float(event.get("y", state.get("y", 0)) or 0)
            state["move"] = None
        elif kind == "move":
            event_time = float(event.get("time", 0.0) or 0.0)
            packet_fx = float(event.get("from_x", state.get("x", 0)) or 0)
            packet_fy = float(event.get("from_y", state.get("y", 0)) or 0)
            tx = float(event.get("to_x", packet_fx) or packet_fx)
            ty = float(event.get("to_y", packet_fy) or packet_fy)

            fx, fy = packet_fx, packet_fy
            previous_move = state.get("move")
            if previous_move:
                prev_start = float(previous_move.get("start", 0.0) or 0.0)
                prev_duration = max(0.001, float(previous_move.get("duration", 0.001) or 0.001))
                prev_ratio = min(1.0, max(0.0, (event_time - prev_start) / prev_duration))
                predicted_x = float(previous_move.get("from_x", 0.0)) + (float(previous_move.get("to_x", 0.0)) - float(previous_move.get("from_x", 0.0))) * prev_ratio
                predicted_y = float(previous_move.get("from_y", 0.0)) + (float(previous_move.get("to_y", 0.0)) - float(previous_move.get("from_y", 0.0))) * prev_ratio
                if math.hypot(predicted_x - packet_fx, predicted_y - packet_fy) <= 4.0:
                    fx, fy = predicted_x, predicted_y

            speed_ms = max(1.0, float(event.get("speed", 0) or state.get("speed", 0) or 150.0))
            dx_cells = abs(tx - fx)
            dy_cells = abs(ty - fy)
            diagonal_cells = min(dx_cells, dy_cells)
            straight_cells = max(dx_cells, dy_cells) - diagonal_cells
            weighted_cells = straight_cells + diagonal_cells * math.sqrt(2.0)
            duration = max(0.05, weighted_cells * speed_ms / 1000.0) if weighted_cells > 0 else 0.05

            next_time = event.get("_next_pos_time")
            next_x = event.get("_next_pos_x")
            next_y = event.get("_next_pos_y")
            if next_time is not None:
                dt = float(next_time) - event_time
                if dt > 0.02 and next_x is not None and next_y is not None:
                    next_x = float(next_x)
                    next_y = float(next_y)
                    target_gap = math.hypot(next_x - tx, next_y - ty)
                    interrupted = dt < duration - 0.02
                    near_expected_timing = dt <= duration * 1.25
                    if interrupted or (target_gap > 0.75 and near_expected_timing):
                        tx, ty = next_x, next_y
                        duration = max(0.05, dt)

            state["x"] = fx
            state["y"] = fy
            state["move"] = {
                "start": event_time, "duration": duration,
                "from_x": fx, "from_y": fy, "to_x": tx, "to_y": ty,
            }

        self.actor_state[aid] = state

    def _advance_to(self, sec):
        sec = max(0.0, float(sec or 0.0))
        if sec + 1e-9 < self.state_time:
            self._reset_state()
        cursor = self.event_cursor
        while cursor < len(self.events) and float(self.events[cursor].get("time", 0.0)) <= sec + 1e-9:
            self._apply_event(self.events[cursor])
            cursor += 1
        self.event_cursor = cursor
        self.state_time = sec

    def _seed_self_from_next_event(self):
        self_aid = int(self.self_sid or 0)
        if not self_aid or self_aid in self.actor_state:
            return
        seed_event = None
        seed_x = seed_y = None
        for idx in range(int(self.event_cursor or 0), len(self.events)):
            event = self.events[idx]
            if event.get("kind") == "map_change":
                break
            event_aid = int(event.get("aid", 0) or 0)
            if not event.get("self_event") and event_aid != self_aid:
                continue
            kind = event.get("kind")
            if kind == "move":
                seed_x, seed_y = event.get("from_x"), event.get("from_y")
            elif kind in ("self_pos", "stand", "stop", "spawn"):
                seed_x, seed_y = event.get("x"), event.get("y")
            else:
                continue
            if seed_x is not None and seed_y is not None:
                seed_event = event
                break
        if seed_event is None:
            return
        self.actor_state[self_aid] = {
            "aid": self_aid,
            "gid": int(seed_event.get("gid", 0) or 0),
            "object_type": 0x00,
            "job": int(seed_event.get("job", 0) or 0),
            "guild_id": int(seed_event.get("guild_id", (seed_event.get("details") or {}).get("guild_id", self.self_guild_id)) or self.self_guild_id or 0),
            "guild_name": (seed_event.get("guild_name") or self.self_guild_name or self.guild_aid_names.get(self_aid, "") or self.guild_names.get(int(seed_event.get("guild_id", (seed_event.get("details") or {}).get("guild_id", self.self_guild_id)) or self.self_guild_id or 0), "")),
            "name": self._lookup_name(self_aid),
            "x": float(seed_x or 0.0), "y": float(seed_y or 0.0), "move": None,
            "details": dict(seed_event.get("details") or {}),
            "last_event_kind": seed_event.get("kind", ""),
            "last_event_timestamp": seed_event.get("timestamp", ""),
            "last_packet_opcode": int(seed_event.get("opcode", 0) or 0),
        }

    def _units_at(self, sec):
        self._advance_to(sec)
        self._seed_self_from_next_event()
        units = []
        for aid, state in self.actor_state.items():
            x = float(state.get("x", 0.0) or 0.0)
            y = float(state.get("y", 0.0) or 0.0)
            move = state.get("move")
            if move:
                start = float(move.get("start", 0.0))
                duration = max(0.001, float(move.get("duration", 0.001)))
                ratio = min(1.0, max(0.0, (float(sec) - start) / duration))
                x = move["from_x"] + (move["to_x"] - move["from_x"]) * ratio
                y = move["from_y"] + (move["to_y"] - move["from_y"]) * ratio
            object_type = int(state.get("object_type", 0) or 0) & 0xFF
            category = minimap_category_from_client_object_type(object_type)
            name = state.get("name") or self._lookup_name(aid)
            units.append({
                "aid": int(aid), "gid": state.get("gid", 0), "name": name,
                "object_type": object_type,
                "object_type_name": CLIENT_ACTOR_TYPE_NAMES.get(object_type, f"TYPE_0x{object_type:02X}"),
                "category": category, "job": state.get("job", 0),
                "guild_id": int(state.get("guild_id", 0) or 0),
                "guild_name": state.get("guild_name") or self.guild_aid_names.get(int(aid), "") or (self.self_guild_name if self.self_sid and int(aid) == self.self_sid else "") or self.guild_names.get(int(state.get("guild_id", 0) or 0), ""),
                "speed": state.get("speed", 0),
                "x": x, "y": y, "is_self": bool(self.self_sid and int(aid) == self.self_sid),
                "last_event_kind": state.get("last_event_kind", ""),
                "last_event_timestamp": state.get("last_event_timestamp", ""),
                "last_packet_opcode": state.get("last_packet_opcode", 0),
                "details": dict(state.get("details") or {}),
            })
            self.recent_positions[int(aid)] = {
                "x": x, "y": y, "time": float(sec), "name": name, "category": category,
            }
        return units

    def _damage_links_at(self, sec, units, selected_did=None, selected_sid=None, damage_time_range=None):
        sec = max(0.0, float(sec or 0.0))
        start_sec = max(0.0, sec - 1.0)
        positions = {
            int(u.get("aid", 0) or 0): (float(u.get("x", 0.0)), float(u.get("y", 0.0)))
            for u in units if int(u.get("aid", 0) or 0)
        }
        for aid, pos in self.recent_positions.items():
            if aid not in positions and sec - float(pos.get("time", -9999.0) or -9999.0) <= 1.25:
                positions[int(aid)] = (float(pos.get("x", 0.0)), float(pos.get("y", 0.0)))

        lo = bisect.bisect_left(self.damage_times, start_sec - 1e-9)
        hi = bisect.bisect_right(self.damage_times, sec + 1e-9)
        grouped = {}
        did_filter = int(selected_did) if selected_did is not None else None
        sid_filter = int(selected_sid) if selected_sid is not None else None

        for idx in range(lo, hi):
            t, sid, did, damage, skill = self.damage_rows[idx]
            if did_filter is not None and did != did_filter:
                continue
            if sid_filter is not None and sid != sid_filter:
                continue
            if damage_time_range is not None:
                rs, re_ = damage_time_range
                if t < float(rs) - 1e-9 or t > float(re_) + 1e-9:
                    continue
            if not sid or not did or sid == did or sid not in positions or did not in positions:
                continue
            key = (sid, did)
            item = grouped.setdefault(key, {
                "sid": sid, "did": did, "damage": 0, "count": 0,
                "latest_time": t, "skills": set(),
            })
            item["damage"] += damage
            item["count"] += 1
            item["latest_time"] = max(float(item["latest_time"]), float(t))
            if skill:
                item["skills"].add(skill)

        links = []
        for item in grouped.values():
            sx, sy = positions[item["sid"]]
            tx, ty = positions[item["did"]]
            links.append({
                **item,
                "source_x": sx, "source_y": sy,
                "target_x": tx, "target_y": ty,
                "age": max(0.0, sec - float(item["latest_time"])),
                "source_name": self._lookup_name(item["sid"]),
                "target_name": self._lookup_name(item["did"]),
                "skills": sorted(item["skills"]),
            })
        links.sort(key=lambda x: (x.get("age", 0.0), -x.get("damage", 0)))
        return links

    def compute(self, request):
        sec = max(0.0, float(request.get("sec", 0.0) or 0.0))
        units = self._units_at(sec)

        # v2.15：人物位置可以 60 FPS 算，但傷害箭頭/文字沒有必要每幀重算。
        # GUI 端只在約 10 FPS 時送 include_damage=True，其餘 frame 只回傳 units。
        include_damage = bool(request.get("include_damage", True))
        if include_damage:
            links = self._damage_links_at(
                sec, units,
                selected_did=request.get("selected_did"),
                selected_sid=request.get("selected_sid"),
                damage_time_range=request.get("damage_time_range"),
            )
            damage_event_count = sum(int(x.get("count", 0) or 0) for x in links)
        else:
            links = None
            damage_event_count = None

        counts = {
            "self": sum(1 for u in units if u.get("is_self")),
            "player": sum(1 for u in units if u.get("category") == "player" and not u.get("is_self")),
            "mob": sum(1 for u in units if u.get("category") == "mob"),
            "pet": sum(1 for u in units if u.get("category") == "pet"),
            "npc": sum(1 for u in units if u.get("category") == "npc"),
            "companion": sum(1 for u in units if u.get("category") == "companion"),
            "other": sum(1 for u in units if u.get("category") == "other"),
        }
        return {
            "seq": int(request.get("seq", 0) or 0),
            # 回傳 engine 真正已套用的 source version；若 request 比 sources 更早抵達，
            # GUI 會丟棄這一幀，不會誤把舊資料當成新資料。
            "source_version": int(self.source_version),
            "sec": sec,
            "active_map": self.active_map_name,
            "units": units,
            "links": links,
            "damage_updated": include_damage,
            "counts": counts,
            "damage_event_count": damage_event_count,
        }


def _minimap_process_put_fifo(q, item):
    """v2.19：回放 frame/result 一律 FIFO，不丟棄中間結果。

    正常播放寧可因計算負載而延後，也不能把中間 Replay frame 直接覆蓋掉。
    """
    try:
        q.put(item)
        return True
    except (EOFError, OSError, BrokenPipeError):
        return False
    except Exception:
        return False


def minimap_compute_process_main(source_queue, request_queue, result_queue):
    """v2.19: 獨立 process 小地圖計算迴圈。

    sources 只在 RRF 資料更新時傳一次；正常播放的 frame request 嚴格 FIFO。
    不再使用 latest-only：每個已送入的 Replay frame 都會依序計算、依序回傳。
    """
    engine = MiniMapReplayEngine()
    running = True
    while running:
        # source 更新優先，並只吃最新一份。
        latest_source = None
        try:
            while True:
                latest_source = source_queue.get_nowait()
        except queue.Empty:
            pass
        if latest_source is not None:
            if latest_source.get("cmd") == "stop":
                break
            engine.set_sources(latest_source)

        try:
            req = request_queue.get(timeout=0.02)
        except queue.Empty:
            continue
        except (EOFError, OSError):
            break

        # v2.19：正常回放不得丟 frame。
        # 只取這一筆 request，下一筆留在 FIFO queue 等下一輪處理。
        if req.get("cmd") == "stop":
            break

        # request 若已經是更新後 source，但 source queue 尚未 drain，再補一次。
        latest_source = None
        try:
            while True:
                latest_source = source_queue.get_nowait()
        except queue.Empty:
            pass
        if latest_source is not None:
            if latest_source.get("cmd") == "stop":
                break
            engine.set_sources(latest_source)

        try:
            result = engine.compute(req)
            _minimap_process_put_fifo(result_queue, result)
        except Exception as e:
            _minimap_process_put_fifo(result_queue, {
                "seq": int(req.get("seq", 0) or 0),
                "source_version": int(req.get("source_version", 0) or 0),
                "error": f"{type(e).__name__}: {e}",
            })

class GATMiniMapWidget(QWidget):
    """輕量 GAT 小地圖。底圖快取成 QImage，播放時只重畫單位點。"""
    unitSelected = Signal(object)
    unitContextRequested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 360)
        self.setMouseTracking(True)
        self.gat = None
        self.map_image = None
        self.units = []
        self.damage_links = []
        self.current_sec = 0.0
        self._last_draw_rect = None
        self._unit_screen_points = []
        self.selected_aid = None
        # v2.12：右上「篩選魔物」鎖定 DID 時，小地圖額外標示該 AID。
        self.highlight_aid = None
        # v2.4：獨立小地圖視窗支援縮放 / 平移。
        self.zoom_factor = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._panning = False
        self._pan_last_pos = None
        # v2.7：小地圖預設鎖定自身，以自身周邊約 80 格作為初始視野。
        self.follow_self = True
        self.self_view_cells = 80.0
        self._needs_initial_self_focus = True
        # v2.13：傷害標籤的避讓結果只在第一次出現時決定；
        # 同一 SID→DID 在可見期間沿用同一組相對 offset，避免每幀左右跳。
        self._damage_label_layout = {}
        self._damage_label_last_seen = {}
        # v2.15：傷害箭頭/文字先畫到透明 overlay，人物 60FPS 時只貼快取圖。
        self._damage_overlay_image = None
        self._damage_overlay_dirty = True
        self._damage_overlay_last_data_sec = -9999.0
        # v2.18：技能名稱可選擇顯示；距離格數固定顯示。
        self.show_skill_names = False

        # v2.24：上方常駐說明精簡，只保留地圖 / 時間。
        # 地圖空白處懸停顯示圖例與操作方式；懸停單位標記則顯示該單位資料。
        self._default_hover_tooltip = (
            "標記：玩家=公會固定色（無公會藍）｜自身=同公會色＋黃白雙圈｜"
            "魔物=紅色菱形｜寵物=橘色點｜NPC=綠色方塊｜召喚=紫色點｜其他=灰點\n"
            "桃紅箭頭=傷害/距離｜左鍵選取｜右鍵單位看完整資料｜"
            "右鍵空白拖曳｜滾輪縮放｜同格單位會自動錯位"
        )
        self.setToolTip(self._default_hover_tooltip)

    @staticmethod
    def _unit_hover_tooltip(unit):
        if not unit:
            return ""
        if unit.get("is_self"):
            category_name = "自身"
        else:
            category_name = {
                "player": "玩家", "mob": "魔物", "pet": "寵物", "npc": "NPC",
                "companion": "召喚/傭兵", "other": "其他"
            }.get(unit.get("category"), "其他")
        guild_id = int(unit.get("guild_id", 0) or 0)
        guild_name = str(unit.get("guild_name") or "").strip()
        guild_text = f"{guild_name} [{guild_id}]" if guild_name else (f"GuildID {guild_id}" if guild_id else "無公會")
        name = str(unit.get("name") or "").strip() or f"AID {int(unit.get('aid', 0) or 0)}"
        return (
            f"{category_name}：{name}\n"
            f"AID {int(unit.get('aid', 0) or 0)}｜GID {int(unit.get('gid', 0) or 0)}\n"
            f"公會：{guild_text}\n"
            f"座標：({float(unit.get('x', 0) or 0):.1f}, {float(unit.get('y', 0) or 0):.1f})\n"
            f"ObjectType：0x{int(unit.get('object_type', 0) or 0):02X} "
            f"({unit.get('object_type_name', '')})"
        )

    def clear_map(self):
        self.gat = None
        self.map_image = None
        self.units = []
        self.damage_links = []
        self.selected_aid = None
        self.highlight_aid = None
        self.zoom_factor = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._panning = False
        self._pan_last_pos = None
        self.follow_self = True
        self._needs_initial_self_focus = True
        self._damage_label_layout.clear()
        self._damage_label_last_seen.clear()
        self._damage_overlay_image = None
        self._damage_overlay_dirty = True
        self.update()

    def set_gat(self, gat):
        self.gat = gat
        self.map_image = self._build_map_image(gat) if gat else None
        # 切圖時上一張地圖的傷害箭頭不能殘留到新 GAT。
        self.damage_links = []
        # 換圖後先等待自身座標，再自動以自身為中心縮放。
        self.zoom_factor = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._panning = False
        self._pan_last_pos = None
        self.follow_self = True
        self._needs_initial_self_focus = True
        self._damage_label_layout.clear()
        self._damage_label_last_seen.clear()
        self._damage_overlay_image = None
        self._damage_overlay_dirty = True
        self.update()

    def reset_view(self):
        """100%：顯示整張 GAT，並暫停自動跟隨自身。"""
        self.zoom_factor = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._panning = False
        self._pan_last_pos = None
        self.follow_self = False
        self._needs_initial_self_focus = False
        self._damage_overlay_dirty = True
        self.update()

    def _self_unit(self):
        for unit in self.units:
            if unit.get("is_self"):
                return unit
        return None

    def _center_on_map_point(self, x, y):
        if not self.gat:
            return
        # 先以零 pan 算出目前 zoom 的基準位置，再把指定地圖座標移到視窗中央。
        self.pan_x = 0.0
        self.pan_y = 0.0
        rect = self._map_rect()
        if not rect:
            return
        sx, sy = self._unit_to_screen(float(x), float(y), rect)
        self.pan_x = self.width() / 2.0 - sx
        self.pan_y = self.height() / 2.0 - sy
        self._clamp_pan()

    def focus_self(self, auto_zoom=True, request_update=True):
        """鎖定自身；auto_zoom=True 時把視野縮到自身周邊固定格數。"""
        if not self.gat:
            return False
        unit = self._self_unit()
        if not unit:
            self.follow_self = True
            self._needs_initial_self_focus = True
            return False

        self.follow_self = True
        if auto_zoom:
            w = max(1.0, float(self.gat["width"]))
            h = max(1.0, float(self.gat["height"]))
            margin = 12.0
            avail_w = max(1.0, self.width() - margin * 2)
            avail_h = max(1.0, self.height() - margin * 2)
            fit = min(avail_w / w, avail_h / h)
            target = max(20.0, float(self.self_view_cells))
            # 讓短邊大約可看到 target 格；長寬比不同時另一邊自然多看到一些。
            z_w = avail_w / max(1e-9, fit * target)
            z_h = avail_h / max(1e-9, fit * target)
            self.zoom_factor = max(1.0, min(20.0, min(z_w, z_h)))

        self._center_on_map_point(unit.get("x", 0.0), unit.get("y", 0.0))
        self._needs_initial_self_focus = False
        if request_update:
            self.update()
        return True

    def zoom_by(self, factor, anchor=None):
        if not self.gat:
            return
        old_zoom = float(self.zoom_factor)
        new_zoom = max(1.0, min(20.0, old_zoom * float(factor)))
        if abs(new_zoom - old_zoom) < 1e-9:
            return

        old_rect = self._map_rect()
        if anchor is None:
            ax = self.width() / 2.0
            ay = self.height() / 2.0
        else:
            ax = float(anchor.x())
            ay = float(anchor.y())

        # 保持滑鼠所在的 GAT 座標在縮放前後位於同一個螢幕位置。
        map_rx = 0.5
        map_ry = 0.5
        if old_rect:
            left, top, dw, dh = old_rect
            if dw > 0 and dh > 0:
                map_rx = (ax - left) / dw
                map_ry = (ay - top) / dh

        self.zoom_factor = new_zoom
        # 先以新 zoom 的置中矩形估算，再補 pan。
        self.pan_x = 0.0
        self.pan_y = 0.0
        base_rect = self._map_rect()
        if base_rect:
            left, top, dw, dh = base_rect
            self.pan_x = ax - map_rx * dw - left
            self.pan_y = ay - map_ry * dh - top
            self._clamp_pan()
        if self.follow_self and self._self_unit() is not None:
            unit = self._self_unit()
            self._center_on_map_point(unit.get("x", 0.0), unit.get("y", 0.0))
        self._damage_overlay_dirty = True
        self.update()

    def _clamp_pan(self):
        if not self.gat:
            self.pan_x = self.pan_y = 0.0
            return
        w = max(1, int(self.gat["width"]))
        h = max(1, int(self.gat["height"]))
        margin = 12.0
        avail_w = max(1.0, self.width() - margin * 2)
        avail_h = max(1.0, self.height() - margin * 2)
        fit = min(avail_w / w, avail_h / h)
        dw = w * fit * self.zoom_factor
        dh = h * fit * self.zoom_factor
        max_x = max(0.0, (dw - avail_w) / 2.0)
        max_y = max(0.0, (dh - avail_h) / 2.0)
        self.pan_x = max(-max_x, min(max_x, self.pan_x))
        self.pan_y = max(-max_y, min(max_y, self.pan_y))

    def _assign_units(self, units, current_sec=0.0):
        self.units = list(units or [])
        new_sec = float(current_sec or 0.0)
        # 往回 seek 時重新建立當下可見傷害標籤配置；往前播放則保持既有位置。
        if new_sec + 1e-9 < float(self.current_sec or 0.0):
            self._damage_label_layout.clear()
            self._damage_label_last_seen.clear()
        self.current_sec = new_sec
        if self.selected_aid is not None and not any(u.get("aid") == self.selected_aid for u in self.units):
            self.selected_aid = None

        # 第一次拿到自身座標時自動縮到自身周邊；之後播放時持續以自身為中心。
        if self._self_unit() is not None and self.follow_self:
            self.focus_self(auto_zoom=self._needs_initial_self_focus, request_update=False)

    def set_units(self, units, current_sec=0.0):
        self._assign_units(units, current_sec)
        self.update()

    def set_damage_links(self, links):
        """設定傷害 overlay。v2.15：只有資料真的更新時才重建透明快取圖。"""
        self.damage_links = list(links or [])
        self._damage_overlay_dirty = True
        self.update()

    def set_highlight_aid(self, aid):
        try:
            aid = int(aid) if aid is not None else None
        except (TypeError, ValueError):
            aid = None
        self.highlight_aid = aid
        self.update()

    def set_frame(self, units, links=None, current_sec=0.0, highlight_aid=None):
        """人物每幀更新；links=None 代表沿用上一張傷害 overlay，不做昂貴重畫。"""
        self._assign_units(units, current_sec)
        if links is not None:
            self.damage_links = list(links or [])
            self._damage_overlay_dirty = True
            self._damage_overlay_last_data_sec = float(current_sec or 0.0)
        try:
            self.highlight_aid = int(highlight_aid) if highlight_aid is not None else None
        except (TypeError, ValueError):
            self.highlight_aid = None
        self.update()

    def set_show_skill_names(self, enabled):
        enabled = bool(enabled)
        if self.show_skill_names == enabled:
            return
        self.show_skill_names = enabled
        self._damage_overlay_dirty = True
        self.update()

    def _compute_unit_visual_offsets(self):
        """同一格有多個單位時只做畫面像素偏移，不改 Replay/GAT 真實座標。"""
        groups = defaultdict(list)
        for unit in self.units:
            try:
                key = (round(float(unit.get("x", 0.0)), 2), round(float(unit.get("y", 0.0)), 2))
            except Exception:
                continue
            groups[key].append(unit)

        offsets = {}
        for group in groups.values():
            if len(group) <= 1:
                aid = int(group[0].get("aid", 0) or 0) if group else 0
                if aid:
                    offsets[aid] = (0.0, 0.0)
                continue

            ordered = sorted(group, key=lambda u: (0 if u.get("is_self") else 1, int(u.get("aid", 0) or 0)))
            remaining = ordered
            if ordered and ordered[0].get("is_self"):
                aid = int(ordered[0].get("aid", 0) or 0)
                if aid:
                    offsets[aid] = (0.0, 0.0)
                remaining = ordered[1:]

            total = len(remaining)
            for idx, unit in enumerate(remaining):
                ring = idx // 8
                pos = idx % 8
                ring_start = ring * 8
                ring_count = min(8, total - ring_start)
                radius = 10.0 + ring * 9.0
                angle = -math.pi / 2.0 + (2.0 * math.pi * pos / max(1, ring_count))
                aid = int(unit.get("aid", 0) or 0)
                if aid:
                    offsets[aid] = (math.cos(angle) * radius, math.sin(angle) * radius)
        return offsets

    def _hit_test_unit(self, pos, radius=13.0):
        best = None
        best_d2 = float(radius) * float(radius)
        # 後畫的 marker 優先，和畫面視覺層級一致。
        for sx, sy, unit in reversed(self._unit_screen_points):
            dx = float(pos.x()) - float(sx)
            dy = float(pos.y()) - float(sy)
            d2 = dx * dx + dy * dy
            if d2 <= best_d2:
                best_d2 = d2
                best = unit
        return best

    def _build_map_image(self, gat):
        w = int(gat["width"])
        h = int(gat["height"])
        terrain = gat["terrain"]
        water = gat.get("water") or [False] * len(terrain)
        image = QImage(w, h, QImage.Format_RGB32)

        c_walk = QColor(224, 224, 224)
        c_block = QColor(55, 55, 55)
        c_cliff = QColor(110, 110, 110)
        c_other = QColor(150, 150, 150)
        c_water = QColor(120, 160, 190)

        for y in range(h):
            row = y * w
            py = h - 1 - y  # GAT/map 座標原點在左下；Qt image 原點在左上。
            for x in range(w):
                idx = row + x
                typ = terrain[idx]
                if water[idx]:
                    color = c_water
                elif typ == 0:
                    color = c_walk
                elif typ == 1:
                    color = c_block
                elif typ == 5:
                    color = c_cliff
                else:
                    color = c_other
                image.setPixelColor(x, py, color)
        return image

    def _map_rect(self):
        if not self.gat:
            return None
        w = max(1, int(self.gat["width"]))
        h = max(1, int(self.gat["height"]))
        margin = 12.0
        avail_w = max(1.0, self.width() - margin * 2)
        avail_h = max(1.0, self.height() - margin * 2)
        scale = min(avail_w / w, avail_h / h) * max(1.0, float(self.zoom_factor))
        dw = w * scale
        dh = h * scale
        left = (self.width() - dw) / 2.0 + float(self.pan_x)
        top = (self.height() - dh) / 2.0 + float(self.pan_y)
        return left, top, dw, dh

    def _unit_to_screen(self, x, y, rect):
        left, top, dw, dh = rect
        mw = max(1.0, float(self.gat["width"]))
        mh = max(1.0, float(self.gat["height"]))
        sx = left + (float(x) / mw) * dw
        sy = top + (1.0 - float(y) / mh) * dh
        return sx, sy


    def _render_damage_overlay(self, rect):
        """v2.15：把箭頭/傷害文字一次畫到透明 QImage；一般 60FPS frame 只貼快取。"""
        w = max(1, int(self.width()))
        h = max(1, int(self.height()))
        image = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        # v2.11：以高對比桃紅色畫最近 1 秒傷害關係線，傷害文字會自動避讓。
        # 線尾的箭頭指向受方 DID；同一攻方→受方在該時間窗內會先合併。
        if self.damage_links:
            painter.setRenderHint(QPainter.Antialiasing, True)

            # 傷害數字使用貪婪式 label placement：每個標籤依序嘗試
            # 線段法向兩側、再沿線前後錯開，盡量不和前面的標籤重疊。
            # 極端密集時選擇重疊面積最小的位置，而不是全部堆在線段中點。
            damage_label_rects = []
            damage_label_index = 0
            # 近距離戰鬥時也把單位 marker 當作避讓障礙，傷害文字優先往外排。
            visual_offsets = self._compute_unit_visual_offsets()
            unit_obstacles = []
            for obstacle_unit in self.units:
                ox = obstacle_unit.get("x")
                oy = obstacle_unit.get("y")
                if ox is None or oy is None:
                    continue
                osx, osy = self._unit_to_screen(ox, oy, rect)
                offx, offy = visual_offsets.get(int(obstacle_unit.get("aid", 0) or 0), (0.0, 0.0))
                osx += offx
                osy += offy
                unit_obstacles.append(QRectF(osx - 10.0, osy - 10.0, 20.0, 20.0))

            def _label_overlap_score(candidate):
                padded = candidate.adjusted(-4.0, -3.0, 4.0, 3.0)
                score = 0.0
                for used in damage_label_rects:
                    inter = padded.intersected(used.adjusted(-4.0, -3.0, 4.0, 3.0))
                    if not inter.isEmpty():
                        score += max(0.0, inter.width()) * max(0.0, inter.height())
                for obstacle in unit_obstacles:
                    inter = padded.intersected(obstacle)
                    if not inter.isEmpty():
                        # 單位本體比文字彼此重疊更重要，給更高懲罰。
                        score += 2.5 * max(0.0, inter.width()) * max(0.0, inter.height())
                return score

            # 已有固定配置的 label 先畫，讓新出現的 label 主動避開舊位置；
            # 排序本身固定，不再受 damage/age 每幀變化影響。
            def _damage_link_key(link):
                return (int(link.get("sid", 0) or 0), int(link.get("did", 0) or 0))

            ordered_damage_links = sorted(
                self.damage_links,
                key=lambda link: (
                    0 if _damage_link_key(link) in self._damage_label_layout else 1,
                    _damage_link_key(link),
                )
            )

            for link in ordered_damage_links:
                try:
                    x1, y1 = float(link.get("source_x")), float(link.get("source_y"))
                    x2, y2 = float(link.get("target_x")), float(link.get("target_y"))
                except (TypeError, ValueError):
                    continue
                sx1, sy1 = self._unit_to_screen(x1, y1, rect)
                sx2, sy2 = self._unit_to_screen(x2, y2, rect)
                # 同格單位 marker 只做視覺錯位；箭頭端點同步指向錯位後的 marker。
                source_off = visual_offsets.get(int(link.get("sid", 0) or 0), (0.0, 0.0))
                target_off = visual_offsets.get(int(link.get("did", 0) or 0), (0.0, 0.0))
                sx1 += source_off[0]
                sy1 += source_off[1]
                sx2 += target_off[0]
                sy2 += target_off[1]
                dx = sx2 - sx1
                dy = sy2 - sy1
                dist = math.hypot(dx, dy)
                # v2.12：近身/重疊座標也不能丟掉傷害。
                # 幾乎同點時使用穩定的虛擬方向，只用於箭頭/文字避讓，不改變實際座標。
                if dist >= 1.0:
                    ux = dx / dist
                    uy = dy / dist
                else:
                    ux, uy = 1.0, 0.0
                px = -uy
                py = ux

                age = max(0.0, float(link.get("age", 0.0) or 0.0))
                alpha = int(max(80, min(235, 235 - age * 135)))
                total_damage = max(0, int(link.get("damage", 0) or 0))
                width = 2 if total_damage < 1000000 else 3
                line_color = QColor(220, 20, 120, alpha)
                painter.setPen(QPen(line_color, width))
                painter.setBrush(QBrush(line_color))
                if dist >= 1.0:
                    painter.drawLine(int(sx1), int(sy1), int(sx2), int(sy2))
                else:
                    # 完全重疊時以小圓脈衝表示此處有攻擊關係，傷害數字仍會顯示。
                    painter.setBrush(Qt.NoBrush)
                    painter.drawEllipse(int(sx2 - 7), int(sy2 - 7), 14, 14)
                    painter.setBrush(QBrush(line_color))

                # 箭頭放在目標點前，方向由 SID → DID。距離太短時不硬塞箭頭，避免蓋滿單位點。
                if dist >= 10.0:
                    tip_x = sx2 - ux * 7.0
                    tip_y = sy2 - uy * 7.0
                    arrow_len = 8.0
                    arrow_w = 4.0
                    bx = tip_x - ux * arrow_len
                    by = tip_y - uy * arrow_len
                    painter.drawLine(int(tip_x), int(tip_y), int(bx + px * arrow_w), int(by + py * arrow_w))
                    painter.drawLine(int(tip_x), int(tip_y), int(bx - px * arrow_w), int(by - py * arrow_w))

                # v2.16：勾選「傷害 0」時，0 傷害攻擊也要顯示標籤。
                # link 本身存在就代表至少有一筆攻擊事件，因此 0 也顯示。
                if int(link.get("count", 0) or 0) > 0:
                    count = max(1, int(link.get("count", 1) or 1))
                    damage_text = f"{total_damage:,}"
                    if count > 1:
                        damage_text += f" ×{count}"

                    # Ragnarok 的格數/技能 range 使用格子距離概念：max(|dx|, |dy|)。
                    grid_distance = max(abs(x2 - x1), abs(y2 - y1))
                    if abs(grid_distance - round(grid_distance)) < 0.05:
                        distance_text = f"距離 {int(round(grid_distance))}格"
                    else:
                        distance_text = f"距離 {grid_distance:.1f}格"
                    detail_line = f"{damage_text}｜{distance_text}"

                    label_lines = []
                    if self.show_skill_names:
                        skills = [str(x) for x in (link.get("skills") or []) if str(x).strip()]
                        if skills:
                            skill_text = skills[0]
                            if len(skills) > 1:
                                skill_text += f" +{len(skills) - 1}"
                            label_lines.append(skill_text)
                    label_lines.append(detail_line)
                    label = "\n".join(label_lines)

                    mx = (sx1 + sx2) / 2.0
                    my = (sy1 + sy2) / 2.0
                    fm = painter.fontMetrics()
                    text_w = max(1.0, max(float(fm.horizontalAdvance(line)) for line in label_lines))
                    text_h = max(1.0, float(fm.height()) * len(label_lines))
                    box_w = text_w + 12.0
                    box_h = text_h + 6.0

                    # v2.13：同一 SID→DID 的 label offset 一旦選定，在這條傷害關係
                    # 可見期間就固定，不再每 16ms 重新避讓而左右跳。人物移動時標籤只會
                    # 跟著該攻擊線平滑移動，側邊/前後 offset 不改變。
                    label_key = (int(link.get("sid", 0) or 0), int(link.get("did", 0) or 0))
                    cached_layout = self._damage_label_layout.get(label_key)
                    base_off = 24.0 if dist < 48.0 else 13.0

                    if cached_layout is not None:
                        candidate_offsets = [(
                            float(cached_layout.get("perp", base_off)),
                            float(cached_layout.get("along", 0.0)),
                        )]
                    else:
                        # 左/右側由 SID/DID 固定決定，不依當前列表排序。
                        side = 1.0 if ((label_key[0] * 31 + label_key[1]) & 1) == 0 else -1.0
                        perp_offsets = [
                            base_off * side, -base_off * side,
                            (base_off + 16.0) * side, -(base_off + 16.0) * side,
                            (base_off + 32.0) * side, -(base_off + 32.0) * side,
                            (base_off + 50.0) * side, -(base_off + 50.0) * side,
                            (base_off + 68.0) * side, -(base_off + 68.0) * side,
                        ]
                        along_offsets = [0.0, 20.0, -20.0, 40.0, -40.0, 60.0, -60.0]
                        candidate_offsets = [
                            (perp_off, along_off)
                            for perp_off in perp_offsets
                            for along_off in along_offsets
                        ]

                    best_rect = None
                    best_score = None
                    best_offsets = None
                    for perp_off, along_off in candidate_offsets:
                        cx = mx + px * perp_off + ux * along_off
                        cy = my + py * perp_off + uy * along_off
                        rx = cx - box_w / 2.0
                        ry = cy - box_h / 2.0

                        # 保持文字在 widget 可視範圍內。
                        rx = max(3.0, min(max(3.0, self.width() - box_w - 3.0), rx))
                        ry = max(3.0, min(max(3.0, self.height() - box_h - 3.0), ry))
                        candidate = QRectF(rx, ry, box_w, box_h)

                        if cached_layout is not None:
                            # v2.14：固定標籤已經在第一次出現時完成避讓；後續每幀直接
                            # 沿用 offset，不再和所有 label / unit 做 O(N²) overlap 掃描。
                            best_rect = candidate
                            best_score = 0.0
                            best_offsets = (perp_off, along_off)
                            break

                        score = _label_overlap_score(candidate)
                        if best_score is None or score < best_score:
                            best_rect = candidate
                            best_score = score
                            best_offsets = (perp_off, along_off)
                        if score <= 0.0:
                            break

                    if best_rect is not None:
                        if cached_layout is None and best_offsets is not None:
                            self._damage_label_layout[label_key] = {
                                "perp": float(best_offsets[0]),
                                "along": float(best_offsets[1]),
                            }
                        self._damage_label_last_seen[label_key] = float(self.current_sec or 0.0)
                        damage_label_rects.append(QRectF(best_rect))
                        damage_label_index += 1

                        # 標籤被挪開時，用細引導線指回原本攻擊線中點。
                        cx = best_rect.center().x()
                        cy = best_rect.center().y()
                        if math.hypot(cx - mx, cy - my) > 17.0:
                            painter.setPen(QPen(QColor(135, 25, 85, max(70, alpha - 55)), 1))
                            painter.drawLine(int(mx), int(my), int(cx), int(cy))

                        # 淡色底框提升白色 GAT 上的可讀性，也讓相鄰數字邊界更清楚。
                        painter.setPen(QPen(QColor(145, 15, 85, alpha), 1))
                        painter.setBrush(QBrush(QColor(255, 244, 250, max(155, alpha - 20))))
                        painter.drawRoundedRect(best_rect, 3.0, 3.0)
                        painter.setPen(QColor(105, 0, 60, alpha))
                        painter.drawText(best_rect, Qt.AlignCenter | Qt.TextWordWrap, label)

        # 只保留最近仍可見的傷害關係配置；消失一段時間後重新出現時可重新避讓。
        if self._damage_label_last_seen:
            now_sec = float(self.current_sec or 0.0)
            stale_keys = [
                key for key, last_seen in self._damage_label_last_seen.items()
                if now_sec - float(last_seen) > 1.5
            ]
            for key in stale_keys:
                self._damage_label_last_seen.pop(key, None)
                self._damage_label_layout.pop(key, None)

        painter.end()
        return image

    @staticmethod
    def _guild_color(guild_id, guild_name=""):
        """同公會固定同色。優先 GuildID；自身缺 GuildID 時可由公會名稱穩定配色。"""
        try:
            gid = int(guild_id or 0)
        except Exception:
            gid = 0
        if gid > 0:
            hue = int((gid * 137.508 + 29.0) % 360.0)
            return QColor.fromHsv(hue, 190, 225)
        name = str(guild_name or "").strip()
        if not name:
            return None
        digest = hashlib.blake2s(name.encode("utf-8", errors="ignore"), digest_size=4).digest()
        value = int.from_bytes(digest, "little")
        hue = int((value * 137.508 + 29.0) % 360.0)
        return QColor.fromHsv(hue, 190, 225)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(28, 28, 28))

        if not self.gat or self.map_image is None:
            painter.setPen(QColor(220, 220, 220))
            painter.drawText(self.rect(), Qt.AlignCenter, "請載入 .gat 地圖")
            return

        rect = self._map_rect()
        self._last_draw_rect = rect
        left, top, dw, dh = rect
        painter.save()
        painter.setClipRect(self.rect())
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        # v2.12：不要每幀建立 map_image.scaled() 巨大暫存圖。
        # 只把目前 widget 真正看得到的 GAT 區域直接縮放到畫面，播放/跟隨自身時成本大幅降低。
        map_target = QRectF(float(left), float(top), float(dw), float(dh))
        visible = map_target.intersected(QRectF(self.rect()))
        if not visible.isEmpty() and dw > 0 and dh > 0:
            src_w = float(self.map_image.width())
            src_h = float(self.map_image.height())
            src_left = (visible.left() - left) / dw * src_w
            src_top = (visible.top() - top) / dh * src_h
            src_width = visible.width() / dw * src_w
            src_height = visible.height() / dh * src_h
            source_rect = QRectF(src_left, src_top, src_width, src_height)
            painter.drawImage(visible, self.map_image, source_rect)
        painter.restore()

        # v2.15：傷害 overlay 與人物渲染解耦。人物可 60 FPS；箭頭/文字只有
        # 傷害資料更新、縮放/平移/尺寸改變時才重建，其餘 frame 直接貼透明快取。
        overlay_size_bad = (
            self._damage_overlay_image is None
            or self._damage_overlay_image.width() != self.width()
            or self._damage_overlay_image.height() != self.height()
        )
        if self._damage_overlay_dirty or overlay_size_bad:
            self._damage_overlay_image = self._render_damage_overlay(rect)
            self._damage_overlay_dirty = False
        if self._damage_overlay_image is not None:
            painter.drawImage(0, 0, self._damage_overlay_image)

        # 固定類型配色/形狀；Replay seek / 切圖時不重新分配。
        player_color = QColor(55, 165, 255)      # PC_TYPE(0)：玩家，藍色
        mob_color = QColor(245, 75, 75)           # NPC_MOB_TYPE(5)：魔物，紅色
        pet_color = QColor(255, 165, 45)           # NPC_PET_TYPE(7)：寵物，橘色
        npc_color = QColor(70, 205, 110)           # NPC_EVT_TYPE(6/12)：NPC，綠色
        companion_color = QColor(180, 105, 255)    # HOM/MER/ELEM/ABR/BIONIC：紫色
        other_color = QColor(190, 190, 190)        # 其他：灰點
        self_color = QColor(255, 215, 50)           # 自身：黃色雙圈

        painter.setRenderHint(QPainter.Antialiasing, True)
        self._unit_screen_points = []

        # v2.18：同一 GAT 格的單位以畫面像素做環狀錯位，真實座標不變。
        visual_offsets = self._compute_unit_visual_offsets()
        # 自身最後畫，避免和其他單位重疊時被蓋住。
        draw_units = sorted(self.units, key=lambda u: bool(u.get("is_self")))
        for unit in draw_units:
            x = unit.get("x")
            y = unit.get("y")
            if x is None or y is None:
                continue
            sx, sy = self._unit_to_screen(x, y, rect)
            offx, offy = visual_offsets.get(int(unit.get("aid", 0) or 0), (0.0, 0.0))
            sx += offx
            sy += offy
            category = unit.get("category")
            is_self = bool(unit.get("is_self"))

            painter.setPen(QPen(QColor(20, 20, 20), 1))
            guild_color = self._guild_color(unit.get("guild_id"), unit.get("guild_name")) if category == "player" or is_self else None
            if is_self:
                radius = 5
                painter.setBrush(QBrush(guild_color or self_color))
                painter.drawEllipse(int(sx - radius), int(sy - radius), radius * 2, radius * 2)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(255, 215, 50), 2))
                painter.drawEllipse(int(sx - 9), int(sy - 9), 18, 18)
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.drawEllipse(int(sx - 7), int(sy - 7), 14, 14)
            elif category == "player":
                radius = 4
                painter.setBrush(QBrush(guild_color or player_color))
                painter.drawEllipse(int(sx - radius), int(sy - radius), radius * 2, radius * 2)
            elif category == "mob":
                # 魔物：紅色菱形。
                painter.save()
                painter.translate(float(sx), float(sy))
                painter.rotate(45.0)
                painter.setBrush(QBrush(mob_color))
                painter.drawRect(-4, -4, 8, 8)
                painter.restore()
            elif category == "pet":
                radius = 4
                painter.setBrush(QBrush(pet_color))
                painter.drawEllipse(int(sx - radius), int(sy - radius), radius * 2, radius * 2)
                painter.setBrush(QBrush(QColor(40, 40, 40)))
                painter.drawEllipse(int(sx - 1), int(sy - 1), 2, 2)
            elif category == "npc":
                half = 4
                painter.setBrush(QBrush(npc_color))
                painter.drawRect(int(sx - half), int(sy - half), half * 2, half * 2)
            elif category == "companion":
                radius = 4
                painter.setBrush(QBrush(companion_color))
                painter.drawEllipse(int(sx - radius), int(sy - radius), radius * 2, radius * 2)
            else:
                radius = 3
                painter.setBrush(QBrush(other_color))
                painter.drawEllipse(int(sx - radius), int(sy - radius), radius * 2, radius * 2)

            # v2.12：右上「篩選魔物」鎖定 DID 時，以青色準星/雙圈特別標示該魔物。
            if (self.highlight_aid is not None and unit.get("aid") == self.highlight_aid
                    and category == "mob"):
                painter.setBrush(Qt.NoBrush)
                lock_color = QColor(0, 180, 255)
                painter.setPen(QPen(lock_color, 3))
                painter.drawEllipse(int(sx - 11), int(sy - 11), 22, 22)
                painter.setPen(QPen(QColor(0, 70, 120), 1))
                painter.drawEllipse(int(sx - 14), int(sy - 14), 28, 28)
                # 四向準星，比單純換色更容易在密集魔物中辨認。
                painter.setPen(QPen(lock_color, 2))
                painter.drawLine(int(sx), int(sy - 18), int(sx), int(sy - 12))
                painter.drawLine(int(sx), int(sy + 12), int(sx), int(sy + 18))
                painter.drawLine(int(sx - 18), int(sy), int(sx - 12), int(sy))
                painter.drawLine(int(sx + 12), int(sy), int(sx + 18), int(sy))

            if unit.get("aid") == self.selected_aid:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.drawEllipse(int(sx - 10), int(sy - 10), 20, 20)

                # v2.26：選取單位名稱加深色半透明底框與亮色外框，
                # 避免白字直接壓在亮色/複雜 GAT 背景上看不清楚。
                label = str(unit.get("name") or f"AID {unit.get('aid')}")
                fm = painter.fontMetrics()
                text_w = max(1, fm.horizontalAdvance(label))
                text_h = max(1, fm.height())
                text_x = float(sx + 11)
                text_y = float(sy - 7)
                pad_x, pad_y = 5.0, 3.0
                label_rect = QRectF(
                    text_x - pad_x,
                    text_y - float(fm.ascent()) - pad_y,
                    float(text_w) + pad_x * 2.0,
                    float(text_h) + pad_y * 2.0,
                )
                painter.setPen(QPen(QColor(235, 235, 235, 235), 1))
                painter.setBrush(QBrush(QColor(20, 20, 20, 205)))
                painter.drawRoundedRect(label_rect, 4.0, 4.0)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(int(text_x), int(text_y), label)

            self._unit_screen_points.append((sx, sy, unit))

        # 邊框最後畫，讓地圖範圍清楚。
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(210, 210, 210), 1))
        painter.drawRect(int(left), int(top), max(1, int(dw)), max(1, int(dh)))

    def wheelEvent(self, event):
        # 滾輪以游標位置為中心縮放。
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.zoom_by(1.20 ** steps, event.position())
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        pos = event.position()
        if event.button() == Qt.RightButton:
            hit = self._hit_test_unit(pos)
            if hit is not None:
                self.selected_aid = hit.get("aid")
                self.unitSelected.emit(hit)
                self.unitContextRequested.emit(hit)
                self.update()
                event.accept()
                return

        if event.button() in (Qt.RightButton, Qt.MiddleButton):
            # 右鍵空白/中鍵仍保留平移；右鍵點單位則改為完整資料。
            self.follow_self = False
            self._needs_initial_self_focus = False
            self._panning = True
            self._pan_last_pos = pos
            event.accept()
            return

        best = self._hit_test_unit(pos)
        if best is not None:
            self.selected_aid = best.get("aid")
            self.unitSelected.emit(best)
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_last_pos is not None:
            pos = event.position()
            self.pan_x += pos.x() - self._pan_last_pos.x()
            self.pan_y += pos.y() - self._pan_last_pos.y()
            self._pan_last_pos = pos
            self._clamp_pan()
            self._damage_overlay_dirty = True
            self.update()
            event.accept()
            return

        # v2.24：標記資訊改成 hover Tooltip，不再占用小地圖上方常駐文字。
        hit = self._hit_test_unit(event.position())
        if hit is not None:
            self.setToolTip(self._unit_hover_tooltip(hit))
        else:
            self.setToolTip(self._default_hover_tooltip)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() in (Qt.RightButton, Qt.MiddleButton) and self._panning:
            self._panning = False
            self._pan_last_pos = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        if self.follow_self and self._self_unit() is not None:
            unit = self._self_unit()
            self._center_on_map_point(unit.get("x", 0.0), unit.get("y", 0.0))
        else:
            self._clamp_pan()
        self._damage_overlay_dirty = True
        super().resizeEvent(event)


class GATMiniMapWindow(QWidget):
    """v2.18：可縮放/跟隨、自動錯位、傷害距離與單位完整資料的小地圖。"""
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Replay 場上小地圖")
        self.resize(720, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        top = QHBoxLayout()
        self.map_label = QLabel("地圖：尚未取得")
        self.map_label.setToolTip("地圖詳細資訊會在載入後顯示於此提示")
        top.addWidget(self.map_label)
        self.count_label = QLabel("時間 00:00:00.000")
        self.count_label.setToolTip("單位數量與傷害線統計會顯示於此提示")
        top.addWidget(self.count_label)
        top.addStretch(1)
        self.zoom_out_btn = QPushButton("－")
        self.zoom_out_btn.setFixedWidth(36)
        top.addWidget(self.zoom_out_btn)
        self.zoom_reset_btn = QPushButton("100%")
        self.zoom_reset_btn.setFixedWidth(58)
        top.addWidget(self.zoom_reset_btn)
        self.focus_self_btn = QPushButton("自身")
        self.focus_self_btn.setFixedWidth(58)
        top.addWidget(self.focus_self_btn)
        self.zoom_in_btn = QPushButton("＋")
        self.zoom_in_btn.setFixedWidth(36)
        top.addWidget(self.zoom_in_btn)
        self.load_gat_btn = QPushButton("載入 .gat")
        top.addWidget(self.load_gat_btn)
        self.show_skill_name_checkbox = QCheckBox("顯示技能名稱")
        self.show_skill_name_checkbox.setChecked(False)
        top.addWidget(self.show_skill_name_checkbox)
        layout.addLayout(top)

        # v2.22：Replay 控制列移到小地圖上方。
        # 與主畫面共用同一個 playhead / 播放狀態，只是提供第二組控制器。
        jump_row = QHBoxLayout()
        jump_row.addWidget(QLabel("快速跳轉："))
        self.playback_jump_buttons = []
        for text, delta in (("−1分", -60.0), ("−10秒", -10.0), ("−1秒", -1.0),
                            ("+1秒", 1.0), ("+10秒", 10.0), ("+1分", 60.0)):
            btn = QPushButton(text)
            btn.setFixedWidth(58)
            btn.clicked.connect(lambda _checked=False, d=delta: parent.jump_damage_playback(d) if parent else None)
            self.playback_jump_buttons.append(btn)
            jump_row.addWidget(btn)
        jump_row.addStretch(1)
        layout.addLayout(jump_row)

        playback_row = QHBoxLayout()
        playback_row.addWidget(QLabel("Replay時間："))
        self.playback_btn = QPushButton("▶ 播放")
        self.playback_btn.setFixedWidth(82)
        self.playback_btn.clicked.connect(lambda: parent.toggle_damage_playback() if parent else None)
        playback_row.addWidget(self.playback_btn)

        # v2.26：小地圖也提供 Replay 播放倍速，與主 UI 共用同一個值。
        from PySide6.QtWidgets import QDoubleSpinBox, QAbstractSpinBox
        playback_row.addWidget(QLabel("倍速："))
        self.playback_speed_input = QDoubleSpinBox()
        self.playback_speed_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.playback_speed_input.setRange(0.1, 4.0)
        self.playback_speed_input.setSingleStep(0.1)
        self.playback_speed_input.setDecimals(1)
        self.playback_speed_input.setPrefix("x")
        self.playback_speed_input.setValue(
            float(getattr(parent, "damage_playback_speed", 1.0) or 1.0) if parent else 1.0
        )
        self.playback_speed_input.setFixedWidth(70)
        if parent:
            self.playback_speed_input.valueChanged.connect(
                lambda value: parent.damage_playback_speed_input.setValue(value)
                if hasattr(parent, "damage_playback_speed_input") else parent.on_damage_playback_speed_changed(value)
            )
        playback_row.addWidget(self.playback_speed_input)

        self.playback_slider = QSlider(Qt.Horizontal)
        self.playback_slider.setRange(0, 0)
        self.playback_slider.setSingleStep(100)
        self.playback_slider.setPageStep(1000)
        playback_row.addWidget(self.playback_slider, 1)

        self.playback_time_label = QLabel("00:00:00.000 / 00:00:00.000")
        self.playback_time_label.setMinimumWidth(210)
        self.playback_time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        playback_row.addWidget(self.playback_time_label)
        layout.addLayout(playback_row)

        # v2.24：圖例與操作說明不再常駐；改由地圖空白處 hover 顯示。
        self.legend_label = QLabel("")
        self.legend_label.hide()
        self.selected_label = QLabel("")
        self.selected_label.hide()

        self.map_widget = GATMiniMapWidget(self)
        layout.addWidget(self.map_widget, 1)

        if parent:
            self.playback_slider.sliderPressed.connect(parent.on_minimap_playback_slider_pressed)
            self.playback_slider.valueChanged.connect(parent.on_minimap_playback_slider_value_changed)
            self.playback_slider.sliderReleased.connect(parent.on_minimap_playback_slider_released)

        self.zoom_out_btn.clicked.connect(lambda: self.map_widget.zoom_by(1 / 1.25))
        self.zoom_in_btn.clicked.connect(lambda: self.map_widget.zoom_by(1.25))
        self.zoom_reset_btn.clicked.connect(self.map_widget.reset_view)
        self.focus_self_btn.clicked.connect(lambda: self.map_widget.focus_self(auto_zoom=True))
        self.show_skill_name_checkbox.stateChanged.connect(
            lambda _state: self.map_widget.set_show_skill_names(self.show_skill_name_checkbox.isChecked())
        )


# ============================================================
# PySide6 使用者介面
# ============================================================
class MainUI(QWidget):
    def __init__(self):
        from collections import defaultdict
        self.is_did_popup_open = False
        self.is_sid_popup_open = False
        self.worker_thread = None
        self.worker = None
        self.is_processing = False
        self.background_enabled = False
        self.rrf_thread = None
        self.rrf_worker = None
        self.rrf_reader = None   # RRFIncrementalReader，跨更新保留 packet cursor
        self.mouse_paused = False
        self.current_chart_mode = "bar"   # bar / line / stairs
        self.chart_status_text = "尚未載入資料"
        # v1.4：時間區間圈選。使用 replay 絕對秒數，避免切換圖表後座標基準改變。
        self.damage_time_range = None        # None 或 (start_sec, end_sec)
        self._span_selector = None

        # v2.0：全介面 Replay 線性播放。
        # 滑桿使用「相對於目前可播放範圍起點」的毫秒值，避免長 Replay 的絕對秒數
        # 造成 QSlider 整數範圍過大。
        self.damage_playback_mode = False
        self.damage_playback_running = False
        self.damage_playback_range_start = 0.0
        self.damage_playback_range_end = 0.0
        self.damage_playback_anchor_sec = 0.0
        self.damage_playback_current_sec = 0.0
        self.damage_playback_source = []
        self.damage_playback_times = []
        self.damage_playback_cursor = 0
        self.damage_playback_wall_t0 = 0.0
        self.damage_playback_base_sec = 0.0
        # v2.17：Replay 播放倍速，0.1x ～ 4.0x。
        self.damage_playback_speed = 1.0
        self._playback_resume_after_seek = False
        # v2.1：滑桿拖曳時即時更新全介面；用短節流避免高速拖曳造成 UI 重算塞車。
        self._playback_pending_seek_sec = None
        self._playback_last_live_seek_sec = None
        self.hud = DamageHUD()
        self.hud.hide()
        super().__init__()
        self.setWindowTitle("RRF傷害解析器 v2.24")
        self.resize(1100, 900)
        self.transform_end_time = {}#結束變身時間
        self.transform_start_time = {}#變身時間    
        self.transform_original_skin = {}#紀錄連續變身的id
        self.transform_history = defaultdict(list)
         # ===== 增量讀取 temp/copy.txt 用 =====
        self.txt_last_path = None
        self.txt_last_pos = 0
        self.txt_pending = ""          # 上次沒收完整的半包
        self.first_full_parse_done = False

        # ===== 增量解析需要保留的狀態 =====
        from collections import defaultdict
        self.ground_history = defaultdict(list)   # 取代 merge_with_true_sid 裡的區域變數
        self.raw_data = []
        self.parsed_data = []
        self.drop_data = []
        self.current_drop_data = []
        self.current_drop_filtered_raw = []
        self.vanish_points = []
        self.sid_name_map = {}
        self.did_name_map = {}
        self.did_name_source = {}
        self.self_sid = 0
        self.guild_id_name_map = {}
        self.guild_aid_name_map = {}
        self.guild_aid_id_map = {}
        self.self_guild_id = 0
        self.self_guild_name = ""
        self.current_map_name = ""

        # v2.12：GAT 小地圖 / actor replay timeline + 60FPS 輕量渲染、鎖定目標與近距離傷害。
        # actor_map_events 內也會混入 kind=map_change，讓 seek / playback 能重建切圖狀態。
        self.actor_map_events = []
        self.gat_data = None
        self.gat_path = ""
        self._gat_autoload_attempted_map = None
        self._minimap_loaded_map_name = ""
        self._minimap_active_map_name = ""
        self._minimap_actor_state = {}
        self._minimap_recent_positions = {}
        self._minimap_event_cursor = 0
        self._minimap_state_time = -1.0
        # v2.12：小地圖傷害線使用時間索引，60FPS 時只掃最近 1 秒的事件。
        self._minimap_damage_index_signature = None
        self._minimap_damage_times = []
        self._minimap_damage_rows = []

        # v2.16：延續小地圖計算 process + 傷害 overlay 快取，並支援可選的 damage==0 攻擊事件。
        self._minimap_compute_ctx = None
        self._minimap_compute_process = None
        self._minimap_source_queue = None
        self._minimap_request_queue = None
        self._minimap_result_queue = None
        self._minimap_compute_source_version = 0
        self._minimap_compute_request_seq = 0
        self._minimap_last_applied_seq = -1
        self._minimap_async_ready = False
        self._minimap_async_last_error = ""
        # v2.15：位置快照 60FPS，但傷害資料/overlay 只約 10FPS 更新。
        self._minimap_damage_request_interval = 0.10
        self._minimap_last_damage_request_wall = -9999.0
        self._minimap_last_damage_request_sec = -9999.0
        self._minimap_last_damage_filter_sig = None
        self._minimap_last_damage_line_count = 0
        self._minimap_last_damage_event_count = 0

        # v1.3：封包完整解析改用 QTableView + Model 虛擬表格，不建立大量 Tree Item。
        self._packet_decode_reload_pending = False
        self._packet_decode_reload_in_progress = False
         
        # 內容指紋快取
        self.last_txt_signature = None
        self.last_txt_path = None
         
        # 主要布局（已經有一個 QVBoxLayout）
        layout = QVBoxLayout(self)

        # 按鈕布局：將「載入檔案」和「停止」按鈕放在同一行
        btn_layout = QHBoxLayout()  # 使用 HBoxLayout 將按鈕放在同一行

        # 載入按鈕
        self.load_btn = QPushButton("載入傷害表")
        self.load_btn.clicked.connect(self.load_file)
        btn_layout.addWidget(self.load_btn)
        # 暫停按鈕（不重設秒數）
        #self.pause_btn = QPushButton("暫停")
        #self.pause_btn.clicked.connect(self.pause_update)
        #btn_layout.addWidget(self.pause_btn)

        # 停止按鈕
        self.stop_btn = QPushButton("停止更新並將秒數設為0")
        self.stop_btn.setFixedWidth(200)
        self.stop_btn.clicked.connect(self.stop_update)
        btn_layout.addWidget(self.stop_btn)
        # 所有 QCheckBox 選項集中到彈出視窗，主畫面只保留一個設定按鈕。
        self.options_btn = QPushButton("選項設定")
        self.options_btn.setFixedWidth(100)
        self.options_btn.clicked.connect(self.show_options_dialog)
        btn_layout.addWidget(self.options_btn)

        self.minimap_btn = QPushButton("小地圖")
        self.minimap_btn.setFixedWidth(80)
        self.minimap_btn.clicked.connect(self.show_minimap_window)
        btn_layout.addWidget(self.minimap_btn)

        self._create_options_dialog()

        # 將按鈕布局加到主要布局中
        layout.addLayout(btn_layout)

        # --- 處理狀態獨立一行，避免和更新秒數 / 篩選器擠在一起 ---
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.addWidget(QLabel("處理狀態："))
        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.status.setWordWrap(False)
        status_layout.addWidget(self.status, 1)
        layout.addLayout(status_layout)

        # --- 更新秒數 + SID / DID 篩選獨立一行 ---
        interval_layout = QHBoxLayout()
        interval_layout.addStretch()
        interval_layout.addWidget(QLabel("更新秒數："))

        # 數字框改右對齊 + 固定寬度
        self.refresh_input = QSpinBox()
        self.refresh_input.setRange(0, 3600)
        self.refresh_input.setValue(0)
        self.refresh_input.setFixedWidth(80)      # ★固定寬度
        self.refresh_input.setAlignment(Qt.AlignRight)   # ★讓數字靠右
        interval_layout.addWidget(self.refresh_input)

        # 「使用最新 RRF」屬於主操作流程，放回主畫面，不收進選項設定。
        self.auto_latest_checkbox = QCheckBox("最新RRF")
        # 右上角選項預設關閉；使用者需要時再手動勾選。
        self.auto_latest_checkbox.setChecked(False)
        interval_layout.addWidget(self.auto_latest_checkbox)

        # 攻方 SID 篩選
        interval_layout.addWidget(QLabel("篩選攻方："))
        self.sid_filter = QComboBox()
        self._orig_sid_showPopup = self.sid_filter.showPopup
        self._orig_sid_hidePopup = self.sid_filter.hidePopup
        self.sid_filter.showPopup = self.on_sid_popup_open
        self.sid_filter.hidePopup = self.on_sid_popup_close
        self.sid_filter.addItem(FILTER_ALL, None)
        self.sid_filter.setFixedWidth(210)
        self.sid_filter.currentIndexChanged.connect(self.apply_did_filter)
        interval_layout.addWidget(self.sid_filter)

        # 受方 DID 篩選
        interval_layout.addWidget(QLabel("篩選魔物："))
        self.did_filter = QComboBox()
        self._orig_did_showPopup = self.did_filter.showPopup
        self._orig_did_hidePopup = self.did_filter.hidePopup
        self.did_filter.showPopup = self.on_did_popup_open
        self.did_filter.hidePopup = self.on_did_popup_close
        self.did_filter.addItem(FILTER_ALL, None)
        self.did_filter.addItem(FILTER_ALL_WITH_STAT, None)
        self.did_filter.setFixedWidth(210)
        self.did_filter.currentIndexChanged.connect(self.apply_did_filter)
        interval_layout.addWidget(self.did_filter)

        # 狀態勾選只改變「顯示」，不重新解析 RRF，也不影響死亡/掉落內部統計資料。
        self.show_status_history_checkbox.stateChanged.connect(self.on_status_display_changed)
        self.show_zero_damage_checkbox.stateChanged.connect(self.on_zero_damage_display_changed)
        self.show_state_change_checkbox.stateChanged.connect(self.on_status_display_changed)
        self.vanish_out_of_sight_checkbox.stateChanged.connect(self.on_status_display_changed)
        self.vanish_death_checkbox.stateChanged.connect(self.on_status_display_changed)
        self.vanish_logout_checkbox.stateChanged.connect(self.on_status_display_changed)
        self.vanish_teleport_checkbox.stateChanged.connect(self.on_status_display_changed)
        self.show_packet_decode_checkbox.stateChanged.connect(self.toggle_packet_decode_tab)


        layout.addLayout(interval_layout)

        # ===== v2.20：全域 Replay 時間軸 =====
        # 快進/快退獨立一列，時間軸本身維持較寬。
        jump_row = QHBoxLayout()
        jump_row.addWidget(QLabel("快速跳轉："))
        for text, delta in (("−1分", -60.0), ("−10秒", -10.0), ("−1秒", -1.0),
                            ("+1秒", 1.0), ("+10秒", 10.0), ("+1分", 60.0)):
            btn = QPushButton(text)
            btn.setFixedWidth(58)
            btn.clicked.connect(lambda _checked=False, d=delta: self.jump_damage_playback(d))
            jump_row.addWidget(btn)
        jump_row.addStretch(1)
        layout.addLayout(jump_row)

        playback_row = QHBoxLayout()
        playback_row.addWidget(QLabel("Replay時間："))

        self.damage_playback_btn = QPushButton("▶ 播放")
        self.damage_playback_btn.setFixedWidth(82)
        self.damage_playback_btn.clicked.connect(self.toggle_damage_playback)
        playback_row.addWidget(self.damage_playback_btn)

        playback_row.addWidget(QLabel("倍速："))
        from PySide6.QtWidgets import QDoubleSpinBox, QAbstractSpinBox
        self.damage_playback_speed_input = QDoubleSpinBox()
        self.damage_playback_speed_input.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.damage_playback_speed_input.setRange(0.1, 4.0)
        self.damage_playback_speed_input.setSingleStep(0.1)
        self.damage_playback_speed_input.setDecimals(1)
        self.damage_playback_speed_input.setPrefix("x")
        self.damage_playback_speed_input.setValue(1.0)
        self.damage_playback_speed_input.setFixedWidth(70)
        self.damage_playback_speed_input.valueChanged.connect(self.on_damage_playback_speed_changed)
        playback_row.addWidget(self.damage_playback_speed_input)

        self.damage_playback_show_all_btn = QPushButton("顯示全部時間")
        self.damage_playback_show_all_btn.setFixedWidth(104)
        self.damage_playback_show_all_btn.clicked.connect(self.show_all_damage_history)
        playback_row.addWidget(self.damage_playback_show_all_btn)

        self.damage_playback_slider = QSlider(Qt.Horizontal)
        self.damage_playback_slider.setRange(0, 0)
        self.damage_playback_slider.setSingleStep(100)
        self.damage_playback_slider.setPageStep(1000)
        self.damage_playback_slider.sliderPressed.connect(self.on_damage_playback_slider_pressed)
        self.damage_playback_slider.valueChanged.connect(self.on_damage_playback_slider_value_changed)
        self.damage_playback_slider.sliderReleased.connect(self.on_damage_playback_slider_released)
        playback_row.addWidget(self.damage_playback_slider, 1)

        self.damage_playback_time_label = QLabel("00:00:00.000 / 00:00:00.000")
        self.damage_playback_time_label.setMinimumWidth(210)
        self.damage_playback_time_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        playback_row.addWidget(self.damage_playback_time_label)

        layout.addLayout(playback_row)

        # 10 FPS 更新整個介面。播放時間仍以 perf_counter 計算，因此不因 UI 忙碌累積誤差。
        # 100 ms 也正好對應短區間圖表的 0.1 秒粒度。
        self.damage_playback_timer = QTimer(self)
        self.damage_playback_timer.setInterval(100)
        self.damage_playback_timer.timeout.connect(self.on_damage_playback_tick)

        # v2.1：即時 seek 合併器。約 30 FPS 更新，拖曳手感即時，同時避免每個 pixel 都完整重算。
        self.damage_playback_seek_timer = QTimer(self)
        self.damage_playback_seek_timer.setSingleShot(True)
        self.damage_playback_seek_timer.setInterval(33)
        self.damage_playback_seek_timer.timeout.connect(self._flush_damage_playback_live_seek)

        # v2.12：小地圖獨立 60 FPS 視覺更新。
        # 主介面仍維持 10 FPS 做昂貴統計，避免為了地圖動畫拖慢整個 UI。
        self.minimap_render_timer = QTimer(self)
        self.minimap_render_timer.setInterval(16)
        try:
            self.minimap_render_timer.setTimerType(Qt.PreciseTimer)
        except Exception:
            pass
        self.minimap_render_timer.timeout.connect(self.on_minimap_render_tick)
        # v2.14：即使暫停播放也保持低成本 polling；視窗沒開時 tick 會立刻 return。
        self.minimap_render_timer.start()


        # 計時器
        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)          # ★重點：不要週期性一直噴
        self.auto_timer.timeout.connect(self.load_file)

        # 儲存路徑
        self.last_rrf_path = None

        #self.status = QLabel("")
        #layout.addWidget(self.status)

        # 設置 Tabs
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)



        # Tab1：統計（長條圖 + 樹狀）
        tab_stats = QWidget()
        vbox = QVBoxLayout(tab_stats)

        # ======= 圖表切換按鈕 =======
        btn_box = QHBoxLayout()

        self.btn_bar = QPushButton("顯示區間總傷害")
        self.btn_line = QPushButton("顯示每秒折線趨勢圖")
        self.btn_stairs = QPushButton("顯示每秒階梯圖")
        self.btn_select_range = QPushButton("圈選秒數")
        self.btn_select_range.setCheckable(True)
        self.btn_clear_range = QPushButton("清除圈選")
        self.damage_range_label = QLabel("傷害範圍：全部")

        self.btn_bar.clicked.connect(self.on_bar_clicked)
        self.btn_line.clicked.connect(self.on_line_clicked)
        self.btn_stairs.clicked.connect(self.on_stairs_clicked)
        self.btn_select_range.toggled.connect(self.on_time_select_toggled)
        self.btn_clear_range.clicked.connect(self.clear_damage_time_range)
        self._update_chart_resolution_labels()

        btn_box.addWidget(self.btn_bar)
        btn_box.addWidget(self.btn_line)
        btn_box.addWidget(self.btn_stairs)
        btn_box.addWidget(self.btn_select_range)
        btn_box.addWidget(self.btn_clear_range)
        btn_box.addWidget(self.damage_range_label)
        btn_box.addStretch(1)

        vbox.addLayout(btn_box)
        # ===========================

        # ➊ 圖表區塊
        self.fig = Figure(figsize=(5, 2))
        self.canvas = FigureCanvas(self.fig)
        self.canvas.mpl_connect("scroll_event", self.on_scroll)
        # v1.6：圖表寬度改變時重新計算時間刻度密度。
        # 能放得下時優先每 1 秒一個刻度，避免固定稀疏刻度浪費可用寬度。
        self.canvas.mpl_connect("resize_event", self.on_chart_resize)

        # v1.5：總傷害圖不再把所有角色硬塞進同一張圖。
        # 固定顯示少量列，透過右側捲軸只替換目前可見的人員。
        chart_box = QHBoxLayout()
        chart_box.setContentsMargins(0, 0, 0, 0)
        chart_box.setSpacing(2)
        chart_box.addWidget(self.canvas, 1)

        self.bar_visible_rows = 10
        self._bar_sorted_sids = []
        self.bar_scrollbar = QScrollBar(Qt.Vertical)
        self.bar_scrollbar.setSingleStep(1)
        self.bar_scrollbar.setPageStep(self.bar_visible_rows)
        self.bar_scrollbar.valueChanged.connect(self.on_bar_scroll_changed)
        self.bar_scrollbar.hide()
        chart_box.addWidget(self.bar_scrollbar)
        vbox.addLayout(chart_box)

        # NavigationToolbar 只保留給既有拖曳邏輯內部使用，不放到 UI。
        # 左下角 Home/Back/Zoom/Save 工具列因此完全隱藏。
        self.toolbar = MyNavigationToolbar(self.canvas, self)
        self.left_pan = LeftButtonPan(self.canvas, self.toolbar)
        self.toolbar.hide()

        self.draw_empty_chart()
        # ➋ 樹狀統計
        self.tree_group = QTreeWidget()
        self.tree_group.setColumnCount(4)
        self.tree_group.setHeaderLabels(["名稱","平均傷害", "總傷害", "DPS"])
        self.tree_group.header().setDefaultAlignment(Qt.AlignCenter)
        self.tree_group.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree_group.setColumnWidth(1, 150)
        self.tree_group.setColumnWidth(2, 180)
        self.tree_group.header().setStretchLastSection(False)
        self.tree_group.setColumnWidth(3, 150)        
        self.tree_group.itemDoubleClicked.connect(self.on_transform_item_double_clicked)


        vbox.addWidget(self.tree_group)
        # --- 分頁底部按鈕列（水平排列） ---
        btn_row = QHBoxLayout()
        
        self.progress_bartext = QLabel("")
        btn_row.addWidget(self.progress_bartext)
        # 更新秒數標籤
        btn_row.addWidget(QLabel("處理進度(%)："))
        # ★★★★★ 進度條 ★★★★★
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        #self.progress_bar.hide()             # 預設隱藏

        self.progress_bar.setMaximumWidth(int(self.width() * 0.5))
        self.progress_bar.setMinimumWidth(int(self.width() * 0.5))
        btn_row.addWidget(self.progress_bar)
        btn_row.addStretch()  # 推到右邊
        # ★★★★★ 進度條結束 ★★★★★
        self.toggle_hud_btn = QPushButton("顯示 HUD")
        self.toggle_hud_btn.clicked.connect(self.toggle_hud)
        btn_row.addWidget(self.toggle_hud_btn)
        
        self.screenshot_btn = QPushButton("截圖此分頁")
        self.screenshot_btn.clicked.connect(self.capture_to_clipboard)
        btn_row.addWidget(self.screenshot_btn)

        vbox.addLayout(btn_row)

        # RRF 大檔案解析進度改用獨立非阻塞小視窗顯示。
        self.parse_progress_dialog = None
        self.parse_progress_tree = None
        self.parse_progress_summary = None
        self.parse_progress_dialog_bar = None

        self.tabs.addTab(tab_stats, "統計傷害")
        # Tab2：傷害歷程。v2.0 播放控制已提升到全域時間軸。
        self.raw_history_tab = QWidget()
        raw_history_layout = QVBoxLayout(self.raw_history_tab)
        raw_history_layout.setContentsMargins(4, 4, 4, 4)
        raw_history_layout.setSpacing(4)

        self.table_raw = QTableWidget()
        self.table_raw.setColumnCount(9)
        self.table_raw.setHorizontalHeaderLabels([
            "時間戳", "技能名稱", "攻方ID", "受方ID",
            "傷害", "等級", "次數", "來源延遲", "目標延遲"
        ])
        raw_history_layout.addWidget(self.table_raw, 1)

        self.tabs.addTab(self.raw_history_tab, "傷害歷程")
        
        self.table_drop = QTableWidget()
        self.table_drop.setColumnCount(7)
        self.table_drop.setHorizontalHeaderLabels([
            "時間戳", "掉落來源", "物品名稱", "掉落數量", "座標X", "座標Y", "導航指令"
        ])
        self.table_drop.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_drop.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table_drop.setSelectionBehavior(QTableWidget.SelectItems)
        self.table_drop.itemDoubleClicked.connect(self.on_drop_item_double_clicked)

        drop_copy_action = QAction(self.table_drop)
        drop_copy_action.setShortcut(QKeySequence.Copy)
        drop_copy_action.triggered.connect(self.copy_drop_selection_to_clipboard)
        self.table_drop.addAction(drop_copy_action)

        self.table_drop.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_drop.customContextMenuRequested.connect(self.show_drop_context_menu)

        self.tabs.addTab(self.table_drop, "物品掉落歷程")
        # Tab4：死亡 / 掉落統計
        self.tree_monster_drop = QTreeWidget()
        self.tree_monster_drop.setColumnCount(3)
        self.tree_monster_drop.setHeaderLabels([
            "怪物 / 物品", "數量", "比例"
        ])
        self.tree_monster_drop.header().setDefaultAlignment(Qt.AlignCenter)
        self.tree_monster_drop.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree_monster_drop.setColumnWidth(1, 140)
        self.tree_monster_drop.setColumnWidth(2, 120)
        self.tree_monster_drop.setAlternatingRowColors(True)

        self.tabs.addTab(self.tree_monster_drop, "死亡/掉落統計")

        # v2.4：GAT 小地圖改成獨立視窗，不占用主介面分頁。
        self.minimap_window = GATMiniMapWindow(self)
        self.minimap_widget = self.minimap_window.map_widget
        self.minimap_map_label = self.minimap_window.map_label
        self.minimap_count_label = self.minimap_window.count_label
        self.minimap_selected_label = self.minimap_window.selected_label
        self.load_gat_btn = self.minimap_window.load_gat_btn
        self.load_gat_btn.clicked.connect(self.choose_gat_file)
        self.minimap_widget.unitSelected.connect(self.on_minimap_unit_selected)
        self.minimap_widget.unitContextRequested.connect(self.on_minimap_unit_context_requested)

        # v2.14：長駐獨立 process。小地圖位置重建 / 傷害聚合不再跑在 Qt GUI thread。
        self._start_minimap_compute_process()

        # Tab5：完整封包解析（v1.3 虛擬 UI）
        # 上半部只顯示封包列；下半部只顯示目前選取封包的完整欄位。
        # 兩邊都使用 QTableView + QAbstractTableModel，不建立大量 QTreeWidgetItem。
        self.packet_decode_panel = QWidget()
        packet_decode_layout = QVBoxLayout(self.packet_decode_panel)
        packet_decode_layout.setContentsMargins(4, 4, 4, 4)

        self.packet_decode_status_label = QLabel("")
        packet_decode_layout.addWidget(self.packet_decode_status_label)

        self.packet_decode_splitter = QSplitter(Qt.Vertical)
        packet_decode_layout.addWidget(self.packet_decode_splitter)

        self.packet_decode_table = QTableView()
        self.packet_decode_model = PacketDecodeTableModel(self.packet_decode_table)
        self.packet_decode_table.setModel(self.packet_decode_model)
        self.packet_decode_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.packet_decode_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.packet_decode_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.packet_decode_table.setAlternatingRowColors(True)
        self.packet_decode_table.setSortingEnabled(False)
        self.packet_decode_table.verticalHeader().setVisible(False)
        self.packet_decode_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.packet_decode_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.packet_decode_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.packet_decode_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.packet_decode_splitter.addWidget(self.packet_decode_table)

        self.packet_decode_fields_table = QTableView()
        self.packet_decode_fields_model = PacketDecodeFieldsModel(self.packet_decode_fields_table)
        self.packet_decode_fields_table.setModel(self.packet_decode_fields_model)
        self.packet_decode_fields_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.packet_decode_fields_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.packet_decode_fields_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.packet_decode_fields_table.setAlternatingRowColors(True)
        self.packet_decode_fields_table.verticalHeader().setVisible(False)
        self.packet_decode_fields_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.packet_decode_fields_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.packet_decode_splitter.addWidget(self.packet_decode_fields_table)
        self.packet_decode_splitter.setStretchFactor(0, 3)
        self.packet_decode_splitter.setStretchFactor(1, 2)

        self.packet_decode_table.selectionModel().currentRowChanged.connect(
            self.on_packet_decode_row_changed
        )

        # 舊程式大量位置使用 tree_packet_decode 判斷分頁；保留 alias，只代表 panel。
        self.tree_packet_decode = self.packet_decode_panel
        # 注意：此處不 addTab；由「顯示封包完整解析」勾選框動態加入/移除。
        self.packet_decode_data = []
        
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # 讓表格可圈選多格
        self.table_raw.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_raw.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table_raw.setSelectionBehavior(QTableWidget.SelectItems)

        # Ctrl+C 複製（TSV：貼到 Excel 會自動分欄）
        copy_action = QAction(self.table_raw)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.triggered.connect(self.copy_raw_selection_to_clipboard)
        self.table_raw.addAction(copy_action)

        # 右鍵選單 → 複製
        self.table_raw.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table_raw.customContextMenuRequested.connect(self.show_raw_context_menu)

        self.parsed_data = []
        self.last_update_start = None
        self.last_update_end = None
        from collections import defaultdict
        self.state_change_count = defaultdict(lambda: defaultdict(int))


    def _create_options_dialog(self):
        """建立集中管理所有勾選項目的設定視窗。"""
        self.options_dialog = QDialog(self)
        self.options_dialog.setWindowTitle("選項設定")
        self.options_dialog.setModal(True)
        self.options_dialog.setMinimumWidth(360)

        vbox = QVBoxLayout(self.options_dialog)

        vbox.addWidget(QLabel("解析 / 顯示選項"))

        self.Character_ability_changes_checkbox = QCheckBox("解析角色能力變動", self.options_dialog)
        self.Character_ability_changes_checkbox.setChecked(False)
        vbox.addWidget(self.Character_ability_changes_checkbox)

        # v2.16：真正的攻擊封包 damage == 0 預設保留在底層，但畫面預設隱藏。
        # 勾選後立即納入傷害歷程 / 技能統計 / 小地圖傷害線，不需要重讀 RRF。
        self.show_zero_damage_checkbox = QCheckBox("解析 / 顯示傷害 0", self.options_dialog)
        self.show_zero_damage_checkbox.setChecked(False)
        vbox.addWidget(self.show_zero_damage_checkbox)

        # 選項設定內所有項目預設關閉；需要時再由使用者勾選。
        self.show_status_history_checkbox = QCheckBox("傷害歷程顯示狀態", self.options_dialog)
        self.show_status_history_checkbox.setChecked(False)
        vbox.addWidget(self.show_status_history_checkbox)

        # 一般 STATE_CHANGE2 / STATE_CHANGE 再獨立控制，與 VANISH 分開。
        self.show_state_change_checkbox = QCheckBox("狀態開始 / 結束", self.options_dialog)
        self.show_state_change_checkbox.setChecked(False)
        vbox.addWidget(self.show_state_change_checkbox)

        self.show_packet_decode_checkbox = QCheckBox("顯示封包完整解析分頁", self.options_dialog)
        self.show_packet_decode_checkbox.setChecked(False)
        vbox.addWidget(self.show_packet_decode_checkbox)

        vbox.addSpacing(8)
        vbox.addWidget(QLabel("VANISH 狀態顯示（需同時勾選「傷害歷程顯示狀態」）"))

        # 依使用需求提供四種 VANISH 顯示選項；全部預設關閉。
        self.vanish_out_of_sight_checkbox = QCheckBox("離開視野 (mode 0)", self.options_dialog)
        self.vanish_death_checkbox = QCheckBox("死亡 (mode 1)", self.options_dialog)
        self.vanish_logout_checkbox = QCheckBox("登出 (mode 2)", self.options_dialog)
        self.vanish_teleport_checkbox = QCheckBox("瞬移 (mode 3)", self.options_dialog)

        self.vanish_out_of_sight_checkbox.setChecked(False)
        self.vanish_death_checkbox.setChecked(False)
        self.vanish_logout_checkbox.setChecked(False)
        self.vanish_teleport_checkbox.setChecked(False)

        vbox.addWidget(self.vanish_out_of_sight_checkbox)
        vbox.addWidget(self.vanish_death_checkbox)
        vbox.addWidget(self.vanish_logout_checkbox)
        vbox.addWidget(self.vanish_teleport_checkbox)

        close_btn = QPushButton("關閉", self.options_dialog)
        close_btn.clicked.connect(self.options_dialog.accept)
        vbox.addWidget(close_btn)

    def show_options_dialog(self):
        """開啟集中設定視窗；各勾選狀態會持續保留。"""
        self.options_dialog.exec()

    def _vanish_checkbox_for_mode(self, mode):
        return {
            0: getattr(self, "vanish_out_of_sight_checkbox", None),
            1: getattr(self, "vanish_death_checkbox", None),
            2: getattr(self, "vanish_logout_checkbox", None),
            3: getattr(self, "vanish_teleport_checkbox", None),
        }.get(mode)

    def is_vanish_mode_visible(self, mode):
        """VANISH 需通過狀態總開關，且該 mode 自己也必須勾選。"""
        if not getattr(self, "show_status_history_checkbox", None):
            return False
        if not self.show_status_history_checkbox.isChecked():
            return False
        checkbox = self._vanish_checkbox_for_mode(mode)
        return bool(checkbox and checkbox.isChecked())


    def _set_packet_decode_message(self, message):
        """完整解析分頁只更新狀態與 Model，不建立 placeholder Item。"""
        if hasattr(self, "packet_decode_status_label"):
            self.packet_decode_status_label.setText(message or "")
        if hasattr(self, "packet_decode_model"):
            self.packet_decode_model.set_records([], [])
        if hasattr(self, "packet_decode_fields_model"):
            self.packet_decode_fields_model.clear()

    def _packet_decode_visible_indices(self):
        """依顯示選項建立可見 index；Model 仍共用原始 records，不複製每筆資料。"""
        records = getattr(self, "packet_decode_data", [])
        visible = []
        visible_transform_by_sid = {}

        for idx, rec in enumerate(records):
            if self.damage_playback_mode:
                rec_t = self.timestamp_to_float_seconds(rec.get("timestamp"))
                if rec_t is not None and rec_t > self.damage_playback_current_sec + 1e-9:
                    continue
            packet_name = rec.get("packet_name")
            source_packet_name = rec.get("source_packet_name", packet_name)
            decoded = rec.get("decoded") or {}

            # 變身只顯示 TRANSFORM_DURATION_MAP 白名單。
            if source_packet_name == "HEADER_ZC_MSG_STATE_CHANGE3" and decoded.get("type") == 665:
                sid = decoded.get("sid") or decoded.get("aid")
                evt = decoded.get("transform_event")
                skin = decoded.get("monsterskin", 0)

                if evt == "start":
                    if skin not in TRANSFORM_DURATION_MAP:
                        if sid:
                            visible_transform_by_sid.pop(sid, None)
                        continue
                    if sid:
                        visible_transform_by_sid[sid] = skin
                elif evt == "end":
                    original_skin = visible_transform_by_sid.pop(sid, None) if sid else None
                    if original_skin not in TRANSFORM_DURATION_MAP:
                        continue

            if source_packet_name in ("HEADER_ZC_MSG_STATE_CHANGE2", "HEADER_ZC_MSG_STATE_CHANGE"):
                if (not self.show_status_history_checkbox.isChecked()
                        or not self.show_state_change_checkbox.isChecked()):
                    continue

            if source_packet_name == "HEADER_ZC_NOTIFY_VANISH":
                if not self.is_vanish_mode_visible(decoded.get("mode")):
                    continue

            visible.append(idx)

        return visible

    def refresh_packet_decode_tree(self):
        """v1.3：只替換虛擬 Model 的資料來源，不再重建 Tree/UI Item。"""
        if not hasattr(self, "packet_decode_model"):
            return
        if not getattr(self, "show_packet_decode_checkbox", None):
            return
        if not self.show_packet_decode_checkbox.isChecked():
            return

        records = getattr(self, "packet_decode_data", [])
        visible_indices = self._packet_decode_visible_indices()
        self.packet_decode_model.set_records(records, visible_indices)
        self.packet_decode_fields_model.clear()

        if not records:
            self.packet_decode_status_label.setText("目前沒有完整封包解析資料")
        else:
            self.packet_decode_status_label.setText(
                f"完整解析：{len(visible_indices):,} / {len(records):,} 包（虛擬表格）"
            )

        # 只選第一列，不建立任何額外 UI row/item。
        if visible_indices:
            self.packet_decode_table.selectRow(0)

    def _append_packet_decode_tree_chunk(self, token=None):
        """v1.3 相容空殼：QTableView/Model 已不需要分批建立 UI 節點。"""
        return

    def on_packet_decode_row_changed(self, current, previous=None):
        """只將目前選取的一包完整解析欄位替換到下方虛擬表格。"""
        if not current.isValid():
            self.packet_decode_fields_model.clear()
            return
        rec = self.packet_decode_model.record_at(current.row())
        self.packet_decode_fields_model.set_record(rec)

    def merge_new_packets_with_true_sid(self, new_packets):
        for pkt in new_packets:
            if pkt["type"] == "GROUND":
                pkt["decoded"] = decode_groundskill(pkt["hex"])
                pkt["decoded"]["skill_id"] = le_int(pkt["hex"][2:4])

            elif pkt["type"] == "SKILL2":
                pkt["decoded"] = decode_skill2(pkt["hex"])

            elif pkt["type"] == "ACT3":
                pkt["decoded"] = decode_act3(pkt["hex"])

        for pkt in new_packets:
            if pkt.get("decoded") is None:
                continue

            t = time_to_float(pkt["timestamp"])

            if pkt["type"] == "GROUND":
                skill = pkt["decoded"]["skill_id"]
                sid = pkt["decoded"]["sid"]

                self.ground_history[skill].append({
                    "sid": sid,
                    "time": t
                })

                if len(self.ground_history[skill]) > 50:
                    self.ground_history[skill].pop(0)

            elif pkt["type"] == "SKILL2":
                sid = pkt["decoded"]["sid"]

                if sid < 100000:
                    skill = pkt["decoded"]["skill_id"]
                    candidates = [
                        g for g in self.ground_history.get(skill, [])
                        if g["time"] <= t
                    ]
                    if candidates:
                        true_sid = max(candidates, key=lambda x: x["time"])["sid"]
                        pkt["decoded"]["sid"] = true_sid

        return new_packets


    def calc_txt_signature(self, path, sample_size=65536):
        """
        取得檔案快速內容指紋：
        - 檔案大小
        - 開頭 sample
        - 中間 sample
        - 結尾 sample

        回傳: (size, hex_digest)
        """
        st = os.stat(path)
        size = st.st_size

        h = hashlib.blake2b(digest_size=16)

        with open(path, "rb") as f:
            if size <= sample_size * 3:
                # 小檔案：直接全讀，反正不大
                h.update(f.read())
            else:
                # head
                head = f.read(sample_size)
                h.update(head)

                # middle
                mid_pos = max(0, size // 2 - sample_size // 2)
                f.seek(mid_pos)
                middle = f.read(sample_size)
                h.update(middle)

                # tail
                tail_pos = max(0, size - sample_size)
                f.seek(tail_pos)
                tail = f.read(sample_size)
                h.update(tail)

        return (size, h.hexdigest())

    def reset_incremental_txt_state(self, clear_data=False):
        # 函式名稱保留以避免大改 UI；raw 版同時重設 RRF reader。
        self.rrf_reader = None
        self.txt_last_pos = 0
        self.txt_pending = ""
        self.first_full_parse_done = False

        if clear_data:
            from collections import defaultdict
            self.ground_history = defaultdict(list)
            self.raw_data = []
            self.parsed_data = []
            self.drop_data = []
            self.current_drop_data = []
            self.current_drop_filtered_raw = []
            self.sid_name_map = {}
            self.did_name_map = {}
            self.did_name_source = {}
            self.self_sid = 0
            self.actor_map_events = []
            self._minimap_loaded_map_name = ""
            self._minimap_active_map_name = ""
            self._reset_minimap_replay_state()


    def extract_complete_blocks(self, text: str):
        """
        把新增文字切成「完整封包區塊」。
        未結束的半包先留到下一次。
        """
        lines = text.splitlines(keepends=True)
        blocks = []
        buf = []
        inside = False

        for line in lines:
            s = line.lstrip()

            # 封包 / Chunk 開頭
            if not inside:
                if s.startswith("[") and (" packet " in s or s.startswith("[Chunk ")):
                    inside = True
                    buf = [line]
            else:
                buf.append(line)
                if line.strip() == "}":
                    blocks.append("".join(buf))
                    buf = []
                    inside = False

        pending = "".join(buf) if inside else ""
        return "".join(blocks), pending


    def read_incremental_text(self, txt_path: str):
        """
        回傳:
            mode: "full" 或 "delta"
            text: 這次可安全解析的完整文字
        """
        import os

        st = os.stat(txt_path)
        path_changed = (self.txt_last_path != txt_path)
        truncated = (st.st_size < self.txt_last_pos)
        need_full = (not self.first_full_parse_done) or path_changed or truncated

        if need_full:
            self.txt_last_path = txt_path
            self.txt_last_pos = 0
            self.txt_pending = ""
            mode = "full"
        else:
            mode = "delta"

        with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(self.txt_last_pos)
            chunk = f.read()
            self.txt_last_pos = f.tell()

        merged = self.txt_pending + chunk
        complete_text, self.txt_pending = self.extract_complete_blocks(merged)
        return mode, complete_text

    def copy_table_selection_to_clipboard(self, table):
        ranges = table.selectedRanges()
        if not ranges:
            return

        lines = []
        for r in ranges:
            headers = []
            for col in range(r.leftColumn(), r.rightColumn() + 1):
                hitem = table.horizontalHeaderItem(col)
                headers.append(hitem.text() if hitem else "")
            lines.append("\t".join(headers))

            for row in range(r.topRow(), r.bottomRow() + 1):
                row_text = []
                for col in range(r.leftColumn(), r.rightColumn() + 1):
                    item = table.item(row, col)
                    row_text.append(item.text() if item else "")
                lines.append("\t".join(row_text))

            lines.append("")

        text = "\n".join(lines).rstrip()
        QApplication.clipboard().setText(text)


    def copy_raw_selection_to_clipboard(self):
        self.copy_table_selection_to_clipboard(self.table_raw)


    def copy_drop_selection_to_clipboard(self):
        self.copy_table_selection_to_clipboard(self.table_drop)


    def show_table_context_menu(self, table, pos):
        menu = QMenu(table)
        menu.addAction("複製 (Ctrl+C)", lambda: self.copy_table_selection_to_clipboard(table))
        menu.exec(table.viewport().mapToGlobal(pos))


    def show_raw_context_menu(self, pos):
        self.show_table_context_menu(self.table_raw, pos)
        
    def on_drop_item_double_clicked(self, item):
        # 只允許「導航指令」欄位雙擊自動複製
        NAV_COL = 6

        if item.column() != NAV_COL:
            return

        text = item.text().strip()
        if not text:
            return

        QApplication.clipboard().setText(text)
        self.status.setText(f"已複製導航指令：{text}")

    def show_drop_context_menu(self, pos):
        self.show_table_context_menu(self.table_drop, pos)


    def resizeEvent(self, event):
        super().resizeEvent(event)

        # 讓進度條寬度 = 視窗寬度 * 0.5  (50%)
        new_width = int(self.width() * 0.5)
        self.progress_bar.setFixedWidth(new_width)

    def toggle_hud(self):
        if self.hud.isVisible():
            self.hud.hide()
            self.toggle_hud_btn.setText("顯示 HUD")
        else:
            self.hud.show()
            self.toggle_hud_btn.setText("隱藏 HUD")

    def toggle_packet_decode_tab(self, state=None):
        """勾選後顯示分頁並自動重新載入目前 RRF，不同步重建整棵樹。"""
        if not hasattr(self, "tabs") or not hasattr(self, "tree_packet_decode"):
            return

        checked = self.show_packet_decode_checkbox.isChecked()
        idx = self.tabs.indexOf(self.tree_packet_decode)

        if checked:
            if idx == -1:
                self.tabs.addTab(self.tree_packet_decode, "封包完整解析")

            # 先讓 UI 立即返回 event loop，再開始 reload。虛擬表格只替換 Model 內容。
            self._set_packet_decode_message("正在重新載入目前 RRF…")
            self._packet_decode_reload_pending = True
            QTimer.singleShot(0, self._reload_current_rrf_for_packet_decode)
        else:
            self._packet_decode_reload_pending = False
            if idx != -1:
                self.tabs.removeTab(idx)

    def _reload_current_rrf_for_packet_decode(self):
        """直接重讀目前 RRF，不跳選檔視窗；若正在更新則等完成後再執行。"""
        if not self.show_packet_decode_checkbox.isChecked():
            self._packet_decode_reload_pending = False
            return

        if not self.last_rrf_path:
            self._packet_decode_reload_pending = False
            self.status.setText("請先載入 RRF，再開啟封包完整解析分頁")
            self._set_packet_decode_message("尚未載入 RRF")
            return

        thread_running = bool(self.worker_thread and self.worker_thread.isRunning())
        if self.is_processing or getattr(self, "_load_lock", False) or thread_running:
            self.status.setText("封包完整解析：等待目前更新完成後重新載入…")
            QTimer.singleShot(200, self._reload_current_rrf_for_packet_decode)
            return

        self._packet_decode_reload_pending = False
        self._packet_decode_reload_in_progress = True
        self.auto_timer.stop()

        # 強制下一次 reader.poll() 回傳 full；保留目前畫面資料直到新結果完成。
        self.rrf_reader = None
        self.first_full_parse_done = False
        self.packet_decode_data = []

        self.status.setText("封包完整解析：正在重新載入目前 RRF…")
        self.progress_bar.show()
        self.progress_bar.setValue(5)
        self.is_processing = True
        self._load_lock = True
        self.start_worker(self.last_rrf_path)
        self.update_load_button_text()

    def _finish_packet_decode_reload(self):
        """完整 reload 結束後只替換虛擬 Model 內容。"""
        if not getattr(self, "_packet_decode_reload_in_progress", False):
            return
        self._packet_decode_reload_in_progress = False
        if (self.show_packet_decode_checkbox.isChecked()
                and self.tabs.indexOf(self.tree_packet_decode) != -1):
            QTimer.singleShot(0, self.refresh_packet_decode_tree)

    def on_zero_damage_display_changed(self, *_args):
        """v2.16：傷害 0 顯示開關只改篩選，不重新讀 RRF。"""
        # fallback 小地圖索引也要失效；async process 則重新同步精簡傷害來源。
        self._minimap_damage_index_signature = None
        self._sync_minimap_compute_sources()
        self._minimap_last_damage_filter_sig = None
        self._minimap_last_damage_request_wall = -9999.0
        self.apply_did_filter()

        # 若目前在播放模式，重建播放來源，讓 0 傷害事件立刻加入/移除歷程。
        if getattr(self, "damage_playback_mode", False):
            try:
                self._sync_damage_playback_source(keep_current=True)
            except Exception:
                pass

    def on_status_display_changed(self, *_args):
        """狀態總開關、開始/結束或 VANISH 個別選項改變時，立即刷新相關畫面。"""
        self.apply_did_filter()
        # 完整解析正在 reload 時先不要替換 Model；完成後會自動刷新。
        if (hasattr(self, "tree_packet_decode")
                and self.tabs.indexOf(self.tree_packet_decode) != -1
                and not getattr(self, "_packet_decode_reload_in_progress", False)
                and not getattr(self, "_packet_decode_reload_pending", False)):
            self.refresh_packet_decode_tree()

    def on_tab_changed(self, idx):
        # 分頁可動態增減，因此不要再依固定 index 判斷。
        current = self.tabs.widget(idx) if idx >= 0 else None
        if current is self.table_raw:
            self.update_raw_table()
        elif current is self.table_drop:
            self.update_drop_table()
        elif current is self.tree_monster_drop:
            self.update_monster_drop_tree()
        elif current is self.tree_packet_decode:
            if (not getattr(self, "_packet_decode_reload_in_progress", False)
                    and not getattr(self, "_packet_decode_reload_pending", False)):
                self.refresh_packet_decode_tree()

    def on_scroll(self, event):
        """時間圖只縮放 X 軸。

        舊版同時縮放 X/Y，柱寬與線條視覺比例會一起被拉伸，看起來像資料失真。
        v1.5 的折線/階梯圖只改變時間視窗，Y 軸維持同一傷害尺度。
        總傷害橫條圖則不做滾輪縮放。
        """
        if self.current_chart_mode == "bar":
            # 總傷害圖：滾輪只用來上下瀏覽角色，不做座標縮放。
            sb = getattr(self, "bar_scrollbar", None)
            if sb is not None and sb.isVisible():
                step = 3
                if event.button == 'up':
                    sb.setValue(max(sb.minimum(), sb.value() - step))
                elif event.button == 'down':
                    sb.setValue(min(sb.maximum(), sb.value() + step))
            return

        ax = event.inaxes
        if ax is None:
            return

        base_scale = 1.2
        if event.button == 'up':
            scale_factor = 1 / base_scale
        elif event.button == 'down':
            scale_factor = base_scale
        else:
            return

        xdata = event.xdata
        if xdata is None:
            return

        cur_xlim = ax.get_xlim()
        width = cur_xlim[1] - cur_xlim[0]
        if width <= 0:
            return

        x_left_ratio = (xdata - cur_xlim[0]) / width
        new_width = width * scale_factor
        new_xmin = xdata - new_width * x_left_ratio
        new_xmax = xdata + new_width * (1 - x_left_ratio)

        ax.set_xlim(new_xmin, new_xmax)
        # v1.6：縮放後依目前可見秒數與實際繪圖寬度重新安排刻度。
        self._apply_adaptive_time_ticks(ax)
        self.canvas.draw_idle()

    def on_chart_resize(self, event=None):
        """時間圖尺寸改變時，自動增加/減少 X 軸秒刻度。"""
        if self.current_chart_mode not in ("line", "stairs"):
            return
        axes = getattr(self.fig, "axes", None) or []
        if not axes:
            return
        for ax in axes:
            self._apply_adaptive_time_ticks(ax)
        self.canvas.draw_idle()

    def on_bar_scroll_changed(self, value):
        """總傷害圖捲動時只替換目前可見的角色，不重算傷害資料。"""
        if self.current_chart_mode != "bar":
            return
        rows = getattr(self, "_bar_sorted_sids", None)
        if not rows:
            return
        self.draw_damage_chart(rows)

    def timestamp_to_float_seconds(self, ts):
        """+HH:MM:SS:mmm -> replay 絕對秒數(float)。"""
        try:
            h, m, s, ms = map(int, str(ts)[1:].split(":"))
            return h * 3600 + m * 60 + s + ms / 1000.0
        except (TypeError, ValueError, AttributeError):
            return None

    def format_replay_second(self, value, with_ms=False):
        """將 replay 秒數顯示成 s / m:ss / h:mm:ss，必要時帶毫秒。"""
        if value is None or not math.isfinite(value) or value < 0:
            return "--"
        total_ms = int(round(value * 1000.0))
        total_sec, ms = divmod(total_ms, 1000)
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        s = total_sec % 60
        if h:
            base = f"{h}:{m:02d}:{s:02d}"
        elif m:
            base = f"{m}:{s:02d}"
        else:
            base = f"{s}"
        if with_ms:
            return f"{base}.{ms:03d}"
        return base

    def update_damage_range_label(self):
        # 圈選範圍同時決定折線/階梯圖的真實統計粒度與按鈕文字。
        self._update_chart_resolution_labels()
        if not hasattr(self, "damage_range_label"):
            return
        if self.damage_time_range is None:
            self.damage_range_label.setText("傷害範圍：全部")
            return
        start, end = self.damage_time_range
        self.damage_range_label.setText(
            f"傷害範圍：{self.format_replay_second(start, True)} ～ "
            f"{self.format_replay_second(end, True)}"
        )

    def on_time_select_toggled(self, checked):
        """啟用左鍵拖曳圈選。總傷害圖沒有時間 X 軸，會自動切到階梯圖。"""
        if checked and self.current_chart_mode == "bar":
            self.current_chart_mode = "stairs"

        if hasattr(self, "left_pan"):
            self.left_pan.enabled = not checked
            self.left_pan.is_panning = False

        self.refresh_chart()

    def setup_damage_span_selector(self, ax):
        """在時間圖建立 SpanSelector；每次重畫都重綁目前 axes。"""
        old = getattr(self, "_span_selector", None)
        if old is not None:
            try:
                old.disconnect_events()
            except Exception:
                pass
        self._span_selector = None

        if not getattr(self, "btn_select_range", None):
            return
        if not self.btn_select_range.isChecked():
            return
        if self.current_chart_mode not in ("line", "stairs"):
            return

        self._span_selector = SpanSelector(
            ax,
            self.on_damage_span_selected,
            "horizontal",
            useblit=True,
            props={"alpha": 0.28, "facecolor": "#66AAFF"},
            minspan=0.02,
            interactive=False,
            drag_from_anywhere=False,
        )

    def on_damage_span_selected(self, xmin, xmax):
        if xmin is None or xmax is None:
            return
        start, end = sorted((float(xmin), float(xmax)))
        if not math.isfinite(start) or not math.isfinite(end) or end - start < 0.02:
            return

        self.damage_time_range = (start, end)
        self.update_damage_range_label()

        # v1.8：不要在 Matplotlib SpanSelector 的 onrelease callback 裡同步
        # clear/rebuild figure。SpanSelector 在 callback 返回後仍會做自己的
        # release/blit 清理，可能把剛畫好的新圖蓋回舊畫面，造成「還要再點一下
        # 才重繪」的現象。改成丟回 Qt event loop，等本次 mouse release 完整
        # 結束後再重算篩選並重畫。
        if not getattr(self, "_damage_range_refresh_pending", False):
            self._damage_range_refresh_pending = True
            QTimer.singleShot(0, self._apply_damage_range_after_span_release)

    def _apply_damage_range_after_span_release(self):
        self._damage_range_refresh_pending = False
        self.apply_did_filter()
        # apply_did_filter -> refresh_chart 已經會重建目前圖表；再排一次 draw_idle
        # 確保 Qt backend 在這個 event-loop cycle 立即呈現最新 canvas。
        QTimer.singleShot(0, self.canvas.draw_idle)

    def clear_damage_time_range(self):
        self.damage_time_range = None
        self.update_damage_range_label()
        if hasattr(self, "current_filtered_data"):
            self.apply_did_filter()

    def on_transform_item_double_clicked(self, item, column):
        """點擊變身次數彈出視窗"""
        sid = item.data(0, Qt.UserRole)
        if sid is None:
            return

        if sid not in self.transform_history:
            QMessageBox.information(self, "變身紀錄", "沒有變身紀錄。")
            return

        self.show_transform_detail_dialog(sid)

    def ms_to_timestamp(self, ms):
        hours   = ms // 3600000
        minutes = (ms % 3600000) // 60000
        seconds = (ms % 60000) // 1000
        millis  = ms % 1000
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


    def show_transform_detail_dialog(self, sid):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"變身詳細資訊")
        dialog.resize(550, 300)

        layout = QVBoxLayout(dialog)

        text_box = QTextEdit()
        text_box.setReadOnly(True)
        layout.addWidget(text_box)

        logs = []

        history = self.transform_history[sid]
        total = len(history)

        # ★★★ 倒序，但序號依照原本順序從 total → 1 ★★★
        for display_no, data in zip(range(total, 0, -1), reversed(history)):
            logs.append(
                f"[變身序號{display_no}] 啟動時間: {self.ms_to_timestamp(data['start'])} 持續: ({data['duration_sec']:.3f} 秒)\n"
            )
            #logs.append(
            #    f"[變身紀錄 {idx}]\n"
            #    f"Skin: {data['skin']}\n"
            #    f"持續: {data['duration_ms']} ms ({data['duration_sec']:.3f} 秒)\n"
            #    f"start: {data['start']} ms\n"
            #    f"end  : {data['end']} ms\n"
            #    "-------------------------------------------\n"
            #)
        # ★★★ 關鍵：先清除舊內容 ★★★
        text_box.setPlainText("".join(logs))

        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)

        dialog.exec()

      
    def capture_to_clipboard(self):
        """截圖當前視窗並複製到剪貼簿"""
        try:
            screen = QGuiApplication.primaryScreen()
            if not screen:
                print("無法取得螢幕")
                return

            # 擷取當前視窗
            pixmap = screen.grabWindow(self.winId())

            # 放進剪貼簿
            clipboard = QGuiApplication.clipboard()
            clipboard.setPixmap(pixmap)

            print("✅ 視窗截圖成功（已複製到剪貼簿）")

        except Exception as e:
            print(f"截圖失敗：{e}")
        
    def on_did_popup_open(self):
        self.is_did_popup_open = True
        self.auto_timer.stop()
        self._orig_did_showPopup()


    def on_did_popup_close(self):
        self.is_did_popup_open = False
        self._orig_did_hidePopup()
        self.resume_auto_update_after_filter_popup()


    def on_sid_popup_open(self):
        self.is_sid_popup_open = True
        self.auto_timer.stop()
        self._orig_sid_showPopup()


    def on_sid_popup_close(self):
        self.is_sid_popup_open = False
        self._orig_sid_hidePopup()
        self.resume_auto_update_after_filter_popup()


    def resume_auto_update_after_filter_popup(self):
        """兩個篩選選單都關閉後，才恢復自動更新。"""
        if self.is_did_popup_open or self.is_sid_popup_open:
            return

        interval = self.refresh_input.value()
        if interval > 0 and not self.is_processing:
            self.auto_timer.start(interval * 1000)
            self.update_load_button_text()


    def reset_filter_combos(self):
        """重設攻方 SID 與受方 DID 篩選選單。"""
        self.sid_filter.blockSignals(True)
        self.sid_filter.clear()
        self.sid_filter.addItem(FILTER_ALL, None)
        self.sid_filter.setCurrentIndex(0)
        self.sid_filter.blockSignals(False)

        self.did_filter.blockSignals(True)
        self.did_filter.clear()
        self.did_filter.addItem(FILTER_ALL, None)
        self.did_filter.addItem(FILTER_ALL_WITH_STAT, None)
        self.did_filter.setCurrentIndex(0)
        self.did_filter.blockSignals(False)



    def stop_update(self):
        self.auto_timer.stop()
        # 停止背景 RRF → TXT
        #self.stop_background_rrf_worker()
        self.refresh_input.setValue(0)
        self.status.setText("自動更新已停止 - 秒數為 0 按下載入按鈕可選擇檔案")
        # ★ 按鈕同步顯示
        self.update_load_button_text()
        self.is_processing = False

        
    def pause_update(self):
        """暫停自動更新，但保留秒數，不把秒數歸 0"""
        self.auto_timer.stop()     # 只停止自動更新，但不動秒數
        self.status.setText("已暫停自動更新（秒數保留，可再次繼續）")
        self.update_load_button_text()
        self.stop_background_rrf_worker()
        self.is_processing = False

        
    def update_load_button_text(self):
        interval = self.refresh_input.value()

        if not self.last_rrf_path:
            self.load_btn.setText("載入傷害表（未選擇檔案）")
            return

        base = os.path.basename(self.last_rrf_path)

        if interval == 0:
            self.load_btn.setText(f"載入傷害表：{base}（狀態:停止更新）")

        elif self.is_processing:
            self.load_btn.setText(f"讀取中：{base}（狀態:更新中, 每 {interval} 秒）")

        elif self.mouse_paused:
            self.load_btn.setText(f"載入傷害表：{base}（狀態:暫停中(滑鼠在視窗內), 每 {interval} 秒）")

        elif self.auto_timer.isActive():
            self.load_btn.setText(f"載入傷害表：{base}（狀態:自動更新, 每 {interval} 秒）")

        else:
            # singleShot 重新排程前的短暫空窗、或剛完成一次更新
            self.load_btn.setText(f"載入傷害表：{base}（狀態:等待下次更新, 每 {interval} 秒）")

    def _ensure_parse_progress_dialog(self):
        """建立 / 顯示 RRF 解析進度小視窗（非 modal，不阻塞主 UI）。"""
        dlg = getattr(self, "parse_progress_dialog", None)
        if dlg is None:
            dlg = QDialog(self)
            dlg.setWindowTitle("RRF 載入 / 解析進度")
            dlg.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
            dlg.setModal(False)
            dlg.resize(520, 700)

            layout = QVBoxLayout(dlg)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(8)

            summary = QLabel("準備載入 RRF…")
            summary.setWordWrap(True)
            layout.addWidget(summary)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            layout.addWidget(bar)

            tree = QTreeWidget()
            tree.setColumnCount(3)
            tree.setHeaderLabels(["處理項目", "狀態", "耗時"])
            tree.setRootIsDecorated(False)
            tree.setAlternatingRowColors(True)
            tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
            tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            tree.header().setSectionResizeMode(2, QHeaderView.ResizeToContents)
            layout.addWidget(tree)

            note = QLabel("完成項目會以綠色標示；等待中／處理中維持原本底色。進度條依解析項目完成數計算；全部完成後視窗會自動關閉。")
            note.setWordWrap(True)
            layout.addWidget(note)

            self.parse_progress_dialog = dlg
            self.parse_progress_tree = tree
            self.parse_progress_summary = summary
            self.parse_progress_dialog_bar = bar

        if not dlg.isVisible():
            dlg.show()
        dlg.raise_()
        return dlg

    def _close_parse_progress_dialog(self):
        dlg = getattr(self, "parse_progress_dialog", None)
        if dlg is not None:
            dlg.hide()

    def _parse_progress_reset(self, raw_elapsed=None, mode=None, packet_count=None, show_dialog=None):
        """開始一次 RRF 載入時重設解析進度；只有首次 full 載入顯示小視窗。"""
        if show_dialog is None:
            show_dialog = not bool(getattr(self, "first_full_parse_done", False))
        self._parse_progress_popup_enabled = bool(show_dialog)
        self._parse_stage_wall_start = time.perf_counter()
        self._parse_stage_timings = {}
        self._parse_stage_states = {}
        self._parse_stage_order = [
            "RRF raw", "raw-adapter",
            "ground", "skill2", "act3", "move", "stand", "new",
            "state3", "status", "efst", "couple", "par", "vanish",
            "drop", "map_events", "map_changes", "guilds", "sid",
            "full_packets", "all Thread", "merge_with_true_sid", "資料整理", "UI更新", "整體完成",
        ]
        self._parse_stage_meta = {
            "mode": mode or "",
            "packet_count": int(packet_count or 0),
            "completed": 0,
            "total": 0,
            "active": "RRF raw",
            "total_lines": 0,
            "processed_lines": 0,
        }
        for name in self._parse_stage_order:
            self._parse_stage_states[name] = "pending"
        if raw_elapsed is not None:
            self._parse_stage_timings["RRF raw"] = float(raw_elapsed)
            self._parse_stage_states["RRF raw"] = "done"
        else:
            self._parse_stage_states["RRF raw"] = "running"

        if self._parse_progress_popup_enabled:
            self._ensure_parse_progress_dialog()
        self._render_parse_progress()
        QApplication.processEvents()

    def _parse_progress_set(self, name, *, state=None, elapsed=None, completed=None, total=None, active=None, total_lines=None, processed_lines=None):
        if not hasattr(self, "_parse_stage_timings"):
            self._parse_progress_reset()
        if elapsed is not None:
            self._parse_stage_timings[name] = float(elapsed)
        if state is not None:
            self._parse_stage_states[name] = state
        if completed is not None:
            self._parse_stage_meta["completed"] = int(completed)
        if total is not None:
            self._parse_stage_meta["total"] = int(total)
        if active is not None:
            self._parse_stage_meta["active"] = active
        if total_lines is not None:
            self._parse_stage_meta["total_lines"] = max(0, int(total_lines))
        if processed_lines is not None:
            self._parse_stage_meta["processed_lines"] = max(0, int(processed_lines))
        self._render_parse_progress()

    def _render_parse_progress(self):
        dlg = getattr(self, "parse_progress_dialog", None)
        tree = getattr(self, "parse_progress_tree", None)
        summary = getattr(self, "parse_progress_summary", None)
        dialog_bar = getattr(self, "parse_progress_dialog_bar", None)

        meta = getattr(self, "_parse_stage_meta", {})
        elapsed_total = 0.0
        if hasattr(self, "_parse_stage_wall_start"):
            elapsed_total = max(0.0, time.perf_counter() - self._parse_stage_wall_start)

        active = meta.get("active", "") or ""
        mode = meta.get("mode", "") or ""
        packet_count = int(meta.get("packet_count", 0) or 0)

        timings = getattr(self, "_parse_stage_timings", {})
        states = getattr(self, "_parse_stage_states", {})
        visible_order = list(getattr(self, "_parse_stage_order", []))
        if hasattr(self, "show_packet_decode_checkbox") and not self.show_packet_decode_checkbox.isChecked():
            visible_order = [n for n in visible_order if n != "full_packets"]

        # 單一真實進度來源：小視窗與主 UI 都依同一份 stage state 計算。
        # pending/running 不算完成，done/error 都代表該步驟已結束。
        total = len(visible_order)
        completed = sum(1 for n in visible_order if states.get(n) in ("done", "error"))
        meta["completed"] = completed
        meta["total"] = total
        pct_done = (completed / max(1, total)) * 100.0 if total else 0.0

        summary_text = f"模式：{mode or '讀取中'}　封包：{packet_count:,}　經過：{elapsed_total:.1f} 秒"
        if total:
            summary_text += f"　已完成：{completed}/{total}（{pct_done:.0f}%）"
        if active:
            summary_text += f"\n目前：{active}"
        if summary is not None:
            summary.setText(summary_text)

        state_text = {
            "pending": "○ 等待中",
            "running": "▶ 處理中",
            "done": "✓ 已完成",
            "error": "✕ 錯誤",
        }

        if tree is not None:
            existing = {}
            for i in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(i)
                existing[item.text(0)] = item

            for name in visible_order:
                item = existing.get(name)
                if item is None:
                    item = QTreeWidgetItem([name, "", ""])
                    tree.addTopLevelItem(item)
                state = states.get(name, "pending")
                item.setText(1, state_text.get(state, state))
                item.setText(2, f"{timings[name]:.2f} s" if name in timings else "—")

                # 完成項目使用低亮度綠色；等待／處理中沿用原底色。
                if state == "done":
                    bg = QBrush(QColor(72, 125, 83))
                elif state == "error":
                    bg = QBrush(QColor(120, 65, 65))
                else:
                    bg = QBrush()
                for col in range(3):
                    item.setBackground(col, bg)

            for i in range(tree.topLevelItemCount() - 1, -1, -1):
                if tree.topLevelItem(i).text(0) not in visible_order:
                    tree.takeTopLevelItem(i)

        if total:
            pct = int(round(100 * completed / max(1, total)))
        else:
            pct = 0
        if states.get("整體完成") == "done":
            pct = 100
        pct = max(0, min(100, pct))
        if dialog_bar is not None:
            dialog_bar.setValue(pct)
        if hasattr(self, "progress_bar"):
            self.progress_bar.setValue(pct)

        if hasattr(self, "status") and active and active != "完成":
            count_text = f"{completed}/{total}" if total else "準備中"
            self.status.setText(f"RRF解析 {count_text}｜{active}｜{elapsed_total:.1f}s")

    def on_worker_start_time(self, t0):
        self.process_start_time = t0   # ★ 儲存開始時間
        self.estimated_total_time = None

    def start_worker(self, rrf_path):
        # 如果上一個 worker 在跑，先停止
        if self.worker_thread:
            self.worker.stop()
            self.worker_thread.quit()
            self.worker_thread.wait()

        # ====== 建立 / 延用 raw incremental reader ======
        abs_rrf_path = os.path.abspath(rrf_path)
        if self.rrf_reader is None or self.rrf_reader.path != abs_rrf_path:
            self.rrf_reader = RRFIncrementalReader(abs_rrf_path)

        # 只有第一次完整載入顯示解析小視窗；後續 delta 更新只同步主 UI 進度條。
        self._parse_progress_reset(
            mode="讀取中", packet_count=0,
            show_dialog=not bool(getattr(self, "first_full_parse_done", False)),
        )

        self.worker_thread = QThread()
        self.worker = RRFWorker(abs_rrf_path, self.rrf_reader)
        self.worker.moveToThread(self.worker_thread)
        
        # ====== 信號連線 ======
        self.worker_thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.failed.connect(self.on_worker_failed)
        self.worker.start_time.connect(self.on_worker_start_time)
        self.worker.status_msg.connect(self.on_worker_status)
        

        # 收到 finished / failed 後結束 thread
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)

        self.worker_thread.start()
        #self.status.setText("正在讀取 / 解析 RRF ...")

    def on_worker_status(self, data):
        if "status" in data:
            self.status.setText(data["status"])

        if "progress" in data:
            self.progress_bar.setValue(data["progressbar"])

    def on_worker_finished(self, result):
        self.progress_bar.show()
        QApplication.processEvents()

        delta = result["delta"]
        elapsed = result["elapsed"]

        # poll() 已經完成 RRF 的結果級增量判斷：full / delta / none。
        if delta.mode == "none":
            self.status.setText(f"共解析到 {len(self.parsed_data)} 筆（RRF 沒有新的完整封包）")
            self.progress_bar.setValue(100)
            self.is_processing = False
            self._load_lock = False
            self._finish_packet_decode_reload()

            interval = self.refresh_input.value()
            if interval > 0 and not self.underMouse():
                self.auto_timer.start(interval * 1000)
            self.update_load_button_text()
            self._close_parse_progress_dialog()
            return

        mode = delta.mode
        # raw 階段完成；沿用 start_worker() 的總計時，不重新歸零。
        if not hasattr(self, "_parse_stage_meta"):
            self._parse_progress_reset(mode=mode, packet_count=len(delta.packets))
        self._parse_stage_meta["mode"] = mode
        self._parse_stage_meta["packet_count"] = len(delta.packets)
        self._parse_progress_set("RRF raw", state="done", elapsed=elapsed, active="raw-adapter")

        # 第一階段相容層：raw bytes 已直接由 Python RRF reader 取得，完全不寫 TXT。
        # 為了先保留既有 decode_* 的行為，暫時只在記憶體中產生舊 parser 需要的
        # 最小文字 block。下一階段可逐一把 parse_* 改成直接接 RawPacket.data。
        t0_opentxt = time.perf_counter()
        text = delta.to_legacy_text(include_metadata=True)
        total_text_lines = (text.count("\n") + 1) if text else 0
        self._parse_progress_set(
            "raw-adapter", state="running", active="建立相容解析資料",
            total_lines=total_text_lines, processed_lines=0,
        )

        map_name = parse_replaydata_mapname(text)
        if map_name:
            # current_map_name 保留「Replay 最新地圖」；小地圖實際顯示哪張，
            # 由全域播放時間對應的 map_change event 決定。
            self.current_map_name = map_name

        if not text.strip():
            self.status.setText("RRF 有更新，但沒有可供分析的新封包")
            self.progress_bar.setValue(100)
            self.is_processing = False
            self._load_lock = False
            self._finish_packet_decode_reload()
            interval = self.refresh_input.value()
            if interval > 0 and not self.underMouse():
                self.auto_timer.start(interval * 1000)
            self._close_parse_progress_dialog()
            return

        t1_opentxt = time.perf_counter()
        raw_adapter_elapsed = t1_opentxt - t0_opentxt
        self._parse_progress_set(
            "raw-adapter", state="done", elapsed=raw_adapter_elapsed, active="平行解析封包",
            total_lines=total_text_lines, processed_lines=0,
        )
        print("====RRF raw → compatibility blocks====")
        print(f"[raw-adapter] 耗時: {raw_adapter_elapsed * 1000:.3f} ms")
        print("====多執行緒區段====")
        self._render_parse_progress()
        self.status.setText(f"直接解析 raw packet（{mode}，新增 {len(delta.packets)} 包）...")
        QApplication.processEvents()

        from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED

        # -------------------------------------------------------
        # ❶ 多執行緒平行解析封包
        # -------------------------------------------------------
        t0_allThread = time.perf_counter()


        checked = check_button_state(self)

        def _timed_parse_call(func, *args, **kwargs):
            t0 = time.perf_counter()
            result = func(*args, **kwargs)
            return result, (time.perf_counter() - t0)
        
        with ThreadPoolExecutor(max_workers=12) as exe:
            futures = {
                "ground": exe.submit(_timed_parse_call, parse_groundskill_blocks, text),
                "skill2": exe.submit(_timed_parse_call, parse_skill2_blocks, text),
                "act3":   exe.submit(_timed_parse_call, parse_act3_blocks, text),
                "move":   exe.submit(_timed_parse_call, parse_moveentry11_blocks, text),
                "stand":  exe.submit(_timed_parse_call, parse_standentry11_blocks, text),
                "new":    exe.submit(_timed_parse_call, parse_newentry11_blocks, text),
                "state3": exe.submit(_timed_parse_call, parse_statechange3_blocks, text),
                "status": exe.submit(_timed_parse_call, parse_status_change_blocks, text),
                "efst":   exe.submit(
                    _timed_parse_call, extract_efstinfo_values,
                    content=text,
                    include_status_changes=True,
                ),
                "couple": exe.submit(_timed_parse_call, parse_couplestatus_blocks, text, checked),
                "par":    exe.submit(_timed_parse_call, parse_par_change_blocks, text, checked),
                "vanish": exe.submit(_timed_parse_call, parse_vanish_blocks, text),
                "drop":   exe.submit(_timed_parse_call, parse_itemdrop_blocks, text),
                "map_events": exe.submit(_timed_parse_call, parse_actor_map_events, text),
                "map_changes": exe.submit(_timed_parse_call, parse_replaydata_map_changes, text),
                "guilds": exe.submit(_timed_parse_call, parse_guild_name_info, text),
            }

            # 未勾完整解析時完全不跑這個較重的掃描。
            if self.show_packet_decode_checkbox.isChecked():
                futures["full_packets"] = exe.submit(_timed_parse_call, parse_all_known_packets_complete, text)

            # raw snapshot 每次都帶目前 metadata；delta 時也更新 SID/隊友名稱。
            futures["sid"] = exe.submit(_timed_parse_call, build_sid_to_name_map, text)
            # 即時輪詢 futures；timeout 讓 Qt event loop 持續有機會重繪，
            # 即使最後一個 parser 要跑二三十秒，視窗也不會看起來像當機。
            parser_total = len(futures)
            parser_done = 0
            future_to_name = {future: name for name, future in futures.items()}
            for parser_name in futures:
                self._parse_stage_states[parser_name] = "running"
            self._parse_progress_set(
                "all Thread", state="running", completed=0, total=parser_total, active="平行解析封包"
            )

            pending = set(future_to_name)
            while pending:
                done_now, pending = wait(pending, timeout=0.10, return_when=FIRST_COMPLETED)
                if done_now:
                    for finished_future in done_now:
                        parser_name = future_to_name[finished_future]
                        try:
                            _preview_result, parser_elapsed = finished_future.result()
                            self._parse_stage_timings[parser_name] = parser_elapsed
                            self._parse_stage_states[parser_name] = "done"
                        except Exception:
                            self._parse_stage_states[parser_name] = "error"
                        parser_done += 1
                    converted_lines = int(total_text_lines * parser_done / max(1, parser_total))
                    self._parse_progress_set(
                        "all Thread", completed=parser_done, total=parser_total,
                        active=("平行解析封包" if pending else "處理解析結果"),
                        total_lines=total_text_lines, processed_lines=converted_lines,
                    )
                    # 主 UI 與小視窗皆由 _render_parse_progress() 的同一份 stage state 更新。
                else:
                    self._render_parse_progress()
                QApplication.processEvents()


        # 用來存這次解析後的資料
        if mode == "full":
            self.sid_name_map = {}
            self.did_name_map = {}
            self.did_name_source = {}
            self.efst_info_map = {}
            self.guild_id_name_map = {}
            self.guild_aid_name_map = {}
            self.guild_aid_id_map = {}
            self.self_guild_id = 0
            self.self_guild_name = ""
        elif not hasattr(self, "efst_info_map"):
            self.efst_info_map = {}
        drops = []
        state3 = []
        status_changes = []
        couple_status = []
        par_change = []
        vanish = []
        ground = []
        skill2 = []
        act3 = []
        full_packet_records = []
        actor_map_events = []
        map_change_events = []
        guild_info_result = {}
        
        # 🔥 誰先完成，就先處理誰
        for future in as_completed(futures.values()):
            name = next(k for k, v in futures.items() if v is future)
            result, parser_elapsed = future.result()
            self._parse_progress_set(name, state="done", elapsed=parser_elapsed, active=f"整理 {name} 結果")
            QApplication.processEvents()

            print(f"[{name}] 已完成，開始處理…")

            # 🔥 在這裡依任務名稱立即做對應處理（你要的功能就在這裡）
            if name == "new":
                # 你想要「new entry 完成就立即 decode」
                #standentry_blocks = result
                for blk in result:
                    info = decode_newentry11(blk["hex"], blk["size"])
                    # 0x09FE 的 AID 用來對應傷害封包的 DID。
                    # GID 只保留於完整解析資料，不拿來做未知目標名稱配對。
                    self.update_actor_entry_names(info, "new")
                #print(f"[new] 已立即完成 decode，寫入 {len(result)} 筆")
                print(f"new 已處理")

            elif name == "sid":
                if mode == "full":
                    self.sid_name_map = result
                else:
                    self.sid_name_map.update(result)

            elif name == "ground":
                ground = result
                

            elif name == "skill2":
                skill2 = result

            elif name == "act3":
                act3 = result

            elif name == "move":
                #moveentry_blocks = result
                
                for blk in result:
                    info = decode_moveentry11(blk["hex"], blk["size"])
                    self.update_actor_entry_names(info, "move")
                print(f"move 已處理")
                
            elif name == "stand":
                #standentry_blocks = result
                for blk in result:
                    info = decode_standentry11(blk["hex"], blk["size"])
                    self.update_actor_entry_names(info, "stand")
                print(f"stand 已處理")
                
            elif name == "state3":
                state3 = result

            elif name == "status":
                status_changes = result

            elif name == "efst":
                self.efst_info_map.update({info["id"]: info for info in result})
                
            elif name == "couple":
                couple_status = result
            elif name == "par":
                par_change = result
            elif name == "vanish":
                vanish = result
            elif name == "drop":
                drops = result
            elif name == "map_events":
                actor_map_events = result
            elif name == "map_changes":
                map_change_events = result
            elif name == "guilds":
                guild_info_result = result or {}
                self.guild_id_name_map.update(guild_info_result.get("guild_id_to_name") or {})
                self.guild_aid_name_map.update(guild_info_result.get("aid_to_guild_name") or {})
                self.guild_aid_id_map.update(guild_info_result.get("aid_to_guild_id") or {})
                if int(guild_info_result.get("self_guild_id", 0) or 0):
                    self.self_guild_id = int(guild_info_result.get("self_guild_id", 0) or 0)
            elif name == "full_packets":
                full_packet_records = result
                
        # v2.8：位置事件 + 地圖切換事件共用同一條 replay timeline。
        # 優先使用真正帶 timestamp 的 0x0091 / 0x0092 / 0x0AC7。
        # ReplayData Mapname 沒有時間戳，在 legacy metadata 集中輸出時不能拿來判斷歷史切圖時間。
        # v2.22：自身通常不會收到自己的 09FE/09FF，因此不能只靠 actor entry 的 guild_id。
        # 直接用 Session 的 self AID 去吃 0x0195/0x0A30 的 AID→公會名稱，以及 0x01B4 的 AID→GuildID。
        if self.self_sid:
            self_aid = int(self.self_sid)
            mapped_gid = int(self.guild_aid_id_map.get(self_aid, 0) or 0)
            if mapped_gid:
                self.self_guild_id = mapped_gid
            self.self_guild_name = (
                self.guild_aid_name_map.get(self_aid, "")
                or self.guild_id_name_map.get(int(self.self_guild_id or 0), "")
                or getattr(self, "self_guild_name", "")
            )
            if self.self_guild_id and self.self_guild_name:
                self.guild_id_name_map[int(self.self_guild_id)] = self.self_guild_name

        packet_map_changes = [
            e for e in actor_map_events
            if e.get("kind") == "map_change" and e.get("map_change_source")
        ]

        metadata_for_timeline = list(map_change_events)
        if packet_map_changes:
            # 有 authoritative 切圖封包時，metadata 只在 full 初始載入保留第一張地圖作 0 秒初始地圖。
            # delta 更新帶的是「目前 metadata」，若硬塞回 0 秒會把歷史初始地圖改成新地圖。
            metadata_for_timeline = []
            if mode == "full" and map_change_events:
                initial = dict(map_change_events[0])
                initial["time"] = 0.0
                initial["timestamp"] = "+00:00:00:000"
                initial["map_change_source"] = "metadata_initial"
                metadata_for_timeline.append(initial)
        else:
            # 增量 poll 的 ReplayData metadata 通常只是目前地圖快照，沒有可靠歷史時間；
            # 已經有 timeline 時不要再把它當成新切圖事件。
            if mode != "full":
                metadata_for_timeline = []
            else:
                # 沒有 0x0091/0x0092 時，利用每次 ACCEPT_ENTER/self_pos 的時間對齊 Mapname 順序。
                # 這比依 metadata 在文字中的位置猜時間穩定。
                enter_times = sorted({
                    float(e.get("time", 0.0))
                    for e in actor_map_events
                    if e.get("kind") == "self_pos"
                })
                if metadata_for_timeline and enter_times:
                    aligned = []
                    for idx, event in enumerate(metadata_for_timeline):
                        ev = dict(event)
                        if idx < len(enter_times):
                            ev["time"] = enter_times[idx]
                            ev["timestamp"] = _seconds_to_packet_timestamp(enter_times[idx])
                        elif idx == 0:
                            ev["time"] = 0.0
                            ev["timestamp"] = "+00:00:00:000"
                        ev["map_change_source"] = "metadata_aligned"
                        aligned.append(ev)
                    metadata_for_timeline = aligned

        incoming_minimap_events = list(actor_map_events) + metadata_for_timeline
        if mode == "full":
            combined_minimap_events = incoming_minimap_events
        else:
            combined_minimap_events = list(self.actor_map_events) + incoming_minimap_events

        combined_minimap_events.sort(
            key=lambda e: (
                float(e.get("time", 0.0)),
                0 if e.get("kind") == "map_change" else 1,
                0 if e.get("map_change_source", "").startswith("packet") else 1,
            )
        )

        # 只去掉真正重複的切圖事件。相同地圖之後若曾切到別圖再切回來，必須保留。
        deduped_minimap_events = []
        last_map_name = None
        last_map_time = None
        for event in combined_minimap_events:
            if event.get("kind") == "map_change":
                event_map = (event.get("map_name") or "").strip()
                event_time = float(event.get("time", 0.0))
                if not event_map:
                    continue
                # 同時間 metadata 與 packet 衝突時，以 packet 為準。
                if deduped_minimap_events and deduped_minimap_events[-1].get("kind") == "map_change":
                    prev = deduped_minimap_events[-1]
                    prev_time = float(prev.get("time", 0.0))
                    if abs(prev_time - event_time) < 1e-6:
                        prev_src = prev.get("map_change_source", "")
                        cur_src = event.get("map_change_source", "")
                        if cur_src.startswith("packet") and not prev_src.startswith("packet"):
                            deduped_minimap_events[-1] = event
                            last_map_name = event_map
                            last_map_time = event_time
                        elif event_map == (prev.get("map_name") or "").strip():
                            pass
                        continue
                if event_map == last_map_name and last_map_time is not None and abs(event_time - last_map_time) < 0.001:
                    continue
                last_map_name = event_map
                last_map_time = event_time
            deduped_minimap_events.append(event)

        # v2.13：為每段 move 預先找「同一單位的下一個位置事件」。
        # 如果下一包在預估走完之前就到達，表示這段路徑被改向/校正；
        # 播放時用下一包的實際時間與起點收斂，避免新封包一到就往回跳。
        next_anchor_by_actor = {}
        for ev in reversed(deduped_minimap_events):
            kind = ev.get("kind")
            if kind == "map_change":
                next_anchor_by_actor.clear()
                continue

            ev_aid = int(ev.get("aid", 0) or 0)
            if ev.get("self_event") or (self.self_sid and ev_aid == int(self.self_sid)):
                actor_key = ("self",)
            else:
                actor_key = ("aid", ev_aid) if ev_aid else None

            if actor_key is None:
                continue

            if kind == "move":
                nxt = next_anchor_by_actor.get(actor_key)
                if nxt is not None:
                    ev["_next_pos_time"] = float(nxt.get("time", 0.0))
                    ev["_next_pos_x"] = nxt.get("x")
                    ev["_next_pos_y"] = nxt.get("y")
                # 這包在事件發生當下的位置就是 from_x/from_y；
                # 讓更早一段 move 可以精準銜接到這裡。
                next_anchor_by_actor[actor_key] = {
                    "time": float(ev.get("time", 0.0)),
                    "x": float(ev.get("from_x", 0.0) or 0.0),
                    "y": float(ev.get("from_y", 0.0) or 0.0),
                }
            elif kind in ("spawn", "stand", "self_pos", "stop"):
                next_anchor_by_actor[actor_key] = {
                    "time": float(ev.get("time", 0.0)),
                    "x": float(ev.get("x", 0.0) or 0.0),
                    "y": float(ev.get("y", 0.0) or 0.0),
                }

        # v2.20：actor packet 的 GID 是單位識別；真正公會欄位是 guild_id / GUID。
        # 將 entry packet 的 GuildID 與 0x0195/0x0A30/0x0150/0x01B6 等公會名稱封包關聯。
        for ev in deduped_minimap_events:
            aid = int(ev.get("aid", 0) or 0)
            details = ev.get("details") if isinstance(ev.get("details"), dict) else {}
            guild_id = int(ev.get("guild_id", details.get("guild_id", 0)) or 0)
            if ev.get("self_event") and not guild_id:
                guild_id = int(self.self_guild_id or 0)
            if aid and guild_id:
                self.guild_aid_id_map[aid] = guild_id
            if aid and not guild_id:
                guild_id = int(self.guild_aid_id_map.get(aid, 0) or 0)
            if guild_id:
                ev["guild_id"] = guild_id
            guild_name = (
                self.guild_id_name_map.get(guild_id, "")
                or self.guild_aid_name_map.get(aid, "")
                or (self.self_guild_name if (ev.get("self_event") or (self.self_sid and aid == int(self.self_sid))) else "")
            )
            if guild_name:
                ev["guild_name"] = guild_name
                if guild_id:
                    self.guild_id_name_map[guild_id] = guild_name

        for aid, guild_name in list(self.guild_aid_name_map.items()):
            guild_id = int(self.guild_aid_id_map.get(int(aid), 0) or 0)
            if guild_id and guild_name:
                self.guild_id_name_map[guild_id] = guild_name

        for rec in full_packet_records:
            dec = rec.get("decoded") if isinstance(rec, dict) else None
            if not isinstance(dec, dict):
                continue
            guild_id = int(dec.get("guild_id", 0) or 0)
            aid = int(dec.get("aid", 0) or 0)
            guild_name = self.guild_id_name_map.get(guild_id) or self.guild_aid_name_map.get(aid, "")
            if guild_name:
                dec["guild_name"] = guild_name

        self.actor_map_events = deduped_minimap_events
        self._reset_minimap_replay_state()

        # 完整解析資料獨立保存；不影響原本傷害/掉落統計。
        if mode == "full":
            self.packet_decode_data = full_packet_records
        else:
            self.packet_decode_data.extend(full_packet_records)
        if (
            not getattr(self, "_packet_decode_reload_in_progress", False)
            and self.tabs.indexOf(self.tree_packet_decode) != -1
            and self.tabs.currentWidget() is self.tree_packet_decode
        ):
            self.refresh_packet_decode_tree()

        print("全部 future 已處理完畢")
        
        # 只有 full 模式才重建整體狀態
        from collections import defaultdict
        if mode == "full":
            self.state_change_count = defaultdict(lambda: defaultdict(int))
            self.transform_history = defaultdict(list)
            self.transform_start_time = {}
            self.transform_end_time = {}
            self.transform_original_skin = {}

        # ===========================================
        # 解析開始 / 結束變身封包（STATE + STATE3）
        # ===========================================
        from collections import defaultdict

        # 若還沒有就初始化（一次）
        if not hasattr(self, "transform_start_time"):
            self.transform_start_time = {}

        def ts_to_ms(ts):
            """把 +HH:MM:SS:ms 轉成整數毫秒（無浮點誤差）"""
            h, m, s, ms = map(int, ts[1:].split(":"))
            return (((h * 60 + m) * 60) + s) * 1000 + ms


        DEFAULT_INTERVAL = 10  # fallback 秒數
        TOLERANCE_MS = 200  # ★ 200 毫秒誤差
        for pkt in state3:
            dec = decode_statechange3(pkt["hex"])
            sid  = dec["sid"]
            skin = dec["monsterskin"]
            evt  = dec["transform_event"]
            ts   = pkt["timestamp"]

            if not sid or evt is None:
                continue

            # ★ 時間變成毫秒（無誤差）
            t_now_ms = ts_to_ms(ts)

            # ------------------------------
            # ⭐ START：首次變身出現
            # ------------------------------
            if evt == "start":

                # 只處理 TRANSFORM_DURATION_MAP 白名單內的變身。
                # 不在表內的 monsterskin 仍可被底層封包 decoder 解析，
                # 但不計次數、不建立歷程，也不顯示成變身事件。
                if skin not in TRANSFORM_DURATION_MAP:
                    # 若同 SID 之前殘留舊的追蹤狀態，避免之後 END 誤配。
                    self.transform_original_skin.pop(sid, None)
                    self.transform_start_time.pop(sid, None)
                    self.transform_end_time.pop(sid, None)
                    continue

                # 若是第一次變身 → 記住原始 skin
                if sid not in self.transform_original_skin:
                    self.transform_original_skin[sid] = skin

                original_skin = self.transform_original_skin[sid]

                # 白名單內一定有對應持續秒數，不使用 fallback。
                TRANSFORM_INTERVAL_MS = TRANSFORM_DURATION_MAP[original_skin] * 1000

                # start 本身 +1
                self.state_change_count[sid][original_skin] += 1

                # 記錄開始時間（毫秒）
                self.transform_start_time[sid] = t_now_ms

                # 清掉舊 end（避免干擾）
                if sid in self.transform_end_time:
                    del self.transform_end_time[sid]

            # ------------------------------
            # ⭐ END：推算中間是否該 +1
            # ------------------------------
            elif evt == "end":

                self.transform_end_time[sid] = t_now_ms

                if sid not in self.transform_start_time:
                    continue

                # END 封包通常 monsterskin=0，因此只接受先前已追蹤到的白名單 START。
                original_skin = self.transform_original_skin.get(sid)
                if original_skin not in TRANSFORM_DURATION_MAP:
                    self.transform_start_time.pop(sid, None)
                    self.transform_original_skin.pop(sid, None)
                    continue

                TRANSFORM_INTERVAL_MS = TRANSFORM_DURATION_MAP[original_skin] * 1000

                t_start_ms = self.transform_start_time[sid]
                t_end_ms   = t_now_ms

                # ★★★ 新增：計算本次變身實際持續時間 ★★★
                transform_duration_ms = t_end_ms - t_start_ms
                #print(f"[變身持續] SID:{sid} Skin:{original_skin} 持續 {transform_duration_ms} ms ({transform_duration_ms/1000:.3f} 秒)")
                ### NEW ###
                # ★★★ 新增：寫入變身紀錄 ★★★
                self.transform_history[sid].append({
                    "skin": original_skin,
                    "duration_ms": transform_duration_ms,
                    "duration_sec": transform_duration_ms / 1000,
                    "start": t_start_ms,
                    "end": t_end_ms,
                })

                # --- 你的段數推算（我用修正版） ---
                effective_end_ms = t_end_ms - TOLERANCE_MS
                next_check = t_start_ms + TRANSFORM_INTERVAL_MS

                while next_check <= effective_end_ms:
                    self.state_change_count[sid][original_skin] += 1
                    next_check += TRANSFORM_INTERVAL_MS

                # 清除
                del self.transform_original_skin[sid]
                del self.transform_start_time[sid]



        # 來源角色（自己）的 SID（能力變動通常是自己）
        if mode == "full":
            self.self_sid = parse_session_gid(text) or 0

        stat_events = []

        for blk in couple_status:
            dec = decode_couplestatus(blk["hex"])
            if dec is None:
                continue
            stat_events.append({
                "timestamp": blk["timestamp"],
                "skill_id": 0,
                "skill_name": "素質能力變動",
                "sid": self.self_sid,
                "did": "",
                "damage": 0,
                #"damage_display": f'{dec["stat_name"]} = {dec["base"]} + {dec["plus"]}',  # 你要的字串
                "damage_display": f'{dec["stat_name"]} ',
                #"level": "",
                "level": f'{dec["base"]} + {dec["plus"]}',
                "hit_count": "",
                "skill_delay": "",
                "global_delay": "",
            })

        for blk in par_change:
            dec = decode_par_change(blk["hex"])
            if dec is None:
                continue
            stat_events.append({
                "timestamp": blk["timestamp"],
                "skill_id": 0,
                "skill_name": "面板能力變動",
                "sid": self.self_sid,
                "did": "",
                "damage": 0,
                #"damage_display": f'{dec["stat_name"]} = {dec["value"]}',
                "damage_display": f'{dec["stat_name"]} ',
                #"level": "",
                "level": f'{dec["value"]}',
                "hit_count": "",
                "skill_delay": "",
                "global_delay": "",
            })
            
        # 一般狀態事件：STATE_CHANGE2 固定為開始，STATE_CHANGE 固定為結束。
        # 狀態名稱統一取 extract_efstinfo_values() 解析出的 COLOR_TITLE_BUFF 標題。
        status_events = []
        for blk in status_changes:
            dec = decode_status_change(blk["hex"], blk["packet_kind"])
            if dec["status_id"] in buffid:
                continue
            status_id = dec["status_id"]
            status_info = self.efst_info_map.get(status_id, {})
            # 僅使用 COLOR_TITLE_BUFF；沒有名稱時只顯示狀態 ID。
            status_name = status_info.get("name", "").strip()
            if status_name:
                status_display = f'{dec["status_event_name"]}：{status_name} (ID {status_id})'
            else:
                status_display = f'{dec["status_event_name"]} (ID {status_id})'

            status_events.append({
                "timestamp": blk["timestamp"],
                "skill_id": status_id,
                "skill_name": status_display,
                "sid": "",
                "did": dec["did"],
                "damage": 0,
                "damage_display": "",
                "level": "",
                "hit_count": "",
                "skill_delay": "",
                "global_delay": "",
                "status_id": status_id,
                "status_name": status_name,
                "efst_name": status_info.get("efst_name", ""),
                "status_event": dec["status_event"],
            })

        # VANISH 顯示事件：UI 提供四種可勾選類型。
        # 事件先完整放入 raw_data，之後 apply_did_filter() 再依勾選狀態決定畫面顯示。
        vanish_display_names = {
            0: "離開視野",
            1: "死亡",
            2: "登出",
            3: "瞬移",
        }
        vanish_events = []
        for ev in vanish:
            mode_value = ev.get("mode")
            if mode_value not in vanish_display_names:
                continue
            vanish_events.append({
                "timestamp": ev["timestamp"],
                "skill_id": 0,
                "skill_name": vanish_display_names[mode_value],
                "sid": "",
                "did": ev["did"],
                "damage": 0,
                "damage_display": "",
                "level": "",
                "hit_count": "",
                "skill_delay": "",
                "global_delay": "",
                "vanish_mode": mode_value,
                "vanish_mode_name": ev.get("mode_name", ""),
                "status_event": "vanish",
            })



        
        t1_allThread = time.perf_counter()
        all_thread_elapsed = t1_allThread - t0_allThread
        print(f"[all Thread] 解析耗時: {all_thread_elapsed * 1000:.3f} ms")
        self._parse_progress_set(
            "all Thread", state="done", elapsed=all_thread_elapsed, active="整併封包",
            total_lines=total_text_lines, processed_lines=total_text_lines,
        )

        self.status.setText("封包解析完成，正在整併資料...")
        QApplication.processEvents()


        # -------------------------------------------------------
        # ❹ 封包整併（原本程式碼）
        # -------------------------------------------------------
        all_packets = ground + skill2 + act3
        all_packets.sort(key=lambda x: x["timestamp"])
        # 統計 SID 的攻擊次數（hit_count）
        from collections import defaultdict
        self.sid_attack_count = defaultdict(int)

        for pkt in all_packets:
            # parse_* 實際使用的 type 是全大寫：GROUND / SKILL2 / ACT3。
            if pkt["type"] not in ("GROUND", "SKILL2", "ACT3"):
                continue

            dec = pkt.get("decoded")
            if not dec:
                continue

            sid = dec.get("sid", 0)
            hits = dec.get("hit_count", 1)

            if sid:
                self.sid_attack_count[sid] += hits

        # -------------------------------------------------------
        # ❺ 修正假 SID（不建議多執行緒，要保持順序）
        # -------------------------------------------------------
        merge_t0 = time.perf_counter()
        self._parse_progress_set("merge_with_true_sid", state="running", active="merge_with_true_sid")
        QApplication.processEvents()
        if mode == "full":
            all_packets = merge_with_true_sid(all_packets)
        else:
            all_packets = self.merge_new_packets_with_true_sid(all_packets)
        merge_elapsed = time.perf_counter() - merge_t0
        self._parse_progress_set("merge_with_true_sid", state="done", elapsed=merge_elapsed, active="整理傷害資料")

        data_stage_t0 = time.perf_counter()
        self._parse_progress_set("資料整理", state="running", active="整理傷害資料")
        self.status.setText("正在整理傷害資料...")
        QApplication.processEvents()

        INT_MAX = 2147483647  # 32-bit signed int 上限
        new_parsed_data = []

        for p in all_packets:
            if p["type"] not in ("SKILL2", "ACT3"):
                continue

            if p["decoded"] is None:
                continue

            d = p["decoded"].copy()
            d["timestamp"] = p["timestamp"]

            # 主傷害（技能傷害 / 普攻主手）
            # v2.16：damage == 0 也保留成真正的攻擊事件；是否顯示由右上選項控制。
            # 負值或超過 signed 32-bit 的值仍視為無效資料。
            dmg = int(d.get("damage", 0) or 0)
            main_damage_positive = 0 < dmg <= INT_MAX
            main_damage_zero = (dmg == 0)

            # 先看 ACT3 是否有有效左手傷害，用來避免左右手攻擊次數重複計算。
            left_damage = int(d.get("damage2", 0) or 0) if p["type"] == "ACT3" else 0
            left_damage_positive = 0 < left_damage <= INT_MAX

            if main_damage_positive or main_damage_zero:
                d["is_offhand_damage"] = False
                d["zero_damage_event"] = bool(main_damage_zero)
                d["is_damage_event"] = True
                # 主手 >0 時由主手代表本次攻擊。主手=0 但左手有傷害時，
                # 攻擊次數交給左手，避免勾選傷害0後同一 ACT3 被算兩次。
                d["counts_as_attack"] = bool(main_damage_positive or not left_damage_positive)
                new_parsed_data.append(d)

            # ACT3 的 damage2 是副手（左手）傷害。
            # 只保留真正 >0 的左手事件；damage2=0 常代表沒有副手傷害，
            # 若也建立 0 傷害事件會產生大量不存在的「左手 MISS」。
            if p["type"] == "ACT3" and left_damage_positive:
                left = d.copy()
                left["skill_id"] = NORMAL_ATTACK_LEFT_SKILL_ID
                left["skill_name"] = "普通攻擊(左手)"
                left["damage"] = left_damage
                left["zero_damage_event"] = False
                left["is_damage_event"] = True
                left["is_offhand_damage"] = True
                left["counts_as_attack"] = not main_damage_positive
                new_parsed_data.append(left)

        new_raw_data = new_parsed_data + stat_events + status_events + vanish_events
        
        new_vanish_points = [
            {
                "timestamp": ev["timestamp"],
                "time_ms": timestamp_to_ms(ev["timestamp"]),
                "did": ev["did"],
                "packet_pos": ev["packet_pos"],   # ★ 新增
            }
            for ev in vanish
            if ev.get("mode") == 1
        ]

        if mode == "full":
            self.vanish_points = new_vanish_points
        else:
            self.vanish_points.extend(new_vanish_points)
            self.vanish_points.sort(key=lambda x: (x["time_ms"], x.get("packet_pos", -1)))

        if mode == "full":
            match_vanish_points = new_vanish_points
        else:
            match_vanish_points = self.vanish_points + new_vanish_points

        drop_events = []
        for blk in drops:
            dec = decode_itemdrop(blk["hex"])
            item_id = dec["item_id"]
            item_name = item_name_map.get(item_id, f"ID {item_id}")
            effect_id = item_effect_map.get(item_id)   # ★ 先定義

            source_did, source_name = self.resolve_drop_source_by_tolerance(
                blk["timestamp"],
                blk["packet_pos"],          # ★ 傳入掉落封包位置
                match_vanish_points         # ★ 傳入這次可用的 vanish pool
            )

            
            map_name = self.current_map_name.strip()
            nav_cmd = f"/navi {map_name} {dec['x']}/{dec['y']}" if map_name else ""
            
            drop_events.append({
                "timestamp": blk["timestamp"],
                "source": source_name,
                "source_did": source_did,
                "item_id": item_id,
                "item_name": item_name,
                "effect_id": effect_id,   # ★ 新增
                "amount": dec["amount"],
                "x": dec["x"],
                "y": dec["y"],
                "nav_cmd": nav_cmd,
            })

        if mode == "full":
            self.parsed_data = new_parsed_data
            self.raw_data = sorted(new_raw_data, key=lambda x: x.get("timestamp", ""))
            self.drop_data = sorted(drop_events, key=lambda x: x.get("timestamp", ""))
        else:
            self.parsed_data.extend(new_parsed_data)
            self.raw_data.extend(new_raw_data)
            self.raw_data.sort(key=lambda x: x.get("timestamp", ""))
            self.drop_data.extend(drop_events)
            self.drop_data.sort(key=lambda x: x.get("timestamp", ""))


        self.current_filtered_raw = self.raw_data.copy()
        self.current_drop_data = self.drop_data.copy()

        # v2.14：RRF 資料完成後把小地圖需要的純資料同步到獨立 process。
        # 只在資料更新時做一次；60FPS 播放每幀不再複製整份傷害資料。
        self._sync_minimap_compute_sources()

        # ★ 這裡資料已經完成
        data_stage_elapsed = time.perf_counter() - data_stage_t0
        self._parse_progress_set("資料整理", state="done", elapsed=data_stage_elapsed, active="更新圖表與統計")
        ui_stage_t0 = time.perf_counter()
        self._parse_progress_set("UI更新", state="running", active="更新圖表與統計")
        self.status.setText("正在更新圖表與統計...")
        QApplication.processEvents()
        # 記錄使用者目前的攻方 / 受方選擇，更新資料後盡量保留。
        previous_did_selection = self.did_filter.currentText()
        previous_did_value = self.did_filter.currentData()
        previous_sid_selection = self.sid_filter.currentText()
        previous_sid_value = self.sid_filter.currentData()

        did_set = sorted({d.get("did") for d in self.parsed_data if d.get("did") is not None})
        sid_set = sorted({d.get("sid") for d in self.parsed_data if d.get("sid") is not None})

        # popup 展開時不重建該下拉選單，避免使用者選到一半被刷新。
        if not self.is_did_popup_open:
            self.did_filter.blockSignals(True)
            self.did_filter.clear()
            self.did_filter.addItem(FILTER_ALL, None)
            self.did_filter.addItem(FILTER_ALL_WITH_STAT, None)

            for did in did_set:
                # 目標名稱統一解析：SID/既有 DID 名稱 -> 09FE.AID 對 DID -> 未知目標。
                name = self.lookup_actor_name(did) or "未知目標"
                self.did_filter.addItem(f"{name} ({did})", did)

            if previous_did_value is not None:
                index = self.did_filter.findData(previous_did_value)
            else:
                index = self.did_filter.findText(previous_did_selection)
            self.did_filter.setCurrentIndex(index if index != -1 else 0)
            self.did_filter.blockSignals(False)

        if not self.is_sid_popup_open:
            self.sid_filter.blockSignals(True)
            self.sid_filter.clear()
            self.sid_filter.addItem(FILTER_ALL, None)

            for sid in sid_set:
                if sid in self.sid_name_map:
                    name = self.sid_name_map[sid]
                elif sid in self.did_name_map:
                    name = self.did_name_map[sid]
                else:
                    name = "未知攻方"

                self.sid_filter.addItem(f"{name} ({sid})", sid)

            if previous_sid_value is not None:
                index = self.sid_filter.findData(previous_sid_value)
            else:
                index = self.sid_filter.findText(previous_sid_selection)
            self.sid_filter.setCurrentIndex(index if index != -1 else 0)
            self.sid_filter.blockSignals(False)




        # 預設顯示全部
        self.current_filtered_data = self.parsed_data.copy()

        # ====== 更新 UI ======
        self.apply_did_filter()
        #self.update_raw_table()
        self.update_group_tree()
        self.refresh_chart()
        self.update_hud_top5()
        ui_stage_elapsed = time.perf_counter() - ui_stage_t0
        self._parse_progress_set("UI更新", state="done", elapsed=ui_stage_elapsed, active="完成")



        #self.status.setText(f"更新完成，耗時 {elapsed:.3f} 秒")        
        #self.status.setText(f"共解析到 {len(self.parsed_data)} 筆 更新耗時：{elapsed:.2f} 秒")
        real_elapsed = time.time() - self.process_start_time
        finalize_elapsed = max(0.0, time.perf_counter() - getattr(self, "_parse_stage_wall_start", time.perf_counter()))
        self._parse_progress_set("整體完成", state="done", elapsed=finalize_elapsed, active="完成")
        self._render_parse_progress()

        self.status.setText(f"共解析 {len(self.parsed_data)} 筆 更新耗時：{real_elapsed:.2f} 秒")
        self.progress_bar.setValue(100)
        if getattr(self, "parse_progress_dialog_bar", None) is not None:
            self.parse_progress_dialog_bar.setValue(100)
        QApplication.processEvents()
        self._close_parse_progress_dialog()
        
        self.first_full_parse_done = True

        self.is_processing = False
        self._load_lock = False
        self._finish_packet_decode_reload()

        interval = self.refresh_input.value()
        if interval > 0 and not self.underMouse():
            self.mouse_paused = False
            self.auto_timer.start(interval * 1000)
        elif interval > 0 and self.underMouse():
            self.mouse_paused = True

        self.update_load_button_text()

        if self.rrf_worker:
            self.rrf_worker.block = False
        if self.background_enabled and not self.rrf_thread:
            print("啟動背景 RRF→TXT 迴圈")
            self.start_background_rrf_worker()

    def stop_background_rrf_worker(self):
        if self.rrf_worker:
            print("停止背景 RRF → TXT")
            self.rrf_worker.stop()
            self.rrf_thread.quit()
            self.rrf_thread.wait()
            self.rrf_thread = None
            self.rrf_worker = None

    def update_hud_top5(self):
        """DPS: 使用最後 10 秒，但不足 10 秒時用實際秒數（動態秒數法）"""
        if not self.current_filtered_data:
            self.hud.clear_hud()
            return

        from collections import defaultdict

        # 將 timestamp 轉成秒
        def ts_to_sec(ts):
            h, m, s, ms = map(int, ts[1:].split(":"))
            return h*3600 + m*60 + s + ms/1000

        # 整場資料
        all_times = [ts_to_sec(d["timestamp"]) for d in self.current_filtered_data]
        t_end = max(all_times)
        window_start = t_end - 5  # 最後 5 秒

        # 統計整場總傷害 + 收集最後 10 秒內資訊
        total_damage = defaultdict(int)
        last_hits = defaultdict(list)  # 每個 sid 的 [(t, dmg), ... ]

        for d in self.current_filtered_data:
            sid = d["sid"]
            dmg = d["damage"]
            t = ts_to_sec(d["timestamp"])

            # ★ 全場總傷害
            total_damage[sid] += dmg

            # ★ 最後 10 秒內的傷害（用list儲存，後續動態算法）
            if t >= window_start:
                last_hits[sid].append((t, dmg))

        top_list = []

        for sid in total_damage:
            total = total_damage[sid]
            hits = last_hits.get(sid, [])

            # -------------------------
            # ★ 動態秒數 DPS 計算邏輯
            # -------------------------
            if not hits:
                # 最後 10 秒無傷害 → 找該 SID 最新的傷害
                # 逆序掃描 current_filtered_data
                recent = []
                last_time = None
                
                for d in reversed(self.current_filtered_data):
                    if d["sid"] != sid:
                        continue
                    t = ts_to_sec(d["timestamp"])
                    if last_time is None:
                        last_time = t
                    # 收集最新連續傷害（秒數遞減中）
                    if t == last_time:
                        recent.append((t, d["damage"]))
                    else:
                        break  # 中斷表示已離開連續傷害
                    
                # 重新計算實際秒數 = hit count
                hits = list(reversed(recent))

            # 現在 hits 至少有一筆
            if hits:
                # 取擊數 = min(10, 實際筆數)
                count = min(10, len(hits))
                dmg_sum = sum(d for (_, d) in hits[-count:])
                
                # 有效秒數 = 初始為 count，但如果同一秒多 hit → 要計算真正秒距
                time_list = [t for (t, _) in hits[-count:]]
                duration = time_list[-1] - time_list[0]
                if duration <= 0:
                    duration = count  # 若同秒傷害，回退到「以 hit 數作為秒數」

                # ★ 真正 DPS
                dps = dmg_sum / duration
            else:
                dps = 0

            # 名稱
            if sid not in self.sid_name_map:
                continue   # ⭐ 跳過，這筆不加入排行

            name = self.sid_name_map[sid]

            top_list.append({
                "name": name,
                "total": total,
                "dps": dps
            })

        # 排序並顯示前 5
        top_list.sort(key=lambda x: x["total"], reverse=True)
        self.hud.update_hud(top_list[:5])




        
    def on_worker_failed(self, msg):
        self.status.setText(f"解析錯誤#")#：{msg}")
        print(f"解析錯誤：{msg}")
        try:
            active = getattr(self, "_parse_stage_meta", {}).get("active", "RRF raw") or "RRF raw"
            stage = active if active in getattr(self, "_parse_stage_order", []) else "RRF raw"
            self._parse_progress_set(stage, state="error", active=f"錯誤：{msg}")
            QApplication.processEvents()
        except Exception:
            pass
        self._close_parse_progress_dialog()
        self.progress_bar.hide()
        self.progress_bar.setValue(0)
        self.is_processing = False
        self._load_lock = False
        if getattr(self, "_packet_decode_reload_in_progress", False):
            self._packet_decode_reload_in_progress = False
            if (self.show_packet_decode_checkbox.isChecked()
                    and self.tabs.indexOf(self.tree_packet_decode) != -1):
                self._set_packet_decode_message(f"完整封包重新載入失敗：{msg}")

    def start_auto_update(self):
        if not self.rrf_thread and self.background_enabled:
            self.start_background_rrf_worker()
            
    def start_background_rrf_worker(self):
        # raw 版不再需要 50ms 背景 copy + EXE 轉 TXT。
        # 自動更新直接由 auto_timer 觸發 start_worker() -> reader.poll()。
        self.rrf_thread = None
        self.rrf_worker = None

    # ========================================================
    # 讀取檔案
    # ========================================================


    def load_file(self):
        print("\n=== load_file() 被呼叫 ===")
        traceback.print_stack(limit=5)
        print("=== end ===\n")

        if self.worker_thread and not self.worker_thread.isRunning():
            self.is_processing = False

        if getattr(self, "_load_lock", False) or self.is_processing:
            return

        self._load_lock = True
        if self.is_processing:
            return

        started = False

        try:
            self.is_processing = True
            interval = self.refresh_input.value()

            # ★ 秒數 = 0：手動選檔
            if interval == 0:
                self.background_enabled = False
                self.auto_timer.stop()

                rrf_path, _ = QFileDialog.getOpenFileName(
                    self, "選擇 RRF", "", "RRF File (*.rrf)"
                )

                if not rrf_path:
                    self.status.setText("沒有選擇檔案")
                    return

                self.last_rrf_path = rrf_path
                self.reset_incremental_txt_state(clear_data=True)
                
                self.last_txt_signature = None
                self.last_txt_path = None
                self.current_filtered_data = []
                self.current_filtered_raw = []
                self.current_drop_data = []
                self.current_drop_filtered_raw = []
                self.vanish_points = []

                self.hud.clear_hud()
                self.tree_group.clear()
                self.chart_status_text = "圖表處理中…"
                self.draw_empty_chart()
                self.table_raw.setRowCount(0)
                self.table_drop.setRowCount(0)
                self.tabs.setCurrentIndex(0)

                self.reset_filter_combos()

                self.tree_group.viewport().update()
                QApplication.processEvents()

            else:
                old_rrf_path = self.last_rrf_path

                if self.auto_latest_checkbox.isChecked() and self.last_rrf_path:
                    latest = self.get_latest_rrf_in_same_folder()
                    if latest:
                        self.last_rrf_path = latest

                print("old_rrf_path =", old_rrf_path)
                print("new_rrf_path =", self.last_rrf_path)
                print("path_changed =", old_rrf_path != self.last_rrf_path if old_rrf_path and self.last_rrf_path else None)

                if old_rrf_path and self.last_rrf_path and old_rrf_path != self.last_rrf_path:
                    self.status.setText(f"偵測到新 RRF：{os.path.basename(self.last_rrf_path)}")

                    self.hud.clear_hud()
                    self.tree_group.clear()
                    self.chart_status_text = "圖表處理中…"
                    self.draw_empty_chart()
                    self.table_raw.setRowCount(0)
                    self.table_drop.setRowCount(0)
                    self.tabs.setCurrentIndex(0)

                    self.reset_filter_combos()

                    self.reset_incremental_txt_state(clear_data=True)
                    self.last_txt_signature = None
                    self.last_txt_path = None
                    self.current_filtered_data = []
                    self.current_filtered_raw = []
                    self.drop_data = []
                    self.current_drop_data = []
                    self.vanish_points = []

                    self.tree_group.viewport().update()
                    QApplication.processEvents()

            if not self.last_rrf_path:
                self.status.setText("請先選擇 RRF 檔案（秒數 = 0）")
                return

            self.start_worker(self.last_rrf_path)
            started = True
            self.update_load_button_text()

        finally:
            if not started:
                self._load_lock = False


    # ========================================================
    # 讀取同資料夾內最新的rrf檔案
    # ========================================================
    def get_latest_rrf_in_same_folder(self):
        """
        在目前 last_rrf_path 所在資料夾中，
        找出「最後修改時間最新」的 .rrf 檔案。
        找不到就回傳 None。
        """
        if not self.last_rrf_path:
            return None

        folder = os.path.dirname(self.last_rrf_path)
        try:
            files = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.lower().endswith(".rrf")
            ]
            if not files:
                return None

            latest = max(files, key=os.path.getmtime)
            return latest
        except Exception as e:
            # 這裡不特別中斷，只是印錯誤以防 debug
            print("get_latest_rrf_in_same_folder error:", e)
            return None


    # ========================================================
    # Tab1：Raw 顯示
    # ========================================================
    def _raw_table_row_time(self, row):
        """傷害歷程 row 的 replay 絕對秒數。"""
        t = self.timestamp_to_float_seconds(row.get("timestamp"))
        return float(t) if t is not None else None

    def _populate_raw_table_row(self, table_row, d):
        """只建立/替換一列傷害歷程；播放模式會重複使用這個函式。"""
        self.table_raw.setItem(table_row, 0, QTableWidgetItem(d.get("timestamp", "")))
        self.table_raw.setItem(table_row, 1, QTableWidgetItem(d.get("skill_name", "")))

        sid = d.get("sid", 0)
        if sid in self.sid_name_map:
            sid_display = f"{self.sid_name_map[sid]}"
        elif sid in self.did_name_map:
            sid_display = f"{self.did_name_map[sid]}"
        else:
            sid_display = str(sid)
        self.table_raw.setItem(table_row, 2, QTableWidgetItem(sid_display))

        did = d.get("did", 0)
        name = self.lookup_actor_name(did) or str(did)
        self.table_raw.setItem(table_row, 3, QTableWidgetItem(name))

        dmg_text = d.get("damage_display")
        if dmg_text is None:
            dmg_text = f"{int(d.get('damage', 0) or 0):,}"
        self.table_raw.setItem(table_row, 4, QTableWidgetItem(dmg_text))
        self.table_raw.setItem(table_row, 5, QTableWidgetItem(str(d.get("level", 0))))
        self.table_raw.setItem(table_row, 6, QTableWidgetItem(str(d.get("hit_count", 0))))
        self.table_raw.setItem(table_row, 7, QTableWidgetItem(str(d.get("skill_delay", 0))))
        self.table_raw.setItem(table_row, 8, QTableWidgetItem(str(d.get("global_delay", 0))))

    def _resize_raw_table_columns(self):
        """完整刷新時才測量欄寬；播放每一 tick 不做 O(rows*cols) 掃描。"""
        metrics = QFontMetrics(self.table_raw.font())
        padding = metrics.horizontalAdvance("字")

        for col in range(self.table_raw.columnCount()):
            header = self.table_raw.horizontalHeaderItem(col)
            max_width = metrics.horizontalAdvance(header.text() if header else "")
            for row in range(self.table_raw.rowCount()):
                item = self.table_raw.item(row, col)
                if item is not None:
                    max_width = max(max_width, metrics.horizontalAdvance(item.text()))
            self.table_raw.setColumnWidth(col, max(max_width + padding, 80))

    def _get_replay_end_sec(self):
        """取得整個 Replay 的最晚時間，不受 SID/DID/播放上限篩選影響。"""
        latest = 0.0
        for seq in (
            getattr(self, "raw_data", []),
            getattr(self, "parsed_data", []),
            getattr(self, "drop_data", []),
            getattr(self, "packet_decode_data", []),
        ):
            for row in seq:
                t = self.timestamp_to_float_seconds(row.get("timestamp"))
                if t is not None and t > latest:
                    latest = t
        # 小地圖 actor 封包可能比最後一筆傷害更晚，Replay slider 也要涵蓋它們。
        for event in getattr(self, "actor_map_events", []):
            t = float(event.get("time", 0.0) or 0.0)
            if t > latest:
                latest = t
        return latest

    def _build_playback_raw_source_without_cutoff(self):
        """建立傷害歷程播放來源，但刻意不套用全域 playhead 上限。

        這樣暫停後再播放，或把滑桿往前跳時，未來事件仍保留在來源中。
        """
        selected_did_text = self.did_filter.currentText()
        did_value = self.did_filter.currentData()
        sid_value = self.sid_filter.currentData()
        include_stat = selected_did_text == FILTER_ALL_WITH_STAT

        raw_base = getattr(self, "raw_data", self.parsed_data)
        raw_source = list(raw_base) if include_stat else [
            d for d in raw_base if d.get("skill_name") not in STAT_SKILL_NAMES
        ]

        if not self.show_zero_damage_checkbox.isChecked():
            raw_source = [d for d in raw_source if not d.get("zero_damage_event", False)]

        if not self.show_status_history_checkbox.isChecked():
            raw_source = [
                d for d in raw_source
                if d.get("status_event") not in ("start", "end", "vanish")
            ]
        else:
            if not self.show_state_change_checkbox.isChecked():
                raw_source = [
                    d for d in raw_source
                    if d.get("status_event") not in ("start", "end")
                ]
            raw_source = [
                d for d in raw_source
                if d.get("status_event") != "vanish"
                or self.is_vanish_mode_visible(d.get("vanish_mode"))
            ]

        if did_value is not None:
            raw_source = [d for d in raw_source if d.get("did") == did_value]

        if sid_value is not None:
            raw_source = [
                d for d in raw_source
                if int(d.get("damage", 0) or 0) <= 0 or d.get("sid") == sid_value
            ]

        if self.damage_time_range is not None:
            range_start, range_end = self.damage_time_range
            raw_source = [
                d for d in raw_source
                if (lambda t: t is not None and range_start <= t <= range_end)(
                    self.timestamp_to_float_seconds(d.get("timestamp"))
                )
            ]

        return raw_source

    def _get_transform_counts_for_display(self):
        """依目前全域 playhead 計算變身次數；非播放模式直接用完整統計。"""
        if not self.damage_playback_mode:
            return self.state_change_count

        cutoff_ms = int(round(max(0.0, self.damage_playback_current_sec) * 1000.0))
        counts = defaultdict(lambda: defaultdict(int))
        tolerance_ms = 200

        for sid, history in getattr(self, "transform_history", {}).items():
            for rec in history:
                skin = rec.get("skin")
                if skin not in TRANSFORM_DURATION_MAP:
                    continue
                start_ms = int(rec.get("start", 0) or 0)
                if start_ms > cutoff_ms:
                    continue
                end_ms = min(int(rec.get("end", cutoff_ms) or cutoff_ms), cutoff_ms)
                counts[sid][skin] += 1
                interval_ms = int(TRANSFORM_DURATION_MAP[skin] * 1000)
                if interval_ms <= 0:
                    continue
                effective_end_ms = end_ms - tolerance_ms
                next_check = start_ms + interval_ms
                while next_check <= effective_end_ms:
                    counts[sid][skin] += 1
                    next_check += interval_ms

        # Replay 結尾仍處於變身中的 SID 也納入目前時間的累積。
        for sid, start_ms in getattr(self, "transform_start_time", {}).items():
            skin = getattr(self, "transform_original_skin", {}).get(sid)
            if skin not in TRANSFORM_DURATION_MAP:
                continue
            start_ms = int(start_ms or 0)
            if start_ms > cutoff_ms:
                continue
            # 若這個 start 已經在 history 中結束，不重複。
            if any(int(h.get("start", -1)) == start_ms for h in getattr(self, "transform_history", {}).get(sid, [])):
                continue
            counts[sid][skin] += 1
            interval_ms = int(TRANSFORM_DURATION_MAP[skin] * 1000)
            effective_end_ms = cutoff_ms - tolerance_ms
            next_check = start_ms + interval_ms
            while interval_ms > 0 and next_check <= effective_end_ms:
                counts[sid][skin] += 1
                next_check += interval_ms

        return counts

    def _format_playback_time(self, sec):
        ms = max(0, int(round(float(sec) * 1000.0)))
        return self.ms_to_timestamp(ms)

    def _update_damage_playback_time_label(self, current=None):
        if current is None:
            current = self.damage_playback_current_sec
        text = (
            f"{self._format_playback_time(current)} / "
            f"{self._format_playback_time(self.damage_playback_range_end)}"
        )
        if hasattr(self, "damage_playback_time_label"):
            self.damage_playback_time_label.setText(text)
        # 小地圖顯示同一個全域 playhead。
        window = getattr(self, "minimap_window", None)
        if window is not None and hasattr(window, "playback_time_label"):
            window.playback_time_label.setText(text)

    def _playback_slider_to_sec(self, value=None):
        if value is None:
            value = self.damage_playback_slider.value()
        return self.damage_playback_range_start + (int(value) / 1000.0)

    def _set_playback_slider_sec(self, sec):
        if not hasattr(self, "damage_playback_slider"):
            return
        sec = min(max(float(sec), self.damage_playback_range_start), self.damage_playback_range_end)
        rel_ms = int(round((sec - self.damage_playback_range_start) * 1000.0))
        old = self.damage_playback_slider.blockSignals(True)
        self.damage_playback_slider.setValue(rel_ms)
        self.damage_playback_slider.blockSignals(old)

        # 鏡像到小地圖滑桿；blockSignals 避免形成 seek 回圈。
        window = getattr(self, "minimap_window", None)
        if window is not None and hasattr(window, "playback_slider"):
            mini_old = window.playback_slider.blockSignals(True)
            window.playback_slider.setValue(rel_ms)
            window.playback_slider.blockSignals(mini_old)
        self._update_damage_playback_time_label(sec)

    def _sync_damage_playback_source(self, data=None, keep_current=True):
        """更新播放來源。滑桿固定代表整個 Replay 的 0 -> 結尾。"""
        if not hasattr(self, "damage_playback_slider"):
            return

        # 播放模式中 current_filtered_raw 已經被 playhead 截短，不能拿它當未來來源。
        if self.damage_playback_mode:
            data = self._build_playback_raw_source_without_cutoff()
        elif data is None:
            data = getattr(self, "current_filtered_raw", getattr(self, "current_filtered_data", []))

        timed = []
        for row in data:
            t = self._raw_table_row_time(row)
            if t is not None:
                timed.append((t, row))
        timed.sort(key=lambda x: x[0])

        self.damage_playback_source = [row for _, row in timed]
        self.damage_playback_times = [t for t, _ in timed]

        # v2.0：全域播放永遠從 Replay 0 秒開始；篩選不改變滑桿總長度。
        range_start = 0.0
        range_end = self._get_replay_end_sec()
        if range_end <= 0.0 and self.damage_playback_times:
            range_end = max(self.damage_playback_times)

        old_current = self.damage_playback_current_sec
        self.damage_playback_range_start = float(range_start)
        self.damage_playback_range_end = float(range_end)

        duration_ms = max(0, int(round((range_end - range_start) * 1000.0)))
        # v2.1：更新資料時調整 range 不應觸發使用者 seek。
        _old_slider_signals = self.damage_playback_slider.blockSignals(True)
        self.damage_playback_slider.setRange(0, duration_ms)
        self.damage_playback_slider.blockSignals(_old_slider_signals)
        enabled = duration_ms > 0
        self.damage_playback_slider.setEnabled(enabled)
        self.damage_playback_btn.setEnabled(enabled)

        window = getattr(self, "minimap_window", None)
        if window is not None and hasattr(window, "playback_slider"):
            mini_old = window.playback_slider.blockSignals(True)
            window.playback_slider.setRange(0, duration_ms)
            window.playback_slider.setEnabled(enabled)
            window.playback_slider.blockSignals(mini_old)
            window.playback_btn.setEnabled(enabled)
            for btn in getattr(window, "playback_jump_buttons", []):
                btn.setEnabled(enabled)

        if not enabled:
            if self.damage_playback_running:
                self.pause_damage_playback()
            self.damage_playback_current_sec = range_start
            self.damage_playback_anchor_sec = range_start
            self._set_playback_slider_sec(range_start)
            return

        if keep_current and range_start <= old_current <= range_end:
            current = old_current
        else:
            current = range_start

        self.damage_playback_current_sec = current
        # 全域播放的累積起點固定是 0 秒。
        self.damage_playback_anchor_sec = range_start
        self._set_playback_slider_sec(current)

        # 播放中若因篩選、圈選或增量資料更新而重新同步範圍，
        # 從目前 playhead 重新校準 wall clock，避免下一 tick 突然跳時。
        if self.damage_playback_running:
            self.damage_playback_base_sec = current
            self.damage_playback_wall_t0 = time.perf_counter()

    def _rebuild_playback_table_to_current(self):
        """篩選條件改變時，重建 0 秒～目前 playhead；timer tick 本身只 append。"""
        self.table_raw.setRowCount(0)
        if not self.damage_playback_times:
            self.damage_playback_cursor = 0
            return

        # v2.0：滑到 1:00 就顯示 0:00～1:00 的全部歷程。
        start_idx = bisect.bisect_left(self.damage_playback_times, self.damage_playback_range_start - 1e-9)
        end_idx = bisect.bisect_right(self.damage_playback_times, self.damage_playback_current_sec + 1e-9)
        self.damage_playback_cursor = start_idx

        for idx in range(start_idx, end_idx):
            r = self.table_raw.rowCount()
            self.table_raw.insertRow(r)
            self._populate_raw_table_row(r, self.damage_playback_source[idx])
            self.damage_playback_cursor = idx + 1

        if self.table_raw.rowCount():
            self.table_raw.scrollToBottom()

    def _seek_damage_playback(self, sec, clear_and_anchor=True):
        """跳到指定 Replay 秒數，整個介面顯示 0 秒～該秒的累積狀態。"""
        sec = min(max(float(sec), self.damage_playback_range_start), self.damage_playback_range_end)

        # 全域播放和「圈選區間分析」是兩種不同模式。
        # 使用滑桿/播放時清除圈選，確保滑到 1:00 就一定是 0:00～1:00，
        # 不會被先前 30～40 秒之類的圈選再次截斷。
        if self.damage_time_range is not None:
            self.damage_time_range = None
            self.update_damage_range_label()
            self._update_chart_resolution_labels()
            if hasattr(self, "btn_select_range") and self.btn_select_range.isChecked():
                old = self.btn_select_range.blockSignals(True)
                self.btn_select_range.setChecked(False)
                self.btn_select_range.blockSignals(old)
            if hasattr(self, "left_pan"):
                self.left_pan.enabled = True

        self.damage_playback_mode = True
        self.damage_playback_current_sec = sec
        self.damage_playback_anchor_sec = self.damage_playback_range_start
        self._set_playback_slider_sec(sec)
        # 一次重算整個介面；apply_did_filter 內也會重建 0～目前時間的歷程表。
        self.apply_did_filter()

    def jump_damage_playback(self, delta_sec):
        """v2.17：相對目前 playhead 快退/快進，範圍固定限制在 Replay 0～結尾。"""
        # 尚未建立 range 時先同步一次，確保按鈕在資料剛載入後也可直接使用。
        if self.damage_playback_range_end <= self.damage_playback_range_start:
            data = getattr(self, "current_filtered_raw", getattr(self, "current_filtered_data", []))
            self._sync_damage_playback_source(data, keep_current=True)
        if self.damage_playback_range_end <= self.damage_playback_range_start:
            return

        if self.damage_playback_mode:
            current = float(self.damage_playback_current_sec)
        else:
            current = float(self._playback_slider_to_sec())

        target = min(
            max(current + float(delta_sec), self.damage_playback_range_start),
            self.damage_playback_range_end,
        )
        was_running = bool(self.damage_playback_running)
        self._seek_damage_playback(target, clear_and_anchor=True)

        # 播放中跳轉後立即以新位置作為 wall-clock 基準，避免下一 tick 又跳回舊軌跡。
        if was_running:
            self.damage_playback_base_sec = target
            self.damage_playback_wall_t0 = time.perf_counter()

    def on_damage_playback_speed_changed(self, value):
        """v2.17：播放中變更倍速時，先鎖定當下 playhead，再用新倍速平順續播。"""
        new_speed = min(max(float(value), 0.1), 4.0)
        old_speed = float(getattr(self, "damage_playback_speed", 1.0) or 1.0)

        if self.damage_playback_running:
            now = time.perf_counter()
            elapsed = max(0.0, now - self.damage_playback_wall_t0)
            current = self.damage_playback_base_sec + elapsed * old_speed
            current = min(max(current, self.damage_playback_range_start), self.damage_playback_range_end)
            self.damage_playback_current_sec = current
            self._set_playback_slider_sec(current)
            self.damage_playback_base_sec = current
            self.damage_playback_wall_t0 = now

        self.damage_playback_speed = new_speed

        # v2.26：主 UI / 小地圖播放倍速雙向同步，避免兩邊顯示不同。
        window = getattr(self, "minimap_window", None)
        mini_speed = getattr(window, "playback_speed_input", None) if window is not None else None
        if mini_speed is not None and abs(float(mini_speed.value()) - new_speed) > 1e-9:
            mini_speed.blockSignals(True)
            mini_speed.setValue(new_speed)
            mini_speed.blockSignals(False)

    def toggle_damage_playback(self):
        if self.damage_playback_running:
            self.pause_damage_playback()
        else:
            self.start_damage_playback()

    def start_damage_playback(self):
        data = getattr(self, "current_filtered_raw", getattr(self, "current_filtered_data", []))
        self._sync_damage_playback_source(data, keep_current=True)
        if self.damage_playback_range_end <= self.damage_playback_range_start:
            return

        # 第一次按播放：從滑桿目前位置開始，但統計內容固定累積自 0 秒。
        if not self.damage_playback_mode:
            sec = self._playback_slider_to_sec()
            self._seek_damage_playback(sec, clear_and_anchor=True)

        # 已播放到尾端，再按播放就從 0 秒重播。
        if self.damage_playback_current_sec >= self.damage_playback_range_end - 1e-6:
            self._seek_damage_playback(self.damage_playback_range_start, clear_and_anchor=True)

        self.damage_playback_running = True
        self.damage_playback_base_sec = self.damage_playback_current_sec
        self.damage_playback_wall_t0 = time.perf_counter()
        self.damage_playback_btn.setText("⏸ 暫停")
        window = getattr(self, "minimap_window", None)
        if window is not None and hasattr(window, "playback_btn"):
            window.playback_btn.setText("⏸ 暫停")
        self.damage_playback_timer.start()
        if hasattr(self, "minimap_render_timer"):
            self.minimap_render_timer.start()

    def pause_damage_playback(self):
        if hasattr(self, "damage_playback_timer"):
            self.damage_playback_timer.stop()
        # v2.14：minimap_render_timer 也負責收獨立 process 的結果，暫停播放時不能停止。
        self.damage_playback_running = False
        if hasattr(self, "damage_playback_btn"):
            self.damage_playback_btn.setText("▶ 播放")
        window = getattr(self, "minimap_window", None)
        if window is not None and hasattr(window, "playback_btn"):
            window.playback_btn.setText("▶ 播放")

    def show_all_damage_history(self):
        """離開全域播放模式，整個介面恢復完整 Replay。"""
        self.pause_damage_playback()
        self.damage_playback_mode = False
        self.damage_playback_current_sec = self._get_replay_end_sec()
        self.damage_playback_anchor_sec = 0.0
        self.apply_did_filter()
        data = getattr(self, "current_filtered_raw", getattr(self, "current_filtered_data", []))
        self._sync_damage_playback_source(data, keep_current=False)
        self.damage_playback_current_sec = self.damage_playback_range_end
        self.damage_playback_anchor_sec = 0.0
        self._set_playback_slider_sec(self.damage_playback_range_end)

    def on_damage_playback_slider_pressed(self):
        self._playback_resume_after_seek = self.damage_playback_running
        self.pause_damage_playback()
        self._playback_pending_seek_sec = self._playback_slider_to_sec()

    def on_minimap_playback_slider_pressed(self):
        """小地圖開始拖曳：沿用主時間軸的 pause/resume 邏輯。"""
        self._playback_resume_after_seek = self.damage_playback_running
        self.pause_damage_playback()
        window = getattr(self, "minimap_window", None)
        if window is not None:
            self._playback_pending_seek_sec = self._playback_slider_to_sec(window.playback_slider.value())

    def on_minimap_playback_slider_value_changed(self, value):
        """小地圖 seek，同步主滑桿並沿用既有 33ms 合併器。"""
        if hasattr(self, "damage_playback_slider"):
            old = self.damage_playback_slider.blockSignals(True)
            self.damage_playback_slider.setValue(int(value))
            self.damage_playback_slider.blockSignals(old)
        self.on_damage_playback_slider_value_changed(int(value))

    def on_minimap_playback_slider_released(self):
        window = getattr(self, "minimap_window", None)
        if window is not None and hasattr(self, "damage_playback_slider"):
            value = int(window.playback_slider.value())
            old = self.damage_playback_slider.blockSignals(True)
            self.damage_playback_slider.setValue(value)
            self.damage_playback_slider.blockSignals(old)
        self.on_damage_playback_slider_released()

    def on_damage_playback_slider_value_changed(self, value):
        """v2.1：滑桿拖曳/鍵盤改值時立即排程全介面更新，不等滑鼠放開。"""
        sec = self._playback_slider_to_sec(value)
        self._update_damage_playback_time_label(sec)
        self._playback_pending_seek_sec = sec

        # 內部程式設定 slider 時都有 blockSignals，不會走到這裡。
        # 33ms 合併高速 valueChanged，避免 apply_did_filter 疊成長佇列。
        if hasattr(self, "damage_playback_seek_timer"):
            if not self.damage_playback_seek_timer.isActive():
                self.damage_playback_seek_timer.start()
        else:
            self._flush_damage_playback_live_seek()

    def _flush_damage_playback_live_seek(self):
        """套用目前最新的滑桿位置；只重算最新位置，舊的拖曳事件直接合併掉。"""
        sec = self._playback_pending_seek_sec
        if sec is None:
            return
        self._playback_pending_seek_sec = None

        if (self._playback_last_live_seek_sec is not None and
                abs(float(sec) - float(self._playback_last_live_seek_sec)) < 0.0005):
            return

        self._playback_last_live_seek_sec = float(sec)
        self._seek_damage_playback(sec, clear_and_anchor=True)

    def on_damage_playback_slider_released(self):
        # 放開時把尚未到 33ms 的最後一格立即套用，確保最終位置完全一致。
        sec = self._playback_slider_to_sec()
        self._playback_pending_seek_sec = sec
        if hasattr(self, "damage_playback_seek_timer"):
            self.damage_playback_seek_timer.stop()
        self._flush_damage_playback_live_seek()

        if self._playback_resume_after_seek:
            self.start_damage_playback()
        self._playback_resume_after_seek = False

    def _append_playback_until(self, sec):
        """一次把這個 tick 到期的事件批次填入，避免每筆 insertRow 造成 UI 抖動。"""
        times = self.damage_playback_times
        source = self.damage_playback_source
        cursor = self.damage_playback_cursor
        end_idx = bisect.bisect_right(times, sec + 1e-9, lo=cursor)
        if end_idx <= cursor:
            return

        # 全域播放固定從 0 秒累積，cursor 就是下一筆尚未顯示的事件。
        first_idx = cursor
        count = max(0, end_idx - first_idx)

        if count:
            old_rows = self.table_raw.rowCount()
            self.table_raw.setUpdatesEnabled(False)
            try:
                self.table_raw.setRowCount(old_rows + count)
                out_row = old_rows
                for idx in range(first_idx, end_idx):
                    self._populate_raw_table_row(out_row, source[idx])
                    out_row += 1
            finally:
                self.table_raw.setUpdatesEnabled(True)
            self.table_raw.viewport().update()
            self.table_raw.scrollToBottom()

        self.damage_playback_cursor = end_idx

    def on_damage_playback_tick(self):
        if not self.damage_playback_running:
            return

        elapsed = time.perf_counter() - self.damage_playback_wall_t0
        current = self.damage_playback_base_sec + elapsed * self.damage_playback_speed
        if current >= self.damage_playback_range_end:
            current = self.damage_playback_range_end

        self.damage_playback_current_sec = current
        self._set_playback_slider_sec(current)

        # v2.0：playhead 是全介面的時間上限。
        # 這次更新會同步總傷害、技能統計、圖表、HUD、掉落與歷程。
        self.apply_did_filter(playback_tick=True)
        self._append_playback_until(current)

        if current >= self.damage_playback_range_end - 1e-9:
            self.pause_damage_playback()

    def update_raw_table(self, force_full=False):
        interval = self.refresh_input.value()
        data = getattr(self, "current_filtered_raw", getattr(self, "current_filtered_data", []))
        self._sync_damage_playback_source(data, keep_current=True)

        # 播放模式中，外部篩選/重新解析更新資料時維持目前 playhead，
        # 不突然把整張歷程表灌回 UI。
        if self.damage_playback_mode and not force_full:
            self._rebuild_playback_table_to_current()
            return

        self.table_raw.setRowCount(len(data))
        for r, d in enumerate(data):
            self._populate_raw_table_row(r, d)

        if interval > 0:
            self.table_raw.scrollToBottom()
        self._resize_raw_table_columns()

    def resolve_drop_source_by_tolerance(self, drop_timestamp, drop_packet_pos, vanish_points=None):
        if vanish_points is None:
            vanish_points = getattr(self, "vanish_points", [])

        drop_ms = timestamp_to_ms(drop_timestamp)
        drop_sec = timestamp_to_sec_key(drop_timestamp)
        tolerance_ms = DROP_MATCH_TOLERANCE_MS

        candidates = []
        for vp in vanish_points:
            diff = abs(vp["time_ms"] - drop_ms)
            if diff <= tolerance_ms:
                candidates.append(vp)

        if not candidates:
            return "", "玩家丟棄/魔物視距外死亡"

        # ① 同秒數時，優先找「掉落封包上方」最近的一筆死亡訊息
        same_sec_above = [
            vp for vp in candidates
            if timestamp_to_sec_key(vp["timestamp"]) == drop_sec
            and vp.get("packet_pos") is not None
            and vp["packet_pos"] < drop_packet_pos
        ]
        if same_sec_above:
            best = max(same_sec_above, key=lambda x: x["packet_pos"])
            did = best["did"]
            return did, self.lookup_actor_name(did) or f"ID {did}"

        # ② 其次找「上方」且時間最近的
        above_candidates = [
            vp for vp in candidates
            if vp.get("packet_pos") is not None
            and vp["packet_pos"] < drop_packet_pos
        ]
        if above_candidates:
            best = min(
                above_candidates,
                key=lambda x: (abs(x["time_ms"] - drop_ms), drop_packet_pos - x["packet_pos"])
            )
            did = best["did"]
            return did, self.lookup_actor_name(did) or f"ID {did}"

        # ③ 最後才退回單純最近時間差
        best = min(candidates, key=lambda x: abs(x["time_ms"] - drop_ms))
        did = best["did"]
        return did, self.lookup_actor_name(did) or f"ID {did}"

    def update_drop_table(self):
        interval = self.refresh_input.value()
        data = getattr(self, "current_drop_data", getattr(self, "drop_data", []))
        self.table_drop.setRowCount(len(data))

        for r, d in enumerate(data):
            row_values = [
                d.get("timestamp", ""),
                str(d.get("source", "-")),
                str(d.get("item_name", "")),
                str(d.get("amount", "")),
                str(d.get("x", "")),
                str(d.get("y", "")),
                str(d.get("nav_cmd", "")),
            ]

            # 看這筆物品是否需要高亮
            highlight_color = get_drop_highlight_color(d.get("effect_id"))

            for c, value in enumerate(row_values):
                item = QTableWidgetItem(str(value))

                if highlight_color is not None:
                    item.setBackground(highlight_color)
                    item.setForeground(QColor("#000000"))   # 亮底配黑字比較清楚

                self.table_drop.setItem(r, c, item)

        if interval > 0 and len(data) > 0:
            self.table_drop.scrollToBottom()

        # 跟傷害歷程一樣：依文字內容 + padding 算欄寬
        metrics = QFontMetrics(self.table_drop.font())
        padding = metrics.horizontalAdvance("字" * 1)

        for col in range(self.table_drop.columnCount()):
            max_width = 0

            header_item = self.table_drop.horizontalHeaderItem(col)
            if header_item:
                max_width = metrics.horizontalAdvance(header_item.text())

            for row in range(self.table_drop.rowCount()):
                item = self.table_drop.item(row, col)
                if item is not None:
                    w = metrics.horizontalAdvance(item.text())
                    if w > max_width:
                        max_width = w

            final_width = max_width + padding
            final_width = max(final_width, 90)
            self.table_drop.setColumnWidth(col, final_width)

        self.table_drop.resizeRowsToContents()

    def auto_resize_table_columns(self, table):
        table.resizeColumnsToContents()
        table.resizeRowsToContents()
        table.horizontalHeader().setStretchLastSection(True)

    # ========================================================
    # Tab2：樹狀統計（名字 → 技能列表）
    # ========================================================
    def update_group_tree(self):
        data = self.current_filtered_data
        if not data:
            self.tree_group.clear()
            return

        # 全域播放時，變身次數也只計算到目前 playhead。
        visible_state_change_count = self._get_transform_counts_for_display()

        # ------------------------------------------------
        # 1. 將所有資料依「整秒」分組
        # ------------------------------------------------
        from collections import defaultdict
        sec_map = defaultdict(list)

        def parse_ts(ts):
            h, m, s, ms = map(int, ts[1:].split(":"))
            return h*3600 + m*60 + s, ms

        for d in data:
            sec, ms = parse_ts(d["timestamp"])
            sec_map[sec].append((ms, d))

        all_secs = sorted(sec_map.keys())
        if not all_secs:
            self.tree_group.clear()
            return

        # ------------------------------------------------
        # 2. 找最後秒 S，並判斷是否完整（是否有 S+1）
        # ------------------------------------------------
        S = all_secs[-1]  # 最後一筆傷害的秒數
        if (S + 1) in sec_map:
            T = S          # S 有下一秒 → S 完整
        else:
            T = S - 1      # S 沒有下一秒 → 使用 S-1

        # 如果 T 不存在也沒資料 → 完全沒有完整秒
        if T not in sec_map or T < 0:
            # ★ 用 v3 的作法：照樣列出所有技能，只是 DPS 一律顯示 0
            from collections import defaultdict

            merged = defaultdict(lambda: defaultdict(lambda: {
                "total": 0,
                "count": 0,
                "skill_name": "",
            }))
            sid_total = defaultdict(int)
            sid_attack_count = defaultdict(int)   # ★ 新增：每個 SID 的攻擊次數
            for d in data:
                sid = d["sid"]
                skill = d["skill_id"]
                dmg = d["damage"]

                merged[sid][skill]["total"] += dmg
                merged[sid][skill]["count"] += 1
                merged[sid][skill]["skill_name"] = d["skill_name"]
                sid_total[sid] += dmg
                # 同一個 ACT3 左右手最多只計一次角色攻擊次數；
                # 主手為 0/無效時，會由左手那筆補算一次。
                if d.get("counts_as_attack", True):
                    sid_attack_count[sid] += 1

            # 把結果存到物件上，給後面樹狀圖用
            self.sid_attack_count = sid_attack_count
            
            self.tree_group.clear()

            # 依總傷害排序角色
            sorted_sids = sorted(sid_total.items(), key=lambda x: x[1], reverse=True)

            for sid, total in sorted_sids:
                if sid in self.sid_name_map:
                    name = self.sid_name_map[sid]
                elif sid in self.did_name_map:
                    name = self.did_name_map[sid]
                else:
                    name = str(sid)         

                parent = QTreeWidgetItem([
                    name,
                    "",
                    f"{total:,}",
                    "0"          # ★ 沒有完整秒，DPS 一律 0
                ])

                color = QColor(60, 80, 120)
                for col in range(4):
                    parent.setBackground(col, color)
                    parent.setForeground(col, Qt.white)

                parent.setTextAlignment(2, Qt.AlignRight)
                parent.setTextAlignment(3, Qt.AlignRight)
                self.tree_group.addTopLevelItem(parent)

                # 技能依總傷害排序
                skills = sorted(
                    merged[sid].items(),
                    key=lambda x: x[1]["total"],
                    reverse=True
                )

                for skill_id, stat in skills:
                    skill_name = stat["skill_name"]
                    cnt = stat["count"]
                    total_skill = stat["total"]
                    avg = total_skill / cnt if cnt > 0 else 0

                    skill_label = (
                        skill_name
                        if skill_id == NORMAL_ATTACK_LEFT_SKILL_ID
                        else f"{skill_name} (ID {skill_id})"
                    )
                    child = QTreeWidgetItem([
                        f"{skill_label} - 次數 {cnt}",
                        f"{avg:,.0f}",
                        f"{total_skill:,.0f}",
                        "0"      # ★ 技能 DPS 也固定 0
                    ])

                    for col in range(1, 4):
                        child.setTextAlignment(col, Qt.AlignRight)

                    parent.addChild(child)
                                    
                # ★ 顯示 monsterskin 的變身次數（type=9999）與機率
                skin_dict = visible_state_change_count.get(sid, {})  # dict: skin -> count
                attack_cnt = self.sid_attack_count.get(sid, 0)

                for skin_id, cnt in sorted(skin_dict.items()):
                    if attack_cnt > 0:
                        rate = cnt / attack_cnt * 100
                        rate_str = f"{rate:.2f}%"
                    else:
                        rate_str = "0%"

                    item = QTreeWidgetItem([
                        f"　變身次數 (ID {skin_id}) - 次數 {cnt}  ({rate_str})",
                        "",
                        "",
                        ""
                    ])

                    # ★ 新增：讓這一行知道該顯示哪個 sid 的資料
                    item.setData(0, Qt.UserRole, sid)

                    parent.addChild(item)




                    
                parent.setExpanded(True)

            return


        # ------------------------------------------------
        # 3. 統計：總傷害、技能次數、T 秒傷害與 T 秒次數
        # ------------------------------------------------
        merged = defaultdict(lambda: defaultdict(lambda: {
            "total": 0,
            "count": 0,
            "skill_name": "",
            "T_damage": 0,
            "T_count": 0
        }))
        sid_total = defaultdict(int)
        sid_T_damage = defaultdict(int)
        sid_attack_count = defaultdict(int)   # ★ 新增：每個 SID 的總攻擊次數

        for d in data:
            sid = d["sid"]
            skill = d["skill_id"]
            dmg = d["damage"]
            sec, ms = parse_ts(d["timestamp"])

            merged[sid][skill]["total"] += dmg
            merged[sid][skill]["count"] += 1
            merged[sid][skill]["skill_name"] = d["skill_name"]

            sid_total[sid] += dmg
            # 同一個 ACT3 左右手最多只計一次角色攻擊次數；
            # 主手為 0/無效時，會由左手那筆補算一次。
            if d.get("counts_as_attack", True):
                sid_attack_count[sid] += 1
            
            if sec == T:
                merged[sid][skill]["T_damage"] += dmg
                merged[sid][skill]["T_count"] += 1
                sid_T_damage[sid] += dmg
        # 把統計好的攻擊次數，存起來給樹狀圖使用
        self.sid_attack_count = sid_attack_count
        # ------------------------------------------------
        # 4. 更新樹狀顯示
        # ------------------------------------------------
        self.tree_group.clear()

        sorted_sids = sorted(sid_total.items(), key=lambda x: x[1], reverse=True)

        for sid, total in sorted_sids:
            if sid in self.sid_name_map:
                name = self.sid_name_map[sid]
            elif sid in self.did_name_map:
                name = self.did_name_map[sid]
            else:
                name = str(sid)

            parent = QTreeWidgetItem([
                name,
                "",
                f"{total:,}",
                f"{sid_T_damage[sid]:,}"     # ★ 角色 DPS = T 秒傷害
            ])

            color = QColor(60, 80, 120)  # 深藍

            parent.setBackground(0, color)
            parent.setBackground(1, color)
            parent.setBackground(2, color)
            parent.setBackground(3, color)

            parent.setForeground(0, Qt.white)
            parent.setForeground(1, Qt.white)
            parent.setForeground(2, Qt.white)
            parent.setForeground(3, Qt.white)
            parent.setTextAlignment(2, Qt.AlignRight)
            parent.setTextAlignment(3, Qt.AlignRight)
            self.tree_group.addTopLevelItem(parent)

            # 技能排序（依總傷害）
            skills = sorted(
                merged[sid].items(),
                key=lambda x: x[1]["total"],
                reverse=True
            )

            for skill_id, stat in skills:
                skill_name = stat["skill_name"]
                cnt = stat["count"]
                total = stat["total"]
                T_cnt = stat["T_count"]
                T_dmg = stat["T_damage"]

                skill_label = (
                    skill_name
                    if skill_id == NORMAL_ATTACK_LEFT_SKILL_ID
                    else f"{skill_name} (ID {skill_id})"
                )
                child = QTreeWidgetItem([
                    f"{skill_label} - 次數 {cnt} (秒{T_cnt})",
                    f"{(total/cnt):,.0f}" if cnt > 0 else "0",
                    f"{total:,.0f}",
                    f"{T_dmg:,.0f}"         # ★ 這個技能在 T 秒的 DPS
                ])

                for col in range(1, 4):
                    child.setTextAlignment(col, Qt.AlignRight)

                parent.addChild(child)
                
            # ★ 顯示 monsterskin 的變身次數（type=9999）與機率
            skin_dict = visible_state_change_count.get(sid, {})  # dict: skin -> count
            attack_cnt = self.sid_attack_count.get(sid, 0)

            for skin_id, cnt in sorted(skin_dict.items()):
                if attack_cnt > 0:
                    rate = cnt / attack_cnt * 100
                    rate_str = f"{rate:.2f}%"
                else:
                    rate_str = "0%"

                item = QTreeWidgetItem([
                    f"　變身次數 (ID {skin_id}) - 次數 {cnt}  ({rate_str})",
                    "",
                    "",
                    ""
                ])

                # ★ 新增：讓這一行知道該顯示哪個 sid 的資料
                item.setData(0, Qt.UserRole, sid)

                parent.addChild(item)





            parent.setExpanded(True)

        self.refresh_chart()




        
    def draw_empty_chart(self):
        if hasattr(self, "bar_scrollbar"):
            self.bar_scrollbar.hide()
        if hasattr(self, "toolbar"):
            self.toolbar.hide()
        # 透明背景
        self.fig.patch.set_alpha(0)
        self.canvas.setStyleSheet("background-color: transparent;")

        self.fig.clear()
        ax = self.fig.add_subplot(111)

        ax.set_facecolor("none")

        # 標題
        ax.set_title("總傷害", fontproperties=font, color="#FFFFFF")

        # 中間顯示尚未載入
        ax.text(
            0.5, 0.5,
            self.chart_status_text,
            ha="center", va="center",
            fontsize=14,
            fontproperties=font,
            color="#777777"
        )

        # 去掉刻度
        ax.set_xticks([])
        ax.set_yticks([])

        # 無外框
        for spine in ax.spines.values():
            spine.set_visible(False)

        self.canvas.draw()

    def draw_damage_chart(self, sorted_sids):
        """總傷害橫條圖：固定顯示 10 人，其他用捲軸瀏覽。"""
        self._bar_sorted_sids = list(sorted_sids or [])

        if self._bar_sorted_sids:
            max_total = self._bar_sorted_sids[0][1]
            threshold = max_total * 0.01
            filtered = [
                (sid, total) for sid, total in self._bar_sorted_sids
                if total >= threshold
            ]
        else:
            filtered = []

        visible_rows = max(1, int(getattr(self, "bar_visible_rows", 10)))
        max_start = max(0, len(filtered) - visible_rows)
        sb = getattr(self, "bar_scrollbar", None)
        if sb is not None:
            sb.blockSignals(True)
            sb.setRange(0, max_start)
            sb.setPageStep(visible_rows)
            sb.setSingleStep(1)
            if sb.value() > max_start:
                sb.setValue(max_start)
            start_index = sb.value()
            sb.setVisible(max_start > 0 and self.current_chart_mode == "bar")
            sb.blockSignals(False)
        else:
            start_index = 0

        visible = filtered[start_index:start_index + visible_rows]
        if not visible:
            old_status = self.chart_status_text
            self.chart_status_text = "沒有符合條件的傷害"
            self.draw_empty_chart()
            self.chart_status_text = old_status
            return

        self.fig.clear()
        ax = self.fig.add_subplot(111)
        self.fig.patch.set_alpha(0)
        ax.set_facecolor("none")
        self.canvas.setStyleSheet("background-color: transparent;")

        names = []
        for sid, _ in visible:
            if sid in self.sid_name_map:
                names.append(self.sid_name_map[sid])
            elif sid in self.did_name_map:
                names.append(self.did_name_map[sid])
            else:
                names.append(str(sid))
        values = [total for _, total in visible]

        y = list(range(len(names)))
        bar_colors = [self._sid_chart_color(sid) for sid, _ in visible]
        bars = ax.barh(y, values, height=0.62, color=bar_colors)
        ax.invert_yaxis()
        ax.set_yticks(y)
        ax.set_yticklabels(names, fontproperties=font, color="#FFFFFF", fontsize=9)

        title_name = self.get_active_filter_title()
        if len(filtered) > visible_rows:
            range_text = f"（{start_index + 1}-{start_index + len(visible)} / {len(filtered)}）"
        else:
            range_text = ""
        ax.set_title(
            f"{title_name} 的個別總傷害 {range_text}",
            fontproperties=font,
            color="#FFFFFF"
        )
        ax.set_xlabel("總傷害", fontproperties=font, color="#DDDDDD")
        ax.tick_params(colors="#AAAAAA")
        for spine in ax.spines.values():
            spine.set_visible(False)

        max_value = max(values) if values else 1
        ax.set_xlim(0, max_value * 1.18 if max_value > 0 else 1)
        for bar, val in zip(bars, values):
            ax.text(
                val + max_value * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{val:,}",
                va='center',
                fontsize=9,
                fontproperties=font,
                color="#FFFFFF"
            )

        self.fig.subplots_adjust(left=0.22, right=0.97, top=0.84, bottom=0.20)
        self.canvas.draw_idle()

    def _prepare_timed_damage_rows(self, data=None):
        data = self.current_filtered_data if data is None else data
        rows = []
        for d in data:
            t = self.timestamp_to_float_seconds(d.get("timestamp"))
            if t is None:
                continue
            rows.append((t, d))
        return rows

    def _damage_time_bin_size(self):
        """目前時間圖真正的統計粒度。

        有圈選且範圍 <= 3 秒時改成 0.1 秒一格；其餘維持 1 秒。
        這不是只改 X 軸標籤，而是實際重新分桶統計傷害。
        """
        if self.damage_time_range is not None:
            start, end = self.damage_time_range
            if math.isfinite(start) and math.isfinite(end) and 0 < (end - start) <= 3.000001:
                return 0.1
        # 全域播放在最前 3 秒也使用真正的 0.1 秒分桶。
        if self.damage_playback_mode and 0 < self.damage_playback_current_sec <= 3.000001:
            return 0.1
        return 1.0

    def _damage_time_resolution_text(self):
        return "每0.1秒" if self._damage_time_bin_size() < 1.0 else "每秒"

    def _update_chart_resolution_labels(self):
        """圈選短區間時，按鈕文字同步反映真實統計粒度。"""
        if hasattr(self, "btn_line"):
            self.btn_line.setText(f"顯示{self._damage_time_resolution_text()}折線趨勢圖")
        if hasattr(self, "btn_stairs"):
            self.btn_stairs.setText(f"顯示{self._damage_time_resolution_text()}階梯圖")

    def _sid_chart_color(self, sid):
        """由 SID 決定固定線色，不受排序、圈選或目前可見玩家數影響。"""
        digest = hashlib.md5(str(sid).encode("utf-8", errors="replace")).digest()
        hue = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        # 暗色背景上維持足夠亮度；色相完全由 SID 決定，因此重畫不換色。
        saturation = 0.58 + (digest[4] / 255.0) * 0.18
        value = 0.82 + (digest[5] / 255.0) * 0.14
        return colorsys.hsv_to_rgb(hue, saturation, value)

    def _time_bucket_bounds(self, timed_rows, bin_size):
        """回傳對齊 replay 絕對時間的 bucket index 範圍。"""
        if self.damage_time_range is not None:
            start, end = self.damage_time_range
        elif self.damage_playback_mode:
            # 全域播放的圖表永遠是 0 -> playhead 累積，而不是只看目前附近。
            start = 0.0
            end = max(0.0, float(self.damage_playback_current_sec))
        else:
            start = min(t for t, _ in timed_rows)
            end = max(t for t, _ in timed_rows)

        first_idx = math.floor((start + 1e-9) / bin_size)
        last_idx = math.floor((end + 1e-9) / bin_size)
        if last_idx < first_idx:
            last_idx = first_idx
        return first_idx, last_idx

    def _format_time_tick(self, value, step):
        """小於 1 秒的主要刻度顯示到 0.1 秒，例如 3.1、1:03.2。"""
        if step >= 1:
            return self.format_replay_second(value, False)
        if value is None or not math.isfinite(value) or value < 0:
            return "--"
        # 目前最細統計為 0.1 秒；先四捨五入可避免 3.199999 顯示異常。
        tenth = int(round(value * 10.0))
        total_sec, dec = divmod(tenth, 10)
        h = total_sec // 3600
        m = (total_sec % 3600) // 60
        s = total_sec % 60
        if h:
            return f"{h}:{m:02d}:{s:02d}.{dec}"
        if m:
            return f"{m}:{s:02d}.{dec}"
        return f"{s}.{dec}"

    def _choose_time_tick_step(self, ax):
        """依目前可見時間跨度與 axes 實際像素寬度選主要刻度。

        短圈選（<= 3 秒）允許 0.1 / 0.2 / 0.5 秒刻度；寬度足夠時
        優先顯示 3.1、3.2、3.3...。長區間則仍以 1 秒為最細刻度。
        """
        try:
            xmin, xmax = ax.get_xlim()
            span = abs(float(xmax) - float(xmin))
        except Exception:
            return self._damage_time_bin_size()

        if not math.isfinite(span) or span <= 0:
            return self._damage_time_bin_size()

        try:
            canvas_px = max(240.0, float(self.canvas.width()))
        except Exception:
            canvas_px = max(240.0, self.fig.get_figwidth() * self.fig.dpi)

        try:
            axes_px = max(180.0, canvas_px * float(ax.get_position().width))
        except Exception:
            axes_px = canvas_px * 0.75

        fine_mode = self._damage_time_bin_size() < 1.0
        # 小數秒標籤較短時盡量多排；仍會依實際寬度自動退到 0.2/0.5 秒。
        label_px = 38.0 if fine_mode else 62.0
        max_labels = max(2, int(axes_px // label_px))
        raw_step = span / max_labels

        if fine_mode:
            candidates = (
                0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 20, 30,
                60, 120, 300, 600, 900, 1800, 3600
            )
        else:
            candidates = (
                1, 2, 5, 10, 15, 20, 30,
                60, 120, 300, 600, 900, 1800, 3600, 7200, 14400
            )

        for step in candidates:
            if step >= raw_step - 1e-12:
                return step
        return max(1, int(math.ceil(raw_step / 3600.0)) * 3600)

    def _apply_adaptive_time_ticks(self, ax):
        """依寬度套用主要時間刻度；短圈選可細到 0.1 秒。"""
        if ax is None:
            return
        step = self._choose_time_tick_step(ax)
        ax.xaxis.set_major_locator(MultipleLocator(step))
        ax.xaxis.set_major_formatter(
            FuncFormatter(lambda x, pos, s=step: self._format_time_tick(x, s))
        )

    def _configure_time_axis(self, ax):
        self._apply_adaptive_time_ticks(ax)

        # set_xlim（圈選/滾輪縮放）之後也會重新選刻度間距。
        def _xlim_changed(changed_ax):
            self._apply_adaptive_time_ticks(changed_ax)

        ax.callbacks.connect("xlim_changed", _xlim_changed)

        def format_coord(x, y):
            return (
                f"時間：{self.format_replay_second(x, True)}    "
                f"傷害：{int(round(y)):,}"
            )

        ax.format_coord = format_coord

    def draw_line_chart(self):
        data = self.current_filtered_data
        if not data:
            self.draw_empty_chart()
            return

        from collections import defaultdict

        self.fig.clear()
        ax = self.fig.add_subplot(111)
        self.fig.patch.set_alpha(0)
        ax.set_facecolor("none")
        self.canvas.setStyleSheet("background-color: transparent;")

        timed_rows = self._prepare_timed_damage_rows(data)
        if not timed_rows:
            self.draw_empty_chart()
            return

        bin_size = self._damage_time_bin_size()
        first_idx, last_idx = self._time_bucket_bounds(timed_rows, bin_size)

        # 依 replay 絕對時間分桶；短圈選時是真正每 0.1 秒統計，不只是改刻度。
        timeline = defaultdict(lambda: defaultdict(int))
        for t, d in timed_rows:
            bucket_idx = math.floor((t + 1e-9) / bin_size)
            timeline[d["sid"]][bucket_idx] += int(d.get("damage", 0) or 0)

        sid_total = {sid: sum(bucket_data.values()) for sid, bucket_data in timeline.items()}
        if sid_total:
            max_total = max(sid_total.values())
            threshold = max_total * 0.01
            allowed_sid = {sid for sid, total in sid_total.items() if total >= threshold}
        else:
            allowed_sid = set()

        bucket_indices = list(range(first_idx, last_idx + 1))
        seconds = [round(idx * bin_size, 10) for idx in bucket_indices]

        for sid, bucket_data in timeline.items():
            if sid not in allowed_sid:
                continue
            values = [bucket_data.get(idx, 0) for idx in bucket_indices]
            if sid in self.sid_name_map:
                label = self.sid_name_map[sid]
            elif sid in self.did_name_map:
                label = self.did_name_map[sid]
            else:
                label = f"{sid}"
            ax.plot(
                seconds, values, label=label,
                color=self._sid_chart_color(sid),
            )

        handles, labels = ax.get_legend_handles_labels()
        if handles:
            leg = ax.legend(
                loc="center left",
                bbox_to_anchor=(-0.28, 0.5),
                frameon=True,
            )
            leg.set_draggable(True)

        title_name = self.get_active_filter_title()
        resolution_text = self._damage_time_resolution_text()
        ax.set_title(
            f"{title_name} 的{resolution_text}傷害趨勢",
            fontproperties=font,
            color="#FFFFFF"
        )
        ax.set_xlabel("Replay 時間", fontproperties=font, color="#DDDDDD")
        ax.tick_params(colors="#AAAAAA")
        for spine in ax.spines.values():
            spine.set_visible(False)

        self._configure_time_axis(ax)
        if self.damage_time_range is not None:
            start, end = self.damage_time_range
            if end > start:
                ax.set_xlim(start, end)
        elif self.damage_playback_mode and self.damage_playback_current_sec > 0:
            ax.set_xlim(0, self.damage_playback_current_sec)
        self.fig.subplots_adjust(left=0.20)
        self.setup_damage_span_selector(ax)
        self.canvas.draw()

    def draw_stairs_chart(self):
        """總傷害階梯圖；短圈選時自動改成每 0.1 秒一格。"""
        data = self.current_filtered_data
        if not data:
            self.draw_empty_chart()
            return

        timed_rows = self._prepare_timed_damage_rows(data)
        if not timed_rows:
            self.draw_empty_chart()
            return

        bin_size = self._damage_time_bin_size()
        first_idx, last_idx = self._time_bucket_bounds(timed_rows, bin_size)

        per_bucket = defaultdict(int)
        for t, d in timed_rows:
            bucket_idx = math.floor((t + 1e-9) / bin_size)
            per_bucket[bucket_idx] += int(d.get("damage", 0) or 0)

        bucket_indices = list(range(first_idx, last_idx + 1))
        values = [per_bucket.get(idx, 0) for idx in bucket_indices]
        edges = [round(idx * bin_size, 10) for idx in range(first_idx, last_idx + 2)]

        self.fig.clear()
        ax = self.fig.add_subplot(111)
        self.fig.patch.set_alpha(0)
        ax.set_facecolor("none")
        self.canvas.setStyleSheet("background-color: transparent;")

        ax.stairs(values, edges, fill=True, alpha=0.28, linewidth=1.2)

        title_name = self.get_active_filter_title()
        resolution_text = self._damage_time_resolution_text()
        ax.set_title(
            f"{title_name} 的{resolution_text}總傷害階梯",
            fontproperties=font,
            color="#FFFFFF"
        )
        ax.set_xlabel("Replay 時間", fontproperties=font, color="#DDDDDD")
        ax.set_ylabel(f"{resolution_text}傷害", fontproperties=font, color="#DDDDDD")
        ax.tick_params(colors="#AAAAAA")
        for spine in ax.spines.values():
            spine.set_visible(False)

        self._configure_time_axis(ax)
        if self.damage_time_range is not None:
            start, end = self.damage_time_range
            if end > start:
                ax.set_xlim(start, end)
        elif self.damage_playback_mode and self.damage_playback_current_sec > 0:
            ax.set_xlim(0, self.damage_playback_current_sec)
        self.setup_damage_span_selector(ax)
        self.canvas.draw()

    def update_actor_entry_names(self, info, source):
        """把 actor entry 的 AID 建立成 DID 名稱索引。

        傷害封包的來源欄位視為 AID、目標欄位視為 DID。
        0x09FE 的 AID 就是用來回查未知 DID 名稱的值；GID 雖然仍保留在
        完整封包解析結果中，但不參與未知目標名稱配對。

        0x09FE 有時只給 #mk_1 這類內部名稱。這種名稱雖不適合覆寫一般
        actor 名稱，但仍是有效的 AID -> DID 關聯標籤，因此特別保留。
        """
        if not info:
            return
        name = info.get("name")
        aid = info.get("aid") or info.get("did")
        if aid:
            is_09fe = (info.get("packet_id") == 0x09FE or info.get("opcode") == 0x09FE)
            self.update_did_name(
                aid,
                name,
                "09fe" if is_09fe else source,
                allow_internal=is_09fe,
            )

    def find_actor_name_from_09fe(self, did):
        """未知 DID 時，以 0x09FE 的 AID 回查名稱。

        配對關係固定為：09FE.AID == 傷害封包.DID。
        GID 不參與這個名稱解析流程。
        """
        if not did:
            return None

        records = getattr(self, "packet_decode_data", [])
        for record in reversed(records):
            if record.get("opcode") != 0x09FE:
                continue
            dec = record.get("decoded") or {}
            aid = dec.get("aid") or dec.get("did")
            if aid != did:
                continue

            # 09FE 即使只有 #mk_1 這種內部名稱，也要能用來關聯 DID。
            name = sanitize_actor_name(dec.get("name"), allow_internal=True)
            if not name:
                continue

            # 找到後只把 09FE.AID 註冊成 DID 名稱快取；GID 不加入。
            self.update_did_name(aid, name, "09fe", allow_internal=True)
            return name
        return None

    def lookup_actor_name(self, actor_id):
        """統一取得角色/怪物名稱；未知時最後回查 0x09FE。"""
        if not actor_id:
            return None
        if actor_id in self.sid_name_map:
            name = str(self.sid_name_map[actor_id]).strip()
            if name:
                return name
        if actor_id in self.did_name_map:
            # 09FE 名稱可能是 #mk_1；這是 replay 提供的有效關聯標籤。
            allow_internal = self.did_name_source.get(actor_id) == "09fe"
            name = sanitize_actor_name(
                self.did_name_map[actor_id],
                allow_internal=allow_internal,
            )
            if name:
                return name
        return self.find_actor_name_from_09fe(actor_id)

    def update_did_name(self, did, raw_name, source, allow_internal=False):
        """更新 DID 顯示名稱；09FE 可保留 #mk_* / #le_* 內部名稱。"""
        if not did:
            return

        override = MONSTER_NAME_OVERRIDE.get(did)
        if override:
            self.did_name_map[did] = override
            self.did_name_source[did] = "override"
            return

        name = sanitize_actor_name(raw_name, allow_internal=allow_internal)
        if not name:
            return

        priority = {"stand": 1, "move": 2, "new": 3, "09fe": 4, "override": 99}
        old_source = self.did_name_source.get(did)
        old_name = sanitize_actor_name(
            self.did_name_map.get(did),
            allow_internal=(old_source == "09fe"),
        )
        old_priority = priority.get(old_source, 0)
        new_priority = priority.get(source, 0)

        if old_name is None or new_priority >= old_priority:
            self.did_name_map[did] = name
            self.did_name_source[did] = source

    def get_monster_name_by_did(self, did, fallback=None):
        # 未知 DID 會自動以 0x09FE.AID 回查名稱。
        name = self.lookup_actor_name(did)
        if not name:
            if fallback:
                name = fallback
            elif did:
                name = f"未知目標 ({did})"
            else:
                name = "未知掉落來源"

        name = str(name).strip()
        return name if name else (fallback or "未知掉落來源")


    def pct_text(self, num, den):
        if not den:
            return "0.00%"
        return f"{(num / den) * 100:.2f}%"

    def is_excluded_drop_source(self, row):
        """
        排除不應納入掉落率統計的來源：
        - 玩家丟棄
        - 魔物視距外死亡
        兩種描述你前後有不同寫法，這裡一起兼容。
        """
        source = str(row.get("source", "")).strip()
        return source in {
            "玩家丟棄/魔物視距外死亡",
        }


    def calc_avg_monster_drop_pct(self, item_sources, stats):
        """
        物品父層比例：
        = 平均(各來源怪物的實際掉率)
        = 平均(該怪此物品件數 / 該怪死亡次數)

        例如：
        (85.27 + 83.97 + 81.15) / 3
        """
        rates = []

        for monster_name, monster_cnt in item_sources.items():
            if monster_name in {
                "玩家丟棄/魔物視距外死亡",
            }:
                continue

            death_count = int(stats[monster_name]["death_count"] or 0)
            if death_count <= 0:
                continue

            rates.append((monster_cnt / death_count) * 100)

        if not rates:
            return "0.00%"

        return f"{sum(rates) / len(rates):.2f}%"



    def build_monster_drop_stats(self):
        from collections import defaultdict

        raw_base = getattr(
            self,
            "current_drop_filtered_raw",
            getattr(self, "current_filtered_raw", [])
        )
        drop_base = getattr(self, "current_drop_data", [])

        # key = 怪物名稱（同名怪合併）
        stats = defaultdict(lambda: {
            "death_count": 0,
            "drop_total": 0,
            "drop_items": defaultdict(int),
            "dids": set(),
        })

        # 1) 死亡統計：從內部 raw 的 VANISH mode=1「死亡」事件抓。
        # 這裡不受「傷害歷程顯示狀態」勾選影響，避免關閉顯示後破壞掉落率統計。
        for row in raw_base:
            if row.get("skill_name") != "死亡" or row.get("vanish_mode") != 1:
                continue

            did = row.get("did", 0)
            monster_name = self.get_monster_name_by_did(did)
            stats[monster_name]["death_count"] += 1

            if did:
                stats[monster_name]["dids"].add(did)

        # 2) 掉落統計：從 drop_data 抓
        for row in drop_base:
            did = row.get("source_did", 0)
            fallback_name = row.get("source")
            monster_name = self.get_monster_name_by_did(did, fallback_name)

            item_name = str(row.get("item_name", "未知物品")).strip() or "未知物品"
            amount = int(row.get("amount", 0) or 0)

            stats[monster_name]["drop_total"] += amount
            stats[monster_name]["drop_items"][item_name] += amount

            if did:
                stats[monster_name]["dids"].add(did)

        total_deaths = sum(v["death_count"] for v in stats.values())
        total_drop_amount = sum(v["drop_total"] for v in stats.values())

        return stats, total_deaths, total_drop_amount


    def update_monster_drop_tree(self):
        from collections import defaultdict

        self.tree_monster_drop.clear()

        stats, total_deaths, total_drop_amount = self.build_monster_drop_stats()
        if not stats:
            return

        # =========================================================
        # 整理「所有物品掉落量」與「物品來源怪物」
        # all_item_totals[item_name] = 全部數量
        # all_item_sources[item_name][monster_name] = 該怪掉了多少
        # =========================================================
        all_item_totals = defaultdict(int)
        all_item_sources = defaultdict(lambda: defaultdict(int))

        for monster_name, info in stats.items():
            for item_name, cnt in info["drop_items"].items():
                all_item_totals[item_name] += cnt
                all_item_sources[item_name][monster_name] += cnt

        # =========================================================
        # 最上層：所有物品掉落量（預設摺疊）
        # =========================================================
        all_parent = QTreeWidgetItem([
            "所有物品掉落量",
            f"{total_drop_amount} 件",
            #"100.00%" if total_drop_amount > 0 else "0.00%",
            "",
        ])

        all_parent_color = QColor(90, 70, 120)
        for col in range(3):
            all_parent.setBackground(col, all_parent_color)
            all_parent.setForeground(col, Qt.white)

        all_parent.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
        all_parent.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
        all_parent.setToolTip(0, "所有怪物掉落物合併統計（已排除玩家丟棄/魔物視距外死亡）")
        all_parent.setToolTip(2, "此區僅顯示全部物品總量")

        self.tree_monster_drop.addTopLevelItem(all_parent)

        # =========================================================
        # 物品層
        # 數量：維持實際總件數
        # 比例：改成各來源怪物掉率的平均值
        # =========================================================
        for item_name, cnt in sorted(all_item_totals.items(), key=lambda x: (-x[1], x[0])):
            pct_all = self.calc_avg_monster_drop_pct(all_item_sources[item_name], stats)

            item_node = QTreeWidgetItem([
                f"└ {item_name}",
                f"{cnt} 件",
                pct_all,
            ])
            for col in range(1, 3):
                item_node.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)

            item_node.setToolTip(2, "比例 = 各來源怪物掉率平均值（已排除玩家丟棄/魔物視距外死亡）")
            all_parent.addChild(item_node)

            # 來源怪物層：比例 = 此怪掉出此物品數量 / 此怪死亡次數
            for monster_name, monster_cnt in sorted(
                all_item_sources[item_name].items(),
                key=lambda x: (-x[1], x[0])
            ):
                monster_death_count = stats[monster_name]["death_count"]
                pct_in_item = self.pct_text(monster_cnt, monster_death_count)

                source_node = QTreeWidgetItem([
                    f"    └ {monster_name}",
                    f"{monster_cnt} 件",
                    pct_in_item,
                ])
                for col in range(1, 3):
                    source_node.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)

                source_node.setToolTip(2, "比例 = 此怪物掉落此物品數量 / 此怪物死亡次數")
                item_node.addChild(source_node)

            item_node.setExpanded(False)

        all_parent.setExpanded(False)

        # =========================================================
        # 原本每隻怪物統計
        # =========================================================
        sorted_monsters = sorted(
            stats.items(),
            key=lambda x: (-x[1]["death_count"], -x[1]["drop_total"], x[0])
        )

        for monster_name, info in sorted_monsters:
            death_count = info["death_count"]
            drop_total = info["drop_total"]

            did_list = sorted(info["dids"])
            merge_count = len(did_list)

            parent = QTreeWidgetItem([
                f"{monster_name} x {death_count}",
                "",
                "",
            ])

            parent_color = QColor(70, 85, 110)
            for col in range(3):
                parent.setBackground(col, parent_color)
                parent.setForeground(col, Qt.white)

            parent.setTextAlignment(1, Qt.AlignRight | Qt.AlignVCenter)
            parent.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)

            parent.setToolTip(0, f"相同名稱怪物已合併，合併總數: {merge_count}")
            parent.setToolTip(2, "物品機率 = 此物品數量 / 此怪物死亡次數")

            self.tree_monster_drop.addTopLevelItem(parent)

            for item_name, cnt in sorted(
                info["drop_items"].items(),
                key=lambda x: (-x[1], x[0])
            ):
                pct_in_monster = self.pct_text(cnt, death_count)

                child = QTreeWidgetItem([
                    f"└ {item_name}",
                    f"{cnt} 件",
                    pct_in_monster,
                ])
                for col in range(1, 3):
                    child.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)

                parent.addChild(child)

            parent.setExpanded(True)


    # ========================================================
    # v2.4：GAT 小地圖 / Replay actor state
    # ========================================================
    def _start_minimap_compute_process(self):
        """啟動 v2.14 小地圖獨立計算 process；失敗時仍保留舊同步 fallback。"""
        if self._minimap_compute_process is not None:
            try:
                if self._minimap_compute_process.is_alive():
                    return True
            except Exception:
                pass
        try:
            self._minimap_compute_ctx = mp.get_context("spawn")
            # source 是完整快照，保留 latest-only 即可；Replay frame request/result 則不可丟棄。
            self._minimap_source_queue = self._minimap_compute_ctx.Queue(maxsize=1)
            self._minimap_request_queue = self._minimap_compute_ctx.Queue()
            self._minimap_result_queue = self._minimap_compute_ctx.Queue()
            self._minimap_compute_process = self._minimap_compute_ctx.Process(
                target=minimap_compute_process_main,
                args=(self._minimap_source_queue, self._minimap_request_queue, self._minimap_result_queue),
                name="RRF-Minimap-Compute",
                daemon=True,
            )
            self._minimap_compute_process.start()
            self._minimap_async_ready = True
            self._minimap_async_last_error = ""
            self._sync_minimap_compute_sources()
            return True
        except Exception as e:
            self._minimap_async_ready = False
            self._minimap_async_last_error = str(e)
            print(f"[minimap async] 啟動失敗，改用同步模式: {e}")
            return False

    @staticmethod
    def _queue_replace_latest(q, item):
        if q is None:
            return False
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass
        except Exception:
            return False
        try:
            q.put_nowait(item)
            return True
        except queue.Full:
            try:
                q.get_nowait()
                q.put_nowait(item)
                return True
            except Exception:
                return False
        except Exception:
            return False

    @staticmethod
    def _queue_put_fifo(q, item):
        """v2.19：Replay frame 用 FIFO；不覆蓋、不清空舊 request。"""
        if q is None:
            return False
        try:
            q.put_nowait(item)
            return True
        except queue.Full:
            # request/result queue 在 v2.19 為 unbounded；保留 fallback，寧可等待也不丟。
            try:
                q.put(item, timeout=0.25)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def _sync_minimap_compute_sources(self):
        """把 actor timeline + 精簡傷害索引一次性送到 worker process。"""
        if not getattr(self, "_minimap_async_ready", False):
            return
        process = getattr(self, "_minimap_compute_process", None)
        if process is None:
            return
        try:
            if not process.is_alive():
                self._minimap_async_ready = False
                return
        except Exception:
            return

        # 只傳小地圖真正需要的欄位，避免把 parsed_data 全 dict pickle 過去。
        damage_rows = []
        ids = set()
        include_zero_damage = bool(getattr(self, "show_zero_damage_checkbox", None)
                                   and self.show_zero_damage_checkbox.isChecked())
        for row in getattr(self, "parsed_data", []) or []:
            try:
                damage = int(row.get("damage", 0) or 0)
                if damage < 0:
                    continue
                if damage == 0 and not include_zero_damage:
                    continue
                t = _packet_timestamp_to_seconds(row.get("timestamp"))
                sid = int(row.get("sid", 0) or 0)
                did = int(row.get("did", 0) or 0)
                damage_rows.append((float(t), sid, did, damage, row.get("skill_name") or ""))
                if sid:
                    ids.add(sid)
                if did:
                    ids.add(did)
            except Exception:
                continue

        events = [dict(ev) for ev in (getattr(self, "actor_map_events", []) or [])]
        for ev in events:
            aid = int(ev.get("aid", 0) or 0)
            gid = int(ev.get("gid", 0) or 0)
            if aid:
                ids.add(aid)
            if gid:
                ids.add(gid)

        names = {}
        # 先吃現有快取，再以 event 內名稱補強；不在 worker process 重新掃 09FE。
        for actor_id, name in getattr(self, "sid_name_map", {}).items():
            if name:
                names[int(actor_id)] = str(name)
        for actor_id, name in getattr(self, "did_name_map", {}).items():
            if name and int(actor_id) not in names:
                names[int(actor_id)] = str(name)
        for ev in events:
            aid = int(ev.get("aid", 0) or 0)
            raw_name = ev.get("name")
            if aid and raw_name:
                names[aid] = str(raw_name)
        # 不在這裡對每個未知 ID 呼叫 find_actor_name_from_09fe()；那會造成
        # O(ID數 × 完整封包數) 的重掃。09FE/entry 名稱已經由 did_name_map / events 帶入。

        self._minimap_compute_source_version += 1
        payload = {
            "cmd": "sources",
            "version": self._minimap_compute_source_version,
            "events": events,
            "damage_rows": damage_rows,
            "names": names,
            "guild_names": dict(getattr(self, "guild_id_name_map", {}) or {}),
            "guild_aid_names": dict(getattr(self, "guild_aid_name_map", {}) or {}),
            "self_sid": int(self.self_sid or 0),
            "self_guild_id": int(getattr(self, "self_guild_id", 0) or 0),
            "self_guild_name": str(getattr(self, "self_guild_name", "") or ""),
        }
        self._queue_replace_latest(self._minimap_source_queue, payload)

    def _request_minimap_async_frame(self, sec):
        if not getattr(self, "_minimap_async_ready", False):
            return False
        process = getattr(self, "_minimap_compute_process", None)
        try:
            if process is None or not process.is_alive():
                self._minimap_async_ready = False
                return False
        except Exception:
            return False

        self._minimap_compute_request_seq += 1
        selected_did = self.did_filter.currentData() if hasattr(self, "did_filter") else None
        selected_sid = self.sid_filter.currentData() if hasattr(self, "sid_filter") else None
        sec = max(0.0, float(sec or 0.0))
        damage_range = tuple(self.damage_time_range) if self.damage_time_range is not None else None

        # 人物位置要順：每個 16ms request 都算。傷害箭頭/文字只約每 100ms 更新一次。
        # 暫停/seek/篩選改變時強制更新一次，避免停在舊傷害畫面。
        now_wall = time.perf_counter()
        filter_sig = (
            selected_did, selected_sid, damage_range,
            bool(getattr(self, "show_zero_damage_checkbox", None) and self.show_zero_damage_checkbox.isChecked()),
        )
        include_damage = (
            not bool(getattr(self, "damage_playback_running", False))
            or filter_sig != self._minimap_last_damage_filter_sig
            or sec + 1e-9 < float(self._minimap_last_damage_request_sec)
            or now_wall - float(self._minimap_last_damage_request_wall) >= float(self._minimap_damage_request_interval)
        )
        if include_damage:
            self._minimap_last_damage_request_wall = now_wall
            self._minimap_last_damage_request_sec = sec
            self._minimap_last_damage_filter_sig = filter_sig

        req = {
            "cmd": "frame",
            "seq": self._minimap_compute_request_seq,
            "source_version": self._minimap_compute_source_version,
            "sec": sec,
            "selected_did": selected_did,
            "selected_sid": selected_sid,
            "damage_time_range": damage_range,
            "include_damage": include_damage,
        }
        # v2.19：正常 Replay frame 嚴格排隊，不再 latest-only。
        return self._queue_put_fifo(self._minimap_request_queue, req)

    def _poll_minimap_async_result(self):
        if not getattr(self, "_minimap_async_ready", False):
            return False
        q = getattr(self, "_minimap_result_queue", None)
        if q is None:
            return False
        # v2.19：一次只套一個 FIFO result，讓中間 frame 真的有機會被畫出來。
        # 不再 drain 到最後一幀。
        try:
            latest = q.get_nowait()
        except queue.Empty:
            return False
        except Exception:
            return False
        if latest.get("error"):
            err = latest.get("error")
            if err != self._minimap_async_last_error:
                self._minimap_async_last_error = err
                print(f"[minimap async] 計算錯誤: {err}")
            return False
        if int(latest.get("source_version", -1)) != int(self._minimap_compute_source_version):
            # source 與 request 經不同 multiprocessing.Queue 傳送，極少數情況 request
            # 會比大型 source payload 先抵達。這一幀丟棄後立刻再請求目前 playhead，
            # 避免暫停狀態只送過一次 request 而一直停在舊 frame。
            if getattr(self, "minimap_window", None) is not None and self.minimap_window.isVisible():
                if self.damage_playback_mode:
                    retry_sec = float(self.damage_playback_current_sec or 0.0)
                else:
                    retry_sec = float(self._get_replay_end_sec() or 0.0)
                self._request_minimap_async_frame(retry_sec)
            return False
        seq = int(latest.get("seq", -1))
        if seq <= int(self._minimap_last_applied_seq):
            return False
        self._minimap_last_applied_seq = seq
        self._apply_minimap_async_snapshot(latest)
        return True

    def _apply_minimap_async_snapshot(self, snapshot):
        active_map = (snapshot.get("active_map") or self.current_map_name or "").strip()
        self._minimap_active_map_name = active_map
        if active_map:
            self._switch_minimap_gat_for_map(active_map)

        units = snapshot.get("units") or []
        damage_updated = bool(snapshot.get("damage_updated", snapshot.get("links") is not None))
        links = snapshot.get("links") if damage_updated else None
        sec = float(snapshot.get("sec", 0.0) or 0.0)
        selected_did = self.did_filter.currentData() if hasattr(self, "did_filter") else None
        self.minimap_widget.set_frame(units, links, sec, highlight_aid=selected_did)

        counts = snapshot.get("counts") or {}
        if damage_updated:
            self._minimap_last_damage_line_count = len(links or [])
            self._minimap_last_damage_event_count = int(snapshot.get("damage_event_count", 0) or 0)
        damage_line_count = int(getattr(self, "_minimap_last_damage_line_count", 0) or 0)
        damage_event_count = int(getattr(self, "_minimap_last_damage_event_count", 0) or 0)
        self.minimap_count_label.setText(f"時間 {self._format_playback_time(sec)}")
        self.minimap_count_label.setToolTip(
            f"自身 {int(counts.get('self', 0))}｜玩家 {int(counts.get('player', 0))}｜"
            f"魔物 {int(counts.get('mob', 0))}｜寵物 {int(counts.get('pet', 0))}｜"
            f"NPC {int(counts.get('npc', 0))}｜召喚 {int(counts.get('companion', 0))}｜"
            f"其他 {int(counts.get('other', 0))}\n"
            f"傷害線 {damage_line_count}組 / {damage_event_count}筆"
        )

    def _stop_minimap_compute_process(self):
        process = getattr(self, "_minimap_compute_process", None)
        if process is None:
            return
        self._minimap_async_ready = False
        try:
            self._queue_replace_latest(self._minimap_request_queue, {"cmd": "stop"})
            self._queue_replace_latest(self._minimap_source_queue, {"cmd": "stop"})
        except Exception:
            pass
        try:
            process.join(timeout=0.8)
        except Exception:
            pass
        try:
            if process.is_alive():
                process.terminate()
                process.join(timeout=0.5)
        except Exception:
            pass
        for q in (self._minimap_source_queue, self._minimap_request_queue, self._minimap_result_queue):
            try:
                q.close()
                q.cancel_join_thread()
            except Exception:
                pass
        self._minimap_compute_process = None

    def _reset_minimap_replay_state(self):
        self._minimap_actor_state = {}
        self._minimap_recent_positions = {}
        self._minimap_event_cursor = 0
        self._minimap_state_time = -1.0
        self._minimap_active_map_name = ""

    def show_minimap_window(self):
        if not hasattr(self, "minimap_window"):
            return
        # 由目前 playhead 決定應該載入哪張 GAT，不直接使用 Replay 最後一張地圖。
        self._sync_damage_playback_source(
            getattr(self, "current_filtered_raw", getattr(self, "current_filtered_data", [])),
            keep_current=True,
        )
        self._sync_minimap_compute_sources()
        self.refresh_minimap_for_time(force=True)
        self.minimap_window.show()
        self.minimap_window.raise_()
        self.minimap_window.activateWindow()

        # 打開小地圖就 zoom 到最近：最大倍率 20x，並把自身鎖在中央。
        # 若自身座標尚未到達，set_frame() 取得自身後仍會依 follow_self 自動置中。
        def _focus_nearest():
            widget = self.minimap_widget
            if widget.gat and widget._self_unit():
                widget.follow_self = True
                widget.zoom_factor = 20.0
                unit = widget._self_unit()
                widget._center_on_map_point(unit.get("x", 0.0), unit.get("y", 0.0))
                widget._needs_initial_self_focus = False
                widget.update()
            else:
                widget.follow_self = True
                widget._needs_initial_self_focus = True

        QTimer.singleShot(0, _focus_nearest)

    @staticmethod
    def _normalize_minimap_map_stem(map_name):
        """
        Replay 地圖名用於 GAT 對應。
        使用者規則：名稱只要含 @，就忽略最前 3 個字元，從第 4 個字元開始。
        """
        normalized = (map_name or "").strip().replace("\\", "/")
        base_name = os.path.basename(normalized)
        stem = os.path.splitext(base_name)[0]
        if "@" in stem and len(stem) > 3:
            stem = stem[3:]
        return stem

    def _python_map_directory(self):
        """取得目前 Python 程式檔所在目錄下的 MAP 資料夾；兼容大小寫。"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        direct = os.path.join(base_dir, "MAP")
        if os.path.isdir(direct):
            return direct
        try:
            for name in os.listdir(base_dir):
                candidate = os.path.join(base_dir, name)
                if name.lower() == "map" and os.path.isdir(candidate):
                    return candidate
        except OSError:
            pass
        return direct

    def choose_gat_file(self):
        start_dir = os.path.dirname(self.gat_path) if self.gat_path else self._python_map_directory()
        if not os.path.isdir(start_dir):
            start_dir = os.path.dirname(os.path.abspath(__file__))
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 GAT 地圖", start_dir, "Ragnarok GAT (*.gat);;所有檔案 (*.*)"
        )
        if path:
            self.load_gat_file(path)

    def load_gat_file(self, path, quiet=False, map_name=None):
        try:
            gat = load_gat_navigation(path)
        except Exception as e:
            if not quiet:
                QMessageBox.warning(self, "GAT 載入失敗", str(e))
            return False

        self.gat_data = gat
        self.gat_path = gat["path"]
        if hasattr(self, "minimap_widget"):
            self.minimap_widget.set_gat(gat)
        map_name = (map_name or self._minimap_active_map_name or self.current_map_name or "").strip()
        self._minimap_loaded_map_name = map_name
        if hasattr(self, "minimap_map_label"):
            map_text = self._normalize_minimap_map_stem(map_name) or os.path.splitext(os.path.basename(path))[0]
            self.minimap_map_label.setText(f"地圖：{map_text}")
            self.minimap_map_label.setToolTip(
                f"地圖：{map_text}\n尺寸：{gat['width']} x {gat['height']}\nGAT：{gat['version']}\n"
                f"檔案：{os.path.basename(path)}"
            )
        return True

    def _try_auto_load_gat_for_current_map(self):
        return self._try_auto_load_gat_for_map(self.current_map_name)

    def _try_auto_load_gat_for_map(self, map_name):
        map_name = (map_name or "").strip()
        if not map_name:
            return False

        stem = self._normalize_minimap_map_stem(map_name)
        if not stem:
            return False
        lookup_key = (map_name, stem, os.path.dirname(os.path.abspath(__file__)))
        if self._gat_autoload_attempted_map == lookup_key and self.gat_data is not None:
            return True
        self._gat_autoload_attempted_map = lookup_key

        gat_name = stem + ".gat"
        map_dir = self._python_map_directory()

        # v2.4：只以「Python 程式檔所在目錄 / MAP」為自動 GAT 來源。
        # Windows 本來不分大小寫；這裡額外做 case-insensitive 掃描，方便其他環境測試。
        candidate = os.path.abspath(os.path.join(map_dir, gat_name))
        if os.path.isfile(candidate) and self.load_gat_file(candidate, quiet=True, map_name=map_name):
            return True

        if os.path.isdir(map_dir):
            wanted = gat_name.lower()
            try:
                for name in os.listdir(map_dir):
                    if name.lower() == wanted:
                        candidate = os.path.abspath(os.path.join(map_dir, name))
                        if os.path.isfile(candidate) and self.load_gat_file(candidate, quiet=True, map_name=map_name):
                            return True
            except OSError:
                pass

        if hasattr(self, "minimap_map_label"):
            self.minimap_map_label.setText(f"地圖：{stem}")
            self.minimap_map_label.setToolTip(f"尚未找到 MAP\\{gat_name}")
        return False

    def _switch_minimap_gat_for_map(self, map_name):
        """依播放時間切換 GAT；切回舊時間也會載回對應地圖。"""
        map_name = (map_name or "").strip()
        if not map_name:
            return False

        if self._minimap_loaded_map_name == map_name and self.gat_data is not None:
            return True

        # 先清舊圖，避免找不到新 GAT 時仍誤顯示前一張。
        self.gat_data = None
        self.gat_path = ""
        self._minimap_loaded_map_name = ""
        self._gat_autoload_attempted_map = None
        if hasattr(self, "minimap_widget"):
            self.minimap_widget.clear_map()

        return self._try_auto_load_gat_for_map(map_name)

    def _apply_minimap_event(self, event):
        kind = event.get("kind")

        if kind == "map_change":
            # 切圖代表上一張地圖上的視野單位全部失效。
            self._minimap_actor_state = {}
            self._minimap_recent_positions = {}
            self._minimap_active_map_name = (event.get("map_name") or "").strip()
            return

        # 0x0087 / ZC_ACCEPT_ENTER 不帶自己的 AID；由 Replay Session Aid 補上。
        if event.get("self_event"):
            aid = int(self.self_sid or 0)
        else:
            aid = int(event.get("aid", 0) or 0)
        if not aid:
            return

        if kind == "vanish":
            # ZC_NOTIFY_VANISH 欄位本身是 GID；傷害分析常用 AID/DID。
            # 移除前保留最後位置 1 個 replay segment，讓致死傷害仍能畫到目標位置。
            remove_aid = aid if aid in self._minimap_actor_state else next((
                state_aid for state_aid, state in self._minimap_actor_state.items()
                if int(state.get("gid", 0) or 0) == aid
            ), None)
            if remove_aid is not None:
                state = self._minimap_actor_state.get(remove_aid) or {}
                x = float(state.get("x", 0.0) or 0.0)
                y = float(state.get("y", 0.0) or 0.0)
                move = state.get("move")
                if move:
                    mt = float(event.get("time", 0.0) or 0.0)
                    start = float(move.get("start", 0.0) or 0.0)
                    duration = max(0.001, float(move.get("duration", 0.001) or 0.001))
                    ratio = min(1.0, max(0.0, (mt - start) / duration))
                    x = move["from_x"] + (move["to_x"] - move["from_x"]) * ratio
                    y = move["from_y"] + (move["to_y"] - move["from_y"]) * ratio
                self._minimap_recent_positions[remove_aid] = {
                    "x": x, "y": y, "time": float(event.get("time", 0.0) or 0.0),
                    "name": state.get("name", ""), "category": minimap_category_from_client_object_type(state.get("object_type", 0)),
                }
                self._minimap_actor_state.pop(remove_aid, None)
            return

        state = self._minimap_actor_state.get(aid, {"aid": aid})
        state["gid"] = event.get("gid", state.get("gid", 0))
        state["object_type"] = event.get("object_type", state.get("object_type", 0))
        state["job"] = event.get("job", state.get("job", 0))
        details_for_guild = event.get("details") if isinstance(event.get("details"), dict) else {}
        event_guild_id = int(event.get("guild_id", details_for_guild.get("guild_id", state.get("guild_id", 0))) or 0)
        if event.get("self_event") and not event_guild_id:
            event_guild_id = int(getattr(self, "self_guild_id", 0) or 0)
        if event_guild_id:
            state["guild_id"] = event_guild_id
        resolved_guild_name = (
            event.get("guild_name")
            or getattr(self, "guild_aid_name_map", {}).get(aid, "")
            or (getattr(self, "self_guild_name", "") if self.self_sid and aid == int(self.self_sid) else "")
            or getattr(self, "guild_id_name_map", {}).get(int(state.get("guild_id", 0) or 0), "")
            or state.get("guild_name", "")
        )
        if resolved_guild_name:
            state["guild_name"] = resolved_guild_name
        if event.get("speed"):
            state["speed"] = abs(float(event.get("speed") or 0))
        raw_name = event.get("name")
        if raw_name:
            state["name"] = raw_name
        details = event.get("details")
        if isinstance(details, dict):
            merged_details = dict(state.get("details") or {})
            merged_details.update(details)
            state["details"] = merged_details
        state["last_event_kind"] = kind
        state["last_event_timestamp"] = event.get("timestamp", state.get("last_event_timestamp", ""))
        state["last_packet_opcode"] = int(event.get("opcode", state.get("last_packet_opcode", 0)) or 0)

        if kind in ("spawn", "stand", "self_pos", "stop"):
            state["x"] = float(event.get("x", state.get("x", 0)) or 0)
            state["y"] = float(event.get("y", state.get("y", 0)) or 0)
            state["move"] = None
        elif kind == "move":
            event_time = float(event.get("time", 0.0) or 0.0)
            packet_fx = float(event.get("from_x", state.get("x", 0)) or 0)
            packet_fy = float(event.get("from_y", state.get("y", 0)) or 0)
            tx = float(event.get("to_x", packet_fx) or packet_fx)
            ty = float(event.get("to_y", packet_fy) or packet_fy)

            # v2.13：新 move 包到達時，先算上一段在「這一刻」應該走到哪。
            # 若和新包的 from 只差幾格，沿用連續位置作視覺起點；這可以消掉
            # 因 client/server speed 誤差造成的 1~3 格往回拉扯。真正的大幅校正/瞬移仍尊重封包。
            fx, fy = packet_fx, packet_fy
            previous_move = state.get("move")
            if previous_move:
                prev_start = float(previous_move.get("start", 0.0) or 0.0)
                prev_duration = max(0.001, float(previous_move.get("duration", 0.001) or 0.001))
                prev_ratio = min(1.0, max(0.0, (event_time - prev_start) / prev_duration))
                predicted_x = float(previous_move.get("from_x", 0.0)) + (float(previous_move.get("to_x", 0.0)) - float(previous_move.get("from_x", 0.0))) * prev_ratio
                predicted_y = float(previous_move.get("from_y", 0.0)) + (float(previous_move.get("to_y", 0.0)) - float(previous_move.get("from_y", 0.0))) * prev_ratio
                if math.hypot(predicted_x - packet_fx, predicted_y - packet_fy) <= 4.0:
                    fx, fy = predicted_x, predicted_y

            # 09FD 的 speed 是每一格的基準走路時間；斜走在 server 端成本較高。
            # 舊版用 Chebyshev max(dx,dy) 會把所有斜步當成一般一步，導致越走越超前，
            # 下一個封包一來就往回跳。改成直走 + 約 sqrt(2) 的斜走時間。
            speed_ms = max(1.0, float(event.get("speed", 0) or state.get("speed", 0) or 150.0))
            dx_cells = abs(tx - fx)
            dy_cells = abs(ty - fy)
            diagonal_cells = min(dx_cells, dy_cells)
            straight_cells = max(dx_cells, dy_cells) - diagonal_cells
            weighted_cells = straight_cells + diagonal_cells * math.sqrt(2.0)
            duration = max(0.05, weighted_cells * speed_ms / 1000.0) if weighted_cells > 0 else 0.05

            # 如果同一 actor 的下一個位置包在預估走完之前就出現，代表途中改向/校正。
            # 直接讓本段在下一包時間點抵達「下一包的起點」，可保證段與段連續，
            # 不會先走過頭再瞬間倒退。若下一包很晚才到，仍照 speed 正常抵達後等待。
            next_time = event.get("_next_pos_time")
            next_x = event.get("_next_pos_x")
            next_y = event.get("_next_pos_y")
            if next_time is not None:
                dt = float(next_time) - event_time
                if dt > 0.02 and next_x is not None and next_y is not None:
                    next_x = float(next_x)
                    next_y = float(next_y)
                    target_gap = math.hypot(next_x - tx, next_y - ty)
                    interrupted = dt < duration - 0.02
                    near_expected_timing = dt <= duration * 1.25
                    if interrupted or (target_gap > 0.75 and near_expected_timing):
                        tx, ty = next_x, next_y
                        duration = max(0.05, dt)

            state["x"] = fx
            state["y"] = fy
            state["move"] = {
                "start": event_time,
                "duration": duration,
                "from_x": fx, "from_y": fy, "to_x": tx, "to_y": ty,
                "packet_from_x": packet_fx, "packet_from_y": packet_fy,
                "speed_ms": speed_ms,
            }

        self._minimap_actor_state[aid] = state

    def _advance_minimap_state_to(self, sec):
        sec = max(0.0, float(sec or 0.0))
        events = getattr(self, "actor_map_events", [])

        # 往回 seek 必須重播位置事件；往前則只吃新增事件。
        if sec + 1e-9 < self._minimap_state_time:
            self._reset_minimap_replay_state()

        cursor = self._minimap_event_cursor
        while cursor < len(events) and float(events[cursor].get("time", 0.0)) <= sec + 1e-9:
            self._apply_minimap_event(events[cursor])
            cursor += 1
        self._minimap_event_cursor = cursor
        self._minimap_state_time = sec

    def _seed_minimap_self_from_next_event(self, sec):
        """
        剛進圖若沒有留下可用的 ACCEPT_ENTER，自身在第一次移動前仍應可見。
        往目前 map segment 後面找第一個自身位置事件：
        - 0x0087 move：使用 from_x/from_y 當作進圖初始位置
        - self_pos/stand/stop：使用該事件座標
        只回填顯示位置，不提前套用移動本身。
        """
        self_aid = int(self.self_sid or 0)
        if not self_aid or self_aid in self._minimap_actor_state:
            return

        events = getattr(self, "actor_map_events", [])
        cursor = int(self._minimap_event_cursor or 0)
        seed_event = None
        seed_x = seed_y = None

        for idx in range(cursor, len(events)):
            event = events[idx]
            if event.get("kind") == "map_change":
                # 下一次切圖之後的座標不屬於目前地圖。
                break

            is_self_event = bool(event.get("self_event"))
            event_aid = int(event.get("aid", 0) or 0)
            if not is_self_event and event_aid != self_aid:
                continue

            kind = event.get("kind")
            if kind == "move":
                seed_x = event.get("from_x")
                seed_y = event.get("from_y")
            elif kind in ("self_pos", "stand", "stop", "spawn"):
                seed_x = event.get("x")
                seed_y = event.get("y")
            else:
                continue

            if seed_x is not None and seed_y is not None:
                seed_event = event
                break

        if seed_event is None:
            return

        state = {
            "aid": self_aid,
            "gid": int(seed_event.get("gid", 0) or 0),
            "object_type": 0x00,
            "job": int(seed_event.get("job", 0) or 0),
            "guild_id": int(seed_event.get("guild_id", (seed_event.get("details") or {}).get("guild_id", getattr(self, "self_guild_id", 0))) or getattr(self, "self_guild_id", 0) or 0),
            "guild_name": (seed_event.get("guild_name") or getattr(self, "self_guild_name", "") or getattr(self, "guild_aid_name_map", {}).get(self_aid, "") or getattr(self, "guild_id_name_map", {}).get(int(seed_event.get("guild_id", (seed_event.get("details") or {}).get("guild_id", getattr(self, "self_guild_id", 0))) or getattr(self, "self_guild_id", 0) or 0), "")),
            "name": self.lookup_actor_name(self_aid) or "",
            "x": float(seed_x or 0.0),
            "y": float(seed_y or 0.0),
            "move": None,
            "details": dict(seed_event.get("details") or {}),
            "last_event_kind": seed_event.get("kind", ""),
            "last_event_timestamp": seed_event.get("timestamp", ""),
            "last_packet_opcode": int(seed_event.get("opcode", 0) or 0),
        }
        self._minimap_actor_state[self_aid] = state

    def _minimap_units_at(self, sec):
        self._advance_minimap_state_to(sec)
        # v2.8：若進圖封包沒有自身座標，用之後第一個自身移動的起點回填。
        self._seed_minimap_self_from_next_event(sec)
        units = []

        for aid, state in self._minimap_actor_state.items():
            x = float(state.get("x", 0.0) or 0.0)
            y = float(state.get("y", 0.0) or 0.0)
            move = state.get("move")
            if move:
                start = float(move.get("start", 0.0))
                duration = max(0.001, float(move.get("duration", 0.001)))
                ratio = min(1.0, max(0.0, (float(sec) - start) / duration))
                x = move["from_x"] + (move["to_x"] - move["from_x"]) * ratio
                y = move["from_y"] + (move["to_y"] - move["from_y"]) * ratio

            object_type = int(state.get("object_type", 0) or 0) & 0xFF
            # 這裡不能用 BL_* bitmask。09FD/09FE/09FF 的 objecttype 是
            # clif_bl_type() 產生的 client actor type：0=玩家、5=魔物、
            # 6=NPC、7=寵物、8=生命體、9=傭兵、10=元素等。
            category = minimap_category_from_client_object_type(object_type)

            # 小地圖名稱先使用 entry packet，缺少時再回查既有 AID/DID 名稱表。
            name = state.get("name") or self.lookup_actor_name(aid) or f"AID {aid}"
            units.append({
                "aid": aid, "gid": state.get("gid", 0), "name": name,
                "object_type": object_type,
                "object_type_name": CLIENT_ACTOR_TYPE_NAMES.get(object_type, f"TYPE_0x{object_type:02X}"),
                "category": category,
                "job": state.get("job", 0),
                "guild_id": int(state.get("guild_id", 0) or 0),
                "guild_name": state.get("guild_name") or getattr(self, "guild_aid_name_map", {}).get(int(aid), "") or (getattr(self, "self_guild_name", "") if self.self_sid and int(aid) == int(self.self_sid) else "") or getattr(self, "guild_id_name_map", {}).get(int(state.get("guild_id", 0) or 0), ""),
                "speed": state.get("speed", 0), "x": x, "y": y,
                "is_self": bool(self.self_sid and aid == self.self_sid),
                "last_event_kind": state.get("last_event_kind", ""),
                "last_event_timestamp": state.get("last_event_timestamp", ""),
                "last_packet_opcode": state.get("last_packet_opcode", 0),
                "details": dict(state.get("details") or {}),
            })
            self._minimap_recent_positions[aid] = {
                "x": x, "y": y, "time": float(sec), "name": name, "category": category,
            }
        return units

    def _ensure_minimap_damage_index(self):
        """建立全傷害事件的時間索引；資料未改變時 60FPS frame 不重掃整份 parsed_data。"""
        source = getattr(self, "parsed_data", [])
        last_ts = source[-1].get("timestamp") if source else None
        signature = (id(source), len(source), last_ts)
        if signature == self._minimap_damage_index_signature:
            return

        indexed = []
        include_zero_damage = bool(getattr(self, "show_zero_damage_checkbox", None)
                                   and self.show_zero_damage_checkbox.isChecked())
        for row in source:
            damage = int(row.get("damage", 0) or 0)
            if damage < 0 or (damage == 0 and not include_zero_damage):
                continue
            t = self.timestamp_to_float_seconds(row.get("timestamp"))
            if t is None:
                continue
            indexed.append((float(t), row))
        indexed.sort(key=lambda item: item[0])
        self._minimap_damage_times = [item[0] for item in indexed]
        self._minimap_damage_rows = [item[1] for item in indexed]
        self._minimap_damage_index_signature = signature

    def _minimap_damage_links_at(self, sec, units):
        """建立 playhead 最近 1 秒內的 SID→DID 攻擊關係線。

        使用 trailing window [sec-1, sec]，所以播放時不會預先看到該秒尚未發生的攻擊。
        同一 SID→DID 在視窗內合併成一條線並累計傷害/次數。
        """
        sec = max(0.0, float(sec or 0.0))
        window_sec = 1.0
        start_sec = max(0.0, sec - window_sec)

        # 目前畫面上的位置優先；剛死亡/剛離場的目標使用最後已知位置，
        # 讓致死傷害線不會在 VANISH 後立刻消失。
        positions = {
            int(u.get("aid", 0) or 0): (float(u.get("x", 0.0)), float(u.get("y", 0.0)))
            for u in units if int(u.get("aid", 0) or 0)
        }
        for aid, pos in getattr(self, "_minimap_recent_positions", {}).items():
            if aid not in positions and sec - float(pos.get("time", -9999.0) or -9999.0) <= 1.25:
                positions[int(aid)] = (float(pos.get("x", 0.0)), float(pos.get("y", 0.0)))

        grouped = {}
        # v2.12：以 parsed_data 的時間索引 bisect 最近 1 秒，不再 60FPS 全表掃描。
        self._ensure_minimap_damage_index()
        times = self._minimap_damage_times
        rows = self._minimap_damage_rows
        lo = bisect.bisect_left(times, start_sec - 1e-9)
        hi = bisect.bisect_right(times, sec + 1e-9)
        selected_did = self.did_filter.currentData() if hasattr(self, "did_filter") else None
        selected_sid = self.sid_filter.currentData() if hasattr(self, "sid_filter") else None

        for idx in range(lo, hi):
            row = rows[idx]
            t = times[idx]
            damage = int(row.get("damage", 0) or 0)
            if damage < 0:
                continue
            sid = int(row.get("sid", 0) or 0)
            did = int(row.get("did", 0) or 0)
            if selected_did is not None and did != int(selected_did):
                continue
            if selected_sid is not None and sid != int(selected_sid):
                continue
            if self.damage_time_range is not None:
                rs, re_ = self.damage_time_range
                if t < rs - 1e-9 or t > re_ + 1e-9:
                    continue
            if not sid or not did or sid == did:
                continue
            if sid not in positions or did not in positions:
                continue
            key = (sid, did)
            item = grouped.setdefault(key, {
                "sid": sid, "did": did, "damage": 0, "count": 0, "latest_time": t,
                "skills": set(),
            })
            item["damage"] += damage
            item["count"] += 1
            item["latest_time"] = max(float(item["latest_time"]), float(t))
            skill = row.get("skill_name")
            if skill:
                item["skills"].add(str(skill))

        links = []
        for item in grouped.values():
            sx, sy = positions[item["sid"]]
            tx, ty = positions[item["did"]]
            links.append({
                **item,
                "source_x": sx, "source_y": sy,
                "target_x": tx, "target_y": ty,
                "age": max(0.0, sec - float(item["latest_time"])),
                "source_name": self.lookup_actor_name(item["sid"]) or f"AID {item['sid']}",
                "target_name": self.lookup_actor_name(item["did"]) or f"AID {item['did']}",
                "skills": sorted(item["skills"]),
            })
        links.sort(key=lambda x: (x.get("age", 0.0), -x.get("damage", 0)))
        return links

    def refresh_minimap_for_time(self, force=False, sec_override=None):
        if not hasattr(self, "minimap_widget"):
            return
        # 小地圖視窗沒開時不做 frame request；打開視窗會立刻補到 playhead。
        if not force:
            window = getattr(self, "minimap_window", None)
            if window is None or not window.isVisible():
                return

        if sec_override is not None:
            sec = max(0.0, float(sec_override))
        elif self.damage_playback_mode:
            sec = max(0.0, float(self.damage_playback_current_sec))
        else:
            sec = self._get_replay_end_sec()

        # v2.14：正常路徑只送 playhead 給獨立 process。GUI 不再重建 actor state / 掃傷害。
        if self._request_minimap_async_frame(sec):
            self._poll_minimap_async_result()
            return

        # process 不可用時保留舊同步 fallback。
        units = self._minimap_units_at(sec)

        # 全域時間軸決定地圖。若 replay 沒有 map_change event，才退回最新 metadata。
        active_map = (self._minimap_active_map_name or self.current_map_name or "").strip()
        if active_map:
            self._switch_minimap_gat_for_map(active_map)

        damage_links = self._minimap_damage_links_at(sec, units)
        selected_did = self.did_filter.currentData() if hasattr(self, "did_filter") else None
        self.minimap_widget.set_frame(units, damage_links, sec, highlight_aid=selected_did)

        self_count = sum(1 for u in units if u.get("is_self"))
        players = sum(1 for u in units if u["category"] == "player" and not u.get("is_self"))
        mobs = sum(1 for u in units if u["category"] == "mob")
        pets = sum(1 for u in units if u["category"] == "pet")
        npcs = sum(1 for u in units if u["category"] == "npc")
        companions = sum(1 for u in units if u["category"] == "companion")
        others = sum(1 for u in units if u["category"] == "other")
        damage_event_count = sum(int(link.get("count", 0) or 0) for link in damage_links)
        self.minimap_count_label.setText(f"時間 {self._format_playback_time(sec)}")
        self.minimap_count_label.setToolTip(
            f"自身 {self_count}｜玩家 {players}｜魔物 {mobs}｜寵物 {pets}｜"
            f"NPC {npcs}｜召喚 {companions}｜其他 {others}\n"
            f"傷害線 {len(damage_links)}組 / {damage_event_count}筆"
        )

    def on_minimap_render_tick(self):
        """v2.19：60FPS UI poll/request；正常播放按 FIFO 套用每一個 snapshot，不跳幀。"""
        window = getattr(self, "minimap_window", None)
        if window is None or not window.isVisible():
            return

        # 先收 worker 已完成的 frame；沒有新 frame 時沿用上一幀，不阻塞 UI。
        self._poll_minimap_async_result()

        if not self.damage_playback_running:
            return
        # 使用 wall clock 推算欲播放時間；request 會 FIFO 排隊。
        # 若計算跟不上，視覺回放會延後，而不是直接跳掉中間 frame。
        sec = self.damage_playback_base_sec + (
            time.perf_counter() - self.damage_playback_wall_t0
        ) * self.damage_playback_speed
        sec = min(max(sec, self.damage_playback_range_start), self.damage_playback_range_end)
        self._request_minimap_async_frame(sec)

    def on_minimap_unit_selected(self, unit):
        if not unit:
            return
        if unit.get("is_self"):
            category_name = "自身"
        else:
            category_name = {
                "player": "玩家", "mob": "魔物", "pet": "寵物", "npc": "NPC",
                "companion": "召喚/傭兵", "other": "其他"
            }.get(unit.get("category"), "其他")
        guild_id = int(unit.get("guild_id", 0) or 0)
        guild_name = (unit.get("guild_name") or self.guild_aid_name_map.get(int(unit.get("aid", 0) or 0), "") or (self.self_guild_name if unit.get("is_self") else "") or (self.guild_id_name_map.get(guild_id, "") if guild_id else ""))
        guild_text = f"{guild_name} [{guild_id}]" if guild_name else (f"GuildID {guild_id}" if guild_id else "無公會")
        # v2.24：選取資訊不再常駐占用上方空間；單位詳細資料由 hover Tooltip 顯示。
        self.minimap_selected_label.setText("")
        if hasattr(self, "minimap_widget"):
            self.minimap_widget.setToolTip(self.minimap_widget._unit_hover_tooltip(unit))

    def on_minimap_unit_context_requested(self, unit):
        """右鍵單位：顯示目前快照 + 最近一包 actor 封包的完整解析欄位。"""
        if not unit:
            return

        def flatten(prefix, value, rows):
            if isinstance(value, dict):
                for k, v in value.items():
                    child = f"{prefix}.{k}" if prefix else str(k)
                    flatten(child, v, rows)
            elif isinstance(value, (list, tuple, set)):
                rows.append((prefix, ", ".join(str(x) for x in value)))
            else:
                rows.append((prefix, str(value)))

        if unit.get("is_self"):
            category_name = "自身"
        else:
            category_name = {
                "player": "玩家", "mob": "魔物", "pet": "寵物", "npc": "NPC",
                "companion": "召喚/傭兵", "other": "其他"
            }.get(unit.get("category"), "其他")

        rows = [
            ("目前.類型", category_name),
            ("目前.名稱", str(unit.get("name", ""))),
            ("目前.AID", str(unit.get("aid", 0))),
            ("目前.GID", str(unit.get("gid", 0))),
            ("目前.GuildID", str(unit.get("guild_id", 0))),
            ("目前.公會名稱", str(unit.get("guild_name") or self.guild_id_name_map.get(int(unit.get("guild_id", 0) or 0), ""))),
            ("目前.ObjectType", f"0x{int(unit.get('object_type', 0) or 0):02X} ({unit.get('object_type_name', '')})"),
            ("目前.Job", str(unit.get("job", 0))),
            ("目前.Speed", str(unit.get("speed", 0))),
            ("目前.X", f"{float(unit.get('x', 0.0) or 0.0):.3f}"),
            ("目前.Y", f"{float(unit.get('y', 0.0) or 0.0):.3f}"),
            # ("最近事件", str(unit.get("last_event_kind", ""))),
            # ("最近事件時間", str(unit.get("last_event_timestamp", ""))),
            # ("最近Opcode", f"0x{int(unit.get('last_packet_opcode', 0) or 0):04X}"),
        ]
        # details = unit.get("details") or {}
        # if details:
        #     flatten("封包", details, rows)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"單位完整資料 - {unit.get('name') or unit.get('aid', '')}")
        dialog.resize(400, 500)
        vbox = QVBoxLayout(dialog)
        table = QTableWidget(len(rows), 2, dialog)
        table.setHorizontalHeaderLabels(["欄位", "值"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setVisible(False)
        for r, (key, value) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(str(key)))
            table.setItem(r, 1, QTableWidgetItem(str(value)))
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        vbox.addWidget(table)
        close_btn = QPushButton("關閉")
        close_btn.clicked.connect(dialog.accept)
        vbox.addWidget(close_btn)
        dialog.exec()

    def apply_did_filter(self, *_args, playback_tick=False):
        """同時套用攻方 SID 與受方 DID 篩選。"""
        selected_did_text = self.did_filter.currentText()

        did_value = self.did_filter.currentData()
        sid_value = self.sid_filter.currentData()

        # 「全部(包含能力變動)」只控制傷害歷程是否納入能力變動事件。
        include_stat = selected_did_text == FILTER_ALL_WITH_STAT

        raw_base = getattr(self, "raw_data", self.parsed_data)
        drop_base = getattr(self, "drop_data", [])
        raw_source = raw_base if include_stat else [
            d for d in raw_base
            if d.get("skill_name") not in STAT_SKILL_NAMES
        ]

        # v2.16：只隱藏真正攻擊事件中的 damage==0，不影響狀態/能力變動等本來就是 damage=0 的事件。
        if not self.show_zero_damage_checkbox.isChecked():
            raw_source = [d for d in raw_source if not d.get("zero_damage_event", False)]

        # 「傷害歷程顯示狀態」是狀態總開關，預設開啟：
        #   1) 一般狀態開始 / 結束，再由「狀態開始 / 結束」子選項控制。
        #   2) VANISH 四種 mode，再由各自勾選框細分。
        # 只影響畫面顯示；死亡/掉落配對與統計仍使用未過濾的 raw_base。
        if not self.show_status_history_checkbox.isChecked():
            raw_source = [
                d for d in raw_source
                if d.get("status_event") not in ("start", "end", "vanish")
            ]
        else:
            if not self.show_state_change_checkbox.isChecked():
                raw_source = [
                    d for d in raw_source
                    if d.get("status_event") not in ("start", "end")
                ]

            raw_source = [
                d for d in raw_source
                if d.get("status_event") != "vanish"
                or self.is_vanish_mode_visible(d.get("vanish_mode"))
            ]

        filtered_damage = self.parsed_data
        if not self.show_zero_damage_checkbox.isChecked():
            filtered_damage = [d for d in filtered_damage if not d.get("zero_damage_event", False)]
        filtered_raw = raw_source

        # 掉落頁沒有攻方 SID，因此只跟隨受方 DID 篩選。
        drop_raw_source = raw_base

        # 受方 DID 條件
        if did_value is not None:
            filtered_damage = [d for d in filtered_damage if d.get("did") == did_value]
            filtered_raw = [d for d in filtered_raw if d.get("did") == did_value]
            self.current_drop_filtered_raw = [
                d for d in drop_raw_source
                if d.get("did") == did_value
            ]
            self.current_drop_data = [
                d for d in drop_base
                if d.get("source_did") == did_value
            ]
        else:
            self.current_drop_filtered_raw = list(drop_raw_source)
            self.current_drop_data = drop_base.copy()

        # 攻方 SID 條件只篩選「實際傷害事件」。
        # 已通過上方顯示開關的狀態事件、能力變動、死亡等 damage=0 歷程事件，
        # 不因為沒有攻方 SID 而被排除。
        if sid_value is not None:
            filtered_damage = [
                d for d in filtered_damage
                if d.get("sid") == sid_value
            ]
            filtered_raw = [
                d for d in filtered_raw
                if int(d.get("damage", 0) or 0) <= 0
                or d.get("sid") == sid_value
            ]

        # v1.4：最後疊加圖上圈選的 replay 時間區間。
        # 這裡從 parsed_data/raw_data 的基礎篩選結果重新計算，所以清除圈選即可完整恢復。
        if self.damage_time_range is not None:
            range_start, range_end = self.damage_time_range

            def in_selected_range(row):
                t = self.timestamp_to_float_seconds(row.get("timestamp"))
                return t is not None and range_start <= t <= range_end

            filtered_damage = [d for d in filtered_damage if in_selected_range(d)]
            filtered_raw = [d for d in filtered_raw if in_selected_range(d)]

        # v2.0：全域 playhead 是「時間上限」。
        # 例如滑到 60 秒，所有統計都使用 0～60 秒已發生的內容。
        if self.damage_playback_mode:
            cutoff = max(0.0, float(self.damage_playback_current_sec))

            def before_playhead(row):
                t = self.timestamp_to_float_seconds(row.get("timestamp"))
                return t is not None and t <= cutoff + 1e-9

            filtered_damage = [d for d in filtered_damage if before_playhead(d)]
            filtered_raw = [d for d in filtered_raw if before_playhead(d)]
            self.current_drop_filtered_raw = [
                d for d in self.current_drop_filtered_raw if before_playhead(d)
            ]
            self.current_drop_data = [
                d for d in self.current_drop_data if before_playhead(d)
            ]

        self.current_filtered_data = list(filtered_damage)
        self.current_filtered_raw = list(filtered_raw)
        self.update_damage_range_label()

        # 播放 tick 時傷害歷程採增量 append，避免每 0.1 秒重建整張表。
        # 手動拖曳/篩選改變時仍完整重建，確保 0～playhead 的內容正確。
        if not playback_tick:
            self.update_raw_table()
        self.update_drop_table()
        self.update_monster_drop_tree()
        self.update_group_tree()
        self.refresh_chart()
        self.update_hud_top5()
        # 播放中由獨立 60FPS timer 負責小地圖；seek/暫停/篩選變更仍立即刷新。
        if not (playback_tick and self.damage_playback_running):
            self.refresh_minimap_for_time()


    def get_active_filter_title(self):
        """圖表標題使用目前的攻方 / 受方篩選條件。"""
        did_text = self.did_filter.currentText() or FILTER_ALL
        sid_text = self.sid_filter.currentText() or FILTER_ALL

        did_is_all = did_text in (FILTER_ALL, FILTER_ALL_WITH_STAT)
        sid_is_all = sid_text == FILTER_ALL

        if not sid_is_all and not did_is_all:
            return f"攻方 {sid_text} → 受方 {did_text}"
        if not sid_is_all:
            return f"攻方 {sid_text}"
        if not did_is_all:
            return f"受方 {did_text}"
        return did_text



    def on_bar_clicked(self):
        self.current_chart_mode = "bar"
        # 橫條總傷害圖沒有時間軸，離開圈選互動；已選的時間範圍仍保留並套用統計。
        if hasattr(self, "btn_select_range") and self.btn_select_range.isChecked():
            self.btn_select_range.setChecked(False)
        self.refresh_chart()

    def on_line_clicked(self):
        self.current_chart_mode = "line"
        self.refresh_chart()

    def on_stairs_clicked(self):
        self.current_chart_mode = "stairs"
        self.refresh_chart()



    def refresh_chart(self):
        if not hasattr(self, "current_filtered_data"):
            return

        data = self.current_filtered_data
        if not data:
            old_status = self.chart_status_text
            self.chart_status_text = (
                "所選時間範圍沒有傷害" if self.damage_time_range is not None else "沒有符合條件的傷害"
            )
            self.draw_empty_chart()
            self.chart_status_text = old_status
            return

        from collections import defaultdict

        # ================ 共用繪圖區（self.fig + self.canvas） ==================
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        self.fig.patch.set_alpha(0)
        ax.set_facecolor("none")
        self.canvas.setStyleSheet("background-color: transparent;")
        # ========================================================================


        # 如果目前是長條圖模式
        if self.current_chart_mode == "bar":
            self.toolbar.hide() 
            # ==== 長條圖 ====
            from collections import defaultdict

            sid_total = defaultdict(int)
            for d in data:
                sid_total[d["sid"]] += d["damage"]

            # 排序
            sorted_sids = sorted(sid_total.items(), key=lambda x: x[1], reverse=True)

            # 套用你原本的長條圖函式
            self.draw_damage_chart(sorted_sids)
            return

        # ==========================
        # 如果是折線圖模式
        # ==========================
        if self.current_chart_mode == "line":
            self.toolbar.hide()
            if hasattr(self, "bar_scrollbar"):
                self.bar_scrollbar.hide()
            self.draw_line_chart()
            return

        # ==========================
        # 每秒傷害階梯圖：用真實時間邊界，不使用 Rectangle bar
        # ==========================
        if self.current_chart_mode == "stairs":
            self.toolbar.hide()
            if hasattr(self, "bar_scrollbar"):
                self.bar_scrollbar.hide()
            self.draw_stairs_chart()
            return



        # 依 SID 分秒傷
        sec_damage_by_sid = defaultdict(lambda: defaultdict(int))

        def parse_sec(ts):
            h, m, s, ms = map(int, ts[1:].split(":"))
            return h*3600 + m*60 + s

        for d in data:
            sid = d["sid"]
            dmg = d["damage"]
            sec = parse_sec(d["timestamp"])
            sec_damage_by_sid[sid][sec] += dmg

        # 依 SID 繪製多條線
        for sid, sec_map in sec_damage_by_sid.items():
            secs = sorted(sec_map.keys())
            vals = [sec_map[s] for s in secs]

            # 顯示 SID 名稱
            if sid in self.sid_name_map:
                label = self.sid_name_map[sid]
            elif sid in self.did_name_map:
                label = self.did_name_map[sid]
            else:
                label = f"{sid}"

            ax.plot(secs, vals, label=label)

        # 設定 UI
        ax.legend()
        ax.set_title("每秒傷害折線（依玩家分線）", fontproperties=font, color="#FFFFFF")
        ax.tick_params(colors="#AAAAAA")
        for spine in ax.spines.values():
            spine.set_visible(False)

        self.canvas.draw()

    def closeEvent(self, event):
        """關閉主程式時停止小地圖獨立 process，避免背景程序殘留。"""
        try:
            self._stop_minimap_compute_process()
        except Exception:
            pass
        try:
            if self.worker_thread and self.worker_thread.isRunning():
                if self.worker:
                    self.worker.stop()
                self.worker_thread.quit()
                self.worker_thread.wait(500)
        except Exception:
            pass
        super().closeEvent(event)

    def enterEvent(self, event):
        """滑鼠進入視窗 → 暫停自動更新（但不影響正在解析）"""
        if not self.is_processing and self.auto_timer.isActive():
            self.auto_timer.stop()
            self.mouse_paused = True
        self.update_load_button_text()
        super().enterEvent(event)


    def leaveEvent(self, event):
        """滑鼠離開視窗 → 若秒數 > 0 則恢復自動更新"""
        interval = self.refresh_input.value()
        if interval > 0 and not self.is_processing:
            self.mouse_paused = False
            self.auto_timer.start(interval * 1000)
        self.update_load_button_text()
        super().leaveEvent(event)

                                       




# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    # v2.14：Windows spawn / frozen executable 需要 freeze_support。
    # 注意：若本模組是由 ItemSearchApp.py import，真正打包入口 ItemSearchApp.py
    # 也必須在其 __main__ 最前面呼叫 mp.freeze_support()。
    mp.freeze_support()
    app = QApplication(sys.argv)
    ui = MainUI()
    ui.show()
    sys.exit(app.exec())
