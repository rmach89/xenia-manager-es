"""Gamer profiles and achievements.

Xenia keeps each profile at
    <content_root>/<XUID>/FFFE07D1/00010000/<XUID>/
        Account          encrypted profile info (not read here)
        FFFE07D1.gpd     dashboard: one entry per game played
        <TitleID>.gpd    that game's achievements
GPD files use the XDBF container (documented by the Free60 project).
Profiles are listed by their XUID; reading the gamertag would need the
console's Account key, which this project deliberately doesn't ship.
"""

from __future__ import annotations

import struct
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from . import platform as P

DASH = "FFFE07D1"
PROFILE_TYPE = "00010000"
NS_ACHIEVEMENT, NS_IMAGE, NS_SETTING, NS_TITLE, NS_STRING = 1, 2, 3, 4, 5
FLAG_EARNED = 0x00020000
FLAG_EARNED_ONLINE = 0x00010000
FLAG_SHOW_UNACHIEVED = 0x00000008
FILETIME_EPOCH = 116444736000000000


@dataclass
class Achievement:
    id: int
    name: str
    description: str
    locked_description: str
    gamerscore: int
    earned: bool
    unlock_time: Optional[float]
    secret: bool


@dataclass
class TitleStats:
    title_id: str
    name: str
    achievements: int
    unlocked: int
    gamerscore: int
    gamerscore_total: int
    last_played: Optional[float]


@dataclass
class Profile:
    xuid: str
    path: Path            # .../<XUID>/FFFE07D1/00010000/<XUID>

    @property
    def root(self) -> Path:
        """content_root/<XUID>: profile plus that profile's saves."""
        return self.path.parents[2]

    def titles(self) -> list[TitleStats]:
        gpd = self.path / f"{DASH}.gpd"
        return read_titles(gpd) if gpd.is_file() else []

    def gamerscore(self) -> tuple[int, int]:
        ts = self.titles()
        return sum(t.gamerscore for t in ts), sum(t.gamerscore_total for t in ts)

    def achievements(self, title_id: str) -> list[Achievement]:
        gpd = self.path / f"{title_id.upper()}.gpd"
        return read_achievements(gpd) if gpd.is_file() else []


def _filetime(v: int) -> Optional[float]:
    if v <= FILETIME_EPOCH:
        return None
    return (v - FILETIME_EPOCH) / 10_000_000


class Xdbf:
    """Read-only XDBF reader (big- or little-endian)."""

    def __init__(self, data: bytes):
        magic = data[:4]
        if magic == b"XDBF":
            self.e = ">"
        elif magic == b"FBDX":
            self.e = "<"
        else:
            raise ValueError("not a GPD/XDBF file")
        _, _ver, table_len, count, free_len, _free_count = struct.unpack_from(self.e + "4sIIIII", data, 0)
        self.data = data
        self.base = 0x18 + table_len * 18 + free_len * 8
        self.entries: list[tuple[int, int, int, int]] = []
        for i in range(min(count, table_len)):
            ns, eid, off, length = struct.unpack_from(self.e + "HQII", data, 0x18 + i * 18)
            self.entries.append((ns, eid, off, length))

    def blobs(self, namespace: int):
        for ns, eid, off, length in self.entries:
            if ns == namespace:
                start = self.base + off
                yield eid, self.data[start:start + length]

    def strings(self, blob: bytes, start: int, count: int, e: Optional[str] = None) -> list[str]:
        enc = "utf-16-be" if (e or self.e) == ">" else "utf-16-le"
        out, pos = [], start
        for _ in range(count):
            end = pos
            while end + 1 < len(blob) and blob[end:end + 2] != b"\x00\x00":
                end += 2
            out.append(blob[pos:end].decode(enc, errors="replace"))
            pos = end + 2
        return out


