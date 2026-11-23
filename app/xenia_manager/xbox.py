"""Reading Title IDs and metadata from Xbox 360 files.

Written from public format documentation (Free60 wiki: STFS, XEX2, XDVDFS).
No code is taken from other projects.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Optional

SECTOR = 2048
XDVDFS_MAGIC = b"MICROSOFT*XBOX*MEDIA"
# Game partition offsets: rebuilt/plain, XGD2, XGD3, XGD1
ISO_PARTITIONS = (0x0, 0xFD90000, 0x2080000, 0x18300000)
STFS_MAGICS = (b"CON ", b"LIVE", b"PIRS")

CONTENT_TYPES = {
    0x00000001: "Saved game",
    0x00000002: "DLC",
    0x00000003: "Publisher content",
    0x00004000: "Installed game",
    0x00007000: "Games on Demand",
    0x00080000: "Game demo",
    0x000B0000: "Title update",
    0x000D0000: "Arcade title",
    0x00009000: "Avatar item",
    0x00020000: "Gamer picture",
    0x00030000: "Theme",
}
TYPE_SAVE = 0x00000001
TYPE_DLC = 0x00000002
TYPE_TU = 0x000B0000

_TITLE_RE = re.compile(r"[\[(]?\b([0-9A-Fa-f]{8})\b[\])]?")


@dataclass
class StfsInfo:
    magic: str
    title_id: str
    content_type: int
    display_name: str
    title_name: str
    version: int
    base_version: int

    @property
    def type_hex(self) -> str:
        return f"{self.content_type:08X}"

    @property
    def type_label(self) -> str:
        return CONTENT_TYPES.get(self.content_type, f"Type {self.type_hex}")


def _utf16(raw: bytes) -> str:
    try:
        text = raw.decode("utf-16-be", errors="ignore")
    except Exception:
        return ""
    return text.split("\x00", 1)[0].strip()


def read_stfs(path: Path) -> Optional[StfsInfo]:
    """Parse the header of a CON/LIVE/PIRS package (DLC, TU, GoD, XBLA, saves)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(0x1800)
    except OSError:
        return None
    if len(head) < 0x1700 or head[:4] not in STFS_MAGICS:
        return None
    content_type = struct.unpack_from(">I", head, 0x344)[0]
    version, base_version = struct.unpack_from(">II", head, 0x358)  # media id sits at 0x354
    title_id = struct.unpack_from(">I", head, 0x360)[0]
    return StfsInfo(
        magic=head[:4].decode("ascii").strip(),
        title_id=f"{title_id:08X}",
        content_type=content_type,
        display_name=_utf16(head[0x411:0x411 + 0x80]),
        title_name=_utf16(head[0x1691:0x1691 + 0x80]),
        version=version,
        base_version=base_version,
    )


def _xex_title_id(header: bytes) -> Optional[str]:
    if len(header) < 0x18 or header[:4] != b"XEX2":
        return None
    count = struct.unpack_from(">I", header, 0x14)[0]
    for i in range(min(count, 64)):
        off = 0x18 + i * 8
        if off + 8 > len(header):
            break
        key, value = struct.unpack_from(">II", header, off)
        if key == 0x00040006:  # execution info
            if value + 16 > len(header):
                return None
            title = struct.unpack_from(">I", header, value + 12)[0]
            return f"{title:08X}"
    return None


def read_xex(path: Path) -> Optional[str]:
    try:
        with open(path, "rb") as fh:
            head = fh.read(0x10000)
    except OSError:
        return None
    return _xex_title_id(head)


def _read_at(fh: BinaryIO, offset: int, size: int) -> bytes:
    fh.seek(offset)
    return fh.read(size)


def _xdvdfs_entries(table: bytes) -> list[tuple[str, int, int, int]]:
    """Return (name, sector, size, attributes) for a directory table."""
    out: list[tuple[str, int, int, int]] = []
    seen: set[int] = set()
    stack = [0]
    while stack:
        pos = stack.pop()
        if pos in seen or pos + 14 > len(table):
            continue
        seen.add(pos)
        left, right, sector, size, attrib, namelen = struct.unpack_from("<HHIIBB", table, pos)
        if left == 0xFFFF and right == 0xFFFF:
            continue
        name = table[pos + 14:pos + 14 + namelen].decode("latin-1", errors="ignore")
        out.append((name, sector, size, attrib))
        if left and left != 0xFFFF:
            stack.append(left * 4)
        if right and right != 0xFFFF:
            stack.append(right * 4)
    return out


def read_iso(path: Path) -> Optional[str]:
    """Find default.xex in an Xbox 360 disc image and return its Title ID."""
    try:
        with open(path, "rb") as fh:
            for base in ISO_PARTITIONS:
                vd = _read_at(fh, base + 32 * SECTOR, 32)
                if vd[:20] != XDVDFS_MAGIC:
                    continue
                root_sector, root_size = struct.unpack_from("<II", vd, 20)
                if not root_size or root_size > 64 * 1024 * 1024:
                    continue
                table = _read_at(fh, base + root_sector * SECTOR, root_size)
                for name, sector, size, _attr in _xdvdfs_entries(table):
                    if name.lower() == "default.xex":
                        head = _read_at(fh, base + sector * SECTOR, min(size, 0x10000))
                        tid = _xex_title_id(head)
                        if tid:
                            return tid
    except OSError:
        return None
    return None


def resolve_playlist(path: Path) -> Path:
    """`.xbox360` files name the real game file on their first line."""
    try:
        first = path.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip().lstrip("/")
    except (OSError, IndexError):
        return path
    target = path.parent / first
    return target if target.exists() else path


def title_from_name(name: str) -> Optional[str]:
    """Title IDs are often embedded in file names, e.g. 'Game [4D5307E6].iso'."""
    for m in _TITLE_RE.finditer(name):
        tid = m.group(1).upper()
        # Real Title IDs start with a publisher code of two letters (ASCII 0x41-0x5A)
        try:
            a, b = int(tid[0:2], 16), int(tid[2:4], 16)
        except ValueError:
            continue
        if 0x41 <= a <= 0x5A and 0x41 <= b <= 0x5A:
            return tid
        if tid.startswith("5841") or tid.startswith("5855"):  # 'XA'/'XU' arcade
            return tid
    return None


def detect(path: Path) -> tuple[Optional[str], str]:
    """Best-effort (Title ID, kind) for any game file EmulationStation lists.

    kind is one of: disc, arcade, god (Games on Demand), demo, xex, unknown.
    """
    p = path
    if p.suffix.lower() == ".xbox360":
        p = resolve_playlist(p)
    if p.is_dir():
        xex = p / "default.xex"
        if xex.is_file():
            p = xex
    suffix = p.suffix.lower()
    tid: Optional[str] = None
    kind = "unknown"
    if suffix == ".iso":
        tid, kind = read_iso(p), "disc"
    elif suffix == ".xex":
        tid, kind = read_xex(p), "xex"
    elif p.is_file():
        info = read_stfs(p)
        if info:
            tid = info.title_id
            kind = {0x000D0000: "arcade", 0x00007000: "god", 0x00080000: "demo"}.get(info.content_type, "unknown")
    if kind == "xex" and any(part.upper() == "000D0000" for part in p.parts):
        kind = "arcade"
    return tid or title_from_name(path.name) or title_from_name(str(p)), kind


def detect_title_id(path: Path) -> Optional[str]:
    return detect(path)[0]
