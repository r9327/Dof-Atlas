"""Compare observed Ganymède DofusDB quest links with existing Atlas guide IDs.

Read-only evidence. Numerical equality is a candidate for independent
verification, never proof of quest identity, required action, route order,
source licensing, or prerequisite satisfaction.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from tools.audit_ganymede_master_refs import (
    INDEX, ROOT, audit_ganymede_master_refs,
)

GUIDES_DIR = Path("data/encyclopedia/guides")
CROSSWALK = GUIDES_DIR / "ganymede_source_crosswalk.json"


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _canonical_ids(path: Path, expected_id: str) -> set[int]:
    guide = _load(path)
    if guide.get("id") != expected_id:
        raise ValueError(f"Atlas guide ID mismatch: {path}")
    sections = guide.get("sections")
    if not isinstance(sections, list):
        raise ValueError(f"Atlas guide has no valid sections: {path}")
    ids: set[int] = set()
    for section in sections:
        if not isinstance(section, dict) or not isinstance(section.get("steps"), list):
            raise ValueError(f"invalid Atlas guide section: {path}")
        for step in section["steps"]:
            if not isinstance(step, dict):
                raise ValueError(f"invalid Atlas guide step: {path}")
            if step.get("type") != "quest":
                continue
            quest_id = step.get("entity_id")
            if type(quest_id) is not int or quest_id <= 0:
                raise ValueError(f"invalid canonical quest ID: {path}")
            ids.add(quest_id)
    return ids


def audit_ganymede_quest_candidates(root: Path) -> dict[str, object]:
    """Return explicit per-guide REVIEW candidates and unpaired references."""
    root = root.resolve()
    problems: list[dict[str, str]] = []
    try:
        catalog = _load(root / INDEX)
        crosswalk = _load(root / CROSSWALK)
    except (OSError, ValueError) as exc:
        return {
            "status": "FAIL", "evidence_type": "numerical_id_comparison_only",
            "certified_quest_mappings": 0,
            "issues": [{"code": "missing_or_invalid_catalog", "detail": str(exc)}],
        }

    indexed = {row.get("ganymede_guide_id") for row in catalog.get("guides", [])
               if isinstance(row, dict) and type(row.get("ganymede_guide_id")) is int}
    relationships: dict[int, list[str]] = {}
    for row in crosswalk.get("guides", []):
        if not isinstance(row, dict):
            problems.append({"code": "invalid_crosswalk", "detail": "non-object crosswalk row"})
            continue
        external = row.get("ganymede_guide_id")
        targets = row.get("atlas_guide_ids")
        if (type(external) is not int or external not in indexed
                or external in relationships
                or not isinstance(targets, list) or not targets
                or any(not isinstance(v, str) or not v for v in targets)
                or len(set(targets)) != len(targets)):
            problems.append({"code": "invalid_crosswalk", "detail": str(external)})
            continue
        if (row.get("status") != "metadata_only"
                or row.get("quest_mapping_verified") is not False
                or row.get("route_parity_verified") is not False):
            problems.append({"code": "unproved_crosswalk", "detail": str(external)})
            continue
        relationships[external] = targets

    reports = []
    unique_external: set[int] = set()
    count_candidate = 0
    for path in sorted((root / GUIDES_DIR).glob("ganymede_*_observed_links.json")):
        validation = audit_ganymede_master_refs(root, snapshot=path.relative_to(root))
        if validation["status"] != "PASS_OBSERVED_LINKS_ONLY":
            problems.append({
                "code": "invalid_source_snapshot",
                "detail": f"{path.name}: {validation['issues']}",
            })
            continue
        snapshot = _load(path)
        guide_id = snapshot["source"]["guide_id"]
        per_quest_steps: dict[int, set[int]] = defaultdict(set)
        for step in snapshot["steps"]:
            for quest_id in step["external_dofusdb_ids"]["quest"]:
                per_quest_steps[quest_id].add(step["source_step_number"])

        external_ids = set(per_quest_steps)
        unique_external.update(external_ids)
        atlas_guides = relationships.get(guide_id, [])
        local_ids: set[int] = set()
        for name in atlas_guides:
            try:
                local_ids.update(_canonical_ids(root / GUIDES_DIR / f"{name}.json", name))
            except (OSError, ValueError) as exc:
                problems.append({
                    "code": "invalid_atlas_guide",
                    "detail": f"{guide_id} -> {name}: {exc}",
                })

        common_ids = external_ids & local_ids
        count_candidate += len(common_ids)
        records = [
            {
                "external_dofusdb_quest_id": quest_id,
                "candidate_atlas_quest_id": quest_id,
                "observed_source_steps": sorted(per_quest_steps[quest_id]),
                "status": "REVIEW_NUMERIC_ID_ONLY",
                "quest_identity_confirmed": False,
                "required_objective_confirmed": False,
            }
            for quest_id in sorted(common_ids)
        ]
        reports.append({
            "source_guide_id": guide_id,
            "source_snapshot": path.name,
            "observed_steps": len(snapshot["steps"]),
            "atlas_guide_ids": atlas_guides,
            "mapping_state": "GUIDE_MATCH_METADATA_ONLY" if atlas_guides else "GUIDE_UNMAPPED",
            "external_quest_ids": len(external_ids),
            "local_atlas_quest_ids": len(local_ids),
            "numeric_id_candidate_count": len(records),
            "external_only_quest_ids": sorted(external_ids - local_ids),
            "atlas_only_quest_ids": sorted(local_ids - external_ids),
            "candidate_pairs": records,
        })

    reports.sort(key=lambda row: row["source_guide_id"])
    return {
        "schema_version": 1,
        "status": "FAIL" if problems else "REVIEW_REQUIRED",
        "evidence_type": "numerical_id_comparison_only",
        "guide_snapshots_checked": len(reports),
        "source_quest_ids_distinct_across_guides": len(unique_external),
        "numeric_id_candidates_per_guide": count_candidate,
        "certified_quest_mappings": 0,
        "certified_quest_objectives": 0,
        "guide_reports": reports,
        "issues": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, help="optional report, not source data")
    args = parser.parse_args()
    report = audit_ganymede_quest_candidates(args.root)
    result = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
