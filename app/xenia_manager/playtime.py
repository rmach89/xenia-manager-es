"""Playtime tracking. Every launch from EmulationStation (or Netplay from the
app) is timed by the launch hook and added up per game."""

from __future__ import annotations

import json
import time
from typing import Optional

from . import platform as P

FILE = P.DATA_DIR / "playtime.json"
MIN_SESSION = 10  # seconds; ignore launches that failed straight away


def _load() -> dict:
    try:
        return json.loads(FILE.read_text())
    except (OSError, ValueError):
        return {}


def record(key: str, seconds: float, when: Optional[float] = None) -> None:
    if seconds < MIN_SESSION:
        return
    data = _load()
    e = data.setdefault(key, {"seconds": 0, "sessions": 0, "last": 0})
    e["seconds"] = int(e.get("seconds", 0) + seconds)
    e["sessions"] = int(e.get("sessions", 0) + 1)
    e["last"] = int(when or time.time())
    P.ensure_data_dirs()
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(FILE)


def get(key: str) -> dict:
    return _load().get(key, {"seconds": 0, "sessions": 0, "last": 0})


def fmt_duration(seconds: int) -> str:
    if seconds <= 0:
        return "Never played"
    h, m = divmod(int(seconds) // 60, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{max(m, 1)}m"


def summary(key: str) -> str:
    e = get(key)
    if not e.get("seconds"):
        return "Never played"
    last = time.strftime("%Y-%m-%d", time.localtime(e["last"]))
    return f"{fmt_duration(e['seconds'])}  |  {e['sessions']} session(s)  |  last {last}"


def reset(key: str) -> None:
    data = _load()
    if data.pop(key, None) is not None:
        FILE.write_text(json.dumps(data, indent=1))
