from __future__ import annotations

from pathlib import Path

from local_dofus_data.config import LocalDataConfig


def make_config(root: Path) -> LocalDataConfig:
    data = root / "data"
    return LocalDataConfig(
        root_dir=root,
        data_dir=data,
        raw_dir=data / "raw",
        raw_d2data_dir=data / "raw" / "d2data",
        raw_d2o_dir=data / "raw" / "d2o",
        raw_d2i_dir=data / "raw" / "d2i",
        raw_maps_dir=data / "raw" / "maps",
        raw_json_dir=data / "raw" / "json",
        raw_legacy_dir=data / "raw" / "legacy",
        images_dir=data / "images",
        image_items_dir=data / "images" / "items",
        image_resources_dir=data / "images" / "resources",
        image_misc_dir=data / "images" / "misc",
        local_dir=data / "local",
        exports_dir=data / "exports",
        reports_dir=data / "reports",
        sqlite_path=data / "local" / "dofus_data.sqlite",
        legacy_cache_dir=data / "raw" / "legacy",
        legacy_cache_api_dir=data / "raw" / "legacy" / "api",
        legacy_cache_recipes_dir=data / "raw" / "legacy" / "recipes",
        legacy_cache_images_dir=data / "raw" / "legacy" / "images",
        legacy_cache_item_images_dir=data / "raw" / "legacy" / "images" / "items",
    )
