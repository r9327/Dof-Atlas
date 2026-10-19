from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    certified_payload_sha256, route_fingerprint, select_verified_replacement_path,
)


class GanymedeCutoverTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.guides = Path(temp.name) / "guides"
        self.drafts = self.guides / "replacement_drafts"
        self.drafts.mkdir(parents=True)
        self.entry = {"id": "dofus_cawotte", "category": "dofus"}
        self.old_guide = self.guides / "dofus_cawotte.json"
        self.old_guide.write_text('{"id":"dofus_cawotte","sections":[{"steps":[]}]}',
                                  encoding="utf-8")
        self.steps = [
            {
                "id": f"ganymede_2205_step_{n:04d}",
                "type": "info",
                "source_guide_id": 2205,
                "source_step_number": n,
                "original_prose_imported": False,
                "manual_completion_allowed": True,
                "verified_actions": [{
                    "kind": "quest_objective",
                    "text": f"Effectuer l'objectif Atlas numéro {n}",
                    "verified": True,
                    "evidence": [{"type": "doduda_quest_objective", "id": n}],
                }],
            }
            for n in (1, 2)
        ]
        self.payload = {
            "schema_version": 1, "id": "dofus_cawotte",
            "category": "dofus", "source_guide_id": 2205,
            "route_origin": "GANYMEDE_CONTINUOUS_STEP_ORDER",
            "replacement_status": "CERTIFIED_FOR_CUTOVER",
            "replacement_active": True,
            "completeness_status": "complete",
            "expected_source_step_count": 2,
            "playable_step_count": 2,
            "source_text_copied": False,
            "sections": [{"id": "ganymede_2205_continuous",
                          "steps": self.steps}],
        }
        self.manifest = {
            "schema_version": 1,
            "guides": {"dofus_cawotte": {
                "enabled": True, "status": "CERTIFIED_FOR_CUTOVER",
                "source_guide_id": 2205, "source_step_count": 2,
                "payload_sha256": certified_payload_sha256(self.payload),
                "fingerprint": route_fingerprint(2205, [
                    "ganymede_2205_step_0001", "ganymede_2205_step_0002",
                ]),
            }},
        }

    def save(self) -> None:
        (self.drafts / "dofus_cawotte.json").write_text(
            json.dumps(self.payload), encoding="utf-8"
        )
        (self.drafts / "cutover_manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8"
        )

    def test_without_explicit_cutover_manifest_always_keep_legacy(self) -> None:
        self.assertIsNone(select_verified_replacement_path(self.guides, self.entry))
        self.assertTrue(self.old_guide.exists())

    def test_individual_verified_cutover_selects_single_new_file(self) -> None:
        self.save()
        path = select_verified_replacement_path(self.guides, self.entry)
        self.assertEqual(path, self.drafts / "dofus_cawotte.json")
        self.assertTrue(self.old_guide.is_file())
        self.assertIsNone(select_verified_replacement_path(
            self.guides, {"id": "alignement_bonta", "category": "alignements"}
        ))

    def test_no_historical_or_legacy_migration_required(self) -> None:
        self.save()
        self.assertEqual(select_verified_replacement_path(self.guides, self.entry),
                         self.drafts / "dofus_cawotte.json")

    def test_trusted_source_cutover_without_human_objective_review(self) -> None:
        self.manifest["guides"]["dofus_cawotte"]["status"] = "TRUSTED_SOURCE_CUTOVER"
        self.payload["replacement_status"] = "TRUSTED_SOURCE_CUTOVER"
        self.manifest["guides"]["dofus_cawotte"]["payload_sha256"] = certified_payload_sha256(self.payload)
        self.save()
        self.assertEqual(select_verified_replacement_path(self.guides, self.entry),
                         self.drafts / "dofus_cawotte.json")

    def test_trusted_source_candidate_actions_without_manual_verification(self) -> None:
        self.manifest["guides"]["dofus_cawotte"]["status"] = "TRUSTED_SOURCE_CUTOVER"
        self.payload["replacement_status"] = "TRUSTED_SOURCE_CUTOVER"
        for step in self.steps:
            step["verified_actions"] = []
            step["source_action_candidates"] = [{"text": "Suivre le guide Ganymède"}]
        self.manifest["guides"]["dofus_cawotte"]["payload_sha256"] = certified_payload_sha256(self.payload)
        self.save()
        self.assertIsNotNone(select_verified_replacement_path(self.guides, self.entry))

    def test_trusted_source_empty_candidates_still_rejected(self) -> None:
        self.manifest["guides"]["dofus_cawotte"]["status"] = "TRUSTED_SOURCE_CUTOVER"
        self.payload["replacement_status"] = "TRUSTED_SOURCE_CUTOVER"
        for step in self.steps:
            step["verified_actions"] = []
            step["source_action_candidates"] = []
        self.manifest["guides"]["dofus_cawotte"]["payload_sha256"] = certified_payload_sha256(self.payload)
        self.save()
        self.assertIsNone(select_verified_replacement_path(self.guides, self.entry))

    def test_no_activation_from_unplayable_source_preview(self) -> None:
        self.payload["replacement_active"] = False
        self.payload["replacement_status"] = "DRAFT_NOT_PLAYABLE"
        self.payload["completeness_status"] = "draft"
        self.payload["playable_step_count"] = 0
        self.save()
        self.assertIsNone(select_verified_replacement_path(self.guides, self.entry))

    def test_every_step_must_have_verified_actions(self) -> None:
        self.steps[1]["verified_actions"] = []
        self.save()
        self.assertIsNone(select_verified_replacement_path(self.guides, self.entry))

    def test_every_step_must_have_exact_source_order(self) -> None:
        self.steps[1]["source_step_number"] = 3
        self.save()
        self.assertIsNone(select_verified_replacement_path(self.guides, self.entry))

    def test_no_cutover_with_invalid_route_fingerprint(self) -> None:
        self.manifest["guides"]["dofus_cawotte"]["fingerprint"] = "0" * 64
        self.save()
        self.assertIsNone(select_verified_replacement_path(self.guides, self.entry))

    def test_modified_verified_action_rejected_after_certification(self) -> None:
        # Step IDs and route fingerprint are unchanged; the signed action is not.
        self.steps[0]["verified_actions"][0]["text"] = "Autre objectif"
        self.save()
        self.assertIsNone(select_verified_replacement_path(self.guides, self.entry))

    def test_modified_action_evidence_rejected_after_certification(self) -> None:
        self.steps[0]["verified_actions"][0]["evidence"][0]["id"] = 999
        self.save()
        self.assertIsNone(select_verified_replacement_path(self.guides, self.entry))

    def test_unsigned_complete_guide_cannot_cut_over(self) -> None:
        del self.manifest["guides"]["dofus_cawotte"]["payload_sha256"]
        self.save()
        self.assertIsNone(select_verified_replacement_path(self.guides, self.entry))

    def test_untrusted_manifest_cannot_leave_guide_directory(self) -> None:
        self.entry["id"] = "../progress"
        self.save()
        self.assertIsNone(select_verified_replacement_path(self.guides, self.entry))

    def test_selection_never_modifies_original_or_progress(self) -> None:
        self.save()
        bytes_before = self.old_guide.read_bytes()
        self.assertIsNotNone(select_verified_replacement_path(self.guides, self.entry))
        self.assertEqual(self.old_guide.read_bytes(), bytes_before)
        self.assertFalse((self.guides / "progress").exists())

    def test_real_staged_dofus_drafts_are_not_selected(self) -> None:
        from app.constants import DATA_DIR
        guides = DATA_DIR / "encyclopedia" / "guides"
        self.assertIsNone(select_verified_replacement_path(
            guides, {"id": "dofus_cawotte", "category": "dofus"}
        ))


if __name__ == "__main__":
    unittest.main()
