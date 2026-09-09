from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.encyclopedia.services.guide_ultime_manual_route import load_manual_chapter
from app.quest_catalog import normalize_text


BASE = ROOT / "data" / "routes" / "guide_ultime_manual"
MANIFEST = BASE / "manifest_v1.json"


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        result: list[str] = []
        for child in value:
            result.extend(_strings(child))
        return result
    return []


def audit() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    canonical = manifest.get("canonical") if isinstance(manifest.get("canonical"), dict) else {}
    chapters = [row for row in canonical.get("chapters", []) or [] if isinstance(row, dict)]
    chapters.sort(key=lambda row: int(row.get("order") or 0))

    quests: dict[str, str] = {}
    successes: dict[str, str] = {}
    chapter_stats: dict[str, dict[str, int]] = {}
    missing_files: list[str] = []
    bad_stage_counts: list[dict[str, Any]] = []
    field_usage: Counter[str] = Counter()

    for meta in chapters:
        chapter_id = str(meta.get("id") or "").strip()
        filename = str(meta.get("file") or "").strip()
        path = BASE / filename
        if not path.is_file():
            missing_files.append(filename)
            continue
        chapter = load_manual_chapter(path)
        stages = [stage for stage in chapter.get("stages", []) or [] if isinstance(stage, dict)]
        declared = meta.get("stage_count")
        if declared is not None and int(declared) != len(stages):
            bad_stage_counts.append({"chapter": chapter_id, "declared": int(declared), "actual": len(stages)})

        local_quests: set[str] = set()
        local_successes: set[str] = set()
        for stage in stages:
            field_usage.update(str(key) for key in stage)
            for field in ("quests", "quest_sequence", "parallel_quests"):
                for name in _strings(stage.get(field)):
                    if name.startswith("conditional:"):
                        continue
                    key = normalize_text(name)
                    if key:
                        quests.setdefault(key, name)
                        local_quests.add(key)
            for name in _strings(stage.get("successes")):
                key = normalize_text(name)
                if key:
                    successes.setdefault(key, name)
                    local_successes.add(key)
        chapter_stats[chapter_id] = {
            "stages": len(stages),
            "quests": len(local_quests),
            "successes": len(local_successes),
        }

    conditional_files: list[str] = []
    for meta in canonical.get("conditional_routes", []) or []:
        if not isinstance(meta, dict):
            continue
        filename = str(meta.get("file") or "").strip()
        if filename:
            conditional_files.append(filename)
            if not (BASE / filename).is_file():
                missing_files.append(filename)

    transversal_files: dict[str, str] = {}
    for field in ("temporal_registry", "ocre_capture_registry", "ocre_final_route"):
        filename = str(canonical.get(field) or "").strip()
        if not filename:
            continue
        transversal_files[field] = filename
        path = BASE / filename
        if not path.is_file():
            missing_files.append(filename)
            continue
        if field == "ocre_final_route":
            route = load_manual_chapter(path)
            declared = route.get("stage_count")
            stages = [stage for stage in route.get("stages", []) or [] if isinstance(stage, dict)]
            if declared is not None and int(declared) != len(stages):
                bad_stage_counts.append({
                    "chapter": field,
                    "declared": int(declared),
                    "actual": len(stages),
                })

    return {
        "manifest_status": str(manifest.get("status") or ""),
        "canonical_chapters": len(chapters),
        "canonical_stages": sum(row["stages"] for row in chapter_stats.values()),
        "distinct_authored_quests": len(quests),
        "distinct_authored_successes": len(successes),
        "conditional_routes": len(conditional_files),
        "transversal_files": transversal_files,
        "chapter_stats": chapter_stats,
        "field_usage": dict(sorted(field_usage.items())),
        "missing_files": sorted(set(missing_files)),
        "bad_stage_counts": bad_stage_counts,
    }


def main() -> int:
    report = audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["missing_files"] or report["bad_stage_counts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
