"""Tests for v1.2 features: playtime, online data, gamer profiles/achievements,
Xenia Netplay (install, config, Batocera plugin) and optimized settings.

Run from the repo root:  python3 tests/test_v12.py
"""

import asyncio
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="xm-v12-"))
os.environ["XM_USERDATA"] = str(TMP)
os.environ["XM_PLATFORM"] = "batocera"
sys.path.insert(0, str(HERE.parent / "app"))
sys.path.insert(0, str(HERE))

import test_core as tc  # noqa: E402
from xenia_manager import gamer, library, netplay, onlinedata, playtime, profiles, tomlio  # noqa: E402
from xenia_manager import platform as P  # noqa: E402

ok = 0


def check(cond, msg=""):
    global ok
    assert cond, msg
    ok += 1


# ---- playtime -------------------------------------------------------------------
playtime.record("4D5307E6", 5)                 # too short, ignored
playtime.record("4D5307E6", 3725)
playtime.record("4D5307E6", 60)
e = playtime.get("4D5307E6")
check(e["seconds"] == 3785 and e["sessions"] == 2, e)
check(playtime.fmt_duration(3785) == "1h 03m")
check("2 session(s)" in playtime.summary("4D5307E6"))

# ---- online data (stubbed downloads) -------------------------------------------
fake = {
    onlinedata.SOURCES["compat-canary"]: [{"id": "4D5307E6", "state": "Playable", "url": "u"}],
    onlinedata.SOURCES["compat-netplay"]: [{"id": "4D5307E6", "status": {"working_public": "ok", "tested_locally": "ok"}}],
    onlinedata.SOURCES["optimized-index"]: [{"id": "4D5307E6", "title": "X"}],
}
onlinedata._get = lambda url, timeout=30: (
    json.dumps(fake[url]).encode() if url in fake else
    b'[GPU]\nframerate_limit = 60 # cap\nreadback_resolve = "fast"\n[Storage]\ncontent_root = "/x"\n')
check(onlinedata.stale())
counts = onlinedata.refresh()
check(counts == {"compat-canary": 1, "compat-netplay": 1, "optimized-index": 1}, counts)
check(not onlinedata.stale())
check(onlinedata.compat_label("4d5307e6") == "Playable")
check(onlinedata.compat_label("00000000") == "Not listed")
check("online: ok" in onlinedata.netplay_status("4D5307E6"))
check(onlinedata.has_optimized("4D5307E6") and not onlinedata.has_optimized("11111111"))
opt = onlinedata.optimized_settings("4D5307E6")
check(opt == {"GPU.framerate_limit": 60, "GPU.readback_resolve": "fast", "Storage.content_root": "/x"}, opt)


# ---- gamer profiles / GPD -------------------------------------------------------
def xdbf(entries, little=False):
    """entries: list of (namespace, id, payload)"""
    e = "<" if little else ">"
    table_len, free_len = max(len(entries), 4), 1
    header = (b"FBDX" if little else b"XDBF") + struct.pack(e + "IIIII", 0x10000, table_len, len(entries), free_len, 0)
    table, data = b"", b""
    for ns, eid, payload in entries:
        table += struct.pack(e + "HQII", ns, eid, len(data), len(payload))
        data += payload
    table += b"\0" * (18 * (table_len - len(entries))) + b"\0" * (8 * free_len)
    return header + table + data


def ach(aid, name, desc, locked, gs, flags, t, e=">"):
    enc = "utf-16-be" if e == ">" else "utf-16-le"
    s = b"".join(x.encode(enc) + b"\0\0" for x in (name, desc, locked))
    return struct.pack(e + "IIIiIq", 0x1C, aid, 0, gs, flags, t) + s


def title(tid, n, unl, gs_total, gs, name):
    return (struct.pack(">Iiiii", tid, n, unl, gs_total, gs) + b"\0" * 8 + struct.pack(">I", 0)
            + struct.pack(">q", 133000000000000000) + name.encode("utf-16-be") + b"\0\0")


