"""Game detection: reads the Xbox 360 list EmulationStation shows and works
out each game's Title ID. Results are cached by path, size and mtime."""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from . import platform as P
from . import xbox

ES_EXTENSIONS = {".iso", ".xex", ".xbox360", ".zar"}
SKIP_DIRS = {"images", "videos", "manuals", "media", "downloaded_images", "downloaded_videos", "content"}
CACHE_FILE = P.DATA_DIR / "library.json"


@dataclass
class Game:
    path: str                    # path EmulationStation launches
    name: str
    title_id: Optional[str]
    image: Optional[str] = None
    kind: str = "unknown"            # disc | arcade | god | demo | xex | unknown
    extra: dict = field(default_factory=dict)

    @property
    def is_arcade(self) -> bool:
        return self.kind in ("arcade", "demo")

    @property
    def key(self) -> str:
        """Profile key: the Title ID when known, otherwise the file name."""
        return self.title_id or "FILE-" + Path(self.path).name

    @property
    def rom_name(self) -> str:
        return Path(self.path).name


def _gamelist(roms: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    gl = roms / "gamelist.xml"
    if not gl.is_file():
        return out
    try:
        root = ET.parse(gl).getroot()
    except ET.ParseError:
        return out
    for g in root.iter("game"):
        rel = (g.findtext("path") or "").strip()
        if not rel:
            continue
        full = (roms / rel).resolve() if not rel.startswith("/") else Path(rel)
        info = {"name": (g.findtext("name") or "").strip()}
        img = (g.findtext("image") or g.findtext("thumbnail") or "").strip()
        if img:
            info["image"] = str((roms / img).resolve()) if not img.startswith("/") else img
        out[str(full)] = info
    return out


def _walk(roms: Path):
    if not roms.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(roms, followlinks=True):
        dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")]
        names_lower = {f.lower() for f in filenames}
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext not in ES_EXTENSIONS:
                continue
            # A folder game shows up as default.xex; skip stray module .xex files
            if ext == ".xex" and f.lower() != "default.xex" and "default.xex" in names_lower:
                continue
            yield Path(dirpath) / f


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict) -> None:
    try:
        P.ensure_data_dirs()
        CACHE_FILE.write_text(json.dumps(cache, indent=1))
    except OSError:
        pass


def scan(roms: Path = P.ROMS_DIR, force: bool = False, progress=None) -> list[Game]:
    cache = {} if force else _load_cache()
    new_cache: dict = {}
    meta = _gamelist(roms)
    games: list[Game] = []
    files = list(_walk(roms))
    for i, path in enumerate(files):
        if progress:
            progress(i, len(files), path.name)
        try:
            st = path.stat()
        except OSError:
            continue
        sig = f"{st.st_size}:{int(st.st_mtime)}"
        cached = cache.get(str(path))
        if cached and cached.get("sig") == sig and "kind" in cached:
            tid, kind = cached.get("title_id"), cached["kind"]
        else:
            tid, kind = xbox.detect(path)
        new_cache[str(path)] = {"sig": sig, "title_id": tid, "kind": kind}
        info = meta.get(str(path.resolve()), {})
        name = info.get("name") or (path.parent.name if path.name.lower() == "default.xex" else path.stem)
        games.append(Game(str(path), name, tid, info.get("image"), kind))
    _save_cache(new_cache)
    games.sort(key=lambda g: g.name.lower())
    return games


def find(rom: str | Path) -> Game:
    """Look up a single ROM (used at launch time, so no full scan)."""
    path = Path(rom)
    cache = _load_cache()
    try:
        st = path.stat()
        sig = f"{st.st_size}:{int(st.st_mtime)}"
        cached = cache.get(str(path))
        if cached and cached.get("sig") == sig and cached.get("title_id") and "kind" in cached:
            return Game(str(path), path.stem, cached["title_id"], kind=cached["kind"])
    except OSError:
        pass
    tid, kind = xbox.detect(path)
    return Game(str(path), path.stem, tid, kind=kind)
