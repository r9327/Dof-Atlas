from __future__ import annotations

import json
import sqlite3

from app.constants import (
    CRAFT_SELECTION_FILE,
    DATA_DIR,
    JOB_RESOURCE_GROUPS,
    LEVELING_FILE,
)
from app.storage import item_id, normalize_key, read_json


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
        "_prepared": True,
        "_lazy_items": True,
        "errors": [],
    }

    database_path = DATA_DIR / "local" / "dofus_data.sqlite"
    if not database_path.exists():
        payload["_skipped_reason"] = "catalogue Craft local absent"
        return payload

    try:
        with sqlite3.connect(database_path) as connection:
            has_items = connection.execute("SELECT 1 FROM items LIMIT 1").fetchone() is not None
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
    return payload


def main() -> int:
    print(
        json.dumps(
            build_compact_craft_preload(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
