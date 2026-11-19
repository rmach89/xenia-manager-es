"""Drives every UI screen with a fake pygame to catch crashes.

Run from the repo root:  python3 tests/test_ui_smoke.py
"""

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="xm-ui-"))
os.environ["XM_USERDATA"] = str(TMP)
os.environ["XM_PLATFORM"] = "batocera"
sys.path.insert(0, str(HERE / "fakepygame"))
sys.path.insert(0, str(HERE.parent / "app"))
sys.path.insert(0, str(HERE))

import pygame  # noqa: E402  (the fake)
import test_core as tc  # noqa: E402
from xenia_manager import platform as P, tomlio, xbox  # noqa: E402
from xenia_manager.ui import core, screens  # noqa: E402

# --- fixture data ---
P.ROMS_DIR.mkdir(parents=True)
tc.make_iso(P.ROMS_DIR / "Game.iso", tc.TID)
(P.ROMS_DIR / "NoId.zar").write_bytes(b"zz")
tc.make_stfs(P.INBOX_DIR / "tu1", tc.TID, xbox.TYPE_TU, "Title Update 1")
tc.make_stfs(P.INBOX_DIR / "dlc1", tc.TID, xbox.TYPE_DLC, "Map Pack")
P.PATCH_DB_DIR.mkdir(parents=True)
(P.PATCH_DB_DIR / f"{tc.TID} - Test.patch.toml").write_text(tc.PATCH)
v = P.variant("xenia-canary")
v.toml.parent.mkdir(parents=True)
tomlio.save(v.toml, {"GPU": {"vsync": True, "framerate_limit": 0, "scale": 1.0}, "General": {"apply_patches": False}})
(P.HOME / "batocera.conf").write_text("xbox360.emulator=xenia\n")

errors = []
orig_call = core.App.call


def call(self, fn):
    try:
        fn()
    except Exception:
        errors.append(traceback.format_exc())
    if self.stack and self.dialog is None:
        self.stack[-1].on_resume()


core.App.call = call
app = core.App("Xenia Manager", bigscreen=True)
app.games = []
app.push(screens.Home(app))
screens.scan_task(app)


def settle():
    for _ in range(200):
        if isinstance(app.dialog, core.Task):
            app.dialog.poll(app)
            if app.dialog and app.dialog.closed:
                app.dialog = None
            time.sleep(0.01)
        else:
            break
    app.draw()


def press(*acts):
    for a in acts:
        settle()
        if app.dialog and not isinstance(app.dialog, core.Task):
            d = app.dialog
            d.handle(app, a)
            if d.closed and app.dialog is d:
                app.dialog = None
                app.refresh()
        else:
            app.stack[-1].handle(a)
        settle()


def goto(label):
    scr = app.stack[-1]
    for i, it in enumerate(scr.items):
        if it.label.startswith(label) and not it.header:
            scr.sel = i
            press(core.ACCEPT)
            return
    raise AssertionError(f"{label!r} not in {[i.label for i in scr.items]} on {scr.title}")


settle()
assert len(app.games) == 2, app.games
goto("Games"); goto("Game")                      # game screen
assert app.stack[-1].title == "Game"
goto("Title updates"); goto("From drop folder"); press(core.ACCEPT)   # install
settle()
press(core.BACK)
goto("DLC"); goto("From drop folder"); press(core.ACCEPT); goto("Map Pack")
press(core.BACK)
goto("Patches"); goto("60 FPS"); press(core.BACK)
goto("Game settings")
scr = app.stack[-1]
scr.sel = 1; press(core.RIGHT, core.RIGHT)       # resolution scale -> 2x
scr.sel = 3; press(core.RIGHT)                    # vsync on
goto("More settings"); app.stack[-1].sel = 1; press(core.RIGHT, core.RIGHT, core.OPTIONS); press(core.BACK)
press(core.BACK)
goto("Saves"); press(core.BACK)
goto("Xenia build"); press(core.RIGHT)
press(core.BACK)
goto("NoId"); press(core.BACK, core.BACK)
goto("Settings for all games"); press(core.RIGHT); press(core.BACK)
goto("Xenia status"); press(core.BACK)
goto("About"); press(core.BACK)
goto("Install from drop folder"); press(core.BACK)
press(core.BACK); press(core.RIGHT, core.ACCEPT)   # exit dialog -> cancel
assert app.running

from xenia_manager import content, profiles  # noqa: E402
prof = profiles.load(tc.TID)
print("profile:", prof.settings, prof.patches, prof.emulator)
assert prof.settings.get("GPU.draw_resolution_scale_x+GPU.draw_resolution_scale_y") == 2
assert prof.patches and prof.emulator == "xenia"
assert any(i.enabled for i in content.list_items(tc.TID, xbox.TYPE_TU))
assert not any(i.enabled for i in content.list_items(tc.TID, xbox.TYPE_DLC))
assert 'xbox360["Game.iso"].emulator=xenia' in (P.HOME / "batocera.conf").read_text()
if errors:
    print("\n".join(errors))
    sys.exit(1)
print("UI smoke test passed")
