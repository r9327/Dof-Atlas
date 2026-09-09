from __future__ import annotations

from typing import Any

import app.cartography.map_view_manifest as map_view_manifest
import app.cartography.world_db as world_db


class WorldService:
    def __init__(self, *, initialize: bool = True) -> None:
        if initialize:
            self.init()

    def init(self) -> None:
        world_db.init_db()

    def import_manifest(self) -> dict[str, Any]:
        return map_view_manifest.import_map_view_manifest()

    def import_seed(self) -> dict[str, Any]:
        return self.import_manifest()

    def get_map_views(self) -> list[dict[str, Any]]:
        return world_db.get_map_views()

    def get_child_views(self, parent_view_key: str | None) -> list[dict[str, Any]]:
        return world_db.get_child_views(parent_view_key)

    def get_map_view(self, view_key: str) -> dict[str, Any] | None:
        return world_db.get_map_view(view_key)

    def get_maps_for_view(self, view_key: str) -> list[dict[str, Any]]:
        return world_db.get_maps_for_view(view_key)

    def get_links_for_view(self, view_key: str) -> list[dict[str, Any]]:
        return world_db.get_links_for_view(view_key)

    def mark_verified(self, view_key: str, x: int, y: int) -> dict[str, Any]:
        return world_db.mark_map_verified(view_key, x, y)

    def mark_unverified(self, view_key: str, x: int, y: int) -> dict[str, Any]:
        return world_db.mark_map_unverified(view_key, x, y)

    def set_current(self, view_key: str, x: int, y: int) -> dict[str, Any]:
        return world_db.set_current_map(view_key, x, y)
