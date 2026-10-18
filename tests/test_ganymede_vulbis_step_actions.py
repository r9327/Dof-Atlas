"""Vulbis source mapping, replacement parity and true reward."""
import json
import unittest
from pathlib import Path
from tools.audit_ganymede_master_refs import ROOT
from tools.audit_ganymede_step_actions import audit_action_candidates
from tools.build_ganymede_replacement_previews import build_dofus_replacement_previews
D=Path("data/encyclopedia/guides")
class VulbisTests(unittest.TestCase):
 def test_source_and_draft(self):
  status=audit_action_candidates(ROOT,D/"ganymede_2260_action_candidates.json")
  self.assertEqual(status["status"],"REVIEW_ACTION_CANDIDATES_ONLY",status["issues"])
  self.assertEqual(status["reviewed_steps"],47)
  report=build_dofus_replacement_previews(ROOT)
  self.assertEqual(report["status"],"PREVIEWS_READY_NOT_PLAYABLE",report["issues"])
  draft=json.loads((ROOT/D/"replacement_drafts"/"dofus_vulbis.json").read_text(encoding="utf-8"))
  self.assertEqual(draft["sections"][0]["steps"],report["previews"]["dofus_vulbis"]["sections"][0]["steps"])
  self.assertEqual(draft["source_action_candidate_actions"],197)
  self.assertEqual(draft["playable_step_count"],0)
  self.assertFalse(draft["replacement_active"])
  self.assertTrue(all(not s["auto_completion_allowed"] and not s["manual_completion_allowed"] for s in draft["sections"][0]["steps"]))
 def test_real_reward(self):
  data=json.loads((ROOT/D/"ganymede_2260_action_candidates.json").read_text(encoding="utf-8"))
  rewards=[s["source_step_number"] for s in data["steps"] if any(a["kind"]=="goal_reward" for a in s["actions"])]
  self.assertEqual(rewards,[47])
  self.assertEqual(data["steps"][-1]["actions"][-1]["object_id"],6980)
if __name__=="__main__":unittest.main()
