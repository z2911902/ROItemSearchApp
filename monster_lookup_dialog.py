# monster_lookup_dialog.py
import json
from pathlib import Path
# === STAGE 18 DESKTOP SHARED MONSTER CORE ===
from ro_core import (
    stage18_decode_monster_element as _core_stage18_decode_monster_element,
    stage18_load_monster_presets as _core_stage18_load_monster_presets,
    stage18_parse_monster_payload as _core_stage18_parse_monster_payload,
)
import requests

from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QLabel, QMessageBox
)
from PySide6.QtWidgets import QComboBox 
# ================= monster =================
MONSTERS_FILE = Path("data","monsters.json")
MONSTER_CACHE_DIR = Path("data", "monster")
def cache_path(monster_id: int) -> Path:
    # data/monster/1002.json
    return MONSTER_CACHE_DIR / f"{int(monster_id)}.json"

def load_presets() -> list[dict]:
    return _core_stage18_load_monster_presets(Path("data"))

# ================= config =================
CONFIG_FILE = Path("data","config.json")

def load_api_key_from_config() -> str:
    if not CONFIG_FILE.exists():
        return ""
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("api_key", "")).strip()
    except Exception:
        return ""


# ================= element decode =================
def decode_element(element_code: int):
    return _core_stage18_decode_monster_element(element_code)


# ================= worker =================
class MonsterFetchWorker(QObject):
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, monster_id: int, api_key: str, language="zh-TW"):
        super().__init__()
        self.monster_id = monster_id
        self.api_key = api_key
        self.language = language

    def run(self):
        try:
            # 1) 先讀快取
            MONSTER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cpath = cache_path(self.monster_id)

            if cpath.exists():
                with cpath.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    data["_from_cache"] = True
                self.finished.emit(data)
                return

            # 2) 沒快取才打 API
            if not self.api_key:
                raise Exception("沒有快取，且未設定 API Key")

            url = f"https://www.divine-pride.net/api/database/Monster/{self.monster_id}?apiKey={self.api_key}"
            headers = {"Accept-Language": self.language}
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()

            # 3) 存快取（存原始 JSON）
            try:
                with cpath.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                # 快取寫入失敗不阻擋主要流程
                pass

            self.finished.emit(data)

        except Exception as e:
            self.error.emit(str(e))


# ================= dialog =================
class MonsterLookupDialog(QDialog):
    """
    使用方式（在主程式）：
        from monster_lookup_dialog import MonsterLookupDialog
        dlg = MonsterLookupDialog(self)
        dlg.monsterSelected.connect(self.apply_monster_to_main_ui)
        dlg.exec()
    """
    monsterSelected = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("怪物查詢")
        self.setModal(True)

        self._last_data = None

        # -------- UI --------
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("怪物ID")

        self.key_input = QLineEdit()
        self.key_input.setText(load_api_key_from_config())
        self.key_input.setPlaceholderText("API Key")

        self.btn_query = QPushButton("查詢")
        self.btn_query.clicked.connect(self.on_query)

        self.btn_apply = QPushButton("套用")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.on_apply)

        self.status = QLabel("請輸入怪物ID")

        self.name_preview = QLineEdit()
        self.name_preview.setReadOnly(True)
        self.preset_box = QComboBox()
        self.preset_box.addItem("（選擇預設怪物）", None)

        for m in load_presets():
            # 顯示名稱，data 存 id
            self.preset_box.addItem(m["name"], m["id"])

        self.preset_box.currentIndexChanged.connect(self.on_preset_changed)
        form = QFormLayout()
        form.addRow("預設怪物", self.preset_box)
        form.addRow("怪物 ID", self.id_input)
        #form.addRow("API Key", self.key_input)
        form.addRow("名稱預覽", self.name_preview)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_query)
        btn_row.addWidget(self.btn_apply)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addLayout(btn_row)

    def on_preset_changed(self, _index: int):
        monster_id = self.preset_box.currentData()
        if monster_id is None:
            return
        self.id_input.setText(str(monster_id))

    # -------- logic --------
    def on_query(self):

        try:
            monster_id = int(self.id_input.text())
        except ValueError:
            QMessageBox.warning(self, "錯誤", "怪物ID 必須是數字")
            return

        api_key = self.key_input.text().strip()

        self.status.setText("查詢中...")
        self.btn_query.setEnabled(False)
        self.btn_apply.setEnabled(False)

        self.thread = QThread(self)
        self.worker = MonsterFetchWorker(monster_id, api_key)
        self.thread.started.connect(self.worker.run)

        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)

        # ✅ 這三行是關鍵：錯誤也要結束 thread，不然按「套用」關窗就會爆
        self.worker.error.connect(self.thread.quit)
        self.worker.error.connect(self.worker.deleteLater)
        self.worker.error.connect(self.thread.quit)  #（重複也沒關係，但建議保留一次即可）

        self.thread.finished.connect(self.thread.deleteLater)

        self.worker.finished.connect(self.on_fetched)
        self.worker.error.connect(self.on_error)


        self.thread.start()

    def on_error(self, msg: str):
        self.btn_query.setEnabled(True)
        self.btn_apply.setEnabled(False)   # <<< 重要：錯誤就不允許套用
        self._last_data = None             # <<< 重要：清掉上一次成功資料，避免誤套用
        self.name_preview.clear()
        self.status.setText("查詢失敗")
        QMessageBox.critical(self, "API 錯誤", msg)



    def on_fetched(self, data: dict):
        self.btn_query.setEnabled(True)

        parsed = self.parse_monster(data)
        self._last_data = parsed

        self.name_preview.setText(parsed["name"])
        src = "快取" if data.get("_from_cache") else "API"
        self.status.setText(f"查詢完成（{src}）")
        self.btn_apply.setEnabled(True)

    def on_apply(self):
        if self._last_data:
            self.monsterSelected.emit(self._last_data)
            self.accept()

    # -------- parse --------
    def parse_monster(self, data: dict) -> dict:
        return _core_stage18_parse_monster_payload(data)
