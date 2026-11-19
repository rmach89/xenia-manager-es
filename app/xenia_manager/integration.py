"""Helpers used by install.sh / uninstall.sh to edit EmulationStation files."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def gamelist_upsert(gamelist: Path, rel_path: str, name: str, desc: str, image: str) -> None:
    if gamelist.is_file():
        try:
            tree = ET.parse(gamelist)
            root = tree.getroot()
        except ET.ParseError:
            return  # never risk damaging a user's list
    else:
        gamelist.parent.mkdir(parents=True, exist_ok=True)
        root = ET.Element("gameList")
        tree = ET.ElementTree(root)
    game = None
    for g in root.findall("game"):
        if (g.findtext("path") or "").strip() == rel_path:
            game = g
            break
    if game is None:
        game = ET.SubElement(root, "game")
    for tag, val in (("path", rel_path), ("name", name), ("desc", desc), ("image", image),
                     ("thumbnail", image), ("developer", "rmach89"), ("genre", "Tools")):
        el = game.find(tag)
        if el is None:
            el = ET.SubElement(game, tag)
        el.text = val
    ET.indent(tree, space="\t")
    tree.write(gamelist, encoding="utf-8", xml_declaration=True)


def gamelist_remove(gamelist: Path, rel_path: str) -> None:
    if not gamelist.is_file():
        return
    try:
        tree = ET.parse(gamelist)
    except ET.ParseError:
        return
    root = tree.getroot()
    changed = False
    for g in root.findall("game"):
        if (g.findtext("path") or "").strip() == rel_path:
            root.remove(g)
            changed = True
    if changed:
        tree.write(gamelist, encoding="utf-8", xml_declaration=True)


def clear_emulator_choices() -> None:
    """Remove per-game Xenia build choices this app wrote to batocera.conf."""
    from . import profiles
    for prof in profiles.all_profiles():
        if prof.emulator and prof.rom:
            profiles.set_batocera_emulator(Path(prof.rom).name, None)


def main(argv: list[str]) -> int:
    cmd = argv[0]
    if cmd == "gamelist-add":
        gamelist_upsert(Path(argv[1]), argv[2], argv[3], argv[4], argv[5])
    elif cmd == "gamelist-remove":
        gamelist_remove(Path(argv[1]), argv[2])
    elif cmd == "clear-emulator-choices":
        clear_emulator_choices()
    else:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
