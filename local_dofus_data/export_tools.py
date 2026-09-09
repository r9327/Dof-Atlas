from __future__ import annotations

import argparse
import json
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig, ensure_directories
from .data_store import DataStore
from .utils import save_json_atomic


EXPORT_TABLES = {
    "items": "items",
    "resources": "resources",
    "equipment": "equipment",
    "item_sets": "item_sets",
    "consumables": "consumables",
    "recipes": "recipes",
    "jobs": "jobs",
    "spells": "spells",
    "classes": "classes",
    "monsters": "monsters",
    "monster_families": "monster_families",
    "maps": "maps",
    "areas": "areas",
    "subareas": "subareas",
    "texts": "texts",
    "images": "image_assets",
    "effects": "effects",
    "item_effects": "item_effects",
    "monster_spells": "monster_spells",
    "class_spells": "class_spells",
    "conditions": "conditions",
}


def decode_row(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    for key, value in list(result.items()):
        if key.endswith("_json") and isinstance(value, str):
            try:
                result[key] = json.loads(value)
            except Exception:
                result[key] = {}
    return result


def export_all(store: DataStore | None = None, config: LocalDataConfig = DEFAULT_CONFIG) -> dict[str, int]:
    ensure_directories(config)
    store = store or DataStore(config=config)
    store.initialize()
    counts: dict[str, int] = {}
    full: dict[str, Any] = {}
    for export_name, table in EXPORT_TABLES.items():
        rows = [decode_row(row) for row in store.query_all(f"SELECT * FROM {table}")]
        save_json_atomic(config.exports_dir / f"{export_name}.json", rows)
        counts[export_name] = len(rows)
        full[export_name] = rows
    ingredients = [decode_row(row) for row in store.query_all("SELECT * FROM recipe_ingredients")]
    save_json_atomic(config.exports_dir / "recipe_ingredients.json", ingredients)
    counts["recipe_ingredients"] = len(ingredients)
    full["recipe_ingredients"] = ingredients
    save_json_atomic(config.exports_dir / "full_export.json", full)
    return counts


def main(argv: list[str] | None = None) -> dict[str, int]:
    parser = argparse.ArgumentParser(description="Export local Dofus SQLite data to JSON")
    parser.add_argument("--all", action="store_true", help="export all known tables")
    args = parser.parse_args(argv)
    counts = export_all()
    print(json.dumps({"exports": counts}, ensure_ascii=False, indent=2))
    return counts


if __name__ == "__main__":
    main()
