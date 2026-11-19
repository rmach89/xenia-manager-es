"""Minimal TOML read/write. Reading uses the standard library (tomllib);
writing covers what Xenia configs contain: tables, nested tables, scalars
and arrays. Both host launchers already rewrite these files without
comments, so we lose nothing by dumping them the same way."""

from __future__ import annotations

import math
import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any

_MISSING = object()


def load(path: Path) -> dict[str, Any]:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _key(k: str) -> str:
    if k and all(c.isalnum() or c in "_-" for c in k):
        return k
    return _str(k)


def _str(s: str) -> str:
    out = s.replace("\\", "\\\\").replace('"', '\\"')
    out = out.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")
    return f'"{out}"'


def _value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v):
            return "nan"
        if math.isinf(v):
            return "inf" if v > 0 else "-inf"
        r = repr(v)
        return r if ("." in r or "e" in r or "E" in r) else r + ".0"
    if isinstance(v, str):
        return _str(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_value(x)}" for k, x in v.items()) + " }"
    return _str(str(v))


def dumps(data: dict[str, Any]) -> str:
    lines: list[str] = []

    def table(prefix: list[str], tbl: dict[str, Any]) -> None:
        scalars = [(k, v) for k, v in tbl.items() if not isinstance(v, dict)]
        subs = [(k, v) for k, v in tbl.items() if isinstance(v, dict)]
        if prefix and (scalars or not subs):
            if lines:
                lines.append("")
            lines.append("[" + ".".join(_key(p) for p in prefix) + "]")
        for k, v in scalars:
            lines.append(f"{_key(k)} = {_value(v)}")
        for k, v in subs:
            table(prefix + [k], v)

    table([], data)
    return "\n".join(lines) + "\n"


def save(path: Path, data: dict[str, Any]) -> None:
    """Atomic write so a half-written config never reaches Xenia."""
    text = dumps(data)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".xm-", suffix=".toml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_path(data: dict[str, Any], dotted: str, default: Any = _MISSING) -> Any:
    """Look up 'Section.key' or 'Section.Sub.key'."""
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None if default is _MISSING else default
        cur = cur[part]
    return cur


def set_path(data: dict[str, Any], dotted: str, value: Any) -> Any:
    """Set a dotted key, returning the previous value (or _MISSING)."""
    parts = dotted.split(".")
    cur = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    prev = cur.get(parts[-1], _MISSING)
    cur[parts[-1]] = value
    return prev


def del_path(data: dict[str, Any], dotted: str) -> None:
    parts = dotted.split(".")
    cur: Any = data
    for part in parts[:-1]:
        cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is None:
            return
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)


def flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in data.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out


MISSING = _MISSING
