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

    def test_pinned_french_names_only_overlay_the_exact_source_action(self):
        import re

        original = prepare_ganymede_plan_input(
            self.report, ["character:1"], atlas_guide_ids=["dofus_cawotte"],
        )
        target = next((
            row for row in original["source_action_proposals"]
            if isinstance(row["source_label"], str)
            and re.search(r"n[º°o]\\s*\\d+", row["source_label"], re.I)
            and row["source_references"]["object_ids"]
        ), None)
        self.assertIsNotNone(target, "Corpus must contain a named object reference")
        item_id = next(
            (i for i in target["source_references"]["object_ids"]
             if re.search(r"n[º°o]\\s*" + str(i) + r"\\b",
                          target["source_label"], re.I)), None,
        )
        self.assertIsNotNone(item_id, "A generic label needs its own referenced ID")
        translated = re.sub(
            r"n[º°o]\\s*" + str(item_id) + r"\\b",
            "«Objet localisé de test»", target["source_label"], count=1, flags=re.I,
        )
        override = {
            "stable_step_id": target["stable_step_id"],
            "action_index": target["source_action_index"],
            "source_label": target["source_label"],
            "display_label": translated,
            "canonical_objective_verified": False,
            "resolved_entities": [{
                "namespace": "object", "source_entity_id": item_id,
                "source_name": "Objet localisé de test", "name_locale": "fr",
            }],
        }
        evidence = {
            "schema_version": 1, "status": "REVIEW_NAMES_RESOLVED",
            "source": "doduda_pinned_french_names_and_ganymede_public_index",
            "pinned_release": "3.7.10.10",
            "generic_label_actions": 1, "resolved_action_labels": 1,
            "unresolved_reference_count": 0,
            "canonical_objectives_verified": 0, "ready_to_replace": False,
            "guides": [{
                "source_guide_id": target["source_guide_id"],
                "label_overrides": [override],
            }],
        }
        localized = prepare_ganymede_plan_input(
            self.report, ["character:1"], atlas_guide_ids=["dofus_cawotte"],
            french_label_evidence=evidence,
        )
        row = next(p for p in localized["source_action_proposals"]
                   if p["proposal_id"] == target["proposal_id"])
        self.assertEqual(row["source_label"], target["source_label"])
        self.assertEqual(row["display_label"], translated)
        self.assertTrue(row["localized_name_verified"])
        self.assertFalse(row["canonical_objective_verified"])
        self.assertFalse(row["route_planning_ready"])
        self.assertFalse(next(p for p in localized["source_action_proposals"]
                              if p["proposal_id"] != target["proposal_id"]
                              )["localized_name_verified"])

        stale = deepcopy(evidence)
        stale["guides"][0]["label_overrides"][0]["source_label"] = "Other action"
        with self.assertRaises(ValueError):
            prepare_ganymede_plan_input(
                self.report, ["character:1"], atlas_guide_ids=["dofus_cawotte"],
                french_label_evidence=stale,
            )
        wrong_id = deepcopy(evidence)
        wrong_id["guides"][0]["label_overrides"][0]["resolved_entities"][0]["source_entity_id"] = 99999999
        with self.assertRaises(ValueError):
            prepare_ganymede_plan_input(
                self.report, ["character:1"], atlas_guide_ids=["dofus_cawotte"],
                french_label_evidence=wrong_id,
            )
        missing_proof = deepcopy(evidence)
        missing_proof["status"] = "REVIEW_NAME_GAPS"
        with self.assertRaises(ValueError):
            prepare_ganymede_plan_input(
                self.report, ["character:1"], atlas_guide_ids=["dofus_cawotte"],
                french_label_evidence=missing_proof,
            )

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
