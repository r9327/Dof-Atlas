"""Export review-only, stage-scoped needs for the future Atlas guide planner.

No character inventory, quest completion, craft feasibility or source link is
inferred from a DofusDB ID. Required vs optional is preserved, not flattened.
This CLI is read-only unless --output is explicitly supplied.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.audit_ganymede_master_refs import ROOT
from tools.audit_ganymede_step_actions import audit_action_candidates

SOURCE = Path("data/encyclopedia/guides")
ALLOWED_SOURCE_STATUS = frozenset({
    "REVIEW_ACTION_CANDIDATES_ONLY", "AUTO_EXTRACTED_NEEDS_MANUAL_REVIEW",
})
OBJECT_NEEDS = frozenset({
    "prepare_object", "optional_preparation", "check_object", "collect_object",
    "craft", "drop_object", "optional_drop", "optional_delivery",
    "check_equipment", "equip",
})
PREREQUISITES = frozenset({"guide_dependency", "quest_prerequisite"})
ENCOUNTER_ACTIONS = frozenset({"combat", "dungeon", "group_mechanic", "optional_capture"})
ON_ROUTE_ACQUISITIONS = frozenset({"drop_object", "optional_drop", "collect_object"})
# Source-introduction reward IDs: a Dofus described as the guide's destination
# cannot simultaneously become a mandatory item to bring at its first step.
# Names and IDs were cross-checked against the pinned Doduda FR catalog.
FIRST_STEP_GOAL_ITEMS = {
    "dofus_abyssal": 18043,
    "dofus_des_glaces": 7043,
    "dofus_ebene": 7114,
    "dofus_ivoire": 7115,
    "dofus_turquoise": 739,
    "domakuro": 23237,
}


def stage_needs(candidate: dict) -> dict:
    """Keep every source action occurrence, even repeated object/quest IDs.

    Quantities are *source proposals*, never projected into inventories. An
    optional or conditional requirement cannot become a mandatory purchase.
    """
    if (candidate.get("ready_to_replace") is not False
            or candidate.get("certified_actions") != 0):
        raise ValueError("candidate cannot claim a certified, playable guide")
    guide_id = candidate["source_guide_id"]
    count = candidate["source_step_count"]
    steps = candidate["steps"]
    if type(count) is not int or count <= 0 or len(steps) != count:
        raise ValueError("incomplete candidate source stage coverage")
    output: list[dict] = []
    for position, stage in enumerate(steps, 1):
        if (stage.get("source_step_number") != position
                or stage.get("stable_step_id")
                != f"ganymede_{guide_id}_step_{position:04d}"
                or stage.get("quest_objectives_verified") is not False):
            raise ValueError(f"untrusted stage {position}")
        needs: list[dict] = []
        prereqs: list[dict] = []
        encounters: list[dict] = []
        goals: list[dict] = []
        for action_index, action in enumerate(stage["actions"]):
            kind = action["kind"]
            optional = (kind.startswith("optional_")
                        or action.get("optional") is True
                        or "conditional" in action
                        or "alternative_group" in action
                        or action.get("optional_branch") is True)
            # Some auto-extracted introductions mislabel the *Dofus reward*
            # as "Prévoir objet". Preserve the raw action but never turn the
            # item being pursued into a prerequisite or shopping order.
            reward_intro = (
                position == 1 and kind == "check_object"
                and action.get("object_id") ==
                FIRST_STEP_GOAL_ITEMS.get(candidate["atlas_guide_id"])
            )
            if kind == "goal_reward" or reward_intro:
                goals.append({
                    "source_action_index": action_index,
                    "source_action_label": action.get("label"),
                    "original_kind": kind,
                    "external_dofusdb_object_id": action.get("object_id"),
                    "goal_reward_candidate": True,
                    "reclassified_source_intro": reward_intro,
                    "owned_or_obtained_by_character": None,
                    "canonical_objective_verified": False,
                })
            if kind in OBJECT_NEEDS and not reward_intro:
                # A 'check_object' with no observed object ID remains a textual
                # task; never fabricate an item, amount, recipe or drop rate.
                external_ids = list(dict.fromkeys(
                    ([action["object_id"]] if "object_id" in action else [])
                    + list(action.get("object_ids", []))
                ))
                needs.append({
                    "source_action_index": action_index,
                    "source_action_label": action.get("label"),
                    "kind": kind,
                    "external_dofusdb_object_ids": external_ids,
                    "quantity_candidate": action.get("quantity"),
                    "quantity_per_character_candidate": action.get(
                        "quantity_per_character"
                    ),
                    "quantity_scope_candidate": action.get("quantity_scope"),
                    "needed_at_source_step": action.get(
                        "needed_at_source_step", position
                    ),
                    "collection_window_end_candidate": action.get(
                        "collection_window_end"
                    ),
                    "references_previous_stage_candidate": action.get(
                        "references_previous_stage"
                    ),
                    "conditional": action.get("conditional"),
                    "alternative_group": action.get("alternative_group"),
                    "optional": optional,
                    "acquisition_mode_candidate": (
                        kind if kind in ON_ROUTE_ACQUISITIONS else None
                    ),
                    "obtainable_on_route_candidate": (
                        True if kind in ON_ROUTE_ACQUISITIONS
                        else action.get("can_obtain_on_route")
                    ),
                    "source_review_status": stage["review_status"],
                    "canonical_requirement_verified": False,
                    "owned_or_prepared_by_any_character": None,
                })
            if kind in PREREQUISITES:
                prereqs.append({
                    "source_action_index": action_index,
                    "source_action_label": action.get("label"),
                    "kind": kind,
                    "external_dofusdb_quest_id": action.get("quest_id"),
                    "ganymede_prerequisite_guide_id": action.get("guide_id"),
                    "optional": optional,
                    "canonical_requirement_verified": False,
                })
            if kind in ENCOUNTER_ACTIONS:
                encounters.append({
                    "source_action_index": action_index,
                    "source_action_label": action.get("label"),
                    "kind": kind,
                    "external_dofusdb_monster_id": action.get("monster_id"),
                    "external_dofusdb_dungeon_id": action.get("dungeon_id"),
                    "alternative_monster_ids_candidate": action.get(
                        "alternative_monster_ids"
                    ),
                    "participants_min_candidate": action.get("participants_min"),
                    "group_fight_candidate": action.get("group_fight"),
                    "repeat_count_candidate": action.get("repeat_count"),
                    "capture_required_candidate": action.get("capture_required"),
                    "conditional_candidate": action.get("conditional"),
                    "optional": optional,
                    "source_review_status": stage["review_status"],
                    "canonical_requirement_verified": False,
                    "character_completion_known": None,
                })
        if needs or prereqs or encounters or goals:
            output.append({
                "stable_step_id": stage["stable_step_id"],
                "source_step_number": position,
                "needs": needs,
                "prerequisites": prereqs,
                "encounters": encounters,
                "goal_rewards": goals,
            })
    return {
        "atlas_guide_id": candidate["atlas_guide_id"],
        "source_guide_id": guide_id,
        "source_step_count": count,
        "stages_with_requirements": output,
        "canonical_requirements_certified": 0,
        "source_status": "REVIEW_ONLY_NOT_READY_FOR_OPTIMIZATION",
    }


def audit_stage_needs(root: Path) -> dict:
    root = Path(root).resolve()
    needs = {}
    problems: list[dict] = []
    paths = sorted((root / SOURCE).glob("ganymede_*_action_candidates.json"))
    for path in paths:
        report = audit_action_candidates(root, path)
        if report.get("status") not in ALLOWED_SOURCE_STATUS:
            problems.append({
                "source": path.name, "code": "candidate_invalid",
                "detail": report.get("issues", []),
            })
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            row = stage_needs(doc)
            guide_id = row["atlas_guide_id"]
            if guide_id in needs:
                raise ValueError(f"duplicate Atlas guide {guide_id}")
            needs[guide_id] = row
        except (OSError, ValueError, TypeError, KeyError) as exc:
            problems.append({
                "source": path.name, "code": "stage_needs_invalid",
                "detail": str(exc),
            })
    total = sum(row["source_step_count"] for row in needs.values())
    if len(paths) != 20 or len(needs) != 20 or total != 1694:
        problems.append({
            "code": "incomplete_dofus_stage_needs_corpus",
            "detail": f"expected 20 guides/1694 stages, got {len(needs)}/{total}",
        })
    return {
        "schema_version": 1,
        "status": "FAIL" if problems else "REVIEW_ONLY_NOT_READY_FOR_OPTIMIZATION",
        "source_candidate_guides": len(paths),
        "guides_with_preparation_proposals": sum(
            any(stage["needs"] or stage["prerequisites"]
                for stage in row["stages_with_requirements"])
            for row in needs.values()
        ),
        "guides_with_encounter_proposals": sum(
            any(stage["encounters"] for stage in row["stages_with_requirements"])
            for row in needs.values()
        ),
        "source_stages": sum(row["source_step_count"] for row in needs.values()),
        "encounter_action_proposals": sum(
            len(stage["encounters"])
            for guide in needs.values()
            for stage in guide["stages_with_requirements"]
        ),
        "goal_reward_proposals": sum(
            len(stage["goal_rewards"])
            for guide in needs.values()
            for stage in guide["stages_with_requirements"]
        ),
        "intro_reward_reclassifications": sum(
            reward["reclassified_source_intro"]
            for guide in needs.values()
            for stage in guide["stages_with_requirements"]
            for reward in stage["goal_rewards"]
        ),
        "on_route_acquisition_proposals": sum(
            need["acquisition_mode_candidate"] is not None
            for guide in needs.values()
            for stage in guide["stages_with_requirements"]
            for need in stage["needs"]
        ),
        "canonical_requirements_certified": 0,
        "stock_assumed": False,
        "participants_assumed": False,
        "guides": needs,
        "issues": problems,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit_stage_needs(args.root)
    data = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data, encoding="utf-8")
    else:
        print(data, end="")
    return 1 if report["status"] == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
