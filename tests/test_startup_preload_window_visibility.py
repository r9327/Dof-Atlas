"""Qt regression: Home handoff after Quest readiness, without warmup overlap."""
from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from app.ui.preload_popup import PreloadProgressPopup


class StartupPreloadVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_standalone_preload_is_visible_while_main_stays_hidden(self) -> None:
        main_window = QWidget()
        popup = PreloadProgressPopup(main_window)
        revealed: list[bool] = []
        popup.readyForMainWindow.connect(lambda: (revealed.append(True), main_window.show()))
        try:
            popup.begin({"quests": "IDLE", "encyclopedia": "IDLE", "craft": "IDLE"})
            self.app.processEvents()
            self.assertTrue(popup.isVisible())
            self.assertFalse(main_window.isVisible())

            popup.update_states({"quests": "READY", "encyclopedia": "LOADING", "craft": "IDLE"})
            popup.handoff()
            self.app.processEvents()
            self.assertTrue(popup._finished)
            self.assertTrue(popup._handed_off)
            self.assertEqual(revealed, [True])
            self.assertFalse(popup.isVisible())
            self.assertTrue(main_window.isVisible())

            # Finishing the optional preload cannot steal focus or reveal twice.
            popup.update_states({"quests": "READY", "encyclopedia": "READY", "craft": "FAILED"})
            popup.handoff()
            popup._hide_if_current(popup._hide_generation)
            self.app.processEvents()
            self.assertEqual(revealed, [True])
            self.assertFalse(popup.isVisible())
        finally:
            main_window.close()
            popup.deleteLater()
            self.app.processEvents()

    def test_launcher_owned_preload_has_no_second_visible_window(self) -> None:
        from unittest.mock import patch

        main_window = QWidget()
        revealed: list[bool] = []
        with patch.dict(os.environ, {"DOFUS_ATLAS_LAUNCHER_HANDOFF": "1"}):
            popup = PreloadProgressPopup(main_window)
        popup.readyForMainWindow.connect(lambda: (revealed.append(True), main_window.show()))
        try:
            popup.begin({"quests": "IDLE", "encyclopedia": "IDLE", "craft": "IDLE"})
            self.app.processEvents()
            self.assertFalse(popup.isVisible())
            self.assertFalse(main_window.isVisible())

            popup.update_states({"quests": "READY", "encyclopedia": "LOADING", "craft": "IDLE"})
            self.app.processEvents()
            self.assertFalse(revealed)
            self.assertFalse(popup.isVisible())

            popup.update_states({"quests": "READY", "encyclopedia": "READY", "craft": "READY"})
            self.app.processEvents()
            self.assertEqual(revealed, [True])
            self.assertFalse(popup.isVisible())
            self.assertTrue(main_window.isVisible())
        finally:
            main_window.close()
            popup.deleteLater()
            self.app.processEvents()

    def test_nonessential_services_start_after_preload_not_during_it(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        window = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AtlasWindow")
        constructor = next(n for n in window.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
        secondary = next(n for n in window.body if isinstance(n, ast.FunctionDef) and n.name == "_start_post_preload_services")
        ctor_body = ast.get_source_segment(source, constructor) or ""
        secondary_body = ast.get_source_segment(source, secondary) or ""
        self.assertNotIn("self._schedule_owned_callback(POST_RENDER_RUNTIME_DELAY_MS, self.start_runtime)", ctor_body)
        self.assertNotIn("self._schedule_owned_callback(POST_RENDER_NETWORK_DELAY_MS, self.prepare_network_capture)", ctor_body)
        self.assertNotIn("self._schedule_owned_callback(EQUIPMENT_PRELOAD_DELAY_MS, self.preload_equipment_page)", ctor_body)
        self.assertIn("not self.preload_finished", secondary_body)
        self.assertIn("self._post_preload_services_started", secondary_body)
        self.assertIn("self._schedule_owned_callback(POST_RENDER_RUNTIME_DELAY_MS, self.start_runtime)", secondary_body)
        self.assertIn("self._schedule_owned_callback(POST_RENDER_NETWORK_DELAY_MS, self.prepare_network_capture)", secondary_body)

    def test_bootstrap_never_shows_main_before_quest_base_is_terminal(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        entry = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
        body = ast.get_source_segment(source, entry) or ""
        self.assertIn("app.setQuitOnLastWindowClosed(False)", body)
        self.assertIn("window.preload_popup.begin(dict(window.preload_states))", body)
        self.assertIn("app.setQuitOnLastWindowClosed(True)", source)
        self.assertNotIn("window.show()", body)
        self.assertNotIn("splash.finish(window)", body)
        self.assertIn(
            "self.preload_popup.readyForMainWindow.connect(self._reveal_after_preload)",
            source,
        )

    def test_quest_ready_releases_home_before_optional_warmups_end(self) -> None:
        from unittest.mock import patch
        import main

        with patch.object(main.AtlasWindow, "_schedule_owned_callback", return_value=None) as schedule:
            window = main.AtlasWindow(initial_preload={})
            try:
                window.preload_popup.begin(dict(window.preload_states))
                window.preload_states["quests"] = main.PRELOAD_LOADING
                window.preload_queue.put({
                    "quests": {"catalog_count": 1976, "errors": []},
                    "_preload_task": "quests",
                    "_complete": True,
                })
                window.collect_preload_result()
                self.assertTrue(window.isVisible())
                self.assertFalse(window.preload_popup.isVisible())
                self.assertFalse(window.preload_finished)
                self.assertFalse(window._post_preload_services_started)
                self.assertEqual(window.preload_states["quests"], main.PRELOAD_READY)
                self.assertEqual(window.preload_states["encyclopedia"], main.PRELOAD_IDLE)
                self.assertNotIn(main.POST_RENDER_RUNTIME_DELAY_MS,
                                 [x.args[0] for x in schedule.call_args_list if x.args])

                window.preload_states.update({"encyclopedia": main.PRELOAD_READY,
                                              "craft": main.PRELOAD_READY})
                window.preload_finished = True
                window._start_post_preload_services()
                window._start_post_preload_services()
                self.assertTrue(window._post_preload_services_started)
                self.assertEqual(sum(
                    x.args == (main.POST_RENDER_RUNTIME_DELAY_MS, window.start_runtime)
                    for x in schedule.call_args_list
                ), 1)
            finally:
                window.quit_requested = True
                window.close()
                window.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
