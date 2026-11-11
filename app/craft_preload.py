from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from app.constants import (
    CRAFT_SELECTION_FILE,
    HARVEST_JOBS,
    JOB_ORDER,
    JOB_RESOURCE_GROUPS,
    LEVELING_FILE,
)
from local_dofus_data.config import DEFAULT_CONFIG
from app.core.item_identity import item_id
from app.core.json_store import read_json_resilient as read_json
from app.core.text import normalize_key



def build_local_leveling_suggestions(
    job_name: str, *, database_path: Path | None = None,
) -> dict[str, object] | None:
    """Offline, explicitly non-optimized alternative when curated guides are absent.

    Read only already-installed, public Craft data. Do not infer XP gains or
    present a single sample craft as the quantity needed to gain 20 levels.
    Called on an explicit job click, never during Craft/Home preload.
    """
    job_key = normalize_key(job_name)
    if job_key not in JOB_ORDER:
        return None

    if job_key in HARVEST_JOBS:
        for name, resources in JOB_RESOURCE_GROUPS.items():
            if normalize_key(name) == job_key and resources:
                return {
                    "source": "atlas-local",
                    "kind": "harvest",
                    "entries": [
                        {
                            "level_range": f"Étape {index}",
                            "craft": {"name": resource_name, "quantity": 1},
                        }
                        for index, (resource_name, _tag) in enumerate(resources, 1)
                    ],
                }
        return None

    path = database_path if database_path is not None else DEFAULT_CONFIG.sqlite_path
    if not path.is_file():
        return None
    try:
        # The public Craft seed, installed on first launch, is canonical.
        # Opening in read-only mode prevents sidecar files or user-data writes.
        with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
            candidates = db.execute(
                """
                SELECT r.level, r.result_name_fr, COUNT(ri.id) AS ingredient_count
                FROM recipes AS r
                JOIN recipe_ingredients AS ri ON ri.recipe_id = r.id
                WHERE r.job_name = ? COLLATE NOCASE
                  AND r.level BETWEEN 1 AND 200
                  AND r.result_name_fr <> ''
                GROUP BY r.id, r.level, r.result_name_fr
                ORDER BY r.level, ingredient_count, r.result_name_fr
                """,
                (job_name,),
            ).fetchall()
    except (OSError, sqlite3.Error, ValueError):
        return None

    entries = []
    previous_name = None
    # Only suggest a recipe once its real required level has been reached.
    for level in (1, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200):
        available = [row for row in candidates if row[0] <= level]
        if not available:
            continue
        recipe_level, recipe_name, ingredient_count = min(
            available, key=lambda row: (-row[0], row[2], row[1])
        )
        if recipe_name == previous_name:
            continue
        previous_name = recipe_name
        entries.append({
            "level_range": f"Niv. {level}+",
            "craft": {"name": recipe_name, "quantity": 1},
            "recipe_level": recipe_level,
            "ingredient_types": ingredient_count,
        })
    return {"source": "atlas-local", "kind": "craft", "entries": entries} if entries else None


def build_compact_craft_preload() -> dict[str, object]:
    """Prepare only small Craft metadata; searchable items stay SQLite-backed."""

    payload: dict[str, object] = {
        "items": [],
        "items_by_name": {},
        "jobs": [],
        "guides": read_json(
            LEVELING_FILE,
            {"source": "gamosaurus", "offline_runtime": True, "guides": {}},
        ),
        "selection": {},
        "lookup_items": [],
        "_prepared": False,
        "_lazy_items": True,
        "errors": [],
    }

    database_path = DEFAULT_CONFIG.sqlite_path
    if not database_path.exists():
        payload["_skipped_reason"] = "catalogue Craft local absent"
        return payload

    try:
        connection = sqlite3.connect(database_path)
        try:
            has_items = connection.execute("SELECT 1 FROM items LIMIT 1").fetchone() is not None
        finally:
            connection.close()
    except sqlite3.Error as exc:
        payload["errors"].append(str(exc))
        return payload
    if not has_items:
        payload["_skipped_reason"] = "catalogue Craft local vide"
        return payload

    from local_dofus_data.compatibility_adapter import LocalCompatibilityAdapter

    adapter = LocalCompatibilityAdapter()
    try:
        payload["jobs"] = adapter.list_jobs()

        lookup_names = {"Ortie", "Frene", "Fer", "Ble", "Goujon", "Viande Fraiche"}
        for resource_group in JOB_RESOURCE_GROUPS.values():
            lookup_names.update(resource_name for resource_name, _tag in resource_group)

        lookup_items: list[dict[str, object]] = []
        seen_lookup_ids: set[object] = set()
        for name in sorted(lookup_names, key=normalize_key):
            try:
                results = adapter.search_items(name, limit=1)
            except Exception:
                results = []
            if not results:
                continue
            item = results[0]
            ident = item_id(item) or item.get("name")
            if ident in seen_lookup_ids:
                continue
            seen_lookup_ids.add(ident)
            lookup_items.append(item)
        payload["lookup_items"] = lookup_items

        selection_payload = read_json(CRAFT_SELECTION_FILE, {"items": []})
        rows = selection_payload.get("items") if isinstance(selection_payload, dict) else []
        selection: dict[int, dict[str, object]] = {}
        if isinstance(rows, list):
            for row in rows:
                try:
                    ident = int(row.get("ankama_id") or row.get("item_id"))
                except (AttributeError, TypeError, ValueError):
                    continue
                item = adapter.get_item(ident)
                if item:
                    selection[ident] = {
                        "item": item,
                        "quantity": max(1, int(row.get("quantity") or 1)),
                    }
        payload["selection"] = selection
    except Exception as exc:
        errors = payload.get("errors")
        if isinstance(errors, list):
            errors.append(str(exc))
    finally:
        adapter.close()
    if not payload["errors"]:
        # SQLite catalogue and adapter were both usable. Empty eager item
        # lists are normal: all searchable items remain SQLite-backed.
        payload["_prepared"] = True
    return payload


def main() -> int:
    payload = json.dumps(
        build_compact_craft_preload(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if "--result-file" in sys.argv:
        try:
            result_path = Path(sys.argv[sys.argv.index("--result-file") + 1])
        except (ValueError, IndexError):
            return 2
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
