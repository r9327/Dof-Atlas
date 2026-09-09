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


def validate_manifest(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Le manifest doit contenir un objet racine."]
    views = data.get("views")
    if views is None:
        return ["La cle 'views' est absente."]
    if not isinstance(views, list):
        return ["La cle 'views' doit contenir une liste."]

    seen_keys: set[str] = set()
    for view_index, view in enumerate(views):
        prefix = f"views[{view_index}]"
        if not isinstance(view, dict):
            errors.append(f"{prefix} doit etre un objet.")
            continue
        view_key = str(view.get("view_key") or "").strip()
        if not view_key:
            errors.append(f"{prefix}.view_key est obligatoire.")
        elif view_key in seen_keys:
            errors.append(f"{prefix}.view_key est en doublon: {view_key}")
        seen_keys.add(view_key)
        if not str(view.get("name") or "").strip():
            errors.append(f"{prefix}.name est obligatoire.")
        maps = view.get("maps", [])
        if maps is None:
            maps = []
        if not isinstance(maps, list):
            errors.append(f"{prefix}.maps doit etre une liste.")
            maps = []
        for map_index, map_row in enumerate(maps):
            map_prefix = f"{prefix}.maps[{map_index}]"
            if not isinstance(map_row, dict):
                errors.append(f"{map_prefix} doit etre un objet.")
                continue
            for key in ("x", "y"):
                try:
                    int(map_row.get(key))
                except (TypeError, ValueError):
                    errors.append(f"{map_prefix}.{key} doit etre un entier.")
            rect = map_row.get("rect")
            if rect is not None and not isinstance(rect, dict):
                errors.append(f"{map_prefix}.rect doit etre un objet.")
        links = view.get("links", [])
        if links is None:
            links = []
        if not isinstance(links, list):
            errors.append(f"{prefix}.links doit etre une liste.")
            continue
        for link_index, link in enumerate(links):
            link_prefix = f"{prefix}.links[{link_index}]"
            if not isinstance(link, dict):
                errors.append(f"{link_prefix} doit etre un objet.")
                continue
            if not str(link.get("target_view_key") or "").strip():
                errors.append(f"{link_prefix}.target_view_key est obligatoire.")
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
    summary["maps"] = sum(len(view.get("maps") or []) for view in views if isinstance(view, dict))
    summary["links"] = sum(len(view.get("links") or []) for view in views if isinstance(view, dict))
    if dry_run:
        return summary

    for view_index, view in enumerate(views):
        try:
            view_key = str(view.get("view_key") or "").strip()
            world_db.upsert_map_view(
                view_key=view_key,
                parent_view_key=view.get("parent_view_key"),
                name=str(view.get("name") or "").strip(),
                kind=str(view.get("kind") or "world").strip() or "world",
                asset_path=view.get("asset_path"),
                min_x=view.get("min_x"),
                max_x=view.get("max_x"),
                min_y=view.get("min_y"),
                max_y=view.get("max_y"),
                tile_width=int(view.get("tile_width") or 64),
                tile_height=int(view.get("tile_height") or 32),
                sort_order=int(view.get("sort_order") or view_index),
                raw_data=view,
            )
            world_db.replace_view_children(view_key)
            for map_row in view.get("maps") or []:
                world_db.upsert_map(
                    view_key=view_key,
                    x=int(map_row["x"]),
                    y=int(map_row["y"]),
                    map_id=str(map_row.get("map_id") or "").strip() or None,
                    status=map_row.get("status") or "unverified",
                    rect_json=map_row.get("rect") or map_row.get("rect_json"),
                    polygon_json=map_row.get("polygon") or map_row.get("polygon_json"),
                    raw_data=map_row,
                )
            for link in view.get("links") or []:
                world_db.add_map_link(
                    from_view_key=view_key,
                    target_view_key=str(link.get("target_view_key") or "").strip(),
                    label=str(link.get("label") or "").strip(),
                    from_x=link.get("from_x"),
                    from_y=link.get("from_y"),
                    link_type=str(link.get("link_type") or "entrance").strip() or "entrance",
                    marker_x=link.get("marker_x"),
                    marker_y=link.get("marker_y"),
                )
        except Exception as exc:
            LOGGER.exception("Import manifest cartographie impossible pour %s", view.get("view_key"))
            summary["errors"].append(f"{view.get('view_key') or view.get('name')}: {exc}")
    return summary
