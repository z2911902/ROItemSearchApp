import re
import subprocess
import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from PySide6.QtWidgets import QMessageBox
import os
import json
import importlib.util

# === PURE PYTHON RRF RAW IMPORT (Core shared) ===
# RRFReader 維持獨立；raw -> legacy compatibility text 改由 ro_core 統一維護。
from rrf_reader import RRFReader, RRFError
from ro_core import (
    stage19_build_rrf_import_text as _core_stage19_build_rrf_import_text,
    stage19_build_rrf_desktop_json_from_dump_text as _core_stage19_build_rrf_desktop_json_from_dump_text,
)


def read_rrf_for_app(rrf_path: str):
    """直接讀 RRF，回傳 snapshot + Core 建立的記憶體 compatibility text。"""
    snapshot = RRFReader().read(rrf_path)
    return snapshot, _core_stage19_build_rrf_import_text(snapshot)


# === STAGE 19 DESKTOP SHARED RRF CORE ===
# RRF compatibility adapter 已集中至 ro_core.py，Desktop / Web 共用同一份。
# ======【設定區】======
SHOW_OFFSET = False# 顯示 slot 在 group 內的 offset 位置 False True
SHOW_RAW = False# 顯示 slot 的原始 bytes（每8顆一行）
SHOW_2201 = True# 顯示 2201 slot 卡片解析
SHOW_2301 = True# 顯示 2301 slot 裝備解析
SHOW_2701 = True# 顯示 2701 slot 解析（精煉等級）
SHOW_2D01 = True# 顯示 2D01 slot 附魔解析
SHOW_2B01 = True# 顯示 2B01 slot 裝備階級
SHOW_GROUPS = []#只顯示指定的 group編號，空列表/None代表顯示全部，如 [1,3] 只顯示第1和第3個group
SHOW_GROUP_NAMES = []# 例如 ['頭下', '盾牌'] 只顯示這兩個部位, 空的話全部顯示
SHOW_ONLY_FILLED = True     # 只顯示有資料的部位（group）
SHOW_ONLY_PARSED_SLOTS = True   # 只顯示有解析/開關開啟的 slot
# ======================
#料理組合 自動轉換
EFST_COMBO_RULES = [
    {
        "sources": {241, 242, 243, 244, 245, 246},#活力激發劑
        "target": {1641},
        "block_if_all_present": {1034, 685},  # 其中有一個存在，就不轉
    },
    {
        "sources": {150, 151, 247, 248},#戰神蒂爾之祝福
        "target": {796},
        "block_if_all_present": {},  #
    },
    {
        "sources": {150, 241},#力量棒棒條
        "target": {150, 271},
        "block_if_all_present": {},  #
    },
    {
        "sources": {247, 242},#敏捷棒棒條
        "target": {247, 272},
        "block_if_all_present": {},  #
    },
    #體力棒棒條是回HP%無法寫轉換。
    {
        "sources": {151, 245},#智力棒棒條
        "target": {151, 275},
        "block_if_all_present": {},  #
    },
    {
        "sources": {248, 244},#靈巧棒棒條
        "target": {248, 274},
        "block_if_all_present": {},  #
    },
    {
        "sources": {249, 246},#幸運棒棒條
        "target": {249, 276},
        "block_if_all_present": {},  #
    }
]

GRADE_MAP = {
    0: "N",
    1: "D",
    2: "C",
    3: "B",
    4: "A"
}
GROUP_NAME_MAP = {
    1: '頭下',
    2: '右手(武器)',
    3: '披肩',
    4: '飾品右',
    5: '鎧甲',
    6: '左手(盾牌)',
    7: '鞋子',
    8: '飾品左',
    9: '頭上',
    10: '頭中',
}
Shadow_GROUP_NAME_MAP = {

    1: '服飾頭下',
    2: '影子手套',
    3: '服飾斗篷',
    4: '影子耳環右',
    5: '影子鎧甲',
    6: '影子盾牌',
    7: '影子鞋子',
    8: '影子墬子左',
    9: '服飾頭上',
    10: '服飾頭中',
}
NAME_MAP = {}

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
            print(f"[rrf to app]✓ 載入 {key} 成功")
        except Exception as e:
            print(f"[rrf to app]⚠️ 載入 {key} 失敗，使用預設值：{e}")
            cls.loaded_data[key] = info["default"]

        return cls.loaded_data[key]

    @classmethod
    def reload_all(cls):
        print("[rrf to app]=== 重新載入所有資料來源 ===")

        for key, info in cls.sources.items():
            cls.load(key)

            cb = info["on_reload"]
            if cb and cls.window:
                cb(cls.window)   # 把 window 實體傳進 callback



# 註冊 job_dict
DataRegistry.register(
    key="jobs",
    path="data/job_dict.py",
    var_name="job_dict",
    default={
    0: {"GetPureJob": [0],"id": "","id_jobneme": "","id_jobneme_OL": "","selectskill": "", "name": "", "TJobMaxPoint": [0,0,0,0,0,0,0,0,0,0,0,0],"point":"0"}},    # 你也可以做一個小預設值
    on_reload=lambda win: win.update_combobox()  # 若職業列表要更新
)
DataRegistry.reload_all()
job_dict = jobs = DataRegistry.loaded_data["jobs"]
#job_dict = load_python_dict("data/job_dict.py", "job_dict")#職業job_id


import sys, os
def resource_path(rel_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, rel_path)
    return os.path.join(os.path.abspath("."), rel_path)


