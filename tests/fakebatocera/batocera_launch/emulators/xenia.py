"""Stand-in for Batocera's Xenia emulator: returns the command shape the real one builds."""
from dataclasses import dataclass
from pathlib import Path
from batocera_launch import Command

@dataclass
class Xenia:
    rom: Path
    core: str = "xenia-netplay"

    async def configure(self):
        bottle = Path("/userdata/system/wine-bottles/xbox360")
        return Command(["/usr/wine/wine-proton/bin/wine", bottle / "xenia" / "xenia.exe", f"z:{self.rom}"],
                       env={"WINEPREFIX": str(bottle)})
