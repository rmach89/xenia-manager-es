"""Host OS detection and the paths each supported Xenia build uses.

Paths mirror what the host launchers write:
  * Batocera: batocera-launch emulators/xenia.py and xenia_edge.py
  * HippOS:   /usr/lib/hippos/emulatorlauncher_xenia.py and emulatorlauncher_extras.py
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

USERDATA = Path(os.environ.get("XM_USERDATA", "/userdata"))
HOME = USERDATA / "system"

APP_DIR = HOME / "xenia-manager"                       # installed program files
DATA_DIR = HOME / "configs" / "xenia-manager"          # profiles, caches, settings
PROFILES_DIR = DATA_DIR / "profiles"
DISABLED_CONTENT_DIR = DATA_DIR / "disabled-content"   # switched-off DLC / title updates
PATCH_DB_DIR = DATA_DIR / "patches-db"                 # downloaded community patches
RUN_DIR = DATA_DIR / "run"                             # launch-time restore state
LOG_FILE = DATA_DIR / "xenia-manager.log"
BACKUP_DIR = USERDATA / "saves" / "xenia-manager" / "backups"
EXPORT_DIR = USERDATA / "saves" / "xenia-manager" / "exports"
INBOX_DIR = USERDATA / "xbox360-content"               # drop DLC / TUs here
ROMS_DIR = USERDATA / "roms" / "xbox360"
DEFAULT_CONTENT_ROOT = USERDATA / "saves" / "xbox360"

SHARED_XUID = "0000000000000000"


@dataclass(frozen=True)
class Variant:
    key: str                 # emulator / core name used by the host launcher
    label: str
    toml: Path               # config file the host launcher writes before each launch
    patches_dir: Optional[Path]
    installed_marker: Path   # exists when the host OS ships this build

    @property
    def installed(self) -> bool:
        return self.installed_marker.exists()

    @property
    def initialised(self) -> bool:
        """True once the host launcher has run this build at least once.

        We never create the emulator's own folders ourselves: on Batocera an
        existing-but-empty bottle folder stops the launcher from copying
        xenia into it.
        """
        return self.toml.parent.is_dir()


@lru_cache(maxsize=1)
def detect_os() -> str:
    forced = os.environ.get("XM_PLATFORM")
    if forced:
        return forced
    if Path("/usr/lib/hippos").is_dir() or Path("/usr/bin/hippos").exists():
        return "hippos"
    if Path("/usr/share/batocera").is_dir() or Path("/usr/bin/batocera-version").exists():
        return "batocera"
    return "unknown"


def os_label() -> str:
    return {"batocera": "Batocera", "hippos": "HippOS"}.get(detect_os(), "Unknown OS")


@lru_cache(maxsize=1)
def variants() -> tuple[Variant, ...]:
    if detect_os() == "hippos":
        emu = USERDATA / "emulators"
        edge_dir = HOME / "configs" / "xenia-edge"
        return (
            Variant("xenia-canary", "Xenia Canary", emu / "xenia-canary/current/xenia-canary.config.toml",
                    emu / "xenia-canary/current/patches", Path("/opt/emulators/xenia-canary")),
            Variant("xenia", "Xenia", emu / "xenia/current/xenia.config.toml",
                    None, Path("/opt/emulators/xenia")),
            Variant("xenia-edge", "Xenia Edge", edge_dir / "xenia-edge.config.toml",
                    edge_dir / "patches", Path("/opt/emulators/xenia-edge")),
        )
    bottle = HOME / "wine-bottles" / "xbox360"
    edge_dir = HOME / "configs" / "Xenia"
    return (
        Variant("xenia-canary", "Xenia Canary", bottle / "xenia-canary/xenia-canary.config.toml",
                bottle / "xenia-canary/patches", Path("/usr/xenia-canary")),
        Variant("xenia", "Xenia", bottle / "xenia/xenia.config.toml",
                None, Path("/usr/xenia")),
        Variant("xenia-edge", "Xenia Edge", edge_dir / "xenia-edge.config.toml",
                edge_dir / "patches", Path("/usr/bin/xenia-edge/xenia_edge")),
    )


def variant(key: str) -> Optional[Variant]:
    for v in variants():
        if v.key == key:
            return v
    return None


def shipped_patch_dirs() -> list[Path]:
    """Read-only patch folders bundled with the OS image."""
    if detect_os() == "hippos":
        return [Path("/opt/emulators/xenia-canary/emulator/patches")]
    return [Path("/usr/xenia-canary/patches")]


def content_root() -> Path:
    """Where Xenia keeps saves, DLC and title updates (Storage.content_root)."""
    from . import tomlio
    for v in variants():
        if v.toml.is_file():
            try:
                root = tomlio.load(v.toml).get("Storage", {}).get("content_root")
            except Exception:
                root = None
            if root:
                return Path(root)
    return DEFAULT_CONTENT_ROOT


def ensure_data_dirs() -> None:
    for d in (DATA_DIR, PROFILES_DIR, DISABLED_CONTENT_DIR, PATCH_DB_DIR, RUN_DIR):
        d.mkdir(parents=True, exist_ok=True)
