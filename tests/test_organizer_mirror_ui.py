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
                    self.assertIsNone(page.macro_grid_host.graphicsEffect())
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


    def test_exact_source_guard_does_not_consume_another_window_or_fallback(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext
        runtime = Mock()
        mirror = SwitchClickMacro(runtime)
        for handle, reason in ((202, "cursor"), (101, "preferred_center")):
            with self.subTest(handle=handle, reason=reason):
                context = SwitchClickContext(handle, 10, 10, 0.4, 0.4, reason)
                with patch.object(mirror, "_capture_trigger_context", return_value=context):
                    self.assertFalse(mirror.run_async(
                        "Left", 50, 60, 1, "Miroir", exact_source_handle=101,
                    ))
        runtime._spawn_macro.assert_not_called()
        runtime.input_state.begin_mouse_block.assert_not_called()

    def test_sequential_sender_visits_2_4_8_clients_exactly_once(self):
        from app.macros.switch_click import SwitchClickMacro, SwitchClickContext
        for count in (2, 4, 8):
            with self.subTest(count=count):
                handles = tuple(range(101, 101 + count))
                clients = [SimpleNamespace(handle=h, display_name=str(h)) for h in handles]
                runtime = Mock()
                runtime.switch_character.ordered_clients_from_source.return_value = clients
                runtime.settings.client_by_handle.return_value = clients[0]
                runtime.macro_lock.should_stop.return_value = False
                runtime.macro_lock.wait.return_value = False
                runtime.settings.timings = SimpleNamespace(
                    switch_background_pre_click_ms=0,
                    activate_attempts=1, activate_retry_ms=0,
                    input_double_gap_ms=5, switch_click_down_ms=1,
                    switch_background_post_up_ms=0, switch_client_settle_ms=0,
                )
                macro = SwitchClickMacro(runtime)
                context = SwitchClickContext(handles[0], 20, 30, 0.5, 0.5, "cursor")
                with (
                    patch("app.macros.switch_click.current_cursor_pos", return_value=(100, 200)),
                    patch("app.macros.switch_click.set_cursor_pos"),
                    patch("app.macros.switch_click.is_unity_window", return_value=True),
                    patch("app.macros.switch_click.activate_window", return_value=True),
                    patch("app.macros.switch_click.send_client_click", return_value=True) as sender,
                    patch.object(macro, "_target_point", return_value=(20, 30)),
                ):
                    macro._run("Left", 1, "Miroir", context)
                self.assertEqual(sender.call_count, count)
                self.assertEqual(
                    [call.args[0] for call in sender.call_args_list], list(handles),
                )
                runtime.switch_character.restore_preferred_client.assert_called_once_with("Miroir")


if __name__ == "__main__":
    unittest.main()
