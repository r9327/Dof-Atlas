"""All Ganymède source steps remain factual, ordered, and unplayable."""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.build_ganymede_all_guide_stages import (
    attach_names, collect_public_stage_refs,
)


class GanymedeAllGuidesSourceTests(unittest.TestCase):
    def test_public_inventory_has_95_guides_and_7705_ordered_stages(self):
        root = Path(__file__).resolve().parents[1]
        guides, refs = collect_public_stage_refs(root)
        self.assertEqual(len(guides), 95)
        self.assertEqual(sum(g["source_step_count"] for g in guides), 7705)
        self.assertTrue(all(not g["playable"] for g in guides))
        for g in guides:
            self.assertEqual(
                [s["stable_step_id"] for s in g["steps"]],
                [f"ganymede_{g['source_guide_id']}_step_{i:04d}"
                 for i in range(1, g["source_step_count"] + 1)],
            )
            self.assertTrue(all(not s["auto_completion_allowed"]
                                and not s["has_verified_action"]
                                for s in g["steps"]))
        self.assertGreater(len(refs["quest"]), 0)
        self.assertGreater(len(refs["object"]), 0)

    def test_names_are_reference_hints_not_inferred_quest_actions(self):
        guides = [{
            "source_guide_id": 2205,
            "source_guide_url": "https://ganymede-app.com/guides/2205",
            "source_title_original": "Cawotte",
            "source_step_count": 2,
            "playable": False,
            "steps": [{
                "stable_step_id": f"ganymede_2205_step_{i:04d}",
                "source_step_number": i,
                "source_page": 1,
                "observed_coordinates": [],
                "linked_guide_ids": [],
                "external_dofusdb_ids": {
                    "quest": [100], "object": [361],
                    "monster": [], "dungeon": [],
                },
                "has_verified_action": False,
                "auto_completion_allowed": False,
            } for i in (1, 2)],
        }]
        original = guides[0]["steps"][0]["external_dofusdb_ids"]["object"]
        report = attach_names(guides, {
            ("object", 361): "Cawotte",
            ("quest", 100): "Sauvegarder l'espèce",
        })
        self.assertEqual(report["source_guides"], 1)
        self.assertEqual(report["source_steps"], 2)
        self.assertEqual(report["reference_occurrences"], 4)
        self.assertEqual(report["localized_reference_occurrences"], 4)
        self.assertEqual(report["unresolved_reference_occurrences"], 0)
        self.assertEqual(report["canonical_objectives_verified"], 0)
        self.assertEqual(report["playable_guides"], 0)
        self.assertFalse(report["ready_to_replace"])
        step = report["guides"][0]["steps"][0]
        self.assertEqual(step["source_references"]["object"][0]["localized_name_fr"],
                         "Cawotte")
        self.assertFalse(step["source_references"]["quest"][0][
            "canonical_objective_verified"])
        self.assertEqual(original, [361])

    def test_unknown_names_remain_explicitly_missing(self):
        sample = [{
            "source_guide_id": 1, "source_step_count": 1, "playable": False,
            "steps": [{"source_step_number": 1,
                       "external_dofusdb_ids": {
                           "quest": [41], "object": [],
                           "monster": [], "dungeon": [],
                       }}],
        }]
        report = attach_names(sample, {})
        self.assertEqual(report["unresolved_reference_occurrences"], 1)
        self.assertIsNone(report["guides"][0]["steps"][0][
            "source_references"]["quest"][0]["localized_name_fr"])


if __name__ == "__main__":
    unittest.main()
