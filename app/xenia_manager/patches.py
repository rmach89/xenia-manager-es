"""Xenia game patches (the community *.patch.toml files).

Patch files are edited as text so their layout and comments survive; only
`is_enabled = ...` lines change. The chosen patches for each game are kept in
its profile and written into the emulator's patches folder at launch time,
because both host launchers may re-sync that folder.
"""

from __future__ import annotations

import io
import re
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import platform as P

PATCHES_ZIP = "https://github.com/xenia-canary/game-patches/archive/refs/heads/main.zip"
_ASSIGN = re.compile(r'^(\s*)([A-Za-z_]+)\s*=\s*(.*?)\s*$')


@dataclass
class Patch:
    name: str
    desc: str = ""
    author: str = ""
    enabled: bool = False
    line: int = -1          # index of the is_enabled line (-1 if absent)
    header_line: int = -1   # index of the [[patch]] line


@dataclass
class PatchFile:
    path: Path
    title_id: str
    title_name: str
    patches: list[Patch] = field(default_factory=list)


def _unquote(v: str) -> str:
    v = v.split(" #", 1)[0].strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def parse(path: Path) -> PatchFile:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    tid = path.name.split(" ", 1)[0].upper()
    pf = PatchFile(path, tid, "")
    cur: Optional[Patch] = None
    in_sub = False
    for i, raw in enumerate(lines):
        s = raw.strip()
        if s == "[[patch]]":
            cur = Patch(name="", header_line=i)
            pf.patches.append(cur)
            in_sub = False
            continue
        if s.startswith("["):
            in_sub = cur is not None
            continue
        m = _ASSIGN.match(raw)
        if not m:
            continue
        key, val = m.group(2), m.group(3)
        if cur is None:
            if key == "title_name":
                pf.title_name = _unquote(val)
            elif key == "title_id":
                pf.title_id = _unquote(val).upper() or tid
            continue
        if in_sub:
            continue
        if key == "name":
            cur.name = _unquote(val)
        elif key == "desc":
            cur.desc = _unquote(val)
        elif key == "author":
            cur.author = _unquote(val)
        elif key == "is_enabled":
            cur.enabled = _unquote(val).lower() == "true"
            cur.line = i
    for n, p in enumerate(pf.patches):
        if not p.name:
            p.name = f"Patch {n + 1}"
    return pf


def write_states(path: Path, states: dict[str, bool]) -> int:
    """Set is_enabled for the named patches. Returns how many lines changed."""
    pf = parse(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    changed = 0
    inserts: list[tuple[int, str]] = []
    for p in pf.patches:
        if p.name not in states:
            continue
        want = bool(states[p.name])
        if p.line >= 0:
            indent = re.match(r"^\s*", lines[p.line]).group(0)
            new = f"{indent}is_enabled = {'true' if want else 'false'}"
            if lines[p.line] != new:
                lines[p.line] = new
                changed += 1
        else:
            inserts.append((p.header_line + 1, f"    is_enabled = {'true' if want else 'false'}"))
            changed += 1
    for idx, text in sorted(inserts, reverse=True):
        lines.insert(idx, text)
    if changed:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


def _search_dirs() -> list[Path]:
    dirs = [P.PATCH_DB_DIR]
    for v in P.variants():
        if v.patches_dir:
            dirs.append(v.patches_dir)
    dirs += P.shipped_patch_dirs()
    return dirs


def files_for(title_id: str) -> list[PatchFile]:
    """All known patch files for a Title ID (first source wins per file name)."""
    seen: dict[str, PatchFile] = {}
    tid = title_id.upper()
    for d in _search_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.glob(f"{tid}*.patch.toml")):
            if f.name not in seen:
                try:
                    seen[f.name] = parse(f)
                except OSError:
                    continue
    return list(seen.values())


def source_for(filename: str) -> Optional[Path]:
    for d in _search_dirs():
        p = d / filename
        if p.is_file():
            return p
    return None


def apply(variant: P.Variant, selection: dict[str, dict[str, bool]]) -> list[str]:
    """Write the profile's patch choices into the emulator's patches folder."""
    log: list[str] = []
    if not variant.patches_dir or not variant.initialised:
        return log
    variant.patches_dir.mkdir(parents=True, exist_ok=True)
    for filename, states in selection.items():
        target = variant.patches_dir / filename
        if not target.is_file():
            src = source_for(filename)
            if src is None:
                log.append(f"patch file missing: {filename}")
                continue
            shutil.copy2(src, target)
        n = write_states(target, states)
        log.append(f"{filename}: {n} change(s)")
    return log


def download(progress=None) -> int:
    """Download the latest community patches from xenia-canary/game-patches."""
    P.ensure_data_dirs()
    req = urllib.request.Request(PATCHES_ZIP, headers={"User-Agent": "xenia-manager-es"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        while True:
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            buf.write(chunk)
            if progress:
                progress(buf.tell(), total)
    count = 0
    tmp = P.PATCH_DB_DIR.with_name("patches-db.new")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    with zipfile.ZipFile(buf) as zf:
        for info in zf.infolist():
            parts = info.filename.split("/")
            if len(parts) == 3 and parts[1] == "patches" and parts[2].endswith(".patch.toml"):
                (tmp / parts[2]).write_bytes(zf.read(info))
                count += 1
    if count == 0:
        shutil.rmtree(tmp)
        raise RuntimeError("Download did not contain any patches.")
    if P.PATCH_DB_DIR.exists():
        shutil.rmtree(P.PATCH_DB_DIR)
    tmp.rename(P.PATCH_DB_DIR)
    return count
