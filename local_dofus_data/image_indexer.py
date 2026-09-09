from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig
from .data_store import DataStore
from .utils import copy_if_missing, now_iso, relative_path_safe, safe_int


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class ImageIndexer:
    def __init__(self, store: DataStore, config: LocalDataConfig = DEFAULT_CONFIG):
        self.store = store
        self.config = config

    def index(self) -> dict[str, Any]:
        copied = self._copy_legacy_images()
        indexed = 0
        linked = 0
        search_dirs = [
            self.config.image_items_dir,
            self.config.image_resources_dir,
            self.config.image_misc_dir,
            self.config.legacy_cache_item_images_dir,
        ]
        seen: set[str] = set()
        for directory in search_dirs:
            if not directory or not Path(directory).exists():
                continue
            for path in sorted(Path(directory).rglob("*")):
                if not path.is_file() or path.suffix.casefold() not in IMAGE_EXTENSIONS:
                    continue
                rel = relative_path_safe(path, self.config.root_dir)
                if rel in seen:
                    continue
                seen.add(rel)
                asset_id = safe_int(path.stem)
                normalized_rel = rel.replace("\\", "/")
                if "/resources/" in f"/{normalized_rel}":
                    kind = "resource"
                elif "/misc/" in f"/{normalized_rel}":
                    kind = "misc"
                else:
                    kind = "item"
                self.store.upsert_entity(
                    "image_assets",
                    {
                        "ankama_id": asset_id,
                        "item_ankama_id": asset_id,
                        "name": path.name,
                        "path": rel,
                        "kind": kind,
                        "source": "local_images",
                        "metadata_json": {"indexed_at": now_iso(), "absolute_path": str(path)},
                    },
                    conflict_column="path",
                )
                indexed += 1
                linked += self._link_asset(path.name, rel, asset_id)
        return {"copied": copied, "indexed": indexed, "linked": linked}

    def _copy_legacy_images(self) -> int:
        count = 0
        source_dir = self.config.legacy_cache_item_images_dir
        if not source_dir.exists():
            return count
        for path in source_dir.glob("*"):
            if path.is_file() and path.suffix.casefold() in IMAGE_EXTENSIONS:
                if copy_if_missing(path, self.config.image_items_dir / path.name):
                    count += 1
        return count

    def _link_asset(self, file_name: str, rel_path: str, asset_id: int | None) -> int:
        return 0