def read_achievements(gpd: Path) -> list[Achievement]:
    x = Xdbf(gpd.read_bytes())
    out = []
    for eid, blob in x.blobs(NS_ACHIEVEMENT):
        if len(blob) < 0x1C:
            continue
        # Some writers store entries in host (little-endian) order; detect per entry.
        e = next((o for o in (x.e, "<" if x.e == ">" else ">")
                  if struct.unpack_from(o + "I", blob, 0)[0] == 0x1C), None)
        if e is None:
            continue
        _size, aid, _img, gs, flags, utime = struct.unpack_from(e + "IIIiIq", blob, 0)
        name, unlocked_desc, locked_desc = x.strings(blob, 0x1C, 3, e)
        earned = bool(flags & (FLAG_EARNED | FLAG_EARNED_ONLINE))
        out.append(Achievement(aid, name, unlocked_desc, locked_desc, gs, earned,
                               _filetime(utime) if earned else None, not flags & FLAG_SHOW_UNACHIEVED))
    out.sort(key=lambda a: (not a.earned, a.id))
    return out


def read_titles(gpd: Path) -> list[TitleStats]:
    x = Xdbf(gpd.read_bytes())
    out = []
    for eid, blob in x.blobs(NS_TITLE):
        if len(blob) < 0x28:
            continue
        tid, ach, unl, gs_total, gs = struct.unpack_from(x.e + "Iiiii", blob, 0)
        last = struct.unpack_from(x.e + "q", blob, 0x20)[0]
        name = x.strings(blob, 0x28, 1)[0]
        out.append(TitleStats(f"{tid:08X}", name, ach, unl, gs, gs_total, _filetime(last)))
    out.sort(key=lambda t: t.last_played or 0, reverse=True)
    return out


def profiles(root: Optional[Path] = None) -> list[Profile]:
    root = root or P.content_root()
    out = []
    if not root.is_dir():
        return out
    for xuid_dir in sorted(root.iterdir()):
        base = xuid_dir / DASH / PROFILE_TYPE
        if not base.is_dir():
            continue
        for prof in sorted(base.iterdir()):
            if prof.is_dir() and ((prof / f"{DASH}.gpd").exists() or (prof / "Account").exists()):
                out.append(Profile(prof.name.upper(), prof))
    return out


def achievements_for(title_id: str) -> list[tuple[Profile, list[Achievement]]]:
    return [(p, a) for p in profiles() if (a := p.achievements(title_id))]


# ---- backup / export / import ---------------------------------------------------

def backup_profile(profile: Profile, include_saves: bool = True, dest_dir: Optional[Path] = None) -> Path:
    """Zip a profile (and, by default, all of its saves) with paths relative
    to the content root, so it can be restored on any Xenia install."""
    root = P.content_root()
    dest_dir = dest_dir or (P.BACKUP_DIR / "profiles")
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = f"profile-{profile.xuid}-{'full' if include_saves else 'profile'}-{stamp}"
    out = dest_dir / f"{base}.zip"
    n = 2
    while out.exists():
        out = dest_dir / f"{base}-{n}.zip"
        n += 1
    src = profile.root if include_saves else profile.path.parents[1]   # <XUID>/FFFE07D1
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in src.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(root).as_posix())
    return out


def import_profile(archive: Path) -> int:
    """Restore a profile zip made by backup_profile. Existing files for that
    profile are backed up first. Returns the number of files written."""
    root = P.content_root()
    with zipfile.ZipFile(archive) as zf:
        members = []
        xuids = set()
        for m in zf.infolist():
            pp = PurePosixPath(m.filename)
            if m.is_dir() or pp.is_absolute() or ".." in pp.parts or len(pp.parts) < 2:
                continue
            members.append(m)
            xuids.add(pp.parts[0])
    if not members or not any(DASH in PurePosixPath(m.filename).parts for m in members):
        raise ValueError("This zip doesn't contain a Xenia gamer profile.")
    for xuid in xuids:
        for p in profiles(root):
            if p.root.name == xuid:
                backup_profile(p, include_saves=True)
    with zipfile.ZipFile(archive) as zf:
        for m in members:
            target = root / PurePosixPath(m.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as s, open(target, "wb") as d:
                d.write(s.read())
    return len(members)


def profile_backups() -> list[Path]:
    d = P.BACKUP_DIR / "profiles"
    return sorted(d.glob("profile-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True) if d.is_dir() else []
