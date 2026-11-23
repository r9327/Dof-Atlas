from __future__ import annotations

import unittest

from app.modules.encyclopedia.services.achievement_progress_logic import derive_completion_state


class AchievementProgressLogicTests(unittest.TestCase):
    def test_legacy_manual_achievement_write_keeps_sorted_json_ids(self) -> None:
        from types import SimpleNamespace
        from app.modules.encyclopedia.services.progress_service import AchievementProgressService

        character = {"completed_achievements": ["9", 9, "bad", 3]}
        saves = []
        owner = SimpleNamespace(
            _character=lambda _key: character,
            save=lambda: saves.append(True),
        )
        AchievementProgressService.set_achievement_completed(
            owner, "character:1", 4, True,
        )
        self.assertEqual(character["completed_achievements"], [3, 4, 9])
        self.assertEqual(saves, [True])

    def test_legacy_reader_shares_canonical_achievement_state(self) -> None:
        from types import SimpleNamespace
        from app.modules.encyclopedia.services.progress_service import AchievementProgressService

        character = {
            "completed_achievements": ["1", 2],
            "auto_completed_achievements": [3],
            "completed_objectives": {"5": ["11", 12]},
            "auto_completed_objectives": {5: [12, 13]},
        }
        owner = SimpleNamespace(
            _completion_cache={},
            _character=lambda _key: character,
        )
        result = AchievementProgressService._completion_state(owner, "character:1")
        self.assertEqual(result, derive_completion_state(character))
        self.assertIs(result, AchievementProgressService._completion_state(owner, "character:1"))

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

    def test_duplicate_numeric_formats_share_single_completion_identity(self) -> None:
        completed, objectives = derive_completion_state({
            "completed_achievements": ["010", 10, True, "bad"],
            "auto_completed_achievements": ["10", 20],
            "completed_objectives": {"9": [1.9, "2", "bad"]},
            "auto_completed_objectives": {"9": [1, 2, 2]},
        })
        self.assertEqual(completed, frozenset({1, 10, 20}))
        self.assertEqual(objectives, {9: frozenset({1, 2})})

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
