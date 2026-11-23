"""Per-game profiles.

A profile is a small JSON file holding Xenia config overrides, chosen patches
and (on Batocera) which Xenia build the game should use. The global profile
(`_global`) applies to every game; a game's own profile wins over it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import platform as P

GLOBAL = "_global"


@dataclass
class Setting:
    key: str                  # dotted TOML key; "+"-joined for linked keys
    label: str
    kind: str                 # bool | choice
    choices: list[tuple[str, Any]] = field(default_factory=list)
    help: str = ""

    @property
    def keys(self) -> list[str]:
        return self.key.split("+")


def _c(*pairs: tuple[str, Any]) -> list[tuple[str, Any]]:
    return list(pairs)


RESOLUTIONS = ["640x480", "640x576", "720x480", "720x576", "800x600", "848x480", "1024x768",
               "1152x864", "1280x720", "1280x768", "1280x960", "1280x1024", "1360x768",
               "1440x900", "1680x1050", "1920x540", "1920x1080"]

CATALOG: list[Setting] = [
    Setting("GPU.gpu", "Graphics API", "choice", _c(("Vulkan", "vulkan"), ("D3D12", "d3d12"), ("Any", "any")),
            "Xenia Edge is Vulkan only."),
    Setting("GPU.draw_resolution_scale_x+GPU.draw_resolution_scale_y", "Resolution scale", "choice",
            _c(("1x (native)", 1), ("2x", 2), ("3x", 3)), "Upscales the game. Needs a strong GPU."),
    Setting("Display.internal_display_resolution", "Internal display resolution", "choice",
            [(r, i) for i, r in enumerate(RESOLUTIONS)]),
    Setting("GPU.vsync", "VSync", "bool"),
    Setting("GPU.framerate_limit", "Frame rate limit", "choice",
            _c(("Off", 0), ("30", 30), ("60", 60), ("120", 120), ("144", 144))),
    Setting("Content.license_mask", "Xbox Live Arcade license", "choice",
            _c(("Full game", 1), ("All licenses", -1), ("Trial only", 0)),
            "Full game unlocks most arcade games. Try All licenses if one still says Trial."),
    Setting("GPU.render_target_path_d3d12", "Render target path (D3D12)", "choice",
            _c(("Any", "any"), ("RTV", "rtv"), ("ROV", "rov"))),
    Setting("GPU.render_target_path_vulkan", "Render target path (Vulkan)", "choice",
            _c(("Any", "any"), ("FBO", "fbo"), ("FSI", "fsi"))),
    Setting("GPU.clear_memory_page_state", "Clear memory page state", "bool",
            help="Fixes missing models in some Team Ninja games."),
    Setting("GPU.gpu_allow_invalid_fetch_constants", "Allow invalid fetch constants", "bool",
            help="Gets some games past fetch-constant errors."),
    Setting("D3D12.d3d12_readback_resolve", "Readback resolve (D3D12)", "bool",
            help="Fixes some effects; costs performance."),
    Setting("Display.postprocess_scaling_and_sharpening", "Scaling / sharpening", "choice",
            _c(("Bilinear", "bilinear"), ("AMD CAS", "cas"), ("AMD FSR", "fsr"))),
    Setting("Display.postprocess_antialiasing", "Post-process anti-aliasing", "choice",
            _c(("None", "none"), ("FXAA", "fxaa"), ("FXAA extreme", "fxaa_extreme"))),
    Setting("APU.apu", "Audio backend", "choice",
            _c(("Any", "any"), ("SDL", "sdl"), ("XAudio2", "xaudio2"), ("None", "nop"))),
    Setting("APU.use_new_decoder", "New audio decoder", "bool", help="Can fix crackling or missing audio."),
    Setting("APU.use_dedicated_xma_thread", "Dedicated XMA thread", "bool"),
    Setting("Memory.protect_zero", "Protect zero page", "bool"),
    Setting("Storage.mount_cache", "Mount cache", "bool"),
    Setting("Storage.mount_scratch", "Mount scratch", "bool"),
    Setting("HID.vibration", "Controller vibration", "bool"),
    Setting("UI.show_achievement_notification", "Achievement pop-ups", "bool"),
    Setting("XConfig.user_language", "Console language", "choice",
            _c(("English", 1), ("Japanese", 2), ("German", 3), ("French", 4), ("Spanish", 5),
               ("Italian", 6), ("Korean", 7), ("Chinese", 8), ("Portuguese", 9), ("Polish", 11),
               ("Russian", 12), ("Swedish", 13), ("Turkish", 14), ("Norwegian", 15), ("Dutch", 16))),
]

# Keys the launch hook must never override: they would break the host OS setup.
PROTECTED = {"Storage.content_root", "Storage.storage_root", "Storage.cache_root",
             "Display.fullscreen", "HID.hid"}

LICENSE_KEY = "Content.license_mask"
# Shown for Xbox Live Arcade games. Xenia treats non-disc games as trials
# unless license_mask grants a license; 1 is the full-game license, -1 grants
# every license bit (needed by a few titles, can upset disc games).
ARCADE_CHOICES: list[tuple[str, Optional[int]]] = [
    ("System default", None), ("Full game", 1), ("All licenses", -1), ("Trial only", 0)]


def license_label(value: Optional[int]) -> str:
    return next((lbl for lbl, v in ARCADE_CHOICES if v == value), str(value))


EMULATOR_CHOICES = [("System default", None), ("Xenia Canary", "xenia-canary"),
                    ("Xenia", "xenia"), ("Xenia Edge", "xenia-edge"), ("Xenia Netplay", "xenia-netplay")]


def emulator_choices() -> list[tuple[str, Optional[str]]]:
    """Builds the user can pick: Netplay only once it's installed."""
    netplay_ready = (P.NETPLAY_DIR / ".xm-installed").exists()
    return [c for c in EMULATOR_CHOICES if c[1] != "xenia-netplay" or netplay_ready]


