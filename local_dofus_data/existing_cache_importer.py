from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig
from .normalizer import (
    _add_typed_item,
    empty_bundle,
    normalize_legacy_item,
    normalize_legacy_job,
    normalize_legacy_recipe,
    normalize_recipe_index_entry,
)
from .utils import load_json_safe, repair_mojibake


class ExistingCacheImporter:
    def __init__(self, config: LocalDataConfig = DEFAULT_CONFIG):
        self.config = config

    def import_cache(self) -> dict[str, Any]:
        bundle = empty_bundle("legacy_cache")
        api_dir = self.config.legacy_cache_api_dir
        recipes_dir = self.config.legacy_cache_recipes_dir
        bundle["sources"].append({"type": "legacy_cache", "name": "Local legacy cache", "path": str(self.config.legacy_cache_dir), "status": "ok"})
        bundle["sources"].append({"type": "legacy_recipe_index", "name": "Legacy recipe index", "path": str(api_dir / "recipe_index.json"), "status": "ok"})

        warnings: list[str] = []
        items = load_json_safe(api_dir / "items.json", default=[], warnings=warnings)
        if isinstance(items, list):
            for raw in items:
                if not isinstance(raw, dict):
                    continue
                row = normalize_legacy_item(raw)
                bundle["items"].append({key: value for key, value in row.items() if key != "normalized_category"})
                _add_typed_item(bundle, row)
        else:
            bundle["warnings"].append("legacy items.json absent ou invalide")

        jobs = load_json_safe(api_dir / "jobs.json", default=[], warnings=warnings)
        if isinstance(jobs, list):
            for raw in jobs:
                if isinstance(raw, dict):
                    bundle["jobs"].append(normalize_legacy_job(raw))

        recipe_index = load_json_safe(api_dir / "recipe_index.json", default={}, warnings=warnings)
        if isinstance(recipe_index, dict):
            for raw in recipe_index.get("recipes") or []:
                if isinstance(raw, dict):
                    bundle["recipes"].append((normalize_recipe_index_entry(raw), []))
            bundle["raw_objects"].append(("legacy_cache", "recipe_index", "", str(api_dir / "recipe_index.json"), recipe_index))

        if recipes_dir.exists():
            for path in sorted(recipes_dir.glob("*.json")):
                payload = load_json_safe(path, default=None, warnings=warnings)
                if isinstance(payload, dict):
                    if payload.get("found") is False and not payload.get("ingredients"):
                        bundle["raw_objects"].append(("legacy_cache", "recipe_unavailable", path.stem, str(path), payload))
                        continue
                    recipe, ingredients = normalize_legacy_recipe(payload)
                    bundle["recipes"].append((recipe, ingredients))
                    for ingredient in ingredients:
                        resource = {
                            "ankama_id": ingredient.get("ingredient_ankama_id"),
                            "gid": ingredient.get("ingredient_ankama_id"),
                            "name_fr": ingredient.get("name_fr", ""),
                            "name_en": ingredient.get("name_en", ""),
                            "category": "resource",
                            "type": ingredient.get("type", ""),
                            "job_id": None,
                            "job_name": "",
                            "level": ingredient.get("level"),
                            "source": "legacy_cache",
                            "image_path": ingredient.get("image_path", ""),
                            "metadata_json": {"from_recipe": recipe.get("result_ankama_id"), "ingredient": ingredient},
                        }
                        bundle["resources"].append(resource)
                        bundle["items"].append(
                            {
                                "ankama_id": resource["ankama_id"],
                                "gid": resource["gid"],
                                "name_fr": resource["name_fr"],
                                "name_en": resource["name_en"],
                                "category": "resource",
                                "type": resource["type"],
                                "family": "resource",
                                "level": resource["level"],
                                "source": "legacy_cache",
                                "image_path": resource["image_path"],
                                "metadata_json": resource["metadata_json"],
                            }
                        )
                else:
                    bundle["raw_objects"].append(("legacy_cache", "recipe", path.stem, str(path), payload))

        craft_index = load_json_safe(api_dir / "craft_item_index.json", default=[], warnings=warnings)
        if isinstance(craft_index, list):
            bundle["raw_objects"].append(("legacy_cache", "craft_item_index", "", str(api_dir / "craft_item_index.json"), craft_index))

        bundle["warnings"].extend(warnings)
        return bundle
