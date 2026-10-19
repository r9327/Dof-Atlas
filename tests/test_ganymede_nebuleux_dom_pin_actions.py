"""Source-derived Nebuleux and Dom de Pin stage candidates remain gated drafts."""
from __future__ import annotations
import json
import unittest
from pathlib import Path
from tools.audit_ganymede_master_refs import ROOT
from tools.audit_ganymede_step_actions import audit_action_candidates
from tools.build_ganymede_replacement_previews import build_dofus_replacement_previews
DIRECTORY=Path("data/encyclopedia/guides")
class TwoShortDofusGuideTests(unittest.TestCase):
    def test_source_crosswalk_draft_parity(self):
        report=build_dofus_replacement_previews(ROOT)
        self.assertEqual(report["status"],"PREVIEWS_READY_NOT_PLAYABLE",report["issues"])
        for gid,name,count,action_count in [(2247,"dofus_nebuleux",6,28),(2285,"dofus_dom_de_pin",4,18)]:
            with self.subTest(guide=name):
                check=audit_action_candidates(ROOT,DIRECTORY/f"ganymede_{gid}_action_candidates.json")
                self.assertEqual(check["status"],"REVIEW_ACTION_CANDIDATES_ONLY",check["issues"])
                self.assertEqual(check["reviewed_steps"],count)
                saved=json.loads((ROOT/DIRECTORY/"replacement_drafts"/f"{name}.json").read_text(encoding="utf-8"))
                produced=report["previews"][name]
                self.assertEqual(produced["source_action_candidate_steps"],count)
                self.assertEqual(produced["source_action_candidate_actions"],action_count)
                self.assertEqual(saved["sections"][0]["steps"],produced["sections"][0]["steps"])
                self.assertEqual(saved["source_action_candidate_actions"],action_count)
                self.assertFalse(saved["replacement_active"])
                self.assertEqual(saved["playable_step_count"],0)
                self.assertFalse(saved["legacy_manual_steps_migration_verified"])
                for step in saved["sections"][0]["steps"]:
                    self.assertTrue(step["source_action_candidates"])
                    self.assertEqual(step["verified_actions"],[])
                    self.assertFalse(step["manual_completion_allowed"])
                    self.assertFalse(step["auto_completion_allowed"])
    def test_nebuleux_four_players_survive_17_turns(self):
        src=json.loads((ROOT/DIRECTORY/"ganymede_2247_action_candidates.json").read_text(encoding="utf-8"))
        combat=next(a for a in src["steps"][4]["actions"] if a["kind"]=="combat")
        self.assertEqual(combat["participants_min"],4)
        self.assertEqual(combat["turns_survive"],17)
        self.assertTrue(combat["all_allies_must_survive"])
    def test_dom_pin_all_six_primordial_dofus(self):
        src=json.loads((ROOT/DIRECTORY/"ganymede_2285_action_candidates.json").read_text(encoding="utf-8"))
        self.assertEqual({a.get("object_id") for a in src["steps"][1]["actions"]
                          if a["kind"]=="check_object"},{737,694,739,7754,7115,7114})
if __name__=="__main__":
    unittest.main()