# 載入EnumVAR.lua
with open("data/enumvar.lua", "r", encoding="utf-8") as f:
    enum_lua = f.read()

# 解析 EnumVAR：104 -> RACE_DAMAGE_HUMAN
id_to_key = {}
enumvar_pat = re.compile(r'(\w+)\s*=\s*{\s*(\d+)\s*,\s*(\d+)\s*}', re.MULTILINE)
for m in enumvar_pat.finditer(enum_lua):
    key, k1, k2 = m.group(1), int(m.group(2)), int(m.group(3))
    id_to_key[k1] = key
    # 部分表格反著也要支援，像 { 104, 7 } ，附魔ID 104、value 7


# 讀 AddRandomOptionNameTable.lua
with open("data/AddRandomOptionNameTable.lua", "r", encoding="utf-8") as f:
    addopt_lua = f.read()

# EnumVAR.KEY[1] = "中文描述"
key_to_desc = {}
desc_pat = re.compile(r'\[EnumVAR\.([A-Z0-9_]+)\[1\]\]\s*=\s*"([^"]+)"')
for m in desc_pat.finditer(addopt_lua):
    key = m.group(1)  # EnumVAR 名稱
    desc = m.group(2)
    key_to_desc[key] = desc

try:
    with open("data/EnchantName.lua", "r", encoding="utf-8") as f:
        enchant_lua = f.read()
except FileNotFoundError:
    # 找不到檔案時，使用空的硬編碼
    enchant_lua = ""

key_to_jsonfmt = {}
json_pat = re.compile(r'\[EnumVAR\.([A-Z0-9_]+)\[1\]\]\s*=\s*"([^"]+)"')

for m in json_pat.finditer(enchant_lua):
    key = m.group(1)
    fmt = m.group(2)
    key_to_jsonfmt[key] = fmt




def get_enchant_info(enchant_id, value):
    """
    return: (顯示用中文, JSON用格式字串)
    """

    # Step1: 找 enumvar key 名稱
    key = id_to_key.get(enchant_id)
    if not key:
        return ("", "")   # 無附魔 or 不支援 ID

    # Step2: 找中文附魔描述
    desc_fmt = key_to_desc.get(key, "")
    if desc_fmt:
        try:
            desc_text = desc_fmt % value
        except:
            desc_text = f"{desc_fmt} ({value})"
    else:
        desc_text = f"{key} +{value}"

    # Step3: 找 JSON 格式 (AddExtParam...)
    json_fmt = key_to_jsonfmt.get(key, "")
    if json_fmt:
        json_text = json_fmt.replace("%d", str(value))
    else:
        json_text = ""

    return (desc_text, json_text)



# ================================================================
# 你的 iteminfo parser（照你給的保留）
# ================================================================
def parse_lub_file(filename):
    try:
        with open(filename, "r", encoding="utf-8") as file:
            content = file.read()
    except FileNotFoundError:
        QMessageBox.critical(None, "錯誤", f"找不到檔案：{filename}")
        return {}

    item_entries = re.findall(
        r"\[(\d+)\]\s*=\s*{(.*?)}(?=,\s*\[\d+\]|\s*\[\d+\]|\s*$)",
        content,
        re.DOTALL
    )

    parsed_items = {}
    for item_id, body in item_entries:
        try:
            item_id = int(item_id)

            identified_name = re.search(r'(?<!un)identifiedDisplayName\s*=\s*"([^"]+)"', body)
            kr_name = re.search(r'(?<!un)identifiedResourceName\s*=\s*"([^"]+)"', body)
            slot = re.search(r'slotCount\s*=\s*(\d+)', body)

            # 描述
            desc_match = re.search(r'(?<!un)identifiedDescriptionName\s*=\s*{(.*?)}', body, re.DOTALL)
            if desc_match:
                desc_body = desc_match.group(1)
                desc_lines_raw = re.findall(r'"([^"]*)"', desc_body)
                desc_lines = [line.strip() for line in desc_lines_raw]
            else:
                desc_lines = []

            if identified_name and kr_name and slot:
                base_name = identified_name.group(1).strip()
                slot_count = int(slot.group(1))

                display_name = f"{base_name} [{slot_count}]" if slot_count > 0 else base_name

                parsed_items[item_id] = {
                    "name": display_name,
                    "base_name": base_name,
                    "kr_name": kr_name.group(1).strip(),
                    "description": desc_lines,
                    "slot": slot_count
                }

        except:
            pass

    return parsed_items

def parse_equipment_blocks(content):
    import re

    blocks = {}
    pattern = re.compile(r"\[(\d+)\]\s*=\s*{", re.MULTILINE)
    matches = list(pattern.finditer(content))
    total = len(matches)
    #print(f"📦 開始解析裝備區塊，共 {total} 筆資料")

    for i, match in enumerate(matches):
        item_id = int(match.group(1))
        start = match.end()
        end = matches[i+1].start() if i+1 < len(matches) else len(content)

        block_text = content[start:end].strip()

        # 加回完整大括號包裹，確保 block 格式正確
        block_text_full = "{" + block_text.rstrip(",") + "}"

        blocks[item_id] = block_text_full
        #print(f"  → 處理中 {i+1}/{total} 筆", end="\r")
    #print(f"\n✅ 解析完成，共 {len(blocks)} 筆裝備。")
    return blocks


