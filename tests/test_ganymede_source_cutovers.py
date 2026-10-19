from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    certified_payload_sha256, route_fingerprint, select_verified_replacement_path,
)
from tools.build_ganymede_source_cutovers import prepare_source_cutover


def fixture():
    return {"schema_version": 1, "id": "dofus_cawotte", "category": "dofus",
            "source_guide_id": 2205, "expected_source_step_count": 1,
            "route_origin": "GANYMEDE_CONTINUOUS_STEP_ORDER",
            "source_text_copied": False, "guide_progress_id_unchanged": True,
            "source_link_snapshot": "ganymede_cawotte_observed_links.json",
            "sections": [{"id": "ganymede_2205_continuous", "steps": [{
                "id": "ganymede_2205_step_0001", "source_guide_id": 2205,
                "source_step_number": 1, "original_prose_imported": False,
                "verified_actions": [],
                "atlas_quest_candidates": [{"quest_id": 827, "atlas_occurrences": []}],
                "external_dofusdb_ids": {"quest": [827], "dungeon": [], "object": [], "monster": []},
                "source_action_review_status": "AUTO_EXTRACTED_NEEDS_REVIEW",
                "source_action_candidates": [{"kind": "move", "label": "Aller à [25,-4]"}],
            }]}]}


class SourceCutoverTests(unittest.TestCase):
    def test_manual_steps_cannot_claim_canonical_actions(self):
        route = prepare_source_cutover(fixture())
        step = route["sections"][0]["steps"][0]
        self.assertTrue(step["manual_completion_allowed"])
        self.assertFalse(step["auto_completion_allowed"])
        self.assertFalse(route["canonical_objectives_certified"])
        self.assertFalse(route["legacy_manual_steps_migration_verified"])
        self.assertEqual(step["content"], "Aller à [25,-4]")
        self.assertNotIn("atlas_quest_candidates", step)
        self.assertEqual(step["external_dofusdb_ids"]["quest"], [827])

    def test_empty_action_rejected(self):
        candidate = fixture()
        candidate["sections"][0]["steps"][0]["source_action_candidates"] = []
        with self.assertRaisesRegex(ValueError, "Missing source action"):
            prepare_source_cutover(candidate)

    def test_manifest_hash_and_step_order_are_enforced(self):
        route = prepare_source_cutover(fixture())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / "replacement_drafts" / "cutovers"
            active.mkdir(parents=True)
            (active / "dofus_cawotte.json").write_text(json.dumps(route), encoding="utf-8")
            declaration = {"enabled": True, "status": "TRUSTED_SOURCE_STEPS",
                           "source_guide_id": 2205, "source_step_count": 1,
                           "fingerprint": route_fingerprint(2205, ["ganymede_2205_step_0001"]),
                           "payload_sha256": certified_payload_sha256(route)}
            (active / "cutover_manifest.json").write_text(
                json.dumps({"schema_version": 1, "guides": {"dofus_cawotte": declaration}}),
                encoding="utf-8")
            row = {"id": "dofus_cawotte", "category": "dofus"}
            self.assertEqual(select_verified_replacement_path(root, row),
                             active / "dofus_cawotte.json")
            route["sections"][0]["steps"][0]["content"] = "Altéré"
            (active / "dofus_cawotte.json").write_text(json.dumps(route), encoding="utf-8")
            self.assertIsNone(select_verified_replacement_path(root, row))

    def test_no_manifest_no_cutover(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(select_verified_replacement_path(
                Path(tmp), {"id": "dofus_cawotte", "category": "dofus"}))


if __name__ == "__main__":
    unittest.main()
