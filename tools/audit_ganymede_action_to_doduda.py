"""Cross-reference staged Ganymède quest-action hints with raw Doduda ID structure.

Read-only evidence. This does NOT certify that a proposed action matches
a canonical objective, identify the player's state, activate guides, or merge PRs.
Run with --raw-dir pointing at the installed Doduda CLI raw source directory.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from collections import defaultdict
from pathlib import Path

from app import quest_catalog as qc
from app.quest_source_index import QuestSourceError, QuestSources
from tools.audit_ganymede_master_refs import ROOT
from tools.audit_ganymede_prerequisites import parse_start_criterion
from tools.audit_ganymede_step_actions import audit_action_candidates

DIRECTORY = Path("data/encyclopedia/guides")
RAW_FILES = ("quests.json", "quest_steps.json", "quest_objectives.json")
VALID_CANDIDATE_STATES = {
    "REVIEW_ACTION_CANDIDATES_ONLY", "AUTO_EXTRACTED_NEEDS_MANUAL_REVIEW",
}

def positive_int(value: object) -> int | None:
    return value if type(value) is int and value > 0 else None

def audit_action_to_doduda(
    root: Path, *, raw_dir: Path | None = None,
    candidate_paths: list[Path] | None = None,
) -> dict:
    root = Path(root).resolve()
    raw_dir = Path(raw_dir) if raw_dir is not None else (
        qc.RAW_QUEST_DATA_DIR if root == ROOT.resolve()
        else root / "data/cache/dofus_maps/raw/doduda_cli"
    )
    candidates = (
        sorted((root / DIRECTORY).glob("ganymede_*_action_candidates.json"))
        if candidate_paths is None
        else [p if p.is_absolute() else root / p for p in candidate_paths]
    )
    issues = []
    occurrences = []
    for file in candidates:
        check = audit_action_candidates(root, file)
        if check["status"] not in VALID_CANDIDATE_STATES:
            issues.append({"code": "invalid_source_action_candidate",
                           "source": file.name,
                           "detail": check.get("issues", [])})
            continue
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
            for step in payload["steps"]:
                for action_index, action in enumerate(step["actions"]):
                    quest_id = action.get("quest_id")
                    if quest_id is None:
                        continue
                    if positive_int(quest_id) is None:
                        raise ValueError("invalid candidate quest ID")
                    occurrences.append({
                        "source_guide_id": payload["source_guide_id"],
                        "atlas_guide_id": payload["atlas_guide_id"],
                        "stable_step_id": step["stable_step_id"],
                        "source_step_number": step["source_step_number"],
                        "action_index": action_index,
                        "kind": action["kind"],
                        "quest_id": quest_id,
                        "source_review_status": step["review_status"],
                        "action_verified": False,
                    })
        except (OSError, KeyError, ValueError, TypeError) as exc:
            issues.append({"code": "unreadable_candidate",
                           "source": file.name, "detail": str(exc)})
    quest_ids = sorted({row["quest_id"] for row in occurrences})
    base = {
        "schema_version": 1,
        "evidence_level": "unverified_stage_action_to_raw_doduda_id_structure",
        "candidate_files": len(candidates),
        "source_quest_action_occurrences": len(occurrences),
        "distinct_quest_ids": len(quest_ids),
        "certified_quest_actions": 0,
        "certified_quest_objectives": 0,
        "certified_prerequisites": 0,
        "verified_character_progress": 0,
        "ready_to_replace": False,
    }
    if issues or not candidates:
        return {**base, "status": "FAIL",
                "issues": issues or [{"code": "no_candidate_files"}]}
    missing = [str(raw_dir / name) for name in RAW_FILES
               if not (raw_dir / name).is_file()]
    if missing:
        return {**base, "status": "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE",
                "missing_files": missing, "issues": [],
                "source_occurrences": occurrences,
                "quest_structure": {}}

    raw_quests = {}
    objective_by_step = defaultdict(list)
    gaps = []
    try:
        with tempfile.TemporaryDirectory(prefix="atlas-ganymede-action-ids-") as tmp:
            sources = QuestSources(Path(tmp), disk_backed=True)
            try:
                quests = sources.rows(raw_dir / RAW_FILES[0])
                steps = sources.rows(raw_dir / RAW_FILES[1])
                all_step_ids = set()
                for quest_id in quest_ids:
                    row = quests.get(quest_id)
                    if not isinstance(row, dict) or row.get("id", quest_id) != quest_id:
                        raw_quests[str(quest_id)] = {
                            "status": "REVIEW_CANONICAL_QUEST_MISSING",
                            "canonical_quest_present": False,
                            "canonical_step_ids": [],
                            "canonical_start_criterion": None,
                            "criterion_branches": None,
                            "raw_steps": [],
                        }
                        gaps.append({"quest_id": quest_id, "reason": "missing_canonical_quest"})
                        continue
                    original = qc.array_value(row.get("stepIds"))
                    if not isinstance(original, list):
                        original = []
                    step_ids = [positive_int(value) for value in original]
                    criterion = row.get("startCriterion", "")
                    parsed_criterion = (
                        parse_start_criterion(criterion) if isinstance(criterion, str)
                        else {"status": "REVIEW_NONSTRING_CRITERION"}
                    )
                    if None in step_ids or not step_ids:
                        gaps.append({"quest_id": quest_id, "reason": "unresolved_quest_steps"})
                    for sid in step_ids:
                        if sid is not None:
                            all_step_ids.add(sid)
                    raw_quests[str(quest_id)] = {
                        "status": "REVIEW_RAW_IDS_ONLY",
                        "canonical_quest_present": True,
                        "canonical_step_ids": step_ids,
                        "canonical_start_criterion": criterion,
                        "criterion_branches": parsed_criterion,
                        "raw_steps": [],
                    }
                for obj in sources.objectives_for_steps(
                    raw_dir / RAW_FILES[2], all_step_ids
                ):
                    if not isinstance(obj, dict):
                        continue
                    sid = positive_int(obj.get("stepId"))
                    if sid not in all_step_ids:
                        continue
                    objective_by_step[sid].append({
                        "objective_id": positive_int(obj.get("id")),
                        "type_id": positive_int(obj.get("typeId")),
                    })
                for quest_id in quest_ids:
                    info = raw_quests[str(quest_id)]
                    if not info["canonical_quest_present"]:
                        continue
                    for sid in info["canonical_step_ids"]:
                        if sid is None:
                            continue
                        record = steps.get(sid)
                        has_record = (isinstance(record, dict)
                                      and record.get("id", sid) == sid)
                        objectives = objective_by_step.get(sid, [])
                        valid = [o for o in objectives
                                 if o["objective_id"] is not None
                                 and o["type_id"] is not None]
                        info["raw_steps"].append({
                            "step_id": sid,
                            "canonical_step_record_present": has_record,
                            "objective_ids": [o["objective_id"] for o in valid],
                            "objective_type_ids": [o["type_id"] for o in valid],
                            "raw_objective_count": len(valid),
                            "objectives_verified_for_candidate_action": False,
                        })
                        if not has_record or not valid or len(valid) != len(objectives):
                            gaps.append({"quest_id": quest_id,
                                         "step_id": sid,
                                         "reason": "raw_step_or_objective_missing"})
                    if gaps and any(g["quest_id"] == quest_id for g in gaps):
                        info["status"] = "REVIEW_RAW_STRUCTURE_GAPS"
            finally:
                sources.close()
    except (QuestSourceError, OSError, ValueError, KeyError, TypeError,
            RuntimeError) as exc:
        return {**base, "status": "FAIL", "issues": [
            {"code": "canonical_data_unreadable", "detail": str(exc)}
        ]}
    # Occurrences remain separate: repeated quest links are not collapsed.
    for mention in occurrences:
        entry = raw_quests[str(mention["quest_id"])]
        mention["canonical_quest_present"] = entry["canonical_quest_present"]
        mention["canonical_objective_match_verified"] = False
        mention["action_is_mandatory"] = None
        mention["character_prerequisites_satisfied"] = None
    return {
        **base,
        "status": ("REVIEW_RAW_STRUCTURE_GAPS" if gaps
                   else "REVIEW_CANONICAL_STRUCTURE_ONLY"),
        "source_occurrences": occurrences,
        "quest_structure": raw_quests,
        "structure_gaps": gaps,
        "issues": [],
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--candidate", type=Path, action="append")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_action_to_doduda(
        args.root, raw_dir=args.raw_dir, candidate_paths=args.candidate,
    )
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    return 1 if result["status"] == "FAIL" else (
        2 if result["status"].startswith("BLOCKED_") else 0
    )

if __name__ == "__main__":
    raise SystemExit(main())
