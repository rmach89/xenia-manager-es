"""Command line entry point: `xenia-manager <command>`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, content, library, patches, profiles, saves, xbox
from . import platform as P


def _cmd_ui(a) -> int:
    from .ui.app import run
    return run(bigscreen=a.bigscreen, uninstall=a.uninstall)


def _cmd_scan(a) -> int:
    games = library.scan(force=a.force)
    for g in games:
        print(f"{g.title_id or '--------'}  {g.name}  ({g.rom_name})")
    print(f"{len(games)} game(s)")
    return 0


def _cmd_info(a) -> int:
    p = Path(a.file)
    st = xbox.read_stfs(p)
    if st:
        print(f"Package: {st.magic}  type={st.type_label} ({st.type_hex})")
        print(f"Title ID: {st.title_id}  name={st.display_name!r}  title={st.title_name!r}")
        return 0
    print(f"Title ID: {xbox.detect_title_id(p) or 'unknown'}")
    return 0


def _cmd_hook(a) -> int:
    from . import hook
    hook.setup_logging()
    hook.recover_stale()
    emu = None
    for cand in (a.core, a.emulator):
        if cand and P.variant(cand):
            emu = cand
            break
    hook.handle_launch(a.rom, emu, a.pid)
    return 0


def _cmd_watch(a) -> int:
    from . import hook
    hook.watch_forever()
    return 0


def _cmd_recover(a) -> int:
    from . import hook
    hook.setup_logging()
    hook.recover_stale()
    return 0


def _cmd_patches(a) -> int:
    n = patches.download(lambda d, t: None)
    print(f"Downloaded {n} patch files to {P.PATCH_DB_DIR}")
    return 0


def _cmd_install(a) -> int:
    for f in a.files:
        item = content.install(Path(f), move=a.move)
        print(f"Installed {item.display_name} -> {item.path}")
    return 0


def _cmd_backup(a) -> int:
    print(saves.backup(a.title_id))
    return 0


def _cmd_update(a) -> int:
    from . import updater
    cur, remote, newer = updater.check(a.ref)
    print(f"Installed {cur}, available {remote} ({a.ref or updater.installed_ref()})")
    if a.check:
        return 0
    if not newer and not a.force:
        print("Already up to date. Use --force to reinstall.")
        return 0
    print(updater.update(a.ref))
    return 0


def _cmd_status(a) -> int:
    print(f"Xenia Manager {__version__} on {P.os_label()}")
    for v in P.variants():
        state = "installed" if v.installed else "not installed"
        if v.installed:
            state += ", ready" if v.initialised else ", launch any game once to set it up"
        print(f"  {v.label:13} {state}  ({v.toml})")
    print(f"  content root  {P.content_root()}")
    print(f"  profiles      {len(profiles.all_profiles())}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="xenia-manager", description="Xenia Manager for Batocera / HippOS")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")

    s = sub.add_parser("ui", help="open the manager")
    s.add_argument("--bigscreen", action="store_true", help="fullscreen, controller-first")
    s.add_argument("--uninstall", action="store_true", help="open straight to the uninstaller")
    s.set_defaults(fn=_cmd_ui)

    s = sub.add_parser("scan", help="detect games and Title IDs")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=_cmd_scan)

    s = sub.add_parser("info", help="show Title ID / package info for a file")
    s.add_argument("file")
    s.set_defaults(fn=_cmd_info)

    s = sub.add_parser("hook", help="(internal) apply a profile for a launch")
    s.add_argument("--rom", required=True)
    s.add_argument("--emulator")
    s.add_argument("--core")
    s.add_argument("--pid", type=int, required=True)
    s.set_defaults(fn=_cmd_hook)

    s = sub.add_parser("watch", help="(internal) HippOS launch watcher")
    s.set_defaults(fn=_cmd_watch)

    s = sub.add_parser("recover", help="undo settings left by an interrupted launch")
    s.set_defaults(fn=_cmd_recover)

    s = sub.add_parser("download-patches", help="fetch the latest community patches")
    s.set_defaults(fn=_cmd_patches)

    s = sub.add_parser("install-content", help="install DLC / title update packages")
    s.add_argument("files", nargs="+")
    s.add_argument("--move", action="store_true")
    s.set_defaults(fn=_cmd_install)

    s = sub.add_parser("backup-saves", help="back up saves for a Title ID")
    s.add_argument("title_id")
    s.set_defaults(fn=_cmd_backup)

    s = sub.add_parser("update", help="update Xenia Manager from GitHub")
    s.add_argument("--check", action="store_true", help="only check, don't install")
    s.add_argument("--force", action="store_true", help="reinstall even if up to date")
    s.add_argument("--ref", help="branch or tag (default: the one you installed from)")
    s.set_defaults(fn=_cmd_update)

    s = sub.add_parser("status", help="show detected Xenia builds and paths")
    s.set_defaults(fn=_cmd_status)

    a = ap.parse_args(argv)
    if not getattr(a, "fn", None):
        a = ap.parse_args(["ui"] + (argv or sys.argv[1:]))
    try:
        return a.fn(a) or 0
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
