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
        clients=clients, primary_handle=clients[0].handle if clients else 0,
        timings=Mock(), macro_mode=mode, switch_character_enabled=True,
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

    def test_hotkey_registered_when_enabled_in_macro_or_disarmed_mirror(self):
        config = settings(4)
        actions = build_hotkey_actions(config)
        self.assertEqual([action.action_id for action in actions], ["next_character"])
        self.assertEqual(actions[0].hotkey_text, "F9")
        self.assertEqual(
            [action.action_id for action in build_hotkey_actions(settings(4, mode="mirror"))],
            ["next_character"],
        )
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
                        expected_context=(runtime.settings.primary_handle, "macro"),
                    )


    def test_previous_wraps_in_order_for_two_four_six_eight(self):
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
                        self.assertTrue(macro.activate_previous())
                    activate.assert_called_once_with(
                        (slot - 2) % count + 1, expected_profile=runtime.settings,
                        expected_context=(runtime.settings.primary_handle, "macro"),
                    )

    def test_previous_and_mirror_hotkeys_do_not_enable_passive_mirror(self):
        config = settings(4)
        config.previous_character_hotkey = "F8"
        self.assertEqual(
            [action.action_id for action in build_hotkey_actions(config)],
            ["next_character", "previous_character"],
        )
        config.macro_mode = "mirror"
        config.mirror_toggle_hotkey = "CTRL+F8"
        self.assertEqual(
            [action.action_id for action in build_hotkey_actions(config)],
            ["mirror_toggle", "next_character", "previous_character"],
        )
        config.stop_hotkey = "F12"
        self.assertEqual(
            [action.action_id for action in build_hotkey_actions(config)],
            ["stop_script", "mirror_toggle", "next_character", "previous_character"],
        )

    def test_previous_button_uses_existing_runtime_callback(self):
        from app.pages.organizer_page import OrganizerPage
        owner = SimpleNamespace(
            previous_character_callback=Mock(), status_callback=Mock(),
        )
        OrganizerPage.activate_previous_character(owner)
        owner.previous_character_callback.assert_called_once_with()
        owner.status_callback.assert_not_called()

    def test_previous_without_known_foreground_selects_last_verified_client(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = Mock()
                runtime.settings = settings(count)
                runtime.macro_lock.should_stop.return_value = False
                macro = SwitchCharacterMacro(runtime)
                with (
                    patch("app.macros.switch_character.is_unity_window", return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
                    patch.object(macro, "logical_active_client", return_value=None),
                    patch.object(macro, "activate_by_index", return_value=True) as activate,
                ):
                    self.assertTrue(macro.activate_previous())
                activate.assert_called_once_with(
                    count, expected_profile=runtime.settings,
                    expected_context=(runtime.settings.primary_handle, "macro"),
                )

    def test_stop_blocks_both_directions_before_native_window_probes(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                runtime = Mock()
                runtime.settings = settings(count)
                runtime.macro_lock.should_stop.return_value = True
                macro = SwitchCharacterMacro(runtime)
                with patch("app.macros.switch_character.is_unity_window") as unity:
                    self.assertFalse(macro.activate_next())
                    self.assertFalse(macro.activate_previous())
                unity.assert_not_called()
                runtime._spawn_macro.assert_not_called()

    def test_mirror_activation_hotkey_fires_once_per_press_and_exact_modifiers(self):
        from app.input.hotkeys import HotkeyRegistry
        from app.input.input_state import InputState

        config = settings(4, mode="mirror")
        config.mirror_toggle_hotkey = "CTRL+F8"
        state = InputState()
        callback = Mock()
        registry = HotkeyRegistry(state, Mock(), callback)
        registry.register_hotkeys(build_hotkey_actions(config))
        # Extra ALT is not a valid consent gesture for CTRL+F8.
        for vk in (0x11, 0x12, 0x77):
            state.set_key(vk, True)
        registry._dispatch_matching_hotkeys()
        callback.assert_not_called()
        state.set_key(0x12, False)
        registry._dispatch_matching_hotkeys()
        callback.assert_called_once_with("mirror_toggle", {})
        registry._dispatch_matching_hotkeys()
        callback.assert_called_once()
        state.set_key(0x77, False)
        registry._dispatch_matching_hotkeys()
        state.set_key(0x77, True)
        registry._dispatch_matching_hotkeys()
        self.assertEqual(callback.call_count, 2)

    def test_runtime_routes_previous_and_mirror_toggle_without_implicit_capture(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                profile = settings(count)
                runtime = SimpleNamespace(
                    settings=profile, _running=True, _admin_ok=True,
                    macro_lock=SimpleNamespace(
                        emergency_latched=False, active_label="",
                    ),
                    switch_character=SimpleNamespace(
                        activate_previous=Mock(return_value=True),
                    ),
                    toggle_mirror=Mock(return_value=True),
                    _mirror_armed=False, _emit_status=Mock(),
                )
                AtlasRuntime._handle_hotkey(runtime, "previous_character", {})
                runtime.switch_character.activate_previous.assert_called_once_with(
                    expected_profile=profile,
                )
                profile.macro_mode = "mirror"
                AtlasRuntime._handle_hotkey(runtime, "mirror_toggle", {})
                runtime.toggle_mirror.assert_called_once_with()
                runtime.switch_character.activate_previous.reset_mock()
                AtlasRuntime._handle_hotkey(runtime, "previous_character", {})
                runtime.switch_character.activate_previous.assert_called_once_with(
                    expected_profile=profile,
                )
                runtime.switch_character.activate_previous.reset_mock()
                runtime._mirror_armed = True
                AtlasRuntime._handle_hotkey(runtime, "previous_character", {})
                runtime.switch_character.activate_previous.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    "Arrêter Miroir avant de changer de personnage."
                )

    def test_mirror_mode_next_action_is_available_only_while_disarmed(self):
        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                profile = settings(count, mode="mirror")
                runtime = SimpleNamespace(
                    settings=profile, _running=True, _admin_ok=True,
                    _mirror_armed=True, _emit_status=Mock(),
                    macro_lock=SimpleNamespace(
                        emergency_latched=False, active_label="",
                    ),
                    switch_character=SimpleNamespace(
                        activate_next=Mock(return_value=True),
                    ),
                )
                AtlasRuntime._handle_hotkey(runtime, "next_character", {})
                runtime.switch_character.activate_next.assert_not_called()
                runtime._emit_status.assert_called_once_with(
                    "Arrêter Miroir avant de changer de personnage."
                )
                runtime._mirror_armed = False
                AtlasRuntime._handle_hotkey(runtime, "next_character", {})
                runtime.switch_character.activate_next.assert_called_once_with(
                    expected_profile=profile,
                )
                runtime.switch_character.activate_next.reset_mock()
                profile.switch_character_enabled = False
                AtlasRuntime._handle_hotkey(runtime, "next_character", {})
                runtime.switch_character.activate_next.assert_not_called()

    def test_direct_activation_ignores_corrupt_numeric_slot_aliases_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = Mock()
                profile = settings(count)
                # Both aliases compare equal to integer 1 in Python. Neither
                # may shadow the actual Organizer slot, even with a DOFUS HWND.
                profile.clients.insert(0, SimpleNamespace(
                    index=True, handle=900, display_name="Bad bool",
                ))
                profile.clients.insert(1, SimpleNamespace(
                    index=1.0, handle=901, display_name="Bad float",
                ))
                runtime.settings = profile
                runtime.macro_lock.should_stop.return_value = False
                runtime._spawn_macro.return_value = True
                macro = SwitchCharacterMacro(runtime)
                with (
                    patch("app.macros.switch_character.is_unity_window", return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
                    patch("app.macros.switch_character.activate_window", return_value=True) as focus,
                    patch("app.macros.switch_character.foreground_window", return_value=101),
                ):
                    self.assertTrue(macro.activate_by_index("1"))
                    runtime._spawn_macro.assert_called_once()
                    runtime._spawn_macro.call_args.args[1]()
                self.assertEqual(focus.call_args.args[0], 101)
                self.assertEqual(runtime.active_client_handle, 101)

    def test_direct_activation_refuses_out_of_range_or_corrupt_only_slot(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = Mock()
                profile = settings(count)
                profile.clients[0].index = True
                runtime.settings = profile
                macro = SwitchCharacterMacro(runtime)
                for raw in (0, -1, 9, "9", 2**64, 1):
                    with self.subTest(raw=repr(raw)):
                        self.assertFalse(macro.activate_by_index(raw))
                runtime._spawn_macro.assert_not_called()

    def test_next_skips_invalid_slot_but_refuses_duplicate_live_slot(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = Mock()
                profile = settings(count)
                runtime.settings = profile
                runtime.macro_lock.should_stop.return_value = False
                macro = SwitchCharacterMacro(runtime)
                profile.clients.insert(0, SimpleNamespace(index=1.0, handle=999))
                with (
                    patch("app.macros.switch_character.is_unity_window", return_value=True) as unity,
                    patch("app.macros.switch_character.is_dofus_unity_process", return_value=True),
                    patch.object(macro, "logical_active_client", return_value=profile.clients[1]),
                    patch.object(macro, "activate_by_index", return_value=True) as activate,
                ):
                    self.assertTrue(macro.activate_next())
                    activate.assert_called_once_with(
                        2, expected_profile=profile,
                        expected_context=(profile.primary_handle, "macro"),
                    )
                    self.assertNotIn(999, [call.args[0] for call in unity.call_args_list])
                    # Two distinct authenticated clients claiming slot 1 make
                    # the character-cycle order ambiguous: never choose one.
                    profile.clients[0].index = 1
                    activate.reset_mock()
                    self.assertFalse(macro.activate_next())
                    activate.assert_not_called()

    def test_direct_activation_cancels_when_slot_turns_into_numeric_alias(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = Mock()
                profile = settings(count)
                runtime.settings = profile
                runtime.macro_lock.should_stop.return_value = False
                runtime._spawn_macro.return_value = True
                macro = SwitchCharacterMacro(runtime)
                self.assertTrue(macro.activate_by_index(1))
                queued_worker = runtime._spawn_macro.call_args.args[1]

                def replace_slot_during_process_check(_hwnd):
                    profile.clients[0].index = 1.0
                    return True

                with (
                    patch("app.macros.switch_character.is_unity_window", return_value=True),
                    patch("app.macros.switch_character.is_dofus_unity_process",
                          side_effect=replace_slot_during_process_check),
                    patch("app.macros.switch_character.activate_window") as focus,
                ):
                    queued_worker()
                focus.assert_not_called()
                self.assertIsNot(runtime.active_client_handle, 101)

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
            expected_context=(runtime.settings.primary_handle, "macro"),
        )

    def test_next_rejects_obsolete_callback_before_native_scan_2_to_8(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                runtime = Mock()
                old = settings(count)
                runtime.settings = settings(count)
                runtime.macro_lock.should_stop.return_value = False
                macro = SwitchCharacterMacro(runtime)
                with (
                    patch("app.macros.switch_character.is_unity_window") as unity,
                    patch("app.macros.switch_character.is_dofus_unity_process") as dofus,
                    patch.object(macro, "activate_by_index") as activate,
                ):
                    self.assertFalse(macro.activate_next(expected_profile=old))
                unity.assert_not_called()
                dofus.assert_not_called()
                activate.assert_not_called()

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


    def test_busy_hotkey_next_character_skips_roster_scanning_2_to_8(self):
        for count in (2, 4, 6, 8):
            for busy in ("Switch clique", "Auto zaap", "Auto groupe", "Miroir"):
                with self.subTest(clients=count, busy=busy):
                    runtime = Mock()
                    runtime._running = True
                    runtime._admin_ok = True
                    runtime.settings = settings(count)
                    runtime.macro_lock.active_label = busy
                    AtlasRuntime._handle_hotkey(runtime, "next_character", {})
                    runtime.switch_character.activate_next.assert_not_called()
                    runtime.switch_character.activate_by_index.assert_not_called()

    def test_runtime_handler_honors_mode_and_existing_toggle(self):
        runtime = Mock()
        runtime._running = True
        runtime._admin_ok = True
        runtime.settings = settings(4)
        runtime.macro_lock.active_label = ""
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
