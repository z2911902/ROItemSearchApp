import sys
import pandas as pd
import yaml
from collections import defaultdict
# === STAGE 19 DESKTOP SHARED SKILL TREE CORE ===
from ro_core import (
    stage19_build_enable_skill_note as _core_stage19_build_enable_skill_note,
    stage19_build_job_skill_map as _core_stage19_build_job_skill_map,
    stage19_compute_skill_depths as _core_stage19_compute_skill_depths,
    stage19_get_job_chain as _core_stage19_get_job_chain,
    stage19_split_job_chain_to_groups as _core_stage19_split_job_chain_to_groups,
)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QComboBox, QLabel, QScrollArea, QGridLayout,
    QPushButton, QHBoxLayout, QMessageBox, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolTip
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QSpacerItem, QSizePolicy
from PySide6.QtCore import QEvent

# =========================================================
# 設定路徑
# =========================================================
SKILL_CSV_PATH = r"data\skillneme.csv"
SKILL_TREE_YML_PATH = r"data\skill_tree.yml"
import re

TREEVIEW_LUB_PATH = r"data\skilltreeview.lub"

# job_name -> { skill_code -> index }
treeview_positions = {}

def _jt_to_id_jobneme(jt_name: str) -> str:
    """
    將 'DRAGON_KNIGHT' 轉成 'Dragon_Knight'
    和你 job_dict 裡的 id_jobneme 對齊。
    """
    return "_".join(p.capitalize() for p in jt_name.lower().split("_"))

def load_skill_treeview(filepath: str = TREEVIEW_LUB_PATH):
    global treeview_positions
    treeview_positions = {}

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        lua = f.read()

    pattern = re.compile(
        r"\[JOBID\.JT_([A-Z0-9_]+)\]\s*=\s*\{(.*?)\}",
        re.S
    )
    matches = pattern.findall(lua)

    for jt_name, body in matches:
        job_key = _jt_to_id_jobneme(jt_name)  # 例如 DRAGON_KNIGHT -> Dragon_Knight
        pairs = re.findall(r"\[(\d+)\]\s*=\s*SKID\.([A-Z0-9_]+)", body)
        if not pairs:
            continue
        pos_map = {code: int(idx) for idx, code in pairs}
        treeview_positions[job_key] = pos_map

    print(f"skilltreeview.lub 解析完成，職業數：{len(treeview_positions)}")


def get_combined_pos_map(job_key: str) -> dict:
    """
    取得某個 4 轉職業的完整技能排序：
    - 先塞 1/2/3 轉 (id_jobneme_OL)
    - 再塞 4 轉本身 (id_jobneme)
    之後 SkillTreeGrid 只會拿有 skills 的 code 來排，所以多塞不會爆。
    """
    pos_map: dict[str, int] = {}

    # 先找到這個 job_key 在 job_dict 的 entry
    job_entry = None
    for _, j in job_dict.items():
        if j.get("id_jobneme") == job_key:
            job_entry = j
            break

    # 先處理舊轉職 (1/2/3 轉)
    if job_entry:
        ol = job_entry.get("id_jobneme_OL")
        if ol:
            for name in ol.split("/"):
                name = name.strip()
                if not name:
                    continue
                pm = treeview_positions.get(name)
                if not pm:
                    continue
                # 不覆蓋已存在的 index（避免互相踢掉）
                for code, idx in pm.items():
                    pos_map.setdefault(code, idx)

    # 再處理 4 轉本身，讓 4 轉的 index 優先（覆蓋舊的）
    base_pm = treeview_positions.get(job_key, {})
    for code, idx in base_pm.items():
        pos_map[code] = idx

    return pos_map







# =========================================================
# skillneme.csv 對照：Code -> ID / 中文
# =========================================================
skill_id_to_name   = {}
skill_code_to_id   = {}
skill_code_to_name = {}

def load_skill_map(filepath=SKILL_CSV_PATH):
    global skill_id_to_name, skill_code_to_id, skill_code_to_name

    df = pd.read_csv(filepath, header=0)
    # 假設欄位：ID, Code, Name
    id_col   = "ID"
    code_col = "Code"
    name_col = "Name"

    skill_id_to_name   = dict(zip(df[id_col], df[name_col]))
    skill_code_to_id   = dict(zip(df[code_col], df[id_col]))
    skill_code_to_name = dict(zip(df[code_col], df[name_col]))

    #print("讀入 skillneme.csv，欄位：", list(df.columns))


