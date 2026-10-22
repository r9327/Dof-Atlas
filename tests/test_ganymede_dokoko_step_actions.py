"""Regression contracts for the 49 source-aligned Dokoko action candidates."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path
from tools.audit_ganymede_step_actions import audit_action_candidates, DIRECTORY

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = DIRECTORY / "ganymede_2208_action_candidates.json"

class DokokoActionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / DIRECTORY).mkdir(parents=True, exist_ok=True)
        self.payload = json.loads((ROOT / CANDIDATE).read_text(encoding="utf-8"))
        snaps = [p for p in (ROOT / DIRECTORY).glob("ganymede_*_observed_links.json")
                 if json.loads(p.read_text(encoding="utf-8"))["source"]["guide_id"] == 2208]
        self.assertEqual(len(snaps), 1)
        (self.root / DIRECTORY / snaps[0].name).write_text(
            snaps[0].read_text(encoding="utf-8"), encoding="utf-8")

    def audit(self):
        (self.root / CANDIDATE).write_text(
            json.dumps(self.payload, ensure_ascii=False), encoding="utf-8")
        return audit_action_candidates(self.root, CANDIDATE)

    def test_all_49_source_stages_only_as_review(self):
        report = self.audit()
        self.assertEqual(report["status"], "REVIEW_ACTION_CANDIDATES_ONLY", report["issues"])
        self.assertEqual((report["source_steps"], report["reviewed_steps"], report["remaining_steps"]), (49,49,0))
        self.assertEqual(report["certified_actions"], 0)
        self.assertFalse(report["ready_to_replace"])
        self.assertFalse(self.payload["ready_to_replace"])

    def test_reward_at_32_then_optional_33_through_49(self):
        steps = self.payload["steps"]
        self.assertEqual(len(steps), 49)
        self.assertTrue(all(not s["optional_completion"] for s in steps[:32]))
        self.assertTrue(all(s["optional_completion"] for s in steps[32:]))
        self.assertIn(17078, [a.get("object_id") for a in steps[31]["actions"]])
        self.assertEqual(steps[31]["route_phase"], "DOKOKO_REWARD_PATH")
        self.assertEqual(steps[32]["route_phase"], "OPTIONAL_ISLAND_COMPLETION")

    def test_quest_1666_start_finish_and_1670_are_not_collapsed(self):
        steps = self.payload["steps"]
        self.assertEqual([s["source_step_number"] for s in steps
                          if any(a.get("quest_id")==1666 and a["kind"]=="quest_start"
                                 for a in s["actions"])], [3])
        self.assertEqual([s["source_step_number"] for s in steps
                          if any(a.get("quest_id")==1666 and a["kind"]=="quest_finish"
                                 for a in s["actions"])], [4])
        self.assertIn(1670, [a.get("quest_id") for a in steps[28]["actions"]])
        self.assertIn(1670, [a.get("quest_id") for a in steps[31]["actions"]])

    def test_capture_is_optional_cross_guide(self):
        capture = [a for a in self.payload["steps"][17]["actions"]
                   if a["kind"] == "optional_capture"]
        self.assertEqual(len(capture), 1)
        self.assertEqual(capture[0]["monster_id"], 2960)
        self.assertEqual(capture[0]["conditional"], "emeraude")

    def test_stop_before_boss_then_finish_dungeon(self):
        first=self.payload["steps"][29]["actions"][0]
        second=self.payload["steps"][31]["actions"][0]
        self.assertEqual(first["dungeon_id"], 92)
        self.assertTrue(first["stop_before_boss"])
        self.assertEqual(second["dungeon_id"], 92)
        self.assertTrue(second["stay_at_end"])

    def test_fake_success_refused(self):
        self.payload["ready_to_replace"]=True
        self.assertEqual(self.audit()["status"], "FAIL")

    def test_invalid_quest_or_object_id_refused(self):
        self.payload["steps"][2]["actions"][0]["quest_id"]=999999
        self.assertEqual(self.audit()["status"], "FAIL")
        self.payload["steps"][2]["actions"][0]["quest_id"]=1666
        self.payload["steps"][1]["actions"][0]["object_id"]=999999
        self.assertEqual(self.audit()["status"], "FAIL")

    def test_missing_or_reordered_stage_refused(self):
        self.payload["steps"][1]["source_step_number"]=1
        self.assertEqual(self.audit()["status"], "FAIL")

if __name__=="__main__":
    unittest.main()
