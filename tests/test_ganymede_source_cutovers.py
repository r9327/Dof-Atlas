from __future__ import annotations

import json
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    certified_payload_sha256, route_fingerprint, select_verified_replacement_path,
)
from tools.build_ganymede_source_cutovers import (
    assert_reviewed_actions_match_source, prepare_source_cutover,
    retain_legacy_display_metadata,
)


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

    def test_legacy_display_metadata_survives_without_old_steps(self):
        route = prepare_source_cutover(fixture())
        old = {"id": "dofus_cawotte", "category": "dofus",
               "reward_item_id": 361, "illustration_item_id": 361,
               "recommended_level_min": 80, "linked_achievement_ids": [123],
               "sections": [{"steps": [{"id": "old_quest", "type": "quest"}]}]}
        decorated = retain_legacy_display_metadata(route, old)
        self.assertEqual(decorated["reward_item_id"], 361)
        self.assertEqual(decorated["linked_achievement_ids"], [123])
        self.assertEqual(decorated["recommended_level_min"], 80)
        self.assertEqual(decorated["sections"][0]["steps"][0]["id"],
                         "ganymede_2205_step_0001")
        self.assertNotIn("parts", decorated)

    def test_legacy_metadata_cannot_be_taken_from_another_guide(self):
        route = prepare_source_cutover(fixture())
        with self.assertRaisesRegex(ValueError, "different local guide"):
            retain_legacy_display_metadata(route, {"id": "dofus_emeraude",
                                                   "category": "dofus"})

    def test_signed_manual_route_must_match_source_review_actions(self):
        source = fixture()
        reviewed = deepcopy(source)
        self.assertIsNone(assert_reviewed_actions_match_source(reviewed, source))
        reviewed["sections"][0]["steps"][0]["source_action_candidates"][0]["label"] = "Combattre un monstre inventé"
        with self.assertRaisesRegex(ValueError, "Source action evidence drift"):
            assert_reviewed_actions_match_source(reviewed, source)

    def test_unreviewed_action_injection_or_reordered_actions_is_rejected(self):
        source = fixture()
        reviewed = deepcopy(source)
        reviewed["sections"][0]["steps"][0]["source_action_candidates"].append(
            {"kind": "combat", "label": "Fausse obligation"},
        )
        with self.assertRaisesRegex(ValueError, "Source action evidence drift"):
            assert_reviewed_actions_match_source(reviewed, source)

    def test_local_review_status_must_agree_with_audited_source(self):
        source = fixture()
        reviewed = deepcopy(source)
        reviewed["sections"][0]["steps"][0]["source_action_review_status"] = "REVIEW_SOURCE_ACTION"
        with self.assertRaisesRegex(ValueError, "Source action evidence drift"):
            assert_reviewed_actions_match_source(reviewed, source)

    def test_unknown_action_kind_cannot_be_signed(self):
        candidate = fixture()
        candidate["sections"][0]["steps"][0]["source_action_candidates"][0]["kind"] = "unverified_new_kind"
        with self.assertRaisesRegex(ValueError, "Malformed action"):
            prepare_source_cutover(candidate)

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
            self.assertIsNone(select_verified_replacement_path(root, row))
            self.assertEqual(select_verified_replacement_path(
                root, row, allow_source_manual=True), active / "dofus_cawotte.json")
            route["sections"][0]["steps"][0]["content"] = "Altéré"
            (active / "dofus_cawotte.json").write_text(json.dumps(route), encoding="utf-8")
            self.assertIsNone(select_verified_replacement_path(
                root, row, allow_source_manual=True))

    def test_no_manifest_no_cutover(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(select_verified_replacement_path(
                Path(tmp), {"id": "dofus_cawotte", "category": "dofus"}))


if __name__ == "__main__":
    unittest.main()
