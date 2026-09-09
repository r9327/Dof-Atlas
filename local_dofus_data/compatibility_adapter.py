from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig
from .utils import now_iso, slugify


def craft_category_for_item(item: dict[str, Any]) -> str:
    text = slugify(
        " ".join(str(item.get(key, "")) for key in ("name", "type", "family", "category"))
    )
    if any(token in text for token in ("trophee", "prysma", "prysmaradite")):
        return "trophy_prysma"
    if any(
        token in text
        for token in (
            "arme",
            "coiffe",
            "cape",
            "ceinture",
            "anneau",
            "collier",
            "amulette",
            "botte",
            "bouclier",
            "dofus",
        )
    ):
        return "equipment"
    return "resource"


def decorate_craft_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in items:
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("_search_name"), str):
            item["_search_name"] = slugify(item.get("name"))
        if item.get("_craft_category") not in {"equipment", "trophy_prysma", "resource"}:
            item["_craft_category"] = craft_category_for_item(item)
    return items


class LocalCompatibilityAdapter:
    def __init__(self, config: LocalDataConfig = DEFAULT_CONFIG, auto_initialize: bool = True):
        # Import the SQLite store/repositories only when an adapter is actually
        # instantiated. Craft imports this class at application import time, but
        # should not load the full local-data stack before the user opens Craft.
        from .data_store import DataStore
        from .repositories import (
            ImageRepository,
            ItemRepository,
            ItemSetRepository,
            JobRepository,
            RecipeRepository,
            ResourceRepository,
        )

        self.config = config
        self.store = DataStore(config=config)
        self.store.initialize()
        if auto_initialize:
            self.ensure_ready()
        self.items = ItemRepository(self.store, config)
        self.resources = ResourceRepository(self.store, config)
        self.recipes = RecipeRepository(self.store, config)
        self.item_sets = ItemSetRepository(self.store, config)
        self.jobs = JobRepository(self.store, config)
        self.images = ImageRepository(self.store, config)

    def ensure_ready(self) -> None:
        row = self.store.query_one("SELECT COUNT(*) AS count FROM items")
        if row and int(row["count"]) > 0:
            return
        from .import_manager import run_import

        run_import(full=False, offline=True, config=self.config)

    def search_items(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        return self.items.search_legacy(query, limit)

    def get_item(self, item_id: int) -> dict[str, Any] | None:
        row = self.items.get_by_ankama_id(int(item_id)) or self.items.get_by_id(int(item_id))
        if not row:
            return None
        return self._legacy_item_from_row(row)

    def get_item_by_name(self, name: str) -> dict[str, Any] | None:
        results = self.search_items(name, limit=1)
        return results[0] if results else None

    def get_item_image(self, item_id: int) -> str:
        return self.get_cached_image_path(item_id)

    def get_cached_image_path(self, item_id: int) -> str:
        rel = self.images.get_image_for_item(int(item_id))
        if not rel:
            return ""
        path = Path(rel)
        if not path.is_absolute():
            path = self.config.root_dir / path
        return str(path) if path.exists() else ""

    def get_recipe(self, item_id: int) -> dict[str, Any]:
        return self._legacy_recipe(int(item_id))

    def get_recipe_for_item(self, item_id: int, force_refresh: bool = False) -> dict[str, Any]:
        return self.get_recipe(item_id)

    def get_resources_for_recipe(self, item_id: int) -> list[dict[str, Any]]:
        return self.get_recipe(item_id).get("ingredients", [])

    def list_items(self) -> list[dict[str, Any]]:
        return self.items.legacy_list(craftable_only=False, limit=50000)

    def list_resources(self) -> list[dict[str, Any]]:
        rows = self.resources.store.query_all("SELECT * FROM resources WHERE name_fr!='' ORDER BY level, name_fr")
        return [self._legacy_item_from_row(row) for row in rows]

    def list_jobs(self) -> list[dict[str, Any]]:
        rows = self.store.query_all("SELECT * FROM jobs WHERE name_fr!='' ORDER BY name_fr")
        jobs = []
        for row in rows:
            name = row.get("name_fr") or row.get("name_en") or ""
            normalized = name.casefold()
            if "mage" in normalized or "bestiologue" in normalized:
                continue
            jobs.append(self._legacy_item_from_row(row))
        return jobs

    def list_recipes(self) -> list[dict[str, Any]]:
        rows = self.store.query_all("SELECT * FROM recipes ORDER BY level, result_name_fr")
        return [self._legacy_recipe(int(row["result_ankama_id"])) for row in rows if row.get("result_ankama_id")]

    def list_craft_items(self) -> list[dict[str, Any]]:
        return decorate_craft_items(self.items.legacy_list(craftable_only=True))

    def build_craft_list(self, items_with_quantities: list[dict[str, Any]] | dict[int, int]) -> list[dict[str, Any]]:
        return self.recipes.build_shopping_list(items_with_quantities)

    def get_item_set_for_item(self, item_id: int) -> dict[str, Any] | None:
        item_set = self.item_sets.get_set_for_item(int(item_id))
        if not item_set:
            return None
        item_set["items"] = [self._legacy_item_from_row(item) for item in item_set.get("items", [])]
        return item_set

    def cache_api(self) -> dict[str, int]:
        from .import_manager import run_import

        report = run_import(full=False, offline=True, config=self.config)
        return {
            "items": report["summary"]["counts"].get("items", 0),
            "jobs": report["summary"]["counts"].get("jobs", 0),
            "craftable_items": len(self.list_craft_items()),
            "recipes": report["summary"]["counts"].get("recipes", 0),
        }

    def sync_local_data_cache(self) -> dict[str, Any]:
        from .import_manager import run_import

        report = run_import(full=False, offline=True, config=self.config)
        return {
            "updated_at": now_iso(),
            "duration_ms": 0,
            "api": {
                "items": report["summary"]["counts"].get("items", 0),
                "jobs": report["summary"]["counts"].get("jobs", 0),
                "craftable_items": len(self.list_craft_items()),
                "recipes": report["summary"]["counts"].get("recipes", 0),
            },
            "errors": report.get("errors", []),
            "source": "local_dofus_data",
            "sqlite": str(self.config.sqlite_path),
        }

    def close(self) -> None:
        self.store.close()

    def _legacy_recipe(self, item_id: int) -> dict[str, Any]:
        recipe = self.recipes.get_by_result_item(item_id)
        if not recipe:
            return {
                "result_id": int(item_id),
                "result_name": "",
                "ingredients": [],
                "source": "local_sqlite",
                "found": False,
            }
        ingredients = []
        for ingredient in self.recipes.get_ingredients_for_item(item_id):
            ingredients.append(
                {
                    "id": ingredient.get("ingredient_ankama_id"),
                    "name": ingredient.get("name_fr") or ingredient.get("name_en") or str(ingredient.get("ingredient_ankama_id") or ""),
                    "quantity": ingredient.get("quantity") or 1,
                    "image": self._local_image_marker(ingredient.get("image_path") or ""),
                    "image_path": ingredient.get("image_path") or "",
                    "type": ingredient.get("type") or "",
                    "level": ingredient.get("level") or "",
                }
            )
        return {
            "result_id": recipe.get("result_ankama_id"),
            "result_name": recipe.get("result_name_fr") or recipe.get("result_name_en") or str(item_id),
            "job_id": recipe.get("job_id"),
            "job_name": recipe.get("job_name") or "",
            "level": recipe.get("level"),
            "ingredients": ingredients,
            "source": "local_sqlite",
            "found": bool(ingredients),
        }

    def _legacy_item_from_row(self, row: dict[str, Any]) -> dict[str, Any]:
        image_path = row.get("image_path") or ""
        return {
            "id": row.get("id"),
            "id_dofus": row.get("ankama_id"),
            "ankama_id": row.get("ankama_id"),
            "gid": row.get("gid") or row.get("ankama_id"),
            "name": row.get("name_fr") or row.get("name_en") or "",
            "name_fr": row.get("name_fr") or "",
            "name_en": row.get("name_en") or "",
            "type": row.get("type") or "",
            "family": row.get("family") or row.get("category") or "",
            "category": row.get("category") or "",
            "level": row.get("level"),
            "image": self._local_image_marker(image_path),
            "image_path": image_path,
            "source": row.get("source") or "local_sqlite",
        }

    def _local_image_marker(self, image_path: str) -> str:
        if not image_path:
            return ""
        return f"local://items/{Path(image_path).name}"


_ADAPTER: LocalCompatibilityAdapter | None = None


def get_adapter() -> LocalCompatibilityAdapter:
    global _ADAPTER
    if _ADAPTER is None:
        _ADAPTER = LocalCompatibilityAdapter()
    return _ADAPTER


def search_items(query: str, limit: int = 50) -> list[dict[str, Any]]:
    return get_adapter().search_items(query, limit)


def get_item(item_id: int) -> dict[str, Any] | None:
    return get_adapter().get_item(item_id)


def get_item_by_name(name: str) -> dict[str, Any] | None:
    return get_adapter().get_item_by_name(name)


def get_item_image(item_id: int) -> str:
    return get_adapter().get_item_image(item_id)


def get_cached_image_path(item_id: int) -> str:
    return get_adapter().get_cached_image_path(item_id)


def get_recipe(item_id: int) -> dict[str, Any]:
    return get_adapter().get_recipe(item_id)


def get_recipe_for_item(item_id: int, force_refresh: bool = False) -> dict[str, Any]:
    return get_adapter().get_recipe_for_item(item_id, force_refresh=force_refresh)


def get_resources_for_recipe(item_id: int) -> list[dict[str, Any]]:
    return get_adapter().get_resources_for_recipe(item_id)


def list_items() -> list[dict[str, Any]]:
    return get_adapter().list_items()


def list_resources() -> list[dict[str, Any]]:
    return get_adapter().list_resources()


def list_jobs() -> list[dict[str, Any]]:
    return get_adapter().list_jobs()


def list_recipes() -> list[dict[str, Any]]:
    return get_adapter().list_recipes()


def list_craft_items() -> list[dict[str, Any]]:
    return get_adapter().list_craft_items()


def build_craft_list(items_with_quantities: list[dict[str, Any]] | dict[int, int]) -> list[dict[str, Any]]:
    return get_adapter().build_craft_list(items_with_quantities)


def get_item_set_for_item(item_id: int) -> dict[str, Any] | None:
    return get_adapter().get_item_set_for_item(item_id)
