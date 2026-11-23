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
| Xbox Live Arcade unlock | Play arcade games as the full version instead of the trial |
| Xenia Netplay | Install, update and remove [Xenia Netplay](https://github.com/AdrianCassar/xenia-canary) (online play, runs under Wine) |
| Playtime & compatibility | Play time per game, plus Canary and Netplay compatibility ratings |
| Gamer profiles & achievements | Achievements and gamerscore per game; profile backup, export and import |
| Optimized settings | One-press community optimized settings per game |
| Updater | Updates Xenia Manager itself from this repository |

Also included: a desktop (F1) app, an uninstaller, a drop folder for DLC and
updates, and on Batocera a per-game choice of Xenia build.

Xenia Manager does **not** install or update Xenia, Xenia Canary or Xenia Edge;
Batocera and HippOS already ship and update those. The one exception is
**Xenia Netplay**, which neither system includes.

## Install

On the Batocera / HippOS machine, open a terminal (SSH, or **F1 → Applications → Terminal**) and run:

```bash
curl -fsSL https://raw.githubusercontent.com/rmach89/xenia-manager-es/main/install.sh | bash
```

To install a specific release: `curl -fsSL https://raw.githubusercontent.com/rmach89/xenia-manager-es/main/install.sh | XM_REF=v1.1.0 bash`.

## Updating

* In the app: **Check for updates** on the home screen (it also checks quietly
  each time the app opens and tells you when a new version is out).
* From a terminal: `xenia-manager update` (`--check` to only look, `--force` to reinstall).
* Or run the install command again.

Updates come from the branch or tag you installed from and keep your profiles,
settings and backups.

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

## The xenia_manager service

Xenia Manager doesn't change anything in `/usr` and doesn't use overlays. The
installer adds a service, `xenia_manager`, which links everything into place on
`/userdata` each time it starts:

| Link | Points to |
|---|---|
| `/userdata/system/scripts/xenia-manager.sh` | game-start hook (Batocera) |
| `/userdata/roms/ports/Xenia Manager.sh` + image | Big Screen mode in Ports (Batocera) |
| `/userdata/Desktop/xenia-manager.desktop` | Big Screen mode in Desktop Shortcuts (HippOS) |
| `/userdata/system/.local/share/applications/xenia-manager*.desktop` | F1 / desktop menu entries |
| `/userdata/system/.local/lib/python3.X/site-packages/xenia_manager_netplay*` | registers the `xenia-netplay` emulator with batocera-launch |

On HippOS the service also runs the launch watcher. Keep it enabled
(Batocera: **Main menu → System settings → Services**; HippOS: `hippos-services`).
`bash /userdata/system/services/xenia_manager status` shows what's linked.

## How launching works

You keep launching games from the normal EmulationStation list. Before every
launch the system rewrites Xenia's config; Xenia Manager waits for that,
adds the game's profile and chosen patches on top, and puts the touched settings
back when the game exits.

* **Batocera:** a game-start script in `/userdata/system/scripts/xenia-manager.sh`.
* **HippOS:** the `xenia_manager` service watches for Xbox 360 launches, since
  HippOS has no game-start hook.

EmulationStation's own per-game "Advanced options" still work; Xenia Manager's
settings win where both set the same thing.

## Xbox Live Arcade: full game instead of trial

Xenia runs arcade games in trial mode unless its `license_mask` setting grants a
license. Set **Xbox Live Arcade games** on the home screen to:

* **Full game**: the full-version license; unlocks most arcade games.
* **All licenses**: every license bit, for the few games that still say Trial.
* **Trial only** / **System default**: leave it to Xenia / your system.

This only applies to games detected as Xbox Live Arcade titles, so disc games are
unaffected. Each arcade game also has its own **Arcade license** setting on its page
that wins over the home screen choice. (HippOS's Xenia Edge launcher doesn't set a
license at all, so arcade games run there as trials until you turn this on.)

## Xenia Netplay

Open **Xenia Netplay** on the home screen to install the latest stable release
(or the newest nightly), update it, download its patches, or remove it. It's
installed to `/userdata/system/xenia-netplay`; it's a Windows build and runs
under your system's Wine. Saves, DLC and title updates are shared with your other
Xenia builds, and game profiles, patches and the arcade unlock apply to it too.

* **Batocera:** Netplay becomes a real Xbox 360 emulator, `xenia-netplay`. A small
  batocera-launch plugin reuses Batocera's own Xenia Wine bottle (wine-proton,
  vcrun2022, DXVK), controller setup, hotkeys and game-start hooks, then starts
  Netplay instead. Pick it per game (game page → **Xenia build**) or for every
  game (**Use Netplay for every Xbox 360 game**). EmulationStation's own
  emulator menu doesn't list it, because that list comes from the read-only system
  file, so choose it in Xenia Manager.
* **HippOS:** start Netplay games from Xenia Manager (game page → **Play with
  Xenia Netplay**), using HippOS's wine-proton runner.

Removing Netplay (or uninstalling Xenia Manager) switches any game set to Netplay
back to the system default.

## Play time, compatibility, achievements

* **Play time:** every launch from EmulationStation is timed; see it on the game's
  page and in the game list.
* **Compatibility:** Canary ratings (Playable / Gameplay / Loads / Unplayable) and
  Netplay ratings from the community trackers, refreshed weekly or with **Update
  online data**.
* **Gamer profiles:** gamerscore and per-game achievements for each Xenia profile,
  plus backup (profile only, or profile with all its saves), export to USB and
  import. Profiles are shown by ID; reading gamertags would need a console key
  this project doesn't ship.
* **Optimized settings:** a game's **Game settings → Apply community optimized
  settings** adds the recommended settings for that game to its profile.

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
| `/userdata/system/xenia-netplay` | Xenia Netplay (if installed) |
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

Uninstalling stops the service, removes every link and removes Xenia Netplay.
Games, saves, save backups and the system's own Xenia builds are never removed.

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
xenia-manager update [--check]       update Xenia Manager from GitHub
xenia-manager netplay install|update|remove|patches|status [--nightly]
xenia-manager netplay launch ROM     start a game in Xenia Netplay
xenia-manager online-data            refresh compatibility ratings / optimized-settings list
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
python3 tests/test_v12.py        # Netplay plugin (stand-in batocera-launch), GPD, online data
python3 tests/test_ui_smoke.py   # uses a stand-in pygame, no display needed
```

## License

[MIT](LICENSE) © 2026 rmach89. Third-party projects keep their own licenses; see [CREDITS.md](CREDITS.md).
