# monster_lookup_dialog.py
import json
from pathlib import Path
import re
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit
# === STAGE 18 DESKTOP SHARED MONSTER CORE ===
from ro_core import (
    stage18_decode_monster_element as _core_stage18_decode_monster_element,
    stage18_parse_monster_payload as _core_stage18_parse_monster_payload,
)
import requests
from dataclasses import dataclass
from fnmatch import fnmatchcase
import sys

# ─── 內建 RO Navigation 搜尋索引（無須 ro_navigation_index.py） ───
# -*- coding: utf-8 -*-
"""Read RO's decompressed Navi_Map / Navi_Mob Lua-text navigation tables.

Only Python's standard library is required. This module does not execute Lua.
The original Taiwan navigation files are CP950/Big5 encoded. Some client
versions use UTF-8; both encodings are supported.
"""




NAV_MAP_FILENAME = "navi_map_tw.lub"
NAV_MOB_FILENAME = "navi_mob_tw.lub"

# Explicitly parse data-only table rows. Never eval/exec an untrusted LUB file.
_QUOTED = r'"((?:\\.|[^"\\])*)"'
_INT = r"(-?\d+)"
_MOB_ROW = re.compile(
    rf'^\s*\{{\s*{_QUOTED}\s*,\s*{_INT}\s*,\s*{_INT}\s*,\s*{_INT}'
    rf'\s*,\s*{_QUOTED}\s*,\s*{_QUOTED}\s*,\s*{_INT}\s*,\s*{_INT}\s*\}}\s*,?\s*$'
)
_MAP_ROW = re.compile(
    rf'^\s*\{{\s*{_QUOTED}\s*,\s*{_QUOTED}\s*,\s*{_INT}'
    rf'\s*,\s*{_INT}\s*,\s*{_INT}\s*\}}\s*,?\s*$'
)


def _lua_text(raw: str) -> str:
    """Unescape basic Lua quoted-string escapes (names are plain in these files)."""
    return re.sub(
        r'\\([\\"nrt])',
        lambda m: {'n': '\n', 'r': '\r', 't': '\t'}.get(m.group(1), m.group(1)),
        raw,
    )


def _read_lua_table(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b'\x1bLua'):
        raise ValueError(f"{path.name} 是 Lua 編譯檔，請先以 GRF Editor 反編譯成文字。")
    for encoding in ("utf-8-sig", "cp950", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path.name} 的文字編碼無法辨識（預期 UTF-8 或 Big5/CP950）。")


def find_navigation_dir() -> Path:
    """Find both .lub files inside a data directory near the running app."""
    candidates = [Path.cwd() / "data", Path(__file__).resolve().parent / "data"]
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "data")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "data")
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / NAV_MAP_FILENAME).is_file() and (candidate / NAV_MOB_FILENAME).is_file():
            return candidate
    folders = "、".join(str(path) for path in seen)
    raise FileNotFoundError(
        f"找不到導航資料。請將 {NAV_MAP_FILENAME}、{NAV_MOB_FILENAME} 放到 data 資料夾。"
        f"（檢查位置：{folders}）"
    )


@dataclass(frozen=True)
class MapEntry:
    code: str
    name: str
    map_type: int
    width: int
    height: int


@dataclass(frozen=True)
class MonsterEntry:
    monster_id: int
    name: str
    internal_name: str
    level: int
    is_mvp: bool


@dataclass(frozen=True)
class SpawnEntry:
    map_code: str
    monster_id: int
    count: int
    level: int
    is_mvp: bool
    name: str
    internal_name: str


@dataclass(frozen=True)
class SearchHit:
    kind: str  # 'monster' or 'map'
    key: int | str
    label: str
    identifier: str
    info: str


