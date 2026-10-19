from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    certified_payload_sha256, route_fingerprint, select_verified_replacement_path,
)
from tools.build_ganymede_trusted_cutovers import prepare_trusted_cutover, write_trusted_cutovers


class TrustedCutoverBuilderTests(unittest.TestCase):
    def setUp(self):
        self.preview = {
            "schema_version": 1,
            "id": "dofus_cawotte",
            "category": "dofus",
            "source_guide_id": 2205,
            "expected_source_step_count": 1,
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

    def test_generated_manifest_selects_trusted_route(self):
        payload = prepare_trusted_cutover(self.preview)
        source_id = payload["source_guide_id"]
        step_ids = [step["id"] for step in payload["sections"][0]["steps"]]
        result = {
            "payloads": {"dofus_cawotte": payload},
            "manifest": {"schema_version": 1, "guides": {"dofus_cawotte": {
                "enabled": True,
                "status": "TRUSTED_SOURCE_CUTOVER",
                "source_guide_id": source_id,
                "source_step_count": len(step_ids),
                "fingerprint": route_fingerprint(source_id, step_ids),
                "payload_sha256": certified_payload_sha256(payload),
            }}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            guides = Path(tmp) / "guides"
            output = guides / "replacement_drafts"
            write_trusted_cutovers(result, output)
            self.assertEqual(
                select_verified_replacement_path(guides, {"id": "dofus_cawotte", "category": "dofus"}),
                output / "dofus_cawotte.json",
            )

    def test_source_count_mismatch_rejected(self):
        self.preview["expected_source_step_count"] = 2
        with self.assertRaises(ValueError):
            prepare_trusted_cutover(self.preview)

    def test_unstable_step_order_rejected(self):
        self.preview["sections"][0]["steps"][0]["source_step_number"] = 2
        with self.assertRaises(ValueError):
            prepare_trusted_cutover(self.preview)

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
