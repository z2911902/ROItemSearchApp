"""Pure-Python Ragnarok Online RRF v5 reader.

This module replaces the old RagnarokReplayExample.exe -> TXT stage.
It parses the replay directly and exposes decrypted PacketStream packets as bytes.

Incremental strategy (v1): each changed RRF is parsed from its current snapshot, but
only packets after the last stable packet are emitted. If the stream was rewritten
or truncated, poll() automatically falls back to mode='full'. This is deliberately
safer for live-recording RRF files than assuming the file itself is append-only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import os
import struct
from typing import Dict, Iterable, List, Optional, Tuple


class RRFError(Exception):
    pass


CONTAINER_NAMES = {
    0: "None",
    1: "PacketStream",
    2: "ReplayData",
    3: "Session",
    4: "Status",
    6: "Quests",
    7: "GroupAndFriends",
    8: "Items",
    9: "UnknownContainingPet",
    10: "Unknown_10",
    12: "Unknown_12",
    13: "Unknown_13",
    14: "InitialPackets",
    15: "Unknown_15",
    16: "Unknown_16",
    17: "Efst",
    18: "Unknown_18",
    19: "Unknown_19",
    20: "Unknown_20",
    21: "Unknown_21",
    22: "Unknown_22",
    23: "Unknown_23",
    24: "Unknown_24",
}

# Packet names used by RRF_compile_damage_view.py.  IDs follow the packet names
# used by the original C# parser / rAthena-style packet headers.
PACKET_NAMES = {
    0x0080: "HEADER_ZC_NOTIFY_VANISH",
    0x00B0: "HEADER_ZC_PAR_CHANGE",
    0x0117: "HEADER_ZC_NOTIFY_GROUNDSKILL",
    0x0141: "HEADER_ZC_COUPLESTATUS",
    0x0196: "HEADER_ZC_MSG_STATE_CHANGE",
    0x01DE: "HEADER_ZC_NOTIFY_SKILL2",
    0x02E1: "HEADER_ZC_NOTIFY_ACT3",
    0x043F: "HEADER_ZC_MSG_STATE_CHANGE2",
    0x0915: "HEADER_ZC_NOTIFY_MOVEENTRY11",
    0x0983: "HEADER_ZC_MSG_STATE_CHANGE3",
    0x09FD: "HEADER_ZC_NOTIFY_NEWENTRY11",
    0x09FE: "HEADER_ZC_NOTIFY_STANDENTRY11",
    0x0ADD: "HEADER_物品掉落",
}


@dataclass(slots=True)
class ReplayHeader:
    version: int
    signature: bytes
    date: datetime
    date_unused: int
    prefix: bytes


@dataclass(slots=True)
class ContainerDescriptor:
    index: int
    container_type: int
    length: int
    offset: int
    real_length: int

    @property
    def name(self) -> str:
        return CONTAINER_NAMES.get(self.container_type, f"Unknown_{self.container_type}")


@dataclass(slots=True)
class ReplayChunk:
    container_type: int
    container_name: str
    chunk_id: int
    data: bytes
    index: int


@dataclass(slots=True)
class RawPacket:
    record_id: int
    time_ms: int
    data: bytes
    header: int
    index: int
    stream_offset: int

    @property
    def length(self) -> int:
        return len(self.data)

    @property
    def packet_name(self) -> str:
        return PACKET_NAMES.get(self.header, f"HEADER_0x{self.header:04X}")

    @property
    def timestamp(self) -> str:
        return ms_to_timestamp(self.time_ms)

    def fingerprint(self) -> Tuple[int, int, int, int, bytes]:
        # The short digest keeps prefix validation cheap while still detecting a
        # rewritten live stream with overwhelming probability.
        digest = hashlib.blake2s(self.data, digest_size=8).digest()
        return (self.record_id, self.time_ms, self.header, len(self.data), digest)


@dataclass(slots=True)
class ReplaySnapshot:
    path: str
    file_size: int
    mtime_ns: int
    header: ReplayHeader
    containers: List[ContainerDescriptor]
    packets: List[RawPacket]
    chunks: List[ReplayChunk]
    partial_packet: bool = False
    partial_chunk: bool = False

    def chunks_for(self, container_type: int) -> List[ReplayChunk]:
        return [c for c in self.chunks if c.container_type == container_type]


@dataclass(slots=True)
class ReplayDelta:
    mode: str  # full / delta / none
    path: str
    packets: List[RawPacket] = field(default_factory=list)
    snapshot: Optional[ReplaySnapshot] = None
    reason: str = ""

    @property
    def has_changes(self) -> bool:
        return self.mode != "none" and bool(self.packets or self.snapshot)

    def to_legacy_text(self, include_metadata: bool = True) -> str:
        """Temporary in-memory adapter for the existing TXT-oriented analyzer.

        No TXT file is written. Packet bytes come directly from the RRF reader.
        The output only mimics the small subset of RagnarokReplayExample text
        that the current analyzer's regex functions consume.
        """
        blocks: List[str] = []
        if include_metadata and self.snapshot is not None:
            blocks.extend(_metadata_legacy_blocks(self.snapshot))
        blocks.extend(_packet_legacy_block(p) for p in self.packets)
        return "".join(blocks)


class RRFReader:
    HEADER_SIZE = 112
    CONTAINER_COUNT = 24
    DESCRIPTOR_SIZE = 10

    def read(self, path: str) -> ReplaySnapshot:
        path = os.path.abspath(path)
        st = os.stat(path)
        file_size = st.st_size
        if file_size < self.HEADER_SIZE:
            raise RRFError(f"RRF 尚未寫完整 header（目前 {file_size} bytes）")

        # A live RRF can change while being read. Reading a byte snapshot keeps
        # all offsets internally consistent without copying to another file.
        with open(path, "rb") as f:
            blob = f.read()

        file_size = len(blob)
        header = self._read_header(blob)
        if header.version != 5:
            raise RRFError(f"目前只支援 RRF version 5，檔案版本是 {header.version}")

        desc_end = self.HEADER_SIZE + self.CONTAINER_COUNT * self.DESCRIPTOR_SIZE
        if file_size < desc_end:
            raise RRFError(f"RRF container table 尚未寫完整（需要至少 {desc_end} bytes）")

        containers: List[ContainerDescriptor] = []
        packets: List[RawPacket] = []
        chunks: List[ReplayChunk] = []
        partial_packet = False
        partial_chunk = False

        pos = self.HEADER_SIZE
        for idx in range(self.CONTAINER_COUNT):
            ctype, length, offset = struct.unpack_from("<Hii", blob, pos)
            pos += self.DESCRIPTOR_SIZE
            if length < 0:
                # A half-written descriptor should not make us seek backwards or
                # allocate nonsense. Keep it visible but skip parsing this poll.
                real_length = 0
            elif length == 0 and offset > 0:
                real_length = max(0, file_size - offset)
            else:
                real_length = length

            desc = ContainerDescriptor(idx, ctype, length, offset, real_length)
            containers.append(desc)

            if offset <= 0 or offset >= file_size or real_length <= 0:
                continue

            available = min(real_length, file_size - offset)
            if available <= 0:
                continue
            content = blob[offset : offset + available]

            if ctype == 1:
                pp = self._read_packet_stream(content, header.date, packets)
                partial_packet = partial_packet or pp or (available < real_length)
            else:
                # The original implementation decrypts exactly container.Length
                # bytes for non-packet containers. A zero Length is an open-ended
                # packet-stream convention; treating it as metadata would be unsafe.
                if length <= 0:
                    continue
                decrypt_len = min(length, len(content))
                decrypted = crypt_rrf(header.date, content[:decrypt_len], decrypt_len)
                pc = self._read_chunks(decrypted, ctype, chunks)
                partial_chunk = partial_chunk or pc or (available < real_length)

        return ReplaySnapshot(
            path=path,
            file_size=file_size,
            mtime_ns=st.st_mtime_ns,
            header=header,
            containers=containers,
            packets=packets,
            chunks=chunks,
            partial_packet=partial_packet,
            partial_chunk=partial_chunk,
        )

    @staticmethod
    def _read_header(blob: bytes) -> ReplayHeader:
        prefix = blob[:100]
        version = blob[100]
        signature = blob[101:104]
        year = struct.unpack_from("<h", blob, 104)[0]
        month = blob[106]
        day = blob[107]
        date_unused = blob[108]
        hour = blob[109]
        minute = blob[110]
        second = blob[111]
        try:
            date = datetime(year, month, day, hour, minute, second)
        except ValueError as exc:
            raise RRFError(
                f"RRF 日期欄位無效: {year:04d}-{month:02d}-{day:02d} "
                f"{hour:02d}:{minute:02d}:{second:02d}"
            ) from exc
        return ReplayHeader(version, signature, date, date_unused, prefix)

    @staticmethod
    def _read_packet_stream(content: bytes, date: datetime, out: List[RawPacket]) -> bool:
        pos = 0
        index = len(out)
        partial = False
        n = len(content)
        while pos < n:
            if n - pos < 10:
                partial = True
                break
            record_id, time_ms, length = struct.unpack_from("<iiH", content, pos)
            data_pos = pos + 10
            end = data_pos + length
            if end > n:
                partial = True
                break
            encrypted = content[data_pos:end]
            data = crypt_rrf(date, encrypted, length)
            if len(data) < 2:
                # Valid framing but not a usable RO packet; preserve it anyway.
                header = 0
            else:
                header = struct.unpack_from("<H", data, 0)[0]
            out.append(RawPacket(record_id, time_ms, data, header, index, pos))
            index += 1
            pos = end
        return partial

    @staticmethod
    def _read_chunks(content: bytes, ctype: int, out: List[ReplayChunk]) -> bool:
        pos = 0
        idx = 0
        n = len(content)
        partial = False
        cname = CONTAINER_NAMES.get(ctype, f"Unknown_{ctype}")
        while pos < n:
            if n - pos < 6:
                partial = True
                break
            chunk_id, length = struct.unpack_from("<hi", content, pos)
            if length < 0:
                partial = True
                break
            data_pos = pos + 6
            end = data_pos + length
            if end > n:
                partial = True
                break
            out.append(ReplayChunk(ctype, cname, chunk_id, content[data_pos:end], idx))
            idx += 1
            pos = end
        return partial


class RRFIncrementalReader:
    """Stateful result-level incremental reader for a live RRF file."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self._reader = RRFReader()
        self._last_stat: Optional[Tuple[int, int]] = None
        self._last_packet_count = 0
        self._last_anchor: Optional[Tuple[int, int, int, int, bytes]] = None
        self._identity: Optional[Tuple[bytes, int, datetime]] = None

    def reset(self, path: Optional[str] = None) -> None:
        if path is not None:
            self.path = os.path.abspath(path)
        self._last_stat = None
        self._last_packet_count = 0
        self._last_anchor = None
        self._identity = None

    def poll(self, force: bool = False) -> ReplayDelta:
        st = os.stat(self.path)
        stat_sig = (st.st_size, st.st_mtime_ns)
        if not force and self._last_stat == stat_sig:
            return ReplayDelta("none", self.path, reason="RRF 未變動")

        snapshot = self._reader.read(self.path)
        identity = (snapshot.header.signature, snapshot.header.version, snapshot.header.date)
        mode = "full"
        reason = "首次解析"
        start = 0

        if self._identity == identity and self._last_anchor is not None:
            if len(snapshot.packets) >= self._last_packet_count and self._last_packet_count > 0:
                current_anchor = snapshot.packets[self._last_packet_count - 1].fingerprint()
                if current_anchor == self._last_anchor:
                    mode = "delta"
                    start = self._last_packet_count
                    reason = "PacketStream 前綴未變，僅回傳新增封包"
                else:
                    reason = "PacketStream 已被改寫，回退 full"
            else:
                reason = "PacketStream 變短/重建，回退 full"
        elif self._identity == identity and self._last_packet_count == 0:
            mode = "delta"
            start = 0
            reason = "先前沒有完整封包"
        elif self._identity is not None:
            reason = "Replay identity 改變，回退 full"

        packets = snapshot.packets[start:] if mode == "delta" else snapshot.packets

        self._last_stat = stat_sig
        self._identity = identity
        self._last_packet_count = len(snapshot.packets)
        self._last_anchor = snapshot.packets[-1].fingerprint() if snapshot.packets else None

        # Even with zero new PacketStream packets, a changed RRF may contain
        # updated Session / Group / Efst metadata. Keep it as delta so the
        # analyzer can refresh those maps without replaying old damage packets.
        if mode == "delta" and not packets:
            reason = "RRF metadata 有變；沒有新的完整 PacketStream 封包"
        return ReplayDelta(mode, self.path, packets, snapshot, reason)


