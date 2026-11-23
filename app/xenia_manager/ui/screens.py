"""The Xenia Manager screens."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .. import __version__, content, gamer, library, netplay, onlinedata, patches, playtime, profiles, saves, tomlio, xbox
from .. import platform as P
from .core import App, Item, Screen

REPO_URL = "github.com/rmach89/xenia-manager-es"


def _games(app: App) -> list[library.Game]:
    return getattr(app, "games", [])


def _game_name(app: App, tid: str) -> str:
    for g in _games(app):
        if g.title_id == tid:
            return g.name
    return tid


def scan_task(app: App, force: bool = False, then: Optional[Callable] = None) -> None:
    def work(report):
        return library.scan(force=force, progress=lambda i, n, name: report(i / max(1, n), f"Reading {name}"))

    def done(games):
        app.games = games
        if then:
            then()
    app.task("Finding your Xbox 360 games", work, done)


def download_patches_task(app: App) -> None:
    def work(report):
        n = patches.download(lambda d, t: report(d / t if t else -1, f"Downloaded {d // 1024} KB"))
        if netplay.installed():
            report(-1, "Downloading Netplay patches")
            n += netplay.download_patches()
        return n
    app.task("Downloading community patches", work,
             lambda n: app.message("Patches updated", f"{n} patch files are ready. Choose them per game under Patches."))


# ---------------------------------------------------------------------------
class Home(Screen):
    title = "Xenia Manager"

    def build(self) -> None:
        app = self.app
        n = len(_games(app))
        self.subtitle = f"{P.os_label()}  |  {n} game(s)  |  v{__version__}"
        waiting = len(content.inbox())
        self.items = [
            Item("Library", header=True),
            Item("Games", lambda: app.push(GameList(app)), value=lambda: str(n),
                 hint="Title updates, DLC, patches, settings and saves for each game."),
            Item("Install from drop folder", lambda: app.push(InboxScreen(app)), value=lambda: str(waiting),
                 hint=f"Copy DLC / title update files to {P.INBOX_DIR} (network share: xbox360-content)."),
            Item("Gamer profiles", lambda: app.push(GamerProfilesScreen(app)),
                 value=lambda: str(len(gamer.profiles())),
                 hint="Achievements, gamerscore, and profile backups."),
            Item("Xenia Netplay", lambda: app.push(NetplayScreen(app)),
                 value=lambda: (netplay.info() or {}).get("version", "Not installed"),
                 hint="Install, update or remove Xenia Netplay (online play, runs under Wine)."),
            Item("Settings", header=True),
            Item("Xbox Live Arcade games", left=lambda: _cycle_arcade(-1), right=lambda: _cycle_arcade(1),
                 value=lambda: profiles.license_label(profiles.load(profiles.GLOBAL).arcade_license),
                 hint="Full game unlocks arcade titles that start as trials. Try All licenses if one still "
                      "says Trial. Applies to arcade games only; each game can override it."),
            Item("Settings for all games", lambda: app.push(ProfileScreen(app, profiles.GLOBAL, "All games")),
                 value=lambda: _count_label(len(profiles.load(profiles.GLOBAL).settings), "changed"),
                 hint="Defaults applied to every game. A game's own settings win over these."),
            Item("Download latest patches", lambda: download_patches_task(app),
                 hint="Fetches xenia-canary/game-patches (and Netplay patches when Netplay is installed)."),
            Item("Update online data", lambda: online_data_task(app), value=_online_age,
                 hint="Compatibility ratings and the optimized-settings list. Refreshed weekly by itself."),
            Item("Rescan games", lambda: scan_task(app, force=True)),
            Item("Xenia status", lambda: app.push(StatusScreen(app))),
            Item("Check for updates", lambda: check_updates_task(app),
                 value=lambda: (f"v{app.update_available} available" if getattr(app, "update_available", None)
                                else f"v{__version__}"),
                 hint="Downloads the newest Xenia Manager from GitHub. Profiles and settings are kept."),
            Item("About & credits", lambda: app.push(AboutScreen(app))),
            Item("Uninstall Xenia Manager", lambda: app.push(UninstallScreen(app))),
            Item("Exit", app.quit),
        ]


def _cycle_arcade(step: int) -> None:
    g = profiles.load(profiles.GLOBAL)
    vals = [v for _, v in profiles.ARCADE_CHOICES]
    idx = vals.index(g.arcade_license) if g.arcade_license in vals else 0
    g.arcade_license = vals[(idx + step) % len(vals)]
    profiles.save(g)


def check_updates_task(app: App) -> None:
    from .. import updater

    def checked(res):
        cur, remote, newer = res
        if newer:
            app.confirm("Update available", f"Xenia Manager {remote} is available (you have {cur}).\n"
                        "Your profiles and settings are kept.", lambda: run_update_task(app), "Update")
        else:
            app.confirm("Up to date", f"You have the latest version ({cur}).",
                        lambda: run_update_task(app), "Reinstall")
    app.task("Checking for updates", lambda report: updater.check(), checked)


def run_update_task(app: App) -> None:
    from .. import updater
    app.task("Updating Xenia Manager", lambda report: updater.update(), lambda out: app.message(
        "Updated", "Xenia Manager was updated. It will close now; open it again to use the new version.",
        then=app.quit))


def background_update_check(app: App) -> None:
    """Quietly check GitHub at startup so the home screen can show an update."""
    import threading

    def run() -> None:
        try:
            from .. import updater
            _, remote, newer = updater.check()
            if newer:
                app.update_available = remote
                app.toast(f"Update available: v{remote}")
        except Exception:
            pass  # offline is fine
        try:
            if onlinedata.stale():
                onlinedata.refresh()
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def _online_age() -> str:
    a = onlinedata.age()
    if a is None:
        return "Never"
    days = int(a // 86400)
    return "Today" if days == 0 else f"{days} day(s) ago"


def online_data_task(app: App) -> None:
    app.task("Updating online data", lambda report: onlinedata.refresh(report),
             lambda counts: app.message("Online data updated",
                                        f"{counts.get('compat-canary', 0)} compatibility ratings\n"
                                        f"{counts.get('compat-netplay', 0)} Netplay ratings\n"
                                        f"{counts.get('optimized-index', 0)} games with optimized settings"))


def _count_label(n: int, word: str) -> str:
    return f"{n} {word}" if n else "Default"


# ---------------------------------------------------------------------------
class GameList(Screen):
    title = "Games"

    def build(self) -> None:
        app = self.app
        games = _games(app)
        custom = {p.key for p in profiles.all_profiles() if not p.is_empty}
        self.subtitle = "Pick a game. Changes apply when you start it from EmulationStation."
        self.items = []
        for g in games:
            mark = "*  " if g.key in custom else ""
            self.items.append(Item(
                g.name, (lambda g=g: app.push(GameScreen(app, g))),
                value=(lambda g=g, m=mark: m + ("Arcade  " if g.is_arcade else "")
                       + (onlinedata.compat_label(g.title_id) if onlinedata.compat(g.title_id)
                          else (g.title_id or "no Title ID"))),
                hint=f"{g.rom_name}  |  {g.title_id or 'no Title ID'}  |  {playtime.fmt_duration(playtime.get(g.key)['seconds'])}"
                     + ("   (* = custom profile)" if mark else ""),
                image=g.image if g.image and os.path.isfile(g.image) else None))
        if not self.items:
            self.items = [Item(f"No games found in {P.ROMS_DIR}", enabled=False),
                          Item("Rescan", lambda: scan_task(app, force=True))]


# ---------------------------------------------------------------------------
class GameScreen(Screen):
    def __init__(self, app: App, game: library.Game):
        super().__init__(app)
        self.game = game
        self.title = game.name

    def build(self) -> None:
        app, g = self.app, self.game
        tid = g.title_id
        prof = profiles.load(g.key)
        if prof.name != g.name or prof.rom != g.path:
            prof.name, prof.rom = g.name, g.path
            if not prof.is_empty:
                profiles.save(prof)
        kind = {"arcade": "Xbox Live Arcade", "demo": "Arcade demo", "god": "Games on Demand",
                "disc": "Disc image", "xex": "Extracted game"}.get(g.kind, "")
        self.subtitle = f"Title ID {tid or 'unknown'}  |  {kind + '  |  ' if kind else ''}{g.rom_name}"
        no_id = "This file's Title ID could not be read, so this isn't available."
        self.items = []
        if g.is_arcade:
            self.items.append(Item(
                "Arcade license", left=lambda: self._cycle_license(-1), right=lambda: self._cycle_license(1),
                value=self._license_value,
                hint="Full game removes trial mode. Try All licenses if the game still says Trial."))
        if tid:
            tus = content.list_items(tid, xbox.TYPE_TU)
            dlc = content.list_items(tid, xbox.TYPE_DLC)
            active_tu = next((t.display_name for t in tus if t.enabled), "None")
            n_patch = sum(1 for s in prof.patches.values() for on in s.values() if on)
            self.items += [
                Item("Title updates", lambda: app.push(ContentScreen(app, g, xbox.TYPE_TU)),
                     value=lambda: active_tu if tus else "None installed"),
                Item("DLC", lambda: app.push(ContentScreen(app, g, xbox.TYPE_DLC)),
                     value=lambda: f"{sum(d.enabled for d in dlc)} of {len(dlc)} on" if dlc else "None installed"),
                Item("Patches", lambda: app.push(PatchScreen(app, g)), value=lambda: f"{n_patch} on"),
            ]
        else:
            self.items += [Item("Title updates", enabled=False, hint=no_id),
                           Item("DLC", enabled=False, hint=no_id),
                           Item("Patches", enabled=False, hint=no_id)]
        self.items.append(Item("Game settings", lambda: app.push(ProfileScreen(app, g.key, g.name, g.title_id)),
                               value=lambda: _count_label(len(prof.settings), "changed")))
        if tid:
            self.items.append(Item("Saves", lambda: app.push(SavesScreen(app, g)),
                                   value=lambda: f"{len(saves.backups(tid))} backup(s)"))
            ach = gamer.achievements_for(tid)
            if ach:
                p0, a0 = ach[0]
                ach_val = f"{sum(a.earned for a in a0)} of {len(a0)}" + (f"  (+{len(ach) - 1} profiles)" if len(ach) > 1 else "")
            else:
                ach_val = "None yet"
            self.items.append(Item("Achievements", lambda: app.push(AchievementsScreen(app, g)),
                                   value=lambda: ach_val, enabled=bool(ach),
                                   hint="" if ach else "Achievements appear here after you play with a profile signed in."))
        else:
            self.items.append(Item("Saves", enabled=False, hint=no_id))
        self.items.append(Item("Play time", value=lambda: playtime.summary(g.key),
                               options=lambda: app.confirm("Reset play time", f"Reset play time for {g.name}?",
                                                           lambda: playtime.reset(g.key), "Reset"),
                               hint="Counted when you play from EmulationStation.  X: reset"))
        if tid:
            c = onlinedata.compat(tid)
            state = c.get("state", "Unknown") if c else None
            self.items.append(Item(
                "Compatibility (Canary)", lambda: self._compat_info(c),
                value=lambda: state or ("Not listed" if onlinedata.age() is not None else "Update online data"),
                hint=onlinedata.STATE_HELP.get(state or "", "From the xenia-canary/game-compatibility tracker.")))
            nps = onlinedata.netplay_status(tid)
            if nps:
                self.items.append(Item("Netplay compatibility", value=lambda: nps,
                                       hint="From the Xenia Netplay compatibility list."))
        if netplay.installed() and P.detect_os() != "batocera":
            self.items.append(Item("Play with Xenia Netplay", lambda: app.run_external(lambda: netplay.launch(g.path)),
                                   hint="Starts this game in Xenia Netplay (under Wine)."))
        if P.detect_os() == "batocera":
            choices = profiles.emulator_choices()

            def cycle(step: int) -> None:
                p = profiles.load(g.key)
                idx = next((i for i, c in enumerate(choices) if c[1] == p.emulator), 0)
                p.emulator = choices[(idx + step) % len(choices)][1]
                p.name, p.rom = g.name, g.path
                profiles.save(p)
                profiles.set_batocera_emulator(g.rom_name, p.emulator)
            self.items.append(Item(
                "Xenia build", left=lambda: cycle(-1), right=lambda: cycle(1),
                value=lambda: next((c[0] for c in choices if c[1] == profiles.load(g.key).emulator), "System default"),
                hint="Which Xenia EmulationStation uses for this game."))
        if not prof.is_empty:
            self.items.append(Item("Reset this game's profile", lambda: app.confirm(
                "Reset profile", f"Remove all custom settings and patch choices for {g.name}?", self._reset)))

    def _compat_info(self, c) -> None:
        if not c:
            self.app.message("Compatibility", "This game isn't in the compatibility list yet, or online data "
                                              "hasn't been downloaded. Use Update online data on the home screen.")
            return
        st = c.get("state", "Unknown")
        self.app.message(f"Compatibility: {st}", f"{onlinedata.STATE_HELP.get(st, '')}\n\n"
                         f"Reported on the Xenia Canary tracker:\n{c.get('url', '')}")

    def _license_value(self) -> str:
        own = profiles.load(self.game.key).settings.get(profiles.LICENSE_KEY)
        if own is not None:
            return profiles.license_label(own)
        glob = profiles.load(profiles.GLOBAL).arcade_license
        return f"{profiles.license_label(glob)} (all arcade games)" if glob is not None else "System default"

    def _cycle_license(self, step: int) -> None:
        p = profiles.load(self.game.key)
        vals = [v for _, v in profiles.ARCADE_CHOICES]
        cur = p.settings.get(profiles.LICENSE_KEY)
        idx = vals.index(cur) if cur in vals else 0
        new = vals[(idx + step) % len(vals)]
        if new is None:
            p.settings.pop(profiles.LICENSE_KEY, None)
        else:
            p.settings[profiles.LICENSE_KEY] = new
        p.name, p.rom = self.game.name, self.game.path
        profiles.save(p)

    def _reset(self) -> None:
        if profiles.load(self.game.key).emulator:
            profiles.set_batocera_emulator(self.game.rom_name, None)
        profiles.delete(self.game.key)
        self.app.toast("Profile reset")


# ---------------------------------------------------------------------------
class ContentScreen(Screen):
    def __init__(self, app: App, game: library.Game, ctype: int):
        super().__init__(app)
        self.game, self.ctype = game, ctype
        self.kind = "title update" if ctype == xbox.TYPE_TU else "DLC"
        self.title = ("Title updates" if ctype == xbox.TYPE_TU else "DLC") + f" - {game.name}"

    def build(self) -> None:
        app, tid = self.app, self.game.title_id
        items = content.list_items(tid, self.ctype)
        waiting = [(p, i) for p, i in content.inbox(tid) if i.content_type == self.ctype]
        self.subtitle = ("Only one title update can be on at a time." if self.ctype == xbox.TYPE_TU
                         else "Turn DLC packs on or off.") + "  X: remove"
        self.items = [Item("Installed", header=True)]
        for it in items:
            self.items.append(Item(
                it.display_name, (lambda it=it: self._toggle(it)),
                value=(lambda it=it: "On" if it.enabled else "Off"),
                options=(lambda it=it: app.confirm("Remove", f"Delete {it.display_name}?",
                                                   lambda: (content.remove(it), app.toast("Removed")))),
                hint=it.path.name))
        if not items:
            self.items.append(Item(f"No {self.kind} installed yet", enabled=False))
        self.items += [
            Item("Add", header=True),
            Item("From drop folder", lambda: self._from_inbox(waiting), value=lambda: str(len(waiting)),
                 hint=f"Files waiting in {P.INBOX_DIR}"),
            Item("Browse for a file...", lambda: app.push(FileBrowser(app, P.USERDATA, self._install_file)),
                 hint="Pick a package from your drive or a USB stick."),
        ]

    def _toggle(self, it: content.ContentItem) -> None:
        content.set_enabled(it, not it.enabled)

    def _from_inbox(self, waiting) -> None:
        if not waiting:
            self.app.message("Drop folder is empty",
                             f"Copy {self.kind} files for this game into {P.INBOX_DIR}, then come back.")
            return
        install_many(self.app, [p for p, _ in waiting], move=True)

    def _install_file(self, path: Path) -> None:
        info = xbox.read_stfs(path)
        if info and info.title_id != self.game.title_id:
            self.app.confirm("Different game",
                             f"This package belongs to {_game_name(self.app, info.title_id)} "
                             f"({info.title_id}). Install it anyway?",
                             lambda: install_many(self.app, [path], move=False), "Install")
            return
        install_many(self.app, [path], move=False)


def install_many(app: App, paths: list[Path], move: bool) -> None:
    def work(report):
        done = []
        for n, p in enumerate(paths):
            report(n / len(paths), f"Installing {p.name}")
            done.append(content.install(
                p, move=move, progress=lambda d, t, n=n: report((n + d / max(1, t)) / len(paths), f"Copying {p.name}")))
        return done

    def finished(items):
        names = "\n".join(f"- {i.display_name}" for i in items[:8])
        app.message("Installed", names + ("\n..." if len(items) > 8 else ""))
    app.task("Installing content", work, finished)


# ---------------------------------------------------------------------------
class InboxScreen(Screen):
    title = "Drop folder"

    def build(self) -> None:
        app = self.app
        waiting = content.inbox()
        self.subtitle = f"{P.INBOX_DIR}  -  files are moved into Xenia when installed"
        self.items = []
        if waiting:
            self.items.append(Item(f"Install all ({len(waiting)})",
                                   lambda: install_many(app, [p for p, _ in waiting], move=True)))
            self.items.append(Item("Packages", header=True))
        for p, info in waiting:
            kind = "Update" if info.content_type == xbox.TYPE_TU else "DLC"
            self.items.append(Item(
                info.display_name or p.name, (lambda p=p: install_many(app, [p], move=True)),
                value=(lambda k=kind, t=info.title_id: f"{k}  |  {_game_name(app, t)}"), hint=str(p)))
        if not waiting:
            self.items.append(Item("Nothing waiting", enabled=False,
                                   hint=f"Copy DLC or title update files into {P.INBOX_DIR}"))


# ---------------------------------------------------------------------------
class PatchScreen(Screen):
    def __init__(self, app: App, game: library.Game):
        super().__init__(app)
        self.game = game
        self.title = f"Patches - {game.name}"

    def build(self) -> None:
        app, g = self.app, self.game
        files = patches.files_for(g.title_id)
        prof = profiles.load(g.key)
        self.subtitle = "Turn patches on or off. They're applied when the game starts (Xenia Canary / Edge)."
        self.items = []
        for pf in files:
            self.items.append(Item(pf.title_name or pf.path.name, header=True))
            for p in pf.patches:
                self.items.append(Item(
                    p.name, (lambda pf=pf, p=p: self._toggle(pf, p)),
                    value=(lambda pf=pf, p=p: "On" if self._state(pf, p) else "Off"),
                    hint=(p.desc or "") + (f"  (by {p.author})" if p.author else "")))
        if not files:
            self.items.append(Item("No patches found for this game", enabled=False))
        self.items.append(Item("Tools", header=True))
        if any(prof.patches.values()):
            self.items.append(Item("Turn all patches off", self._all_off))
        self.items.append(Item("Download latest patches", lambda: download_patches_task(app)))

    def _state(self, pf: patches.PatchFile, p: patches.Patch) -> bool:
        sel = profiles.load(self.game.key).patches.get(pf.path.name, {})
        return sel.get(p.name, False)

    def _toggle(self, pf: patches.PatchFile, p: patches.Patch) -> None:
        prof = profiles.load(self.game.key)
        sel = {q.name: prof.patches.get(pf.path.name, {}).get(q.name, False) for q in pf.patches}
        sel[p.name] = not sel[p.name]
        prof.patches[pf.path.name] = sel
        prof.name, prof.rom = self.game.name, self.game.path
        profiles.save(prof)

    def _all_off(self) -> None:
        prof = profiles.load(self.game.key)
        prof.patches = {f: {n: False for n in s} for f, s in prof.patches.items()}
        profiles.save(prof)


# ---------------------------------------------------------------------------
def _fmt(v: Any) -> str:
    if isinstance(v, bool):
        return "On" if v else "Off"
    return str(v)


class ProfileScreen(Screen):
    def __init__(self, app: App, key: str, label: str, title_id: Optional[str] = None):
        super().__init__(app)
        self.key = key
        self.title_id = title_id
        self.title = f"Settings - {label}"

    def build(self) -> None:
        prof = profiles.load(self.key)
        self.subtitle = "Left/Right to change, X to reset. Applied next time a game starts from EmulationStation."
        self.items = []
        for s in profiles.CATALOG:
            options: list[tuple[str, Any]] = [("Default", None)]
            options += [("On", True), ("Off", False)] if s.kind == "bool" else s.choices
            self.items.append(Item(
                s.label,
                left=(lambda s=s, o=options: self._cycle(s, o, -1)),
                right=(lambda s=s, o=options: self._cycle(s, o, 1)),
                value=(lambda s=s, o=options: self._label(s, o)),
                options=(lambda s=s: self._set(s.key, None)),
                hint=s.help))
        if self.title_id:
            avail = onlinedata.has_optimized(self.title_id)
            self.items.insert(0, Item(
                "Apply community optimized settings", self._optimized,
                value=lambda: "Available" if avail else ("Not listed" if onlinedata.age() is not None else "Check"),
                hint="Recommended settings for this game from the community optimized-settings list."))
        n_raw = len([k for k in prof.settings if k not in {s.key for s in profiles.CATALOG}])
        self.items.append(Item("More settings...", lambda: self.app.push(RawSettingsScreen(self.app, self.key)),
                               value=lambda: _count_label(n_raw, "changed"),
                               hint="Every option from Xenia's own config file."))
        if prof.settings:
            self.items.append(Item("Reset all settings", lambda: self.app.confirm(
                "Reset", "Put every setting back to default?", self._reset_all)))

    def _optimized(self) -> None:
        tid = self.title_id

        def done(settings: dict) -> None:
            usable = {k: v for k, v in settings.items() if k not in profiles.PROTECTED}
            if not usable:
                self.app.message("Nothing to apply", "The optimized settings for this game are empty.")
                return
            lines = "\n".join(f"{k} = {_fmt(v)}" for k, v in list(usable.items())[:10])
            more = f"\n...and {len(usable) - 10} more" if len(usable) > 10 else ""

            def apply() -> None:
                prof = profiles.load(self.key)
                prof.settings.update(usable)
                profiles.save(prof)
                self.app.toast(f"Applied {len(usable)} setting(s)")
            self.app.confirm("Optimized settings", f"Add these to this game's settings?\n{lines}{more}", apply, "Apply")

        self.app.task("Fetching optimized settings", lambda report: onlinedata.optimized_settings(tid), done)

    def _label(self, s: profiles.Setting, options) -> str:
        cur = profiles.load(self.key).settings.get(s.key)
        for lbl, val in options:
            if val is not None and val == cur and type(val) is type(cur):
                return lbl
        return "Default" if cur is None else _fmt(cur)

    def _cycle(self, s: profiles.Setting, options, step: int) -> None:
        cur = profiles.load(self.key).settings.get(s.key)
        idx = 0
        for i, (_, val) in enumerate(options):
            if val is not None and val == cur and type(val) is type(cur):
                idx = i
        self._set(s.key, options[(idx + step) % len(options)][1])

    def _set(self, dotted: str, value: Any) -> None:
        prof = profiles.load(self.key)
        if value is None:
            prof.settings.pop(dotted, None)
        else:
            prof.settings[dotted] = value
        profiles.save(prof)

    def _reset_all(self) -> None:
        prof = profiles.load(self.key)
        prof.settings = {}
        profiles.save(prof)


class RawSettingsScreen(Screen):
    title = "More settings"

    def __init__(self, app: App, key: str):
        super().__init__(app)
        self.key = key

    def _reference(self) -> tuple[Optional[P.Variant], dict]:
        for v in P.variants():
            if v.toml.is_file():
                try:
                    return v, tomlio.load(v.toml)
                except Exception:
                    continue
        return None, {}

    def build(self) -> None:
        v, data = self._reference()
        self.items = []
        if v is None:
            self.subtitle = ""
            self.items.append(Item("Start any Xbox 360 game once so Xenia creates its config file.", enabled=False))
            return
        self.subtitle = f"From {v.label}'s config. Left/Right to change, X to reset.  * = changed"
        overrides = profiles.load(self.key).settings
        section = None
        for dotted, base in sorted(tomlio.flatten(data).items()):
            if dotted in profiles.PROTECTED or not isinstance(base, (bool, int, float)):
                continue
            sec = dotted.rsplit(".", 1)[0]
            if sec != section:
                section = sec
                self.items.append(Item(sec, header=True))
            name = dotted.rsplit(".", 1)[1]
            self.items.append(Item(
                ("* " if dotted in overrides else "") + name,
                left=(lambda d=dotted, b=base: self._step(d, b, -1)),
                right=(lambda d=dotted, b=base: self._step(d, b, 1)),
                value=(lambda d=dotted, b=base: _fmt(profiles.load(self.key).settings.get(d, b))),
                options=(lambda d=dotted: self._reset(d)), hint=dotted))

    def _step(self, dotted: str, base: Any, step: int) -> None:
        prof = profiles.load(self.key)
        cur = prof.settings.get(dotted, base)
        if isinstance(base, bool):
            new: Any = not bool(cur)
        elif isinstance(base, int):
            new = int(cur) + step
        else:
            new = round(float(cur) + 0.1 * step, 3)
        if new == base and type(new) is type(base):
            prof.settings.pop(dotted, None)
        else:
            prof.settings[dotted] = new
        profiles.save(prof)

    def _reset(self, dotted: str) -> None:
        prof = profiles.load(self.key)
        prof.settings.pop(dotted, None)
        profiles.save(prof)


# ---------------------------------------------------------------------------
class SavesScreen(Screen):
    def __init__(self, app: App, game: library.Game):
        super().__init__(app)
        self.game = game
        self.title = f"Saves - {game.name}"

    def build(self) -> None:
        app, g = self.app, self.game
        tid = g.title_id
        dirs = saves.save_dirs(tid)
        self.subtitle = (f"Saves found in {len(dirs)} folder(s)" if dirs else "No saves yet") + "  |  X on a backup: delete"
        self.items = [
            Item("Back up now", self._backup, enabled=bool(dirs)),
            Item("Export saves...", lambda: app.push(ChoiceScreen(
                app, "Export to", [(lbl, (lambda d=d: self._export(d))) for lbl, d in saves.export_destinations()])),
                enabled=bool(dirs), hint="Makes a zip you can copy to another machine."),
            Item("Restore from a zip file...", lambda: app.push(FileBrowser(app, P.EXPORT_DIR if P.EXPORT_DIR.is_dir()
                                                                             else P.USERDATA, self._restore_file))),
            Item("Backups", header=True),
        ]
        bks = saves.backups(tid)
        for b in bks:
            self.items.append(Item(
                b.label, (lambda b=b: app.confirm("Restore", f"Replace current saves with this backup?\n{b.label}\n"
                                                             "Your current saves are backed up first.",
                                                  lambda: self._restore(b.path), "Restore")),
                options=(lambda b=b: app.confirm("Delete backup", b.label,
                                                 lambda: (b.path.unlink(), app.toast("Deleted")), "Delete")),
                hint=str(b.path)))
        if not bks:
            self.items.append(Item("No backups yet", enabled=False))

    def _backup(self) -> None:
        p = saves.backup(self.game.title_id)
        self.app.toast(f"Saved {p.name}")

    def _export(self, dest: Path) -> None:
        p = saves.export(self.game.title_id, dest, self.game.name)
        self.app.pop()
        self.app.message("Exported", str(p))

    def _restore(self, path: Path) -> None:
        n = saves.restore(path, self.game.title_id)
        self.app.message("Restored", f"{n} file(s) restored.")

    def _restore_file(self, path: Path) -> None:
        self.app.confirm("Restore", f"Restore saves from {path.name}?\nYour current saves are backed up first.",
                         lambda: self._restore(path), "Restore")


# ---------------------------------------------------------------------------
class ChoiceScreen(Screen):
    def __init__(self, app: App, title: str, choices: list[tuple[str, Callable]]):
        super().__init__(app)
        self.title = title
        self.choices = choices

    def build(self) -> None:
        self.items = [Item(lbl, fn) for lbl, fn in self.choices]


class FileBrowser(Screen):
    footer = "A Open/Pick   B Back"

    def __init__(self, app: App, start: Path, on_pick: Callable[[Path], None]):
        super().__init__(app)
        self.cwd = start if start.is_dir() else P.USERDATA
        self.on_pick = on_pick
        self.title = "Choose a file"

    def build(self) -> None:
        self.subtitle = str(self.cwd)
        self.items = []
        if self.cwd.parent != self.cwd:
            self.items.append(Item(".. (up)", lambda: self._go(self.cwd.parent)))
        roots = [Path("/userdata"), Path("/media")]
        for r in roots:
            if r.is_dir() and r != self.cwd and not str(self.cwd).startswith(str(r) + "/"):
                self.items.append(Item(f"[{r}]", (lambda r=r: self._go(r))))
        try:
            entries = sorted(self.cwd.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as e:
            self.items.append(Item(f"Can't open: {e}", enabled=False))
            return
        for p in entries:
            if p.name.startswith("."):
                continue
            if p.is_dir():
                self.items.append(Item(p.name + "/", (lambda p=p: self._go(p))))
            else:
                info = xbox.read_stfs(p) if p.stat().st_size >= 0x1800 else None
                tag = f"{info.type_label} {info.title_id}" if info else ""
                self.items.append(Item(p.name, (lambda p=p: self._pick(p)), value=(lambda t=tag: t)))

    def _go(self, p: Path) -> None:
        self.cwd = p
        self.sel = 0
        self.scroll = 0

    def on_resume(self) -> None:
        self.build()
        self.sel = min(self.sel, max(0, len(self.items) - 1))

    def _pick(self, p: Path) -> None:
        self.app.pop()
        self.on_pick(p)


# ---------------------------------------------------------------------------
class StatusScreen(Screen):
    title = "Xenia status"

    def build(self) -> None:
        self.subtitle = f"{P.os_label()}  |  Xenia Manager {__version__}"
        self.items = [Item("Xenia builds from your system", header=True)]
        for v in P.variants():
            if not v.installed:
                state = "Not included"
            elif v.initialised:
                state = "Ready"
            else:
                state = "Start a game with it once"
            self.items.append(Item(v.label, value=(lambda s=state: s), hint=str(v.toml)))
        self.items += [
            Item("Folders", header=True),
            Item("Saves / content", value=lambda: str(P.content_root()), hint="Where Xenia keeps saves, DLC and updates."),
            Item("Drop folder", value=lambda: str(P.INBOX_DIR)),
            Item("Profiles", value=lambda: str(P.PROFILES_DIR)),
            Item("Backups", value=lambda: str(P.BACKUP_DIR)),
            Item("Log", value=lambda: str(P.LOG_FILE)),
        ]


class NetplayScreen(Screen):
    title = "Xenia Netplay"

    def build(self) -> None:
        app = self.app
        inf = netplay.info()
        bato = P.detect_os() == "batocera"
        self.subtitle = ("AdrianCassar's Xenia Canary fork with online play. Runs under Wine; "
                         "shares saves, DLC and updates with your other Xenia builds.")
        self.items = [Item("Installed version", value=lambda: f"{inf['version']} ({inf.get('channel', 'stable')})"
                           if inf else "Not installed", hint=str(P.NETPLAY_DIR))]
        self.items.append(Item("Install / update (stable)" if inf else "Install Xenia Netplay (stable)",
                               lambda: self._install("stable"),
                               hint="Latest release from github.com/AdrianCassar/xenia-canary."))
        self.items.append(Item("Install latest nightly build", lambda: self._install("nightly"),
                               hint="Newest test build. May be less stable."))
        if inf:
            self.items.append(Item("Download Netplay patches", lambda: app.task(
                "Downloading Netplay patches", lambda report: netplay.download_patches(),
                lambda n: app.message("Netplay patches", f"{n} patch files ready. Pick them under a game's Patches."))))
            if bato:
                self.items += [
                    Item("Batocera", header=True),
                    Item("Use Netplay for every Xbox 360 game", self._toggle_default,
                         value=lambda: "On" if profiles.get_system_emulator() == "xenia-netplay" else "Off",
                         hint="Or choose it per game: game page > Xenia build."),
                    Item("Emulator link", self._relink, value=_plugin_state,
                         hint="The xenia_manager service links Netplay into Batocera. Select to re-link now."),
                ]
            else:
                self.items.append(Item("Start Netplay games from their game page", enabled=False,
                                       hint="Games > pick a game > Play with Xenia Netplay."))
            self.items.append(Item("Remove Xenia Netplay", lambda: app.confirm(
                "Remove Netplay", "Delete Xenia Netplay? Your saves, DLC and updates are kept.",
                self._remove, "Remove")))

    def _install(self, channel: str) -> None:
        def work(report):
            return netplay.install(channel, lambda d, t: report(d / t if t else -1, f"Downloaded {d // (1024 * 1024)} MB"))

        def done(tag):
            if P.detect_os() == "batocera":
                _run_service("start")
                msg = (f"Xenia Netplay {tag} is installed. Choose it per game (game page > Xenia build) "
                       "or for every game on this screen.")
            else:
                msg = f"Xenia Netplay {tag} is installed. Start games with it from their game page."
            self.app.message("Netplay installed", msg)
        self.app.task("Installing Xenia Netplay", work, done)

    def _toggle_default(self) -> None:
        prev_file = P.DATA_DIR / "previous-xbox360-emulator"
        if profiles.get_system_emulator() == "xenia-netplay":
            try:
                prev = prev_file.read_text().strip() or None
            except OSError:
                prev = None
            profiles.set_system_emulator(prev)
        else:
            prev_file.write_text(profiles.get_system_emulator() or "")
            profiles.set_system_emulator("xenia-netplay")

    def _relink(self) -> None:
        _run_service("start")
        self.app.toast("Linked" if _plugin_state() == "Linked" else "Link failed - see the log")

    def _remove(self) -> None:
        netplay.uninstall()
        self.app.toast("Xenia Netplay removed")


def _plugin_state() -> str:
    import site
    try:
        user_site = Path(site.getusersitepackages())
    except Exception:
        return "Unknown"
    return "Linked" if (user_site / "xenia_manager_netplay.py").exists() else "Not linked"


def _run_service(action: str) -> None:
    import subprocess
    svc = P.HOME / "services" / "xenia_manager"
    if svc.exists():
        subprocess.run(["bash", str(svc), action], capture_output=True, timeout=60)


# ---------------------------------------------------------------------------
class GamerProfilesScreen(Screen):
    title = "Gamer profiles"

    def build(self) -> None:
        app = self.app
        profs = gamer.profiles()
        self.subtitle = "Profiles Xenia created. Shown by profile ID (XUID)."
        self.items = []
        for p in profs:
            gs, total = p.gamerscore()
            self.items.append(Item(f"Profile {p.xuid}", (lambda p=p: app.push(GamerProfileScreen(app, p))),
                                   value=(lambda gs=gs, t=total, n=len(p.titles()): f"{gs} / {t} G  |  {n} game(s)")))
        if not profs:
            self.items.append(Item("No profiles yet", enabled=False,
                                   hint="Create a profile inside Xenia (Guide button), then it shows up here."))
        self.items += [
            Item("Tools", header=True),
            Item("Import a profile from a zip...", lambda: app.push(FileBrowser(
                app, P.BACKUP_DIR / "profiles" if (P.BACKUP_DIR / "profiles").is_dir() else P.USERDATA, self._import))),
        ]

    def _import(self, path: Path) -> None:
        self.app.confirm("Import profile", f"Import {path.name}?\nExisting files for that profile are backed up first.",
                         lambda: self.app.message("Imported", f"{gamer.import_profile(path)} file(s) restored."),
                         "Import")


class GamerProfileScreen(Screen):
    def __init__(self, app: App, profile: gamer.Profile):
        super().__init__(app)
        self.profile = profile
        self.title = f"Profile {profile.xuid}"

    def build(self) -> None:
        app, p = self.app, self.profile
        gs, total = p.gamerscore()
        self.subtitle = f"Gamerscore {gs} / {total}"
        self.items = [
            Item("Back up profile and its saves", lambda: self._backup(True)),
            Item("Back up profile only", lambda: self._backup(False)),
            Item("Export to...", lambda: app.push(ChoiceScreen(app, "Export profile to", [
                (lbl, (lambda d=d: self._export(d))) for lbl, d in saves.export_destinations()]))),
            Item("Games", header=True),
        ]
        for t in p.titles():
            self.items.append(Item(
                t.name or t.title_id, (lambda t=t: app.push(TitleAchievementsScreen(app, p, t.title_id, t.name))),
                value=(lambda t=t: f"{t.unlocked}/{t.achievements}  |  {t.gamerscore}/{t.gamerscore_total} G"),
                hint=t.title_id + (f"  |  last played {time.strftime('%Y-%m-%d', time.localtime(t.last_played))}"
                                   if t.last_played else "")))
        if not p.titles():
            self.items.append(Item("No games recorded yet", enabled=False))

    def _backup(self, with_saves: bool) -> None:
        out = gamer.backup_profile(self.profile, include_saves=with_saves)
        self.app.message("Backed up", str(out))

    def _export(self, dest: Path) -> None:
        out = gamer.backup_profile(self.profile, include_saves=True, dest_dir=dest)
        self.app.pop()
        self.app.message("Exported", str(out))


def _achievement_items(achs: list) -> list[Item]:
    items = []
    for a in achs:
        if a.earned:
            when = time.strftime("%Y-%m-%d", time.localtime(a.unlock_time)) if a.unlock_time else ""
            items.append(Item(a.name, value=(lambda a=a, w=when: f"{a.gamerscore} G  |  {w or 'Unlocked'}"),
                              hint=a.description))
        elif a.secret:
            items.append(Item("Secret achievement", value=(lambda a=a: f"{a.gamerscore} G  |  Locked"),
                              hint="Keep playing to reveal it."))
        else:
            items.append(Item(a.name, value=(lambda a=a: f"{a.gamerscore} G  |  Locked"),
                              hint=a.locked_description or a.description))
    return items


class TitleAchievementsScreen(Screen):
    def __init__(self, app: App, profile: gamer.Profile, title_id: str, name: str):
        super().__init__(app)
        self.profile, self.title_id = profile, title_id
        self.title = f"Achievements - {name or title_id}"

    def build(self) -> None:
        achs = self.profile.achievements(self.title_id)
        self.subtitle = (f"Profile {self.profile.xuid}  |  {sum(a.earned for a in achs)} of {len(achs)} unlocked  |  "
                         f"{sum(a.gamerscore for a in achs if a.earned)} G")
        self.items = _achievement_items(achs) or [Item("No achievement data for this game", enabled=False)]


class AchievementsScreen(Screen):
    def __init__(self, app: App, game: library.Game):
        super().__init__(app)
        self.game = game
        self.title = f"Achievements - {game.name}"

    def build(self) -> None:
        self.items = []
        data = gamer.achievements_for(self.game.title_id)
        self.subtitle = f"{len(data)} profile(s) have played this game"
        for prof, achs in data:
            got = sum(a.earned for a in achs)
            self.items.append(Item(f"Profile {prof.xuid}  -  {got}/{len(achs)}  "
                                   f"{sum(a.gamerscore for a in achs if a.earned)} G", header=True))
            self.items += _achievement_items(achs)
        if not data:
            self.items.append(Item("No achievements yet", enabled=False))


class UninstallScreen(Screen):
    title = "Uninstall Xenia Manager"

    def build(self) -> None:
        app = self.app
        self.subtitle = "Your games, saves and Xenia itself are never touched."
        self.items = [
            Item("Uninstall, keep my profiles and backups", lambda: app.confirm(
                "Uninstall", "Remove Xenia Manager but keep profiles, save backups and switched-off content?",
                lambda: self._run([]), "Uninstall"),
                hint="Reinstalling later picks everything back up."),
            Item("Uninstall and delete profiles", lambda: app.confirm(
                "Uninstall", "Remove Xenia Manager and delete its profiles and caches?\n"
                             "Save backups and switched-off content are kept.",
                lambda: self._run(["--purge"]), "Delete"),
                hint="Save backups in saves/xenia-manager are kept either way."),
            Item("Cancel", app.pop),
        ]

    def _run(self, args: list[str]) -> None:
        import subprocess
        script = P.APP_DIR / "uninstall.sh"

        def work(report):
            if not script.is_file():
                raise FileNotFoundError(f"{script} is missing. Run the uninstaller from the project page.")
            r = subprocess.run(["bash", str(script), "--yes", *args], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(r.stderr.strip() or r.stdout.strip() or "Uninstall failed")
            return r.stdout

        self.app.task("Uninstalling", work, lambda out: self.app.message(
            "Uninstalled", "Xenia Manager has been removed. It will disappear from menus after "
                           "EmulationStation refreshes its game lists.", then=self.app.quit))


class AboutScreen(Screen):
    title = "About & credits"

    LINES = [
        ("Xenia Manager for EmulationStation", f"v{__version__}"),
        ("Project", REPO_URL),
        ("License", "MIT"),
        ("Credits", None),
        ("Xenia Manager (original Windows app)", "xenia-manager/xenia-manager - inspiration"),
        ("Xenia emulator", "xenia-project"),
        ("Xenia Canary", "xenia-canary"),
        ("Xenia Edge", "Xenia Edge developers"),
        ("Game patches", "xenia-canary/game-patches community"),
        ("Xenia Netplay", "AdrianCassar/xenia-canary, Xenia-WebServices"),
        ("Compatibility & settings data", "xenia-manager/database, optimized-settings"),
        ("Optimized settings source", "A1eNaz's Xenia Game Settings wiki"),
        ("Batocera Linux", "batocera-linux - host OS and Xenia builds"),
        ("HippOS", "hippos-linux - host OS and Xenia builds"),
        ("File format docs", "Free60 project"),
        ("UI", "pygame / SDL"),
        ("Not affiliated with", None),
        ("the Xenia team, Microsoft, Batocera or HippOS", ""),
    ]

    def build(self) -> None:
        self.items = []
        for a, b in self.LINES:
            if b is None:
                self.items.append(Item(a, header=True))
            else:
                self.items.append(Item(a, value=(lambda b=b: b)))