def resolve_name_conflicts(parsed_items, equipment_blocks):
    """
    parsed_items: parse_lub_file() 的結果
    equipment_blocks: parse_equipment_blocks() 的結果
    只對有能力區塊的 itemID 執行名稱重複處理
    """

    # 只取出「有能力」的物品
    affected_items = {
        item_id: parsed_items[item_id]
        for item_id in equipment_blocks.keys()
        if item_id in parsed_items
    }

    # 統計名稱出現次數
    name_count = {}
    for item_id, info in affected_items.items():
        name = info["name"]
        name_count[name] = name_count.get(name, 0) + 1

    # 只有重複名稱需要加 itemID
    for item_id, info in affected_items.items():
        name = info["name"]
        if name_count[name] > 1:
            #print(f"{name}")
            info["name"] = f"{name} (ID:{item_id})"

    # 注意：parsed_items 本身也會被更新（因為 dict 是參考）
    return parsed_items

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




def run_replay_and_dump():
    """
    選擇 RRF 後直接用 Python rrf_reader 解碼。
    為了保持既有 API，仍回傳 (rrf_path, replay_text)，
    但第二個值現在是「記憶體字串」，不是 temp.txt 路徑。
    """
    root = tk.Tk()
    root.withdraw()

    rrf_path = filedialog.askopenfilename(
        title="選擇 RRF 檔案",
        filetypes=[("Ragnarok Replay Files", "*.rrf"), ("All Files", "*.*")]
    )
    try:
        root.destroy()
    except Exception:
        pass

    if not rrf_path:
        print("使用者取消選擇。")
        return None, None

    try:
        print(f"[rrf to app] 直接解析 RRF：{rrf_path}")
        snapshot, replay_text = read_rrf_for_app(rrf_path)
        print(
            f"[rrf to app] ✓ raw 解析完成："
            f"{len(snapshot.packets)} packets / {len(snapshot.chunks)} chunks"
        )
        return rrf_path, replay_text
    except (RRFError, OSError, ValueError) as e:
        print(f"[rrf to app] RRF 解析失敗：{e}")
        try:
            QMessageBox.critical(None, "RRF 解析錯誤", str(e))
        except Exception:
            pass
        return rrf_path, None


#截取技能等級
import string

def is_valid_skill_name(s):
    # 技能名至少 6 個字元，全部由 A~Z、0~9、_ 組成，且必須包含 _
    if len(s) < 3:
        return False
    
    allowed = string.ascii_uppercase + string.digits + "_"
    
    for ch in s:
        if ch not in allowed:
            return False
    
    # 新增：一定要至少有一個 _
    if "_" not in s:
        return False
    
    return True



import re

def parse_skillinfo_list_from_text(content):

    # 專找 packet HEADER_ZC_SKILLINFO_LIST 的 { ... }
    pattern = (
        r"packet\s+HEADER_ZC_SKILLINFO_LIST[\s\S]*?\{"   # 找到 HEADER_ZC_SKILLINFO_LIST 並定位到它的 {
        r"([\s\S]*?)"                                     # 抓裡面內容
        r"^\}\n\s*\n"                                     # 必須以獨立的 } + 換行 + 空行結束
    )

    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        return []

    block = match.group(1)

    hex_list = re.findall(r'\b([0-9A-Fa-f]{2})\b', block)
    n = len(hex_list)

    skills = []
    i = 0

    while i < n - 20:

        if hex_list[i] != "00" and hex_list[i+1] != "00":

            name_start = i

            name_bytes = []
            j = i
            while j < n and hex_list[j] != "00":
                name_bytes.append(hex_list[j])
                j += 1

            try:
                name = bytes.fromhex("".join(name_bytes)).decode("ascii", errors="ignore")
            except:
                name = ""

            if not is_valid_skill_name(name):
                i += 1
                continue

            lvl_pos = name_start - 6
            level = 0
            if lvl_pos >= 0:
                lv_low = int(hex_list[lvl_pos], 16)
                lv_high = int(hex_list[lvl_pos + 1], 16)
                level = lv_high * 256 + lv_low

            skills.append((name, level))

            i = j + 1
        else:
            i += 1

    return skills






def bytes_to_int_le(b):
    return int(''.join(reversed(b)), 16)

import re