root = P.content_root()
pdir = root / "E030000012345678" / "FFFE07D1" / "00010000" / "E030000012345678"
pdir.mkdir(parents=True)
(pdir / "Account").write_bytes(b"\0" * 404)
(pdir / "FFFE07D1.gpd").write_bytes(xdbf([(4, 0x4D5307E6, title(0x4D5307E6, 3, 1, 50, 10, "Halo 3"))]))
earned_time = 133000000000000000
(pdir / "4D5307E6.gpd").write_bytes(xdbf([
    (1, 1, ach(1, "First", "Did it", "Do it", 10, 0x20000 | 0x8, earned_time)),
    (1, 2, ach(2, "Hidden", "Secret done", "???", 20, 0x0, 0)),
    (1, 3, ach(3, "Little endian", "LE done", "LE todo", 20, 0x8, 0, e="<")),
]))
profs = gamer.profiles()
check(len(profs) == 1 and profs[0].xuid == "E030000012345678")
check(profs[0].gamerscore() == (10, 50))
t = profs[0].titles()[0]
check((t.title_id, t.name, t.unlocked, t.achievements) == ("4D5307E6", "Halo 3", 1, 3), t)
a = profs[0].achievements("4D5307E6")
check([x.name for x in a] == ["First", "Hidden", "Little endian"], a)
check(a[0].earned and a[0].unlock_time and not a[1].earned and a[1].secret and not a[2].secret)
check(a[2].locked_description == "LE todo")
check(len(gamer.achievements_for("4D5307E6")) == 1)
save = root / "E030000012345678" / "4D5307E6" / "00000001" / "slot"
save.parent.mkdir(parents=True)
save.write_bytes(b"save")
z = gamer.backup_profile(profs[0], include_saves=True)
names = zipfile.ZipFile(z).namelist()
check(any(n.endswith("00000001/slot") for n in names) and any(n.endswith("4D5307E6.gpd") for n in names))
zp = gamer.backup_profile(profs[0], include_saves=False)
check(not any("00000001" in n for n in zipfile.ZipFile(zp).namelist()))
save.write_bytes(b"changed")
check(gamer.import_profile(z) == len(names) and save.read_bytes() == b"save")
check(len(gamer.profile_backups()) >= 3)

# ---- Netplay install (stubbed download) -----------------------------------------
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as zf:
    zf.writestr("xenia_canary_netplay.exe", b"MZ")
    zf.writestr("LICENSE", b"BSD")
netplay.latest_release = lambda: ("v6.0.0", "https://example/xenia_canary_netplay_windows.zip")
netplay._download = lambda url, progress=None: buf.getvalue()
check(not netplay.installed())
check(netplay.install() == "v6.0.0" and netplay.installed())
check(netplay.exe_path().name == "xenia_canary_netplay.exe")
check(("Xenia Netplay", "xenia-netplay") in profiles.emulator_choices())
(P.NETPLAY_DIR / "patches" / "keep.patch.toml").write_text("x")
check(netplay.install() == "v6.0.0" and (P.NETPLAY_DIR / "patches" / "keep.patch.toml").exists())

# ---- Netplay config + Batocera plugin --------------------------------------------
P.ROMS_DIR.mkdir(parents=True, exist_ok=True)
rom = P.ROMS_DIR / "Halo.iso"
tc.make_iso(rom, "4D5307E6")
prof = profiles.load("4D5307E6")
prof.settings = {"GPU.vsync": False}
profiles.save(prof)
other = P.ROMS_DIR / "Other.iso"
tc.make_iso(other, "41560817")
bottle_cfg = P.HOME / "wine-bottles" / "xbox360" / "xenia" / "xenia.config.toml"
bottle_cfg.parent.mkdir(parents=True)
tomlio.save(bottle_cfg, {"GPU": {"vsync": True, "gpu": "vulkan"}, "Storage": {"storage_root": "/elsewhere"}})

sys.path.insert(0, str(HERE / "fakebatocera"))
sys.path.insert(0, str(HERE.parent / "integration" / "batocera"))
import xenia_manager_netplay as plugin  # noqa: E402
cmd = asyncio.run(plugin.XeniaNetplay(rom).configure())
check(cmd.args[1] == str(netplay.exe_path()) and cmd.args[2] == "--config", cmd.args)
check(cmd.args[3] == "z:" + str(P.NETPLAY_TOML) and cmd.args[4] == f"z:{rom}", cmd.args)
check(cmd.env.get("WINEPREFIX"), cmd.env)
cfg = tomlio.load(P.NETPLAY_TOML)
check(cfg["GPU"]["vsync"] is False and cfg["GPU"]["gpu"] == "vulkan", cfg)
check(cfg["Storage"]["storage_root"] == str(P.NETPLAY_DIR) and cfg["Display"]["fullscreen"] is True)
# next game without a profile: previous game's override must not leak
tomlio.save(bottle_cfg, {"GPU": {"gpu": "vulkan"}})
asyncio.run(plugin.XeniaNetplay(other).configure())
check(tomlio.load(P.NETPLAY_TOML)["GPU"].get("vsync") is not False, tomlio.load(P.NETPLAY_TOML))

# direct launch command
try:
    netplay.launch_command(str(rom))
except RuntimeError as e:
    check("Wine was not found" in str(e), e)       # no wine in the test box

# Netplay as default emulator + removal clears it
conf = P.HOME / "batocera.conf"
conf.write_text("xbox360.emulator=xenia-edge\nxbox360.core=xenia-edge\nother=1\n")
check(profiles.set_system_emulator("xenia-netplay") and profiles.get_system_emulator() == "xenia-netplay")
pg = profiles.load("41560817"); pg.emulator = "xenia-netplay"; pg.rom = str(other); profiles.save(pg)
profiles.set_batocera_emulator("Other.iso", "xenia-netplay")
netplay.uninstall()
txt = conf.read_text()
check("xenia-netplay" not in txt and "other=1" in txt, txt)
check(not P.NETPLAY_DIR.exists() and profiles.load("41560817").emulator is None)

print(f"all {ok} v1.2 checks passed")
shutil.rmtree(TMP)
shutil.rmtree(P.USERDATA, ignore_errors=True)
