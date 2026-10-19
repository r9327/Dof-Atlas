from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    certified_payload_sha256, route_fingerprint,
)
from tools.build_ganymede_trusted_cutovers import prepare_trusted_cutover


class TrustedCutoverBuilderTests(unittest.TestCase):
    def setUp(self):
        self.preview = {
            "schema_version": 1,
            "id": "dofus_cawotte",
            "category": "dofus",
            "source_guide_id": 2205,
            "route_origin": "GANYMEDE_CONTINUOUS_STEP_ORDER",
            "source_text_copied": False,
            "sections": [{
                "id": "ganymede_2205_continuous",
                "steps": [{
                    "id": "ganymede_2205_step_0001",
                    "source_guide_id": 2205,
                    "source_step_number": 1,
                    "manual_completion_allowed": False,
                    "original_prose_imported": False,
                    "verified_actions": [],
                    "source_action_candidates": [{
                        "kind": "prepare_object",
                        "label": "Préparer une Cawotte",
                        "object_id": 361,
                        "quantity": 1,
                    }],
                }],
            }],
        }

    def test_converts_actions_without_losing_ids_or_quantities(self):
        result = prepare_trusted_cutover(self.preview)
        step = result["sections"][0]["steps"][0]
        self.assertTrue(step["manual_completion_allowed"])
        self.assertEqual(step["content"], "Préparer une Cawotte")
        self.assertEqual(step["source_action_candidates"][0]["object_id"], 361)
        self.assertEqual(step["source_action_candidates"][0]["quantity"], 1)
        self.assertEqual(result["playable_step_count"], 1)
        self.assertFalse(self.preview["sections"][0]["steps"][0]["manual_completion_allowed"])
        self.assertEqual(len(certified_payload_sha256(result)), 64)
        self.assertEqual(len(route_fingerprint(2205, [step["id"]])), 64)

    def test_missing_actions_never_activates(self):
        self.preview["sections"][0]["steps"][0]["source_action_candidates"] = []
        with self.assertRaises(ValueError):
            prepare_trusted_cutover(self.preview)

    def test_empty_action_label_never_activates(self):
        self.preview["sections"][0]["steps"][0]["source_action_candidates"][0]["label"] = " "
        with self.assertRaises(ValueError):
            prepare_trusted_cutover(self.preview)


if __name__ == "__main__":
    unittest.main()
