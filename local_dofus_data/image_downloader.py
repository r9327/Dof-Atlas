from __future__ import annotations

import argparse
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .config import DEFAULT_CONFIG, LocalDataConfig, ensure_directories
from .data_store import DataStore
from .image_indexer import ImageIndexer
from .utils import image_basename_from_url, now_iso, safe_int, save_json_atomic

JOB_ICON_IDS = {
    2: 1,
    24: 13,
    26: 14,
    28: 18,
    36: 30,
}


class ImageDownloader:
    def __init__(self, config: LocalDataConfig = DEFAULT_CONFIG, store: DataStore | None = None):
        self.config = config
        self.store = store or DataStore(config=config)
        self.store.initialize()

    def download_missing(self, scope: str = "craft", workers: int = 12, limit: int | None = None) -> dict[str, Any]:
        ensure_directories(self.config)
        started_at = now_iso()
        tasks = self.collect_missing(scope=scope)
        if limit is not None:
            tasks = tasks[: max(0, limit)]
        downloaded = 0
        skipped = 0
        failed: list[dict[str, str]] = []

        with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
            futures = {executor.submit(self._download_one, task): task for task in tasks}
            for future in as_completed(futures):
                task = futures[future]
                try:
                    status = future.result()
                except Exception as exc:
                    failed.append({"url": task["url"], "path": task["path"], "error": str(exc)})
                    continue
                if status == "downloaded":
                    downloaded += 1
                else:
                    skipped += 1

        indexed = ImageIndexer(self.store, self.config).index()
        report = {
            "scope": scope,
            "started_at": started_at,
            "finished_at": now_iso(),
            "planned": len(tasks),
            "downloaded": downloaded,
            "skipped": skipped,
            "failed_count": len(failed),
            "failed": failed[:200],
            "image_index": indexed,
        }
        save_json_atomic(self.config.reports_dir / "image_download_report.json", report)
        return report

    def collect_missing(self, scope: str = "craft") -> list[dict[str, str]]:
        rows = self._scope_rows(scope)
        tasks: dict[str, dict[str, str]] = {}
        for row in rows:
            image_path = row.get("image_path") or ""
            url = self._image_url_from_row(row)
            if not url:
                continue
            if not image_path:
                file_name = image_basename_from_url(url)
                if row.get("table_name") == "jobs":
                    image_path = f"data/images/misc/jobs/{file_name}" if file_name else ""
                else:
                    image_path = f"data/images/items/{file_name}" if file_name else ""
                self._persist_inferred_path(row, image_path)
            if not image_path:
                continue
            destination = Path(image_path)
            if not destination.is_absolute():
                destination = self.config.root_dir / destination
            if destination.exists():
                continue
            tasks[str(destination)] = {"url": url, "path": str(destination)}
        return list(tasks.values())

    def _scope_rows(self, scope: str) -> list[dict[str, Any]]:
        if scope == "craft":
            return self.store.query_all(
                """
                SELECT 'items' AS table_name, i.id AS row_id, i.image_path, i.metadata_json
                FROM items i
                JOIN recipes r ON r.result_ankama_id=i.ankama_id
                UNION
                SELECT 'recipe_ingredients' AS table_name, ri.id AS row_id, ri.image_path, ri.metadata_json
                FROM recipe_ingredients ri
                """
            )
        if scope == "all-items":
            return self.store.query_all("SELECT 'items' AS table_name, id AS row_id, image_path, metadata_json FROM items")
        if scope == "resources":
            return self.store.query_all("SELECT 'resources' AS table_name, id AS row_id, ankama_id, image_path, metadata_json FROM resources")
        if scope == "jobs":
            return self.store.query_all("SELECT 'jobs' AS table_name, id AS row_id, ankama_id, image_path, metadata_json FROM jobs")
        raise ValueError(f"scope image inconnu: {scope}")

    def _persist_inferred_path(self, row: dict[str, Any], image_path: str) -> None:
        table = row.get("table_name")
        row_id = safe_int(row.get("row_id"))
        if table not in {"items", "resources", "recipe_ingredients", "jobs"} or row_id is None or not image_path:
            return
        with self.store.transaction() as conn:
            conn.execute(f"UPDATE {table} SET image_path=? WHERE id=? AND image_path=''", (image_path, row_id))

    def _image_url_from_row(self, row: dict[str, Any]) -> str:
        metadata = self._loads(row.get("metadata_json"))
        url = metadata.get("image_url")
        raw = metadata.get("raw") or metadata.get("legacy") or metadata.get("ingredient") or {}
        if not url and isinstance(raw, dict):
            url = raw.get("img") or raw.get("image")
        if row.get("table_name") == "jobs":
            if not url and safe_int(row.get("ankama_id")) in JOB_ICON_IDS:
                url = f"https://api.dofusdb.fr/img/jobs/{JOB_ICON_IDS[safe_int(row.get('ankama_id'))]}.png"
            return re.sub(r"\.(?:jpg|jpeg|webp)(?:[?#].*)?$", ".png", str(url or ""), flags=re.IGNORECASE)
        if not url and isinstance(raw, dict):
            if not url and safe_int(raw.get("iconId")) is not None:
                url = f"https://api.dofusdb.fr/img/items/{safe_int(raw.get('iconId'))}.png"
        if url:
            name = image_basename_from_url(url)
            if name:
                return f"https://api.dofusdb.fr/img/items/{name}"
        if not url and row.get("image_path"):
            name = Path(row["image_path"]).name
            if name.casefold().endswith(".png"):
                url = f"https://api.dofusdb.fr/img/items/{name}"
        return str(url or "")

    @staticmethod
    def _download_one(task: dict[str, str]) -> str:
        destination = Path(task["path"])
        if destination.exists():
            return "skipped"
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = Request(
            task["url"],
            headers={
                "Accept": "image/png,image/*,*/*",
                "User-Agent": "SessionHub-LocalImageImport/1.0",
            },
        )
        with urlopen(request, timeout=30) as response:
            data = response.read()
        if not data.startswith((b"\x89PNG", b"\xff\xd8", b"RIFF")):
            raise ValueError("reponse image invalide")
        tmp = destination.with_suffix(destination.suffix + ".tmp")
        with tmp.open("wb") as handle:
            handle.write(data)
        os.replace(tmp, destination)
        return "downloaded"

    @staticmethod
    def _loads(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return {}
        return value or {}


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Download missing local Dofus images for imported data")
    parser.add_argument("--scope", choices=("craft", "all-items", "resources", "jobs"), default="craft")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    report = ImageDownloader().download_missing(scope=args.scope, workers=args.workers, limit=args.limit)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()
