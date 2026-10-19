"""Every mapped Dofus has an indexed step-by-step, reversible *review* draft.

This proves ordered provenance and complete hint coverage, not gameplay parity,
DofusDB objective equivalence, migration, or safe activation.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.audit_ganymede_master_refs import ROOT
from tools.audit_ganymede_replacement_readiness import audit_ganymede_replacement_readiness
from tools.audit_ganymede_step_actions import audit_action_candidates
from tools.build_ganymede_replacement_previews import build_dofus_replacement_previews

D = Path("data/encyclopedia/guides")
MANUALLY_REVIEWED = {2205, 2208, 2211, 2247, 2248, 2260, 2271, 2276, 2285}

class AllDofusReviewDraftParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = build_dofus_replacement_previews(ROOT)
        cls.readiness = audit_ganymede_replacement_readiness(ROOT)

    def test_all_twenty_mapped_guides_have_source_candidates(self) -> None:
        self.assertEqual(self.report["status"], "PREVIEWS_READY_NOT_PLAYABLE",
                         self.report["issues"])
        self.assertEqual(len(self.report["previews"]), 20)
        self.assertEqual(self.report["total_source_steps_in_drafts"], 1694)
        self.assertEqual(self.readiness["source_action_reviewed_steps"], 338)
        self.assertEqual(self.readiness["source_auto_extracted_hint_steps"], 1356)
        self.assertEqual(self.readiness["ready_to_replace"], 0)
        self.assertFalse(self.readiness["replacement_activated"])
        self.assertEqual(set(self.report["dofus_guides_without_direct_ganymede"]),
                         {"dokille", "dofoozbz"})

    def test_candidate_ids_draft_parity_and_no_progress_activation(self) -> None:
        for atlas_id, produced in self.report["previews"].items():
            with self.subTest(guide=atlas_id):
                source_id = produced["source_guide_id"]
                candidate = D / f"ganymede_{source_id}_action_candidates.json"
                self.assertTrue((ROOT / candidate).is_file())
                evidence = json.loads((ROOT / candidate).read_text(encoding="utf-8"))
                raw = audit_action_candidates(ROOT, candidate)
                expected = ("REVIEW_ACTION_CANDIDATES_ONLY"
                            if source_id in MANUALLY_REVIEWED
                            else "AUTO_EXTRACTED_NEEDS_MANUAL_REVIEW")
                self.assertEqual(raw["status"], expected, raw["issues"])
                self.assertEqual(raw["source_steps"], produced["expected_source_step_count"])
                self.assertEqual(len(evidence["steps"]), produced["expected_source_step_count"])
                self.assertEqual(raw["remaining_steps"], 0)
                self.assertFalse(raw["ready_to_replace"])
                self.assertEqual(raw["certified_actions"], 0)
                self.assertFalse(evidence["ready_to_replace"])

                stored = json.loads(
                    (ROOT / D / "replacement_drafts" / f"{atlas_id}.json")
                    .read_text(encoding="utf-8")
                )
                self.assertEqual(stored, produced)
                self.assertFalse(stored["replacement_active"])
                self.assertFalse(stored["legacy_manual_steps_migration_verified"])
                self.assertEqual(stored["playable_step_count"], 0)
                actions_total = sum(len(step["actions"]) for step in evidence["steps"])
                self.assertEqual(stored["source_action_candidate_steps"],
                                 stored["expected_source_step_count"])
                self.assertEqual(stored["source_action_candidate_actions"], actions_total)

                for index, (candidate_step, view_step) in enumerate(
                    zip(evidence["steps"], stored["sections"][0]["steps"]), 1
                ):
                    step_id = f"ganymede_{source_id}_step_{index:04d}"
                    self.assertEqual(candidate_step["stable_step_id"], step_id)
                    self.assertEqual(view_step["id"], step_id)
                    self.assertEqual(candidate_step["source_step_number"], index)
                    self.assertEqual(view_step["source_action_candidates"],
                                     candidate_step["actions"])
                    self.assertTrue(candidate_step["actions"])
                    self.assertEqual(view_step["verified_actions"], [])
                    self.assertFalse(view_step["manual_completion_allowed"])
                    self.assertFalse(view_step["auto_completion_allowed"])
                    if source_id not in MANUALLY_REVIEWED:
                        self.assertEqual(view_step["source_action_candidate_status"],
                                         "AUTO_EXTRACTED_NEEDS_REVIEW")
                        self.assertEqual(view_step["action_reconstruction_status"],
                                         "AUTO_EXTRACTED_ACTION_NOT_REVIEWED")

if __name__ == "__main__":
    unittest.main()
