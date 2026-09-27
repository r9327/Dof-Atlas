from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Callable

from app.core.json_store import InvalidPersistentJsonError
from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    AchievementProgressService,
)
from app.services.profile_settings_service import ProfileSettingsService


Loader = Callable[[Path], object]


class CriticalJsonSchemaTests(unittest.TestCase):
    def assert_refused_without_rewrite(
        self,
        filename: str,
        original: bytes,
        loader: Loader,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / filename
            path.write_bytes(original)

            with self.assertRaises(InvalidPersistentJsonError) as raised:
                loader(path)

            self.assertEqual(raised.exception.path, path)
            self.assertTrue(raised.exception.reason)
            self.assertEqual(path.read_bytes(), original)
            backups = list(path.parent.glob(f"{filename}.corrupt.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)

    def test_quest_progress_rejects_wrong_root_version_and_nested_fields(self) -> None:
        cases = (
            b"[]",
            b'{"version":2,"characters":{}}',
            b'{"version":1,"characters":[]}',
            b'{"version":1,"characters":{"character:1":{"done":[]}}}',
            b'{"version":1,"characters":{"character:1":{"quest_items":{"42":[]}}}}',
        )
        for original in cases:
            with self.subTest(original=original):
                self.assert_refused_without_rewrite(
                    "quest_progress.json", original, QuestProgressService
                )

    def test_guide_progress_rejects_wrong_root_version_and_nested_fields(self) -> None:
        cases = (
            b'"empty"',
            b'{"version":9,"characters":{}}',
            b'{"version":1,"characters":[]}',
            b'{"version":1,"characters":{"character:1":{"manual_steps":[]}}}',
            b'{"version":1,"characters":{"character:1":{"manual_steps":{"g":{}}}}}',
        )
        for original in cases:
            with self.subTest(original=original):
                self.assert_refused_without_rewrite(
                    "guide_progress.json", original, GuideProgressService
                )

    def test_achievement_progress_rejects_wrong_root_version_and_nested_fields(self) -> None:
        cases = (
            b"[]",
            b'{"version":2,"characters":{}}',
            b'{"version":1,"characters":[]}',
            b'{"version":1,"characters":{"character:1":{"completed_achievements":{}}}}',
            b'{"version":1,"characters":{"character:1":{"completed_objectives":{"9":{}}}}}',
        )
        for original in cases:
            with self.subTest(original=original):
                self.assert_refused_without_rewrite(
                    "achievement_progress.json", original, AchievementProgressService
                )

    def test_profile_rejects_wrong_root_before_load_or_mutation(self) -> None:
        for original in (b"[]", b'"profile"', b"null"):
            with self.subTest(original=original):
                self.assert_refused_without_rewrite(
                    "profiles.json",
                    original,
                    lambda path: ProfileSettingsService(path).set_value("theme", "dark"),
                )

    def test_syntax_error_is_refused_without_rewrite(self) -> None:
        self.assert_refused_without_rewrite(
            "quest_progress.json",
            b'{"version":1,"characters":',
            QuestProgressService,
        )

    def test_missing_documents_remain_valid_first_run_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            quests = QuestProgressService(root / "quests.json")
            guides = GuideProgressService(root / "guides.json")
            achievements = AchievementProgressService(root / "achievements.json")
            profile = ProfileSettingsService(root / "profiles.json")

            self.assertTrue(quests.set_quest_completed("character:1", 10, True))
            self.assertTrue(guides.set_manual_step_completed("character:1", "g", "s", True))
            self.assertTrue(achievements.set_achievement_completed("character:1", 20, True))
            self.assertTrue(profile.set_value("theme", "dark"))

            self.assertTrue((root / "quests.json").exists())
            self.assertTrue((root / "guides.json").exists())
            self.assertTrue((root / "achievements.json").exists())
            self.assertTrue((root / "profiles.json").exists())


if __name__ == "__main__":
    unittest.main()
