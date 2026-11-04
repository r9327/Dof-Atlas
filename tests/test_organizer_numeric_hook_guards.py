from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.runtime_state import AtlasRuntime
from app.core.settings import int_value
from app.windows.unity_windows import find_known_client_from_point


class OrganizerNumericHookGuardsTests(unittest.TestCase):
    def test_infinite_hotkey_client_index_never_starts_a_switch(self):
        runtime = Mock()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings.macro_mode = "macro"
        for value in (float("inf"), -float("inf"), float("nan")):
            with self.subTest(value=str(value)):
                AtlasRuntime._handle_hotkey(
                    runtime, "client:1", {"client_index": value},
                )
        runtime.switch_character.activate_by_index.assert_not_called()
        self.assertEqual(runtime.logger.debug.call_count, 3)

    def test_client_hotkey_rejects_fractional_and_bool_slot_aliases(self):
        runtime = Mock()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings.macro_mode = "macro"
        for value in (True, False, 1.0, 1.75, -1.5):
            with self.subTest(value=repr(value)):
                AtlasRuntime._handle_hotkey(runtime, "client:1", {"client_index": value})
        runtime.switch_character.activate_by_index.assert_not_called()
        self.assertEqual(runtime.logger.debug.call_count, 5)
        # Keep the persisted textual slot contract and legitimate int path.
        AtlasRuntime._handle_hotkey(runtime, "client:1", {"client_index": "1"})
        AtlasRuntime._handle_hotkey(runtime, "client:2", {"client_index": 2})
        self.assertEqual(
            [c.args[0] for c in runtime.switch_character.activate_by_index.call_args_list],
            [1, 2],
        )

    def test_infinite_click_binding_falls_back_to_single_native_click(self):
        for value in (float("inf"), -float("inf"), float("nan")):
            with self.subTest(value=str(value)):
                runtime = Mock()
                runtime._running = True
                runtime._admin_ok = True
                runtime._pending_physical_switch = None
                runtime.settings.macro_mode = "macro"
                runtime.settings.clients = ()
                runtime.macro_lock.active_label = None
                runtime.registry.switch_action_for_pressed_keys.return_value = (
                    SimpleNamespace(
                        action_id="switch_click",
                        payload={"click_count": value, "label": "Switch clique"},
                    )
                )
                runtime.switch_click.run_async.return_value = True
                with patch(
                    "app.windows.unity_windows.find_known_client_from_point",
                    return_value=0,
                ):
                    self.assertTrue(
                        AtlasRuntime._handle_mouse_click(runtime, "Left", 10, 20)
                    )
                runtime.switch_click.run_async.assert_called_once_with(
                    "Left", 10, 20, 1, "Switch clique",
                )
                runtime.logger.debug.assert_any_call(
                    "Payload switch invalide: action=%s payload=%s",
                    "switch_click", {"click_count": value, "label": "Switch clique"},
                )

    def test_untrusted_overflowing_hwnds_are_ignored_during_hit_test(self):
        with (
            patch("app.windows.unity_windows.window_from_point",
                  return_value=101) as point,
            patch("app.windows.unity_windows.is_unity_window",
                  return_value=True) as unity,
        ):
            self.assertEqual(find_known_client_from_point(
                20, 30, [float("inf"), float("-inf"), float("nan"), None, 101],
            ), 101)
        point.assert_called_once_with(20, 30)
        unity.assert_called_once_with(101)

    def test_invalid_only_roster_does_not_produce_trusted_source(self):
        with (
            patch("app.windows.unity_windows.window_from_point",
                  return_value=101),
            patch("app.windows.unity_windows.is_unity_window",
                  return_value=True),
        ):
            self.assertEqual(find_known_client_from_point(
                20, 30, (float("inf"), float("-inf"), float("nan"), None),
            ), 0)

    def test_settings_integer_conversion_preserves_default_on_overflow(self):
        for value in (float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=str(value)):
                self.assertEqual(int_value(value, default=37), 37)
        self.assertEqual(int_value("21", default=37), 21)
        self.assertEqual(int_value(0, default=37), 0)


if __name__ == "__main__":
    unittest.main()
