"""Ganymède cutover gate exposes review coverage but cannot activate drafts."""
from __future__ import annotations

import unittest
from pathlib import Path

from tools.audit_ganymede_replacement_readiness import (
    audit_ganymede_replacement_readiness,
)

ROOT = Path(__file__).resolve().parents[1]


class ActionCoverageReadinessTests(unittest.TestCase):
    def test_emeraude_candidates_are_visible_but_never_certified(self):
        result = audit_ganymede_replacement_readiness(ROOT)
        self.assertEqual(result["status"], "BLOCKED_PENDING_PLAYABLE_ACTIONS",
                         result["issues"])
        self.assertEqual(result["dofus_guides"], 22)
        self.assertEqual(result["dofus_guides_with_direct_source_mapping"], 20)
        self.assertEqual(result["ready_to_replace"], 0)
        self.assertFalse(result["replacement_activated"])
        emeraude = next(row for row in result["guide_reports"]
                       if row["atlas_guide_id"] == "dofus_emeraude")
        state = emeraude["source_guides"][0]
        self.assertEqual(state["ganymede_guide_id"], 2211)
        self.assertEqual(state["expected_source_step_count"], 52)
        self.assertEqual(state["reviewed_action_candidate_steps"], 52)
        self.assertEqual(state["action_candidate_evidence_status"],
                         "REVIEW_ACTION_CANDIDATES_ONLY")
        self.assertEqual(state["playable_actions_reconstructed"], 0)
        self.assertEqual(state["source_step_actions_verified"], 0)
        self.assertFalse(state["canonical_objectives_verified"])
        self.assertFalse(emeraude["ready_to_replace"])
        self.assertIn("PROGRESS_MIGRATION_NOT_VERIFIED", emeraude["blockers"])

    def test_unmatched_dofus_kept(self):
        result = audit_ganymede_replacement_readiness(ROOT)
        self.assertEqual(
            set(result["dofus_guides_without_direct_source_mapping"]),
            {"dokille", "dofoozbz"})


    def test_human_review_and_auto_hints_are_separate(self):
        result = audit_ganymede_replacement_readiness(ROOT)
        self.assertEqual(result["status"], "BLOCKED_PENDING_PLAYABLE_ACTIONS",
                         result["issues"])
        self.assertEqual(result["source_action_reviewed_steps"], 338)
        self.assertEqual(result["source_auto_extracted_hint_steps"], 55)
        nightmare = next(row for row in result["guide_reports"]
                         if row["atlas_guide_id"] == "dofus_du_cauchemar")
        evidence = nightmare["source_guides"][0]
        self.assertEqual(evidence["reviewed_action_candidate_steps"], 0)
        self.assertEqual(evidence["auto_extracted_candidate_steps"], 55)
        self.assertFalse(nightmare["ready_to_replace"])
        self.assertEqual(result["ready_to_replace"], 0)


if __name__ == "__main__":
    unittest.main()
