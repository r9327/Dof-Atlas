from __future__ import annotations

import os
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import main
from app.ui.preload_popup import PRELOAD_TASK_ORDER, PreloadProgressPopup


class FunctionalPreloadV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_popup_tracks_functional_tasks_only(self) -> None:
        self.assertEqual(PRELOAD_TASK_ORDER, ("quests", "encyclopedia", "craft"))
        self.assertNotIn("runtime", PRELOAD_TASK_ORDER)
        self.assertNotIn("tray", PRELOAD_TASK_ORDER)
        self.assertNotIn("network", PRELOAD_TASK_ORDER)

        popup = PreloadProgressPopup()
        try:
            popup.update_states(
                {
                    "quests": main.PRELOAD_READY,
                    "encyclopedia": main.PRELOAD_LOADING,
                    "craft": main.PRELOAD_IDLE,
                }
            )
            self.assertEqual(popup.progress.value(), 1)
            self.assertIn("Guides", popup.status_label.text())
        finally:
            popup.close()
            popup.deleteLater()

    def test_payload_error_marks_task_failed_and_popup_reports_failure(self) -> None:
        with patch.object(main.AtlasWindow, "_schedule_owned_callback", return_value=None):
            window = main.AtlasWindow(initial_preload={})
        try:
            window.preload_states.update(
                {
                    "quests": main.PRELOAD_READY,
                    "encyclopedia": main.PRELOAD_READY,
                    "craft": main.PRELOAD_LOADING,
                }
            )
            window.preload_started = True
            window.preload_queue.put(
                {
                    "craft": {"items": [], "errors": ["craft preload failed"]},
                    "_preload_task": "craft",
                    "_complete": True,
                }
            )
            with (
                patch.object(window, "apply_home_preload_update", return_value=None),
                patch.object(window, "apply_encyclopedia_preload_update", return_value=None),
                patch.object(window, "apply_craft_preload_update", return_value=None),
            ):
                window.collect_preload_result()

            self.assertEqual(window.preload_states["craft"], main.PRELOAD_FAILED)
            self.assertTrue(window.preload_finished)
            self.assertEqual(window.preload_popup.progress.value(), len(PRELOAD_TASK_ORDER))
            self.assertIn("erreur", window.preload_popup.status_label.text().casefold())
            self.assertIn("partiel", window.last_status_text.casefold())
        finally:
            window.quit_requested = True
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_related_warmup_reuses_quest_catalog_without_materializing_pages(self) -> None:
        catalog = object()
        with patch.object(main.AtlasWindow, "_schedule_owned_callback", return_value=None):
            window = main.AtlasWindow(initial_preload={"quests": {"catalog": catalog}})
        try:
            page_factories_before = set(window.page_factories)
            related_payload = {
                "achievement_provider": object(),
                "guide_provider": object(),
                "quest_graph": object(),
                "guide_progress_by_guide": {"guide:test": (1, 2, "En cours")},
                "guide_progress_character_key": "character:test",
                "errors": [],
            }
            with (
                patch.object(main, "build_quest_related_preload", return_value=related_payload) as build_related,
                patch.object(window, "apply_home_preload_update", return_value=None),
                patch.object(window, "apply_encyclopedia_preload_update", return_value=None),
                patch.object(window.preload_popup, "update_states", return_value=None),
            ):
                window.start_preload("encyclopedia")
                deadline = time.monotonic() + 2.0
                while window.preload_queue.empty() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertFalse(window.preload_queue.empty())
                window.collect_preload_result()

            build_related.assert_called_once_with(catalog)
            self.assertEqual(window.preload_states["encyclopedia"], main.PRELOAD_READY)
            self.assertIs(window.preload_results["quests"]["guide_provider"], related_payload["guide_provider"])
            self.assertEqual(set(window.page_factories), page_factories_before)
            self.assertIn("Quetes", window.page_factories)
            self.assertIn("Organizer", window.page_factories)
            self.assertIn("Equipement", window.page_factories)
        finally:
            window.quit_requested = True
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_related_warmup_is_not_started_twice(self) -> None:
        catalog = object()
        with patch.object(main.AtlasWindow, "_schedule_owned_callback", return_value=None):
            window = main.AtlasWindow(initial_preload={"quests": {"catalog": catalog}})
        try:
            gate_calls: list[object] = []

            def slow_related(value: object) -> dict[str, object]:
                gate_calls.append(value)
                time.sleep(0.08)
                return {"errors": []}

            with (
                patch.object(main, "build_quest_related_preload", side_effect=slow_related),
                patch.object(window.preload_popup, "update_states", return_value=None),
            ):
                window.start_preload("encyclopedia")
                window.start_preload("encyclopedia", user_requested=True)
                deadline = time.monotonic() + 2.0
                while window.preload_queue.empty() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertFalse(window.preload_queue.empty())
                window.collect_preload_result()

            self.assertEqual(gate_calls, [catalog])
        finally:
            window.quit_requested = True
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
