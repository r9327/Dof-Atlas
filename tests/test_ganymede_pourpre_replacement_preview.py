"""Pourpre replacement draft must match source-action review, without activation."""
from __future__ import annotations
import json
import unittest
from pathlib import Path
from tools.audit_ganymede_master_refs import ROOT
from tools.build_ganymede_replacement_previews import build_dofus_replacement_previews
DIRECTORY=Path("data/encyclopedia/guides")
class PourpreDraftTests(unittest.TestCase):
    def test_preview_45_steps_and_175_actions(self):
        report=build_dofus_replacement_previews(ROOT)
        self.assertEqual(report["status"],"PREVIEWS_READY_NOT_PLAYABLE",report["issues"])
        current=report["previews"]["dofus_pourpre"]
        stored=json.loads((ROOT/DIRECTORY/"replacement_drafts"/"dofus_pourpre.json").read_text(encoding="utf-8"))
        self.assertEqual(current["source_action_candidate_steps"],45)
        self.assertEqual(current["source_action_candidate_actions"],175)
        self.assertEqual(stored["sections"][0]["steps"],current["sections"][0]["steps"])
        self.assertEqual(stored["source_action_candidate_steps"],45)
        self.assertEqual(stored["source_action_candidate_actions"],175)
        self.assertEqual(stored["playable_step_count"],0)
        self.assertFalse(stored["replacement_active"])
        self.assertFalse(stored["legacy_manual_steps_migration_verified"])
        for s in stored["sections"][0]["steps"]:
            self.assertEqual(s["source_action_candidate_status"],"REVIEW_SOURCE_ACTION")
            self.assertTrue(s["source_action_candidates"])
            self.assertEqual(s["verified_actions"],[])
            self.assertFalse(s["manual_completion_allowed"])
            self.assertFalse(s["auto_completion_allowed"])

    def test_external_side_quests_remain_reviewed_not_direct_completion(self):
        report=build_dofus_replacement_previews(ROOT)
        steps=report["previews"]["dofus_pourpre"]["sections"][0]["steps"]
        side=steps[14]["source_action_candidates"][1]
        self.assertEqual(side["quest_id"],1527)
        self.assertEqual(side["relation"],"side_required_for_progression")
        daily=next(a for a in steps[19]["source_action_candidates"] if a.get("quest_id")==2538)
        self.assertEqual(daily["relation"],"repeatable_support")
        self.assertFalse(steps[36]["manual_completion_allowed"])
if __name__=="__main__":
    unittest.main()
