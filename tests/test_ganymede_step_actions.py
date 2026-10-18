from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_step_actions import audit_action_candidates, DEFAULT, DIRECTORY

ROOT = Path(__file__).resolve().parents[1]


class ActionCandidateTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        (self.root / DIRECTORY).mkdir(parents=True)
        self.payload = json.loads((ROOT / DEFAULT).read_text(encoding="utf-8"))
        for p in (ROOT / DIRECTORY).glob("ganymede_*_observed_links.json"):
            src = json.loads(p.read_text(encoding="utf-8"))
            if src["source"]["guide_id"] == 2205:
                (self.root / DIRECTORY / p.name).write_text(
                    p.read_text(encoding="utf-8"), encoding="utf-8")
                break

    def check(self):
        (self.root / DEFAULT).write_text(json.dumps(self.payload), encoding="utf-8")
        return audit_action_candidates(self.root)

    def test_ten_source_steps_with_29_actions(self):
        report = self.check()
        self.assertEqual(report["status"], "REVIEW_ACTION_CANDIDATES_ONLY", report["issues"])
        self.assertEqual(report["source_steps"], 64)
        self.assertEqual(report["reviewed_steps"], 10)
        self.assertEqual(report["remaining_steps"], 54)
        self.assertFalse(report["ready_to_replace"])
        self.assertEqual(report["certified_actions"], 0)
        self.assertEqual(sum(len(s["actions"]) for s in self.payload["steps"]), 29)

    def test_repeated_quest_is_not_deduplicated_across_steps(self):
        self.assertIn(836, [a.get("quest_id") for a in self.payload["steps"][2]["actions"]])
        self.assertIn(836, [a.get("quest_id") for a in self.payload["steps"][9]["actions"]])
        self.assertEqual(self.check()["status"], "REVIEW_ACTION_CANDIDATES_ONLY")

    def test_invalid_quest_id_is_rejected(self):
        self.payload["steps"][2]["actions"][0]["quest_id"] = 998877
        self.assertEqual(self.check()["status"], "FAIL")

    def test_invalid_location_is_rejected(self):
        self.payload["steps"][0]["at"] = [888, 888]
        self.assertEqual(self.check()["status"], "FAIL")

    def test_reordered_step_is_rejected(self):
        self.payload["steps"][2]["source_step_number"] = 1
        self.assertEqual(self.check()["status"], "FAIL")

    def test_false_certification_is_rejected(self):
        self.payload["certified_actions"] = 29
        self.assertEqual(self.check()["status"], "FAIL")

    def test_missing_snapshot_fails_closed(self):
        for p in (self.root / DIRECTORY).glob("ganymede_*_observed_links.json"):
            p.unlink()
        self.assertEqual(self.check()["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
