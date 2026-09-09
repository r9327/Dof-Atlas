from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig
from .normalizer import bundle_from_records, empty_bundle
from .utils import load_json_safe


class JsonImporter:
    def __init__(self, config: LocalDataConfig = DEFAULT_CONFIG):
        self.config = config

    def import_path(self, path: str | Path, source: str = "json_local") -> dict[str, Any]:
        path = Path(path)
        warnings: list[str] = []
        payload = load_json_safe(path, default=None, warnings=warnings)
        bundle = empty_bundle(source)
        bundle["warnings"].extend(warnings)
        bundle["sources"].append({"type": source, "name": path.stem, "path": str(path), "status": "ok" if payload is not None else "warning"})
        if payload is None:
            return bundle
        records = self._records(payload)
        if records is None:
            bundle["raw_objects"].append((source, path.stem, "", str(path), payload))
            return bundle
        parsed = bundle_from_records(records, path, source)
        for key, value in parsed.items():
            if isinstance(bundle.get(key), list) and isinstance(value, list):
                bundle[key].extend(value)
        return bundle

    def import_directory(self, directory: str | Path | None = None, source: str = "json_local") -> dict[str, Any]:
        directory = Path(directory) if directory else self.config.raw_json_dir
        bundle = empty_bundle(source)
        if not directory.exists():
            return bundle
        for path in sorted(directory.rglob("*.json")):
            if self._should_skip_path(path):
                continue
            sub = self.import_path(path, source=source)
            for key, value in sub.items():
                if isinstance(bundle.get(key), list) and isinstance(value, list):
                    bundle[key].extend(value)
        return bundle

    @staticmethod
    def _records(payload: Any) -> list[Any] | None:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "items", "objects", "results", "recipes", "maps"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
            if all(isinstance(value, dict) for value in payload.values()):
                records = []
                for key, value in payload.items():
                    record = dict(value)
                    record.setdefault("id", key)
                    records.append(record)
                return records
        return None

    @staticmethod
    def _should_skip_path(path: Path) -> bool:
        if path.name.startswith("dofusdb_") and "_page_" in path.name:
            combined_name = path.name.split("_page_", 1)[0] + ".json"
            return (path.parent / combined_name).exists()
        if path.name.startswith("dofusdb_recipes_page_") and (path.parent / "dofusdb_recipes.json").exists():
            return True
        return False
