from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.json_store import InvalidPersistentJsonError
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)


class AchievementProgressJsonStoreTests(unittest.TestCase):
    def test_corrupt_progress_is_backed_up_and_never_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "achievement_progress.json"
            original = b'{"characters": '
            path.write_bytes(original)

            with self.assertRaises(InvalidPersistentJsonError):
                AchievementProgressService(path)

            backups = list(path.parent.glob("achievement_progress.json.corrupt.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
