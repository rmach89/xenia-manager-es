"""UI entry point."""

from __future__ import annotations

from .. import APP_NAME
from .. import platform as P


def run(bigscreen: bool = False, uninstall: bool = False) -> int:
    P.ensure_data_dirs()
    from .core import App
    from .screens import Home, UninstallScreen, background_update_check, scan_task

    app = App(APP_NAME, bigscreen)
    app.games = []
    app.push(Home(app))
    if uninstall:
        app.push(UninstallScreen(app))
    else:
        P.INBOX_DIR.mkdir(parents=True, exist_ok=True)
        scan_task(app)
        background_update_check(app)
    return app.run()
