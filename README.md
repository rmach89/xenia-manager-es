# Xenia Manager for EmulationStation

Manage Xbox 360 games on **Batocera** and **HippOS**: DLC, title updates,
patches, per-game settings and saves, all applied automatically when you start a
game from the EmulationStation game list.

It uses the Xenia builds that come with your system (Xenia, Xenia Canary and
Xenia Edge) and doesn't install an emulator of its own.

> Inspired by [Xenia Manager](https://github.com/xenia-manager/xenia-manager) for
> Windows. This is an independent project, not the official app. See [CREDITS.md](CREDITS.md).

## Features

| Feature | What it does |
|---|---|
| DLC Manager | Install DLC packages and turn each one on or off |
| Title Update Manager | Install, switch and remove title updates (one active at a time) |
| Patch Manager | Download the community Xenia patches and pick them per game |
| Game Profiles | Per-game Xenia settings, plus defaults for all games |
| Save Manager | Back up, restore and export saves (to a folder or USB stick) |
| Game Detection | Reads your Xbox 360 list and Title IDs from ISO, XEX, GoD/XBLA and `.xbox360` files |
| Big Screen Mode | Fullscreen, controller-friendly UI started from EmulationStation |

Also included: a desktop (F1) app, an uninstaller, a drop folder for DLC and
updates, and on Batocera a per-game choice of Xenia build.

## Install

On the Batocera / HippOS machine, open a terminal (SSH, or **F1 → Applications → Terminal**) and run:

```bash
curl -fsSL https://raw.githubusercontent.com/rmach89/xenia-manager-es/main/install.sh | bash
```

Run the same command again to update; your profiles are kept. To install a
specific release: `curl -fsSL .../install.sh | XM_REF=v1.0.0 bash`.

**Before first use**, start one Xbox 360 game with each Xenia build you plan to
use. That lets the system create Xenia's config, which Xenia Manager then layers
its settings on top of.

## Opening it

| Where | How |
|---|---|
| EmulationStation (Batocera) | **Ports → Xenia Manager** (Big Screen mode) |
| EmulationStation (HippOS) | **Desktop Shortcuts → Xenia Manager** (Big Screen mode) |
| Desktop / F1 | **Applications → Xenia Manager** |
| Terminal | `/userdata/system/xenia-manager/bin/xenia-manager` |

Controls: **A** select, **B** back, **X/Y** item options (remove, reset), **LB/RB** page,
**Left/Right** change a value, **Start + Select** quit. Keyboard and mouse work too
(Enter, Esc, arrows, Tab, Page Up/Down, right-click = back).

## How launching works

You keep launching games from the normal EmulationStation list. Before every
launch the system rewrites Xenia's config; Xenia Manager waits for that,
adds the game's profile and chosen patches on top, and puts the touched settings
back when the game exits.

* **Batocera:** a game-start script in `/userdata/system/scripts/xenia-manager.sh`.
* **HippOS:** a small watcher service, `/userdata/system/services/xenia_manager`
  (managed with `hippos-services`), since HippOS has no game-start hook.

EmulationStation's own per-game "Advanced options" still work; Xenia Manager's
settings win where both set the same thing.

## DLC and title updates

Copy the packages (the CON/LIVE/PIRS files) to **`/userdata/xbox360-content`**
(the `xbox360-content` folder on the network share), then pick **Install from drop
folder**. You can also browse to a file, e.g. on a USB stick. Packages are placed
in Xenia's content folder (`/userdata/saves/xbox360/0000000000000000/<TitleID>/…`);
switched-off items move to `/userdata/system/configs/xenia-manager/disabled-content`.

## Files

| Path | What |
|---|---|
| `/userdata/system/xenia-manager` | Program files |
| `/userdata/system/configs/xenia-manager` | Profiles, game cache, patches, log |
| `/userdata/saves/xenia-manager/backups` | Save backups |
| `/userdata/saves/xenia-manager/exports` | Exported saves and profiles |
| `/userdata/xbox360-content` | Drop folder for DLC / title updates |

## Uninstall

Pick **Uninstall Xenia Manager** in the app, open **Xenia Manager Uninstaller** from
the F1 Applications menu, or run:

```bash
bash /userdata/system/xenia-manager/uninstall.sh          # keep profiles
bash /userdata/system/xenia-manager/uninstall.sh --purge  # delete profiles too
```

Games, saves, save backups and Xenia itself are never removed.

## Command line

```
xenia-manager ui [--bigscreen]       open the manager
xenia-manager status                 show Xenia builds and folders
xenia-manager scan                   list games and Title IDs
xenia-manager info FILE              Title ID / package type of a file
xenia-manager install-content FILE…  install DLC or title updates
xenia-manager download-patches       fetch the latest community patches
xenia-manager backup-saves TITLEID   back up a game's saves
xenia-manager recover                undo settings left by a crashed launch
```

## Troubleshooting

* **Settings don't apply:** check `/userdata/system/configs/xenia-manager/xenia-manager.log`.
  The game needs a Title ID (shown on its page); `.zar` files only have one if it is
  in the file name, e.g. `Game [4D5307E6].zar`.
* **Patches don't apply:** patches need Xenia Canary or Xenia Edge, and the right title update for the game.
* **"Start a game with it once":** that Xenia build hasn't created its config yet.

## Development

Pure Python 3.11+, with pygame for the UI. Run the tests from the repo root:

```bash
python3 tests/test_core.py
python3 tests/test_ui_smoke.py   # uses a stand-in pygame, no display needed
```

## License

[MIT](LICENSE) © 2026 rmach89. Third-party projects keep their own licenses; see [CREDITS.md](CREDITS.md).
