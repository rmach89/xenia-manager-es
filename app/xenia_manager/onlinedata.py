"""Community data downloaded on request and cached locally:

  * Compatibility ratings for Xenia Canary and Xenia Netplay, and the list of
    games with optimized settings, from the Xenia Manager project's public
    databases (github.com/xenia-manager/database, .../optimized-settings).
  * Per-game optimized settings (A1eNaz's Xenia Game Settings wiki, ported
    to TOML by the Xenia Manager project), fetched when you apply them.
"""

from __future__ import annotations

import json
import time
import tomllib
import urllib.request
from typing import Any, Optional

from . import platform as P
from . import tomlio

RAW = "https://raw.githubusercontent.com"
SOURCES = {
    "compat-canary": f"{RAW}/xenia-manager/database/main/data/game-compatibility/canary.json",
    "compat-netplay": f"{RAW}/xenia-manager/database/main/data/game-compatibility/netplay.json",
    "optimized-index": f"{RAW}/xenia-manager/optimized-settings/main/data/settings.json",
}
OPTIMIZED_TOML = f"{RAW}/xenia-manager/optimized-settings/main/settings/{{tid}}.toml"
CACHE = P.DATA_DIR / "online"
MAX_AGE = 7 * 24 * 3600
UA = {"User-Agent": "xenia-manager-es"}

STATE_ORDER = ["Playable", "Gameplay", "Loads", "Unplayable", "Unknown"]
STATE_HELP = {
    "Playable": "Can be played start to finish",
    "Gameplay": "Gets in-game, with problems",
    "Loads": "Loads but doesn't reach gameplay",
    "Unplayable": "Crashes or doesn't start",
    "Unknown": "Not rated yet",
}

_mem: dict[str, Any] = {}


def _get(url: str, timeout: float = 30) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def refresh(progress=None) -> dict[str, int]:
    """Download every cached data set. Returns item counts."""
    CACHE.mkdir(parents=True, exist_ok=True)
    counts = {}
    for n, (name, url) in enumerate(SOURCES.items()):
        if progress:
            progress(n / len(SOURCES), f"Downloading {name}")
        data = json.loads(_get(url))
        (CACHE / f"{name}.json").write_text(json.dumps(data))
        counts[name] = len(data)
    (CACHE / "updated").write_text(str(int(time.time())))
    _mem.clear()
    return counts


def age() -> Optional[float]:
    try:
        return time.time() - int((CACHE / "updated").read_text())
    except (OSError, ValueError):
        return None


def stale() -> bool:
    a = age()
    return a is None or a > MAX_AGE


def _load(name: str) -> list:
    if name not in _mem:
        try:
            _mem[name] = json.loads((CACHE / f"{name}.json").read_text())
        except (OSError, ValueError):
            _mem[name] = []
    return _mem[name]


def _by_id(name: str) -> dict[str, dict]:
    key = name + ":idx"
    if key not in _mem:
        _mem[key] = {str(e.get("id", "")).upper(): e for e in _load(name) if isinstance(e, dict)}
    return _mem[key]


def compat(title_id: Optional[str]) -> Optional[dict]:
    """{'state': 'Playable', 'url': ...} for Xenia Canary, or None."""
    if not title_id:
        return None
    return _by_id("compat-canary").get(title_id.upper())


def compat_label(title_id: Optional[str]) -> str:
    c = compat(title_id)
    return c.get("state", "Unknown") if c else "Not listed"


def netplay_status(title_id: Optional[str]) -> Optional[str]:
    if not title_id:
        return None
    e = _by_id("compat-netplay").get(title_id.upper())
    if not e:
        return None
    st = e.get("status") or {}
    parts = []
    for key, label in (("working_public", "online"), ("tested_locally", "local"), ("systemlink", "System Link")):
        val = st.get(key)
        if val:
            parts.append(f"{label}: {val}")
    return ", ".join(parts) or "Listed, not tested"


def has_optimized(title_id: Optional[str]) -> bool:
    return bool(title_id) and title_id.upper() in _by_id("optimized-index")


def optimized_settings(title_id: str) -> dict[str, Any]:
    """Fetch the community optimized settings for a game as dotted keys."""
    import urllib.error
    try:
        text = _get(OPTIMIZED_TOML.format(tid=title_id.upper())).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError("There are no community optimized settings for this game yet.") from e
        raise
    data = tomllib.loads(text)
    return tomlio.flatten(data)