def extract_session_stats(filepath=None, *, content=None):
    if content is None:
        if not filepath:
            return {}
        with open(filepath, 'r', encoding='cp950', errors='ignore') as f:
            content = f.read()

    target_fields = [
        "Job", "Level", "JobLevel",
        "Str", "Agi", "Vit", "Int", "Dex", "Luk"
    ]

    results = {}

    # --------------------------
    # 數值類 (4 bytes)
    # --------------------------
    for field in target_fields:
        pat = (
            r"\[Chunk Session\] Unparsed opcode " + field +
            r", Length=4\s+[^\{]*\{([^}]*)\}"
        )
        m = re.search(pat, content, re.DOTALL)
        if not m:
            continue

        block = m.group(1)

        data_bytes = []
        for line in block.splitlines():
            line = line.strip()
            hexes = re.findall(r'\b([0-9A-Fa-f]{2})\b', line)
            if len(hexes) >= 4:
                data_bytes.extend(hexes[-4:])  # 只抓最後 4 bytes

        if len(data_bytes) == 4:
            val = int(''.join(reversed(data_bytes)), 16)
            results[field] = val


    # --------------------------
    # HEADER_ZC_COUPLESTATUS：解析所有封包，取最後更新
    # --------------------------
    pat_couple = r"packet HEADER_ZC_COUPLESTATUS.*?\{([^}]*)\}"
    all_matches = re.findall(pat_couple, content, re.DOTALL)

    # 對照表
    attr_map = {
        0xdb: "POW",
        0xdc: "STA",
        0xdd: "WIS",
        0xde: "SPL",
        0xdf: "CON",
        0xe0: "CRT",
    }

    # 逐筆處理，後出現的會覆蓋前面的
    for block in all_matches:

        # 抓全部 hex bytes
        hex_list = re.findall(r'\b([0-9A-Fa-f]{2})\b', block)
        if len(hex_list) < 8:
            continue

        # 第 3 byte = 屬性 ID（index 2）
        attr_id = int(hex_list[2], 16)

        # 第 7+8 byte = 數值（little-endian）
        low = int(hex_list[6], 16)
        high = int(hex_list[7], 16)
        value = (high << 8) | low

        # 若 ID 有在對照表中 -> 記錄 (後面出現的會覆蓋)
        if attr_id in attr_map:
            results[attr_map[attr_id]] = value

    # --------------------------
    # 新增：Charactername (64 bytes，Big5)
    # --------------------------
    pat_name = (
        r"\[Chunk ReplayData\] Unparsed opcode Charactername, Length=64"
        r".*?Raw hex:[^\{]*\{([^}]*)\}"
    )
    m = re.search(pat_name, content, re.DOTALL)
    if m:
        block = m.group(1)
        hex_list = []

        for line in block.splitlines():
            line = line.strip()
            hexes = re.findall(r'\b([0-9A-Fa-f]{2})\b', line)
            # 每行最多取 16 bytes (正常 hex dump 格式)
            hex_list.extend(hexes)

        # 只取 64 bytes
        hex_list = hex_list[:64]

        # 轉成 bytes
        raw_bytes = bytes(int(h, 16) for h in hex_list)

        # 去除後面 NUL padding
        raw_bytes = raw_bytes.split(b'\x00', 1)[0]

        try:
            name = raw_bytes.decode('big5', errors='ignore')
        except:
            name = ""

        results["Charactername"] = name

    return results



def apply_efst_combo_transform(results, combo_rules):
    if not results:
        return results

    existing_ids = {item["id"] for item in results}
    matched_source_ids = set()
    new_entries = []
    produced_ids = set()

    for rule in combo_rules:
        sources = set(rule["sources"])
        target_spec = rule.get("targets", rule.get("target"))
        block_if_any_present = set(
            rule.get("block_if_any_present", rule.get("block_if_all_present", set()))
        )

        if not sources.issubset(existing_ids):
            continue

        # 只要 block 名單中任一個存在，就擋掉
        if block_if_any_present & existing_ids:
            continue

        if target_spec is None:
            continue

        matched_source_ids.update(sources)

        # target_spec 支援：
        # 1. 單一值: 100
        # 2. set: {100, 101}
        # 3. dict:
        #    {
        #        100: {"name": "...", "descript": [...]},
        #        101: {"name": "...", "descript": [...]}
        #    }
        if isinstance(target_spec, dict):
            iterable = target_spec.items()
        elif isinstance(target_spec, (set, list, tuple)):
            iterable = ((target_id, None) for target_id in target_spec)
        else:
            iterable = ((target_spec, None),)

        for target_id, meta in iterable:
            if target_id in produced_ids or target_id in existing_ids:
                continue

            if isinstance(meta, dict):
                entry = {
                    "id": target_id,
                    "name": meta.get("name", f"COMBO_{'_'.join(map(str, sorted(sources)))}_{target_id}"),
                    "descript": meta.get("descript", [f"由組合 {sorted(sources)} 自動轉換"])
                }
            else:
                entry = {
                    "id": target_id,
                    "name": f"COMBO_{'_'.join(map(str, sorted(sources)))}_{target_id}",
                    "descript": [f"由組合 {sorted(sources)} 自動轉換"]
                }

            new_entries.append(entry)
            produced_ids.add(target_id)

    filtered = [item for item in results if item["id"] not in matched_source_ids]
    filtered.extend(new_entries)
    filtered.sort(key=lambda x: x["id"])
    return filtered

def extract_hex_bytes_from_block(block):
    import re
    hex_list = []

    for line in block.splitlines():
        line = line.strip()
        # 移除前面的位址欄，例如 0000
        line = re.sub(r'^\s*[0-9A-Fa-f]{4,}\s+', '', line)
        hexes = re.findall(r'\b([0-9A-Fa-f]{2})\b', line)
        if hexes:
            hex_list.extend(hexes)

    return hex_list



