from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService


class QuestProgressReloadFastPathTests(unittest.TestCase):
    def test_reload_skips_json_parse_when_generation_and_file_are_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "progress.json"
            calls: list[str] = []

            def fake_load(target: Path):
                calls.append(str(target))
                marker = target.read_text(encoding="utf-8") if target.exists() else "missing"
                return {"marker": marker, "characters": {}}

            with patch(
                "app.modules.encyclopedia.services.quest_progress_service.load_quest_progress",
                side_effect=fake_load,
            ):
                service = QuestProgressService(path)
                first = service.progress
                second = service.reload()

            self.assertIs(first, second)
            self.assertEqual(len(calls), 1)

    def test_reload_still_detects_external_file_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "progress.json"
            calls: list[str] = []

            def fake_load(target: Path):
                calls.append(str(target))
                marker = target.read_text(encoding="utf-8") if target.exists() else "missing"
                return {"marker": marker, "characters": {}}

            with patch(
                "app.modules.encyclopedia.services.quest_progress_service.load_quest_progress",
                side_effect=fake_load,
            ):
                service = QuestProgressService(path)
                self.assertEqual(service.progress["marker"], "missing")
                path.write_text("external-change", encoding="utf-8")
                refreshed = service.reload()

            self.assertEqual(refreshed["marker"], "external-change")
            self.assertEqual(len(calls), 2)

    def test_refresh_if_changed_detects_external_file_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "progress.json"

            def fake_load(target: Path):
                marker = target.read_text(encoding="utf-8") if target.exists() else "missing"
                return {"marker": marker, "characters": {}}

            with patch(
                "app.modules.encyclopedia.services.quest_progress_service.load_quest_progress",
                side_effect=fake_load,
            ):
                service = QuestProgressService(path)
                self.assertFalse(service.refresh_if_changed())
                path.write_text("peer", encoding="utf-8")
                self.assertTrue(service.refresh_if_changed())
                self.assertEqual(service.progress["marker"], "peer")

    def test_quest_mutation_does_not_reread_after_its_own_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "progress.json"
            loads: list[str] = []
            saves: list[dict] = []

            def fake_load(target: Path):
                loads.append(str(target))
                return {"version": 1, "characters": {}}

            def fake_save(progress: dict, target: Path):
                saves.append(progress)

            with (
                patch(
                    "app.modules.encyclopedia.services.quest_progress_service.load_quest_progress",
                    side_effect=fake_load,
                ),
                patch(
                    "app.modules.encyclopedia.services.quest_progress_service.save_quest_progress",
                    side_effect=fake_save,
                ),
            ):
                service = QuestProgressService(path)
                service.set_quest_completed("character:1", 42, True)

            self.assertEqual(len(loads), 2)
            self.assertEqual(len(saves), 1)
            self.assertTrue(service.progress["characters"]["character:1"]["done"]["42"])
            self.assertEqual(service._seen_generation, service._coordinator.generation)


if __name__ == "__main__":
    unittest.main()
