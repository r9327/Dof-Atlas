"""Make source-aligned Dokoko review drafts preserve the reward/optional boundary."""
from __future__ import annotations
import json
import unittest
from pathlib import Path
from tools.audit_ganymede_master_refs import ROOT
from tools.build_ganymede_replacement_previews import build_dofus_replacement_previews

GUIDES = Path("data/encyclopedia/guides")
class DokokoDraftParityTests(unittest.TestCase):
    def test_dokoko_preview_stays_not_playable_and_tracks_all_actions(self):
        report=build_dofus_replacement_previews(ROOT)
        self.assertEqual(report["status"],"PREVIEWS_READY_NOT_PLAYABLE", report["issues"])
        generated=report["previews"]["dokoko"]
        saved=json.loads((ROOT/GUIDES/"replacement_drafts"/"dokoko.json").read_text(encoding="utf-8"))
        self.assertEqual(generated["source_action_candidate_steps"],49)
        self.assertEqual(generated["source_action_candidate_actions"],148)
        self.assertEqual(saved["source_action_candidate_steps"],49)
        self.assertEqual(saved["source_action_candidate_actions"],148)
        self.assertEqual(saved["sections"][0]["steps"],generated["sections"][0]["steps"])
        self.assertEqual(saved["playable_step_count"],0)
        self.assertFalse(saved["replacement_active"])
        self.assertFalse(saved["legacy_manual_steps_migration_verified"])
        self.assertEqual(len(saved["sections"][0]["steps"]),49)
        for index,step in enumerate(saved["sections"][0]["steps"]):
            self.assertEqual(step["optional"],index>=32)
            self.assertEqual(step["route_phase"],
                             "OPTIONAL_ISLAND_COMPLETION" if index>=32
                             else "DOKOKO_REWARD_PATH")
            self.assertEqual(step["source_action_candidate_status"],"REVIEW_SOURCE_ACTION")
            self.assertTrue(step["source_action_candidates"])
            self.assertEqual(step["verified_actions"],[])
            self.assertFalse(step["manual_completion_allowed"])
            self.assertFalse(step["auto_completion_allowed"])

    def test_reward_is_at_step_32_not_at_optional_stages(self):
        preview=build_dofus_replacement_previews(ROOT)["previews"]["dokoko"]
        steps=preview["sections"][0]["steps"]
        self.assertTrue(any(a.get("kind")=="goal_reward" and
                            a.get("object_id")==17078 for a in steps[31]["source_action_candidates"]))
        self.assertFalse(steps[31]["optional"])
        self.assertTrue(steps[32]["optional"])
        self.assertEqual(steps[31]["id"],"ganymede_2208_step_0032")
        self.assertEqual(steps[32]["id"],"ganymede_2208_step_0033")

if __name__=="__main__":
    unittest.main()
