from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig
from .json_importer import JsonImporter
from .normalizer import empty_bundle


class D2DataImporter:
    """Importer for JSON files produced by AnkaBot D2Data exports."""

    def __init__(self, config: LocalDataConfig = DEFAULT_CONFIG):
        self.config = config
        self.json_importer = JsonImporter(config)

    def import_directory(self, directory: str | Path | None = None) -> dict[str, Any]:
        directory = Path(directory) if directory else self.config.raw_d2data_dir
        bundle = empty_bundle("d2data")
        if not directory.exists():
            return bundle
        for path in sorted(directory.rglob("*.json")):
            sub = self.json_importer.import_path(path, source="d2data")
            for key, value in sub.items():
                if isinstance(bundle.get(key), list) and isinstance(value, list):
                    bundle[key].extend(value)
        return bundle
