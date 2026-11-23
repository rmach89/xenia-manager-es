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


def profiles_mod():
    from xenia_manager import profiles
    return profiles
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
tc.make_stfs(P.ROMS_DIR / "xbla" / "PKG", "58410B00", 0x000D0000, "Arcade")
(P.ROMS_DIR / "Arcade.xbox360").write_text("xbla/PKG\n")
from xenia_manager import updater  # noqa: E402
updater._fetch = lambda path, ref, timeout=20: b'__version__ = "9.9.9"\n'
updater.update = lambda ref=None: "ok"
# v1.2 fixtures: online data, a gamer profile with achievements, a Netplay "release"
import io, json, zipfile  # noqa: E401,E402
import test_v12_fixtures as fx  # noqa: E402
from xenia_manager import netplay, onlinedata  # noqa: E402
onlinedata._get = fx.fake_get
fx.make_profile(P.content_root())
_buf = io.BytesIO()
with zipfile.ZipFile(_buf, "w") as _z:
    _z.writestr("xenia_canary_netplay.exe", b"MZ")
netplay.latest_release = lambda: ("v6.0.0", "x")
_pbuf = io.BytesIO()
with zipfile.ZipFile(_pbuf, "w") as _z:
    _z.writestr("Xenia-WebServices-main/patches/4D5307E6 - Game.patch.toml", "title_id = '4D5307E6'\n")
netplay._download = lambda url, progress=None: (_pbuf if "WebServices" in url else _buf).getvalue()
_launched = []
netplay.launch = lambda rom: _launched.append(rom) or 0

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
assert len(app.games) == 3, app.games
goto("Xbox Live Arcade games"); press(core.RIGHT)          # -> Full game, then All licenses
goto("Check for updates"); press(core.ACCEPT); press(core.ACCEPT)   # update -> message -> quit
assert not app.running
app.running = True
goto("Games"); goto("Arcade"); goto("Arcade license"); press(core.RIGHT, core.RIGHT)
press(core.BACK, core.BACK)
# v1.2 screens
goto("Update online data"); press(core.ACCEPT)
goto("Xenia Netplay"); goto("Install Xenia Netplay"); press(core.ACCEPT)
assert netplay.installed()
goto("Use Netplay for every"); assert profiles_mod().get_system_emulator() == "xenia-netplay"
goto("Use Netplay for every"); assert profiles_mod().get_system_emulator() == "xenia"
goto("Emulator link"); goto("Download Netplay patches"); press(core.ACCEPT)
press(core.BACK)
goto("Gamer profiles"); goto("Profile E030"); goto("Back up profile only"); press(core.ACCEPT)
goto("Halo 3"); press(core.BACK); press(core.BACK, core.BACK)
goto("Games"); goto("Game")                      # game screen
assert app.stack[-1].title == "Game"
goto("Achievements"); press(core.BACK)
goto("Compatibility"); press(core.ACCEPT)
goto("Play time"); press(core.OPTIONS, core.ACCEPT)
goto("Game settings"); goto("Apply community optimized settings"); press(core.ACCEPT); press(core.BACK)
goto("Title updates"); goto("From drop folder"); press(core.ACCEPT)   # install
settle()
press(core.BACK)
goto("DLC"); goto("From drop folder"); press(core.ACCEPT); goto("Map Pack")
press(core.BACK)
goto("Patches"); goto("60 FPS"); press(core.BACK)
goto("Game settings")
scr = app.stack[-1]
scr.sel = 2; press(core.RIGHT, core.RIGHT)       # resolution scale -> 2x (row 0 = optimized settings)
scr.sel = 4; press(core.RIGHT)                    # vsync on
goto("More settings"); app.stack[-1].sel = 2; press(core.RIGHT, core.RIGHT, core.OPTIONS); press(core.BACK)
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
assert profiles.load(profiles.GLOBAL).arcade_license == -1
assert profiles.load("58410B00").settings["Content.license_mask"] == 0, profiles.load("58410B00").settings
assert prof.settings.get("GPU.draw_resolution_scale_x+GPU.draw_resolution_scale_y") == 2
assert prof.settings.get("GPU.framerate_limit") == 60 and "Storage.content_root" not in prof.settings, prof.settings
assert prof.patches and prof.emulator == "xenia"
assert any(i.enabled for i in content.list_items(tc.TID, xbox.TYPE_TU))
assert not any(i.enabled for i in content.list_items(tc.TID, xbox.TYPE_DLC))
assert 'xbox360["Game.iso"].emulator=xenia' in (P.HOME / "batocera.conf").read_text()
if errors:
    print("\n".join(errors))
    sys.exit(1)
print("UI smoke test passed")
