"""Craft-only fallback for legacy flat image paths in the SQLite seed.

The tracked item sprites live in data/images/items/<family>/<id>.png while
some existing user databases still reference data/images/items/<id>.png.
Resolve lazily per visible icon rather than indexing thousands of images on
startup. Ambiguous matches are deliberately left blank, not guessed.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from app.constants import ROOT_DIR
from app.core.text import normalize_key


_WEAPON_TYPES = {
    "arme", "armes", "epee", "epees", "arc", "arcs", "dague", "dagues",
    "baton", "batons", "baguette", "baguettes", "pelle", "pelles",
    "marteau", "marteaux", "hache", "haches", "lance", "lances",
    "faux",
}
_GROUPS = (
    ({"anneau", "anneaux"}, "anneaux"),
    ({"coiffe", "coiffes"}, "coiffes"),
    ({"cape", "capes"}, "capes"),
    ({"botte", "bottes"}, "bottes"),
    ({"ceinture", "ceintures"}, "ceintures"),
    ({"collier", "colliers", "amulette", "amulettes"}, "colliers"),
    ({"bouclier", "boucliers"}, "boucliers"),
    ({"trophee", "trophees"}, "trophees"),
    ({"prysmaradite", "prysmaradites"}, "prysmaradite"),
    (_WEAPON_TYPES, "armes"),
)


@lru_cache(maxsize=4096)
def _find_nested_image(directory: str, filename: str, family: str) -> str:
    root = Path(directory)
    parts = set(family.split("_"))
    for types, folder in _GROUPS:
        if parts & types:
            candidate = root / folder / filename
            if candidate.is_file():
                return str(candidate)
    # Only use a generic fallback if there is a unique asset for that ID.
    # Several categories may contain the same numeric sprite basename.
    matches = list(root.glob("*/" + filename))
    return str(matches[0]) if len(matches) == 1 else ""


def craft_image_item(item: dict[str, Any], *, root: Path = ROOT_DIR) -> dict[str, Any]:
    raw = item.get("image_path") or item.get("local_image_path")
    if not raw:
        return item
    path = Path(str(raw))
    absolute = path if path.is_absolute() else root / path
    if absolute.is_file():
        return item
    directory = root / "data" / "images" / "items"
    if absolute.parent != directory or absolute.suffix.lower() not in {".png", ".webp"}:
        return item
    family = normalize_key(" ".join(str(item.get(key) or "") for key in (
        "type", "family", "category",
    )))
    found = _find_nested_image(str(directory), absolute.name, family)
    return {**item, "image_path": found} if found else item