def _i32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value


def crypt_rrf(date: datetime, buffer: bytes, size: Optional[int] = None) -> bytes:
    """Mirror the C# RRF XOR transform, including signed Int32 overflow."""
    if size is None:
        size = len(buffer)
    size = max(0, min(size, len(buffer)))
    if size == 0:
        return b""

    key1_bytes = struct.pack("<hBB", date.year, date.month, date.day)
    key1 = struct.unpack("<i", key1_bytes)[0]
    key2 = struct.unpack("<i", bytes((0, date.hour, date.minute, date.second)))[0]
    real_key1 = key1 >> 5
    real_key2 = key2 >> 3

    src = memoryview(buffer)[:size]
    out = bytearray(size)
    word_count = size // 4
    for cursor in range(word_count):
        off = cursor * 4
        old = struct.unpack_from("<i", src, off)[0]
        addend = _i32(real_key1 + cursor + 1)
        product = _i32(addend * real_key2)
        value = _i32(old ^ product)
        struct.pack_into("<i", out, off, value)
    tail = word_count * 4
    out[tail:] = src[tail:size]
    return bytes(out)


def ms_to_timestamp(ms: int) -> str:
    # C# TimeSpan-style output used by the existing analyzer.
    if ms < 0:
        ms = 0
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1_000)
    return f"+{hours:02d}:{minutes:02d}:{seconds:02d}:{millis:03d}"


