"""Xenia Netplay (AdrianCassar/xenia-canary) support.

Neither Batocera nor HippOS ships Netplay, so Xenia Manager installs it into
/userdata/system/xenia-netplay. It is a Windows build and runs under the
system's own Wine:

  * Batocera: as the emulator "xenia-netplay", through a small batocera-launch
    plugin (integration/batocera/xenia_manager_netplay.py) that reuses
    Batocera's Xenia Wine bottle, controller and hotkey setup.
  * HippOS: started from Xenia Manager (game page > Play with Xenia Netplay)
    with HippOS's wine-proton runner.

Saves, DLC and title updates are shared with the other Xenia builds.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Optional

from . import library, patches, profiles, tomlio
from . import platform as P

REPO = "AdrianCassar/xenia-canary"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
NIGHTLY_URL = ("https://nightly.link/AdrianCassar/xenia-canary/workflows/Orchestrator/"
               "netplay_canary_experimental/xenia_canary_netplay_windows.zip")
PATCHES_ZIP = "https://github.com/AdrianCassar/Xenia-WebServices/archive/refs/heads/main.zip"
PATCH_DB = P.DATA_DIR / "patches-netplay"
VERSION_FILE = P.NETPLAY_DIR / ".xm-installed"
UNDO_FILE = P.NETPLAY_DIR / ".xm-last-profile.json"
KEEP = {"patches", "portable.txt", P.NETPLAY_TOML.name, ".xm-last-profile.json", "cache", "content"}
UA = {"User-Agent": "xenia-manager-es"}


def info() -> Optional[dict]:
    try:
        return json.loads(VERSION_FILE.read_text())
    except (OSError, ValueError):
        return None


def installed() -> bool:
    return info() is not None and exe_path() is not None


def exe_path() -> Optional[Path]:
    if not P.NETPLAY_DIR.is_dir():
        return None
    exes = sorted(P.NETPLAY_DIR.glob("*.exe"))
    for e in exes:
        if "netplay" in e.name.lower():
            return e
    for e in exes:
        if "xenia" in e.name.lower():
            return e
    return None


def _get(url: str, timeout: float = 60) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def latest_release() -> tuple[str, str]:
    """(tag, download url) of the newest stable Netplay release."""
    rel = json.loads(_get(LATEST_API, 30))
    for a in rel.get("assets", []):
        name = a.get("name", "").lower()
        if name.endswith(".zip") and "netplay" in name and "wsasendto" not in name:
            return rel.get("tag_name", "?"), a["browser_download_url"]
    raise RuntimeError("The latest Netplay release has no Windows build.")


def check_update() -> tuple[Optional[str], str]:
    cur = (info() or {}).get("version")
    tag, _ = latest_release()
    return cur, tag


def _download(url: str, progress=None) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        buf = io.BytesIO()
        while chunk := resp.read(512 * 1024):
            buf.write(chunk)
            if progress:
                progress(buf.tell(), total)
    return buf.getvalue()


def install(channel: str = "stable", progress=None) -> str:
    """Install or update Netplay. Keeps its config, patches and portable.txt."""
    if channel == "nightly":
        tag, url = time.strftime("nightly-%Y%m%d"), NIGHTLY_URL
    else:
        tag, url = latest_release()
    data = _download(url, progress)
    new = P.NETPLAY_DIR.with_name("xenia-netplay.new")
    if new.exists():
        shutil.rmtree(new)
    new.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(new)
    # some archives wrap everything in one folder
    entries = [e for e in new.iterdir()]
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for e in inner.iterdir():
            shutil.move(str(e), str(new / e.name))
        inner.rmdir()
    if not any(new.glob("*.exe")):
        shutil.rmtree(new)
        raise RuntimeError("The download didn't contain a Xenia program.")
    if P.NETPLAY_DIR.is_dir():
        for name in KEEP:
            src = P.NETPLAY_DIR / name
            if src.exists():
                dst = new / name
                if dst.exists():
                    shutil.rmtree(dst) if dst.is_dir() else dst.unlink()
                shutil.move(str(src), str(dst))
        shutil.rmtree(P.NETPLAY_DIR)
    new.rename(P.NETPLAY_DIR)
    (P.NETPLAY_DIR / "portable.txt").touch()
    (P.NETPLAY_DIR / "patches").mkdir(exist_ok=True)
    VERSION_FILE.write_text(json.dumps({"version": tag, "channel": channel, "installed": int(time.time())}))
    return tag


def uninstall() -> None:
    if P.NETPLAY_DIR.exists():
        shutil.rmtree(P.NETPLAY_DIR)
    profiles.set_system_emulator(None, only_if="xenia-netplay")
    for prof in profiles.all_profiles():
        if prof.emulator == "xenia-netplay":
            prof.emulator = None
            profiles.save(prof)
            if prof.rom:
                profiles.set_batocera_emulator(Path(prof.rom).name, None)


def download_patches(progress=None) -> int:
    """Netplay-specific patches from AdrianCassar/Xenia-WebServices."""
    data = _download(PATCHES_ZIP, progress)
    tmp = PATCH_DB.with_name("patches-netplay.new")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    n = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for m in zf.infolist():
            parts = m.filename.split("/")
            if len(parts) == 3 and parts[1] == "patches" and parts[2].endswith(".patch.toml"):
                (tmp / parts[2]).write_bytes(zf.read(m))
                n += 1
    if not n:
        shutil.rmtree(tmp)
        raise RuntimeError("No Netplay patches found in the download.")
    if PATCH_DB.exists():
        shutil.rmtree(PATCH_DB)
    tmp.rename(PATCH_DB)
    return n


# ---- config -------------------------------------------------------------------

def base_settings() -> dict[str, Any]:
    cache = P.USERDATA / "cache" / "xenia-netplay"
    cache.mkdir(parents=True, exist_ok=True)
    return {
        "Display.fullscreen": True,
        "HID.hid": "sdl",
        "General.discord": False,
        "Storage.content_root": str(P.content_root()),
        "Storage.storage_root": str(P.NETPLAY_DIR),
        "Storage.cache_root": str(cache),
        "Storage.mount_scratch": True,
        "Memory.protect_zero": False,
        "CPU.break_on_unimplemented_instructions": False,
        "Logging.log_level": 1,
    }


def prepare_config(rom: str, base_toml: Optional[Path] = None) -> Path:
    """Write Netplay's config for this launch: the host's Xenia settings
    (when given), Netplay's own saved keys, then this game's profile."""
    data: dict = {}
    if P.NETPLAY_TOML.is_file():
        try:
            data = tomlio.load(P.NETPLAY_TOML)
        except Exception:
            data = {}
    # undo the previous game's profile so it doesn't leak into this one
    try:
        for key, prev in json.loads(UNDO_FILE.read_text()).items():
            if prev == "__xm_missing__":
                tomlio.del_path(data, key)
            else:
                tomlio.set_path(data, key, prev)
    except (OSError, ValueError):
        pass
    if base_toml and base_toml.is_file():
        try:
            base = tomlio.load(base_toml)
            for dotted, val in tomlio.flatten(base).items():
                if not dotted.startswith(("Netplay.", "Live.")):
                    tomlio.set_path(data, dotted, val)
        except Exception:
            pass
    for k, v in base_settings().items():
        tomlio.set_path(data, k, v)
    game = library.find(rom)
    settings = profiles.effective_settings(game.key, arcade=game.is_arcade)
    prof = profiles.load(game.key)
    selection = {f: s for f, s in prof.patches.items() if s}
    if any(any(s.values()) for s in selection.values()):
        settings["General.apply_patches"] = True
    undo: dict = {}
    for dotted, val in settings.items():
        for key in dotted.split("+"):
            prev = tomlio.set_path(data, key, val)
            undo.setdefault(key, "__xm_missing__" if prev is tomlio.MISSING else prev)
    tomlio.save(P.NETPLAY_TOML, data)
    UNDO_FILE.write_text(json.dumps(undo))
    if selection:
        v = P.variant("xenia-netplay")
        if v:
            patches.apply(v, selection)
    return P.NETPLAY_TOML


def winpath(p: Path | str) -> str:
    return "z:" + str(p)


# ---- direct launch (HippOS, or from the app) ------------------------------------

def _hippos_wine() -> tuple[Path, Path]:
    return Path("/opt/wine-builds/wine-proton/bin/wine"), P.USERDATA / "wine-bottles" / "xenia-netplay"


def _batocera_wine() -> tuple[Path, Path]:
    return Path("/usr/wine/wine-proton/bin/wine"), P.HOME / "wine-bottles" / "xbox360"


def launch_command(rom: str) -> tuple[list[str], dict[str, str]]:
    exe = exe_path()
    if exe is None:
        raise RuntimeError("Xenia Netplay isn't installed.")
    target = rom
    if rom.lower().endswith(".xbox360"):
        from . import xbox
        target = str(xbox.resolve_playlist(Path(rom)))
    cfg = prepare_config(rom)
    wine, prefix = _hippos_wine() if P.detect_os() == "hippos" else _batocera_wine()
    if not wine.exists():
        raise RuntimeError(f"Wine was not found at {wine}.")
    prefix.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, WINEPREFIX=str(prefix), WINEARCH="win64", WINEDEBUG="-all",
               SDL_JOYSTICK_HIDAPI="0", WINEDLLOVERRIDES="winemenubuilder.exe=;mscoree=d;mshtml=d",
               VKD3D_SHADER_CACHE_PATH=str(P.USERDATA / "cache" / "xenia-netplay"))
    return [str(wine), str(exe), "--config", winpath(cfg), winpath(target)], env


def launch(rom: str) -> int:
    from . import playtime
    cmd, env = launch_command(rom)
    game = library.find(rom)
    start = time.time()
    try:
        return subprocess.call(cmd, env=env, cwd=str(P.NETPLAY_DIR))
    finally:
        playtime.record(game.key, time.time() - start)
