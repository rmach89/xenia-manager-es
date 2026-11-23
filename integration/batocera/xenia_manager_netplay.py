"""Xenia Netplay emulator for batocera-launch.

Part of Xenia Manager (https://github.com/rmach89/xenia-manager-es), MIT.

The xenia_manager service links this file and its .dist-info folder into
Python's per-user site-packages (/userdata/system/.local/lib/pythonX.Y/
site-packages). batocera-launch finds emulators through the
"batocera_launch.emulators" entry point group, so "xenia-netplay" becomes a
normal Xbox 360 emulator with Batocera's controller, hotkey, bezel and
game-start hook handling. Nothing in /usr is changed.

It reuses Batocera's Xenia emulator to prepare the Wine bottle (wine-proton,
vcrun2022, DXVK/VKD3D) and its Xenia config, then swaps in the Netplay
program and points it at its own config file.
"""

from __future__ import annotations

import logging
import sys

APP_DIR = "/userdata/system/xenia-manager"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from batocera_common.dataclasses import cached_dataclass  # noqa: E402
from batocera_launch import BatoceraException, Command  # noqa: E402
from batocera_launch.emulators.xenia import Xenia  # noqa: E402

_logger = logging.getLogger(__name__)


@cached_dataclass
class XeniaNetplay(Xenia):

    async def configure(self) -> Command:
        try:
            from xenia_manager import netplay
            from xenia_manager import platform as xm_paths
        except ImportError as e:
            raise BatoceraException("Xenia Manager is missing; reinstall it to use Xenia Netplay.") from e

        exe = netplay.exe_path()
        if exe is None:
            raise BatoceraException("Xenia Netplay isn't installed. Install it from Xenia Manager > Xenia Netplay.")

        # Batocera prepares the Wine bottle and writes the Xenia config;
        # as core "xenia-netplay" it takes its regular-Xenia code path.
        command = await super().configure()

        args = [str(a) for a in command.args]
        rom_args = [a for a in args[2:] if a.lower().startswith("z:")]
        bottle = xm_paths.HOME / "wine-bottles" / "xbox360"
        cfg = netplay.prepare_config(str(self.rom), base_toml=bottle / "xenia" / "xenia.config.toml")
        command.args = [args[0], str(exe), "--config", netplay.winpath(cfg), *rom_args]
        _logger.debug("Xenia Netplay command: %s", command.args)
        return command