# =========================================================
# skill_tree.yml：Body: [ { Job, Inherit, Tree: [...] }, ... ]
# =========================================================
job_skill_tree_raw = {}

def load_skill_tree(filepath=SKILL_TREE_YML_PATH):
    global job_skill_tree_raw

    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    body = data.get("Body", data)
    job_skill_tree_raw = {}
    for entry in body:
        job_name = entry.get("Job")
        if not job_name:
            continue
        inherit = entry.get("Inherit") or {}
        tree    = entry.get("Tree") or []
        job_skill_tree_raw[job_name] = {
            "inherit": inherit,
            "tree": tree,
        }
    print("讀入 skill_tree.yml，職業數：", len(job_skill_tree_raw))

def get_job_chain(job_key: str) -> list[str]:
    return _core_stage19_get_job_chain(job_key, job_dict)

def split_job_chain_to_groups(job_chain: list[str]) -> list[list[str]]:
    return _core_stage19_split_job_chain_to_groups(job_chain)

def build_job_skill_map(job_name, visited=None):
    return _core_stage19_build_job_skill_map(
        job_name, job_skill_tree_raw, visited
    )


# =========================================================
# 計算技能「層級」（深度），用來決定放哪一欄
# =========================================================
def compute_skill_depths(skill_map_job: dict) -> dict:
    return _core_stage19_compute_skill_depths(skill_map_job)


