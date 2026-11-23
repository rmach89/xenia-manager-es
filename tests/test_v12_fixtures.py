"""Shared fixtures for the UI smoke test (online data stubs, a gamer profile)."""
import json
import struct


def fake_get(url, timeout=30):
    if url.endswith("canary.json"):
        return json.dumps([{"id": "4D5307E6", "state": "Playable", "url": "u"}]).encode()
    if url.endswith("netplay.json"):
        return json.dumps([{"id": "4D5307E6", "status": {"tested_locally": "ok"}}]).encode()
    if url.endswith("settings.json"):
        return json.dumps([{"id": "4D5307E6"}]).encode()
    return b"[GPU]\nframerate_limit = 60\n[Storage]\ncontent_root = '/x'\n"


def _xdbf(entries):
    header = b"XDBF" + struct.pack(">IIIII", 0x10000, len(entries), len(entries), 1, 0)
    table, data = b"", b""
    for ns, eid, payload in entries:
        table += struct.pack(">HQII", ns, eid, len(data), len(payload))
        data += payload
    return header + table + b"\0" * 8 + data


def make_profile(root, tid="4D5307E6"):
    p = root / "E030000012345678" / "FFFE07D1" / "00010000" / "E030000012345678"
    p.mkdir(parents=True)
    t = (struct.pack(">Iiiii", int(tid, 16), 2, 1, 30, 10) + b"\0" * 12 + struct.pack(">q", 133000000000000000)
         + "Halo 3".encode("utf-16-be") + b"\0\0")
    (p / "FFFE07D1.gpd").write_bytes(_xdbf([(4, int(tid, 16), t)]))

    def ach(aid, name, gs, flags):
        s = b"".join(x.encode("utf-16-be") + b"\0\0" for x in (name, "done", "todo"))
        return struct.pack(">IIIiIq", 0x1C, aid, 0, gs, flags, 133000000000000000 if flags & 0x20000 else 0) + s
    (p / f"{tid}.gpd").write_bytes(_xdbf([(1, 1, ach(1, "First", 10, 0x20008)), (1, 2, ach(2, "Secret", 20, 0))]))
