# Credits

Xenia Manager for EmulationStation stands on the work of these projects. Thank you.

| Project | What it gave us | License |
|---|---|---|
| [Xenia Manager](https://github.com/xenia-manager/xenia-manager) by shazzaam7 and contributors | The idea and feature set: DLC manager, title update manager, patch manager, per-game profiles, save manager, game detection and Big Screen mode. This project is an independent rewrite for Linux/EmulationStation and contains none of its code. | BSD 3-Clause |
| [Xenia](https://github.com/xenia-project/xenia) by the Xenia team | The Xbox 360 emulator itself | BSD 3-Clause |
| [Xenia Canary](https://github.com/xenia-canary/xenia-canary) | The experimental Xenia build most games run best on, plus its patch system | BSD 3-Clause |
| Xenia Edge | Native Linux Xenia build shipped by Batocera | see upstream |
| [xenia-canary/game-patches](https://github.com/xenia-canary/game-patches) and every patch author | The community patches the Patch Manager downloads and toggles | see upstream |
| [Batocera Linux](https://github.com/batocera-linux/batocera.linux) | Host OS, its bundled Xenia builds and launcher, whose config paths and game-start hooks we integrate with | LGPL-3.0 / various |
| [HippOS](https://github.com/hippos-linux/hippos-linux) | Host OS, its bundled Xenia builds, launcher and services system | see upstream |
| [Free60](https://free60.org/) | Public documentation of the STFS, XEX and XDVDFS formats used for game detection | — |
| [pygame](https://www.pygame.org/) / [SDL](https://www.libsdl.org/) | The UI and controller support | LGPL |

No code from the projects above is included in this repository; each project is
used only through its normal interfaces (config files, folders and hooks) or
downloaded at runtime by the user (community patches).

This project is not affiliated with or endorsed by the Xenia team, the Xenia
Manager project, Batocera, HippOS or Microsoft. Xbox and Xbox 360 are trademarks
of Microsoft.