# =========================================================
# SkillNodeWidget：單一技能的小方塊
# =========================================================
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class SkillNodeWidget(QFrame):
    def __init__(self, code, get_level, max_level, inc_cb, dec_cb, parent=None):
        super().__init__(parent)
        self.code = code
        self.get_level = get_level
        self.inc_cb = inc_cb      # 加點 callback (父視窗的 increase_skill)
        self.dec_cb = dec_cb      # 減點 callback (父視窗的 decrease_skill)
        self.max_level = max_level

        self.setFrameShape(QFrame.Box)
        self.setLineWidth(1)
        self.setCursor(Qt.PointingHandCursor)  # 滑鼠變小手

        self.setStyleSheet(
            "QFrame { background:#222; border-radius:4px; } "
            "QLabel { color:white; font-size:12px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # 技能中文名稱
        cn_name = skill_code_to_name.get(code, code)
        self.lbl_name = QLabel(cn_name)
        self.lbl_name.setAlignment(Qt.AlignCenter)
        self.lbl_name.setWordWrap(True)
        layout.addWidget(self.lbl_name)

        # 等級顯示
        row = QGridLayout()
        row.setColumnStretch(0, 1)
        row.setColumnStretch(1, 0)   # Lv 置中
        row.setColumnStretch(2, 1)

        self.lbl_level = QLabel()
        self.lbl_level.setStyleSheet("color: white; font-size: 12px;")
        self.lbl_level.setAlignment(Qt.AlignCenter)

        self.lbl_req = QLabel()
        self.lbl_req.setStyleSheet("color: red; font-weight: bold; font-size: 12px; padding-right:2px;")
        self.lbl_req.setAlignment(Qt.AlignRight)
        self.lbl_req.setVisible(False)

        row.addWidget(QLabel(""), 0, 0)  # 左虛位
        row.addWidget(self.lbl_level, 0, 1, alignment=Qt.AlignHCenter)
        row.addWidget(self.lbl_req, 0, 2, alignment=Qt.AlignRight)

        layout.addLayout(row)





        self.update_display()

    def force_set_level(self, lv):
        # ① 直接覆蓋 get_level，讓 UI 讀取新的 lv
        self.get_level = lambda c, lv=lv: lv
        # ② 更新顯示
        self.update_display()


    def enterEvent(self, event):
        # 找到主視窗並呼叫 on_skill_hover
        window = self.window()
        if hasattr(window, 'on_skill_hover'):
            window.on_skill_hover(self.code)
        super().enterEvent(event)

    def leaveEvent(self, event):
        window = self.window()
        if hasattr(window, 'on_skill_hover'):
            window.on_skill_hover(None)
        super().leaveEvent(event)


    def show_requirement(self, text):
        self.lbl_req.setText(text)
        self.lbl_req.setVisible(bool(text))

    def hide_requirement(self):
        self.lbl_req.clear()
        self.lbl_req.setVisible(False)

    # 在這個函式加一個參數 parent_widget: SkillNodeWidget 或事件來源
    def show_tooltip(self, msg, widget):
        pos = widget.mapToGlobal(widget.rect().center())
        QToolTip.showText(pos, msg, widget)


    def update_display(self):
        lv = self.get_level(self.code)
        self.lbl_level.setText(f"Lv {lv}/{self.max_level}")
        # 有點數時背景亮一點
        if lv > 0:
            self.setStyleSheet(
                "QFrame { background:#666; border-radius:4px; } "
                "QLabel { color:white; font-size:11px; }"
            )
        else:
            self.setStyleSheet(
                "QFrame { background:#222; border-radius:4px; } "
                "QLabel { color:white; font-size:11px; }"
            )

    def mousePressEvent(self, event):
        # 左鍵加點
        if event.button() == Qt.LeftButton:
            # 這裡可以檢查「能不能加點」
            # 但只要你把點數檢查放在 increase_skill 裡，其實這裡不用檢查
            self.inc_cb(self.code, from_widget=self, event=event)

        # 右鍵減點
        elif event.button() == Qt.RightButton:
            # ❗ 這裡千萬不要檢查「點數是否已滿」之類的東西
            # 也不要呼叫什麼 can_increase_skill
            self.dec_cb(self.code)


# =========================================================
# SkillTreeGrid：用 GridLayout 排技能
# =========================================================
SKILL_PER_ROW = 7  # 一排 7 個

class SkillTreeGrid(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setSpacing(12)
        self.code2widget = {}

    def clear(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def set_tree(self, skill_map_job, levels, job_chain, inc_cb, dec_cb):
        """
        skill_map_job: { skill_code -> skill_info }
        levels:        { skill_code -> lv }
        job_chain:     ['Swordman', 'Knight', 'Knight_H', 'Rune_Knight', ...]
        """

        self.clear()
        if not skill_map_job:
            return
        self.code2widget = {}
        placed = set()
        row_offset = 0

        # ---------- 1) 先把 job_chain 分成「職業群組」 ----------
        # 例如: ['Swordman', 'Knight', 'Knight_H', 'Rune_Knight']
        # -> groups = [
        #      ['Swordman'],
        #      ['Knight','Knight_H'],
        #      ['Rune_Knight'],
        #    ]
        groups: list[list[str]] = split_job_chain_to_groups(job_chain)

        # ---------- 2) 逐個群組往下堆疊 ----------
        for idx_group, group in enumerate(groups):
            # 合併這個群組所有職業頁面的位置表
            # combined_pos: { skill_code -> index }
            combined_pos: dict[str, int] = {}
            for job_name in group:
                pos_map = treeview_positions.get(job_name, {})
                if not pos_map:
                    continue
                # 後出現的職業可以覆蓋前面的 index（例如 Knight_H 想調整部分技能位置）
                for code, idx in pos_map.items():
                    if code in skill_map_job:  # 只排在本職業 skill tree 有的技能
                        combined_pos[code] = idx

            if not combined_pos:
                continue

            # 拿出 index 與 code，並排序
            codes_with_idx = sorted(combined_pos.items(), key=lambda x: x[1])
            max_idx = max(idx for _, idx in codes_with_idx)
            max_local_row = max_idx // SKILL_PER_ROW

            # ---------- 2-1) 排這個群組的所有技能 ----------
            for code, idx in codes_with_idx:
                if code in placed:
                    continue
                info   = skill_map_job[code]
                max_lv = info.get("MaxLevel", 0)

                row_local = idx // SKILL_PER_ROW
                col       = idx %  SKILL_PER_ROW
                row       = row_offset + row_local

                node = SkillNodeWidget(
                    code,
                    get_level=lambda c, lv=levels: lv.get(c, 0),
                    max_level=max_lv,
                    inc_cb=inc_cb,
                    dec_cb=dec_cb,
                )
                self.grid.addWidget(node, row, col)
                self.code2widget[code] = node
                placed.add(code)

            # 這個群組使用的總行數 = max_local_row + 1
            row_offset += max_local_row + 1

            # ---------- 2-2) 群組之間插分隔線 ----------
            if idx_group < len(groups) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFrameShadow(QFrame.Sunken)
                line.setStyleSheet("color: #666;")
                self.grid.addWidget(line, row_offset, 0, 1, SKILL_PER_ROW)
                row_offset += 1

        # ---------- 3) 把沒出現在任何職業頁面裡的技能丟最後 ----------
        remaining = [code for code in skill_map_job.keys() if code not in placed]
        if remaining:
            if row_offset > 0:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setFrameShadow(QFrame.Sunken)
                line.setStyleSheet("color: #666;")
                self.grid.addWidget(line, row_offset, 0, 1, SKILL_PER_ROW)
                row_offset += 1

            for i, code in enumerate(sorted(remaining)):
                info   = skill_map_job[code]
                max_lv = info.get("MaxLevel", 0)
                row    = row_offset + i // SKILL_PER_ROW
                col    = i % SKILL_PER_ROW

                node = SkillNodeWidget(
                    code,
                    get_level=lambda c, lv=levels: lv.get(c, 0),
                    max_level=max_lv,
                    inc_cb=inc_cb,
                    dec_cb=dec_cb,
                )
                self.grid.addWidget(node, row, col)
                placed.add(code)



    def refresh_levels(self, skill_map_job, levels):
        for i in range(self.grid.count()):
            w = self.grid.itemAt(i).widget()
            if isinstance(w, SkillNodeWidget):
                # ★ 每次刷新時更新 get_level 來源
                w.get_level = lambda c, lv=levels: lv.get(c, 0)

                info = skill_map_job.get(w.code, {})
                w.max_level = info.get("MaxLevel", 0)
                w.update_display()


# =========================================================
# 主視窗
# =========================================================
class SkillTreeWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("RO 技能表")
        self.resize(900, 600)
        # ★★ 新增：關閉視窗後回傳資料的 callback ★★
        self.on_close_callback = None

        self.current_job_key = None
        self.current_skill_map_job = {}
        self.current_levels = {}
        # 新增：反向依賴表  { 前置技能code -> [依賴它的技能code, ...] }
        self.dependents = {}
        # ★ 新增：技能 → 所屬區域，跟各區域點數上限 / 已使用
        self.skill_region = {}           # { skill_code -> region_index }
        self.region_points_max = []      # [每個區塊可用點數]
        self.region_points_used = []     # [目前已用點數]
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 職業選單
        top_row = QHBoxLayout()
        main_layout.addLayout(top_row)
        top_row.addWidget(QLabel("職業："))

        self.job_combo = QComboBox()
        self.job_combo.addItem("-- 請選擇 --", userData=None)
        for jid, job in job_dict.items():
            key = job["id_jobneme"]
            if key not in job_skill_tree_raw:
                continue
            text = f'{job["name"]}' #({key})'
            self.job_combo.addItem(text, userData=key)
        self.job_combo.currentIndexChanged.connect(self.on_job_changed)
        top_row.addWidget(self.job_combo, 1)
        self.job_combo.setEnabled(False)
        self.job_combo.setStyleSheet("color: gray;")  # 看起來像唯讀

        # 滾動區包 SkillTreeGrid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.tree_widget = SkillTreeGrid()
        self.scroll.setWidget(self.tree_widget)
        main_layout.addWidget(self.scroll)

        self.lbl_points = QLabel()
        self.lbl_points.setAlignment(Qt.AlignRight)
        main_layout.addWidget(self.lbl_points)
        self.update_points_label()


    def attach_main_window(self, main_window):
        """註冊主視窗事件以便監聽焦點"""
        self.main_window = main_window
        self.main_window.installEventFilter(self)

    def eventFilter(self, obj, event):
        # 主視窗被啟用（使用者點回主程式 UI）
        if obj == getattr(self, "main_window", None):
            if event.type() == QEvent.WindowActivate:
                self.close()
        return super().eventFilter(obj, event)

    def apply_restored_levels(self):
        if not hasattr(self, "current_levels"):
            return
        if not hasattr(self, "grid"):
            return
    
        for code, lv in self.current_levels.items():
            widget = self.grid.code2widget.get(code)
            if widget:
                widget.force_set_level(lv)

    def get_all_prerequisites(self, code, require_lv=None, out=None):
        """
        遞迴收集所有前置技能及各自需要的最高等級。
        回傳格式: {skill_code: max_required_lv}
        """
        if out is None:
            out = {}
        info = self.current_skill_map_job.get(code, {})
        requires = info.get("Requires", []) or []
        for r in requires:
            pre_code = r.get("Name")
            lv = r.get("Level", 1)
            if not pre_code:
                continue
            # 只記錄最高需求等級
            out[pre_code] = max(out.get(pre_code, 0), lv)
            self.get_all_prerequisites(pre_code, require_lv=lv, out=out)
        return out


    def on_skill_hover(self, code):
        widgets = getattr(self.tree_widget, 'code2widget', {})
        # 先全部隱藏
        for w in widgets.values():
            w.hide_requirement()
        if not code:
            return
        # 取得所有遞迴前置 {code: lv}
        all_requires = self.get_all_prerequisites(code)
        for pre_code, req_lv in all_requires.items():
            widget = widgets.get(pre_code)
            if widget:
                widget.show_requirement(f"+{req_lv}")



    def update_points_label(self):
        # region_points_max, region_points_used 已初始化
        names = ["1轉", "2轉", "3轉", "4轉"] + [f"{i+1}區" for i in range(4, len(self.region_points_max))]

        lefts = []
        total_left = 0
        total_max = 0

        for i, (used, mx) in enumerate(zip(self.region_points_used, self.region_points_max)):
            left = mx - used
            lefts.append(left)
            total_left += left
            total_max += mx

        # 預設最多只顯示到4區，多的你可自行增刪
        txts = []
        for i, left in enumerate(lefts):
            if i < len(names):
                txts.append(f"{names[i]}剩餘: <b>{left}</b> / {self.region_points_max[i]}")
            else:
                txts.append(f"{i+1}區剩餘: <b>{left}</b> / {self.region_points_max[i]}")
        txts.append(f"總剩餘: <b>{total_left}</b> / {total_max}")

        self.lbl_points.setText("　｜　".join(txts))

    # ---- 切換職業 ----
    def on_job_changed(self, idx):
        key = self.job_combo.itemData(idx)
        if key is None:
            self.current_job_key = None
            self.current_skill_map_job = {}
            self.current_levels = {}
            self.dependents = {}
            self.tree_widget.clear()
            return

        self.current_job_key = key
        self.current_skill_map_job = build_job_skill_map(key)
        self.current_levels = {code: 0 for code in self.current_skill_map_job.keys()}

        # 建依賴表（你原本就有）
        self.dependents = {code: [] for code in self.current_skill_map_job.keys()}
        for code, info in self.current_skill_map_job.items():
            for r in info.get("Requires", []) or []:
                parent = r.get("Name")
                if parent in self.dependents:
                    self.dependents[parent].append(code)

        # ★ 取得這條職業線：1轉/2轉/3轉/4轉
        job_chain = get_job_chain(key)

        # ★ 依 job_dict 的 point 建立各區塊點數上限與技能歸屬
        self.setup_point_system(key, job_chain)

        self.tree_widget.set_tree(
            self.current_skill_map_job,
            self.current_levels,
            job_chain,
            inc_cb=self.increase_skill,
            dec_cb=self.decrease_skill,
        )
        self.update_points_label()

    def closeEvent(self, event):
        result = _core_stage19_build_enable_skill_note(
            self.current_levels, skill_code_to_id
        )
        if self.on_close_callback:
            self.on_close_callback(result)
        super().closeEvent(event)




    def setup_point_system(self, job_key: str, job_chain: list[str]):
        """
        依照 job_dict 的 'point' 與 job_chain，建立：
        - self.region_points_max  每個職業區塊可用總點數
        - self.skill_region       每個技能屬於哪一個區塊
        規則：
        - job_chain 例如：['Swordman','Knight','Knight_H','Rune_Knight','Dragon_Knight']
        - job_dict['point'] 例如："49/49/20/49/54"
        - 分組後: ['Swordman'], ['Knight','Knight_H'], ['Rune_Knight'], ['Dragon_Knight']
          -> 各組點數 = 同組職業 point 加總
             => S:49, K+K_H:49+20=69, RK:49, DK:54
        """
        self.skill_region = {}
        self.region_points_max = []
        self.region_points_used = []

        # 找到 job_dict 裡對應的 entry
        job_entry = None
        for _, j in job_dict.items():
            if j.get("id_jobneme") == job_key:
                job_entry = j
                break

        if not job_entry:
            return

        raw_points = job_entry.get("point")
        if not raw_points:
            # 沒設定 point → 不限制
            return

        # 解析 point，可以是 "a/b/c" 或 [a,b,c]
        if isinstance(raw_points, str):
            try:
                pt_values = [int(p) for p in raw_points.split("/") if p.strip()]
            except ValueError:
                pt_values = []
        elif isinstance(raw_points, (list, tuple)):
            pt_values = [int(p) for p in raw_points]
        else:
            pt_values = []

        if not pt_values:
            return

        # job_chain 中各職業的 index
        job_index_map = {name: idx for idx, name in enumerate(job_chain)}

        # 依 job_chain 分組（Knight + Knight_H 算一組）
        groups = split_job_chain_to_groups(job_chain)

        # 1) 算出每個「職業區塊」能用的總點數
        region_points_max = []
        for group in groups:
            total = 0
            for name in group:
                idx = job_index_map.get(name)
                if idx is None:
                    continue
                if idx < len(pt_values):
                    total += pt_values[idx]
            region_points_max.append(total)

        self.region_points_max = region_points_max

        # 2) 建立「技能屬於哪個區塊」
        #    用 skilltreeview.lub 的位置表來判斷技能是哪一轉的技能
        skill_region = {}

        for region_index, group in enumerate(groups):
            for job_name in group:
                pos_map = treeview_positions.get(job_name, {})
                if not pos_map:
                    continue
                for code in pos_map.keys():
                    if code in self.current_skill_map_job:
                        # 同一技能出現在多個職業頁時，維持第一次設定即可
                        skill_region.setdefault(code, region_index)

        # 3) 沒出現在任何職業頁面的技能 → 預設放在最後一個區塊
        default_region = max(0, len(region_points_max) - 1)
        for code in self.current_skill_map_job.keys():
            if code not in skill_region:
                skill_region[code] = default_region

        self.skill_region = skill_region

        # 4) 初始化已用點數
        self.recalc_region_used()


    #自動補滿前置技能
    def auto_fill_prerequisites(self, code: str, max_check_region=None):
        """
        補前置時，**只補目前未滿的最低區塊**（優先補一轉，滿了再補二轉……）
        """
        info = self.current_skill_map_job.get(code)
        if not info:
            return

        if max_check_region is None:
            max_check_region = self.skill_region.get(code, 0)

        requires = info.get("Requires", []) or []

        # 先決定目前還有哪個低區塊沒滿
        self.recalc_region_used()
        min_unfull_region = None
        for region in range(max_check_region):
            if self.region_points_used[region] < self.region_points_max[region]:
                min_unfull_region = region
                break

        for r in requires:
            p_code = r.get("Name")
            req_lv = r.get("Level", 1)
            if not p_code:
                continue
            parent_region = self.skill_region.get(p_code, 0)

            # 只補「最低未滿區塊」的前置
            if min_unfull_region is not None and parent_region == min_unfull_region:
                # 遞迴只補這個區塊
                self.auto_fill_prerequisites(p_code, max_check_region=min_unfull_region+1)
                parent_info = self.current_skill_map_job.get(p_code)
                if not parent_info:
                    continue
                max_lv_parent = parent_info.get("MaxLevel", 0)
                req_lv = min(req_lv, max_lv_parent)
                cur_lv_parent = self.current_levels.get(p_code, 0)
                if cur_lv_parent < req_lv:
                    self.current_levels[p_code] = req_lv
            # 其它區塊不補！





    def recalc_region_used(self):
        """依照目前 self.current_levels 重算各區塊已使用點數"""
        if not self.region_points_max:
            self.region_points_used = []
            return

        used = [0] * len(self.region_points_max)
        for code, lv in self.current_levels.items():
            info = self.current_skill_map_job.get(code, {})
            # ★ 任務學習技能不計入點數消耗
            if info.get("QuestSkill"):
                continue

            region = self.skill_region.get(code)
            if region is None:
                continue
            if 0 <= region < len(used):
                used[region] += lv

        self.region_points_used = used


    def is_region_over_limit(self) -> bool:
        """
        檢查是不是有任何一個區塊超過點數上限。
        有超過就回傳 True。
        """
        if not self.region_points_max:
            return False

        self.recalc_region_used()
        for used, max_pt in zip(self.region_points_used, self.region_points_max):
            if used > max_pt:
                return True
        return False

    def check_points_limit(self) -> bool:
        """
        檢查目前已使用點數是否有超過各區塊上限。
        若有超過，回傳 False；否則 True。
        """
        if not self.region_points_max:
            # 代表沒有設定 point，當作不限制
            return True

        self.recalc_region_used()

        for idx, (used, max_pt) in enumerate(zip(self.region_points_used, self.region_points_max)):
            if used > max_pt:
                # 若要提示可以在這裡加 messagebox
                # QMessageBox.information(self, "點數不足", f"第 {idx+1} 區塊點數不足（{used}/{max_pt}）。")
                return False
        return True


    # ---- 加點----
    def increase_skill(self, code: str, from_widget=None, event=None):
        info = self.current_skill_map_job.get(code)
        if not info:
            return

        # ★ 任務學習技能：禁止用點數加點
        if info.get("QuestSkill"):
            if from_widget:
                pos = from_widget.mapToGlobal(from_widget.rect().center())
                QToolTip.showText(pos, "此技能為任務/靈魂習得，不能用技能點數加點。", from_widget)
            return

        max_lv = info.get("MaxLevel", 0)
        cur_lv = self.current_levels.get(code, 0)
        if cur_lv >= max_lv:
            return

        # 這個技能屬於哪一區（0=一轉, 1=二轉, 2=三轉, 3=四轉...）
        region = self.skill_region.get(code, 0)

        # --------------------------------------------------
        # ① 先算目前每一區已使用點數，找出「第一個沒點滿的區塊」
        #    → 之後自動補前置，只能補到這個區塊為止
        # --------------------------------------------------
        self.recalc_region_used()


        # -----------------------
        # 計算 max_pre_region
        # -----------------------

        # 1) 建立累積需求
        cumulative = []
        running = 0
        for v in self.region_points_max:
            running += v
            cumulative.append(running)

        # 2) 計算目前總使用點數
        total_used = sum(self.region_points_used)

        # 3) 找出目前已解鎖的最高轉職
        max_pre_region = 0
        for i, req in enumerate(cumulative):
            if total_used >= req:
                max_pre_region = i + 1    # +1 因為達成 i 表示可補到下一轉
            else:
                break

        # max_pre_region 現在是補前置的最高轉職 INDEX（0 起算）


        active_region = None  # 第一個還沒滿的區塊
        if self.region_points_max:
            for i, (used, mx) in enumerate(zip(self.region_points_used, self.region_points_max)):
                if used < mx:
                    active_region = i
                    break
            # 全部都滿的情況，就當作最後一區是 active
            if active_region is None:
                active_region = len(self.region_points_max) - 1

        # --------------------------------------------------
        # ② 自動補前置（跨區塊）
        #    規則：只能補到 "min(region, active_region)" 這一區為止
        #    ★ 這樣就能保證：
        #      - 一轉沒滿時，只會補一轉，不會動到二三轉
        #      - 二轉沒滿時，只會補到二轉，不會動到三轉
        # --------------------------------------------------
        all_requires = self.get_all_prerequisites(code)  # { pre_code: req_lv }

        if active_region is not None:
            max_pre_region = min(region, max_pre_region)

        else:
            # 沒有設定 point 的職業，當作不限
            max_pre_region = region

        for pre_code, req_lv in all_requires.items():
            pre_info = self.current_skill_map_job.get(pre_code)
            if not pre_info:
                continue

            pre_region = self.skill_region.get(pre_code, 0)
            # 超過允許補的區塊就跳過（例如一轉沒滿時，二三轉不補）
            if pre_region > max_pre_region:
                continue


            pre_max_lv = pre_info.get("MaxLevel", 0)
            want_lv = min(req_lv, pre_max_lv)
            if self.current_levels.get(pre_code, 0) < want_lv:
                self.current_levels[pre_code] = want_lv


        # --------------------------------------------------
        # ③ 解鎖檢查：
        #    點第 N 區技能 → 前面 0..N-1 區都要點滿，否則不能點本區
        #    （但剛剛補的前置會保留）
        # --------------------------------------------------
        self.recalc_region_used()

        if self.region_points_max and region > 0:
            can_unlock = True
            # 加總模式
            needed = sum(self.region_points_max[:region])
            current = sum(self.region_points_used[:region])
            diff = current - needed

            # 解鎖不足 → 只在不足時顯示提示
            if diff < 0:
                missing_info = []
                # （這裡只列出真正需要補滿的前置區域）
                running = 0
                for i in range(region):
                    running += self.region_points_used[i] - self.region_points_max[i]
                    if running < 0:
                        missing_info.append(f"{i+1}轉還缺{-running}點")

                msg = "、".join(missing_info) + "，無法點本區技能（已先自動補前置）"
                if from_widget:
                    pos = from_widget.mapToGlobal(from_widget.rect().center())
                    QToolTip.showText(pos, msg, from_widget)

                self.tree_widget.refresh_levels(self.current_skill_map_job, self.current_levels)
                self.update_points_label()
                return

        # --------------------------------------------------
        # ④ 前面區塊都點滿之後，才補「同區塊前置」技能
        # --------------------------------------------------
        requires = info.get("Requires", []) or []
        for r in requires:
            pre_code = r.get("Name")
            req_lv = r.get("Level", 1)
            if not pre_code:
                continue

            pre_region = self.skill_region.get(pre_code, 0)
            if pre_region != region:
                continue  # 只處理同區塊的前置

            pre_info = self.current_skill_map_job.get(pre_code)
            if not pre_info:
                continue

            pre_max_lv = pre_info.get("MaxLevel", 0)
            want_lv = min(req_lv, pre_max_lv)
            if self.current_levels.get(pre_code, 0) < want_lv:
                self.current_levels[pre_code] = want_lv

        # --------------------------------------------------
        # ⑤ 最後才真的幫這個技能 +1
        # --------------------------------------------------
        cur_lv = self.current_levels.get(code, 0)
        if cur_lv >= max_lv:
            self.tree_widget.refresh_levels(self.current_skill_map_job, self.current_levels)
            self.update_points_label()
            return

        self.current_levels[code] = cur_lv + 1

        self.recalc_region_used()
        self.tree_widget.refresh_levels(self.current_skill_map_job, self.current_levels)
        self.update_points_label()








    #存在且沒超過 MaxLevel
    def can_increase_skill(self, code: str) -> bool:
        info = self.current_skill_map_job.get(code)
        if not info:
            return False
        cur = self.current_levels.get(code, 0)
        max_lv = info.get("MaxLevel", 0)
        return cur < max_lv


    #連鎖清除不符合前置的技能
    def cascade_invalidate(self, code: str, visited=None):
        """
        某技能等級變低後，檢查其所有後繼技能；
        若不滿足前置要求，該技能歸 0，並且繼續往下一層傳遞。
        """
        if visited is None:
            visited = set()
        if code in visited:
            return
        visited.add(code)

        for dep in self.dependents.get(code, []):
            info = self.current_skill_map_job.get(dep)
            if not info:
                continue

            requires = info.get("Requires", []) or []
            ok = True
            for r in requires:
                p_code = r.get("Name")
                req_lv = r.get("Level", 1)
                if not p_code:
                    continue
                if self.current_levels.get(p_code, 0) < req_lv:
                    ok = False
                    break

            if not ok and self.current_levels.get(dep, 0) > 0:
                # 不符合前置 → 歸 0，並繼續往下清
                self.current_levels[dep] = 0
                self.cascade_invalidate(dep, visited)

    # ---- 減點----
    def decrease_skill(self, code: str):
        info = self.current_skill_map_job.get(code, {})
        if info.get("QuestSkill"):
            # 任務技能不允許用技能點直接減等
            return

        cur = self.current_levels.get(code, 0)
        if cur <= 0:
            return

        # 先自己減 1
        self.current_levels[code] = cur - 1

        # ★ 檢查所有依賴這個技能的後續技能
        self.cascade_invalidate(code)

        # ★ 重新計算各區塊已用點數
        self.recalc_region_used()

        # 更新畫面
        self.tree_widget.refresh_levels(self.current_skill_map_job, self.current_levels)
        self.update_points_label()





# =========================================================
# main
# =========================================================
def main():
    #load_skill_map()       # 讀 skillneme.csv
    load_skill_tree()      # 讀 skill_tree.yml
    load_skill_treeview()  # ★ 新增：讀 skilltreeview.lub

    app = QApplication(sys.argv)
    win = SkillTreeWindow()
    win.show()
    sys.exit(app.exec())



if __name__ == "__main__":
    main()
