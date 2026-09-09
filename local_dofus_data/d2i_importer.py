from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig
from .normalizer import empty_bundle, normalize_text_entry
from .utils import load_json_safe


class D2IImporter:
    def __init__(self, config: LocalDataConfig = DEFAULT_CONFIG):
        self.config = config

    def import_directory(self, directory: str | Path | None = None) -> dict[str, Any]:
        directory = Path(directory) if directory else self.config.raw_d2i_dir
        bundle = empty_bundle("d2i_export")
        if not directory.exists():
            return bundle
        for path in sorted(directory.rglob("*.json")):
            warnings: list[str] = []
            payload = load_json_safe(path, default=None, warnings=warnings)
            bundle["warnings"].extend(warnings)
            bundle["sources"].append({"type": "d2i_export", "name": path.stem, "path": str(path), "status": "ok" if payload is not None else "warning"})
            if isinstance(payload, dict):
                records = payload.get("texts") if isinstance(payload.get("texts"), dict) else payload
                if isinstance(records, dict):
                    for key, value in records.items():
                        bundle["texts"].extend(normalize_text_entry(key, value, source="d2i_export"))
                    continue
            bundle["raw_objects"].append(("d2i_export", path.stem, "", str(path), payload))
        return bundle
