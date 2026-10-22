"""Contracts for Tachete source steps and safe replacement preview."""
from __future__ import annotations
import json
import unittest
from pathlib import Path
from tools.audit_ganymede_master_refs import ROOT
from tools.audit_ganymede_step_actions import audit_action_candidates
from tools.build_ganymede_replacement_previews import build_dofus_replacement_previews

D=Path("data/encyclopedia/guides")
class TacheteSourceTests(unittest.TestCase):
    def test_62_stages_parity_and_safe_progress(self):
        audit=audit_action_candidates(ROOT,D/"ganymede_2271_action_candidates.json")
        self.assertEqual(audit["status"],"REVIEW_ACTION_CANDIDATES_ONLY",audit["issues"])
        self.assertEqual((audit["source_steps"],audit["reviewed_steps"],audit["remaining_steps"]),(62,62,0))
        built=build_dofus_replacement_previews(ROOT)
        self.assertEqual(built["status"],"PREVIEWS_READY_NOT_PLAYABLE",built["issues"])
        saved=json.loads((ROOT/D/"replacement_drafts"/"dofus_tachete.json").read_text(encoding="utf-8"))
        generated=built["previews"]["dofus_tachete"]
        self.assertEqual(saved["source_action_candidate_actions"],270)
        self.assertEqual(saved["sections"][0]["steps"],generated["sections"][0]["steps"])
        self.assertFalse(saved["replacement_active"])
        self.assertEqual(saved["playable_step_count"],0)
        self.assertTrue(all(s["verified_actions"] == [] and
                            not s["manual_completion_allowed"] and
                            not s["auto_completion_allowed"] for s in saved["sections"][0]["steps"]))

    def test_alternative_vase_and_two_dungeons_required(self):
        d=json.loads((ROOT/D/"ganymede_2271_action_candidates.json").read_text(encoding="utf-8"))
        options=[a for a in d["steps"][26]["actions"] if a.get("alternative_group")=="vase_fleur"]
        self.assertEqual({a["branch"] for a in options},{"combat","fleur"})
        self.assertTrue(d["steps"][27]["optional_completion"])
        both=next(a for a in d["steps"][47]["actions"] if a.get("required_dungeons"))
        self.assertEqual((both["required_dungeons"],both["order"]),([133,134],"any"))
        self.assertEqual(next(a["dungeon_id"] for a in d["steps"][48]["actions"] if a["kind"]=="dungeon"),133)
        self.assertEqual(next(a["dungeon_id"] for a in d["steps"][49]["actions"] if a["kind"]=="dungeon"),134)

    def test_reward_final_stage(self):
        d=json.loads((ROOT/D/"ganymede_2271_action_candidates.json").read_text(encoding="utf-8"))
        rewards=[s["source_step_number"] for s in d["steps"]
            if any(a["kind"]=="goal_reward" and a.get("object_id")==7112 for a in s["actions"])]
        self.assertEqual(rewards,[1,62])
if __name__=="__main__":
    unittest.main()
