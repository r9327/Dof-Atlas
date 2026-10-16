from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.constants import DATA_DIR, LOGGER
import app.cartography.world_db as world_db

MAP_VIEWS_PATH = DATA_DIR / "cartography" / "map_views.json"


def empty_summary() -> dict[str, Any]:
    return {"views": 0, "maps": 0, "links": 0, "errors": []}


def load_manifest(path: str | Path | None = None) -> tuple[dict[str, Any] | None, list[str]]:
    manifest_path = Path(path) if path is not None else MAP_VIEWS_PATH
    if not manifest_path.exists():
        return None, [f"Manifest cartographie introuvable: {manifest_path}"]
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"JSON invalide: {exc.msg} ligne {exc.lineno}, colonne {exc.colno}"]
    except OSError as exc:
        return None, [f"Lecture impossible: {exc}"]
    errors = validate_manifest(data)
    if errors:
        return None, errors
    return data, []


def _manifest_integer(value: Any) -> int | None:
    """Reject truncated floats and booleans even though int() accepts them."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text and text.lstrip("+-").isdigit():
            return int(text)
    return None


def validate_manifest(data: Any) -> list[str]:
    """Two-pass check: all declared views first, then their references."""
    if not isinstance(data, dict):
        return ["Le manifest doit contenir un objet racine."]
    views = data.get("views")
    if not isinstance(views, list):
        return ["La cle 'views' doit contenir une liste."]

    errors: list[str] = []
    by_key: dict[str, dict[str, Any]] = {}
    parents: dict[str, str] = {}
    external_keys = data.get("external_view_keys", [])
    if not isinstance(external_keys, list) or any(
        not isinstance(key, str) or not key.strip() for key in external_keys
    ):
        errors.append("external_view_keys doit etre une liste de cles non vides.")
        external_keys = []
    external = set(external_keys)

    for index, view in enumerate(views):
        prefix = f"views[{index}]"
        if not isinstance(view, dict):
            errors.append(f"{prefix} doit etre un objet.")
            continue
        key = str(view.get("view_key") or "").strip()
        if not key:
            errors.append(f"{prefix}.view_key est obligatoire.")
        elif key in by_key:
            errors.append(f"{prefix}.view_key est en doublon: {key}")
        else:
            by_key[key] = view
        if not str(view.get("name") or "").strip():
            errors.append(f"{prefix}.name est obligatoire.")
        parent = str(view.get("parent_view_key") or "").strip()
        if key:
            parents[key] = parent
        for field in ("min_x", "max_x", "min_y", "max_y", "sort_order"):
            raw = view.get(field)
            if raw not in (None, "") and _manifest_integer(raw) is None:
                errors.append(f"{prefix}.{field} doit etre un entier.")
        for dimension in ("x", "y"):
            low = _manifest_integer(view.get(f"min_{dimension}"))
            high = _manifest_integer(view.get(f"max_{dimension}"))
            if low is not None and high is not None and low > high:
                errors.append(f"{prefix}: min_{dimension} > max_{dimension}.")
        for field in ("tile_width", "tile_height"):
            raw = view.get(field)
            if raw not in (None, ""):
                value = _manifest_integer(raw)
                if value is None or value <= 0:
                    errors.append(f"{prefix}.{field} doit etre un entier positif.")

        maps = view.get("maps", [])
        if maps is None:
            maps = []
        if not isinstance(maps, list):
            errors.append(f"{prefix}.maps doit etre une liste.")
            maps = []
        seen_coords: set[tuple[int, int]] = set()
        for map_index, row in enumerate(maps):
            loc = f"{prefix}.maps[{map_index}]"
            if not isinstance(row, dict):
                errors.append(f"{loc} doit etre un objet.")
                continue
            coords: list[int] = []
            for axis in ("x", "y"):
                coordinate = _manifest_integer(row.get(axis))
                if coordinate is None:
                    errors.append(f"{loc}.{axis} doit etre un entier.")
                else:
                    coords.append(coordinate)
                    low = _manifest_integer(view.get(f"min_{axis}"))
                    high = _manifest_integer(view.get(f"max_{axis}"))
                    if (low is not None and coordinate < low) or (high is not None and coordinate > high):
                        errors.append(f"{loc}.{axis} hors limites de la vue.")
            if len(coords) == 2:
                pair = (coords[0], coords[1])
                if pair in seen_coords:
                    errors.append(f"{loc}: coordonnees en doublon {pair}.")
                seen_coords.add(pair)
            for field in ("rect", "polygon", "rect_json", "polygon_json"):
                value = row.get(field)
                if value is not None and not isinstance(value, (dict, list, str)):
                    errors.append(f"{loc}.{field}: geometrie invalide.")

        links = view.get("links", [])
        if links is None:
            links = []
        if not isinstance(links, list):
            errors.append(f"{prefix}.links doit etre une liste.")
            links = []
        for link_index, link in enumerate(links):
            loc = f"{prefix}.links[{link_index}]"
            if not isinstance(link, dict):
                errors.append(f"{loc} doit etre un objet.")
                continue
            target = str(link.get("target_view_key") or "").strip()
            if not target:
                errors.append(f"{loc}.target_view_key est obligatoire.")
            elif target not in by_key and target not in external:
                # The second pass below handles forward references.
                pass
            for field in ("from_x", "from_y", "marker_x", "marker_y"):
                raw = link.get(field)
                if raw not in (None, "") and _manifest_integer(raw) is None:
                    errors.append(f"{loc}.{field} doit etre un entier.")

    for index, view in enumerate(views):
        if not isinstance(view, dict):
            continue
        key = str(view.get("view_key") or "").strip()
        parent = str(view.get("parent_view_key") or "").strip()
        if parent and parent not in by_key:
            errors.append(f"views[{index}].parent_view_key absent: {parent}")
        links = view.get("links") or ()
        if not isinstance(links, list):
            continue
        for link_index, link in enumerate(links):
            if not isinstance(link, dict):
                continue
            target = str(link.get("target_view_key") or "").strip()
            if target and target not in by_key and target not in external:
                if link.get("external_target") is not True:
                    errors.append(f"views[{index}].links[{link_index}]: cible absente {target}")

    # Parent relationships must be acyclic even when all references exist.
    for key in by_key:
        visited: set[str] = set()
        current = key
        while current:
            if current in visited:
                errors.append(f"Cycle de parents dans la vue {key}.")
                break
            visited.add(current)
            current = parents.get(current, "")
    return errors


def import_map_view_manifest(path: str | Path | None = None, dry_run: bool = False) -> dict[str, Any]:
    summary = empty_summary()
    data, errors = load_manifest(path)
    if errors:
        summary["errors"].extend(errors)
        return summary
    if data is None:
        return summary

    views = data.get("views") or []
    summary["views"] = len(views)
    summary["maps"] = sum(len(view.get("maps") or []) for view in views)
    summary["links"] = sum(len(view.get("links") or []) for view in views)
    if dry_run:
        return summary

    try:
        world_db.import_manifest_rows(views)
    except Exception as exc:
        LOGGER.exception("Import manifest cartographie annule (transaction complete)")
        summary["errors"].append(f"Transaction annulee : {exc}")
    return summary
