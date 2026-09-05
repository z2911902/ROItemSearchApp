import sys
import re
from collections import defaultdict
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QTabWidget,
    QTableWidget, QTableWidgetItem, QFileDialog, QLabel,
    QTreeWidget, QTreeWidgetItem, QHBoxLayout , QCheckBox , QProgressBar
)
from PySide6.QtCore import QObject, QThread, Signal
import time
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
from PySide6.QtGui import QColor
from PySide6.QtGui import QGuiApplication, QClipboard
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from PySide6.QtWidgets import QMessageBox
import threading
from PySide6.QtWidgets import QHeaderView
from collections import defaultdict
from matplotlib.ticker import FuncFormatter
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

        # 綁定 canvas 事件
        canvas.mpl_connect("button_press_event", self.on_press)
        canvas.mpl_connect("motion_notify_event", self.on_move)
        canvas.mpl_connect("button_release_event", self.on_release)

    def on_press(self, event):
        if event.button == 1 and event.inaxes:
            self.is_panning = True
            # Matplotlib 3.8 新名稱：press_pan
            self.toolbar.press_pan(event)

    def on_move(self, event):
        if self.is_panning:
            # Matplotlib 3.8 新名稱：drag_pan
            self.toolbar.drag_pan(event)

    def on_release(self, event):
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

def parse_replaydata_mapname(text):
    pattern = re.compile(
        r'\[Chunk ReplayData\]\s+Unparsed opcode Mapname,[\s\S]*?'
        r'Raw hex:\s*\[0x[0-9A-Fa-f]+\s*\(\d+\)\]\s*\{\s*\n'
        r'([\s\S]*?)^}',
        re.MULTILINE
    )

    m = pattern.search(text)
    if not m:
        return None

    block = m.group(1)
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
    #print(hex_bytes)
    parsed = {}

    parsed["skill_id"] = 0              # 普通攻擊 → skill_id = 0
    parsed["skill_name"] = "普通攻擊"

    parsed["sid"] = le_int(hex_bytes[2:6])
    parsed["did"] = le_int(hex_bytes[6:9])

    parsed["damage"] = le_int(hex_bytes[22:26])

    parsed["level"] = 1                # 統一設成 1
    parsed["hit_count"] = 1            # 普通攻擊 = 1 hit
    parsed["skill_delay"] = 0
    parsed["global_delay"] = 0
    #print(f"sid:{le_int(hex_bytes[2:6])} did:{le_int(hex_bytes[6:9])}")
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
    return {
        "sid": le_int(hex_bytes[4:8])    # 5~8 位
    }

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
    parsed = {}

    # sid (5~8)
    parsed["sid"] = le_int(hex_bytes[4:8]) if len(hex_bytes) >= 8 else 0

    # type (3~4)
    parsed["type"] = le_int(hex_bytes[2:4]) if len(hex_bytes) >= 4 else 0

    # monsterskin（STATE_CHANGE 沒有 → 為 0）
    parsed["monsterskin"] = le_int(hex_bytes[17:19]) if len(hex_bytes) >= 19 else 0

    # 既有變身封包仍依 type / monsterskin 判斷
    if parsed["type"] == 665:
        if parsed["monsterskin"] > 0:
            parsed["transform_event"] = "start"
        else:
            parsed["transform_event"] = "end"
    else:
        parsed["transform_event"] = None

    parsed["skill_id"]      = 0
    parsed["skill_name"]    = "外觀變更"
    parsed["did"]           = 0
    parsed["damage"]        = 0
    parsed["level"]         = 0
    parsed["hit_count"]     = 0
    parsed["skill_delay"]   = 0
    parsed["global_delay"]  = 0

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
    """解碼一般狀態開始/結束封包。事件方向只依封包名稱判定。"""
    status_id = le_int(hex_bytes[2:4]) if len(hex_bytes) >= 4 else 0
    did = le_int(hex_bytes[4:8]) if len(hex_bytes) >= 7 else 0
    is_start = packet_kind == "START"


    return {
        "status_id": status_id,
        "did": did,
        "status_event": "start" if is_start else "end",
        "status_event_name": "狀態開始" if is_start else "狀態結束",
    }


