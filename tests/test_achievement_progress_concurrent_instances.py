from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)


class AchievementProgressConcurrentInstanceTests(unittest.TestCase):
    def test_stale_instances_preserve_each_others_achievement_writes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "achievement_progress.json"
            first = AchievementProgressService(path)
            stale_second = AchievementProgressService(path)

            first.set_achievement_completed("character:1", 101, True)
            stale_second.set_achievement_completed("character:1", 202, True)

            reloaded = AchievementProgressService(path)
            state = reloaded.state_for("character:1")
            self.assertTrue(state.is_achievement_completed(101))
            self.assertTrue(state.is_achievement_completed(202))

    def test_stale_instances_preserve_manual_objectives(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "achievement_progress.json"
            first = AchievementProgressService(path)
            stale_second = AchievementProgressService(path)

            first.set_objective_completed("character:1", 10, 1001, True)
            stale_second.set_objective_completed("character:1", 10, 1002, True)

            reloaded = AchievementProgressService(path)
            self.assertTrue(reloaded.is_objective_completed("character:1", 10, 1001))
            self.assertTrue(reloaded.is_objective_completed("character:1", 10, 1002))


if __name__ == "__main__":
    unittest.main()
