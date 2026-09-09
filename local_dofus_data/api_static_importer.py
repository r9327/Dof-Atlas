from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from .config import DEFAULT_CONFIG, LocalDataConfig
from .json_importer import JsonImporter
from .normalizer import empty_bundle
from .utils import now_iso, save_json_atomic


DOFUSDB_BASE_URL = "https://api.dofusdb.fr"
DOFUSDB_RECIPES_URL = f"{DOFUSDB_BASE_URL}/recipes"


class ApiStaticImporter:
    """Controlled importer for public static APIs.

    This importer is never used by runtime adapters. It writes raw JSON locally,
    then returns normalized records for SQLite import.
    """

    def __init__(self, config: LocalDataConfig = DEFAULT_CONFIG):
        self.config = config
        self.json_importer = JsonImporter(config)

    def fetch_dofusdb_recipes(self, limit: int = 500, max_pages: int | None = None) -> dict[str, Any]:
        return self.fetch_collection("recipes", DOFUSDB_RECIPES_URL, limit=limit, max_pages=max_pages)

    def fetch_static_data(self, scope: str = "recipes", limit: int = 500, max_pages: int | None = None) -> dict[str, Any]:
        bundles: list[dict[str, Any]] = []
        if scope in {"recipes", "all"}:
            bundles.append(self.fetch_dofusdb_recipes(limit=limit, max_pages=max_pages))
        if scope in {"items", "all"}:
            for collection in ("items", "item-sets"):
                bundles.append(self.fetch_collection(collection, f"{DOFUSDB_BASE_URL}/{collection}", limit=limit, max_pages=max_pages))
        if scope in {"bestiary", "all"}:
            for collection in ("monsters", "monster-races", "monster-super-races", "spells", "breeds", "areas", "subareas"):
                bundles.append(self.fetch_collection(collection, f"{DOFUSDB_BASE_URL}/{collection}", limit=limit, max_pages=max_pages))
        merged = empty_bundle("api_static_import")
        for bundle in bundles:
            for key, value in bundle.items():
                if isinstance(merged.get(key), list) and isinstance(value, list):
                    merged[key].extend(value)
        return merged

    def fetch_collection(self, collection: str, url_base: str, limit: int = 500, max_pages: int | None = None) -> dict[str, Any]:
        raw_dir = self.config.raw_json_dir / "api_static"
        raw_dir.mkdir(parents=True, exist_ok=True)
        all_records: list[dict[str, Any]] = []
        warnings: list[str] = []
        errors: list[str] = []
        skip = 0
        total: int | None = None
        page_index = 0

        while total is None or skip < total:
            if max_pages is not None and page_index >= max_pages:
                break
            query = urlencode({"$limit": limit, "$skip": skip})
            url = f"{url_base}?{query}"
            try:
                payload = self._fetch_json(url)
            except Exception as exc:
                errors.append(f"DofusDB {collection} page skip={skip}: {exc}")
                break

            page_data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(page_data, list):
                warnings.append(f"DofusDB {collection} page skip={skip}: format inattendu")
                break

            save_json_atomic(raw_dir / f"dofusdb_{collection}_page_{page_index:03d}.json", payload)
            all_records.extend([row for row in page_data if isinstance(row, dict)])
            total = int(payload.get("total", len(all_records))) if isinstance(payload, dict) else len(all_records)
            if not page_data:
                break
            skip += len(page_data)
            page_index += 1

        combined = {
            "source": url_base,
            "fetched_at": now_iso(),
            "total": total if total is not None else len(all_records),
            "count": len(all_records),
            "data": all_records,
        }
        combined_path = raw_dir / f"dofusdb_{collection}.json"
        save_json_atomic(combined_path, combined)

        bundle = self.json_importer.import_path(combined_path, source="api_static_import")
        bundle["warnings"].extend(warnings)
        bundle["errors"].extend(errors)
        bundle["sources"].append(
            {
                "type": "api_static_import",
                "name": f"DofusDB {collection}",
                "path": str(combined_path),
                "status": "ok" if not errors else "warning",
                "metadata_json": {"url": url_base, "fetched_at": combined["fetched_at"], "count": len(all_records)},
            }
        )
        return bundle

    @staticmethod
    def _fetch_json(url: str, timeout: int = 45) -> Any:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "SessionHub-LocalDofusDataImport/1.0",
            },
        )
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8-sig"))
