"""Review the raw Doduda quest -> step -> objective links for named Ganymède candidates.

This standalone CLI does not build any optimized guide or modify game progress.
Raw row existence, start criteria and objective type IDs are *evidence for review*,
not verification of the objective meaning, item quantities or mandatory route.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from app import quest_catalog as qc
from app.quest_source_index import QuestSourceError, QuestSources
from tools.audit_ganymede_quest_candidates import ROOT, audit_ganymede_quest_candidates

REQUIRED = ("quests.json", "quest_steps.json", "quest_objectives.json")


def _positive_int(value: object) -> int | None:
    if type(value) is int and value > 0:
        return value
    return None


def audit_ganymede_doduda_objective_links(
    root: Path,
    *,
    raw_dir: Path | None = None,
) -> dict[str, object]:
    root = Path(root).resolve()
    default_dir = (
        qc.RAW_QUEST_DATA_DIR if root == ROOT.resolve()
        else root / "data/cache/dofus_maps/raw/doduda_cli"
    )
    data_dir = Path(raw_dir) if raw_dir is not None else default_dir
    upstream = audit_ganymede_quest_candidates(root)
    base = {
        "schema_version": 1,
        "evidence_level": "doduda_raw_quest_step_objective_id_structure_only",
        "raw_source_dir": str(data_dir),
        "certified_quest_objectives": 0,
        "certified_prerequisites": 0,
        "certified_routes": 0,
    }
    if upstream["status"] != "REVIEW_REQUIRED":
        return {
            **base, "status": "FAIL", "candidate_count": 0,
            "issues": [{"code": "unvalidated_source_candidates",
                        "detail": "Ganymède source and crosswalk audit did not pass"}],
        }
    candidates = [
        {
            "source_guide_id": report["source_guide_id"],
            "quest_id": pair["external_dofusdb_quest_id"],
            "source_step_mentions": pair["observed_source_steps"],
        }
        for report in upstream["guide_reports"]
        for pair in report["candidate_pairs"]
        if pair["status"] == "REVIEW_TRIANGULATED_SOURCES"
    ]
    missing = [str(data_dir / name) for name in REQUIRED
               if not (data_dir / name).is_file()]
    if missing:
        return {
            **base, "status": "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE",
            "candidate_count": len(candidates), "missing_files": missing,
            "structure_reviews": [], "issues": [],
        }
    problems: list[dict[str, str]] = []
    reviews: list[dict[str, object]] = []
    try:
        # Temporary disk-backed offsets; no persistent caches, guide edits or UI.
        with tempfile.TemporaryDirectory(prefix="atlas-ganymede-structure-") as tmp:
            sources = QuestSources(Path(tmp), disk_backed=True)
            try:
                quests = sources.rows(data_dir / REQUIRED[0])
                steps = sources.rows(data_dir / REQUIRED[1])
                objectives_path = data_dir / REQUIRED[2]
                # Reuse Atlas' objective/step indexing contract. It loads IDs
                # from the source without decoding quest enrichment or UI rows.
                selected: dict[int, list[int]] = {}
                raw_quest_rows: dict[int, dict] = {}
                candidate_ids = {row["quest_id"] for row in candidates}
                for quest_id in sorted(candidate_ids):
                    raw = quests.get(quest_id)
                    if not isinstance(raw, dict) or (
                        (row_id := raw.get("id")) is not None and row_id != quest_id
                    ):
                        continue
                    raw_quest_rows[quest_id] = raw
                    raw_steps = qc.array_value(raw.get("stepIds"))
                    selected[quest_id] = [
                        _positive_int(v) for v in raw_steps
                    ]
                all_steps = {
                    sid for ids in selected.values() for sid in ids if sid is not None
                }
                objectives_by_step: dict[int, list[dict]] = {
                    sid: [] for sid in all_steps
                }
                for objective in sources.objectives_for_steps(
                    objectives_path, all_steps
                ):
                    if not isinstance(objective, dict):
                        problems.append({
                            "code": "invalid_objective_row",
                            "detail": "non-object objective data",
                        })
                        continue
                    sid = _positive_int(objective.get("stepId"))
                    if sid not in objectives_by_step:
                        problems.append({
                            "code": "unexpected_objective_step",
                            "detail": str(objective.get("stepId")),
                        })
                        continue
                    objectives_by_step[sid].append(objective)
                for row in candidates:
                    quest_id = row["quest_id"]
                    raw = raw_quest_rows.get(quest_id)
                    observed_steps = selected.get(quest_id, [])
                    invalid_step_ids = any(sid is None for sid in observed_steps)
                    step_reviews: list[dict[str, object]] = []
                    for sid in observed_steps:
                        if sid is None:
                            continue
                        step = steps.get(sid)
                        step_ok = (
                            isinstance(step, dict)
                            and step.get("id", sid) == sid
                        )
                        objective_rows = objectives_by_step.get(sid, [])
                        good_objectives = [
                            obj for obj in objective_rows
                            if _positive_int(obj.get("id")) is not None
                            and _positive_int(obj.get("typeId")) is not None
                        ]
                        objective_ids = [
                            obj["id"] for obj in good_objectives
                        ]
                        combat_types = sorted({
                            obj["typeId"] for obj in good_objectives
                            if obj["typeId"] in qc.COMBAT_OBJECTIVE_TYPES
                        })
                        step_reviews.append({
                            "step_id": sid,
                            "raw_step_record_present": bool(step_ok),
                            "raw_objective_ids": objective_ids,
                            "raw_objective_count": len(good_objectives),
                            "raw_combat_type_ids": combat_types,
                            "raw_objective_type_ids": sorted({
                                obj["typeId"] for obj in good_objectives
                            }),
                            "unresolved_objective_rows": (
                                len(objective_rows) - len(good_objectives)
                            ),
                        })
                    incomplete = (
                        raw is None or not observed_steps or invalid_step_ids
                        or any(
                            not s["raw_step_record_present"]
                            or s["raw_objective_count"] == 0
                            or s["unresolved_objective_rows"] > 0
                            for s in step_reviews
                        )
                    )
                    reviews.append({
                        **row,
                        "status": ("REVIEW_RAW_STRUCTURE_GAPS" if incomplete
                                   else "RAW_QUEST_STEP_OBJECTIVE_IDS_PRESENT_ONLY"),
                        "canonical_quest_row_present": raw is not None,
                        "canonical_start_criterion_uninterpreted": (
                            str(raw.get("startCriterion") or "") if raw else None
                        ),
                        "canonical_quest_step_ids": observed_steps,
                        "step_reviews": step_reviews,
                        "quest_actions_confirmed": False,
                        "item_quantities_confirmed": False,
                        "mandatory_order_confirmed": False,
                    })
            finally:
                sources.close()
    except (QuestSourceError, OSError, ValueError, KeyError, RuntimeError) as exc:
        problems.append({
            "code": "canonical_data_unreadable",
            "detail": str(exc),
        })
    count_gaps = sum(
        r["status"] == "REVIEW_RAW_STRUCTURE_GAPS" for r in reviews
    )
    return {
        **base,
        "status": (
            "FAIL" if problems
            else "REVIEW_RAW_STRUCTURE_GAPS" if count_gaps
            else "PASS_RAW_STRUCTURE_ONLY"
        ),
        "candidate_count": len(candidates),
        "reviewed_candidates": len(reviews),
        "incomplete_structure_candidates": count_gaps,
        "structure_reviews": reviews,
        "issues": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_ganymede_doduda_objective_links(
        args.root, raw_dir=args.raw_dir
    )
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if report["status"] == "FAIL" else (
        2 if report["status"].startswith("BLOCKED_") else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
