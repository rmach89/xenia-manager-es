"""Applies profiles when a game is started from EmulationStation.

Both Batocera and HippOS rewrite Xenia's config file right before every
launch. We wait for that write, then layer the game's profile on top of it
(and write its chosen patches) before Xenia reads the file. When the game
exits, the keys we touched are put back so the next game starts clean.

  * Batocera: a gameStart script in /userdata/system/scripts starts us with
    the ROM, emulator and launcher PID.
  * HippOS: there is no gameStart hook, so a small service watches for the
    launcher process and does the same thing.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

from . import library, patches, profiles, tomlio
from . import platform as P

log = logging.getLogger("xenia-manager")
_MISSING_TAG = "__xm_missing__"
POLL = 0.02


def setup_logging() -> None:
    P.ensure_data_dirs()
    try:
        if P.LOG_FILE.exists() and P.LOG_FILE.stat().st_size > 1_000_000:
            P.LOG_FILE.rename(P.LOG_FILE.with_suffix(".log.1"))
    except OSError:
        pass
    logging.basicConfig(filename=str(P.LOG_FILE), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _mtime(path: Path) -> int:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _proc_start(pid: int) -> Optional[float]:
    """Unix time a process started, from /proc."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        ticks = int(stat.rsplit(")", 1)[1].split()[19])
        btime = next(int(ln.split()[1]) for ln in Path("/proc/stat").read_text().splitlines()
                     if ln.startswith("btime"))
        return btime + ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, StopIteration):
        return None


def _wait_stable(path: Path) -> None:
    last = -1
    for _ in range(25):
        try:
            size = path.stat().st_size
        except OSError:
            size = -2
        if size == last and size > 0:
            return
        last = size
        time.sleep(POLL)


def _state_file(pid: int) -> Path:
    return P.RUN_DIR / f"{pid}.json"


def apply_settings(toml_path: Path, settings: dict) -> dict:
    """Merge overrides into a config file; return what is needed to undo it."""
    data = tomlio.load(toml_path)
    undo: dict = {}
    for dotted, value in settings.items():
        for key in dotted.split("+"):
            prev = tomlio.set_path(data, key, value)
            if key not in undo:
                undo[key] = _MISSING_TAG if prev is tomlio.MISSING else prev
    tomlio.save(toml_path, data)
    return undo


def restore_settings(toml_path: Path, undo: dict) -> None:
    if not toml_path.is_file() or not undo:
        return
    data = tomlio.load(toml_path)
    for key, prev in undo.items():
        if prev == _MISSING_TAG:
            tomlio.del_path(data, key)
        else:
            tomlio.set_path(data, key, prev)
    tomlio.save(toml_path, data)


def recover_stale() -> None:
    """Undo changes left behind by a launch that ended without cleanup."""
    if not P.RUN_DIR.is_dir():
        return
    for f in P.RUN_DIR.glob("*.json"):
        try:
            pid = int(f.stem)
        except ValueError:
            continue
        if _alive(pid):
            continue
        try:
            st = json.loads(f.read_text())
            restore_settings(Path(st["toml"]), st.get("undo", {}))
            log.info("recovered settings left by pid %s", pid)
        except Exception as e:  # never block a launch
            log.warning("could not recover %s: %s", f, e)
        f.unlink(missing_ok=True)


def handle_launch(rom: str, emulator: Optional[str], launcher_pid: int, timeout: float = 900,
                  late: bool = False) -> None:
    lock = P.RUN_DIR / f"{launcher_pid}.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return  # another watcher already handles this launch
    try:
        _handle(rom, emulator, launcher_pid, timeout, late)
    finally:
        lock.unlink(missing_ok=True)


def _handle(rom: str, emulator: Optional[str], launcher_pid: int, timeout: float, late: bool) -> None:
    game = library.find(rom)
    key = game.key
    settings = profiles.effective_settings(key)
    prof = profiles.load(key)
    selection = {f: s for f, s in prof.patches.items() if s}
    wants_patches = any(any(s.values()) for s in selection.values())
    if not settings and not selection:
        log.info("launch %s (%s): no profile, nothing to do", game.rom_name, key)
        return

    candidates = [v for v in P.variants() if emulator is None or v.key == emulator] or list(P.variants())
    before = {v.key: _mtime(v.toml) for v in candidates}
    started = time.monotonic()
    log.info("launch %s (%s) via %s: waiting for config write", game.rom_name, key, emulator or "?")

    target: Optional[P.Variant] = None
    # If the launcher already wrote the config before we noticed it (possible
    # with the HippOS watcher), use that write instead of waiting for another.
    launched_at = _proc_start(launcher_pid) if late else None
    if launched_at:
        for v in candidates:
            if before[v.key] / 1e9 > launched_at + 0.05:
                target = v
                break
    while target is None:
        for v in candidates:
            if _mtime(v.toml) != before[v.key]:
                target = v
                break
        if target is not None:
            break
        if not _alive(launcher_pid) or time.monotonic() - started > timeout:
            log.info("launcher ended before writing a config; giving up")
            return
        time.sleep(POLL)

    _wait_stable(target.toml)
    if wants_patches:
        settings = dict(settings)
        settings["General.apply_patches"] = True
    undo = {}
    try:
        undo = apply_settings(target.toml, settings)
        _state_file(launcher_pid).write_text(json.dumps({"toml": str(target.toml), "undo": undo}))
        log.info("applied %d setting(s) to %s", len(settings), target.toml)
    except Exception as e:
        log.error("could not apply settings: %s", e)

    if selection:
        # The host launcher may re-enable patches right after its config write,
        # so write our choices again a couple of times while Xenia boots.
        for delay in (0, 1.0, 2.5, 5.0):
            time.sleep(delay)
            try:
                for line in patches.apply(target, selection):
                    log.info("patches: %s", line)
            except Exception as e:
                log.error("could not apply patches: %s", e)

    while _alive(launcher_pid):
        time.sleep(0.5)
    time.sleep(0.5)  # let Xenia finish writing its config on exit
    try:
        restore_settings(target.toml, undo)
        log.info("restored %d key(s) in %s", len(undo), target.toml)
    except Exception as e:
        log.error("restore failed: %s", e)
    _state_file(launcher_pid).unlink(missing_ok=True)


# ---- HippOS watcher -----------------------------------------------------------

def _cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]


def _arg(args: list[str], name: str) -> Optional[str]:
    try:
        return args[args.index(name) + 1]
    except (ValueError, IndexError):
        return None


def find_launches() -> list[tuple[int, str, Optional[str]]]:
    out = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        args = _cmdline(int(entry))
        if "-rom" not in args or _arg(args, "-system") != "xbox360":
            continue
        if not any(Path(a).name in ("emulatorlauncher", "batocera-launch", "emulatorlauncher.py") for a in args[:3]):
            continue
        rom = _arg(args, "-rom")
        if rom:
            out.append((int(entry), rom, _arg(args, "-emulator") or _arg(args, "-core")))
    return out


def watch_forever() -> None:
    setup_logging()
    recover_stale()
    log.info("watcher started (%s)", P.os_label())
    seen: set[int] = set()
    while True:
        try:
            current = find_launches()
        except Exception as e:
            log.warning("scan failed: %s", e)
            current = []
        live = {pid for pid, _, _ in current}
        for pid, rom, emu in current:
            if pid in seen:
                continue
            seen.add(pid)
            threading.Thread(target=handle_launch, args=(rom, emu, pid), kwargs={"late": True}, daemon=True).start()
        seen &= live
        time.sleep(0.1)
