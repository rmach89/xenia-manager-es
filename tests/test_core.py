"""Self-contained tests using synthetic Xbox 360 files.

Run from the repo root:  python3 tests/test_core.py
"""

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="xm-test-"))
os.environ["XM_USERDATA"] = str(TMP)
os.environ["XM_PLATFORM"] = "batocera"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from xenia_manager import content, hook, library, patches, profiles, saves, tomlio, xbox  # noqa: E402
from xenia_manager import platform as P  # noqa: E402

TID = "4D5307E6"


def make_xex(title_id: str) -> bytes:
    hdr = bytearray(0x200)
    hdr[0:4] = b"XEX2"
    struct.pack_into(">I", hdr, 0x14, 2)
    struct.pack_into(">II", hdr, 0x18, 0x00010001, 0)
    struct.pack_into(">II", hdr, 0x20, 0x00040006, 0x100)
    struct.pack_into(">IIII", hdr, 0x100, 0x11223344, 0, 0, int(title_id, 16))
    return bytes(hdr)


def make_iso(path: Path, title_id: str, base: int = 0) -> None:
    S = 2048
    xex = make_xex(title_id)
    # directory table: two entries, default.xex is the right child of "media"
    table = bytearray(b"\xff" * S)

    def entry(left, right, sector, size, name):
        e = struct.pack("<HHIIBB", left, right, sector, size, 0x80, len(name)) + name
        return e + b"\x00" * ((4 - len(e) % 4) % 4)
    e1 = entry(0, 0, 0, 0, b"default.xex")
    e0 = entry(0, 0, 40, 0, b"media")
    off1 = len(e0)
    e0 = entry(0, off1 // 4, 40, 0, b"media")
    blob = e0 + entry(0, 0, 50, len(xex), b"default.xex")
    table[:len(blob)] = blob
    with open(path, "wb") as fh:
        fh.truncate(base + 60 * S)
        fh.seek(base + 32 * S)
        fh.write(b"MICROSOFT*XBOX*MEDIA" + struct.pack("<II", 33, S))
        fh.seek(base + 33 * S)
        fh.write(bytes(table))
        fh.seek(base + 50 * S)
        fh.write(xex)


def make_stfs(path: Path, title_id: str, ctype: int, name: str) -> None:
    h = bytearray(0x2000)
    h[0:4] = b"LIVE"
    struct.pack_into(">I", h, 0x344, ctype)
    struct.pack_into(">I", h, 0x360, int(title_id, 16))
    n = name.encode("utf-16-be")
    h[0x411:0x411 + len(n)] = n
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(h))


PATCH = """title_name = "Test Game"
title_id = "4D5307E6"
hash = "ABCDEF"

[[patch]]
    name = "60 FPS"
    desc = "Unlocks"
    author = "someone"
    is_enabled = false

    [[patch.be32]]
        address = 0x82000000
        value = 0x60000000

[[patch]]
    name = "No blur"
    is_enabled = true
"""


