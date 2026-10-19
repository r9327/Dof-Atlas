"""Source proposals become scoped planning evidence, never shopping orders."""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.audit_ganymede_stage_needs import audit_stage_needs, stage_needs


def candidate() -> dict:
    return {
        "atlas_guide_id": "dofus_test", "source_guide_id": 9001,
        "source_step_count": 3, "ready_to_replace": False,
        "certified_actions": 0, "steps": [
            {
                "source_step_number": 1,
                "stable_step_id": "ganymede_9001_step_0001",
                "review_status": "REVIEW_SOURCE_ACTION",
                "quest_objectives_verified": False,
                "actions": [
                    {"kind": "prepare_object", "object_id": 42, "quantity": 5,
                     "can_obtain_on_route": True, "needed_at_source_step": 3},
                    {"kind": "optional_preparation", "object_ids": [42, 43],
                     "quantity": 2, "conditional": "alternate_route"},
                    {"kind": "guide_dependency", "guide_id": 2211},
                    {"kind": "quest_prerequisite", "quest_id": 300,
                     "alternative_group": "either_of_two"},
                ],
            },
            {
                "source_step_number": 2,
                "stable_step_id": "ganymede_9001_step_0002",
                "review_status": "AUTO_EXTRACTED_NEEDS_REVIEW",
                "quest_objectives_verified": False,
                "actions": [{"kind": "talk", "label": "Talk"}],
            },
            {
                "source_step_number": 3,
                "stable_step_id": "ganymede_9001_step_0003",
                "review_status": "REVIEW_SOURCE_ACTION",
                "quest_objectives_verified": False,
                "actions": [
                    {"kind": "check_object", "object_id": 42,
                     "quantity_per_character": 1, "optional_branch": True},
                ],
            },
        ],
    }