def _file(key: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key)
    return P.PROFILES_DIR / f"{safe}.json"


@dataclass
class Profile:
    key: str
    name: str = ""
    settings: dict[str, Any] = field(default_factory=dict)        # dotted key -> value
    patches: dict[str, dict[str, bool]] = field(default_factory=dict)
    emulator: Optional[str] = None
    rom: Optional[str] = None
    arcade_license: Optional[int] = None   # global profile only: license for every arcade game

    def to_json(self) -> dict:
        return {"key": self.key, "name": self.name, "settings": self.settings,
                "patches": self.patches, "emulator": self.emulator, "rom": self.rom,
                "arcade_license": self.arcade_license}

    @property
    def is_empty(self) -> bool:
        return (not self.settings and not any(self.patches.values()) and not self.emulator
                and self.arcade_license is None)


def load(key: str) -> Profile:
    try:
        data = json.loads(_file(key).read_text())
    except (OSError, ValueError):
        return Profile(key)
    return Profile(key, data.get("name", ""), data.get("settings", {}) or {},
                   data.get("patches", {}) or {}, data.get("emulator"), data.get("rom"),
                   data.get("arcade_license"))


def save(profile: Profile) -> None:
    P.ensure_data_dirs()
    f = _file(profile.key)
    if profile.is_empty and profile.key != GLOBAL:
        f.unlink(missing_ok=True)
        return
    f.write_text(json.dumps(profile.to_json(), indent=2, sort_keys=True))


def delete(key: str) -> None:
    _file(key).unlink(missing_ok=True)


def all_profiles() -> list[Profile]:
    if not P.PROFILES_DIR.is_dir():
        return []
    return [load(f.stem) for f in sorted(P.PROFILES_DIR.glob("*.json"))]


def effective_settings(key: str, arcade: bool = False) -> dict[str, Any]:
    glob = load(GLOBAL)
    merged = dict(glob.settings)
    if arcade and glob.arcade_license is not None:
        merged[LICENSE_KEY] = glob.arcade_license
    if key != GLOBAL:
        merged.update(load(key).settings)
    return {k: v for k, v in merged.items() if k not in PROTECTED}


def export_profile(key: str, dest_dir: Path = P.EXPORT_DIR) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / f"profile-{key}.json"
    out.write_text(json.dumps(load(key).to_json(), indent=2, sort_keys=True))
    return out


# ---- Batocera per-game emulator choice (batocera.conf) -----------------------

BATOCERA_CONF = P.HOME / "batocera.conf"
_EMU_TO_CORE = {"xenia-canary": ("xenia-canary", "xenia-canary"), "xenia": ("xenia", "xenia"),
                "xenia-edge": ("xenia-edge", "xenia-edge"), "xenia-netplay": ("xenia-netplay", "xenia-netplay")}


def set_batocera_emulator(rom_name: str, emulator: Optional[str]) -> bool:
    """Write xbox360["<rom>"].emulator/.core so ES launches the chosen build."""
    if P.detect_os() != "batocera" or not BATOCERA_CONF.is_file():
        return False
    prefix = f'xbox360["{rom_name}"].'
    lines = BATOCERA_CONF.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = [ln for ln in lines
            if not (ln.startswith(prefix + "emulator=") or ln.startswith(prefix + "core="))]
    if emulator in _EMU_TO_CORE:
        emu, core = _EMU_TO_CORE[emulator]
        kept += [f"{prefix}emulator={emu}", f"{prefix}core={core}"]
    if kept != lines:
        BATOCERA_CONF.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return True


def get_system_emulator() -> Optional[str]:
    if not BATOCERA_CONF.is_file():
        return None
    for ln in BATOCERA_CONF.read_text(encoding="utf-8", errors="replace").splitlines():
        if ln.startswith("xbox360.emulator="):
            return ln.split("=", 1)[1].strip() or None
    return None


def set_system_emulator(emulator: Optional[str], only_if: Optional[str] = None) -> bool:
    """Default Xenia build for every Xbox 360 game (xbox360.emulator / .core)."""
    if P.detect_os() != "batocera" or not BATOCERA_CONF.is_file():
        return False
    if only_if is not None and get_system_emulator() != only_if:
        return False
    lines = BATOCERA_CONF.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = [ln for ln in lines if not ln.startswith(("xbox360.emulator=", "xbox360.core="))]
    if emulator in _EMU_TO_CORE:
        emu, core = _EMU_TO_CORE[emulator]
        kept += [f"xbox360.emulator={emu}", f"xbox360.core={core}"]
    if kept != lines:
        BATOCERA_CONF.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return True