def extract_efstinfo_values(filepath=None,
                            efst_ids_path="data/EFSTIDs.lua",
                            stateiconinfo_path="data/stateiconinfo.lua",
                            *, content=None):
    """
    來源1：
      [Chunk ...] Unparsed opcode EfstInfo, Length=...
      -> 前2 bytes 為狀態ID (little-endian)

    來源2：
      packet HEADER_ZC_MSG_STATE_CHANGE3
      -> 在 {} 內找 83 09
      -> 後2 bytes = 狀態ID (little-endian)
      -> 再後4 bytes = 施放者AID
      -> 只保留 AID == [Chunk Session] Aid 的封包
    """
    import re

    def read_text_auto(path):
        for enc in ("utf-8-sig", "utf-8", "cp950", "big5"):
            try:
                with open(path, "r", encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue

        with open(path, "r", encoding="big5", errors="replace") as f:
            return f.read()

    def extract_brace_block(text, start_brace_idx):
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

    def to_result(value, id_to_name, name_to_desc):
        efst_name = id_to_name.get(value, f"UNKNOWN_EFST_{value}")
        descript_list = name_to_desc.get(efst_name, [])
        return {
            "id": value,
            "name": efst_name,
            "descript": descript_list
        }

    def append_unique(results, seen_ids, value, id_to_name, name_to_desc):
        if value in seen_ids:
            return
        seen_ids.add(value)
        results.append(to_result(value, id_to_name, name_to_desc))

    def extract_hex_bytes_from_block(block):
        hex_list = []

        for line in block.splitlines():
            line = line.strip()
            line = re.sub(r'^\s*[0-9A-Fa-f]{4,}\s+', '', line)
            hexes = re.findall(r'\b([0-9A-Fa-f]{2})\b', line)
            if hexes:
                hex_list.extend(hexes)

        return hex_list

    # --------------------------------------------------
    # 1) 讀 EFSTIDs.lua，建立 數字ID -> EFST名稱
    # --------------------------------------------------
    efst_ids_content = read_text_auto(efst_ids_path)
    id_to_name = {}

    for name, num in re.findall(r'\b(EFST_[A-Z0-9_]+)\s*=\s*(\d+)\s*,?', efst_ids_content):
        id_to_name[int(num)] = name

    # --------------------------------------------------
    # 2) 讀 stateiconinfo.lua，建立 EFST名稱 -> descript[]
    # --------------------------------------------------
    stateicon_content = read_text_auto(stateiconinfo_path)
    name_to_desc = {}

    entry_pattern = re.compile(
        r'StateIconList\[EFST_IDs\.(EFST_[A-Z0-9_]+)\]\s*=\s*\{'
    )

    for m in entry_pattern.finditer(stateicon_content):
        efst_name = m.group(1)

        block_start = m.end() - 1
        block_text = extract_brace_block(stateicon_content, block_start)
        if not block_text:
            continue

        desc_m = re.search(r'descript\s*=\s*\{', block_text)
        if not desc_m:
            continue

        desc_start = desc_m.end() - 1
        desc_block = extract_brace_block(block_text, desc_start)
        if not desc_block:
            continue

        lines = re.findall(r'\{\s*"([^"]*)"', desc_block)

        clean_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line == "%s":
                continue
            clean_lines.append(line)

        name_to_desc[efst_name] = clean_lines

    # --------------------------------------------------
    # 3) 取得 replay 內容（raw 模式直接使用記憶體字串）
    # --------------------------------------------------
    if content is None:
        if not filepath:
            return []
        with open(filepath, 'r', encoding='cp950', errors='ignore') as f:
            content = f.read()

    results = []
    seen_ids = set()

    # --------------------------------------------------
    # 4) 先抓角色自己的 AID
    #    [Chunk Session] Unparsed opcode Aid, Length=4
    # --------------------------------------------------
    player_aid_hex = None

    aid_pattern = (
        r"\[Chunk Session\] Unparsed opcode Aid, Length=4"
        r"[\s\S]*?\{([^}]*)\}"
    )

    aid_match = re.search(aid_pattern, content, re.DOTALL)
    if aid_match:
        aid_hex_list = extract_hex_bytes_from_block(aid_match.group(1))
        if len(aid_hex_list) >= 4:
            # 直接保留原始 byte 順序比對，例如 AA 8C 7C 01
            player_aid_hex = ''.join(x.lower() for x in aid_hex_list[:4])

    # --------------------------------------------------
    # 5) 原本的 EfstInfo
    # --------------------------------------------------
    pattern_efstinfo = (
        r"\[Chunk [^\]]+\] Unparsed opcode EfstInfo, Length=\d+"
        r"[\s\S]*?\{([^}]*)\}"
    )

    matches = re.findall(pattern_efstinfo, content, re.DOTALL)

    for block in matches:
        hex_list = extract_hex_bytes_from_block(block)
        if len(hex_list) < 2:
            continue

        low = int(hex_list[0], 16)
        high = int(hex_list[1], 16)
        value = (high << 8) | low

        append_unique(results, seen_ids, value, id_to_name, name_to_desc)

    # --------------------------------------------------
    # 6) 新增：HEADER_ZC_MSG_STATE_CHANGE3
    #    找 83 09
    #    後2 bytes = 狀態ID (little-endian)
    #    再後4 bytes = 施放者AID
    #    只保留 AID == player_aid_hex
    # --------------------------------------------------
    if player_aid_hex:
        pattern_state_change3 = (
            r"packet\s+HEADER_ZC_MSG_STATE_CHANGE3"
            r"[\s\S]*?\{([^}]*)\}"
        )

        state_matches = re.findall(pattern_state_change3, content, re.DOTALL)

        for block in state_matches:
            hex_list = extract_hex_bytes_from_block(block)
            if len(hex_list) < 8:
                continue

            for i in range(len(hex_list) - 7):
                if hex_list[i].lower() == "83" and hex_list[i + 1].lower() == "09":
                    # 狀態ID：83 09 後面兩個 byte，小端序
                    low = int(hex_list[i + 2], 16)
                    high = int(hex_list[i + 3], 16)
                    state_id = (high << 8) | low

                    # 施放者 AID：再後面四個 byte，直接比原始順序
                    caster_aid_hex = ''.join(x.lower() for x in hex_list[i + 4:i + 8])

                    if caster_aid_hex != player_aid_hex:
                        continue

                    append_unique(results, seen_ids, state_id, id_to_name, name_to_desc)
                    break  # 這包抓到就夠了

    results = apply_efst_combo_transform(results, EFST_COMBO_RULES)
    return results


def extract_equip_chunk(filepath, json_data, get_itemname,
                        chunk_name="EquippedItems", group_map=None, *, content=None):

    import re

    if content is None:
        if not filepath:
            print(f"找不到指定chunk！({chunk_name})")
            return
        with open(filepath, 'r', encoding='UTF-8', errors='ignore') as f:
            content = f.read()

    # === 只抓 chunk 本體 ===
    pattern = (
        r"\[Chunk Items\] Unparsed opcode "
        + re.escape(chunk_name)
        + r", Length=\d+\s*"
        + r"(?:→\s*Raw hex:\s*)?"
        + r"\[[^\]]+\]\s*\{([\s\S]*?)^\s*\}"
    )

    match = re.search(pattern, content, re.MULTILINE)
    if not match:
        print(f"找不到指定chunk！({chunk_name})")
        return

    # === 轉成 hex list ===
    hex_body = match.group(1)
    hex_list = []

    for line in hex_body.splitlines():
        line = re.sub(r'^\s*[0-9A-Fa-f]{4,}\s+', '', line)
        hex_line = re.findall(r'([0-9A-Fa-f]{2})', line)
        if hex_line:
            hex_list.extend(hex_line)

    # === 找所有 1901 ===
    group_tag = '1901'
    n = len(hex_list)
    group_starts = []

    for i in range(n - 1):
        if hex_list[i].lower() == '19' and hex_list[i + 1].lower() == '01':
            group_starts.append(i)

    group_starts.append(n)  # 保護結尾

    # === slot 定義 ===
    slot_tags = [
        '1901','1b01','1d01','1c01','1e01','1f01','2001','2101',
        '2301','2701','2b01','2201','2401','2501','2601','2801',
        '2901','2a01','2c01','2d01','1a01'
    ]

    # === slot 判斷：是否完整 ===
    def has_enough_slots(group_bytes):
        found = set()
        for slot in slot_tags:
            b1, b2 = slot[:2], slot[2:]
            for i in range(len(group_bytes) - 1):
                if (group_bytes[i].lower() == b1
                        and group_bytes[i + 1].lower() == b2):
                    found.add(slot)
                    break
        return len(found) >= len(slot_tags)

    weapon_id = None
    shield_id = None

    g = 0
    group_number = 1
    equip_map = {}  # {equip_id: [(chunk_name, group_number, group_name), ...]}



    # === 核心：動態延伸 group ===
    while g < len(group_starts) - 1:
        start = group_starts[g]
        end_idx = g + 1
        group_bytes = None

        while end_idx < len(group_starts):
            end = group_starts[end_idx]
            candidate = hex_list[start:end]

            if has_enough_slots(candidate):
                group_bytes = candidate
                break

            end_idx += 1

        if group_bytes is None:
            g += 1
            continue

        if group_map is None:
            group_map = GROUP_NAME_MAP

        group_name = group_map.get(group_number, f'未知部位{group_number}')

        if SHOW_GROUP_NAMES and group_name not in SHOW_GROUP_NAMES:
            g = end_idx
            group_number += 1
            continue

        if SHOW_GROUPS and group_number not in SHOW_GROUPS:
            g = end_idx
            group_number += 1
            continue

        group_lines = []
        group_has_data = False

        # === slot offset ===
        slot_offsets = []
        for slot in slot_tags:
            b1, b2 = slot[:2], slot[2:]
            idx = None
            for i in range(len(group_bytes) - 1):
                if group_bytes[i].lower() == b1 and group_bytes[i + 1].lower() == b2:
                    idx = i
                    break
            slot_offsets.append(idx)

        # === slot parsing ===
        for si, idx in enumerate(slot_offsets):
            if idx is None:
                continue

            slot_name = slot_tags[si].upper()

            should_parse = (
                (slot_name == '2201' and SHOW_2201) or
                (slot_name == '2301' and SHOW_2301) or
                (slot_name == '2701' and SHOW_2701) or
                (slot_name == '2D01' and SHOW_2D01) or
                (slot_name == '2B01' and SHOW_2B01)
            )

            # if SHOW_ONLY_PARSED_SLOTS and not should_parse:
            #     continue

            next_idx = None
            for ni in range(si + 1, len(slot_offsets)):
                if slot_offsets[ni] is not None and slot_offsets[ni] > idx:
                    next_idx = slot_offsets[ni]
                    break

            slot_bytes = group_bytes[idx:next_idx] if next_idx else group_bytes[idx:]

            if SHOW_ONLY_FILLED and len(slot_bytes) <= 4:
                continue

            title = f'---- Slot {slot_name}'
            if SHOW_OFFSET:
                title += f' (offset={idx})'
            title += ' ----'

            slot_content = [title]

            if SHOW_RAW:
                for j in range(0, len(slot_bytes), 8):
                    slot_content.append(' '.join(slot_bytes[j:j + 8]))

            # === 2201 卡片 ===
            if slot_name == '2201':
                try:
                    card_ids = [
                        bytes_to_int_le(slot_bytes[6:9]),
                        bytes_to_int_le(slot_bytes[10:13]),
                        bytes_to_int_le(slot_bytes[14:17]),
                        bytes_to_int_le(slot_bytes[18:21]),
                    ]
                    slot_content.append('四洞卡片ID：')

                    for i, cid in enumerate(card_ids, 1):
                        cname = get_itemname(cid) if cid else ""
                        slot_content.append(f'  卡{i}: {cid or ""}　{cname}')
                        json_data[f"{group_name}_card{i}"] = str(cname)

                except:
                    slot_content.append('解析2201失敗')
            
            # === 2301 裝備ID ===
            elif slot_name == '2301':
                try:
                    equip_id = bytes_to_int_le(slot_bytes[6:9])
                    equip_name = get_itemname(equip_id) if equip_id else ""
                    slot_content.append(f'裝備ID：{equip_id}　{equip_name}')
                    json_data[f"{group_name}_equip"] = str(equip_name)
                except:
                    slot_content.append('解析2301失敗')

            # === 2701 精煉 ===
            elif slot_name == '2701':
                try:
                    refine_lv = int(slot_bytes[6], 16)
                    slot_content.append(f'精煉等級：{refine_lv}')
                    json_data[group_name] = str(refine_lv)
                except:
                    slot_content.append('解析2701失敗')

            # === 2D01 附魔 ===
            elif slot_name == '2D01':
                try:
                    enchant_json = []
                    for i in range(4):
                        id_idx = 6 + i * 5
                        val_idx = 8 + i * 5
                        if val_idx >= len(slot_bytes):
                            break
                        eid = int(slot_bytes[id_idx], 16)
                        val = int(slot_bytes[val_idx], 16)
                        if eid == 0 and val == 0:
                            slot_content.append(f'  詞條{i+1}：無')
                        else:
                            desc, json_text = get_enchant_info(eid, val)
                            slot_content.append(f'  詞條{i+1}：{desc}')
                            enchant_json.append(json_text)
                    json_data[f"{group_name}_note"] = "\n".join(enchant_json)
                except:
                    slot_content.append('解析2D01失敗')

            # === 2B01 階級 ===
            elif slot_name == '2B01':
                try:
                    grade = int(slot_bytes[6], 16)
                    grade_name = GRADE_MAP.get(grade, str(grade))
                    slot_content.append(f'裝備階級：{grade_name}')
                    json_data[f"{group_name}_階級"] = grade_name
                except:
                    slot_content.append('解析2B01失敗')

            group_lines.extend(slot_content)
            group_has_data = True

        if group_has_data:
            print(f'==== {chunk_name} Group {group_number}（{group_name}）====')

            # 原本在 for line 裡面做 weapon/shield 指派，這裡就不用了
            for line in group_lines:
                print(line)
            print()

            # ✅ 收集這一組的 equip_id（假設 equip_id 在這裡已經算出來了）
            # 只收有效 ID
            if isinstance(equip_id, int) and equip_id > 0:
                equip_map.setdefault(equip_id, []).append((chunk_name, group_number, group_name, equip_name))


        group_number += 1
        g = end_idx

    # ===== 全部部位重複偵測（放在該 chunk 解析完之後）=====
    duplicates = {eid: places for eid, places in equip_map.items() if len(places) > 1}

    if duplicates:
        # 印在 console
        for eid, places in duplicates.items():
            place_text = "、".join([f"{cn} G{gn}（{gname} - {ename}）" for cn, gn, gname, ename in places])

            print(f"[警告] 偵測到裝備 ID 重複 (ID: {eid})：{place_text}")

        # 跳視窗（把全部重複整理成文字）
        try:
            from tkinter import messagebox
            lines = []
            for eid, places in duplicates.items():
                #place_text = "\n".join([f" - {cn} G{gn}（{gname}）" for cn, gn, gname in places])
                #place_text = "\n".join([f" - {cn} G{gn}（{gname} - {ename}）" for cn, gn, gname, ename in places])
                place_text = "\n".join([f" - {gname}：{ename}" for cn, gn, gname, ename in places])
                lines.append(f"ID: {eid}\n{place_text}")
            msg = (
                "偵測到以下裝備 ID 在多個部位重複：\n\n"
                + "\n\n".join(lines)
                + "\n\n為避免重複運算裝備能力，需手動將重複裝備清空到剩餘一個部位。"
                + "\n若為可雙持武器職業，需自行判斷是否為雙刀/雙手武器。"
            )

            messagebox.showwarning("裝備重複偵測", msg)
        except Exception:
            pass

    print("Done.\n")


def get_job_info(job_dict, job_id):
    # 先直接找 key
    if job_id in job_dict:
        return job_id, job_dict[job_id]

    # 找不到就去 GetPureJob 裡找
    for key, info in job_dict.items():
        if job_id in info.get("GetPureJob", []):
            return key, info

    return None, None

def run_rrf_main(iteminfo_dict=None, sequipment_data=None):
    def get_itemname(item_id):
        info = iteminfo_dict.get(item_id)
        if info:
            return info["name"]
        return f"[{item_id}]"

    with open("data/default.json", "r", encoding="utf-8") as f:
        json_data = json.load(f)

    # 1. 選 RRF → Python raw reader → 記憶體 replay_text
    rrf_path, replay_text = run_replay_and_dump()
    if not replay_text:
        #input("按 Enter 結束...")
        #exit()
        return None

    # 2. 解析技能資訊（直接吃記憶體內容）
    skills = parse_skillinfo_list_from_text(replay_text)
    load_skill_map("data/skillneme.csv") 
    from skill_tree import skill_code_to_name, skill_code_to_id

    print("========== 技能清單 ==========")

    skill_json_list = []   # ★ 用來輸出 JSON 的 note

    for code, lv in skills:
        # 技能名稱：依前 23 字比對
        skill_prefix_map = {k[:23]: v for k, v in skill_code_to_name.items()}
        cname = skill_prefix_map.get(code[:23], code)

        # 技能 ID：也是依前 23 字比對 skill_code_to_id
        skill_prefix_id_map = {k[:23]: v for k, v in skill_code_to_id.items()}
        skill_id = skill_prefix_id_map.get(code[:23], 0)

        # 顯示用
        print(f"{cname:<23} 等級 {lv}")

        # ★ JSON 用 EnableSkill(技能ID, lv)
        if skill_id != 0:
            skill_json_list.append(f"EnableSkill({skill_id}, {lv})")

    print("")
    json_data["技能_note"] = "\n".join(skill_json_list)
    # 3.★ 解析角色 Session 資料
    session_data = extract_session_stats(content=replay_text)

    # 角色基本資料
    json_data["BaseLv"] = str(session_data.get("Level", ""))
    json_data["JobLv"] = str(session_data.get("JobLevel", ""))
    job_id = session_data.get("Job")
    main_job_id, job_info = get_job_info(job_dict, job_id)    
    json_data["JOB"] = str(job_info["name"]) if main_job_id else ""

    for k in ["Str","Agi","Vit","Int","Dex","Luk","POW","STA","WIS","SPL","CON","CRT"]:
        if k in session_data:
            json_data[k.upper()] = str(session_data[k])
    
    print("========== 角色資訊 ==========")
    if "Charactername" in session_data:
        print(f"角色名稱：{session_data['Charactername']}")
    if "Job" in session_data:
        job_id = session_data["Job"]
        main_job_id, job_info = get_job_info(job_dict, job_id)   

        if main_job_id:
            job_name = job_info.get("name", f"未知職業({job_id})")
            print(f"職業：{job_name}")
        else:
            print(f"職業：未知職業 (ID: {job_id})")
    if "Level" in session_data:
        print(f"角色等級：{session_data['Level']}")
    if "JobLevel" in session_data:
        print(f"Job 等級：{session_data['JobLevel']}")

    print("------ 基礎素質 ------")
    for stat in ["Str", "Agi", "Vit", "Int", "Dex", "Luk", "POW", "STA", "WIS", "SPL", "CON", "CRT"]:
        if stat in session_data:
            print(f"{stat}: {session_data[stat]}")
    print("")
    
    # 4. 解析 EfstInfo（ID -> 狀態名稱 -> descript）
    efstinfo_list = extract_efstinfo_values(
        None,
        "data/EFSTIDs.lua",
        "data/stateiconinfo.lua",
        content=replay_text,
    )
    # 把 EfstInfo 的數字 ID 寫入 default.json 的 buff，並用逗號分隔
    json_data["buff"] = ",".join(str(info["id"]) for info in efstinfo_list)
    print("========== EfstInfo ==========")
    if efstinfo_list:
        for i, info in enumerate(efstinfo_list, 1):
            print(f"EfstInfo #{i}: {info['id']} ({info['name']})")
            if info["descript"]:
                for line in info["descript"]:
                    print(f"  {line}")
            else:
                print("  找不到 descript")
    else:
        print("找不到 EfstInfo 封包")
    print("")

    # 5. 直接解析記憶體中的 RRF Items chunks
    extract_equip_chunk(None, json_data, get_itemname, 'EquippedItems', GROUP_NAME_MAP, content=replay_text)
    extract_equip_chunk(None, json_data, get_itemname, 'EquippedShadowItems', Shadow_GROUP_NAME_MAP, content=replay_text)
    #投擲物品查詢 找到EquipArrowIndex的開頭序號 到InventoryItems物品內的1D01內的第五組就是代號 要反查出物品名稱再匯入json，但是我懶得寫了
    #extract_equip_chunk(txt_path, json_data, get_itemname,'InventoryItems', NAME_MAP)


    # 6. raw 模式沒有 temp.txt，不需要刪除暫存文字檔。
    #    JSON 輸出與 tmp/rrf_output_path.txt 保持原本流程。

    def replace_windows_invalid_chars(name):
        table = str.maketrans({
            '\\': '＼',
            '/': '／',
            ':': '：',
            '*': '＊',
            '?': '？',
            '"': '＂',
            '<': '＜',
            '>': '＞',
            '|': '｜',
        })
        return name.translate(table)


    rrfname = (
        session_data['Charactername'] + "_" + job_info["name"]
        if main_job_id == job_id
        else session_data['Charactername'] + "_" + job_info["name"] + "(非4轉)"
    )

    rrf_filename = os.path.basename(rrfname)
    json_base_name = os.path.splitext(rrf_filename)[0]

    json_base_name = replace_windows_invalid_chars(json_base_name)

    json_name = json_base_name + ".json"
    json_output_path = os.path.join("tmp", json_name)

    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    # === 告訴 GUI 輸出的 json 是哪個 ===
    with open("tmp/rrf_output_path.txt", "w", encoding="utf-8") as f:
        f.write(json_output_path)

    print(f"JSON 已輸出為 {json_output_path}")
    #input("按 Enter 結束...")

    return json_output_path

if __name__ == "__main__":
    run_rrf_main()