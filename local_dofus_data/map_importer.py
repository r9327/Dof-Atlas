from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig
from .normalizer import empty_bundle, normalize_map
from .utils import load_json_safe


class MapImporter:
    def __init__(self, config: LocalDataConfig = DEFAULT_CONFIG):
        self.config = config

    def import_directory(self, directory: str | Path | None = None) -> dict[str, Any]:
        directory = Path(directory) if directory else self.config.raw_maps_dir
        bundle = empty_bundle("maps_export")
        if not directory.exists():
            return bundle
        for path in sorted(directory.rglob("*.json")):
            warnings: list[str] = []
            payload = load_json_safe(path, default=None, warnings=warnings)
            bundle["warnings"].extend(warnings)
            bundle["sources"].append({"type": "maps_export", "name": path.stem, "path": str(path), "status": "ok" if payload is not None else "warning"})
            records = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
            for raw in records:
                if not isinstance(raw, dict):
                    bundle["raw_objects"].append(("maps_export", path.stem, "", str(path), raw))
                    continue
                map_row, cells, interactives = normalize_map(raw, source="maps_export")
                if map_row:
                    bundle["maps"].append(map_row)
                    bundle["cells"].extend(cells)
                    bundle["interactive_elements"].extend(interactives)
                else:
                    bundle["raw_objects"].append(("maps_export", path.stem, "", str(path), raw))
        return bundle
