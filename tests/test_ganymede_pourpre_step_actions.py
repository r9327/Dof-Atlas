"""Pourpre factual actions: all source occurrences, OR choices, no premature activation."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from tools.audit_ganymede_step_actions import audit_action_candidates,DIRECTORY
ROOT=Path(__file__).resolve().parents[1]
CANDIDATE=DIRECTORY/"ganymede_2276_action_candidates.json"
class PourpreActionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        (self.root/DIRECTORY).mkdir(parents=True)
        self.payload=json.loads((ROOT/CANDIDATE).read_text(encoding="utf-8"))
        snapshots=[p for p in (ROOT/DIRECTORY).glob("ganymede_*_observed_links.json")
                   if json.loads(p.read_text(encoding="utf-8"))["source"]["guide_id"]==2276]
        self.assertEqual(len(snapshots),1)
        (self.root/DIRECTORY/snapshots[0].name).write_text(snapshots[0].read_text(encoding="utf-8"),encoding="utf-8")
    def audit(self):
        (self.root/CANDIDATE).write_text(json.dumps(self.payload,ensure_ascii=False),encoding="utf-8")
        return audit_action_candidates(self.root,CANDIDATE)
    def test_45_steps_review_only(self):
        r=self.audit()
        self.assertEqual(r["status"],"REVIEW_ACTION_CANDIDATES_ONLY",r["issues"])
        self.assertEqual((r["source_steps"],r["reviewed_steps"],r["remaining_steps"]),(45,45,0))
        self.assertEqual(r["certified_actions"],0)
        self.assertFalse(r["ready_to_replace"])
    def test_main_quests_and_side_references_are_distinct(self):
        bystep=self.payload["steps"]
        self.assertEqual(bystep[14]["actions"][1]["quest_id"],1527)
        self.assertEqual(bystep[14]["actions"][1]["relation"],"side_required_for_progression")
        self.assertEqual(next(a for a in bystep[19]["actions"] if a["kind"]=="quest_start")["relation"],"repeatable_support")
        self.assertEqual(next(a for a in bystep[36]["actions"] if a.get("quest_id")==2538)["relation"],"optional_method")
    def test_alternative_treasure_methods_not_all_mandatory(self):
        arr=self.payload["steps"][36]["actions"]
        self.assertEqual(len([x for x in arr if x["kind"]=="dungeon" and x["relation"]=="alternative_source"]),12)
        self.assertEqual(next(x for x in arr if x["kind"]=="check_object")["quantity"],25)
    def test_reward_only_final_step(self):
        rewards=[s["source_step_number"] for s in self.payload["steps"]
                 if any(a["kind"]=="goal_reward" and a.get("object_id")==694
                        for a in s["actions"])]
        self.assertEqual(rewards,[1,45])
        self.assertEqual(self.payload["steps"][-1]["actions"][-1]["object_id"],694)
    def test_unknown_location_remains_unknown(self):
        self.assertIsNone(self.payload["steps"][0]["at"])
    def test_fake_certification_and_foreign_reference_fail(self):
        self.payload["ready_to_replace"]=True
        self.assertEqual(self.audit()["status"],"FAIL")
        self.payload["ready_to_replace"]=False
        self.payload["steps"][10]["actions"][0]["dungeon_id"]=999999
        self.assertEqual(self.audit()["status"],"FAIL")
if __name__=="__main__":
    unittest.main()
