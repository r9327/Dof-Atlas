from __future__ import annotations

from pathlib import Path
from typing import Any

from .data_store import DataStore
from .utils import now_iso


class SourceRegistry:
    def __init__(self, store: DataStore):
        self.store = store

    def register(self, source_type: str, path: str | Path = "", name: str | None = None, status: str = "ok", version: str = "", metadata: dict[str, Any] | None = None) -> int:
        return self.store.upsert_source(
            {
                "name": name or source_type,
                "type": source_type,
                "path": str(path or ""),
                "version": version,
                "status": status,
                "metadata_json": {"registered_at": now_iso(), **(metadata or {})},
            }
        )
