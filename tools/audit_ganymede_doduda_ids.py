"""Audit Ganymède quest-link IDs against Atlas' installed Doduda quest source.

Read-only. A number found in Doduda is not proof of the quest's localized
name, required objective, prerequisite, or optimal order. Neither a guide's
quest list nor the optional enriched documentation is canonical game truth.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from app.constants import RAW_QUEST_DATA_DIR
from app.quest_source_index import QuestSourceError, QuestSources
from tools.audit_ganymede_master_refs import INDEX, ROOT, audit_ganymede_master_refs

GUIDES = Path("data/encyclopedia/guides")
FILENAME = "quests.json"


def audit_ganymede_doduda_ids(
    root: Path,
    *,
    raw_quests_path: Path | None = None,
) -> dict[str, object]:
    root = Path(root).resolve()
    raw_path = Path(raw_quests_path) if raw_quests_path is not None else (
        RAW_QUEST_DATA_DIR / FILENAME if root == ROOT.resolve()
        else root / "data/cache/dofus_maps/raw/doduda_cli" / FILENAME
    )
    issues: list[dict[str, str]] = []
    try:
        index = json.loads((root / INDEX).read_text(encoding="utf-8"))
        catalog = index["guides"]
        if not isinstance(catalog, list) or not catalog:
            raise ValueError("empty or invalid main index")
        expected_ids = [row["ganymede_guide_id"] for row in catalog]
        if (any(type(x) is not int or x <= 0 for x in expected_ids)
                or len(expected_ids) != len(set(expected_ids))):
            raise ValueError("duplicate/invalid guide IDs in main index")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {
            "status": "FAIL",
            "issues": [{"code": "invalid_main_index", "detail": str(exc)}],
            "certified_quest_identities": 0, "certified_quest_objectives": 0,
            "certified_routes": 0,
        }

    seen: set[int] = set()
    all_ids: set[int] = set()
    source_guides: list[dict[str, object]] = []
    for path in sorted((root / GUIDES).glob("ganymede_*_observed_links.json")):
        check = audit_ganymede_master_refs(root, snapshot=path.relative_to(root))
        if check["status"] != "PASS_OBSERVED_LINKS_ONLY":
            issues.append({"code": "invalid_source_snapshot", "detail": path.name})
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        guide_id = doc["source"]["guide_id"]
        if guide_id in seen:
            issues.append({"code": "duplicate_source_guide", "detail": str(guide_id)})
            continue
        seen.add(guide_id)
        refs: dict[int, list[int]] = {}
        for step in doc["steps"]:
            for qid in step["external_dofusdb_ids"]["quest"]:
                refs.setdefault(qid, []).append(step["source_step_number"])
                all_ids.add(qid)
        source_guides.append({
            "source_guide_id": guide_id,
            "snapshot": path.name,
            "source_quest_ids": sorted(refs),
            "source_quest_id_occurrences": sum(len(v) for v in refs.values()),
            "source_step_references": {str(k): v for k, v in sorted(refs.items())},
        })

    missing_guides = sorted(set(expected_ids) - seen)
    unexpected_guides = sorted(seen - set(expected_ids))
    if missing_guides or unexpected_guides:
        issues.append({
            "code": "incomplete_source_coverage",
            "detail": f"missing={missing_guides}, unexpected={unexpected_guides}",
        })

    raw_ids: set[int] | None = None
    raw_failure: str | None = None
    if raw_path.is_file():
        try:
            # Reuse Atlas' canonical byte-offset reader; only enumerate IDs.
            # Never materialize complete quest records or import UI/web workers.
            with tempfile.TemporaryDirectory(prefix="atlas-ganymede-ids-") as tmp:
                sources = QuestSources(Path(tmp), disk_backed=True)
                try:
                    raw_ids = set(sources.rows(raw_path))
                finally:
                    sources.close()
            if any(type(k) is not int or k <= 0 for k in raw_ids):
                raise ValueError("invalid Doduda quest identifier")
        except (QuestSourceError, OSError, ValueError, KeyError) as exc:
            raw_failure = str(exc)
            issues.append({"code": "invalid_canonical_source", "detail": raw_failure})
    else:
        raw_failure = "installed Doduda quests.json not available"
        # Missing installation input blocks matching, not the source snapshots.

    for guide in source_guides:
        ids = set(guide["source_quest_ids"])
        guide["raw_doduda_id_state"] = (
            "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE" if raw_ids is None
            else "RAW_ID_EXISTENCE_CHECK_ONLY"
        )
        guide["raw_doduda_present_quest_ids"] = (
            sorted(ids & raw_ids) if raw_ids is not None else []
        )
        guide["raw_doduda_missing_quest_ids"] = (
            sorted(ids - raw_ids) if raw_ids is not None else []
        )
        guide["certified_quest_identities"] = 0
        guide["certified_quest_objectives"] = 0

    return {
        "schema_version": 1,
        "status": (
            "FAIL" if issues else
            "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE" if raw_ids is None else
            "REVIEW_RAW_ID_GAPS" if all_ids - raw_ids else
            "PASS_RAW_ID_EXISTENCE_ONLY"
        ),
        "evidence_level": "raw_doduda_numeric_id_membership_only",
        "raw_source_path": str(raw_path),
        "raw_source_available": raw_ids is not None,
        "canonical_source_blocker": raw_failure,
        "observed_source_guides": len(source_guides),
        "indexed_source_guides": len(expected_ids),
        "distinct_external_quest_ids": len(all_ids),
        "raw_doduda_quest_records": len(raw_ids) if raw_ids is not None else None,
        "raw_doduda_present_external_ids": (
            len(all_ids & raw_ids) if raw_ids is not None else None
        ),
        "raw_doduda_missing_external_ids": (
            sorted(all_ids - raw_ids) if raw_ids is not None else None
        ),
        "certified_quest_identities": 0,
        "certified_quest_objectives": 0,
        "certified_routes": 0,
        "guide_reports": sorted(source_guides, key=lambda x: x["source_guide_id"]),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--raw-quests", type=Path,
        help="explicit installed Doduda quests.json (never downloaded automatically)",
    )
    parser.add_argument("--output", type=Path, help="optional review report path")
    args = parser.parse_args()
    report = audit_ganymede_doduda_ids(args.root, raw_quests_path=args.raw_quests)
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 1 if report["status"] == "FAIL" else 2 if report["status"].startswith("BLOCKED_") else 0


if __name__ == "__main__":
    raise SystemExit(main())