class GanymedeStageNeedsTests(unittest.TestCase):
    def test_needs_are_kept_in_source_order_with_future_due_step(self):
        doc = stage_needs(candidate())
        self.assertEqual(doc["source_step_count"], 3)
        self.assertEqual(
            [s["source_step_number"] for s in doc["stages_with_requirements"]],
            [1, 3],
        )
        first = doc["stages_with_requirements"][0]
        self.assertEqual(first["needs"][0]["needed_at_source_step"], 3)
        self.assertEqual(first["needs"][0]["quantity_candidate"], 5)
        self.assertIs(first["needs"][0]["obtainable_on_route_candidate"], True)
        self.assertIsNone(first["needs"][0]["owned_or_prepared_by_any_character"])
        self.assertFalse(first["needs"][0]["canonical_requirement_verified"])
        self.assertEqual(first["prerequisites"][0]["ganymede_prerequisite_guide_id"], 2211)

    def test_collection_window_and_prior_stage_provenance_survive_export(self):
        data = candidate()
        data["steps"][0]["actions"][0]["collection_window_end"] = 2
        data["steps"][2]["actions"][0]["references_previous_stage"] = 1
        result = stage_needs(data)
        initial = result["stages_with_requirements"][0]["needs"][0]
        later = result["stages_with_requirements"][1]["needs"][0]
        self.assertEqual(initial["needed_at_source_step"], 3)
        self.assertEqual(initial["collection_window_end_candidate"], 2)
        self.assertIsNone(initial["references_previous_stage_candidate"])
        self.assertEqual(later["references_previous_stage_candidate"], 1)
        self.assertIsNone(later["collection_window_end_candidate"])

    def test_encounters_and_in_route_drops_are_not_shopping_orders(self):
        data = candidate()
        data["steps"][1]["actions"] = [
            {"kind": "combat", "label": "Combattre ensemble",
             "monster_id": 44, "group_fight": True, "participants_min": 3},
            {"kind": "dungeon", "label": "Entrer au donjon", "dungeon_id": 70},
            {"kind": "optional_capture", "label": "Capture facultative",
             "monster_id": 44, "conditional": "guide_ocre"},
            {"kind": "group_mechanic", "label": "Activer trois dalles",
             "participants_min": 3},
        ]
        data["steps"][2]["actions"].extend([
            {"kind": "drop_object", "label": "Obtenir la ressource",
             "object_id": 81, "quantity": 2},
            {"kind": "collect_object", "label": "Récolter la ressource",
             "object_id": 82, "quantity": 1},
            {"kind": "optional_drop", "label": "Drop annexe",
             "object_id": 83},
        ])
        stages = stage_needs(data)["stages_with_requirements"]
        self.assertEqual([s["source_step_number"] for s in stages], [1, 2, 3])
        encounters = stages[1]["encounters"]
        self.assertEqual([e["kind"] for e in encounters],
                         ["combat", "dungeon", "optional_capture", "group_mechanic"])
        self.assertEqual(encounters[0]["participants_min_candidate"], 3)
        self.assertEqual(encounters[0]["external_dofusdb_monster_id"], 44)
        self.assertFalse(encounters[0]["canonical_requirement_verified"])
        self.assertIsNone(encounters[0]["character_completion_known"])
        self.assertTrue(encounters[2]["optional"])
        self.assertEqual(encounters[2]["conditional_candidate"], "guide_ocre")
        self.assertFalse(encounters[3]["optional"])
        drops = stages[2]["needs"][1:]
        self.assertEqual([n["acquisition_mode_candidate"] for n in drops],
                         ["drop_object", "collect_object", "optional_drop"])
        self.assertTrue(all(n["obtainable_on_route_candidate"] is True for n in drops))
        self.assertTrue(drops[-1]["optional"])
        self.assertFalse(drops[0]["canonical_requirement_verified"])
        self.assertIsNone(drops[0]["owned_or_prepared_by_any_character"])
        self.assertEqual(drops[0]["source_action_label"], "Obtenir la ressource")

    def test_optional_or_alternative_must_not_become_mandatory_stock(self):
        doc = stage_needs(candidate())
        first = doc["stages_with_requirements"][0]
        self.assertEqual(first["needs"][1]["external_dofusdb_object_ids"], [42, 43])
        self.assertTrue(first["needs"][1]["optional"])
        self.assertTrue(first["prerequisites"][1]["optional"])
        last = doc["stages_with_requirements"][1]["needs"][0]
        self.assertTrue(last["optional"])
        self.assertEqual(last["quantity_per_character_candidate"], 1)

    def test_repeated_item_occurrences_are_not_deduplicated_as_progress(self):
        doc = stage_needs(candidate())
        rows = [need for stage in doc["stages_with_requirements"]
                for need in stage["needs"] if 42 in need["external_dofusdb_object_ids"]]
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["canonical_requirement_verified"] is False
                            for r in rows))

    def test_false_certification_and_missing_stages_are_rejected(self):
        doc = candidate()
        doc["ready_to_replace"] = True
        with self.assertRaises(ValueError):
            stage_needs(doc)
        doc = candidate()
        doc["steps"][1]["stable_step_id"] = "ganymede_9001_step_0001"
        with self.assertRaises(ValueError):
            stage_needs(doc)
        doc = candidate()
        doc["steps"].pop()
        with self.assertRaises(ValueError):
            stage_needs(doc)

    def test_all_20_source_guides_report_unverified_needs(self):
        report = audit_stage_needs(Path(__file__).resolve().parents[1])
        self.assertEqual(
            report["status"], "REVIEW_ONLY_NOT_READY_FOR_OPTIMIZATION",
            report["issues"],
        )
        self.assertEqual(report["source_candidate_guides"], 20)
        self.assertEqual(report["source_stages"], 1694)
        self.assertEqual(report["canonical_requirements_certified"], 0)
        self.assertIs(report["stock_assumed"], False)
        self.assertIs(report["participants_assumed"], False)


if __name__ == "__main__":
    unittest.main()
