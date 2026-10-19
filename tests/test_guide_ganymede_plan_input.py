"""Integration tests for #229 factual needs handed to #226.

Every imported row remains review-only until independently certified
against canonical quest objectives and explicit per-character progress.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from app.modules.encyclopedia.services.guide_ganymede_plan_input import (
    prepare_ganymede_plan_input,
)
from tools.audit_ganymede_stage_needs import audit_stage_needs


class GanymedePlanInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = audit_stage_needs(Path(__file__).resolve().parents[1])
        if cls.report["status"] == "FAIL":
            raise AssertionError(cls.report["issues"])

    def test_all_real_candidates_stay_unverified_and_keep_source_identity(self):
        result = prepare_ganymede_plan_input(
            self.report, ["character:1", "character:2"]
        )
        self.assertEqual(result["status"], "REVIEW_ONLY_NOT_READY_FOR_OPTIMIZATION")
        self.assertEqual(len(result["atlas_guide_ids"]), 20)
        self.assertEqual(result["source_stages"], 1694)
        self.assertFalse(result["inventory_assumed"])
        self.assertFalse(result["ready_for_automatic_planning"])
        self.assertTrue(result["source_action_proposals"])
        self.assertTrue(all(not x["auto_completion_allowed"]
                            and not x["route_planning_ready"]
                            and x["remaining_quantity"] is None
                            and x["inventory_status"] == "UNKNOWN"
                            and x["selected_character_keys"] ==
                            ["character:1", "character:2"]
                            for x in result["source_action_proposals"]))
        self.assertEqual(
            len({x["proposal_id"] for x in result["source_action_proposals"]}),
            len(result["source_action_proposals"]),
        )
        self.assertEqual(
            result["counts_by_source_bucket"]["encounters"], 444
        )
        self.assertEqual(
            result["counts_by_source_bucket"]["related_guide_links"], 9
        )

    def test_zero_one_two_five_characters_never_infer_stock(self):
        for size in (0, 1, 2, 5):
            with self.subTest(size=size):
                keys = [f"character:{i}" for i in range(1, size + 1)]
                result = prepare_ganymede_plan_input(
                    self.report, keys, atlas_guide_ids=["dofus_abyssal"],
                )
                self.assertEqual(result["selected_character_keys"], keys)
                self.assertTrue(all(x["selected_character_keys"] == keys
                                    for x in result["source_action_proposals"]))
                self.assertTrue(all(x["remaining_quantity"] is None
                                    for x in result["source_action_proposals"]))
                self.assertFalse(result["ready_for_automatic_planning"])

    def test_dofus_reward_is_not_scheduled_as_early_purchase(self):
        result = prepare_ganymede_plan_input(
            self.report, ["character:1"], atlas_guide_ids=["dofus_abyssal"],
        )
        rewards = [x for x in result["source_action_proposals"]
                   if x["classification"] == "reward_goal"]
        self.assertTrue(any(x["source_details"]["external_dofusdb_object_id"] == 18043
                            and x["source_step_number"] == 1
                            for x in rewards))
        self.assertFalse(any(
            x["classification"] in (
                "preparation_candidate", "acquire_on_route_candidate"
            ) and 18043 in (x["source_references"]["object_ids"] or [])
            and x["source_step_number"] == 1
            for x in result["source_action_proposals"]
        ))

    def test_on_route_and_optional_preserved_without_mandatory_purchase(self):
        result = prepare_ganymede_plan_input(self.report, [])
        on_route = [x for x in result["source_action_proposals"]
                    if x["classification"] == "acquire_on_route_candidate"]
        self.assertEqual(len(on_route), 91)
        self.assertTrue(all(x["kind"] in {
            "drop_object", "optional_drop", "collect_object"
        } for x in on_route))
        optional = [x for x in result["source_action_proposals"]
                    if x["kind"] == "optional_delivery"]
        self.assertEqual(len(optional), 2)
        self.assertTrue(all(x["optional"] for x in optional))
        unverified = [x for x in result["source_action_proposals"]
                      if x["classification"] == "related_guide_reference"]
        self.assertEqual(len(unverified), 9)
        self.assertTrue(all(
            x["source_details"]["public_tree_predecessor_verified"] is False
            for x in unverified
        ))

    def test_untrusted_report_or_character_is_rejected(self):
        fake = deepcopy(self.report)
        fake["canonical_requirements_certified"] = 1
        with self.assertRaises(ValueError):
            prepare_ganymede_plan_input(fake, ["character:1"])
        with self.assertRaises(ValueError):
            prepare_ganymede_plan_input(self.report,
                                        ["character:1", "character:1"])
        with self.assertRaises(ValueError):
            prepare_ganymede_plan_input(self.report,
                                        ["character:1"],
                                        atlas_guide_ids=["not-a-guide"])
        with self.assertRaises(ValueError):
            prepare_ganymede_plan_input(self.report,
                                        ["slot:1"])

    def test_no_duplicate_action_or_false_owned_state(self):
        fake = deepcopy(self.report)
        guide = fake["guides"]["dofus_abyssal"]
        stage = next(x for x in guide["stages_with_requirements"]
                     if x["needs"])
        stage["needs"][0]["owned_or_prepared_by_any_character"] = True
        with self.assertRaises(ValueError):
            prepare_ganymede_plan_input(fake, ["character:1"],
                                        atlas_guide_ids=["dofus_abyssal"])


if __name__ == "__main__":
    unittest.main()
