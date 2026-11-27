"""One filesystem resolver for Craft item artwork, shared by all Craft views.

The database item's ID is not its sprite ID. Only an explicitly supplied
image filename may be searched in the matching shipped image folder. Unknown
families never receive an arbitrary icon when multiple candidates exist.
"""
from __future__ import annotations

from functools import lru_cache
from glob import escape
from pathlib import Path
from typing import Any, Mapping

from app.constants import ROOT_DIR
from app.core.text import normalize_key


_ARTWORK_FOLDERS = (
    ({"anneau", "anneaux"}, "anneaux"),
    ({"coiffe", "coiffes"}, "coiffes"),
    ({"cape", "capes"}, "capes"),
    ({"botte", "bottes"}, "bottes"),
    ({"ceinture", "ceintures"}, "ceintures"),
    ({"collier", "colliers", "amulette", "amulettes"}, "colliers"),
    ({"bouclier", "boucliers"}, "boucliers"),
    ({"trophee", "trophees"}, "trophees"),
    ({"prysmaradite", "prysmaradites"}, "prysmaradite"),
    ({
        "arme", "armes", "epee", "epees", "arc", "arcs",
        "dague", "dagues", "baton", "batons", "baguette",
        "baguettes", "pelle", "pelles", "marteau", "marteaux",
        "hache", "haches", "lance", "lances", "faux",
        "weapon", "weapons",
    }, "armes"),
)


def _nested_artwork(directory: str, filename: str, family: str) -> Path | None:
    root = Path(directory)
    tokens = set(family.split("_"))
    for kinds, folder in _ARTWORK_FOLDERS:
        if kinds & tokens:
            candidate = root / folder / filename
            if candidate.is_file():
                return candidate
    # A missing or ambiguous asset can change after an incremental update.
    # Never retain these guesses indefinitely. Known families above use an
    # exact path; only the fallback enumerates one directory level.
    matches = tuple(path for path in root.glob("*/" + escape(filename)) if path.is_file())
    return matches[0] if len(matches) == 1 else None


def item_artwork_path(
    item: Mapping[str, Any], *, root: Path = ROOT_DIR,
) -> Path | None:
    """Resolve the one real local sprite for a Craft item or resource."""
    raw = item.get("image_path") or item.get("local_image_path")
    if not raw:
        return None
    base = Path(root)
    path = Path(str(raw))
    absolute = path if path.is_absolute() else base / path
    if absolute.is_file():
        return absolute

    directory = base / "data" / "images" / "items"
    if (
        absolute.parent != directory
        or absolute.suffix.casefold() not in {".png", ".webp"}
    ):
        return None
    family = normalize_key(" ".join(str(item.get(key) or "") for key in (
        "type", "family", "category",
    )))
    return _nested_artwork(str(directory), absolute.name, family)


@lru_cache(maxsize=1)
def item_icon_index() -> dict[int, str]:
    """Lazy official item ID -> sprite ID -> local artwork mapping.

    The Quest catalogue and item source files are only read on first actual
    request for an item icon, never when the Craft/Organizer shell imports.
    """
    from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR
    from app.quest_catalog import doduda_rows, safe_int
    from app.quest_source_index import build_image_index

    sprites = build_image_index(DATA_DIR / "images")
    result: dict[int, str] = {}
    for item_id, row in doduda_rows(RAW_QUEST_DATA_DIR / "items.json").items():
        icon_id = safe_int(row.get("iconId"))
        if icon_id is None:
            continue
        path = sprites.get(str(icon_id))
        if path:
            result[int(item_id)] = path
    return result


def item_icon_path(item_id: int | None) -> str:
    """The single official item-icon lookup for Quests and Guide Preparation."""
    return item_icon_index().get(int(item_id), "") if item_id is not None else ""


def item_with_artwork(
    item: dict[str, Any], *, root: Path = ROOT_DIR,
) -> dict[str, Any]:
    """Preserve supplied metadata when artwork needs no correction."""
    path = item_artwork_path(item, root=root)
    raw = item.get("image_path") or item.get("local_image_path")
    if path is None or not raw:
        return item
    original = Path(str(raw))
    absolute = original if original.is_absolute() else Path(root) / original
    return item if path == absolute else {**item, "image_path": str(path)}
