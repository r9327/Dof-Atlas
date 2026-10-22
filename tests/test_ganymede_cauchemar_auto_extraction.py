"""Automated Nightmare source hints are evidence only, never executable."""
from __future__ import annotations
import json,unittest
from pathlib import Path
from tools.audit_ganymede_master_refs import ROOT
from tools.audit_ganymede_step_actions import audit_action_candidates
from tools.build_ganymede_replacement_previews import build_dofus_replacement_previews
D=Path("data/encyclopedia/guides")
class NightmareExtractedTests(unittest.TestCase):
    def test_55_auto_steps_not_playable(self):
        result=audit_action_candidates(ROOT,D/"ganymede_2283_action_candidates.json")
        self.assertEqual(result["status"],"AUTO_EXTRACTED_NEEDS_MANUAL_REVIEW",result["issues"])
        self.assertEqual(result["source_steps"],55)
        self.assertEqual(result["auto_extracted_steps"],55)
        self.assertEqual(result["reviewed_steps"],0)
        built=build_dofus_replacement_previews(ROOT)
        self.assertEqual(built["status"],"PREVIEWS_READY_NOT_PLAYABLE",built["issues"])
        draft=json.loads((ROOT/D/"replacement_drafts"/"dofus_du_cauchemar.json").read_text(encoding="utf-8"))
        self.assertEqual(draft["sections"][0]["steps"],built["previews"]["dofus_du_cauchemar"]["sections"][0]["steps"])
        self.assertEqual(draft["source_action_candidate_steps"],55)
        self.assertEqual(draft["factual_action_reviewed_step_count"],0)
        self.assertFalse(draft["replacement_active"])
        self.assertTrue(all(s["verified_actions"]==[] and not s["manual_completion_allowed"] and
                            not s["auto_completion_allowed"] for s in draft["sections"][0]["steps"]))
if __name__=="__main__":
    unittest.main()
