"""Update Xenia Manager from its GitHub repository.

Checks the version on the branch or tag this copy was installed from, then
re-runs that branch's install.sh, which keeps profiles and settings.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import urllib.request
from typing import Optional

from . import __version__
from . import platform as P

REPO = "rmach89/xenia-manager-es"
RAW = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"


def installed_ref() -> str:
    """Branch or tag recorded by install.sh in VERSION, e.g. '1.0.0 (main)'."""
    try:
        m = re.search(r"\(([^)]+)\)", (P.APP_DIR / "VERSION").read_text())
        if m:
            return m.group(1).strip()
    except OSError:
        pass
    return "main"


def _fetch(path: str, ref: str, timeout: float = 20) -> bytes:
    url = RAW.format(repo=REPO, ref=ref, path=path)
    req = urllib.request.Request(url, headers={"User-Agent": "xenia-manager-es", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def remote_version(ref: Optional[str] = None) -> str:
    text = _fetch("app/xenia_manager/__init__.py", ref or installed_ref()).decode("utf-8", "replace")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not m:
        raise RuntimeError("Couldn't read the version from the repository.")
    return m.group(1)


def check(ref: Optional[str] = None) -> tuple[str, str, bool]:
    """Returns (installed, available, newer_available)."""
    remote = remote_version(ref)
    return __version__, remote, _tuple(remote) > _tuple(__version__)


def update(ref: Optional[str] = None) -> str:
    """Download and run install.sh from the repository. Returns its output."""
    ref = ref or installed_ref()
    script = _fetch("install.sh", ref, timeout=60)
    fd, path = tempfile.mkstemp(prefix="xm-install-", suffix=".sh")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(script)
        env = dict(os.environ, XM_REF=ref)
        r = subprocess.run(["bash", path], capture_output=True, text=True, env=env, timeout=600)
    finally:
        os.unlink(path)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        raise RuntimeError(out.strip().splitlines()[-1] if out.strip() else "The installer failed.")
    return out
