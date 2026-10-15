from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
ROOT_DIR = PACKAGE_DIR.parent
DATA_DIR = ROOT_DIR / "data"
# Runtime user data must survive version swaps. Static images stay bundled.
_USER_ROOT = os.environ.get("DOFUS_ATLAS_USER_ROOT", "")
USER_DATA_DIR = Path(_USER_ROOT) / "data" if _USER_ROOT else DATA_DIR



@dataclass(frozen=True)
class LocalDataConfig:
    root_dir: Path = ROOT_DIR
    data_dir: Path = DATA_DIR
    raw_dir: Path = DATA_DIR / "raw"
    raw_d2data_dir: Path = DATA_DIR / "raw" / "d2data"
    raw_d2o_dir: Path = DATA_DIR / "raw" / "d2o"
    raw_d2i_dir: Path = DATA_DIR / "raw" / "d2i"
    raw_maps_dir: Path = DATA_DIR / "raw" / "maps"
    raw_json_dir: Path = DATA_DIR / "raw" / "json"
    raw_legacy_dir: Path = DATA_DIR / "raw" / "legacy"
    images_dir: Path = DATA_DIR / "images"
    image_items_dir: Path = DATA_DIR / "images" / "items"
    image_resources_dir: Path = DATA_DIR / "images" / "resources"
    image_misc_dir: Path = DATA_DIR / "images" / "misc"
    local_dir: Path = USER_DATA_DIR / "local"
    exports_dir: Path = USER_DATA_DIR / "exports"
    reports_dir: Path = USER_DATA_DIR / "reports"
    sqlite_path: Path = USER_DATA_DIR / "local" / "dofus_data.sqlite"
    legacy_cache_dir: Path = DATA_DIR / "raw" / "legacy"
    legacy_cache_api_dir: Path = DATA_DIR / "raw" / "legacy" / "api"
    legacy_cache_recipes_dir: Path = DATA_DIR / "raw" / "legacy" / "recipes"
    legacy_cache_images_dir: Path = DATA_DIR / "raw" / "legacy" / "images"
    legacy_cache_item_images_dir: Path = DATA_DIR / "raw" / "legacy" / "images" / "items"
    debug: bool = False


DEFAULT_CONFIG = LocalDataConfig()


def ensure_directories(config: LocalDataConfig = DEFAULT_CONFIG) -> None:
    # An installed bundle is immutable; only touch user-owned directories.
    if _USER_ROOT:
        for folder in (config.local_dir, config.exports_dir, config.reports_dir):
            folder.mkdir(parents=True, exist_ok=True)
        return
    for folder in (
        config.data_dir,
        config.raw_dir,
        config.raw_d2data_dir,
        config.raw_d2o_dir,
        config.raw_d2i_dir,
        config.raw_maps_dir,
        config.raw_json_dir,
        config.raw_legacy_dir,
        config.images_dir,
        config.image_items_dir,
        config.image_resources_dir,
        config.image_misc_dir,
        config.local_dir,
        config.exports_dir,
        config.reports_dir,
        config.legacy_cache_dir,
        config.legacy_cache_api_dir,
        config.legacy_cache_recipes_dir,
        config.legacy_cache_item_images_dir,
    ):
        folder.mkdir(parents=True, exist_ok=True)
