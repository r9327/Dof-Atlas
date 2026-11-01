from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.constants import KEY_ORGANIZER_MACRO_MODE
from app.core.runtime_state import AtlasRuntime
from app.input.hotkeys import build_hotkey_actions
from app.pages.organizer_page import OrganizerPage


class OrganizerMirrorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt = QApplication.instance() or QApplication([])

    def test_three_cards_and_compact_mode_with_persisted_classic_preferences(self):
        import app.pages.organizer_page as organizer
        import app.pages.organizer.character_sessions as sessions

        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "profiles.json"
            index = Path(directory) / "client_index.json"
            ini = Path(directory) / "client_index.ini"
            profile.write_text("{}", encoding="utf-8")
            index.write_text(json.dumps({"clients": []}), encoding="utf-8")
            on_stop, on_reload = Mock(), Mock()
            with (
                patch.dict(os.environ, {"QT_QPA_PLATFORM": "offscreen"}),
                patch.object(organizer, "PROFILE_FILE", profile),
                patch.object(organizer, "CLIENT_INDEX_JSON", index),
                patch.object(organizer, "CLIENT_INDEX_INI", ini),
                patch.object(sessions, "PROFILE_FILE", profile),
                patch.object(sessions, "CLIENT_INDEX_JSON", index),
                patch.object(sessions, "CLIENT_INDEX_INI", ini),
                patch.object(organizer.UnityWindowEventWatcher, "start",
                             side_effect=AssertionError("Native watcher started")),
            ):
                page = OrganizerPage(Mock(), on_reload, stop_runtime_callback=on_stop)
                try:
                    self.assertTrue(page.macro_panel.isAncestorOf(page.macro_mode_button))
                    self.assertTrue(page.macro_panel.isAncestorOf(page.mirror_mode_button))
                    self.assertTrue(page.macro_panel.isAncestorOf(page.switch_click))
                    self.assertTrue(page.quick_actions_panel.isAncestorOf(page.switch_fake))
                    self.assertTrue(page.quick_actions_panel.isAncestorOf(page.radial_select_button))
                    self.assertTrue(page.quick_actions_panel.isAncestorOf(page.script_speed_fast))
                    self.assertTrue(page.controls_panel.isAncestorOf(page.reload_runtime_button))
                    self.assertTrue(page.controls_panel.isAncestorOf(page.debug_button))
                    self.assertTrue(page.controls_panel.isAncestorOf(page.stop_script_button))
                    self.assertTrue(page.macro_grid_host.isEnabled())
                    page.mirror_mode_button.click()
                    self.assertEqual(page.profiles[KEY_ORGANIZER_MACRO_MODE], "mirror")
                    self.assertFalse(page.macro_grid_host.isEnabled())
                    self.assertTrue(page.stop_script_button.isEnabled())
                    self.assertTrue(page.radial_select_button.isEnabled())
                    on_stop.assert_called_once()
                    page.macro_mode_button.click()
                    self.assertEqual(page.profiles[KEY_ORGANIZER_MACRO_MODE], "macro")
                    self.assertTrue(page.macro_grid_host.isEnabled())
                    self.assertEqual(on_stop.call_count, 2)
                    self.assertEqual(
                        json.loads(profile.read_text(encoding="utf-8"))[KEY_ORGANIZER_MACRO_MODE],
                        "macro",
                    )
                finally:
                    page.stop_session_event_watcher()
                    page.deleteLater()

    def test_mirror_disables_classic_hotkeys_but_keeps_emergency_stop(self):
        actions = build_hotkey_actions(
            SimpleNamespace(macro_mode="mirror", stop_hotkey="F12"),
        )
        self.assertEqual([action.action_id for action in actions], ["stop_script"])
        self.assertEqual(
            build_hotkey_actions(SimpleNamespace(macro_mode="mirror", stop_hotkey="")),
            [],
        )

    def _runtime(self, *, primary=101, handles=(101, 202, 303)):
        clients = tuple(SimpleNamespace(handle=h) for h in handles)
        settings = SimpleNamespace(
            macro_mode="mirror", primary_handle=primary, clients=clients,
            client_by_handle=lambda h: next((c for c in clients if c.handle == h), None),
        )
        runtime = Mock()
        runtime.settings = settings
        runtime.macro_lock.active_label = ""
        runtime.switch_click.run_async.return_value = True
        return runtime

    def test_favorite_click_reuses_existing_sender_once(self):
        runtime = self._runtime()
        with (
            patch("app.windows.unity_windows.is_unity_window", return_value=True),
            patch("app.windows.unity_windows.foreground_window", return_value=101),
            patch("app.windows.unity_windows.find_known_client_from_point", return_value=101),
        ):
            self.assertTrue(AtlasRuntime._handle_mirror_click(runtime, "Left", 12, 28))
        runtime.switch_click.run_async.assert_called_once_with(
            "Left", 12, 28, 1, "Miroir", exact_source_handle=101,
        )

    def test_no_favorite_foreign_focus_one_client_or_too_many_fail_closed(self):
        cases = [
            (self._runtime(primary=0), 101, 101),
            (self._runtime(), 777, 101),
            (self._runtime(), 101, 777),
            (self._runtime(handles=(101,)), 101, 101),
            (self._runtime(handles=tuple(range(101, 110))), 101, 101),
        ]
        for runtime, foreground, under_cursor in cases:
            with self.subTest(primary=runtime.settings.primary_handle, foreground=foreground):
                with (
                    patch("app.windows.unity_windows.is_unity_window", return_value=True),
                    patch("app.windows.unity_windows.foreground_window", return_value=foreground),
                    patch("app.windows.unity_windows.find_known_client_from_point", return_value=under_cursor),
                ):
                    self.assertFalse(
                        AtlasRuntime._handle_mirror_click(runtime, "Left", 12, 28)
                    )
                runtime.switch_click.run_async.assert_not_called()

    def test_macro_busy_consumes_without_starting_a_second_delivery(self):
        runtime = self._runtime()
        runtime.macro_lock.active_label = "Miroir"
        with (
            patch("app.windows.unity_windows.is_unity_window", return_value=True),
            patch("app.windows.unity_windows.foreground_window", return_value=101),
            patch("app.windows.unity_windows.find_known_client_from_point", return_value=101),
        ):
            self.assertTrue(AtlasRuntime._handle_mirror_click(runtime, "Left", 12, 28))
        runtime.switch_click.run_async.assert_not_called()


if __name__ == "__main__":
    unittest.main()
