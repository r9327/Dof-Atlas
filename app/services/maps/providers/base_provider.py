from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.services.maps.map_manifest import MapEntry


class BaseMapProvider(ABC):
    name = "base"

    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_maps(self) -> list[MapEntry]:
        raise NotImplementedError

    def fetch_map_image(self, map_entry: MapEntry) -> Path | None:
        return None

    def build_manifest(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "maps": [entry.to_dict() for entry in self.list_maps()],
        }

