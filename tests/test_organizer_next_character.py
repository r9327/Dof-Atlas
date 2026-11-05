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
    def test_organizer_button_invokes_existing_runtime_action(self):
        from app.pages.organizer_page import OrganizerPage
        owner = SimpleNamespace(
            next_character_callback=Mock(), status_callback=Mock(),
        )
        OrganizerPage.activate_next_character(owner)
        owner.next_character_callback.assert_called_once_with()
        owner.status_callback.assert_not_called()

    def test_organizer_button_without_runtime_reports_unavailable(self):
        from app.pages.organizer_page import OrganizerPage
        owner = SimpleNamespace(
            next_character_callback=None, status_callback=Mock(),
        )
        OrganizerPage.activate_next_character(owner)
        owner.status_callback.assert_called_once()

    def test_organizer_refuses_next_hotkey_conflicts_with_existing_actions(self):
        from app.pages.organizer.organizer_hotkeys import OrganizerHotkeysMixin
        from app.constants import KEY_NEXT_CHARACTER_HOTKEY, KEY_CLICK_HOTKEY
        from app.pages.organizer import organizer_hotkeys as hooks

        class Fake(OrganizerHotkeysMixin):
            def __init__(self, kind):
                self.capture_target = {"kind": kind, "slot": None}
                self.profiles = {KEY_NEXT_CHARACTER_HOTKEY: "F9", KEY_CLICK_HOTKEY: "F3"}
                self.status_callback = Mock()
                self.update_global_buttons = Mock()
                self.render_sessions = Mock()
                self.save_profiles = Mock()
                self.export_client_index = Mock()
                self.reload_runtime_callback = Mock()
                self.client_hotkey_owner = Mock(return_value="")
                self._capture_timer = None

            def hotkey_label(self, key):
                return self.profiles.get(key, "")

        for kind in ("click", "double_click", "stop_script", "radial"):
            with self.subTest(kind=kind):
                owner = Fake(kind)
                event = Mock()
                event.key.return_value = 0x78
                event.modifiers.return_value = 0
                with patch.object(hooks, "key_sequence_to_hotkey", return_value="F9"):
                    owner.keyPressEvent(event)
                self.assertEqual(owner.profiles[KEY_NEXT_CHARACTER_HOTKEY], "F9")
                owner.save_profiles.assert_not_called()
                owner.status_callback.assert_called_once()

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
                    activate.assert_called_once_with(
                        slot % count + 1, expected_profile=runtime.settings,
                    )


    def test_next_rejects_profile_reload_while_resolving_active_character(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = Mock()
                runtime.settings = settings(count)
                runtime.macro_lock.should_stop.return_value = False
                old = runtime.settings

                def active_and_reload():
                    # Process checks passed, but Organizer was reloaded while
                    # looking up the currently focused character.
                    runtime.settings = settings(count)
                    return old.clients[-1]

                macro = SwitchCharacterMacro(runtime)
                with (
                    patch("app.macros.switch_character.is_unity_window", return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
                    patch.object(macro, "logical_active_client",
                                 side_effect=active_and_reload),
                    patch.object(macro, "activate_by_index") as activate,
                ):
                    self.assertFalse(macro.activate_next())
                activate.assert_not_called()

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
        activate.assert_called_once_with(
            3, expected_profile=runtime.settings,
        )

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
        runtime.switch_character.activate_next.assert_called_once_with(
            expected_profile=runtime.settings,
        )
        runtime.settings.macro_mode = "mirror"
        AtlasRuntime._handle_hotkey(runtime, "next_character", {})
        runtime.switch_character.activate_next.assert_called_once()
        runtime.settings.macro_mode = "macro"
        runtime.settings.switch_character_enabled = False
        AtlasRuntime._handle_hotkey(runtime, "next_character", {})
        runtime.switch_character.activate_next.assert_called_once()


if __name__ == "__main__":
    unittest.main()
