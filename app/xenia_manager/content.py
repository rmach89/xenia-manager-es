"""DLC and title update management.

Xenia loads packages straight from its content folder:
    <content_root>/0000000000000000/<TitleID>/<ContentType>/<package>
(00000002 = DLC, 000B0000 = title update). Packages can stay as single STFS
files; extracted folders work too. Switched-off items are moved to
DATA_DIR/disabled-content so Xenia no longer sees them.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import platform as P
from . import xbox


@dataclass
class ContentItem:
    title_id: str
    content_type: int
    path: Path
    enabled: bool
    display_name: str
    version: int = 0

    @property
    def type_hex(self) -> str:
        return f"{self.content_type:08X}"

    @property
    def label(self) -> str:
        name = self.display_name or self.path.name
        return name if self.enabled else f"{name}  (off)"


def _active_dir(title_id: str, ctype: int) -> Path:
    return P.content_root() / P.SHARED_XUID / title_id.upper() / f"{ctype:08X}"


def _disabled_dir(title_id: str, ctype: int) -> Path:
    return P.DISABLED_CONTENT_DIR / title_id.upper() / f"{ctype:08X}"


def _describe(path: Path) -> tuple[str, int]:
    target = path
    if path.is_dir():
        # extracted package: name comes from the matching header if Xenia wrote one
        return path.name, 0
    info = xbox.read_stfs(target)
    if info:
        return info.display_name or path.name, info.version
    return path.name, 0


def list_items(title_id: str, ctype: int) -> list[ContentItem]:
    items: list[ContentItem] = []
    for enabled, base in ((True, _active_dir(title_id, ctype)), (False, _disabled_dir(title_id, ctype))):
        if not base.is_dir():
            continue
        for entry in sorted(base.iterdir()):
            if entry.name.startswith("."):
                continue
            name, ver = _describe(entry)
            items.append(ContentItem(title_id, ctype, entry, enabled, name, ver))
    return items


def _unique(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, i = dest.name, 2
    while (dest.parent / f"{stem}.{i}").exists():
        i += 1
    return dest.parent / f"{stem}.{i}"


def _copy(src: Path, dest: Path, progress: Optional[Callable[[int, int], None]] = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        shutil.copytree(src, dest)
        return
    total = src.stat().st_size
    done = 0
    tmp = dest.with_name(dest.name + ".part")
    with open(src, "rb") as fi, open(tmp, "wb") as fo:
        while True:
            buf = fi.read(4 * 1024 * 1024)
            if not buf:
                break
            fo.write(buf)
            done += len(buf)
            if progress:
                progress(done, total)
    os.replace(tmp, dest)


def install(package: Path, move: bool = False, progress=None) -> ContentItem:
    """Install a DLC or title update package. Returns the installed item.

    Installing a title update switches off any other active update for that
    game, because Xenia should only see one at a time.
    """
    info = xbox.read_stfs(package)
    if info is None:
        raise ValueError(f"{package.name} is not an Xbox 360 content package (CON/LIVE/PIRS).")
    if info.content_type not in (xbox.TYPE_DLC, xbox.TYPE_TU):
        raise ValueError(f"{package.name} is a {info.type_label}, not DLC or a title update.")
    if info.content_type == xbox.TYPE_TU:
        for other in list_items(info.title_id, xbox.TYPE_TU):
            if other.enabled:
                set_enabled(other, False)
    dest = _unique(_active_dir(info.title_id, info.content_type) / package.name)
    if move:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(package), str(dest))
    else:
        _copy(package, dest, progress)
    return ContentItem(info.title_id, info.content_type, dest, True, info.display_name or dest.name, info.version)


def set_enabled(item: ContentItem, enabled: bool) -> ContentItem:
    if item.enabled == enabled:
        return item
    if enabled and item.content_type == xbox.TYPE_TU:
        for other in list_items(item.title_id, xbox.TYPE_TU):
            if other.enabled:
                set_enabled(other, False)
    base = _active_dir if enabled else _disabled_dir
    dest = _unique(base(item.title_id, item.content_type) / item.path.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(item.path), str(dest))
    return ContentItem(item.title_id, item.content_type, dest, enabled, item.display_name, item.version)


def remove(item: ContentItem) -> None:
    if item.path.is_dir():
        shutil.rmtree(item.path)
    else:
        item.path.unlink(missing_ok=True)


def inbox(title_id: Optional[str] = None, folder: Path = P.INBOX_DIR) -> list[tuple[Path, xbox.StfsInfo]]:
    """DLC and title update packages waiting in the drop folder."""
    found: list[tuple[Path, xbox.StfsInfo]] = []
    if not folder.is_dir():
        return found
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            p = Path(dirpath) / f
            info = xbox.read_stfs(p)
            if info and info.content_type in (xbox.TYPE_DLC, xbox.TYPE_TU):
                if title_id is None or info.title_id == title_id.upper():
                    found.append((p, info))
    return found
