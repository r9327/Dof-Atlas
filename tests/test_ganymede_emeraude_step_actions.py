"""Regressions: Émeraude source-step evidence, never an activated Atlas route."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.audit_ganymede_step_actions import (
    DIRECTORY, audit_action_candidates,
)

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = DIRECTORY / "ganymede_2211_action_candidates.json"
SOURCE = DIRECTORY / "ganymede_emeraude_observed_links.json"


class EmeraldActionsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / DIRECTORY).mkdir(parents=True)
        self.candidate = json.loads((ROOT / CANDIDATE).read_text(encoding="utf-8"))
        (self.root / SOURCE).write_text(
            (ROOT / SOURCE).read_text(encoding="utf-8"), encoding="utf-8")

    def validate(self):
        (self.root / CANDIDATE).write_text(
            json.dumps(self.candidate, ensure_ascii=False), encoding="utf-8")
        return audit_action_candidates(self.root, CANDIDATE)

    def test_all_fifty_two_source_steps_have_reviewable_actions(self):
        result = self.validate()
        self.assertEqual(result["status"], "REVIEW_ACTION_CANDIDATES_ONLY", result["issues"])
        self.assertEqual(result["source_steps"], 52)
        self.assertEqual(result["reviewed_steps"], 52)
        self.assertEqual(result["remaining_steps"], 0)
        self.assertEqual(result["certified_actions"], 0)
        self.assertFalse(result["ready_to_replace"])
        self.assertEqual(sum(len(s["actions"]) for s in self.candidate["steps"]), 179)

    def test_stable_ids_and_every_occurrence_kept(self):
        self.assertEqual(
            [s["stable_step_id"] for s in self.candidate["steps"]],
            [f"ganymede_2211_step_{i:04d}" for i in range(1, 53)])
        self.assertEqual(
            [s["source_step_number"] for s in self.candidate["steps"]],
            list(range(1, 53)))

    def test_capture_quest_is_started_and_finished_at_distinct_steps(self):
        self.assertTrue(any(a.get("quest_id") == 1465 and a["kind"] == "quest_start"
                            for a in self.candidate["steps"][19]["actions"]))
        self.assertTrue(any(a.get("quest_id") == 1465 and a["kind"] == "quest_finish"
                            for a in self.candidate["steps"][21]["actions"]))
        self.assertEqual(sum(a.get("monster_id") is not None and a.get("capture_required") is True
                             for a in self.candidate["steps"][19]["actions"]), 5)

    def test_actual_collection_and_conditional_fights(self):
        for step in self.candidate["steps"][6:12]:
            self.assertTrue(any(a["kind"] == "collect_object" for a in step["actions"]))
            battles = [a for a in step["actions"] if a["kind"] == "combat"]
            self.assertEqual(len(battles), 1)
            self.assertEqual(battles[0]["conditional"], "may_trigger")

    def test_dungeon_and_breeding_never_autocomplete(self):
        self.assertTrue(any(a["kind"] == "dungeon" for a in self.candidate["steps"][42]["actions"]))
        self.assertTrue(any(a["kind"] == "group_mechanic"
                            for a in self.candidate["steps"][32]["actions"]))
        self.assertTrue(all(s["quest_objectives_verified"] is False
                            for s in self.candidate["steps"]))
        self.assertEqual(self.candidate["certified_actions"], 0)

    def test_source_references_exact_match_with_namespace(self):
        source = json.loads((self.root / SOURCE).read_text(encoding="utf-8"))
        for expected, step in zip(source["steps"], self.candidate["steps"], strict=True):
            self.assertEqual(step["source_step_number"], expected["source_step_number"])
            self.assertIn(step["at"], expected["coordinate_mentions"])
            self.assertIn(step["next"], expected["coordinate_mentions"])
            for action in step["actions"]:
                for key, kind in (("quest_id", "quest"), ("object_id", "object"),
                                  ("monster_id", "monster"), ("dungeon_id", "dungeon")):
                    if key in action:
                        self.assertIn(action[key], expected["external_dofusdb_ids"][kind])

    def test_invalid_quest_reference_fails_closed(self):
        self.candidate["steps"][19]["actions"][0]["quest_id"] = 999999
        self.assertEqual(self.validate()["status"], "FAIL")

    def test_wrong_source_coordinates_fails_closed(self):
        self.candidate["steps"][11]["next"] = [500, 500]
        self.assertEqual(self.validate()["status"], "FAIL")

    def test_repeated_step_number_fails_closed(self):
        self.candidate["steps"][21]["source_step_number"] = 20
        self.assertEqual(self.validate()["status"], "FAIL")

    def test_no_false_certification_or_activation(self):
        self.candidate["ready_to_replace"] = True
        self.assertEqual(self.validate()["status"], "FAIL")
        self.candidate["ready_to_replace"] = False
        self.candidate["certified_actions"] = 179
        self.assertEqual(self.validate()["status"], "FAIL")

    def test_invalid_snapshot_fails_closed(self):
        (self.root / SOURCE).unlink()
        self.assertEqual(self.validate()["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
