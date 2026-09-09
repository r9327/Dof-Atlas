from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.services.guide_progress_service import GuideProgressService
from app.modules.encyclopedia.services.serialized_achievement_progress_service import AchievementProgressService


class ProgressServiceReloadFastPathTests(unittest.TestCase):
    def test_achievement_reload_skips_unchanged_disk_parse(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "achievement_progress.json"
            calls: list[str] = []

            def fake_read(target: Path, default):
                calls.append(str(target))
                return {"version": 1, "characters": {}}

            with patch(
                "app.modules.encyclopedia.services.serialized_achievement_progress_service.read_json_resilient",
                side_effect=fake_read,
            ):
                service = AchievementProgressService(path)
                first = service.progress
                second = service.reload()

            self.assertIs(first, second)
            self.assertEqual(len(calls), 1)

    def test_guide_reload_skips_unchanged_disk_parse(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "guide_progress.json"
            calls: list[str] = []

            def fake_read(target: Path, default):
                calls.append(str(target))
                return {"version": 1, "characters": {}}

            with patch(
                "app.modules.encyclopedia.services.guide_progress_service.read_json_resilient",
                side_effect=fake_read,
            ):
                service = GuideProgressService(path)
                first = service.progress
                second = service.reload()

            self.assertIs(first, second)
            self.assertEqual(len(calls), 1)

    def test_external_file_creation_still_invalidates_both_services(self):
        for service_type, module_path, filename in (
            (
                AchievementProgressService,
                "app.modules.encyclopedia.services.serialized_achievement_progress_service.read_json_resilient",
                "achievement_progress.json",
            ),
            (
                GuideProgressService,
                "app.modules.encyclopedia.services.guide_progress_service.read_json_resilient",
                "guide_progress.json",
            ),
        ):
            with self.subTest(service=service_type.__name__), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / filename

                def fake_read(target: Path, default):
                    marker = target.read_text(encoding="utf-8") if target.exists() else "missing"
                    return {"version": 1, "marker": marker, "characters": {}}

                with patch(module_path, side_effect=fake_read):
                    service = service_type(path)
                    self.assertEqual(service.progress["marker"], "missing")
                    path.write_text("external", encoding="utf-8")
                    self.assertTrue(service.refresh_if_changed())
                    self.assertEqual(service.progress["marker"], "external")


if __name__ == "__main__":
    unittest.main()
