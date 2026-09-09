from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from local_dofus_data.config import DEFAULT_CONFIG, ensure_directories
from local_dofus_data.utils import save_json_atomic


DATA_DIR = DEFAULT_CONFIG.data_dir
MANIFEST_FILE = DEFAULT_CONFIG.reports_dir / "local_data_manifest.json"


def _compatibility_adapter():
    # Keep the SQLite/repository stack out of application import time. Craft and
    # other local-data consumers resolve it only when they actually need data.
    from local_dofus_data import compatibility_adapter

    return compatibility_adapter


def ensure_dirs() -> None:
    ensure_directories(DEFAULT_CONFIG)


def atomic_write_json(path: str | Path, payload: Any) -> None:
    save_json_atomic(path, payload)


def search_items(query: str, limit: int = 50) -> list[dict[str, Any]]:
    return _compatibility_adapter().search_items(query, limit)


def get_item(item_id: int) -> dict[str, Any] | None:
    return _compatibility_adapter().get_item(item_id)


def get_item_by_name(name: str) -> dict[str, Any] | None:
    return _compatibility_adapter().get_item_by_name(name)


def get_item_image(item_id: int) -> str:
    return _compatibility_adapter().get_item_image(item_id)


def get_cached_image_path(item_id: int) -> str:
    return _compatibility_adapter().get_cached_image_path(item_id)


def get_recipe(item_id: int) -> dict[str, Any]:
    return _compatibility_adapter().get_recipe(item_id)


def get_recipe_for_item(item_id: int, force_refresh: bool = False) -> dict[str, Any]:
    return _compatibility_adapter().get_recipe_for_item(item_id, force_refresh=force_refresh)


def get_resources_for_recipe(item_id: int) -> list[dict[str, Any]]:
    return _compatibility_adapter().get_resources_for_recipe(item_id)


def list_items() -> list[dict[str, Any]]:
    return _compatibility_adapter().list_items()


def list_resources() -> list[dict[str, Any]]:
    return _compatibility_adapter().list_resources()


def list_jobs() -> list[dict[str, Any]]:
    return _compatibility_adapter().list_jobs()


def list_recipes() -> list[dict[str, Any]]:
    return _compatibility_adapter().list_recipes()


def list_craft_items() -> list[dict[str, Any]]:
    return _compatibility_adapter().list_craft_items()


def build_craft_list(items_with_quantities: list[dict[str, Any]] | dict[int, int]) -> list[dict[str, Any]]:
    return _compatibility_adapter().build_craft_list(items_with_quantities)


def get_item_set_for_item(item_id: int) -> dict[str, Any] | None:
    return _compatibility_adapter().get_item_set_for_item(item_id)


def cache_api() -> dict[str, int]:
    from local_dofus_data.import_manager import run_import

    report = run_import(full=False, offline=True, config=DEFAULT_CONFIG)
    return {
        "items": report["summary"]["counts"].get("items", 0),
        "jobs": report["summary"]["counts"].get("jobs", 0),
        "craftable_items": len(list_craft_items()),
        "recipes": report["summary"]["counts"].get("recipes", 0),
    }


def recipe_cache_path(item_id_dofus: int) -> Path:
    _ = item_id_dofus
    return DEFAULT_CONFIG.exports_dir / "recipes.json"


def load_or_fetch_recipe_index() -> dict[str, Any]:
    recipes = list_recipes()
    result_ids = sorted({recipe.get("result_id") for recipe in recipes if recipe.get("result_id") is not None})
    return {
        "source": "local_dofus_data",
        "count": len(result_ids),
        "result_ids": result_ids,
        "recipes": [
            {
                "result_id": recipe.get("result_id"),
                "name": recipe.get("result_name", ""),
                "level": recipe.get("level"),
                "job_id": recipe.get("job_id"),
            }
            for recipe in recipes
        ],
    }


def fetch_recipe_index(limit: int = 500) -> dict[str, Any]:
    _ = limit
    return load_or_fetch_recipe_index()


def sync_local_data_cache() -> dict[str, Any]:
    from local_dofus_data.import_manager import run_import

    report = run_import(full=False, offline=True, config=DEFAULT_CONFIG)
    manifest = {
        "updated_at": report.get("finished_at"),
        "duration_ms": 0,
        "api": {
            "items": report["summary"]["counts"].get("items", 0),
            "jobs": report["summary"]["counts"].get("jobs", 0),
            "craftable_items": len(list_craft_items()),
            "recipes": report["summary"]["counts"].get("recipes", 0),
        },
        "errors": report.get("errors", []),
        "source": "local_dofus_data",
        "sqlite": str(DEFAULT_CONFIG.sqlite_path),
    }
    save_json_atomic(MANIFEST_FILE, manifest)
    return manifest


def main() -> None:
    manifest = sync_local_data_cache()
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
