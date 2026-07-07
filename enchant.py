
import sys
import os
import re
from PySide6.QtWidgets import (
    QApplication, QWidget, QListWidget, QTableWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QTableWidgetItem, QLabel, QTabWidget , QMessageBox,
    QPushButton, QInputDialog
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView
from PySide6.QtWidgets import QToolTip
from PySide6.QtGui import QCursor
from PySide6.QtGui import QFontMetrics
from PySide6.QtCore import QPoint
# ---------------------------------------------------------------
# 讀檔：自動嘗試多種編碼
# ---------------------------------------------------------------
def read_text_with_fallback(path):
    encodings = ["utf-8", "utf-8-sig", "cp950", "big5", "cp936", "cp932", "latin1"]
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                data = f.read()
            print(f"[INFO] 使用 {enc} 讀取成功：{path}")
            return data
        except Exception:
            continue

    with open(path, "rb") as f:
        data = f.read().decode("latin1", errors="replace")
    print(f"[WARN] 所有編碼失敗，改用 latin1+replace：{path}")
    return data




# ---------------------------------------------------------------
# 解析 ItemDBNameTbl.lua  => {"DBName": item_id}
# ---------------------------------------------------------------
def parse_itemdb_name_tbl(filename):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ 找不到檔案：{filename}")
        return {}
    except UnicodeDecodeError:
        with open(filename, "rb") as f:
            content = f.read().decode("latin1", errors="replace")

    # 支援  Name = 123  或  ["Name"] = 123
    pattern = r'(?:\["([^"]+)"\]|([A-Za-z0-9_]+))\s*=\s*(\d+)'
    name_to_id = {}

    for m in re.finditer(pattern, content):
        key1, key2, val = m.groups()
        key = key1 or key2
        if key:
            name_to_id[key] = int(val)

    print(f"[INFO] ItemDBNameTbl 解析完成，共 {len(name_to_id)} 筆")
    return name_to_id


# ---------------------------------------------------------------
# 解析 EnchantList.lua
# parsed 結構：
#   { table_id: {
#       "slot_order": [3,2,1],
#       "target_items": ["N_Avenger_Cape_TW", ...],
#       "slots": {
#          slot_id: {
#             "enchants": [(grade, name, rate), ...],
#             "perfect":  [{"name": n, "rate": r, "materials": [...]}, ...]
#          }
#       }
#   } }
# ---------------------------------------------------------------
def parse_enchant_list(filename):
    if not os.path.exists(filename):
        print("❌ 找不到檔案", filename)
        return {}

    content = read_text_with_fallback(filename)

    # 找出所有 CreateEnchantInfo
    tables = re.split(r"Table\[(\d+)\]\s*=\s*CreateEnchantInfo\(\s*\)", content)
    if len(tables) <= 1:
        print("⚠ 解析不到任何 Table")
        return {}

    parsed = {}

    # 先逐 Table 把 slot_order / target_items / reset 抓出來
    for i in range(1, len(tables), 2):
        tid = int(tables[i])
        body = tables[i + 1]

        parsed[tid] = {
            "slot_order": [],
            "target_items": [],
            "reset": None,
            "slots": {}
        }

        # SetSlotOrder(3, 2, 1)
        sso = re.search(r"SetSlotOrder\((.*?)\)", body)
        if sso:
            nums = [
                int(x.strip()) for x in sso.group(1).split(",")
                if x.strip().isdigit()
            ]
            parsed[tid]["slot_order"] = nums

        # AddTargetItem("xxx")
        targets = re.findall(r'AddTargetItem(?:_Duplicate)?\("([^"]+)"\)', body)
        parsed[tid]["target_items"] = targets

        # SetReset(true, 80000, 0, {"Silvervine", 3})
        rst = re.search(
            r"SetReset\((true|false)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*((?:\{.*?\})+))?",
            body,
            re.DOTALL
        )
        if rst:
            enable = rst.group(1) == "true"
            rr = int(rst.group(2))
            er = int(rst.group(3))

            mats = []
            raw = rst.group(4)
            if raw:
                mats = [
                    (a, int(b))
                    for a, b in re.findall(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}', raw)
                ]
            parsed[tid]["reset"] = {
                "enable": enable,
                "reset_rate": rr,
                "enchant_rate": er,
                "materials": mats,
            }

    # --------------------------------------------------
    # 解析 SetRequire (支援多材料)
    # --------------------------------------------------
    all_requires = re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:SetRequire'
        r'\(\s*(\d+)(?:\s*,\s*((?:\{[^}]+\}\s*,?\s*)*))?\s*\)',
        content
    )

    for tid, sid, zeny, mats_raw in all_requires:
        tid = int(tid)
        sid = int(sid)
        zeny = int(zeny)

        if tid not in parsed:
            continue

        parsed[tid]["slots"].setdefault(sid, {
            "enchants": [],
            "perfect": [],
            "upgrade": [],
            "perfect_upgrade": [],
            "random_upgrade": []
        })

        mats_raw = mats_raw or ""
        mats = re.findall(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}', mats_raw)
        materials = [(m_name, int(m_cnt)) for m_name, m_cnt in mats]

        parsed[tid]["slots"][sid]["require"] = {
            "zeny": zeny,
            "materials": materials
        }



    # --------------------------------------------------
    # 全檔掃描 SetEnchant
    # --------------------------------------------------
    all_enchants = re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:SetEnchant\(\s*(\d+)\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*\)',
        content
    )

    for tid, sid, grade, name, rate in all_enchants:
        tid = int(tid)
        sid = int(sid)
        grade = int(grade)
        rate = int(rate)

        if tid not in parsed:
            continue

        if sid not in parsed[tid]["slots"]:
            parsed[tid]["slots"][sid] = {
                "enchants": [],
                "perfect": []
            }

        parsed[tid]["slots"][sid]["enchants"].append((grade, name, rate))

    # --------------------------------------------------
    # 全檔掃描 AddPerfectEnchant
    # --------------------------------------------------
    all_perfects = re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:AddPerfectEnchant'
        r'\(\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*((?:\{.*?\})+)\)',
        content,
        re.DOTALL
    )

    for tid, sid, name, zeny, mats_raw in all_perfects:
        tid = int(tid)
        sid = int(sid)
        zeny = int(zeny)

        if tid not in parsed:
            continue

        if sid not in parsed[tid]["slots"]:
            parsed[tid]["slots"][sid] = {
                "enchants": [],
                "perfect": []
            }

        mats = re.findall(r'\{\s*"([^"]*)"\s*,\s*(\d+)\s*\}', mats_raw)
        materials = [(m_name, int(m_cnt)) for m_name, m_cnt in mats]

        parsed[tid]["slots"][sid]["perfect"].append({
            "name": name,
            "zeny": zeny,
            "materials": materials
        })

    # --------------------------------------------------
    # 全檔掃描 AddUpgradeEnchant
    # --------------------------------------------------
    all_upgrades = re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:AddUpgradeEnchant'
        r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*((?:\{.*?\})+)\)',
        content,
        re.DOTALL
    )

    for tid, sid, src, dst, zeny, mats_raw in all_upgrades:
        tid = int(tid)
        sid = int(sid)
        zeny = int(zeny)

        if tid not in parsed:
            continue

        if sid not in parsed[tid]["slots"]:
            parsed[tid]["slots"][sid] = {
                "enchants": [],
                "perfect": [],
                "upgrade": []
            }
        else:
            parsed[tid]["slots"][sid].setdefault("upgrade", [])

        # 解析材料
        mats = re.findall(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}', mats_raw)
        materials = [(m_name, int(m_cnt)) for m_name, m_cnt in mats]

        parsed[tid]["slots"][sid]["upgrade"].append({
            "from": src,
            "to": dst,
            "zeny": zeny,
            "materials": materials
        })

    # --------------------------------------------------
    # 完美升階 AddPerfectUpgradeEnchant
    # --------------------------------------------------
    all_perfect_upgrades = re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:AddPerfectUpgradeEnchant'
        r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*((?:\{.*?\})+)\)',
        content,
        re.DOTALL
    )

    for tid, sid, src, dst, zeny, mats_raw in all_perfect_upgrades:
        tid = int(tid)
        sid = int(sid)
        zeny = int(zeny)

        if tid not in parsed:
            continue

        if sid not in parsed[tid]["slots"]:
            parsed[tid]["slots"][sid] = {
                "enchants": [],
                "perfect": [],
                "upgrade": [],
                "perfect_upgrade": [],
                "random_upgrade": []
            }
        else:
            parsed[tid]["slots"][sid].setdefault("perfect_upgrade", [])

        # 材料
        mats = re.findall(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}', mats_raw)
        materials = [(m_name, int(m_cnt)) for m_name, m_cnt in mats]

        parsed[tid]["slots"][sid]["perfect_upgrade"].append({
            "from": src,
            "to": dst,
            "zeny": zeny,
            "materials": materials
        })
    # --------------------------------------------------
    # 解析 SetRandomUpgradeRequire
    # --------------------------------------------------
    all_random_require = re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:SetRandomUpgradeRequire'
        r'\(\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*((?:\{[^}]+\}\s*,?\s*)+)\)',
        content
    )

    for tid, sid, src, zeny, mats_raw in all_random_require:
        tid = int(tid)
        sid = int(sid)
        zeny = int(zeny)

        if tid not in parsed:
            continue

        parsed[tid]["slots"].setdefault(sid, {
            "enchants": [],
            "perfect": [],
            "upgrade": [],
            "perfect_upgrade": [],
            "random_upgrade": []
        })

        # 多組材料解析
        mats = re.findall(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}', mats_raw)
        materials = [(m_name, int(m_cnt)) for m_name, m_cnt in mats]

        parsed[tid]["slots"][sid].setdefault("random_require", {})

        parsed[tid]["slots"][sid]["random_require"][src] = {
            "zeny": zeny,
            "materials": materials
        }
    # --------------------------------------------------
    # 機率升階 AddRandomUpgradeEnchant
    # --------------------------------------------------
    all_random_upgrades = re.findall(
        r'Table\[(\d+)\]\.Slot\[(\d+)\]\:AddRandomUpgradeEnchant'
        r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*\)',
        content
    )

    for tid, sid, src, dst, rate in all_random_upgrades:
        tid = int(tid)
        sid = int(sid)
        rate = int(rate)

        if tid not in parsed:
            continue

        if sid not in parsed[tid]["slots"]:
            parsed[tid]["slots"][sid] = {
                "enchants": [],
                "perfect": [],
                "upgrade": [],
                "perfect_upgrade": [],
                "random_upgrade": []
            }
        else:
            parsed[tid]["slots"][sid].setdefault("random_upgrade", [])

        parsed[tid]["slots"][sid]["random_upgrade"].append({
            "from": src,
            "to": dst,
            "rate": rate,   # 這個才是真的機率
            "zeny": parsed[tid]["slots"][sid]
                .get("random_require", {})
                .get(src, {})
                .get("zeny", 0),
            "materials": parsed[tid]["slots"][sid]
                .get("random_require", {})
                .get(src, {})
                .get("materials", [])
        })






    print(f"✅ 完成解析，共 {len(parsed)} 組 Table")
    return parsed


