"""Dolmanax source has nine information stages, but 365 separate daily offerings."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_step_actions import audit_action_candidates, DIRECTORY

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = DIRECTORY / "ganymede_2248_action_candidates.json"
SNAPSHOT = DIRECTORY / "ganymede_dolmanax_observed_links.json"


class DolmanaxActionsTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        (self.root / DIRECTORY).mkdir(parents=True)
        self.rows = json.loads((ROOT / CANDIDATE).read_text(encoding="utf-8"))
        (self.root / SNAPSHOT).write_bytes((ROOT / SNAPSHOT).read_bytes())

    def audit(self):
        (self.root / CANDIDATE).write_text(
            json.dumps(self.rows, ensure_ascii=False), encoding="utf-8")
        return audit_action_candidates(self.root, CANDIDATE)

    def test_nine_factual_stages_do_not_certify_dolmanax(self):
        report = self.audit()
        self.assertEqual(report["status"], "REVIEW_ACTION_CANDIDATES_ONLY", report["issues"])
        self.assertEqual(report["reviewed_steps"], 9)
        self.assertEqual(report["remaining_steps"], 0)
        self.assertEqual(report["certified_actions"], 0)
        self.assertFalse(report["ready_to_replace"])
        self.assertEqual(sum(len(s["actions"]) for s in self.rows["steps"]), 23)

    def test_daily_offering_is_not_marked_completed_365_times(self):
        daily = self.rows["steps"][1]
        mechanic = next(a for a in daily["actions"]
                        if a.get("repetition") == "daily")
        self.assertEqual(mechanic["max_daily_completions"], 1)
        self.assertEqual(mechanic["target_pages"], 365)
        self.assertTrue(all(s["quest_objectives_verified"] is False
                            for s in self.rows["steps"]))

    def test_missing_source_coordinate_is_explicit_null(self):
        for step in self.rows["steps"]:
            if step["source_step_number"] != 2:
                self.assertIsNone(step["at"])
                self.assertIsNone(step["next"])
        self.assertEqual(self.rows["steps"][1]["at"], [-4, -24])
        self.assertEqual(self.audit()["status"], "REVIEW_ACTION_CANDIDATES_ONLY")

    def test_invented_coordinate_fails_closed(self):
        self.rows["steps"][0]["at"] = [0, 0]
        self.assertEqual(self.audit()["status"], "FAIL")

    def test_unknown_quest_id_fails_closed(self):
        self.rows["steps"][1]["actions"][0]["quest_id"] = 999999
        self.assertEqual(self.audit()["status"], "FAIL")

    def test_false_guide_activation_fails_closed(self):
        self.rows["ready_to_replace"] = True
        self.assertEqual(self.audit()["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
