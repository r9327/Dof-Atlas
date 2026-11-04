from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.runtime_state import AtlasRuntime
from app.input.hotkeys import build_hotkey_actions
from app.macros.switch_character import SwitchCharacterMacro


def settings(count: int, *, hotkey: str = "F9", mode: str = "macro"):
    clients = [
        SimpleNamespace(index=i, handle=100 + i, display_name=f"Client {i}", binding="")
        for i in range(1, count + 1)
    ]
    return SimpleNamespace(
        clients=clients, macro_mode=mode, switch_character_enabled=True,
        next_character_hotkey=hotkey, switch_click_enabled=False,
        switch_click_hotkey="", switch_double_click_enabled=False,
        switch_double_click_hotkey="", movement_enabled=False, stop_hotkey="",
    )


class NextCharacterTests(unittest.TestCase):
    def test_hotkey_registered_only_in_macro_with_enabled_setting(self):
        config = settings(4)
        actions = build_hotkey_actions(config)
        self.assertEqual([action.action_id for action in actions], ["next_character"])
        self.assertEqual(actions[0].hotkey_text, "F9")
        self.assertEqual(build_hotkey_actions(settings(4, mode="mirror")), [])
        self.assertEqual(build_hotkey_actions(settings(4, hotkey="")), [])
        config.switch_character_enabled = False
        self.assertEqual(build_hotkey_actions(config), [])

    def test_next_wraps_in_order_for_two_four_six_eight(self):
        for count in (2, 4, 6, 8):
            for slot in range(1, count + 1):
                with self.subTest(count=count, slot=slot):
                    runtime = Mock()
                    runtime.settings = settings(count)
                    runtime.macro_lock.should_stop.return_value = False
                    macro = SwitchCharacterMacro(runtime)
                    with (
                        patch("app.macros.switch_character.is_unity_window", return_value=True),
                        patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
                        patch.object(macro, "logical_active_client",
                                     return_value=runtime.settings.clients[slot - 1]),
                        patch.object(macro, "activate_by_index", return_value=True) as activate,
                    ):
                        self.assertTrue(macro.activate_next())
                    activate.assert_called_once_with(slot % count + 1)

    def test_closed_client_skipped_without_false_activation(self):
        runtime = Mock()
        runtime.settings = settings(4)
        runtime.macro_lock.should_stop.return_value = False
        macro = SwitchCharacterMacro(runtime)
        with (
            patch("app.macros.switch_character.is_unity_window", return_value=True),
            patch("app.macros.switch_character.is_dofus_unity_process",
                  side_effect=lambda hwnd: hwnd != 102),
            patch.object(macro, "logical_active_client",
                         return_value=runtime.settings.clients[0]),
            patch.object(macro, "activate_by_index", return_value=True) as activate,
        ):
            self.assertTrue(macro.activate_next())
        activate.assert_called_once_with(3)

    def test_zero_or_one_live_client_cannot_start_worker(self):
        for count in (0, 1):
            runtime = Mock()
            runtime.settings = settings(count)
            runtime.macro_lock.should_stop.return_value = False
            macro = SwitchCharacterMacro(runtime)
            with (
                patch("app.macros.switch_character.is_unity_window", return_value=True),
                patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
                patch.object(macro, "activate_by_index") as activate,
            ):
                self.assertFalse(macro.activate_next())
            activate.assert_not_called()

    def test_stop_before_hotkey_never_probes_native_windows(self):
        runtime = Mock()
        runtime.settings = settings(8)
        runtime.macro_lock.should_stop.return_value = True
        macro = SwitchCharacterMacro(runtime)
        with (
            patch("app.macros.switch_character.is_unity_window") as unity,
            patch("app.macros.switch_character.is_dofus_unity_process") as dofus,
        ):
            self.assertFalse(macro.activate_next())
        unity.assert_not_called()
        dofus.assert_not_called()

    def test_runtime_handler_honors_mode_and_existing_toggle(self):
        runtime = Mock()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings = settings(4)
        AtlasRuntime._handle_hotkey(runtime, "next_character", {})
        runtime.switch_character.activate_next.assert_called_once_with()
        runtime.settings.macro_mode = "mirror"
        AtlasRuntime._handle_hotkey(runtime, "next_character", {})
        runtime.switch_character.activate_next.assert_called_once()
        runtime.settings.macro_mode = "macro"
        runtime.settings.switch_character_enabled = False
        AtlasRuntime._handle_hotkey(runtime, "next_character", {})
        runtime.switch_character.activate_next.assert_called_once()


if __name__ == "__main__":
    unittest.main()
