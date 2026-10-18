"""Read-only readiness gate for replacing legacy Dofus guides with Ganymède routes.

The existing Ganymède snapshots contain numbered factual-link occurrences
only, NOT playable step actions. Never activate or write replacements merely
because the source's numbered-step coverage reaches 100 percent.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.audit_ganymede_master_refs import (
    INDEX, ROOT, audit_ganymede_master_refs,
)
from tools.audit_ganymede_step_actions import audit_action_candidates

GUIDES_DIR = Path("data/encyclopedia/guides")
CATALOG = GUIDES_DIR / "catalog.json"
CROSSWALK = GUIDES_DIR / "ganymede_source_crosswalk.json"


def audit_ganymede_replacement_readiness(root: Path) -> dict:
    root = Path(root).resolve()
    issues: list[dict] = []
    try:
        catalogue = json.loads((root / CATALOG).read_text(encoding="utf-8"))
        links = json.loads((root / CROSSWALK).read_text(encoding="utf-8"))
        index = json.loads((root / INDEX).read_text(encoding="utf-8"))
        guide_entries = catalogue["guides"]
        source_entries = index["guides"]
        link_entries = links["guides"]
        if not all(isinstance(v, list) for v in
                   (guide_entries, source_entries, link_entries)):
            raise ValueError("catalog/index/crosswalk records must be lists")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "FAIL", "issues": [
            {"code": "invalid_catalog", "detail": str(exc)}
        ], "ready_to_replace": 0}

    source_by_id = {
        row["ganymede_guide_id"]: row for row in source_entries
    }
    matched: dict[str, list[dict]] = {}
    for link in link_entries:
        for guide_id in link["atlas_guide_ids"]:
            matched.setdefault(guide_id, []).append(link)
    snapshots: dict[int, Path] = {}
    for path in sorted((root / GUIDES_DIR).glob("ganymede_*_observed_links.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            source_id = payload["source"]["guide_id"]
            if source_id in snapshots:
                raise ValueError(f"duplicate source guide: {source_id}")
            snapshots[source_id] = path
        except (OSError, ValueError, KeyError, TypeError) as exc:
            issues.append({"code": "invalid_source_snapshot",
                           "detail": f"{path.name}: {exc}"})

    dofus_guides = [item for item in guide_entries
                    if item.get("category") == "dofus"
                    and item.get("enabled") is True]
    records = []
    for entry in dofus_guides:
        local_id = entry["id"]
        originals = matched.get(local_id, [])
        sources = []
        blockers = []
        if not originals:
            blockers.append("NO_DIRECT_GANYMEDE_MAPPING")
        try:
            existing = json.loads((
                root / GUIDES_DIR / entry["file"]
            ).read_text(encoding="utf-8"))
            if existing.get("id") != local_id:
                raise ValueError("local guide ID differs from catalog")
            old_steps = sum(len(section["steps"]) for section in
                            existing["sections"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            old_steps = None
            blockers.append("INVALID_LEGACY_GUIDE")
            issues.append({"code": "invalid_legacy_guide",
                           "detail": f"{local_id}: {exc}"})
        for link in originals:
            source_id = link["ganymede_guide_id"]
            index_entry = source_by_id.get(source_id)
            path = snapshots.get(source_id)
            state = {
                "ganymede_guide_id": source_id,
                "mapping_state": link.get("status"),
                "expected_source_step_count": (
                    index_entry["listed_step_count"] if index_entry else None
                ),
                "observed_source_step_count": None,
                "source_snapshot_verified": False,
                "playable_actions_reconstructed": 0,
                "source_step_actions_verified": 0,
                "canonical_objectives_verified": False,
            }
            if path is None:
                blockers.append("MISSING_SOURCE_SNAPSHOT")
            elif index_entry is None:
                blockers.append("UNKNOWN_SOURCE_GUIDE")
            else:
                check = audit_ganymede_master_refs(
                    root, snapshot=path.relative_to(root)
                )
                if check["status"] != "PASS_OBSERVED_LINKS_ONLY":
                    blockers.append("SOURCE_REFERENCE_INCOMPLETE")
                    issues.append({"code": "source_coverage_failure",
                                   "detail": f"{source_id}: {check['issues']}"})
                else:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    state["observed_source_step_count"] = len(payload["steps"])
                    state["source_snapshot_verified"] = True
            # A source-action review is evidence, not gameplay certification.
            # The validator checks external IDs and coordinates against the
            # observed source without enabling the replacement.
            state["reviewed_action_candidate_steps"] = 0
            state["action_candidate_evidence_status"] = "NOT_RECONSTRUCTED"
            candidate_file = (
                GUIDES_DIR / f"ganymede_{source_id}_action_candidates.json"
            )
            if (root / candidate_file).is_file():
                action_report = audit_action_candidates(root, candidate_file)
                state["action_candidate_evidence_status"] = action_report["status"]
                if action_report["status"] == "REVIEW_ACTION_CANDIDATES_ONLY":
                    state["reviewed_action_candidate_steps"] = (
                        action_report["reviewed_steps"]
                    )
                else:
                    issues.append({
                        "code": "action_candidate_evidence_invalid",
                        "detail": f"{source_id}: {action_report.get('issues', [])}",
                    })
            sources.append(state)
        # The known snapshot schema explicitly forbids editorial text/actions.
        # It never proves a runnable fiche, progress migration or prerequisites.
        blockers.extend([
            "SOURCE_STEP_ACTIONS_NOT_RECONSTRUCTED",
            "DODUDA_OBJECTIVES_AND_PREREQUISITES_NOT_CERTIFIED",
            "PROGRESS_MIGRATION_NOT_VERIFIED",
        ])
        records.append({
            "atlas_guide_id": local_id,
            "category": "dofus",
            "legacy_step_count": old_steps,
            "legacy_guide_preserved": True,
            "legacy_progress_preserved": True,
            "source_guides": sources,
            "replacement_active": False,
            "ready_to_replace": False,
            "blockers": sorted(set(blockers)),
        })

    mapped = sum(bool(record["source_guides"]) for record in records)
    return {
        "schema_version": 1,
        "status": "FAIL" if issues else "BLOCKED_PENDING_PLAYABLE_ACTIONS",
        "evidence_level": "migration_gate_not_route_generation",
        "dofus_guides": len(records),
        "dofus_guides_with_direct_source_mapping": mapped,
        "dofus_guides_without_direct_source_mapping": [
            r["atlas_guide_id"] for r in records
            if not r["source_guides"]
        ],
        "ready_to_replace": 0,
        "replacement_activated": False,
        "progress_contract": (
            "characters[character_key].manual_steps[atlas_guide_id]"
        ),
        "guide_reports": records,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_ganymede_replacement_readiness(args.root)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 1 if report["status"] == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