def _hexdump(data: bytes) -> str:
    lines = []
    for off in range(0, len(data), 16):
        chunk = data[off:off + 16]
        hx = " ".join(f"{b:02X}" for b in chunk)
        lines.append(f"{off:04X}  {hx} \n")
    return "".join(lines)


def _packet_legacy_block(packet: RawPacket) -> str:
    return (
        f"[{packet.timestamp}] packet {packet.packet_name}\n"
        f"[0x{packet.header:08X} ({packet.length})] {{\n"
        f"{_hexdump(packet.data)}"
        "}\n"
    )


def _chunk_legacy_block(container_name: str, opcode_name: str, data: bytes) -> str:
    # The current analyzer accepts either a 'Raw hex:' marker (ReplayData/Session)
    # or directly the [0x... (len)] block (Group/Efst). Include both; its regexes
    # intentionally skip across text until the byte block they need.
    return (
        f"[Chunk {container_name}] Unparsed opcode {opcode_name}, Length={len(data)}\n"
        "Raw hex:\n"
        f"[0x00000000 ({len(data)})] {{\n"
        f"{_hexdump(data)}"
        "}\n"
    )


def _metadata_legacy_blocks(snapshot: ReplaySnapshot) -> List[str]:
    """Synthesize only metadata records consumed by the existing analyzer.

    This adapter uses stable structural facts from the original parser where
    possible: ReplayData[4]=character name, ReplayData[5]=map name and
    Session[1]=player AID. GroupInfo is detected by its embedded 0x00FB member
    marker. Efst-container chunks are exposed as EfstInfo candidates.
    """
    blocks: List[str] = []

    replay_data = snapshot.chunks_for(2)
    if len(replay_data) > 4:
        blocks.append(_chunk_legacy_block("ReplayData", "Charactername", replay_data[4].data))
    if len(replay_data) > 5:
        blocks.append(_chunk_legacy_block("ReplayData", "Mapname", replay_data[5].data))

    session = snapshot.chunks_for(3)
    if len(session) > 1:
        blocks.append(_chunk_legacy_block("Session", "Aid", session[1].data))

    for chunk in snapshot.chunks_for(7):
        # GroupInfo payloads in the existing analyzer are split on FB 00.
        if b"\xFB\x00" in chunk.data:
            blocks.append(_chunk_legacy_block("GroupAndFriends", "GroupInfo", chunk.data))

    for chunk in snapshot.chunks_for(17):
        if len(chunk.data) >= 2:
            blocks.append(_chunk_legacy_block("Efst", "EfstInfo", chunk.data))

    return blocks
