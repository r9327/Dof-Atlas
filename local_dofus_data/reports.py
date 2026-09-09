from __future__ import annotations

import argparse
import json
from typing import Any

from .config import DEFAULT_CONFIG, LocalDataConfig, ensure_directories
from .data_store import DataStore
from .image_integrity import build_image_integrity_report
from .utils import save_json_atomic
from .validators import Validator


TABLES = [
    "sources",
    "items",
    "resources",
    "equipment",
    "item_sets",
    "consumables",
    "recipes",
    "recipe_ingredients",
    "jobs",
    "spells",
    "classes",
    "monsters",
    "monster_families",
    "maps",
    "cells",
    "areas",
    "subareas",
    "interactive_elements",
    "texts",
    "image_assets",
    "effects",
    "item_effects",
    "monster_spells",
    "class_spells",
    "conditions",
    "raw_objects",
]


def build_summary(store: DataStore | None = None, config: LocalDataConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    ensure_directories(config)
    store = store or DataStore(config=config)
    store.initialize()
    counts = {}
    for table in TABLES:
        row = store.query_one(f"SELECT COUNT(*) AS count FROM {table}")
        counts[table] = row["count"] if row else 0
    validation = Validator(store).run_all()
    summary = {
        "sqlite_path": str(config.sqlite_path),
        "integrity_check": store.integrity_check(),
        "counts": counts,
        "validation_warning_count": validation["warning_count"],
        "source_coverage": build_source_coverage(config),
        "image_integrity": build_image_integrity_report(store, config, verify_readable=False),
        "route_coverage": build_route_coverage(config, counts),
    }
    save_json_atomic(config.reports_dir / "validation_report.json", validation)
    save_json_atomic(config.reports_dir / "source_coverage_report.json", summary["source_coverage"])
    return summary


def build_route_coverage(config: LocalDataConfig = DEFAULT_CONFIG, counts: dict[str, int] | None = None) -> dict[str, Any]:
    route_root = config.data_dir / "routes"
    screenshots = [path for path in route_root.rglob("*") if path.is_file() and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"}] if route_root.exists() else []
    by_job: dict[str, int] = {}
    for path in screenshots:
        try:
            job = path.relative_to(route_root).parts[0]
        except Exception:
            job = "unknown"
        by_job[job] = by_job.get(job, 0) + 1
    counts = counts or {}
    coverage = {
        "path": str(route_root),
        "screenshot_count": len(screenshots),
        "screenshots_by_job": dict(sorted(by_job.items())),
        "maps_in_sqlite": counts.get("maps", 0),
        "cells_in_sqlite": counts.get("cells", 0),
        "interactive_elements_in_sqlite": counts.get("interactive_elements", 0),
        "status": "partial" if counts.get("maps", 0) == 0 or counts.get("cells", 0) == 0 else "ok",
        "next_source_needed": "D2Data/doduda/dodumap maps export for full farm-route reconstruction",
    }
    save_json_atomic(config.reports_dir / "route_coverage_report.json", coverage)
    return coverage


def build_source_coverage(config: LocalDataConfig = DEFAULT_CONFIG) -> dict[str, Any]:
    raw_dirs = {
        "d2data": config.raw_d2data_dir,
        "d2o": config.raw_d2o_dir,
        "d2i": config.raw_d2i_dir,
        "maps": config.raw_maps_dir,
        "json": config.raw_json_dir,
        "legacy": config.legacy_cache_dir,
        "images_items": config.image_items_dir,
        "images_resources": config.image_resources_dir,
        "images_misc": config.image_misc_dir,
    }
    coverage: dict[str, Any] = {"directories": {}, "missing_core_sources": []}
    for name, directory in raw_dirs.items():
        files = [path for path in directory.rglob("*") if path.is_file()] if directory.exists() else []
        coverage["directories"][name] = {
            "path": str(directory),
            "exists": directory.exists(),
            "file_count": len(files),
            "json_count": len([path for path in files if path.suffix.casefold() == ".json"]),
            "png_count": len([path for path in files if path.suffix.casefold() == ".png"]),
        }
    for name in ("d2data", "d2o", "d2i", "maps"):
        if coverage["directories"][name]["file_count"] == 0:
            coverage["missing_core_sources"].append(name)
    coverage["next_expected_files"] = {
        "d2data": ["Items.json", "Recipes.json", "Spells.json", "Monsters.json", "Areas.json", "SubAreas.json"],
        "d2i": ["texts.json"],
        "maps": ["*.json avec mapId/cells/walkable/Los/neighbours"],
        "doduda": ["placer les sorties JSON dans data/raw/json ou data/raw/maps"],
    }
    return coverage


def write_import_report(report: dict[str, Any], config: LocalDataConfig = DEFAULT_CONFIG) -> None:
    ensure_directories(config)
    save_json_atomic(config.reports_dir / "last_import_report.json", report)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Show local Dofus data summary")
    parser.add_argument("--summary", action="store_true", help="print a summary")
    args = parser.parse_args(argv)
    summary = build_summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


if __name__ == "__main__":
    main()