class NavigationIndex:
    """Local lookup of monsters, maps and spawn locations from RO navigation."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.maps: dict[str, MapEntry] = {}
        self.monsters: dict[int, MonsterEntry] = {}
        self.spawns_by_map: dict[str, list[SpawnEntry]] = {}
        self.spawns_by_monster: dict[int, list[SpawnEntry]] = {}
        self.spawn_record_count = 0
        self._load_maps(self.data_dir / NAV_MAP_FILENAME)
        self._load_monsters(self.data_dir / NAV_MOB_FILENAME)

    def _load_maps(self, path: Path) -> None:
        text = _read_lua_table(path)
        if "Navi_Map" not in text:
            raise ValueError(f"{path.name} 不是 Navi_Map 資料表。")
        for line in text.splitlines():
            match = _MAP_ROW.fullmatch(line)
            if not match:
                continue
            code, name, map_type, width, height = match.groups()
            code = _lua_text(code).strip()
            if not code or code == "NULL":
                continue
            self.maps[code] = MapEntry(
                code, _lua_text(name).strip() or code,
                int(map_type), int(width), int(height),
            )
        if not self.maps:
            raise ValueError(f"{path.name} 沒有可用的地圖資料。")

    def _load_monsters(self, path: Path) -> None:
        text = _read_lua_table(path)
        if "Navi_Mob" not in text:
            raise ValueError(f"{path.name} 不是 Navi_Mob 資料表。")
        for line in text.splitlines():
            match = _MOB_ROW.fullmatch(line)
            if not match:
                continue
            map_code, _record_id, mob_type, packed, name, internal, level, _flags = match.groups()
            map_code = _lua_text(map_code).strip()
            if not map_code or map_code == "NULL":
                continue
            packed = int(packed)
            # Navi_Mob: high 16 bits = spawn count; low 16 bits = monster class ID.
            # This is *not* the second-field navigation row ID.
            monster_id = packed & 0xFFFF
            if not monster_id:
                continue
            count = packed >> 16
            name = _lua_text(name).strip() or _lua_text(internal).strip() or str(monster_id)
            internal = _lua_text(internal).strip()
            level = int(level)
            is_mvp = int(mob_type) == 301
            spawn = SpawnEntry(map_code, monster_id, count, level, is_mvp, name, internal)
            self.spawns_by_map.setdefault(map_code, []).append(spawn)
            self.spawns_by_monster.setdefault(monster_id, []).append(spawn)
            if monster_id not in self.monsters:
                self.monsters[monster_id] = MonsterEntry(monster_id, name, internal, level, is_mvp)
            elif is_mvp and not self.monsters[monster_id].is_mvp:
                old = self.monsters[monster_id]
                self.monsters[monster_id] = MonsterEntry(old.monster_id, old.name, old.internal_name, old.level, True)
            self.spawn_record_count += 1
        if not self.monsters:
            raise ValueError(f"{path.name} 沒有可用的怪物資料。")

    def map_name(self, code: str) -> str:
        info = self.maps.get(code)
        return info.name if info else code

    def map_monsters(self, map_code: str) -> list[SpawnEntry]:
        """List each monster ID once per map, summing repeated spawn entries."""
        grouped: dict[int, SpawnEntry] = {}
        for spawn in self.spawns_by_map.get(map_code, ()):
            old = grouped.get(spawn.monster_id)
            if old is None:
                grouped[spawn.monster_id] = spawn
            else:
                grouped[spawn.monster_id] = SpawnEntry(
                    spawn.map_code, spawn.monster_id, old.count + spawn.count,
                    spawn.level, old.is_mvp or spawn.is_mvp,
                    old.name, old.internal_name,
                )
        return sorted(grouped.values(), key=lambda x: (x.level, x.monster_id))

    def monster_maps(self, monster_id: int) -> list[SpawnEntry]:
        """List maps containing this monster, summing duplicate spawns per map."""
        grouped: dict[str, SpawnEntry] = {}
        for spawn in self.spawns_by_monster.get(int(monster_id), ()):
            old = grouped.get(spawn.map_code)
            if old is None:
                grouped[spawn.map_code] = spawn
            else:
                grouped[spawn.map_code] = SpawnEntry(
                    spawn.map_code, spawn.monster_id, old.count + spawn.count,
                    spawn.level, old.is_mvp or spawn.is_mvp,
                    old.name, old.internal_name,
                )
        return sorted(grouped.values(), key=lambda x: (self.map_name(x.map_code).casefold(), x.map_code))

    def search(self, query: str, limit: int = 160) -> tuple[list[SearchHit], int]:
        """Search ID/Chinese/English monster names, Chinese/map-code map names.

        Returns (first N matches, full match count) to prevent a huge UI refresh.
        """
        query = str(query or "").strip().casefold()
        if not query:
            return [], 0
        found: list[tuple[int, int, str, SearchHit]] = []

        def score(values: tuple[str, ...]) -> int | None:
            normalized = [value.casefold() for value in values if value]
            if query in normalized:
                return 0
            if any(value.startswith(query) for value in normalized):
                return 1
            if any(query in value for value in normalized):
                return 2
            return None

        for monster in self.monsters.values():
            s = score((str(monster.monster_id), monster.name, monster.internal_name))
            if s is not None:
                n_maps = len(self.monster_maps(monster.monster_id))
                found.append((s, 0, monster.name.casefold(), SearchHit(
                    "monster", monster.monster_id, monster.name, str(monster.monster_id),
                    f"Lv.{monster.level}｜{n_maps} 張地圖" + ("｜MVP" if monster.is_mvp else ""),
                )))
        for map_entry in self.maps.values():
            s = score((map_entry.code, map_entry.name))
            if s is not None:
                n_monsters = len(self.map_monsters(map_entry.code))
                found.append((s, 1, map_entry.name.casefold(), SearchHit(
                    "map", map_entry.code, map_entry.name, map_entry.code,
                    f"{n_monsters} 種怪物",
                )))
        found.sort(key=lambda x: (x[0], x[1], x[2], str(x[3].key)))
        return [item[3] for item in found[:max(1, limit)]], len(found)

def _search_rank(query: str, *values: object) -> int | None:
    """Search rank: exact before prefix before substring; Unicode-case-insensitive."""
    normalized = [str(value).strip().casefold() for value in values if value is not None and str(value).strip()]
    if query in normalized:
        return 0
    if any(value.startswith(query) for value in normalized):
        return 1
    if any(query in value for value in normalized):
        return 2
    return None


def search_navigation_and_cache(
    index: NavigationIndex | None, cached_monsters: list[dict],
    query: str, limit: int = 160,
) -> tuple[list[SearchHit], int]:
    """Search LUB maps/monsters AND the original JSON cache as one result set.

    The same monster ID is shown once, even when it appears in both sources.
    Matches found through an alternate cached name are still associated with
    their original navigation ID, so selecting them shows the known spawn maps.
    This function never calls the network and does not load full JSON payloads.
    """
    query = str(query or "").strip().casefold()
    if not query:
        return [], 0

    cached_by_id: dict[int, str] = {}
    for entry in cached_monsters:
        try:
            monster_id = int(entry["id"])
        except (KeyError, ValueError, TypeError):
            continue
        name = str(entry.get("name") or "").strip()
        if monster_id > 0 and name:
            cached_by_id[monster_id] = name

    # Keep one winning hit per (kind, key), but match all source-name aliases.
    found: dict[tuple[str, int | str], tuple[int, int, SearchHit]] = {}
    if index is not None:
        nav_hits, _ = index.search(query, limit=len(index.monsters) + len(index.maps))
        for hit in nav_hits:
            if hit.kind == "monster":
                monster_id = int(hit.key)
                nav = index.monsters[monster_id]
                score = _search_rank(query, monster_id, nav.name, nav.internal_name)
                cache_name = cached_by_id.get(monster_id)
                description = hit.info + (f"｜已快取：{cache_name}" if cache_name else "")
                hit = SearchHit("monster", monster_id, hit.label, hit.identifier, description)
                category = 0
            else:
                map_entry = index.maps[str(hit.key)]
                score = _search_rank(query, map_entry.code, map_entry.name)
                category = 1
            if score is not None:
                found[(hit.kind, hit.key)] = (score, category, hit)

    for monster_id, cache_name in cached_by_id.items():
        score = _search_rank(query, monster_id, cache_name)
        if score is None:
            continue
        nav = index.monsters.get(monster_id) if index is not None else None
        if nav is not None:
            kind = "monster"
            maps = len(index.monster_maps(monster_id))
            details = f"Lv.{nav.level}｜{maps} 張地圖｜已快取"
            if nav.name != cache_name:
                details += f"｜導航名稱：{nav.name}"
            if nav.is_mvp:
                details += "｜MVP"
            priority = 0
        else:
            kind = "cache"
            details = "已快取（JSON），導航資料沒有這隻怪物的出現地圖；雙擊查詢詳細資料"
            priority = 2
        key = (kind, monster_id)
        existing = found.get(key)
        # Prefer the source that gives a stronger match; preserve the search
        # term's visible cached name when that is the only source match.
        if existing is None or score < existing[0]:
            found[key] = (score, priority, SearchHit(
                kind, monster_id, cache_name, str(monster_id), details,
            ))

    ordered = sorted(found.values(), key=lambda item: (
        item[0], item[1], item[2].label.casefold(), str(item[2].key),
    ))
    return [item[2] for item in ordered[:max(1, limit)]], len(ordered)


# ─── 原怪物查詢 UI / 快取 / API ───

from PySide6.QtCore import QObject, Signal, Slot, QThread, Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QSplitter,
    QLineEdit, QPushButton, QLabel, QMessageBox, QWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox,
    QTreeWidget, QTreeWidgetItem,
)
# ================= monster =================
MONSTER_CACHE_DIR = Path("data", "monster")

# Divine Pride API 使用兩個彼此獨立的 HTTP Header：
# Accept-Language 決定本地化語言；x-server 決定資料屬於哪個遊戲伺服器。
# 請注意伺服器別名的大小寫：API 使用 twRO，而不是 TwRO。
MONSTER_API_LANGUAGE = "cn"
MONSTER_API_SERVER = "twRO"
MONSTER_API_SERVERS = ("twRO", "twROZ")


def cache_path(monster_id: int, server: str = MONSTER_API_SERVER,
               language: str = MONSTER_API_LANGUAGE) -> Path:
    """沿用原始快取位置 data/monster/{id}.json，不建立伺服器子目錄。

    沿用單一 ID 快取檔。已存在的檔案不依 region 排除，
    因為下拉選單必須支援所有伺服器的本機怪物資料。
    """
    if server not in MONSTER_API_SERVERS:
        raise ValueError(f"不支援的怪物 API 伺服器：{server}")
    if language != MONSTER_API_LANGUAGE:
        raise ValueError(f"怪物 API 目前僅支援中文（cn），收到：{language}")
    return MONSTER_CACHE_DIR / f"{int(monster_id)}.json"


def has_chinese_characters(value: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", str(value or "")))


# Divine Pride 2026-06-17 公告：至多 1 API request/s，禁止平行 API 請求。
# 另外 API 文件說明，每個 API key 可能有更低的專屬額度；收到 429 須遵照 Retry-After。
# 此鎖保證「同一個程式進程」內所有經此 helper 的 API 請求序列化。
API_MIN_REQUEST_INTERVAL = 1.10  # 避免 1.000s 邊界碰上遠端時鐘/伺服器誤判
_API_REQUEST_LOCK = threading.Lock()
_API_NEXT_REQUEST_AT = 0.0
_API_BACKOFF_UNTIL = 0.0


class ApiRateLimitError(RuntimeError):
    """伺服器已回 429：禁止在 Retry-After 之前重新發送 API 請求。"""


def _retry_after_seconds(value) -> float:
    """支援 Retry-After 秒數及 HTTP-date；缺失/無效時保守退避 60 秒。"""
    if value is not None:
        raw = str(value).strip()
        try:
            return max(1.0, float(raw))
        except (TypeError, ValueError):
            try:
                when = parsedate_to_datetime(raw)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                return max(1.0, (when - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, IndexError, OverflowError):
                pass
    return 60.0


def _api_get_monster(url: str, *, api_key: str, headers: dict):
    """同進程 API 互斥、相鄰請求 >=1.1s；429 後不自動暴力重試。"""
    global _API_NEXT_REQUEST_AT, _API_BACKOFF_UNTIL
    with _API_REQUEST_LOCK:
        now = time.monotonic()
        if now < _API_BACKOFF_UNTIL:
            remaining = max(1, int(_API_BACKOFF_UNTIL - now + .999))
            raise ApiRateLimitError(f"Divine Pride API 已達流量限制 (429)，請於 {remaining} 秒後重試。")
        wait = _API_NEXT_REQUEST_AT - now
        if wait > 0:
            time.sleep(wait)
        # 在實際送出前記錄起始時間，並保持全程持鎖，絕不平行呼叫。
        _API_NEXT_REQUEST_AT = time.monotonic() + API_MIN_REQUEST_INTERVAL
        try:
            response = requests.get(
                url, params={"apiKey": api_key}, headers=headers, timeout=10
            )
        except requests.Timeout as exc:
            raise RuntimeError("Divine Pride API 連線逾時，可稍後重試。") from exc
        except requests.RequestException as exc:
            # 不直接顯示例外內的完整請求 URL，因為 URL 查詢參數包含 API key。
            raise RuntimeError(f"Divine Pride API 網路錯誤（{type(exc).__name__}）。") from exc

        status = int(getattr(response, "status_code", 200))
        if status == 429:
            seconds = _retry_after_seconds(getattr(response, "headers", {}).get("Retry-After"))
            _API_BACKOFF_UNTIL = time.monotonic() + seconds
            raise ApiRateLimitError(
                f"Divine Pride API 已達流量限制 (429)，已停止繼續查詢，"
                f"請至少 {int(seconds + .999)} 秒後重試。"
            )
        if status == 401:
            raise RuntimeError("Divine Pride API 401：API Key 未設定或無效。")
        if status == 400:
            raise RuntimeError("Divine Pride API 400：請求參數無效。")
        if status == 404:
            raise RuntimeError("Divine Pride API 404：找不到此怪物 ID。")
        if status >= 500:
            raise RuntimeError(f"Divine Pride API {status}：伺服器暫時發生錯誤。")
        if status >= 400:
            raise RuntimeError(f"Divine Pride API {status}：查詢失敗。")
        return response


def validated_sprite_url(value) -> str:
    """只允許 Divine Pride 的 HTTPS 靜態圖，避免非預期外部 URL。"""
    if not isinstance(value, str) or not value or len(value) > 2048:
        return ""
    try:
        url = urlsplit(value.strip())
        if (url.scheme.lower() == "https"
                and url.netloc.lower() == "static.divine-pride.net"
                and url.path.startswith("/images/")
                and url.path.lower().endswith((".png", ".gif", ".webp", ".jpg", ".jpeg"))
                and not url.fragment):
            return value.strip()
    except ValueError:
        pass
    return ""


def load_presets() -> list[dict]:
    """掃描 data/monster/*.json 的所有怪物，不依伺服器標籤過濾。

    - 所有 region / availableServers（包含缺少這兩欄）都可以列在下拉選單。
    - 名稱直接使用 JSON 的 name；若不是中文，也保留原名以免漏掉怪物。
      新查詢仍以 Accept-Language: cn 向 API 要求中文名稱，不自行杜撰翻譯。
    - 下拉選單只顯示「名稱（ID）」，不顯示任何伺服器標籤。
    - 只掃描原有的 data/monster 平面目錄，不會改寫或搬動快取。
    """
    if not MONSTER_CACHE_DIR.is_dir():
        return []
    monsters = {}
    for path in MONSTER_CACHE_DIR.glob("*.json"):
        if not path.stem.isdecimal():
            continue
        try:
            if path.stat().st_size > 8 * 1024 * 1024:
                continue
            with path.open("r", encoding="utf-8-sig") as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                continue
            monster_id = int(data.get("id", data.get("monsterId", data.get("monster_id", 0))))
            if monster_id <= 0 or monster_id != int(path.stem):
                continue
            name = str(data.get("name") or "").strip()
            if not name or len(name) > 100:
                continue
            monsters[monster_id] = {"id": monster_id, "name": name}
        except (OSError, ValueError, TypeError, OverflowError, json.JSONDecodeError):
            continue
    return [monsters[monster_id] for monster_id in sorted(monsters)]

# ═══════════════════════════════════════════════════════════════════════════════
# 怪物 JSON 顯示設定：只修改此 .py 的常數；介面沒有欄位設定控制項。
# 1. MONSTER_DETAIL_FIELD_ORDER 調整「完整 JSON 資料」最外層欄位順序。
# 2. 要隱藏欄位，在 MONSTER_DETAIL_HIDDEN_PATHS 加入路徑，如 "spriteUrl"、
#    "skills.*.iconUrl"、"statsVersions.*.health"。
# 3. MONSTER_DETAIL_CHILD_FIELD_ORDER 可調整物件或陣列各筆資料的子欄位順序。
# 4. MONSTER_DETAIL_SHOW_UNLISTED = True：API 增加新欄位時一樣會自動顯示。
#    改 False：只顯示下方明列的最外層欄位。
# 注意：這些設定只影響顯示，不刪除 JSON 快取，也不更動套用至主程式的資料。
# ═══════════════════════════════════════════════════════════════════════════════
MONSTER_DETAIL_FIELD_ORDER = (
    "id", "name", "spriteName", "level", "health", "magicHealth",
    "element", "elementLevel", "size", "race", "type",
    "attackRange", "magicAttackRange", "range", "def", "mDef",
    "hit", "flee", "criticalHit", "res", "mRes", "speed", "attackSpeed",
    "str", "agi", "vit", "int", "dex", "luk",
    "baseExperience", "jobExperience", "availableServers", "region",
    "aiFlags", "aiFlagDetails", "attributes", "elementResistances",
    "drops", "mvpDrops", "mapSpecificDrops", "spawns", "skills",
    "expPenaltyTable", "statsVersions", "spawnVersions", "skillVersions",
    "dropVersions", "mvpDropVersions", "mapDropVersions",
    "history", "otherServers", "adminData", "spriteUrl", "spriteSheetUrl",
)
MONSTER_DETAIL_HIDDEN_PATHS = (
    "name", "spriteName", "magicHealth", "element", "elementLevel", "size",
    "race", "type", "criticalHit", "speed", "availableServers", "region",
    "aiFlags", "elementResistances", "drops", "mvpDrops", "mapSpecificDrops",
    "spawns", "skills", "expPenaltyTable", "statsVersions", "spawnVersions",
    "skillVersions", "dropVersions", "aiFlagDetails", "mvpDropVersions",
    "mapDropVersions", "adminData", "spriteUrl", "spriteSheetUrl",
    "otherServers", "history", "attributes",
)
MONSTER_DETAIL_CHILD_FIELD_ORDER = {
    "skills.*": ("skillName", "skillId", "skillLevel", "probabilityPercent",
                 "castTime", "cooldownTime", "interruptable", "state", "condition",
                 "description", "iconUrl"),
    "skillVersions.*.*": ("skillName", "skillId", "skillLevel", "probabilityPercent",
                           "castTime", "cooldownTime", "interruptable", "state",
                           "condition", "description", "iconUrl"),
    "drops.*": ("itemName", "itemId", "probability", "displayName"),
    "mvpDrops.*": ("itemName", "itemId", "probability", "displayName"),
    "mapSpecificDrops.*": ("mapDisplayName", "mapName", "itemName", "itemId",
                             "probability", "dropType", "optionGroup", "hasEnchant"),
    "mapDropVersions.*.*": ("mapDisplayName", "mapName", "itemName", "itemId",
                              "probability", "dropType", "optionGroup", "hasEnchant"),
    "elementResistances.*": ("element", "percentage"),
    "expPenaltyTable.*": ("level", "percent", "baseExperience", "jobExperience"),
    "statsVersions.*": ("level", "health", "element", "elementLevel", "size",
                        "race", "def", "mDef", "hit", "flee", "str", "agi", "vit",
                        "int", "dex", "luk", "attackRange", "magicAttackRange"),
}
MONSTER_DETAIL_SHOW_UNLISTED = True
MONSTER_DETAIL_EXPAND_TOP_LEVEL = ("aiFlagDetails",)  # 只展開這些群組，其他仍可手動展開
MONSTER_DETAIL_MAX_TREE_NODES = 30000             # 針對異常過大 JSON 的介面保護

# 保留已套用資料的 monster_stats 欄位格式（供主程式／舊專案使用）。
# 這些欄位不再繪製成上方重複的素質摘要，完整資料統一在下方 JSON 樹顯示。
STAT_DISPLAY_FIELDS = (
    ("Lv.", "level"), ("HP", "hp"), ("ATK", "attack"), ("MATK", "matk"),
    ("DEF", "def"), ("MDEF", "mdef"), ("RES", "res"), ("MRES", "mres"),
    ("HIT", "hit"), ("FLEE", "flee"), ("STR", "str"), ("AGI", "agi"),
    ("VIT", "vit"), ("INT", "int"), ("DEX", "dex"), ("LUK", "luk"),
    ("Base EXP", "base_exp"), ("Job EXP", "job_exp"),
)

MONSTER_JSON_LABELS = {
    "id": "怪物 ID", "name": "名稱", "spriteName": "資源名稱",
    "availableServers": "可用伺服器", "spriteUrl": "圖片網址",
    "spriteSheetUrl": "圖集網址", "level": "等級", "health": "HP",
    "magicHealth": "魔法 HP", "baseExperience": "Base EXP", "jobExperience": "Job EXP",
    "expPenaltyTable": "經驗懲罰表", "race": "種族", "element": "屬性",
    "elementLevel": "屬性等級", "size": "體型", "type": "階級",
    "aiFlags": "AI 標記", "aiFlagDetails": "AI 行為", "attributes": "特殊特性",
    "attackRange": "物理攻擊傷害區間", "magicAttackRange": "魔法攻擊傷害區間",
    "range": "攻擊射程", "def": "DEF", "mDef": "MDEF", "hit": "HIT",
    "flee": "FLEE", "criticalHit": "CRI", "speed": "移動速度",
    "attackSpeed": "攻擊速度", "res": "RES", "mRes": "MRES",
    "str": "STR", "agi": "AGI", "vit": "VIT", "int": "INT",
    "dex": "DEX", "luk": "LUK", "elementResistances": "屬性抗性",
    "drops": "一般掉落", "mvpDrops": "MVP 掉落",
    "dropVersions": "掉落版本", "mvpDropVersions": "MVP 掉落版本",
    "mapSpecificDrops": "地圖限定掉落", "mapDropVersions": "地圖掉落版本",
    "spawns": "出現位置", "skills": "使用技能",
    "statsVersions": "素質版本", "spawnVersions": "出現版本",
    "skillVersions": "技能版本", "history": "歷史記錄",
    "otherServers": "其他伺服器", "region": "區域", "adminData": "管理資料",
    "skillId": "技能 ID", "skillName": "技能名稱", "skillLevel": "技能等級",
    "probabilityPercent": "發動機率 (%)", "castTime": "詠唱時間",
    "cooldownTime": "冷卻時間", "interruptable": "可中斷",
    "condition": "使用條件", "state": "行為狀態", "description": "描述",
    "element": "屬性", "percentage": "百分比 (%)", "percent": "百分比 (%)",
    "itemId": "物品 ID", "itemName": "物品名稱", "displayName": "顯示名稱",
    "mapName": "地圖代碼", "mapDisplayName": "地圖名稱",
    "aggressive": "主動攻擊", "assist": "協助攻擊", "looter": "撿取物品",
    "changeTarget": "切換目標", "changeTargetOnAttack": "受攻擊時切換目標",
    "immobile": "無法移動", "castSensor": "感應施法", "isNormal": "一般怪物",
}
MONSTER_ELEMENT_NAMES = {
    "neutral": "無屬性", "water": "水屬性", "earth": "地屬性", "fire": "火屬性",
    "wind": "風屬性", "poison": "毒屬性", "holy": "聖屬性",
    "shadow": "暗屬性", "dark": "暗屬性", "ghost": "念屬性",
    "undead": "不死屬性",
}
MONSTER_SIZE_NAMES = {"small": "小型", "medium": "中型", "large": "大型"}
MONSTER_RACE_NAMES = {
    "formless": "無形族", "undead": "不死族", "brute": "動物族",
    "animal": "動物族", "plant": "植物族", "insect": "昆蟲族",
    "fish": "魚貝族", "fish/shell": "魚貝族", "demon": "惡魔族",
    "demi-human": "人形族", "demihuman": "人形族", "human": "人形族",
    "angel": "天使族", "dragon": "龍族",
}
MONSTER_CLASS_NAMES = {"mvp": "MVP", "boss": "BOSS", "normal": "一般", "regular": "一般"}


def _first_value(data: dict, *names):
    for name in names:
        if name in data and data[name] is not None and data[name] != "":
            return data[name]
    return None


def _stat_string(value) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "—"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value).strip() or "—"


def _stat_range(value) -> str:
    if not isinstance(value, dict):
        return _stat_string(value)
    minimum = _first_value(value, "minimum", "min", "from")
    maximum = _first_value(value, "maximum", "max", "to")
    if minimum is None and maximum is None:
        return "—"
    if minimum is None:
        return _stat_string(maximum)
    if maximum is None or minimum == maximum:
        return _stat_string(minimum)
    return f"{_stat_string(minimum)}–{_stat_string(maximum)}"


def extract_monster_stats(payload: dict) -> dict[str, str]:
    """Return existing monster data only; handle nested and flat API layouts."""
    if not isinstance(payload, dict):
        return {}
    saved = payload.get("monster_stats")
    if isinstance(saved, dict):
        return {key: _stat_string(saved.get(key)) for _, key in STAT_DISPLAY_FIELDS}
    stats = payload.get("stats")
    if not isinstance(stats, dict):
        stats = payload

    def get(*names):
        value = _first_value(stats, *names)
        return value if value is not None else _first_value(payload, *names)

    values = {
        "level": get("level", "lv"),
        "hp": get("health", "hp", "maxHp", "maxHP"),
        "attack": get("attack", "atk", "attackRange"),
        "matk": get("magicAttack", "matk", "mAtk", "magicAttackRange"),
        "def": get("defense", "def"),
        "mdef": get("magicDefense", "mDef", "mdef"),
        "hit": get("hit"),
        "flee": get("flee"),
        "res": get("res"),
        "mres": get("mRes", "mres"),
        "speed": get("speed"),
        "attack_speed": get("attackSpeed"),
        "range": get("range"),
        "str": get("str", "strength"),
        "agi": get("agi", "agility"),
        "vit": get("vit", "vitality"),
        "int": get("_int", "int", "intelligence"),
        "dex": get("dex", "dexterity"),
        "luk": get("luk", "luck"),
        "base_exp": get("baseExperience", "baseExp", "base_exp"),
        "job_exp": get("jobExperience", "jobExp", "job_exp"),
    }
    if all(value is None for value in values.values()):
        return {}
    return {
        key: (_stat_range(value) if key in ("attack", "matk") else _stat_string(value))
        for key, value in values.items()
    }


def read_cached_monster_payload(monster_id: int) -> dict:
    """讀取原有 JSON 快取，驗證 ID，且絕不對外呼叫 API。"""
    try:
        path = cache_path(int(monster_id))
        if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
            return {}
        with path.open("r", encoding="utf-8-sig") as stream:
            data = json.load(stream)
        if not isinstance(data, dict):
            return {}
        cached_id = data.get("id", data.get("monsterId", data.get("monster_id")))
        if cached_id is None or int(cached_id) != int(monster_id):
            return {}
        return data
    except (OSError, ValueError, TypeError, OverflowError, json.JSONDecodeError):
        return {}


def read_cached_monster_stats(monster_id: int) -> dict[str, str]:
    """相容既有呼叫：從同一個 JSON 快取中取出精簡素質。"""
    return extract_monster_stats(read_cached_monster_payload(monster_id))


def _display_field_name(key: object) -> str:
    key = str(key)
    translated = MONSTER_JSON_LABELS.get(key)
    # return f"{translated} ({key})" if translated and translated != key else key
    return f"{translated}" if translated and translated != key else key


def _match_path(path: str, patterns) -> bool:
    """支援 skills.*.iconUrl 這種路徑寫法，陣列的各筆索引統一為 *。"""
    return any(fnmatchcase(path, pattern) for pattern in patterns)


def _ordered_json_items(obj: dict, parent_path: str = "") -> list[tuple[str, object]]:
    """在程式碼中設定欄位順序和排除名單，不更動原始 JSON。"""
    if parent_path == "":
        desired = MONSTER_DETAIL_FIELD_ORDER
    else:
        desired = ()
        for pattern, order in MONSTER_DETAIL_CHILD_FIELD_ORDER.items():
            if fnmatchcase(parent_path, pattern):
                desired = order
                break
    keys = [key for key in desired if key in obj]
    if parent_path or MONSTER_DETAIL_SHOW_UNLISTED:
        keys.extend(key for key in obj if key not in keys)
    result = []
    for key in keys:
        path = f"{parent_path}.{key}" if parent_path else str(key)
        if not _match_path(path, MONSTER_DETAIL_HIDDEN_PATHS):
            result.append((key, obj[key]))
    return result


def _pretty_json_value(value) -> str:
    """保留零、False、null 與空清單的意義，顯示原始值而不推測。"""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return str(value)
    return str(value)


def _ordered_json_tree(value, path: str = "", depth: int = 0):
    """純資料樹，用於測試顯示邏輯；深度防護避免異常巢狀輸入。"""
    if depth > 32:
        return [("...", "（巢狀層數過深）", [])]
    if isinstance(value, dict):
        items = _ordered_json_items(value, path)
        return [(str(k), _json_summary(v), _ordered_json_tree(v, f"{path}.{k}" if path else str(k), depth + 1))
                for k, v in items]
    if isinstance(value, list):
        result = []
        for i, item in enumerate(value):
            item_path = f"{path}.*" if path else "*"
            if _match_path(item_path, MONSTER_DETAIL_HIDDEN_PATHS):
                continue
            result.append((f"[{i+1}]", _json_summary(item), _ordered_json_tree(item, item_path, depth + 1)))
        return result
    return []


def _json_summary(value) -> str:
    if isinstance(value, list):
        return f"{len(value)} 筆" if value else "[]（空清單）"
    if isinstance(value, dict):
        return f"{len(value)} 個欄位" if value else "{}（空物件）"
    return _pretty_json_value(value)


def _localized_monster_element(value, element_level=None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"
    match = re.fullmatch(r"([A-Za-z][A-Za-z -]*?)\s*(\d+)?", raw)
    if not match:
        return raw
    name = MONSTER_ELEMENT_NAMES.get(match.group(1).strip().lower(), match.group(1))
    level = element_level if element_level is not None else match.group(2)
    return f"{name} Lv.{level}" if level is not None and str(level).strip() else name


def monster_name_with_traits(payload: dict, fallback: str = "") -> str:
    """顯示名稱 + 屬性、體型、種族、階級；缺值使用 — 而不杜撰資料。"""
    if not isinstance(payload, dict):
        payload = {}
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    versions = payload.get("statsVersions")
    default = versions.get("default") if isinstance(versions, dict) else None
    default = default if isinstance(default, dict) else {}
    def value(k):
        # Nested stats take priority; if absent, use top-level JSON and the
        # saved default version. Any field can be missing independently.
        for source in (stats, payload, default):
            found = _first_value(source, k)
            if found is not None:
                return found
        return None
    name = str(payload.get("name") or fallback or "").strip()
    element = _localized_monster_element(value("element"), value("elementLevel"))
    size_raw = str(value("size") or "").strip()
    size = MONSTER_SIZE_NAMES.get(size_raw.casefold(), size_raw or "—")
    race_raw = str(value("race") or "").strip()
    race = MONSTER_RACE_NAMES.get(race_raw.casefold(), race_raw or "—")
    type_raw = str(value("type") or "").strip()
    kind = MONSTER_CLASS_NAMES.get(type_raw.casefold(), type_raw or "—")
    return f"{name}｜屬性：{element}｜體型：{size}｜種族：{race}｜階級：{kind}" if name else ""


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

    def __init__(self, monster_id: int, api_key: str,
                 language: str = MONSTER_API_LANGUAGE,
                 server: str = MONSTER_API_SERVER):
        super().__init__()
        self.monster_id = int(monster_id)
        self.api_key = api_key
        self.language = language
        self.server = server

    def run(self):
        try:
            cpath = cache_path(self.monster_id, self.server, self.language)
            cpath.parent.mkdir(parents=True, exist_ok=True)

            # 下拉式清單允許所有伺服器的既有快取，因此手動選取後查詢時
            # 也要能讀取該檔原始資料；沒有必要重新對 twRO 送出 API 請求。
            if cpath.is_file():
                try:
                    with cpath.open("r", encoding="utf-8-sig") as f:
                        cached = json.load(f)
                    if (isinstance(cached, dict)
                            and str(cached.get("name") or cached.get("dbname") or "").strip()
                            and int(cached.get("id", cached.get("monsterId", self.monster_id))) == self.monster_id):
                        data = dict(cached)
                        data["_from_cache"] = True
                        data["_request_server"] = str(cached.get("region") or "").strip() or self.server
                        data["_request_language"] = self.language
                        self.finished.emit(data)
                        return
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    pass  # 損壞/舊格式的快取重新向 API 查詢。

            if not self.api_key:
                raise RuntimeError("找不到怪物快取，且尚未設定 API Key")

            # apiKey 用 params 交給 requests URL encode，避免手動拼接。
            url = f"https://www.divine-pride.net/api/database/Monster/{self.monster_id}"
            headers = {
                "Accept-Language": self.language,
                "x-server": self.server,
            }
            response = _api_get_monster(url, api_key=self.api_key, headers=headers)
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("API 回傳非物件 JSON，不能套用怪物資料")
            response_id = data.get("id", data.get("monsterId", data.get("monster_id")))
            if response_id is not None and int(response_id) != self.monster_id:
                raise ValueError(f"API 怪物 ID 不符（要求 {self.monster_id}，回傳 {response_id}）")
            region = str(data.get("region") or "").strip()
            if region and region.lower() != self.server.lower():
                raise ValueError(f"API 回傳伺服器為 {region}，但要求的是 {self.server}，資料未套用")
            if not str(data.get("name") or data.get("dbname") or "").strip():
                raise ValueError("API 沒有提供怪物名稱，不能確認本地化結果")

            # 儲存 API 原樣回應；不會將本地提示欄位寫入原始快取。
            try:
                with cpath.open("w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except OSError:
                pass

            result = dict(data)
            result["_from_cache"] = False
            result["_request_server"] = self.server
            result["_request_language"] = self.language
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


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
        self.resize(1120, 850)
        self.setMinimumSize(810, 640)

        # The original API/cache workflow remains available if the local
        # navigation files are missing, invalid, or have not been deployed.
        self.navigation_index = None
        self.navigation_error = ""
        self._updating_search_results = False
        self._cache_entries: list[dict] = []
        self._load_navigation_index()

        self._last_data = None
        self._sprite_reply = None
        # 不要命名 self.thread：QObject 已有 thread() 方法。
        # 保留所有尚未完全結束的 QThread，避免視窗過早關閉而銷毀執行緒。
        self._fetch_threads: list[QThread] = []
        self._fetch_workers: dict[QThread, MonsterFetchWorker] = {}
        self._sprite_manager = QNetworkAccessManager(self)

        # -------- UI --------
        self.id_input = QLineEdit()
        self.id_input.setPlaceholderText("怪物 ID（可以直接手動輸入，保留原本 API 查詢）")

        # Unified local search: monster IDs, Chinese/English names and map names.
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜尋怪物 ID／名稱、地圖名稱或代碼…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.search_input.returnPressed.connect(self.on_search_enter)
        self.btn_reload_navigation = QPushButton("重讀 LUB")
        self.btn_reload_navigation.setToolTip("重新讀取 data/navi_map_tw.lub 及 data/navi_mob_tw.lub，不呼叫 API")
        self.btn_reload_navigation.clicked.connect(self.reload_navigation)
        self.navigation_status = QLabel()
        self.navigation_status.setWordWrap(True)
        self.navigation_status.hide()

        # Two-pane master/detail view: click a monster to see maps, click a
        # map to see monsters. Double-clicking a monster requests full data.
        self.search_results = QTableWidget(0, 3)
        self.search_results.setHorizontalHeaderLabels(["類型", "名稱", "怪物 ID／地圖代碼"])
        self.search_results.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.search_results.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.search_results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.search_results.verticalHeader().setVisible(False)
        self.search_results.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.search_results.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.search_results.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.search_results.setMinimumHeight(155)
        self.search_results.itemSelectionChanged.connect(self.on_search_result_selected)
        self.search_results.cellDoubleClicked.connect(self.on_search_result_activated)
        self.search_count_label = QLabel("搜尋結果")
        self.search_count_label.setWordWrap(True)

        self.details_heading = QLabel("對應地圖／怪物")
        self.details_heading.setWordWrap(True)
        self.details_table = QTableWidget(0, 5)
        self.details_table.setHorizontalHeaderLabels(["怪物／地圖名稱", "ID／地圖代碼", "Lv.", "數量", "類型"])
        self.details_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.details_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.details_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.details_table.verticalHeader().setVisible(False)
        self.details_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3, 4):
            self.details_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.details_table.setMinimumHeight(155)
        self.details_table.cellDoubleClicked.connect(self.on_detail_activated)

        self._update_navigation_status()

        self.key_input = QLineEdit()
        self.key_input.setText(load_api_key_from_config())
        self.key_input.setPlaceholderText("API Key")

        self.btn_query = QPushButton("查詢詳細資料（快取／API）")
        self.btn_query.clicked.connect(self.on_query)

        self.btn_apply = QPushButton("套用")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self.on_apply)

        self.status = QLabel("")

        # 不再建立「名稱預覽」及 Lv./HP/ATK 等重複摘要欄位。
        # 名稱與分類改顯示在下方完整 JSON 的標題，避免重複佔用高度。

        # 縮圖位於下方完整 JSON 資料的右側；固定大小以免原圖撐大視窗。
        # 無圖片時隱藏標題與圖片本身，但保留固定版位防止左右跳動。
        self.sprite_section = QWidget(self)
        self.sprite_section.setFixedSize(152, 162)
        sprite_layout = QVBoxLayout(self.sprite_section)
        sprite_layout.setContentsMargins(8, 4, 8, 4)
        self.sprite_title = QLabel("怪物外型")
        self.sprite_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sprite_preview = QLabel()
        self.sprite_preview.setFixedSize(136, 136)
        self.sprite_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sprite_title.hide()
        self.sprite_preview.hide()
        sprite_layout.addWidget(self.sprite_title)
        sprite_layout.addWidget(self.sprite_preview)

        # 完整 JSON 瀏覽器（唯讀）。欄位與排序只使用上方 Python 常數設定。
        self.json_details_heading = QLabel("完整怪物資料")
        self.json_details_heading.setWordWrap(True)
        self.json_details_tree = QTreeWidget(self)
        self.json_details_tree.setColumnCount(2)
        self.json_details_tree.setHeaderLabels(["欄位", "資料"])
        self.json_details_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.json_details_tree.setMinimumHeight(105)
        self.json_details_tree.setAlternatingRowColors(True)
        self.json_details_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.json_details_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.json_details_tree.setColumnWidth(0, 270)

        # 恢復原本的快取怪物下拉清單：僅索引 data/monster/*.json，
        # 與上方 LUB 導航雙欄搜尋獨立，選擇時只將 ID 帶到查詢框。
        self.preset_box = QComboBox()
        self.preset_box.addItem("（選擇已快取的怪物）", None)
        self.preset_box.setToolTip("顯示 data/monster/*.json 中已快取的怪物")
        self.btn_refresh_presets = QPushButton("更新清單")
        self.btn_refresh_presets.setToolTip("重新掃描 data/monster 內的 JSON，不呼叫 API")
        self.btn_refresh_presets.clicked.connect(lambda _checked=False: self.refresh_presets())
        self.preset_box.currentIndexChanged.connect(self.on_preset_changed)

        # 從專案恢復已套用的怪物，不必重新查詢就能顯示原有 ID 與名稱。
        project_monster = getattr(parent, "_monster_lookup_data", None)
        if isinstance(project_monster, dict) and project_monster:
            self._last_data = dict(project_monster)
            monster_id = project_monster.get("monster_id")
            if monster_id:
                self.id_input.setText(str(monster_id))
            saved_payload = read_cached_monster_payload(monster_id) if monster_id else {}
            payload = saved_payload or project_monster
            self._show_sprite_from_url(saved_payload.get("spriteUrl") or project_monster.get("sprite_url", ""))
            self._show_monster_json(payload)
            self.status.setText("已載入專案怪物")
            self.btn_apply.setEnabled(True)

        # ID 變動必須清除上次查詢的完整資料，避免誤套用。
        self.id_input.textChanged.connect(self.on_monster_id_changed)
        form = QFormLayout()
        preset_row = QHBoxLayout()
        preset_row.addWidget(self.preset_box, 1)
        preset_row.addWidget(self.btn_refresh_presets)
        form.addRow("已快取怪物", preset_row)
        form.addRow("怪物 ID", self.id_input)
        #form.addRow("API Key", self.key_input)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_query)
        btn_row.addWidget(self.btn_apply)

        layout = QVBoxLayout(self)
        # 搜尋欄永遠放在視窗的第一排；快取選單和怪物 ID 緊接在後。
        # 查詢／套用按鈕則留在導航結果與下方完整資料區之間。
        search_row = QHBoxLayout()
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.btn_reload_navigation)
        layout.addLayout(search_row)
        layout.addWidget(self.navigation_status)
        layout.addLayout(form)

        # 中：左右並排的導航搜尋；下：查詢／套用、圖片及完整 JSON。
        # 使用垂直分隔線，可自由改變閱讀區域高度；沒有任何顯示設定 UI。
        self.main_splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.results_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        left_panel = QWidget(self.results_splitter)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.addWidget(self.search_count_label)
        left_layout.addWidget(self.search_results, 1)
        right_panel = QWidget(self.results_splitter)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.addWidget(self.details_heading)
        right_layout.addWidget(self.details_table, 1)
        self.results_splitter.addWidget(left_panel)
        self.results_splitter.addWidget(right_panel)
        self.results_splitter.setStretchFactor(0, 5)
        self.results_splitter.setStretchFactor(1, 6)
        self.results_splitter.setChildrenCollapsible(False)
        self.results_splitter.setSizes([465, 540])

        detail_panel = QWidget(self.main_splitter)
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(3)
        # 查詢／套用仍在導航搜尋與完整資料之間；不佔用圖片的高度。
        detail_layout.addLayout(btn_row)
        detail_layout.addWidget(self.json_details_heading)

        # 右側固定寬度顯示怪物外型；左側完整 JSON 資料可使用剩餘空間。
        # 圖片未載入時仍保留小欄寬，切換怪物時版面不會跳動。
        json_content_row = QHBoxLayout()
        json_content_row.setContentsMargins(0, 0, 0, 0)
        json_content_row.setSpacing(8)
        json_content_row.addWidget(self.json_details_tree, 1)
        json_content_row.addWidget(self.sprite_section, 0, Qt.AlignmentFlag.AlignTop)
        detail_layout.addLayout(json_content_row, 1)
        detail_layout.addWidget(self.status)

        self.main_splitter.addWidget(self.results_splitter)
        self.main_splitter.addWidget(detail_panel)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 6)
        self.main_splitter.setSizes([305, 485])
        layout.addWidget(self.main_splitter, 1)

        # 初始化時重新掃描所有快取，保留原本不依伺服器標籤篩選的邏輯。
        self.refresh_presets()
        self.search_input.setFocus(Qt.FocusReason.OtherFocusReason)

    # -------- JSON cache monster dropdown --------
    def refresh_presets(self, *, select_id=None):
        """重新掃描本機快取並保留目前輸入 ID；不改寫檔案、不呼叫 API。"""
        entries = load_presets()
        self._cache_entries = entries
        if select_id is None:
            try:
                select_id = int(self.id_input.text().strip())
            except (ValueError, TypeError):
                select_id = None
        self.preset_box.blockSignals(True)
        try:
            self.preset_box.clear()
            self.preset_box.addItem(f"（已快取 {len(entries)} 隻怪物）", None)
            for entry in entries:
                self.preset_box.addItem(f"{entry['name']}（{entry['id']}）", entry["id"])
            index = self.preset_box.findData(select_id) if select_id is not None else -1
            self.preset_box.setCurrentIndex(index if index >= 0 else 0)
            self.preset_box.setToolTip(
                f"所有已快取怪物：{len(entries)} 筆，來源 data/monster/*.json"
            )
        finally:
            self.preset_box.blockSignals(False)
        # The upper search field also indexes these cached records.  Updating
        # the dropdown (including after an API fetch) refreshes those results.
        if hasattr(self, "search_input") and hasattr(self, "search_results"):
            self.on_search_text_changed(self.search_input.text())

    def on_preset_changed(self, _index: int):
        """選擇快取怪物只帶入 ID；查詢詳細資料仍使用原有快取/API 流程。"""
        monster_id = self.preset_box.currentData()
        if monster_id is None:
            return
        new_id = str(monster_id)
        if self.id_input.text().strip() != new_id:
            self.id_input.setText(new_id)

    # -------- local navigation index and map/monster search --------
    def _load_navigation_index(self):
        try:
            self.navigation_index = NavigationIndex(find_navigation_dir())
            self.navigation_error = ""
        except (OSError, ValueError) as exc:
            self.navigation_index = None
            self.navigation_error = str(exc)

    def _update_navigation_status(self):
        index = self.navigation_index
        if index is None:
            self.navigation_status.setText("導航索引無法載入；快取與 API 仍可用。" + self.navigation_error)
            self.navigation_status.show()
        else:
            self.navigation_status.setToolTip(
                f"已載入 {len(index.maps)} 張地圖、{len(index.monsters)} 種怪物｜{index.data_dir}"
            )
            self.navigation_status.hide()

    def reload_navigation(self):
        """Reload both files from data/ without resetting the API workflow."""
        self._load_navigation_index()
        self._update_navigation_status()
        self.on_search_text_changed(self.search_input.text())
        if self.navigation_index is None:
            QMessageBox.warning(self, "導航資料讀取失敗", self.navigation_error)

    def on_search_text_changed(self, value: str):
        index = self.navigation_index
        self._updating_search_results = True
        try:
            self.search_results.setRowCount(0)
            self.details_table.setRowCount(0)
            self.details_heading.setText("對應地圖／怪物")
            if not value.strip():
                self.search_count_label.setText("搜尋結果")
                return
            hits, total = search_navigation_and_cache(
                index, getattr(self, "_cache_entries", []), value, limit=160,
            )
            self.search_results.setRowCount(len(hits))
            cached_ids = {int(row["id"]) for row in getattr(self, "_cache_entries", [])}
            for row, hit in enumerate(hits):
                if hit.kind == "map":
                    label = "地圖"
                elif hit.kind == "cache":
                    label = "快取怪物"
                else:
                    label = "怪物（已快取）" if int(hit.key) in cached_ids else "怪物"
                cells = (label, hit.label, hit.identifier)
                for col, cell in enumerate(cells):
                    item = QTableWidgetItem(str(cell))
                    item.setToolTip(hit.info)
                    if col == 0:
                        item.setData(Qt.ItemDataRole.UserRole, (hit.kind, hit.key))
                    self.search_results.setItem(row, col, item)
            self.search_count_label.setText(
                f"搜尋結果：{total} 筆" + (f"（前 {len(hits)} 筆）" if total > len(hits) else "")
            )
            if not hits:
                self.details_heading.setText("無符合項目")
        finally:
            self._updating_search_results = False

    def on_search_enter(self):
        if self.search_results.rowCount():
            self.search_results.selectRow(0)
            self.on_search_result_selected()

    def _left_target(self, row: int):
        item = self.search_results.item(row, 0)
        if item is None:
            return None
        target = item.data(Qt.ItemDataRole.UserRole)
        return target if isinstance(target, (list, tuple)) and len(target) == 2 else None

    def on_search_result_selected(self):
        if self._updating_search_results:
            return
        target = self._left_target(self.search_results.currentRow())
        if target is None:
            return
        kind, key = target
        if kind in ("monster", "cache"):
            # Single-click reveals LUB spawn maps (when available), not API data.
            self._show_monster_locations(int(key))
        elif kind == "map":
            self._show_map_monsters(str(key))

    def on_search_result_activated(self, row: int, _column: int):
        target = self._left_target(row)
        if target is None:
            return
        kind, key = target
        if kind in ("monster", "cache"):
            self._activate_monster(int(key))
        elif kind == "map":
            self._show_map_monsters(str(key))

    def _activate_monster(self, monster_id: int):
        """Double-click monster: copy ID to the lookup box and query JSON/API."""
        if not self.btn_query.isEnabled():
            return  # Do not create a second concurrent API worker.
        monster_id = int(monster_id)
        if monster_id <= 0:
            return
        if self.id_input.text().strip() != str(monster_id):
            self.id_input.setText(str(monster_id))
        self.on_query()

    def _set_detail_rows(self, entries):
        """Render (name, identifier, level, count, kind, navigation_target)."""
        self.details_table.setRowCount(len(entries))
        for row, (name, identifier, level, count, kind, target) in enumerate(entries):
            for col, value in enumerate((name, identifier, level, count, kind)):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, target)
                self.details_table.setItem(row, col, item)

    def _show_map_monsters(self, map_code: str):
        index = self.navigation_index
        if index is None:
            return
        # Map selection is not a monster selection. Discard any previously
        # fetched monster so the user cannot accidentally apply stale data.
        if self.id_input.text():
            self.id_input.clear()
        entries = index.map_monsters(map_code)
        self.details_heading.setText(
            f"{index.map_name(map_code)}（{map_code}）｜{len(entries)} 種怪物"
        )
        self.details_table.setHorizontalHeaderLabels(["怪物名稱", "怪物 ID", "Lv.", "數量", "類型"])
        self._set_detail_rows([
            (entry.name, entry.monster_id, entry.level,
             entry.count if entry.count > 0 else "—", "MVP" if entry.is_mvp else "一般",
             ("monster", entry.monster_id))
            for entry in entries
        ])
        if not entries:
            self.status.setText("這張地圖在 navi_mob_tw.lub 中沒有怪物紀錄")

    def _show_monster_locations(self, monster_id: int):
        index = self.navigation_index
        monster = index.monsters.get(monster_id) if index is not None else None
        if monster is None:
            cached = next((row for row in getattr(self, "_cache_entries", [])
                           if int(row["id"]) == monster_id), None)
            name = cached["name"] if cached else str(monster_id)
            self.details_heading.setText(f"{name}（{monster_id}）｜無導航地圖紀錄")
            self.details_table.setHorizontalHeaderLabels(["地圖名稱", "地圖代碼", "Lv.", "數量", "類型"])
            self.details_table.setRowCount(0)
            return
        entries = index.monster_maps(monster_id)
        self.details_heading.setText(
            f"{monster.name}（{monster_id}）｜{len(entries)} 張出現地圖"
        )
        self.details_table.setHorizontalHeaderLabels(["地圖名稱", "地圖代碼", "Lv.", "數量", "類型"])
        self._set_detail_rows([
            (index.map_name(entry.map_code), entry.map_code, entry.level,
             entry.count if entry.count > 0 else "—", "MVP" if entry.is_mvp else "一般",
             ("map", entry.map_code))
            for entry in entries
        ])

    def on_detail_activated(self, row: int, _column: int):
        item = self.details_table.item(row, 0)
        if item is None:
            return
        target = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(target, (list, tuple)) or len(target) != 2:
            return
        kind, key = target
        if kind in ("monster", "cache"):
            self._activate_monster(int(key))
        elif kind == "map":
            self._show_map_monsters(str(key))

    def _show_monster_json(self, payload: dict | None = None):
        """依 .py 的篩選/排序設定，逐層顯示 JSON 裡所有允許的欄位。"""
        self.json_details_tree.clear()
        if not isinstance(payload, dict) or not payload:
            self.json_details_heading.setText("完整怪物資料（無快取，可查詢 API）")
            return
        # 曾顯示於「名稱預覽」的屬性／體型／種族／階級移至 JSON 標題。
        # 不再顯示另一排重複的 HP/ATK/六大素質。
        self.json_details_heading.setText(monster_name_with_traits(payload) or "完整怪物資料")
        tree = self.json_details_tree
        tree.setUpdatesEnabled(False)
        try:
            count = [0]

            def append_item(parent, name: str, value, path: str, depth: int):
                if count[0] >= MONSTER_DETAIL_MAX_TREE_NODES:
                    return
                count[0] += 1
                item = QTreeWidgetItem(parent, [_display_field_name(name), _json_summary(value)])
                item.setToolTip(0, path)
                if not isinstance(value, (dict, list)):
                    item.setToolTip(1, _pretty_json_value(value))
                if depth >= 32:
                    if isinstance(value, (dict, list)):
                        QTreeWidgetItem(item, ["…", "巢狀層數過深"]) 
                    return
                if isinstance(value, dict):
                    for key, sub in _ordered_json_items(value, path):
                        append_item(item, str(key), sub, f"{path}.{key}", depth+1)
                elif isinstance(value, list):
                    for n, sub in enumerate(value):
                        subpath = f"{path}.*"
                        if _match_path(subpath, MONSTER_DETAIL_HIDDEN_PATHS):
                            continue
                        label = f"[{n+1}]"
                        if isinstance(sub, dict):
                            meaningful = sub.get("skillName") or sub.get("itemName") or sub.get("mapDisplayName")
                            if meaningful:
                                label += f" {meaningful}"
                        append_item(item, label, sub, subpath, depth+1)
                if depth == 0 and name in MONSTER_DETAIL_EXPAND_TOP_LEVEL:
                    item.setExpanded(True)

            for key, value in _ordered_json_items(payload):
                append_item(tree, str(key), value, str(key), 0)
            if count[0] >= MONSTER_DETAIL_MAX_TREE_NODES:
                QTreeWidgetItem(tree, ["…", "資料量已達介面保護上限，未顯示後續節點"])
        finally:
            tree.setUpdatesEnabled(True)

    def on_monster_id_changed(self, _text: str):
        """Invalidate the prior full record whenever the manual ID is changed."""
        try:
            selected_id = int(str(_text).strip())
        except (ValueError, TypeError):
            selected_id = None
        # 同步下拉快取清單，但避免 currentIndexChanged 再回頭修改 ID。
        index = self.preset_box.findData(selected_id) if selected_id is not None else -1
        self.preset_box.blockSignals(True)
        try:
            self.preset_box.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self.preset_box.blockSignals(False)
        self._last_data = None
        self.btn_apply.setEnabled(False)
        self._clear_sprite()
        # 切換怪物時改直接更新下方完整 JSON；本機有快取便不呼叫 API。
        cached_payload = read_cached_monster_payload(selected_id) if selected_id is not None else {}
        self._show_monster_json(cached_payload)
        if cached_payload:
            self._show_sprite_from_url(cached_payload.get("spriteUrl", ""))
        local = (self.navigation_index.monsters.get(selected_id)
                 if self.navigation_index is not None and selected_id is not None else None)
        if cached_payload:
            self.status.setText("已載入本機 JSON 快取，可直接查看完整怪物資料")
        elif local is not None:
            self.status.setText("已帶入本機怪物 ID；可查詢 JSON 快取／API 詳細資料")
        elif selected_id is not None:
            self.status.setText("怪物 ID 已變更，請重新查詢")
        else:
            self.status.setText("請搜尋或輸入怪物 ID")

    # -------- logic --------
    def on_query(self):

        if not self.btn_query.isEnabled():
            return
        # 工作訊號可能比 QThread.finished 早抵達 UI；禁止重疊建立執行緒。
        if self._has_running_fetch():
            self.status.setText("上一筆查詢正在結束，請稍後再試")
            return
        try:
            monster_id = int(self.id_input.text())
        except ValueError:
            QMessageBox.warning(self, "錯誤", "怪物ID 必須是數字")
            return

        api_key = self.key_input.text().strip()

        self._query_monster_id = monster_id
        self.status.setText("查詢中...")
        self.btn_query.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.id_input.setEnabled(False)
        self.preset_box.setEnabled(False)
        self.btn_refresh_presets.setEnabled(False)
        self.search_input.setEnabled(False)
        self.search_results.setEnabled(False)
        self.details_table.setEnabled(False)
        self.btn_reload_navigation.setEnabled(False)

        fetch_thread = QThread(self)
        fetch_worker = MonsterFetchWorker(
            monster_id, api_key, language=MONSTER_API_LANGUAGE,
            server=MONSTER_API_SERVER
        )
        self._fetch_threads.append(fetch_thread)
        # 防止 run() 執行期間 Python 提前回收沒有 Qt parent 的 worker。
        self._fetch_workers[fetch_thread] = fetch_worker
        fetch_worker.moveToThread(fetch_thread)
        fetch_thread.started.connect(fetch_worker.run)

        fetch_worker.finished.connect(fetch_thread.quit)
        fetch_worker.finished.connect(fetch_worker.deleteLater)

        # 成功或失敗均結束工作執行緒，避免視窗關閉時背景執行緒殘留。
        fetch_worker.error.connect(fetch_thread.quit)
        fetch_worker.error.connect(fetch_worker.deleteLater)

        # finished 後移除追蹤，然後讓 Qt 安全釋放該執行緒。
        fetch_thread.finished.connect(self._on_fetch_thread_finished)
        fetch_thread.finished.connect(fetch_thread.deleteLater)

        fetch_worker.finished.connect(self.on_fetched)
        fetch_worker.error.connect(self.on_error)

        fetch_thread.start()

    @Slot()
    def _on_fetch_thread_finished(self):
        """在主 UI 執行緒移除已完成的 QThread 追蹤。"""
        finished_thread = self.sender()
        if finished_thread in self._fetch_threads:
            self._fetch_threads.remove(finished_thread)
        self._fetch_workers.pop(finished_thread, None)

    def _has_running_fetch(self) -> bool:
        """只檢查自己建立的執行緒；不會誤取 QObject.thread()。"""
        for fetch_thread in tuple(self._fetch_threads):
            try:
                if fetch_thread.isRunning():
                    return True
            except RuntimeError:
                # Qt 可能已釋放舊 QThread；忽略失效的 Python 包裝物件。
                if fetch_thread in self._fetch_threads:
                    self._fetch_threads.remove(fetch_thread)
                self._fetch_workers.pop(fetch_thread, None)
        return False

    def on_error(self, msg: str):
        self.id_input.setEnabled(True)
        self.preset_box.setEnabled(True)
        self.btn_refresh_presets.setEnabled(True)
        self.search_input.setEnabled(True)
        self.search_results.setEnabled(True)
        self.details_table.setEnabled(True)
        self.btn_reload_navigation.setEnabled(True)
        self.btn_query.setEnabled(True)
        self.btn_apply.setEnabled(False)   # <<< 重要：錯誤就不允許套用
        self._last_data = None             # <<< 重要：清掉上一次成功資料，避免誤套用
        self._clear_sprite()
        self._show_monster_json()
        self.status.setText("查詢失敗")
        QMessageBox.critical(self, "API 錯誤", msg)



    def on_fetched(self, data: dict):
        self.id_input.setEnabled(True)
        self.preset_box.setEnabled(True)
        self.btn_refresh_presets.setEnabled(True)
        self.search_input.setEnabled(True)
        self.search_results.setEnabled(True)
        self.details_table.setEnabled(True)
        self.btn_reload_navigation.setEnabled(True)
        self.btn_query.setEnabled(True)

        parsed = self.parse_monster(data)
        # 部分 API 回應未包含 ID；使用者輸入的 ID 才是這次查詢的對象。
        if not parsed.get("monster_id"):
            parsed["monster_id"] = self._query_monster_id
        parsed["api_server"] = data.get("_request_server", data.get("region") or MONSTER_API_SERVER)
        parsed["api_language"] = data.get("_request_language", MONSTER_API_LANGUAGE)
        # 此欄位隨專案儲存；再次開啟查詢視窗也能恢復外型預覽。
        # 若 API 無圖片 URL，就不新增欄位也不顯示圖片。
        sprite_url = validated_sprite_url(data.get("spriteUrl"))
        if sprite_url:
            parsed["sprite_url"] = sprite_url
        # 保留在專案資料中，讓重新開啟對話框也能顯示先前查到的數值。
        # 只保存解析到的原始欄位，不額外推算缺少的數值。
        full_stats = extract_monster_stats(data)
        if full_stats:
            parsed["monster_stats"] = full_stats
        self._last_data = parsed

        self._show_monster_json(data)
        # 新下載的 JSON 立即加入快取選單，仍使用原本平面目錄。
        self.refresh_presets(select_id=parsed["monster_id"])
        self._show_sprite_from_url(sprite_url)
        src = "快取" if data.get("_from_cache") else "API"
        server = parsed["api_server"]
        if has_chinese_characters(parsed["name"]):
            self.status.setText(f"查詢完成（{src}｜{server}｜中文名稱）")
        else:
            self.status.setText(
                f"查詢完成（{src}｜{server}），但 API 未提供中文名稱，已保留原始名稱"
            )
        self.btn_apply.setEnabled(True)

    def _clear_sprite(self):
        """查詢目標切換時，立即隱藏舊圖並取消未完成的網路請求。"""
        reply = self._sprite_reply
        self._sprite_reply = None
        self.sprite_preview.clear()
        self.sprite_preview.hide()
        self.sprite_title.hide()
        if reply is not None:
            try:
                if reply.isRunning():
                    reply.abort()
            except RuntimeError:
                pass  # Qt 已自動清除舊回應。
            # reply 的 finished 處理器會在之後 deleteLater。

    def _show_sprite_from_url(self, url):
        """只在有可用 spriteUrl 時非同步請求圖片；不阻塞怪物資料套用。"""
        self._clear_sprite()
        url = validated_sprite_url(url)
        if not url:
            return
        request = QNetworkRequest(QUrl(url))
        # 部分 Qt / 圖片伺服器組合會出現 HTTP/2 HPACK 解壓錯誤。
        # 僅對此處的怪物圖片請求改用 HTTP/1.1，不影響 requests 的 API 查詢。
        request.setAttribute(QNetworkRequest.Attribute.Http2AllowedAttribute, False)
        # 並非 API 查詢：靜態圖片不計入 API 的每秒請求限流。
        request.setTransferTimeout(10000)
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        reply = self._sprite_manager.get(request)
        self._sprite_reply = reply
        reply.finished.connect(lambda r=reply: self._on_sprite_finished(r))

    def _on_sprite_finished(self, reply):
        try:
            # 較舊請求完成時不准覆蓋最新查詢結果。
            if reply is not self._sprite_reply:
                return
            self._sprite_reply = None
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            # 保護記憶體：不讀入過大的影像檔案。
            if reply.bytesAvailable() > 4 * 1024 * 1024:
                return
            raw = bytes(reply.readAll())
            if not raw or len(raw) > 4 * 1024 * 1024:
                return
            pixmap = QPixmap()
            if not pixmap.loadFromData(raw) or pixmap.isNull():
                return
            # 僅縮小、不放大：保留原尺寸較小怪物圖，並維持長寬比。
            bounds = self.sprite_preview.size()
            target_width = min(pixmap.width(), bounds.width())
            target_height = min(pixmap.height(), bounds.height())
            self.sprite_preview.setPixmap(pixmap.scaled(
                target_width, target_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
            self.sprite_title.show()
            self.sprite_preview.show()
        finally:
            reply.deleteLater()

    def on_apply(self):
        # 即使已收到資料，背景執行緒仍可能正在退出事件迴圈。
        if self._has_running_fetch():
            self.status.setText("API 查詢正在結束，請稍後再套用")
            return
        if self._last_data:
            self._clear_sprite()
            self.monsterSelected.emit(self._last_data)
            self.accept()

    def reject(self):
        # QDialog 的 Esc / reject() 不一定經過 closeEvent，需一併保護。
        if self._has_running_fetch():
            self.status.setText("API 查詢進行中，查詢結束後可關閉視窗")
            return
        self._clear_sprite()
        super().reject()

    def closeEvent(self, event):
        # 僅檢查自己追蹤的 QThread，避免與 QObject.thread() 同名衝突。
        if self._has_running_fetch():
            event.ignore()
            self.status.setText("API 查詢進行中，查詢結束後可關閉視窗")
            return
        self._clear_sprite()
        super().closeEvent(event)

    # -------- parse --------
    def parse_monster(self, data: dict) -> dict:
        return _core_stage18_parse_monster_payload(data)