def main():
    ok = 0
    roms = P.ROMS_DIR
    roms.mkdir(parents=True)
    make_iso(roms / "Halo Test.iso", TID, base=0xFD90000 if False else 0)
    (roms / "Folder Game").mkdir()
    (roms / "Folder Game" / "default.xex").write_bytes(make_xex("58410A1B"))
    (roms / "gamelist.xml").write_text(
        '<gameList><game><path>./Halo Test.iso</path><name>Halo Pretty</name></game></gameList>')
    assert xbox.read_iso(roms / "Halo Test.iso") == TID; ok += 1
    games = library.scan(force=True)
    names = {g.name: g.title_id for g in games}
    assert names == {"Halo Pretty": TID, "Folder Game": "58410A1B"}, names; ok += 1
    assert xbox.title_from_name("Game [4D5307E6].zar") == TID; ok += 1

    # XGD2 offset
    make_iso(TMP / "xgd2.iso", "41560817", base=0xFD90000)
    assert xbox.read_iso(TMP / "xgd2.iso") == "41560817"; ok += 1

    # content
    make_stfs(P.INBOX_DIR / "tu1", TID, xbox.TYPE_TU, "Title Update 1")
    make_stfs(P.INBOX_DIR / "tu2", TID, xbox.TYPE_TU, "Title Update 2")
    make_stfs(P.INBOX_DIR / "dlc", TID, xbox.TYPE_DLC, "Map Pack")
    assert len(content.inbox(TID)) == 3; ok += 1
    for p, _ in content.inbox(TID):
        content.install(p)
    tus = content.list_items(TID, xbox.TYPE_TU)
    assert sum(t.enabled for t in tus) == 1 and len(tus) == 2, tus; ok += 1
    off = [t for t in tus if not t.enabled][0]
    content.set_enabled(off, True)
    tus = content.list_items(TID, xbox.TYPE_TU)
    assert sum(t.enabled for t in tus) == 1 and [t for t in tus if t.enabled][0].path.name == off.path.name; ok += 1
    dlc = content.list_items(TID, xbox.TYPE_DLC)[0]
    assert dlc.path == P.DEFAULT_CONTENT_ROOT / P.SHARED_XUID / TID / "00000002" / "dlc"; ok += 1

    # patches
    P.PATCH_DB_DIR.mkdir(parents=True, exist_ok=True)
    (P.PATCH_DB_DIR / f"{TID} - Test Game.patch.toml").write_text(PATCH)
    pf = patches.files_for(TID)[0]
    assert [(p.name, p.enabled) for p in pf.patches] == [("60 FPS", False), ("No blur", True)]; ok += 1

    # variant + config as Batocera would leave it
    v = P.variant("xenia-canary")
    v.toml.parent.mkdir(parents=True)
    tomlio.save(v.toml, {"GPU": {"gpu": "d3d12", "vsync": True}, "General": {"apply_patches": False},
                         "Storage": {"content_root": str(P.DEFAULT_CONTENT_ROOT)}})
    prof = profiles.load(TID)
    prof.settings = {"GPU.vsync": False, "GPU.draw_resolution_scale_x+GPU.draw_resolution_scale_y": 2,
                     "Storage.content_root": "/evil"}
    prof.patches = {pf.path.name: {"60 FPS": True, "No blur": False}}
    profiles.save(prof)
    g = profiles.load(profiles.GLOBAL); g.settings = {"GPU.gpu": "vulkan"}; profiles.save(g)

    # simulate a launch: a fake launcher process, then the host writes the config
    launcher = subprocess.Popen(["sleep", "4"])
    t = __import__("threading").Thread(target=hook.handle_launch,
                                       args=(str(roms / "Halo Test.iso"), "xenia-canary", launcher.pid))
    t.start()
    time.sleep(0.3)
    tomlio.save(v.toml, {"GPU": {"gpu": "d3d12", "vsync": True}, "General": {"apply_patches": False},
                         "Storage": {"content_root": str(P.DEFAULT_CONTENT_ROOT)}})
    time.sleep(1.5)
    cfg = tomlio.load(v.toml)
    assert cfg["GPU"]["vsync"] is False and cfg["GPU"]["gpu"] == "vulkan", cfg; ok += 1
    assert cfg["GPU"]["draw_resolution_scale_y"] == 2 and cfg["General"]["apply_patches"] is True; ok += 1
    assert cfg["Storage"]["content_root"] == str(P.DEFAULT_CONTENT_ROOT); ok += 1
    written = patches.parse(v.patches_dir / pf.path.name)
    assert [(p.name, p.enabled) for p in written.patches] == [("60 FPS", True), ("No blur", False)]; ok += 1
    assert "0x82000000" in (v.patches_dir / pf.path.name).read_text(); ok += 1
    launcher.wait()
    t.join(timeout=15)
    cfg = tomlio.load(v.toml)
    assert cfg["GPU"]["vsync"] is True and cfg["GPU"]["gpu"] == "d3d12" and "draw_resolution_scale_x" not in cfg["GPU"], cfg; ok += 1
    assert cfg["General"]["apply_patches"] is False; ok += 1
    assert not list(P.RUN_DIR.glob("*")); ok += 1

    # saves
    sd = P.DEFAULT_CONTENT_ROOT / "E030000012345678" / TID / "00000001"
    sd.mkdir(parents=True)
    (sd / "slot1").write_bytes(b"save-data")
    b = saves.backup(TID)
    (sd / "slot1").write_bytes(b"broken")
    assert saves.restore(b, TID) == 1 and (sd / "slot1").read_bytes() == b"save-data"; ok += 1
    assert len(saves.backups(TID)) == 2; ok += 1
    assert saves.export(TID, game_name="Halo").is_file(); ok += 1

    # batocera.conf per-game emulator
    profiles.BATOCERA_CONF.parent.mkdir(parents=True, exist_ok=True)
    profiles.BATOCERA_CONF.write_text('xbox360.emulator=xenia\nxbox360["Halo Test.iso"].core=xenia\n')
    profiles.set_batocera_emulator("Halo Test.iso", "xenia-edge")
    txt = profiles.BATOCERA_CONF.read_text()
    assert 'xbox360["Halo Test.iso"].emulator=xenia-edge' in txt and txt.count("core=") == 1; ok += 1
    profiles.set_batocera_emulator("Halo Test.iso", None)
    assert "Halo Test" not in profiles.BATOCERA_CONF.read_text(); ok += 1

    # Xbox Live Arcade: detection via .xbox360 playlist, license only for arcade games
    make_stfs(roms / "xbla" / "58410B00" / "000D0000" / "PKG", "58410B00", 0x000D0000, "Arcade Game")
    (roms / "Arcade Game.xbox360").write_text("xbla/58410B00/000D0000/PKG\n")
    games = {g.name: g for g in library.scan(force=True)}
    assert games["Arcade Game"].kind == "arcade" and games["Arcade Game"].title_id == "58410B00"; ok += 1
    assert games["Halo Pretty"].kind == "disc" and not games["Halo Pretty"].is_arcade; ok += 1
    g = profiles.load(profiles.GLOBAL); g.arcade_license = -1; profiles.save(g)
    assert profiles.effective_settings("58410B00", arcade=True)["Content.license_mask"] == -1; ok += 1
    assert "Content.license_mask" not in profiles.effective_settings(TID, arcade=False); ok += 1
    a = profiles.load("58410B00"); a.settings = {"Content.license_mask": 1}; profiles.save(a)
    assert profiles.effective_settings("58410B00", arcade=True)["Content.license_mask"] == 1; ok += 1
    assert library.find(roms / "Arcade Game.xbox360").is_arcade; ok += 1
    launcher = subprocess.Popen(["sleep", "2"])
    t = __import__("threading").Thread(target=hook.handle_launch,
                                       args=(str(roms / "Arcade Game.xbox360"), "xenia-canary", launcher.pid))
    t.start(); time.sleep(0.3)
    tomlio.save(v.toml, {"Content": {"license_mask": 0}, "GPU": {"gpu": "d3d12"}})
    time.sleep(0.6)
    assert tomlio.load(v.toml)["Content"]["license_mask"] == 1; ok += 1
    launcher.wait(); t.join(timeout=10)
    assert tomlio.load(v.toml)["Content"]["license_mask"] == 0; ok += 1

    # updater: version compare with a stubbed download
    from xenia_manager import updater
    updater._fetch = lambda path, ref, timeout=20: b'__version__ = "9.0.1"\n'
    assert updater.check() == (__import__("xenia_manager").__version__, "9.0.1", True); ok += 1
    updater._fetch = lambda path, ref, timeout=20: b'__version__ = "0.1.0"\n'
    assert updater.check()[2] is False; ok += 1

    # toml round trip incl. nested tables (Xenia Edge GPU.Debug)
    d = {"GPU": {"gpu": "vulkan", "Debug": {"x": 1.5}}, "A": {"s": 'q"\\'}}
    assert tomlio.load(Path(_w(tomlio.dumps(d)))) == d; ok += 1
    print(f"all {ok} checks passed")
    shutil.rmtree(TMP)


def _w(text):
    p = TMP / "rt.toml"
    p.write_text(text)
    return p


if __name__ == "__main__":
    main()