def parse_vanish_blocks(text: str):
    lines = text.splitlines()
    results = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].strip()
        if "packet HEADER_ZC_NOTIFY_VANISH" not in line:
            i += 1
            continue

        packet_pos = i   # ★ 記住這筆封包在文字中的位置
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

        if len(hex_bytes) >= 7:
            did = int(hex_bytes[2], 16) | (int(hex_bytes[3], 16) << 8)
            mode = int(hex_bytes[6], 16)

            if mode == 1:
                results.append({
                    "timestamp": timestamp,
                    "did": did,
                    "mode": mode,
                    "packet_pos": packet_pos,   # ★ 新增
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
    return {
        "item_id": le_int(hex_bytes[6:9]),      # 94 03 00 -> 916
        "x": le_int(hex_bytes[13:15]),          # E1 00 -> 225
        "y": le_int(hex_bytes[15:17]),          # 5E 01 -> 350
        "amount": le_int(hex_bytes[19:21]),     # 01 00 -> 1
    }





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
    """
    0x0141 ZC_COUPLESTATUS:
      [0..1]   packet id (0141)
      [2..5]   status id   (L)
      [6..9]   base status (L)
      [10..13] plus status (L)
    """
    stat_id = le_int(hex_bytes[2:4]) if len(hex_bytes) >= 6 else 0
    base    = le_int(hex_bytes[6:7]) if len(hex_bytes) >= 10 else 0
    plus    = le_int(hex_bytes[10:12]) if len(hex_bytes) >= 14 else 0

    stat_name = COUPLESTATUS_STAT_MAP.get(stat_id)

    # 沒對應：看開關決定要不要隱藏
    if stat_name is None:
        if not show_unknown:
            return None
        stat_name = f"0x{stat_id:08X}"  # 顯示未知ID（可自行換格式）

    total = base + plus
    return {
        "stat_id": stat_id,
        "stat_name": stat_name,
        "base": base,
        "plus": plus,
        "total": total,
    }

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
    """
    0x00B0 ZC_PAR_CHANGE: <var id>.W <value>.L
    """
    if show_unknown is None:
        show_unknown = SHOW_UNKNOWN_PAR_CHANGE

    stat_id = le_int(hex_bytes[2:4]) if len(hex_bytes) >= 4 else 0
    value   = le_int(hex_bytes[4:8]) if len(hex_bytes) >= 8 else 0  # 4 bytes (L)

    stat_name = PAR_CHANGE_STAT_MAP.get(stat_id)

    # 沒對應：看開關要不要隱藏
    if stat_name is None:
        if not show_unknown:
            return None
        stat_name = f"0x{stat_id:04X}"

    return {"stat_id": stat_id, "stat_name": stat_name, "value": value}



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

    parsed = {}

    parsed["skill_id"] = le_int(hex_bytes[2:4])  # ★ 真正的技能 ID（不能改）
    sid = parsed["skill_id"]

    # ★ 顯示用途的 ID：只用于查中文名！！！其他不影響
    display_id = skill_display_map.get(sid, sid)

    # ★ 技能名稱（使用 display_id 查）
    parsed["skill_name"] = skill_name_map.get(display_id, f"ID {display_id}")

    parsed["sid"]          = le_int(hex_bytes[4:8])
    # DID 編碼：如果 hex_bytes[8] == '00' → 抓 2 bytes，否則抓 4 bytes
    if len(hex_bytes) >= 12:
        if hex_bytes[8] == '00':
            parsed["did"] = le_int(hex_bytes[8:10])   # 2 bytes
        else:
            parsed["did"] = le_int(hex_bytes[8:12])   # 4 bytes
    else:
        parsed["did"] = 0   # 保護，不會崩潰
    parsed["skill_delay"]  = int(hex_bytes[16], 16) if len(hex_bytes) > 16 else 0
    # global_delay
    gd_bytes = hex_bytes[20:22]

    if gd_bytes == ['FF', 'FF']:
        parsed["global_delay"] = -1
    else:
        parsed["global_delay"] = le_int(gd_bytes)
    parsed["damage"]       = le_int(hex_bytes[24:28])  # 25~28（4 bytes）
    parsed["level"]        = int(hex_bytes[28], 16) if len(hex_bytes) > 28 else 0
    parsed["hit_count"]    = int(hex_bytes[30], 16) if len(hex_bytes) > 30 else 0

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


def sanitize_actor_name(name):
    """拒絕污染字元及 RO 內部隱藏物件名，避免覆寫正常中文名稱。"""
    if name is None:
        return None
    name = str(name).replace("\x00", "").strip()
    # 解碼錯誤的 replacement character 代表 offset/編碼不可信。
    if not name or "\ufffd" in name:
        return None
    # 控制字元不應出現在顯示名稱。
    if any(ord(ch) < 0x20 for ch in name):
        return None
    # #mk_10 / #le_4 等是腳本/內部 actor 名，不拿來當怪物顯示名稱。
    if name.startswith("#") or _INTERNAL_ACTOR_NAME_RE.fullmatch(name):
        return None
    return name


def decode_moveentry11(hex_bytes, size):
    # 6~7 怪物 DID（小端）
    did = le_int(hex_bytes[5:9])

    # MOVEENTRY11 名稱欄位從 byte 90 開始。
    name = _decode_actor_name(hex_bytes, 90, size)

    return {
        "did": did,
        "name": name
    }
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
    # 6~7 怪物 DID（小端）
    did = le_int(hex_bytes[5:9])

    # STANDENTRY11 在 byte 83 可能保留 # 前綴（例如 #mk_10）。
    # 保留它讓 sanitize_actor_name() 能辨識為內部名稱，而不是誤當顯示名稱。
    name = _decode_actor_name(hex_bytes, 83, size)

    return {
        "did": did,
        "name": name
    }
# ============================================================
# 解析 HEADER_ZC_NOTIFY_NEWENTRY11
# ============================================================
def decode_newentry11(hex_bytes, size):
    # 6~7 怪物 DID（小端）
    did = le_int(hex_bytes[5:9])

    # 這個 client 的 NEWENTRY11 真正名稱從 byte 90 開始。
    # 舊版從 83 開始會把 FF/flag/class 一起解碼，造成「���中文名」污染。
    name = _decode_actor_name(hex_bytes, 90, size)

    return {
        "did": did,
        "name": name
    }
    
def parse_newentry11_blocks(text):
    t0_new = time.perf_counter()
    pattern = re.compile(
        r'\[(\+\d{2}:\d{2}:\d{2}:\d{3})\]\s+packet\s+(HEADER_ZC_NOTIFY_NEWENTRY11)\s*'
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
    t1_new = time.perf_counter()
    print(f"[new entry] 解析耗時: {(t1_new - t0_new) * 1000:.3f} ms")
    return results

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
        self.current_chart_mode = "bar"   # bar / line
        self.chart_status_text = "尚未載入資料"
        self.hud = DamageHUD()
        self.hud.hide()
        super().__init__()
        self.setWindowTitle("RRF傷害解析器 v1.1")
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
        self.current_map_name = ""
         
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
        self.Character_ability_changes_checkbox = QCheckBox("解析角色能力變動")
        self.Character_ability_changes_checkbox.setFixedWidth(150)
        btn_layout.addWidget(self.Character_ability_changes_checkbox)

        # 傷害歷程：是否顯示一般狀態開始 / 結束事件（預設顯示）
        self.show_status_history_checkbox = QCheckBox("傷害歷程顯示狀態")
        self.show_status_history_checkbox.setChecked(False)
        self.show_status_history_checkbox.setFixedWidth(150)
        btn_layout.addWidget(self.show_status_history_checkbox)



        # 將按鈕布局加到主要布局中
        layout.addLayout(btn_layout)

        # --- 更新秒數 + DID 選擇在同一行（靠右） ---
        interval_layout = QHBoxLayout()

  
        self.status = QLabel("")
        self.status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status.setMaximumWidth(400) 
        interval_layout.addWidget(self.status)
        # ★靠右關鍵：先塞一個彈性空間
        interval_layout.addStretch()
        # 更新秒數標籤
        interval_layout.addWidget(QLabel("｜更新秒數："))

        # 數字框改右對齊 + 固定寬度
        self.refresh_input = QSpinBox()
        self.refresh_input.setRange(0, 3600)
        self.refresh_input.setValue(0)
        self.refresh_input.setFixedWidth(80)      # ★固定寬度
        self.refresh_input.setAlignment(Qt.AlignRight)   # ★讓數字靠右
        interval_layout.addWidget(self.refresh_input)
        # 自動使用資料夾內最新 RRF 勾選
        self.auto_latest_checkbox = QCheckBox("最新 RRF")
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

        # 勾選狀態改變時只重新套用傷害歷程篩選，不重新解析 RRF。
        self.show_status_history_checkbox.stateChanged.connect(self.apply_did_filter)


        layout.addLayout(interval_layout)


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

        self.btn_bar = QPushButton("顯示總傷害長條圖")
        self.btn_line = QPushButton("顯示每秒折線趨勢圖")

        self.btn_bar.clicked.connect(self.on_bar_clicked)       # 原本的畫面
        self.btn_line.clicked.connect(self.on_line_clicked)        # 新增的折線圖

        btn_box.addWidget(self.btn_bar)
        btn_box.addWidget(self.btn_line)

        vbox.addLayout(btn_box)
        # ===========================

        # ➊ 圖表區塊
        self.fig = Figure(figsize=(5, 2))
        self.canvas = FigureCanvas(self.fig)
        self.canvas.mpl_connect("scroll_event", self.on_scroll)
        vbox.addWidget(self.canvas)

        
        # ⭐ 加入拖曳/縮放工具列（NavigationToolbar）
        self.toolbar = MyNavigationToolbar(self.canvas, self)
        self.left_pan = LeftButtonPan(self.canvas, self.toolbar)

        vbox.addWidget(self.toolbar)
        # ⭐ 預設隱藏（因為預設是長條圖）
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

        self.tabs.addTab(tab_stats, "統計傷害")
        # Tab2：原始資料
        self.table_raw = QTableWidget()
        self.table_raw.setColumnCount(9)
        self.table_raw.setHorizontalHeaderLabels([
            "時間戳", "技能名稱", "攻方ID", "受方ID",
            "傷害", "等級", "次數", "來源延遲", "目標延遲"
        ])
        self.tabs.addTab(self.table_raw, "傷害歷程")
        
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

    def on_tab_changed(self, idx):
        if idx == 1:
            self.update_raw_table()
        elif idx == 2:
            self.update_drop_table()
        elif idx == 3:
            self.update_monster_drop_tree()   

    def on_scroll(self, event):
        ax = event.inaxes
        if ax is None:
            return

        # 縮放比例
        base_scale = 1.2
        if event.button == 'up':      # 放大
            scale_factor = 1 / base_scale
        elif event.button == 'down':  # 縮小
            scale_factor = base_scale
        else:
            return

        # 滑鼠所在點
        xdata = event.xdata
        ydata = event.ydata
        if xdata is None or ydata is None:
            return

        # 目前範圍
        cur_xlim = ax.get_xlim()
        cur_ylim = ax.get_ylim()

        # 滑鼠位置佔目前視窗的比例
        x_left_ratio  = (xdata - cur_xlim[0]) / (cur_xlim[1] - cur_xlim[0])
        y_bottom_ratio = (ydata - cur_ylim[0]) / (cur_ylim[1] - cur_ylim[0])

        # 新範圍大小
        new_width  = (cur_xlim[1] - cur_xlim[0]) * scale_factor
        new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

        # 依滑鼠比例重新計算新視窗位置 → 不會跳掉！
        new_xmin = xdata - new_width * x_left_ratio
        new_xmax = xdata + new_width * (1 - x_left_ratio)

        new_ymin = ydata - new_height * y_bottom_ratio
        new_ymax = ydata + new_height * (1 - y_bottom_ratio)

        # 設定新範圍
        ax.set_xlim(new_xmin, new_xmax)
        ax.set_ylim(new_ymin, new_ymax)

        self.canvas.draw_idle()

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

            interval = self.refresh_input.value()
            if interval > 0 and not self.underMouse():
                self.auto_timer.start(interval * 1000)
            self.update_load_button_text()
            return

        mode = delta.mode

        # 第一階段相容層：raw bytes 已直接由 Python RRF reader 取得，完全不寫 TXT。
        # 為了先保留既有 decode_* 的行為，暫時只在記憶體中產生舊 parser 需要的
        # 最小文字 block。下一階段可逐一把 parse_* 改成直接接 RawPacket.data。
        t0_opentxt = time.perf_counter()
        text = delta.to_legacy_text(include_metadata=True)

        map_name = parse_replaydata_mapname(text)
        if map_name:
            self.current_map_name = map_name

        if not text.strip():
            self.status.setText("RRF 有更新，但沒有可供分析的新封包")
            self.progress_bar.setValue(100)
            self.is_processing = False
            self._load_lock = False
            interval = self.refresh_input.value()
            if interval > 0 and not self.underMouse():
                self.auto_timer.start(interval * 1000)
            return

        t1_opentxt = time.perf_counter()
        print("====RRF raw → compatibility blocks====")
        print(f"[raw-adapter] 耗時: {(t1_opentxt - t0_opentxt) * 1000:.3f} ms")
        print("====多執行緒區段====")
        self.progress_bar.setValue(30)
        self.status.setText(f"直接解析 raw packet（{mode}，新增 {len(delta.packets)} 包）...")
        QApplication.processEvents()

        from concurrent.futures import ThreadPoolExecutor, as_completed

        # -------------------------------------------------------
        # ❶ 多執行緒平行解析封包
        # -------------------------------------------------------
        t0_allThread = time.perf_counter()


        checked = check_button_state(self)
        
        with ThreadPoolExecutor(max_workers=12) as exe:
            futures = {
                "ground": exe.submit(parse_groundskill_blocks, text),
                "skill2": exe.submit(parse_skill2_blocks, text),
                "act3":   exe.submit(parse_act3_blocks, text),
                "move":   exe.submit(parse_moveentry11_blocks, text),
                "stand":  exe.submit(parse_standentry11_blocks, text),
                "new":    exe.submit(parse_newentry11_blocks, text),
                "state3": exe.submit(parse_statechange3_blocks, text),
                "status": exe.submit(parse_status_change_blocks, text),
                "efst":   exe.submit(
                    extract_efstinfo_values,
                    content=text,
                    include_status_changes=True,
                ),
                "couple": exe.submit(parse_couplestatus_blocks, text, checked),
                "par":    exe.submit(parse_par_change_blocks, text, checked),
                "vanish": exe.submit(parse_vanish_blocks, text),
                "drop":   exe.submit(parse_itemdrop_blocks, text),
            }

            # raw snapshot 每次都帶目前 metadata；delta 時也更新 SID/隊友名稱。
            futures["sid"] = exe.submit(build_sid_to_name_map, text)

        # 用來存這次解析後的資料
        if mode == "full":
            self.sid_name_map = {}
            self.did_name_map = {}
            self.did_name_source = {}
            self.efst_info_map = {}
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
        
        # 🔥 誰先完成，就先處理誰
        for future in as_completed(futures.values()):
            name = next(k for k, v in futures.items() if v is future)
            result = future.result()


            print(f"[{name}] 已完成，開始處理…")

            # 🔥 在這裡依任務名稱立即做對應處理（你要的功能就在這裡）
            if name == "new":
                # 你想要「new entry 完成就立即 decode」
                #standentry_blocks = result
                for blk in result:
                    info = decode_newentry11(blk["hex"], blk["size"])
                    self.update_did_name(info["did"], info["name"], "new")
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
                    self.update_did_name(info["did"], info["name"], "move")
                print(f"move 已處理")
                
            elif name == "stand":
                #standentry_blocks = result
                for blk in result:
                    info = decode_standentry11(blk["hex"], blk["size"])
                    self.update_did_name(info["did"], info["name"], "stand")
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

                # 若是第一次變身 → 記住原始 skin
                if sid not in self.transform_original_skin:
                    self.transform_original_skin[sid] = skin

                original_skin = self.transform_original_skin[sid]

                # 變身持續秒數 → 毫秒
                TRANSFORM_INTERVAL_MS = TRANSFORM_DURATION_MAP.get(original_skin, DEFAULT_INTERVAL) * 1000

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

                original_skin = self.transform_original_skin.get(sid, skin)
                TRANSFORM_INTERVAL_MS = TRANSFORM_DURATION_MAP.get(original_skin, DEFAULT_INTERVAL) * 1000

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

        vanish_events = []
        #print(f"{vanish}")
        for ev in vanish:
            vanish_events.append({
                "timestamp": ev["timestamp"],
                "skill_id": 0,
                "skill_name": "消失狀態",
                "sid": "死亡",                 # 不知道攻方就先 0
                "did": ev["did"],
                "damage": 0,
                "damage_display": "",
                "level": "",
                "hit_count": "",
                "skill_delay": "",
                "global_delay": "",
            })



        
        t1_allThread = time.perf_counter()
        print(f"[all Thread] 解析耗時: {(t1_allThread - t0_allThread) * 1000:.3f} ms")

        self.progress_bar.setValue(50)
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
            if pkt["type"] != "Skill2" and pkt["type"] != "GroundSkill" and pkt["type"] != "Act3":
                continue

            dec = pkt.get("decode")
            if not dec:
                continue

            sid = dec.get("sid", 0)
            hits = dec.get("hit_count", 1)

            if sid:
                self.sid_attack_count[sid] += hits

        # -------------------------------------------------------
        # ❺ 修正假 SID（不建議多執行緒，要保持順序）
        # -------------------------------------------------------
        if mode == "full":
            all_packets = merge_with_true_sid(all_packets)
        else:
            all_packets = self.merge_new_packets_with_true_sid(all_packets)

        self.progress_bar.setValue(70)
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
            dmg = d["damage"]

            if dmg <= 0 or dmg > INT_MAX:
                continue

            d["timestamp"] = p["timestamp"]
            new_parsed_data.append(d)

        new_raw_data = new_parsed_data + stat_events + status_events + vanish_events
        
        new_vanish_points = [
            {
                "timestamp": ev["timestamp"],
                "time_ms": timestamp_to_ms(ev["timestamp"]),
                "did": ev["did"],
                "packet_pos": ev["packet_pos"],   # ★ 新增
            }
            for ev in vanish
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

        # ★ 這裡資料已經完成
        self.progress_bar.setValue(90)
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
                if did in self.sid_name_map:
                    name = self.sid_name_map[did]
                elif did in self.did_name_map:
                    name = self.did_name_map[did]
                else:
                    name = "未知目標"

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



        #self.status.setText(f"更新完成，耗時 {elapsed:.3f} 秒")        
        #self.status.setText(f"共解析到 {len(self.parsed_data)} 筆 更新耗時：{elapsed:.2f} 秒")
        real_elapsed = time.time() - self.process_start_time

        self.status.setText(f"共解析 {len(self.parsed_data)} 筆 更新耗時：{real_elapsed:.2f} 秒")
        self.progress_bar.setValue(100)
        QApplication.processEvents()
        
        self.first_full_parse_done = True

        self.is_processing = False
        self._load_lock = False

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
        self.progress_bar.hide()
        self.progress_bar.setValue(0)
        self.is_processing = False
        self._load_lock = False

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
    def update_raw_table(self):
        interval = self.refresh_input.value()
        data = getattr(self, "current_filtered_raw", self.current_filtered_data)
        self.table_raw.setRowCount(len(data))

        for r, d in enumerate(data):
            self.table_raw.setItem(r, 0, QTableWidgetItem(d["timestamp"]))
            self.table_raw.setItem(r, 1, QTableWidgetItem(d["skill_name"]))
            # --- SID 顯示名稱 ---
            sid = d["sid"]

            # 玩家（GroupInfo）
            if sid in self.sid_name_map:
                sid_display = f"{self.sid_name_map[sid]}"# ({sid})"

            # 怪物（MOVEENTRY/STANDENTRY/NEWENTRY）
            elif sid in self.did_name_map:
                sid_display = f"{self.did_name_map[sid]}"# ({sid})"

            # 未知
            else:
                sid_display = str(sid)               

            self.table_raw.setItem(r, 2, QTableWidgetItem(sid_display))
            did = d["did"]
            name = self.sid_name_map.get(did, self.did_name_map.get(did, str(did)))
            self.table_raw.setItem(r, 3, QTableWidgetItem(name))

            dmg_text = d.get("damage_display")
            if dmg_text is None:
                dmg_text = f"{int(d['damage']):,}"
            self.table_raw.setItem(r, 4, QTableWidgetItem(dmg_text))
            self.table_raw.setItem(r, 5, QTableWidgetItem(str(d["level"])))
            self.table_raw.setItem(r, 6, QTableWidgetItem(str(d["hit_count"])))
            self.table_raw.setItem(r, 7, QTableWidgetItem(str(d["skill_delay"])))
            self.table_raw.setItem(r, 8, QTableWidgetItem(str(d["global_delay"])))
            
        # 滾動到最後一行
        if interval > 0 :
            self.table_raw.scrollToBottom()
        # 字體測量（使用表格目前字體）
        metrics = QFontMetrics(self.table_raw.font())

        padding = metrics.horizontalAdvance("字" * 1)   # 5 個中文字的寬度

        for col in range(self.table_raw.columnCount()):
            max_width = 0

            # 1. 檢查表頭文字寬度
            header_text = self.table_raw.horizontalHeaderItem(col).text()
            max_width = metrics.horizontalAdvance(header_text)

            # 2. 檢查每列資料
            for row in range(self.table_raw.rowCount()):
                item = self.table_raw.item(row, col)
                if item is not None:
                    w = metrics.horizontalAdvance(item.text())
                    if w > max_width:
                        max_width = w

            # 3. 最後加上額外 5 個字寬度
            final_width = max_width + padding

            # 最小寬度避免太窄（可調整）
            final_width = max(final_width, 80)

            self.table_raw.setColumnWidth(col, final_width)

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
            return did, self.did_name_map.get(did, f"ID {did}")

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
            return did, self.did_name_map.get(did, f"ID {did}")

        # ③ 最後才退回單純最近時間差
        best = min(candidates, key=lambda x: abs(x["time_ms"] - drop_ms))
        did = best["did"]
        return did, self.did_name_map.get(did, f"ID {did}")

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
                # ★ 這裡把「攻擊次數」（技能次數）加總起來
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

                    child = QTreeWidgetItem([
                        f"{skill_name} (ID {skill_id}) - 次數 {cnt}",
                        f"{avg:,.0f}",
                        f"{total_skill:,.0f}",
                        "0"      # ★ 技能 DPS 也固定 0
                    ])

                    for col in range(1, 4):
                        child.setTextAlignment(col, Qt.AlignRight)

                    parent.addChild(child)
                                    
                # ★ 顯示 monsterskin 的變身次數（type=9999）與機率
                skin_dict = self.state_change_count.get(sid, {})  # dict: skin -> count
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
            # ★ 每進來一筆，就是一次攻擊（對應你樹上「次數」那個欄位）
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

                child = QTreeWidgetItem([
                    f"{skill_name} (ID {skill_id}) - 次數 {cnt} (秒{T_cnt})",
                    f"{(total/cnt):,.0f}" if cnt > 0 else "0",
                    f"{total:,.0f}",
                    f"{T_dmg:,.0f}"         # ★ 這個技能在 T 秒的 DPS
                ])

                for col in range(1, 4):
                    child.setTextAlignment(col, Qt.AlignRight)

                parent.addChild(child)
                
            # ★ 顯示 monsterskin 的變身次數（type=9999）與機率
            skin_dict = self.state_change_count.get(sid, {})  # dict: skin -> count
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
        self.fig.clear()
        ax = self.fig.add_subplot(111)

        # 透明背景融入黑色 UI
        self.fig.patch.set_alpha(0)
        ax.set_facecolor("none")
        self.canvas.setStyleSheet("background-color: transparent;")

        # --- ★ 過濾掉總傷害 < 第一名 1% 的 SID ---
        if sorted_sids:
            max_total = sorted_sids[0][1]          # 第一名的總傷害
            threshold = max_total * 0.01           # 1%

            filtered = [
                (sid, total) for sid, total in sorted_sids
                if total >= threshold
            ]
        else:
            filtered = sorted_sids

        # 使用過濾後的列表
        names = []
        for sid, _ in filtered:

            # 1. 先找角色名稱 (玩家名稱)
            if sid in self.sid_name_map:
                names.append(self.sid_name_map[sid])
                continue

            # 2. 再找 DID 名稱 (魔物名稱)
            if sid in self.did_name_map:
                names.append(self.did_name_map[sid])
                continue

            # 3. 樹狀清單 fallback：如果你有在樹狀中使用特殊格式，可在這裡補
            #    目前先用 SID 當作字串
            names.append(str(sid))        
        values = [total for _, total in filtered]


        # 深色 UI 色系
        bars = ax.barh(range(len(names)), values, color="#4C9AFF", height=0.55)
        ax.invert_yaxis()

        # 刻度
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontproperties=font, color="#FFFFFF")
        title_name = self.get_active_filter_title()
        #ax.set_title("總傷害", fontproperties=font, color="#FFFFFF")
        ax.set_title(
            f"{title_name} 的個別總傷害",
            fontproperties=font,
            color="#FFFFFF"
        )
        ax.set_xlabel("總傷害", fontproperties=font, color="#DDDDDD")

        ax.tick_params(colors="#AAAAAA")

        # 移除邊框
        for spine in ax.spines.values():
            spine.set_visible(False)

        # 顯示數字
        for bar, val in zip(bars, values):
            ax.text(
                val + max(values) * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{val:,}",
                va='center',
                fontsize=10,
                fontproperties=font,
                color="#FFFFFF"
            )

        self.canvas.draw()

    def draw_line_chart(self):
        data = self.current_filtered_data
        if not data:
            return

        from collections import defaultdict

        self.fig.clear()
        ax = self.fig.add_subplot(111)

        # 透明背景
        self.fig.patch.set_alpha(0)
        ax.set_facecolor("none")
        self.canvas.setStyleSheet("background-color: transparent;")

        # timeline[sid][second] = damage
        timeline = defaultdict(lambda: defaultdict(int))

        # 先解析全部有效時間，並以最早一筆作為折線圖起點。
        # 不再把 600 秒（10 分鐘）之後的資料直接丟棄。
        timed_rows = []
        for d in data:
            try:
                ts = d["timestamp"]   # 例如 "+00:04:36:783"
                h, m, s, ms = map(int, ts[1:].split(":"))
                t = h * 3600 + m * 60 + s + ms / 1000.0
            except (KeyError, TypeError, ValueError):
                continue

            timed_rows.append((t, d))

        if not timed_rows:
            return

        t0 = min(t for t, _ in timed_rows)

        # ---- 計算完整紀錄的每秒傷害 ----
        for t, d in timed_rows:
            sec = int(t - t0)
            if sec < 0:
                continue

            timeline[d["sid"]][sec] += d["damage"]


        # ---- 1% 過濾 ----
        sid_total = { sid: sum(sec_data.values()) for sid, sec_data in timeline.items() }

        if sid_total:
            max_total = max(sid_total.values())
            threshold = max_total * 0.01
            allowed_sid = { sid for sid, total in sid_total.items() if total >= threshold }
        else:
            allowed_sid = set()


        # ---- 找出完整時間範圍 ----
        max_sec = 0
        for sid in timeline:
            if timeline[sid]:
                max_sec = max(max_sec, max(timeline[sid].keys()))

        # ---- 畫線（含 1% 過濾）----
        for sid, sec_data in timeline.items():

            if sid not in allowed_sid:
                continue

            seconds = list(range(max_sec + 1))
            # 缺少傷害的秒數直接顯示為 0，不必先把大量 0 寫回 timeline。
            values = [sec_data.get(sec, 0) for sec in seconds]

            # SID 名稱
            if sid in self.sid_name_map:
                label = self.sid_name_map[sid]
            elif sid in self.did_name_map:
                label = self.did_name_map[sid]
            else:
                label = f"{sid}"

            ax.plot(seconds, values, label=label)


        # ---- 💄 還原你舊折線圖的 UI 外觀設定 ----
        leg = ax.legend(
            loc="center left",       # 固定在左側
            bbox_to_anchor=(-0.28, 0.5),  # (x, y) 偏移位置
            frameon=True,
        )
        leg.set_draggable(True)
        title_name = self.get_active_filter_title()

        ax.set_title(
            f"{title_name} 的每秒傷害趨勢",
            fontproperties=font,
            color="#FFFFFF"
        )
        ax.set_xlabel("時間 (+HH:MM:SS)", fontproperties=font, color="#DDDDDD")

        ax.tick_params(colors="#AAAAAA")

        for spine in ax.spines.values():
            spine.set_visible(False)

        # ---- 💡 X 軸用「實際時間戳」來顯示 ----
        # x 是「從第一筆傷害開始的第幾秒」，要換成：t_real = t0 + x
        def format_time(x):
            if t0 is None:
                return ""

            total = int(t0 + x)
            if total < 0:
                return ""

            h = total // 3600
            m = (total % 3600) // 60
            s = total % 60

            # ---- 規則：自動縮短 ----
            if h == 0 and m == 0:
                return f"{s}"                    # 只顯示秒
            elif h == 0:
                return f"{m}:{s:02d}"            # mm:ss
            else:
                return f"{h}:{m:02d}:{s:02d}"    # h:mm:ss（不補 h 前導 0）


        # X 軸刻度文字
        ax.xaxis.set_major_formatter(
            FuncFormatter(lambda x, pos: format_time(x))
        )

        # ---- 💡 滑鼠 XY 顯示格式也改成時間戳 ----
        def format_coord(x, y):
            dmg = int(round(y))
            dmg_str = f"{dmg:,}"

            if t0 is None:
                return f"時間：N/A    傷害：{dmg_str}"

            total = int(t0 + round(x))
            if total < 0:
                return f"時間：N/A    傷害：{dmg_str}"

            h = total // 3600
            m = (total % 3600) // 60
            s = total % 60

            # ---- 套用相同顯示規則 ----
            if h == 0 and m == 0:
                ts_str = f"{s}"
            elif h == 0:
                ts_str = f"{m}:{s:02d}"
            else:
                ts_str = f"{h}:{m:02d}:{s:02d}"

            return f"時間：{ts_str}    傷害：{dmg_str}"


        ax.format_coord = format_coord

        # ---- 左邊空間補齊 ----
        self.fig.subplots_adjust(left=0.20)

        self.canvas.draw()

    def update_did_name(self, did, raw_name, source):
        """更新 DID 顯示名稱；避免低品質/內部名稱覆寫正常名稱。"""
        if not did:
            return

        override = MONSTER_NAME_OVERRIDE.get(did)
        if override:
            self.did_name_map[did] = override
            self.did_name_source[did] = "override"
            return

        name = sanitize_actor_name(raw_name)
        if not name:
            return

        priority = {"stand": 1, "move": 2, "new": 3, "override": 99}
        old_source = self.did_name_source.get(did)
        old_name = sanitize_actor_name(self.did_name_map.get(did))
        old_priority = priority.get(old_source, 0)
        new_priority = priority.get(source, 0)

        if old_name is None or new_priority >= old_priority:
            self.did_name_map[did] = name
            self.did_name_source[did] = source

    def get_monster_name_by_did(self, did, fallback=None):
        if did in self.did_name_map:
            name = self.did_name_map[did]
        elif did in self.sid_name_map:
            name = self.sid_name_map[did]
        else:
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

        # 1) 死亡統計：從 raw 裡的「消失狀態」抓
        for row in raw_base:
            if row.get("skill_name") != "消失狀態":
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


    def apply_did_filter(self, *_args):
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

        # 只控制傷害歷程中的一般狀態開始 / 結束事件。
        # 不影響實際傷害、能力變動、死亡/消失、掉落或任何統計資料。
        if not self.show_status_history_checkbox.isChecked():
            raw_source = [
                d for d in raw_source
                if d.get("status_event") not in ("start", "end")
            ]

        filtered_damage = self.parsed_data
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
        # 狀態開始/結束、能力變動、死亡消失等 damage=0 的歷程事件
        # 必須保留，不能因為沒有攻方 SID 而被排除。
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

        self.current_filtered_data = list(filtered_damage)
        self.current_filtered_raw = list(filtered_raw)

        self.update_raw_table()
        self.update_drop_table()
        self.update_monster_drop_tree()
        self.update_group_tree()
        self.refresh_chart()
        self.update_hud_top5()


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
        self.refresh_chart()

    def on_line_clicked(self):
        self.current_chart_mode = "line"
        self.refresh_chart()



    def refresh_chart(self):
        if not hasattr(self, "current_filtered_data"):
            return

        data = self.current_filtered_data
        if not data:
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
            self.toolbar.show()
            self.draw_line_chart()
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
    app = QApplication(sys.argv)
    ui = MainUI()
    ui.show()
    sys.exit(app.exec())