# ============================================================
# PySide6 UI
# ============================================================
from PySide6.QtWidgets import (
    QWidget, QListWidget, QTableWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QLabel, QTabWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt


class EnchantUI(QWidget):
    def __init__(self, enchant_data, item_data, itemdb, main_window=None):
        super().__init__()

        self.parsed = enchant_data        # EnchantList 解析結果
        self.items = item_data           # iteminfo_new
        self.itemdb = itemdb             # ItemDBNameTbl
        self.main_window = main_window   # 主視窗參考（供套用至裝備設定）
        self.current_tid = None          # 目前選取裝備的 table_id

        self.setWindowTitle("Enchant Viewer")
        layout = QHBoxLayout(self)

        # ==============================
        # 左區域（搜尋欄 + 裝備列表）
        # ==============================
        left_box = QVBoxLayout()
        layout.addLayout(left_box)

        # ▶ 搜尋欄
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜尋裝備名稱...")
        left_box.addWidget(self.search_box)

        # ▶ 裝備列表
        self.list_items = QListWidget()
        left_box.addWidget(self.list_items)

        # ==============================
        # 右：附魔資訊（套用按鈕 + Tab）
        # ==============================
        right_box = QVBoxLayout()
        layout.addLayout(right_box)

        self.apply_button = QPushButton("套用至裝備設定")
        self.apply_button.clicked.connect(self.apply_to_equipment_setting)
        right_box.addWidget(self.apply_button)

        self.tabs = QTabWidget()
        right_box.addWidget(self.tabs)

        # -----------------------------------------------------------
        # 建立：裝備名稱 → 所屬 Enchant Table 映射
        # -----------------------------------------------------------
        self.all_target_items = {}  # key: 顯示名, value: table_id

        for tid, data in self.parsed.items():
            for raw_name in data["target_items"]:
                disp = self.resolve_item_name(raw_name)
                self.all_target_items[disp] = tid

        # 顯示所有裝備
        #self.full_item_list = sorted(self.all_target_items.keys())
        self.full_item_list = sorted(
        self.all_target_items.keys(),
        key=lambda name: (self.all_target_items[name], name)
    )
        self.refresh_item_list("")
        self.adjust_left_list_width()

        # 綁定搜尋事件
        self.search_box.textChanged.connect(self.refresh_item_list)

        # 點選裝備
        self.list_items.currentTextChanged.connect(self.select_equipment)


    def show_materials(self, row, col):
        tab_index = self.tabs.currentIndex()
        tab_widget = self.tabs.widget(tab_index)

        table = tab_widget.findChild(QTableWidget)
        if not table:
            return

        item = table.item(row, 1)
        if not item:
            return

        data = item.data(Qt.UserRole)
        if not data:
            return

        # ---------------------------------------------------------
        # 裝備名稱
        # ---------------------------------------------------------
        equip_name = self.list_items.currentItem().text()

        # ---------------------------------------------------------
        # 附魔類型
        # ---------------------------------------------------------
        type_map = {
            "enchant": "機率附魔",
            "perfect": "指定附魔",
            "upgrade": "指定升階",
            "perfect_upgrade": "指定升階",
            "random_upgrade": "機率升階",
        }
        type_text = type_map.get(data["type"], "附魔")

        # ---------------------------------------------------------
        # 附魔名稱
        # ---------------------------------------------------------
        if data["type"] in ("upgrade", "perfect_upgrade", "random_upgrade"):
            # 升階：from → to
            src = self.resolve_item_name(data["from"])
            dst = self.resolve_item_name(data["to"])
            enchant_name = f"{src} → {dst}"
        else:
            enchant_name = self.resolve_item_name(item.text())

        # ---------------------------------------------------------
        # 機率（沒有 rate = 100%）
        # ---------------------------------------------------------
        if "rate" in data:
            value = data["rate"] / 1000
            rate_text = f"{value:.3f}".rstrip("0").rstrip(".")
            rate_str = f"{rate_text}%"
        else:
            rate_str = "100%"

        # ---------------------------------------------------------
        # 收集材料
        # ---------------------------------------------------------
        mlist = []

        tid = self.all_target_items[equip_name]
        info = self.parsed[tid]
        slot_order = list(reversed(info["slot_order"]))
        sid = slot_order[tab_index]
        slot_info = info["slots"].get(sid)

        # 只有機率附魔才加 SetRequire
        if data["type"] == "enchant" and slot_info and "require" in slot_info:
            req = slot_info["require"]

            if req.get("zeny", 0) > 0:
                mlist.append(("Zeny", req["zeny"]))

            for name, cnt in req.get("materials", []):
                mlist.append((self.resolve_item_name(name), cnt))

        # 各類附魔 / 升階自己的金額
        if data.get("zeny", 0) > 0:
            mlist.append(("Zeny", data["zeny"]))

        # 加上自身材料
        for name, cnt in data.get("materials", []):
            mlist.append((self.resolve_item_name(name), cnt))

        # ---------------------------------------------------------
        # 組 Tooltip 文字（符合你要的格式）
        # ---------------------------------------------------------
        msg = f"裝備名稱：{equip_name}\n"
        msg += f"【{type_text}】 {enchant_name} （機率 {rate_str}）\n\n"

        if not mlist:
            msg += "此裝備無需任何材料。"
        else:
            msg += "附魔材料：\n"
            for name, cnt in mlist:
                if name == "Zeny":
                    msg += f"● {name}: {cnt:,}\n"
                else:
                    msg += f"● {name} × {cnt}\n"

        msg = msg.rstrip()

        # ---------------------------------------------------------
        # 顯示 Tooltip
        # ---------------------------------------------------------
        pos = QCursor.pos() + QPoint(10, -10)
        QToolTip.showText(pos, msg, table)




    def adjust_left_list_width(self):
        fm = QFontMetrics(self.list_items.font())
        max_width = 0

        for name in self.full_item_list:
            w = fm.horizontalAdvance(name)
            if w > max_width:
                max_width = w

        # 加上捲軸、邊框的空間（大約）
        max_width += 40

        self.list_items.setMinimumWidth(max_width)
        self.list_items.setMaximumWidth(max_width)
        self.search_box.setMinimumWidth(max_width)
        self.search_box.setMaximumWidth(max_width)
        

    # ==============================
    # 裝備名稱解析（DBName -> id -> 顯示名）
    # ==============================
    def resolve_item_name(self, key: str) -> str:
        display = key

        # ① DBName → item_id → 中文名
        item_id = self.itemdb.get(key)
        if item_id is not None:
            item_info = self.items.get(item_id)
            if item_info:
                return item_info["name"]

        # ② kr_name
        for info in self.items.values():
            if info["kr_name"] == key:
                return info["name"]

        return display

    # ==============================
    # 附魔能力說明解析（DBName -> id -> description）
    # ==============================
    def resolve_item_description(self, key: str) -> str:
        """回傳該附魔物品的能力說明（多行以換行合併）；查無回空字串。"""
        item_info = None

        # ① DBName → item_id → 物品
        item_id = self.itemdb.get(key)
        if item_id is not None:
            item_info = self.items.get(item_id)

        # ② kr_name 備援
        if item_info is None:
            for info in self.items.values():
                if info.get("kr_name") == key:
                    item_info = info
                    break

        if not item_info:
            return ""

        desc_lines = item_info.get("description") or []
        cleaned = [line.strip() for line in desc_lines if line and line.strip()]
        return "\n".join(cleaned)

    def _make_desc_item(self, key: str) -> QTableWidgetItem:
        """建立「能力說明」欄的格子，內容為附魔物品說明，並設 tooltip。"""
        desc = self.resolve_item_description(key)
        cell = QTableWidgetItem(desc)
        if desc:
            cell.setToolTip(desc)
        return cell

    # ==============================
    # 搜尋 + 重新填入列表
    # ==============================
    def refresh_item_list(self, text):
        text = text.strip().lower()
        self.list_items.clear()

        for name in self.full_item_list:
            if text in name.lower():  # 部分比對
                self.list_items.addItem(name)

    # ==============================
    # 選擇裝備
    # ==============================
    def select_equipment(self, equip_name: str):
        if not equip_name:
            return

        tid = self.all_target_items.get(equip_name)
        if tid is None:
            return

        self.load_all_slots_tabs(tid)

    # ==============================
    # 顯示該 table 所有 Slots 附魔
    # ==============================
    def load_all_slots_tabs(self, tid):
        self.tabs.clear()
        self.current_tid = tid

        info = self.parsed.get(tid)
        if not info:
            return

        slot_name_map = {
            0: "第一洞",
            1: "第二洞",
            2: "第三洞",
            3: "第四洞",
        }

        for sid in reversed(info["slot_order"]):
            tab = QWidget()
            v = QVBoxLayout(tab)

            table = QTableWidget()
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels(["Grade", "Enchant", "機率 (%)", "能力說明"])
            table.verticalHeader().setVisible(False)
            table.setWordWrap(True)
            # 列高自動貼合內容，讓多行能力說明完整顯示（不再以 ... 截斷）
            table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            table.cellClicked.connect(self.show_materials)


            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Fixed)
            header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QHeaderView.Fixed)
            header.setSectionResizeMode(3, QHeaderView.Stretch)
            header.resizeSection(0, 80)
            header.resizeSection(2, 70)

            v.addWidget(table)

            title = slot_name_map.get(sid, f"第{sid}洞")
            self.tabs.addTab(tab, title)

            slot_info = info.get("slots", {}).get(sid)
            if not slot_info:
                continue

            enchants = slot_info.get("enchants", [])
            perfects = slot_info.get("perfect", [])
            upgrades = slot_info.get("upgrade", [])
            perfect_upgrades = slot_info.get("perfect_upgrade", [])
            random_upgrades = slot_info.get("random_upgrade", [])

            total_rows = (
                len(enchants) +
                len(perfects) +
                len(upgrades) +
                len(perfect_upgrades) +
                len(random_upgrades)
            )
            table.setRowCount(total_rows)

            row = 0

            # --------------------------------------------------
            # 合併一般附魔：只看名稱 + 機率，不看 Grade
            # --------------------------------------------------
            merged = {}  # key = (name, rate) → value = True

            for grade, name, rate in enchants:
            #     key = (name, rate)
            #     merged[key] = True  # 重複會自動覆蓋

            # # 寫入表格
            # for (name, rate) in merged.keys():
                table.setItem(row, 0, QTableWidgetItem("機率附魔"))  # 統一名稱
                item = QTableWidgetItem(self.resolve_item_name(name))
                item.setData(Qt.UserRole, {
                    "type": "enchant",
                    "name": name,
                    "rate": rate 
                })
                table.setItem(row, 1, item)
                table.setItem(row, 2, QTableWidgetItem(f"{rate/1000:.3f}"))
                value = rate / 1000
                text = f"{value:.3f}".rstrip('0').rstrip('.')
                table.setItem(row, 2, QTableWidgetItem(f"{text}%"))
                table.setItem(row, 3, self._make_desc_item(name))
                row += 1


            # 完美附魔
            for p in perfects:
                table.setItem(row, 0, QTableWidgetItem("指定附魔"))
                item = QTableWidgetItem(self.resolve_item_name(p["name"]))
                item.setData(Qt.UserRole, {
                    "type": "perfect",
                    "name": p["name"],
                    "zeny": p.get("zeny", 0),
                    "materials": p["materials"],
                })
                table.setItem(row, 1, item)

                table.setItem(row, 2, QTableWidgetItem("100%"))
                table.setItem(row, 3, self._make_desc_item(p["name"]))
                row += 1

            # 升階 目前沒有物品會附魔失敗，都先寫100%
            for up in upgrades:
                src = self.resolve_item_name(up["from"])
                dst = self.resolve_item_name(up["to"])
                table.setItem(row, 0, QTableWidgetItem("指定升階"))
                item = QTableWidgetItem(f"{src} → {dst}")
                item.setData(Qt.UserRole, {
                    "type": "upgrade",
                    "from": up["from"],
                    "to": up["to"],
                    "zeny": up.get("zeny", 0),
                    "materials": up["materials"],
                })
                table.setItem(row, 1, item)

                table.setItem(row, 2, QTableWidgetItem("100%"))#(f"{up['rate']/1000:.3f}"))
                table.setItem(row, 3, self._make_desc_item(up["to"]))

                row += 1

            # 完美升階
            for up in perfect_upgrades:
                src = self.resolve_item_name(up["from"])
                dst = self.resolve_item_name(up["to"])
                table.setItem(row, 0, QTableWidgetItem("指定升階"))
                item = QTableWidgetItem(f"{src} → {dst}")
                item.setData(Qt.UserRole, {
                    "type": "perfect_upgrade",
                    "from": up["from"],
                    "to": up["to"],
                    "zeny": up.get("zeny", 0),
                    "materials": up.get("materials", [])
                })
                table.setItem(row, 1, item)
                table.setItem(row, 2, QTableWidgetItem("100%"))
                table.setItem(row, 3, self._make_desc_item(up["to"]))
                row += 1

            # 機率升階
            for up in random_upgrades:
                src = self.resolve_item_name(up["from"])
                dst = self.resolve_item_name(up["to"])
                table.setItem(row, 0, QTableWidgetItem("機率升階"))
                item = QTableWidgetItem(f"{src} → {dst}")
                item.setData(Qt.UserRole, {
                    "type": "random_upgrade",
                    "from": up["from"],
                    "to": up["to"],
                    "rate": up["rate"],
                    "zeny": up.get("zeny", 0),
                    "materials": up.get("materials", [])
                })
                table.setItem(row, 1, item)

                #table.setItem(row, 2, QTableWidgetItem(f"{up['rate']/1000:.3f}"))
                value = up['rate'] / 1000
                text = f"{value:.3f}".rstrip('0').rstrip('.')
                table.setItem(row, 2, QTableWidgetItem(f"{text}%"))
                table.setItem(row, 3, self._make_desc_item(up["to"]))
                row += 1

    # ==============================
    # 套用選取附魔至主視窗裝備設定（對應部位由使用者選）
    # ==============================
    def apply_to_equipment_setting(self):
        if self.main_window is None:
            QMessageBox.warning(self, "無法套用", "此視窗未連結主程式，無法套用至裝備設定。")
            return

        # 需已選取裝備
        current_equip_item = self.list_items.currentItem()
        if not current_equip_item or self.current_tid is None:
            QMessageBox.information(self, "提示", "請先在左側選取一件裝備。")
            return

        # 取得目前分頁 table 與選取列
        tab_index = self.tabs.currentIndex()
        if tab_index < 0:
            QMessageBox.information(self, "提示", "請先選取一個附魔洞分頁。")
            return

        tab_widget = self.tabs.widget(tab_index)
        table = tab_widget.findChild(QTableWidget) if tab_widget else None
        if table is None or table.currentRow() < 0:
            QMessageBox.information(self, "提示", "請先在附魔列表中選取一列附魔。")
            return

        row = table.currentRow()
        cell = table.item(row, 1)
        data = cell.data(Qt.UserRole) if cell else None
        if not data:
            QMessageBox.information(self, "提示", "此列沒有可套用的附魔資料。")
            return

        # 洞號 sid（= 卡片 index），與 show_materials 一致
        info = self.parsed.get(self.current_tid, {})
        slot_order = list(reversed(info.get("slot_order", [])))
        if tab_index >= len(slot_order):
            QMessageBox.information(self, "提示", "無法辨識目前附魔洞。")
            return
        sid = slot_order[tab_index]

        # 附魔名（升階類用 to，其餘用 name）
        if data["type"] in ("upgrade", "perfect_upgrade", "random_upgrade"):
            enchant_name = self.resolve_item_name(data["to"])
        else:
            enchant_name = self.resolve_item_name(data["name"])

        equip_name = current_equip_item.text()

        # 部位選單（只列可放卡片的部位）
        parts = self.main_window.get_enchant_target_parts()
        if not parts:
            QMessageBox.warning(self, "無法套用", "找不到可套用的裝備部位。")
            return

        # 記憶上一次選擇（存在主視窗，僅當前程序有效）
        last_part = getattr(self.main_window, "last_enchant_target_part", None)
        default_index = parts.index(last_part) if last_part in parts else 0

        part_name, ok = QInputDialog.getItem(
            self, "選擇部位",
            f"將「{equip_name}」與附魔「{enchant_name}」套用至：",
            parts, default_index, False
        )
        if not ok or not part_name:
            return

        applied = self.main_window.apply_enchant_to_equipment(
            part_name, equip_name, sid, enchant_name
        )
        if applied:
            QMessageBox.information(
                self, "已套用",
                f"已套用至「{part_name}」\n裝備：{equip_name}\n第{sid + 1}洞卡片：{enchant_name}"
            )
        else:
            QMessageBox.warning(self, "套用失敗", f"無法套用至「{part_name}」。")



# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------
def main():
    app = QApplication(sys.argv)

    # base_dir = os.path.dirname(os.path.abspath(__file__))
    # item_path = os.path.join(base_dir, "data", "iteminfo_new.lua")
    # enchant_path = os.path.join(base_dir, "data", "EnchantList.lua")
    # itemdb_path = os.path.join(base_dir, "data", "ItemDBNameTbl.lua")

    # iteminfo = parse_lub_file(item_path)
    # enchant = parse_enchant_list(enchant_path)
    # itemdb = parse_itemdb_name_tbl(itemdb_path)

    # ui = EnchantUI(enchant, iteminfo, itemdb)
    # ui.resize(900, 600)
    # ui.show()
    # sys.exit(app.exec())


if __name__ == "__main__":
    main()
