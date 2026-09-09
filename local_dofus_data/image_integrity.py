from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig, ensure_directories
from .data_store import DataStore
from .utils import now_iso, save_json_atomic

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional runtime dependency
    Image = None


IMAGE_TABLES = ("items", "resources", "equipment", "consumables", "jobs", "spells", "classes", "monsters")


def build_image_integrity_report(
    store: DataStore | None = None,
    config: LocalDataConfig = DEFAULT_CONFIG,
    verify_readable: bool = True,
) -> dict[str, Any]:
    ensure_directories(config)
    store = store or DataStore(config=config)
    store.initialize()
    references: list[dict[str, Any]] = []
    counts: dict[str, dict[str, int]] = {}
    for table in IMAGE_TABLES:
        total = store.query_one(f"SELECT COUNT(*) AS count FROM {table}")["count"]
        rows = store.query_all(f"SELECT ankama_id, name_fr, image_path FROM {table} WHERE COALESCE(image_path, '')!=''")
        counts[table] = {"total": int(total), "with_image": len(rows)}
        for row in rows:
            references.append({"table": table, **row})

    missing = []
    unreadable = []
    path_counter = Counter(str(row.get("image_path") or "").replace("\\", "/") for row in references)
    path_tables: dict[str, Counter[str]] = {}
    for row in references:
        rel_path = str(row.get("image_path") or "").replace("\\", "/")
        path_tables.setdefault(rel_path, Counter())[str(row.get("table") or "unknown")] += 1
    for rel_path in sorted(path_counter):
        path = config.root_dir / rel_path
        if not path.exists():
            missing.append({"path": rel_path, "references": path_counter[rel_path], "tables": dict(path_tables.get(rel_path, {}))})
            continue
        if verify_readable and Image is not None:
            try:
                with Image.open(path) as img:
                    img.verify()
            except Exception:
                unreadable.append({"path": rel_path, "references": path_counter[rel_path], "tables": dict(path_tables.get(rel_path, {}))})

    report = {
        "generated_at": now_iso(),
        "tables": counts,
        "unique_image_paths": len(path_counter),
        "references": len(references),
        "missing_count": len(missing),
        "unreadable_count": len(unreadable),
        "missing_by_table": _count_issue_tables(missing),
        "unreadable_by_table": _count_issue_tables(unreadable),
        "shared_path_count": len([path for path, count in path_counter.items() if count > 1]),
        "missing_samples": missing[:200],
        "unreadable_samples": unreadable[:200],
    }
    save_json_atomic(config.reports_dir / "image_integrity_report.json", report)
    return report


def _count_issue_tables(issues: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for issue in issues:
        for table, count in (issue.get("tables") or {}).items():
            counts[table] += int(count)
    return dict(sorted(counts.items()))


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Check local Dofus image references")
    parser.add_argument("--fast", action="store_true", help="skip image decoding and only check paths")
    args = parser.parse_args(argv)
    report = build_image_integrity_report(verify_readable=not args.fast)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    main()
