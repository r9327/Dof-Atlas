"""Prepare continuous Ganymède-step replacements for Atlas Dofus guides.

Produces fully ordered, ID-stable *draft* route JSON from public factual
link/coordinate observations and existing Atlas quest IDs. No Ganymède prose
is copied. A link to a quest is not proof of the action required at a step.

This tool intentionally CANNOT activate or replace existing guides. The
step actions, quest-objective mapping, prerequisites, and per-character
progress migration need independent certification before cutover.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.audit_ganymede_master_refs import INDEX, ROOT, audit_ganymede_master_refs
from tools.audit_ganymede_replacement_readiness import (
    CATALOG, CROSSWALK, GUIDES_DIR,
)


def _json(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return result


def stable_step_id(source_guide_id: int, step_number: int) -> str:
    if (type(source_guide_id) is not int or source_guide_id <= 0
            or type(step_number) is not int or step_number <= 0):
        raise ValueError("Source guide/step identifiers must be positive integers")
    return f"ganymede_{source_guide_id}_step_{step_number:04d}"


def _snapshot_by_source_id(root: Path) -> dict[int, Path]:
    sources: dict[int, Path] = {}
    for path in sorted((root / GUIDES_DIR).glob("ganymede_*_observed_links.json")):
        payload = _json(path)
        ident = payload.get("source", {}).get("guide_id")
        if type(ident) is not int or ident <= 0 or ident in sources:
            raise ValueError(f"Invalid/duplicate Ganymède source guide: {path}")
        sources[ident] = path
    return sources


def build_dofus_replacement_previews(root: Path) -> dict[str, object]:
    root = Path(root).resolve()
    failures: list[dict[str, str]] = []
    try:
        catalog = _json(root / CATALOG)
        crosswalk = _json(root / CROSSWALK)
        index = _json(root / INDEX)
        snapshots = _snapshot_by_source_id(root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "FAIL", "issues": [{"code": "invalid_input",
                                               "detail": str(exc)}], "previews": {}}

    indexed = {row["ganymede_guide_id"]: row for row in index["guides"]}
    mapped: dict[str, list[int]] = {}
    for row in crosswalk["guides"]:
        for atlas_id in row["atlas_guide_ids"]:
            mapped.setdefault(atlas_id, []).append(row["ganymede_guide_id"])

    previews: dict[str, dict] = {}
    no_direct_source: list[str] = []
    candidate_count = 0
    for record in catalog["guides"]:
        if record.get("category") != "dofus" or record.get("enabled") is not True:
            continue
        atlas_id = record["id"]
        linked_ids = mapped.get(atlas_id, [])
        if not linked_ids:
            no_direct_source.append(atlas_id)
            continue
        if len(linked_ids) != 1:
            failures.append({"code": "ambiguous_route_sources",
                             "detail": f"{atlas_id}: {linked_ids}"})
            continue
        source_id = linked_ids[0]
        expected = indexed.get(source_id)
        snapshot_path = snapshots.get(source_id)
        if expected is None or snapshot_path is None:
            failures.append({"code": "source_missing", "detail": atlas_id})
            continue
        valid = audit_ganymede_master_refs(
            root, snapshot=snapshot_path.relative_to(root)
        )
        if valid["status"] != "PASS_OBSERVED_LINKS_ONLY":
            failures.append({"code": "source_invalid",
                             "detail": f"{atlas_id}: {valid['issues']}"})
            continue
        try:
            old = _json(root / GUIDES_DIR / record["file"])
            if old.get("id") != atlas_id:
                raise ValueError("Guide ID mismatch")
            observed = _json(snapshot_path)
            source_steps = observed["steps"]
            if len(source_steps) != expected["listed_step_count"]:
                raise ValueError("Step count differs from public index")
            local_quests: dict[int, list[dict]] = {}
            for section in old["sections"]:
                for step in section["steps"]:
                    if step.get("type") != "quest":
                        continue
                    qid = step.get("entity_id")
                    if type(qid) is not int or qid <= 0:
                        raise ValueError("Invalid Atlas quest ID")
                    local_quests.setdefault(qid, []).append({
                        "atlas_step_id": step.get("id"),
                        "atlas_section_id": section.get("id"),
                        "local_optional": step.get("optional"),
                        "local_relation": step.get("relation"),
                        "local_declared_prerequisites": step.get("prerequisites", []),
                        "local_alternative_groups": step.get("alternative_groups", []),
                    })
            # Reviewed factual actions are separate from executable/certified
            # objectives. Never make these drafts playable from a source hint.
            candidate_by_step = {}
            candidate_path = root / GUIDES_DIR / f"ganymede_{source_id}_action_candidates.json"
            if candidate_path.is_file():
                from tools.audit_ganymede_step_actions import audit_action_candidates
                validation = audit_action_candidates(root, candidate_path)
                if validation["status"] != "REVIEW_ACTION_CANDIDATES_ONLY":
                    raise ValueError(f"Invalid candidate actions for {source_id}: {validation['issues']}")
                candidate_evidence = _json(candidate_path)
                if candidate_evidence.get("atlas_guide_id") != atlas_id:
                    raise ValueError("Candidate actions belong to another Atlas guide")
                candidate_by_step = {
                    entry["source_step_number"]: entry
                    for entry in candidate_evidence["steps"]
                }
            steps = []
            for i, source_step in enumerate(source_steps, 1):
                if source_step["source_step_number"] != i:
                    raise ValueError(f"Source step out of sequence at #{i}")
                refs = source_step["external_dofusdb_ids"]
                quest_refs = refs["quest"]
                # Keep every source link, but never pretend a quest link
                # identifies the task actually performed on this step.
                steps.append({
                    "id": stable_step_id(source_id, i),
                    "type": "info",
                    "title": f"Étape {i}",
                    "content": "",
                    "optional": bool(candidate_by_step.get(i, {}).get("optional_completion", False)),
                    "source_guide_id": source_id,
                    "source_step_number": i,
                    "source_page": source_step["source_page"],
                    "source_coordinates_mentioned": source_step["coordinate_mentions"],
                    "source_linked_guide_ids": source_step["linked_guide_ids"],
                    "external_dofusdb_ids": refs,
                    "atlas_quest_candidates": [
                        {"quest_id": qid,
                         "atlas_occurrences": local_quests.get(qid, []),
                         "identity_certified": False,
                         "is_step_action_certified": False}
                        for qid in quest_refs
                    ],
                    **({"route_phase": candidate_by_step[i]["route_phase"]}
                       if i in candidate_by_step and "route_phase" in candidate_by_step[i]
                       else {}),
                    "source_action_candidate_status": (
                        "REVIEW_SOURCE_ACTION" if i in candidate_by_step
                        else "NO_ACTION_CANDIDATE_YET"
                    ),
                    "verified_actions": [],
                    "source_action_candidates": candidate_by_step.get(i, {}).get("actions", []),
                    "source_action_review_status": (
                        candidate_by_step.get(i, {}).get("review_status", "NOT_RECONSTRUCTED")
                    ),
                    "action_reconstruction_status": (
                        "REVIEW_FACTUAL_ACTION_NOT_CANONICAL" if i in candidate_by_step
                        else "NEEDS_CANONICAL_OBJECTIVE_REVIEW"
                    ),
                    "manual_completion_allowed": False,
                    "auto_completion_allowed": False,
                    "original_prose_imported": False,
                })
            candidate_count += len(steps)
            previews[atlas_id] = {
                "schema_version": 1,
                "id": atlas_id,
                "title": old.get("title", atlas_id),
                "category": "dofus",
                "completeness_status": "draft",
                "description": "Prévisualisation technique des étapes Ganymède (références uniquement).",
                "route_origin": "GANYMEDE_CONTINUOUS_STEP_ORDER",
                "replacement_status": "DRAFT_NOT_PLAYABLE",
                "replacement_active": False,
                "guide_progress_id_unchanged": True,
                "legacy_manual_steps_migration_verified": False,
                "source_guide_id": source_id,
                "source_guide_url": f"https://ganymede-app.com/guides/{source_id}",
                "source_prerequisite_guide_ids":
                    expected.get("public_tree_prerequisite_guide_ids", []),
                "expected_source_step_count": len(steps),
                "playable_step_count": 0,
                "factual_action_reviewed_step_count": len(candidate_by_step),
                "source_action_candidate_steps": len(candidate_by_step),
                "source_action_candidate_actions": sum(
                    len(value["actions"]) for value in candidate_by_step.values()
                ),
                "source_link_snapshot": snapshot_path.name,
                "source_text_copied": False,
                "sections": [{
                    "id": f"ganymede_{source_id}_continuous",
                    "title": "Suivi continu Ganymède",
                    "steps": steps,
                }],
                "cutover_blockers": [
                    "EACH_SOURCE_STEP_NEEDS_ORIGINAL_CANONICAL_ACTION",
                    "OBJECTIVES_AND_PREREQUISITES_UNVERIFIED",
                    "PER_CHARACTER_PROGRESS_MIGRATION_UNVERIFIED",
                ],
            }
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failures.append({"code": "cannot_build_preview",
                             "detail": f"{atlas_id}: {exc}"})

    return {
        "schema_version": 1,
        "status": "FAIL" if failures else "PREVIEWS_READY_NOT_PLAYABLE",
        "evidence_level": "public_links_and_local_quest_id_candidate_overlay",
        "dofus_guides_with_continuous_drafts": len(previews),
        "total_source_steps_in_drafts": candidate_count,
        "dofus_guides_without_direct_ganymede": no_direct_source,
        "replacement_activated": False,
        "playable_steps_certified": 0,
        "previews": previews,
        "issues": failures,
    }


def write_replacement_previews(report: dict[str, object], destination: Path) -> list[Path]:
    if report.get("status") != "PREVIEWS_READY_NOT_PLAYABLE":
        raise ValueError("Cannot export invalid source previews")
    out = Path(destination)
    # Export into an explicit review directory, never the live catalogue.
    if out.name in ("guides", "encyclopedia"):
        raise ValueError("Refusing to replace the live guide directory")
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, payload in sorted(report["previews"].items()):
        file = out / f"{name}.json"
        file.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        written.append(file)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path,
                        help="export continuous *drafts*, not live replacements")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = build_dofus_replacement_previews(args.root)
    if args.output_dir and result["status"] == "PREVIEWS_READY_NOT_PLAYABLE":
        written = write_replacement_previews(result, args.output_dir)
        result["written_draft_files"] = [str(p) for p in written]
    summary = {k: v for k, v in result.items() if k != "previews"}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
