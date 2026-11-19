"""Save game backup, restore and export.

Xenia stores saves as
    <content_root>/<XUID>/<TitleID>/00000001/...           (current builds, per gamer profile)
    <content_root>/<XUID>/<TitleID>/Headers/00000001/...
    <content_root>/<TitleID>/00000001/...                  (older builds, no profiles)
Backups are zip files with paths relative to the content root, so they can be
restored on any machine using the same layout.
"""

from __future__ import annotations

import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

from . import platform as P

SAVE_TYPE = "00000001"


@dataclass
class Backup:
    path: Path
    title_id: str
    created: float
    size: int

    @property
    def label(self) -> str:
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(self.created))
        note = ""
        if "-pre-restore" in self.path.name:
            note = "  (auto, before restore)"
        return f"{stamp}  {self.size // 1024} KB{note}"


def save_dirs(title_id: str, root: Optional[Path] = None) -> list[Path]:
    root = root or P.content_root()
    tid = title_id.upper()
    out: list[Path] = []
    if not root.is_dir():
        return out
    legacy = root / tid / SAVE_TYPE
    if legacy.is_dir():
        out.append(legacy)
    for xuid in root.iterdir():
        if not xuid.is_dir():
            continue
        for sub in (xuid / tid / SAVE_TYPE, xuid / tid / "Headers" / SAVE_TYPE):
            if sub.is_dir():
                out.append(sub)
    return out


def has_saves(title_id: str) -> bool:
    return any(any(d.rglob("*")) for d in save_dirs(title_id))


def _zip_saves(title_id: str, dest: Path) -> Path:
    root = P.content_root()
    dirs = save_dirs(title_id, root)
    if not dirs:
        raise FileNotFoundError("No saves found for this game yet.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in dirs:
            for f in d.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(root).as_posix())
    return dest


def backup(title_id: str, tag: str = "") -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = f"{title_id.upper()}_{stamp}{tag}.zip"
    return _zip_saves(title_id, P.BACKUP_DIR / title_id.upper() / name)


def export(title_id: str, dest_dir: Path = P.EXPORT_DIR, game_name: str = "") -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = "".join(c for c in game_name if c.isalnum() or c in " -_").strip()
    name = f"{safe + ' ' if safe else ''}[{title_id.upper()}] saves {stamp}.zip"
    return _zip_saves(title_id, dest_dir / name)


def backups(title_id: str) -> list[Backup]:
    d = P.BACKUP_DIR / title_id.upper()
    if not d.is_dir():
        return []
    out = [Backup(f, title_id.upper(), f.stat().st_mtime, f.stat().st_size) for f in d.glob("*.zip")]
    return sorted(out, key=lambda b: b.created, reverse=True)


def restore(archive: Path, title_id: str) -> int:
    """Restore a backup. Current saves are backed up first. Returns file count."""
    tid = title_id.upper()
    root = P.content_root()
    with zipfile.ZipFile(archive) as zf:
        members = []
        for m in zf.infolist():
            pp = PurePosixPath(m.filename)
            if m.is_dir() or pp.is_absolute() or ".." in pp.parts or tid not in pp.parts:
                continue
            members.append(m)
        if not members:
            raise ValueError("This backup has no saves for this game.")
        if has_saves(tid):
            backup(tid, "-pre-restore")
        for m in members:
            target = root / PurePosixPath(m.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(m) as src, open(target, "wb") as dst:
                dst.write(src.read())
    return len(members)


def export_destinations() -> list[tuple[str, Path]]:
    """The exports folder plus any mounted USB drives."""
    dests = [("Exports folder (saves/xenia-manager/exports)", P.EXPORT_DIR)]
    media = Path("/media")
    if media.is_dir():
        for d in sorted(media.iterdir()):
            if d.is_dir() and not d.name.startswith("."):
                dests.append((f"USB: {d.name}", d / "xenia-manager-exports"))
    return dests
