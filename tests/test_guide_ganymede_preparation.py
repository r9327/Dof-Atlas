"""Preparation projections use source evidence; they never invent shopping lists."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from app.modules.encyclopedia.services.guide_ganymede_plan_input import (
    prepare_ganymede_plan_input,
    preview_ganymede_preparation,
)
from app.modules.encyclopedia.services.guide_ganymede_preparation import (
    stage_preparation_preview,
    summarize_stage_preparation,
)
from tools.audit_ganymede_stage_needs import audit_stage_needs


def _fixture(participants=("character:1", "character:2")):
    participants = list(participants)
    def proposal(num, classification, ids, qty, optional=False, **details):
        return {
            "proposal_id": f"ganymede_2205_step_{num:04d}:action:000",
            "atlas_guide_id": "dofus_cawotte",
            "stable_step_id": f"ganymede_2205_step_{num:04d}",
            "source_step_number": num,
            "classification": classification,
            "source_label": "Action source",
            "source_references": {"object_ids": ids},
            "source_details": {
                "quantity_scope_candidate": None,
                "obtainable_on_route_candidate": False,
                **details,
            },
            "quantity_candidate": qty,
            "optional": optional,
            "route_planning_ready": False,
            "auto_completion_allowed": False,
            "canonical_objective_verified": False,
            "selected_character_keys": participants,
        }
    return {
        "status": "REVIEW_ONLY_NOT_READY_FOR_OPTIMIZATION",
        "ready_for_automatic_planning": False,
        "inventory_assumed": False,
        "canonical_objectives_verified": 0,
        "selected_character_keys": participants,
        "source_action_proposals": [
            proposal(1, "preparation_candidate", [361], 3),
            proposal(2, "acquire_on_route_candidate", [441], 2),
            proposal(3, "preparation_candidate", [361], 10,
                     optional=True, needed_at_source_step=8),
            proposal(4, "preparation_candidate", [12, 13], 10),
            proposal(5, "preparation_candidate", [12, 13], 10,
                     quantity_scope_candidate="each_item"),
        ],
    }


class GanymedeStagePreparationTests(unittest.TestCase):
    def test_known_stock_unknown_stock_and_repeated_occurrences(self):
        data = stage_preparation_preview(
            _fixture(), known_owned_items={"character:1": {361: 2, 441: 0}},
        )
        self.assertEqual(len(data["rows"]), 14)
        self.assertEqual(data["on_route_rows"], 2)
        self.assertFalse(data["mandatory_purchase_claimed"])
        self.assertIsNone(data["aggregated_purchase_total"])
        first = next(x for x in data["rows"]
                     if x["source_step_number"] == 1
                     and x["character_key"] == "character:1")
        second = next(x for x in data["rows"]
                      if x["source_step_number"] == 1
                      and x["character_key"] == "character:2")
        self.assertEqual(first["remaining_quantity_candidate"], 1)
        self.assertEqual(first["owned_quantity_explicit"], 2)
        self.assertFalse(first["must_purchase"])
        self.assertIsNone(second["remaining_quantity_candidate"])
        self.assertFalse(second["stock_known"])
        self.assertEqual(
            [x["quantity_per_character_candidate"] for x in data["rows"]
             if x["source_step_number"] == 4],
            [None] * 4,
        )
        self.assertEqual(
            [x["quantity_per_character_candidate"] for x in data["rows"]
             if x["source_step_number"] == 5],
            [10] * 4,
        )
        optional = [x for x in data["rows"] if x["source_step_number"] == 3]
        self.assertTrue(all(x["optional_or_conditional"] and
                            x["needed_at_source_step"] == 8
                            for x in optional))

    def test_compact_summary_never_adds_repeated_or_optional_source_actions(self):
        preview = stage_preparation_preview(
            _fixture(), known_owned_items={
                "character:1": {361: 1, 441: 0},
            },
        )
        summary = summarize_stage_preparation(preview)
        self.assertEqual(summary["status"], "REVIEW_PREPARATION_COMPACT")
        self.assertEqual(summary["distinct_item_count"], 4)
        self.assertFalse(summary["mandatory_purchase_claimed"])
        carrots = next(x for x in summary["items"] if x["item_id"] == 361)
        self.assertEqual(len(carrots["source_occurrences"]), 2)
        self.assertTrue(carrots["quantity_review_required"])
        self.assertIsNone(carrots["required_total_candidate"])
        self.assertIsNone(carrots["remaining_total_candidate"])
        self.assertTrue(carrots["by_character"]["character:1"]["requires_quantity_review"])
        self.assertFalse(carrots["must_purchase"])
        on_route = next(x for x in summary["items"] if x["item_id"] == 441)
        self.assertIsNone(on_route["remaining_total_candidate"])
        self.assertTrue(on_route["by_character"]["character:1"]["obtainable_on_route_candidate"])

    def test_single_known_item_sums_only_explicit_per_character_needs(self):
        source = _fixture()
        source["source_action_proposals"] = source["source_action_proposals"][:1]
        preview = stage_preparation_preview(source, known_owned_items={
            "character:1": {361: 1},
            "character:2": {361: 2},
        })
        summary = summarize_stage_preparation(preview)
        self.assertEqual(summary["distinct_item_count"], 1)
        item = summary["items"][0]
        self.assertEqual(item["required_total_candidate"], 6)
        self.assertEqual(item["remaining_total_candidate"], 3)
        self.assertEqual(item["by_character"]["character:1"]["remaining_quantity_candidate"], 2)
        self.assertEqual(item["by_character"]["character:2"]["remaining_quantity_candidate"], 1)
        self.assertFalse(item["quantity_review_required"])
        self.assertFalse(item["must_purchase"])
        partial = stage_preparation_preview(
            source, known_owned_items={"character:1": {361: 1}}
        )
        self.assertIsNone(
            summarize_stage_preparation(partial)["items"][0]["remaining_total_candidate"]
        )
        zero = stage_preparation_preview(_fixture(()))
        self.assertEqual(summarize_stage_preparation(zero)["items"], [])

    def test_one_thousand_items_five_characters_remain_distinct_and_compact(self):
        participants = [f"character:{index}" for index in range(1, 6)]
        source = _fixture(participants)
        base = source["source_action_proposals"][0]
        source["source_action_proposals"] = []
        for number in range(1, 1001):
            row = deepcopy(base)
            row["proposal_id"] = f"ganymede_2205_step_{number:04d}:action:000"
            row["stable_step_id"] = f"ganymede_2205_step_{number:04d}"
            row["source_step_number"] = number
            row["source_references"]["object_ids"] = [number]
            row["quantity_candidate"] = 1
            source["source_action_proposals"].append(row)
        inventories = {key: {i: 0 for i in range(1, 1001)}
                       for key in participants}
        preview = stage_preparation_preview(source, known_owned_items=inventories)
        summary = summarize_stage_preparation(preview)
        self.assertEqual(summary["distinct_item_count"], 1000)
        self.assertEqual(len(preview["rows"]), 5000)
        self.assertEqual(summary["items"][0]["required_total_candidate"], 5)
        self.assertEqual(summary["items"][-1]["remaining_total_candidate"], 5)
        self.assertTrue(all(len(item["by_character"]) == 5
                            and not item["must_purchase"]
                            for item in summary["items"]))

    def test_compact_rejects_false_certification_and_foreign_participants(self):
        preview = stage_preparation_preview(_fixture())
        preview["mandatory_purchase_claimed"] = True
        with self.assertRaises(ValueError):
            summarize_stage_preparation(preview)
        preview = stage_preparation_preview(_fixture())
        preview["rows"][0]["character_key"] = "character:unknown"
        with self.assertRaises(ValueError):
            summarize_stage_preparation(preview)

    def test_manual_progress_hides_only_selected_character_stage(self):
        data = stage_preparation_preview(
            _fixture(),
            completed_source_steps={
                "character:1": {"dofus_cawotte": {"ganymede_2205_step_0001"}}
            },
        )
        self.assertEqual(len(data["rows"]), 13)
        self.assertFalse(any(
            row["source_step_number"] == 1
            and row["character_key"] == "character:1"
            for row in data["rows"]
        ))
        self.assertTrue(any(
            row["source_step_number"] == 1
            and row["character_key"] == "character:2"
            for row in data["rows"]
        ))

    def test_zero_and_five_characters(self):
        none = stage_preparation_preview(_fixture(()))
        self.assertEqual(none["rows"], [])
        self.assertEqual(none["selected_character_keys"], [])
        five = stage_preparation_preview(_fixture(
            tuple(f"character:{i}" for i in range(1, 6))
        ))
        self.assertEqual(len(five["rows"]), 35)
        self.assertEqual(five["unknown_stock_rows"], 35)
        self.assertFalse(five["mandatory_purchase_claimed"])

    def test_invalid_evidence_inventory_and_participants_fail_closed(self):
        fake = _fixture()
        fake["ready_for_automatic_planning"] = True
        with self.assertRaises(ValueError):
            stage_preparation_preview(fake)
        fake = _fixture()
        fake["selected_character_keys"] = ["character:1", "character:1"]
        with self.assertRaises(ValueError):
            stage_preparation_preview(fake)
        with self.assertRaises(ValueError):
            stage_preparation_preview(
                _fixture(), known_owned_items={"character:1": {361: -1}},
            )
        with self.assertRaises(ValueError):
            stage_preparation_preview(
                _fixture(), known_owned_items={"character:3": {361: 1}},
            )
        fake = _fixture()
        fake["source_action_proposals"][0]["canonical_objective_verified"] = True
        with self.assertRaises(ValueError):
            stage_preparation_preview(fake)

    @classmethod
    def setUpClass(cls):
        cls.report = audit_stage_needs(Path(__file__).resolve().parents[1])
        if cls.report["status"] == "FAIL":
            raise AssertionError(cls.report["issues"])

    def test_real_dofus_source_and_explicit_characters(self):
        data = preview_ganymede_preparation(
            self.report, ["character:1", "character:2"],
            atlas_guide_ids=["dofus_abyssal"],
        )
        self.assertEqual(data["status"], "REVIEW_PREPARATION_BY_CHARACTER")
        self.assertGreater(len(data["rows"]), 0)
        self.assertTrue(all(x["atlas_guide_id"] == "dofus_abyssal"
                            for x in data["rows"]))
        self.assertFalse(any(x["item_id"] == 18043
                             and x["source_step_number"] == 1
                             for x in data["rows"]))
        self.assertTrue(all(x["owned_quantity_explicit"] is None
                            and x["remaining_quantity_candidate"] is None
                            for x in data["rows"]))

    def test_real_source_cannot_invent_stocks_or_skip_source_review(self):
        data = prepare_ganymede_plan_input(
            self.report, ["character:1"], atlas_guide_ids=["dofus_cawotte"],
        )
        projected = stage_preparation_preview(data, known_owned_items={
            "character:1": {361: 0},
        })
        self.assertFalse(projected["mandatory_purchase_claimed"])
        self.assertTrue(all(not row["canonical_requirement_verified"]
                            and not row["must_purchase"]
                            for row in projected["rows"]))
        fake = deepcopy(data)
        fake["inventory_assumed"] = True
        with self.assertRaises(ValueError):
            stage_preparation_preview(fake)


if __name__ == "__main__":
    unittest.main()
