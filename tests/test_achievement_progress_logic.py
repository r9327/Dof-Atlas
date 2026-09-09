from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.achievement_progress_logic import derive_completion_state


class AchievementProgressLogicTests(unittest.TestCase):
    def test_merges_manual_and_automatic_completion(self) -> None:
        completed, objectives = derive_completion_state(
            {
                "completed_achievements": [1, "2", "bad"],
                "auto_completed_achievements": [2, 3],
                "completed_objectives": {"10": [100, "101", "bad"]},
                "auto_completed_objectives": {10: [101, 102], "bad": [999]},
            }
        )

        self.assertEqual(completed, frozenset({1, 2, 3}))
        self.assertEqual(objectives, {10: frozenset({100, 101, 102})})

    def test_ignores_malformed_objective_containers_without_mutating_input(self) -> None:
        character = {
            "completed_achievements": [],
            "auto_completed_achievements": [],
            "completed_objectives": ["not-a-dict"],
            "auto_completed_objectives": {"12": "not-a-list"},
        }

        completed, objectives = derive_completion_state(character)

        self.assertEqual(completed, frozenset())
        self.assertEqual(objectives, {12: frozenset()})
        self.assertEqual(character["auto_completed_objectives"], {"12": "not-a-list"})


if __name__ == "__main__":
    unittest.main()
