from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)


class AchievementProgressJsonStoreTests(unittest.TestCase):
    def test_corrupt_progress_is_backed_up_then_rewritten_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "achievement_progress.json"
            path.write_text('{"characters": ', encoding="utf-8")

            service = AchievementProgressService(path)

            self.assertFalse(service.is_achievement_completed("character:1", 42))
            backups = list(path.parent.glob("achievement_progress.json.corrupt.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), '{"characters": ')

            service.set_achievement_completed("character:1", 42, True)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn(42, payload["characters"]["character:1"]["completed_achievements"])
            self.assertTrue(AchievementProgressService(path).is_achievement_completed("character:1", 42))


if __name__ == "__main__":
    unittest.main()
