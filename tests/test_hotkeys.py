from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.input.hotkeys import (
    HotkeyAction, HotkeyRegistry, KBDLLHOOKSTRUCT, WM_KEYDOWN, WM_KEYUP,
)
from app.input.input_state import InputState


class HotkeyRegistryOwnershipTests(unittest.TestCase):
    def _registry(self):
        return HotkeyRegistry(InputState(), Mock(), Mock())

    def test_mirrored_key_pair_survives_state_update_failure(self):
        for w_param in (WM_KEYDOWN, WM_KEYUP):
            for accounts in (2, 4, 6, 8):
                with self.subTest(event=w_param, accounts=accounts):
                    registry = self._registry()
                    registry._mirrored_key_ups.add(65)
                    registry.logger.exception.side_effect = RuntimeError(
                        "diagnostics unavailable",
                    )
                    event = KBDLLHOOKSTRUCT()
                    event.vkCode = 65
                    next_hook = Mock(return_value=37)
                    with (
                        patch.object(
                            registry.input_state, "set_key",
                            side_effect=RuntimeError("key state unavailable"),
                        ),
                        patch.object(
                            ctypes, "windll",
                            SimpleNamespace(user32=SimpleNamespace(
                                CallNextHookEx=next_hook,
                            )),
                            create=True,
                        ),
                    ):
                        self.assertEqual(
                            registry._keyboard_proc(
                                0, w_param, ctypes.addressof(event),
                            ),
                            1,
                        )
                    next_hook.assert_not_called()
                    registry.logger.exception.assert_called_once()
                    self.assertEqual(
                        registry._mirrored_key_ups,
                        ({65} if w_param == WM_KEYDOWN else set()),
                    )

    def test_mirror_toggle_pair_survives_input_state_failure(self):
        for w_param in (WM_KEYDOWN, WM_KEYUP):
            for accounts in (2, 4, 6, 8):
                with self.subTest(event=w_param, accounts=accounts):
                    registry = self._registry()
                    registry._command_key_ups.add(0x77)  # F8 toggle
                    registry.logger.exception.side_effect = RuntimeError(
                        "diagnostics unavailable",
                    )
                    event = KBDLLHOOKSTRUCT()
                    event.vkCode = 0x77
                    next_hook = Mock(return_value=37)
                    with (
                        patch.object(
                            registry.input_state, "set_key",
                            side_effect=RuntimeError("key state unavailable"),
                        ),
                        patch.object(
                            ctypes, "windll",
                            SimpleNamespace(user32=SimpleNamespace(
                                CallNextHookEx=next_hook,
                            )),
                            create=True,
                        ),
                    ):
                        self.assertEqual(
                            registry._keyboard_proc(
                                0, w_param, ctypes.addressof(event),
                            ),
                            1,
                        )
                    next_hook.assert_not_called()
                    self.assertEqual(
                        registry._command_key_ups,
                        ({0x77} if w_param == WM_KEYDOWN else set()),
                    )

    def test_owned_toggle_up_skips_registry_dispatch_and_remains_consumed(self):
        registry = self._registry()
        registry._command_key_ups.add(0x77)
        event = KBDLLHOOKSTRUCT()
        event.vkCode = 0x77
        next_hook = Mock(return_value=37)
        with (
            patch.object(registry, "_dispatch_priority_stop") as stop,
            patch.object(registry, "_dispatch_matching_hotkeys") as dispatch,
            patch.object(
                ctypes, "windll",
                SimpleNamespace(user32=SimpleNamespace(
                    CallNextHookEx=next_hook,
                )),
                create=True,
            ),
        ):
            self.assertEqual(
                registry._keyboard_proc(0, WM_KEYUP, ctypes.addressof(event)),
                1,
            )
        self.assertEqual(registry._command_key_ups, set())
        stop.assert_not_called()
        dispatch.assert_not_called()
        next_hook.assert_not_called()

    def test_owned_toggle_down_cannot_leak_after_dispatch_failure(self):
        registry = self._registry()
        registry._command_key_ups.add(0x77)
        event = KBDLLHOOKSTRUCT()
        event.vkCode = 0x77
        next_hook = Mock(return_value=37)
        with (
            patch.object(
                registry, "_dispatch_matching_hotkeys",
                side_effect=RuntimeError("hotkey dispatch failed"),
            ),
            patch.object(
                ctypes, "windll",
                SimpleNamespace(user32=SimpleNamespace(
                    CallNextHookEx=next_hook,
                )),
                create=True,
            ),
        ):
            self.assertEqual(
                registry._keyboard_proc(0, WM_KEYDOWN, ctypes.addressof(event)),
                1,
            )
        self.assertEqual(registry._command_key_ups, {0x77})
        next_hook.assert_not_called()

    def test_first_mirror_toggle_down_remains_owned_if_callback_raises(self):
        registry = self._registry()
        report = registry.register_hotkeys([HotkeyAction(
            action_id="mirror_toggle", label="Activer Miroir",
            hotkey_text="F8", kind="press",
        )])
        self.assertTrue(report.ok)
        registry.callback.side_effect = RuntimeError("activation partial failure")
        event = KBDLLHOOKSTRUCT()
        event.vkCode = 0x77
        next_hook = Mock(return_value=37)
        with patch.object(
            ctypes, "windll",
            SimpleNamespace(user32=SimpleNamespace(
                CallNextHookEx=next_hook,
            )),
            create=True,
        ):
            self.assertEqual(
                registry._keyboard_proc(0, WM_KEYDOWN, ctypes.addressof(event)),
                1,
            )
            self.assertEqual(registry._command_key_ups, {0x77})
            self.assertEqual(
                registry._keyboard_proc(0, WM_KEYUP, ctypes.addressof(event)),
                1,
            )
        self.assertEqual(registry._command_key_ups, set())
        next_hook.assert_not_called()

    def test_command_key_pairs_are_consumed_and_rearm_across_repeated_taps(self):
        for action_id, binding, vk in (
            ("stop_script", "F12", 0x7B),
            ("mirror_toggle", "F8", 0x77),
            ("next_character", "F9", 0x78),
            ("previous_character", "F10", 0x79),
        ):
            with self.subTest(action=action_id):
                registry = self._registry()
                report = registry.register_hotkeys([HotkeyAction(
                    action_id=action_id, label=action_id,
                    hotkey_text=binding, kind="press",
                )])
                self.assertTrue(report.ok)
                event = KBDLLHOOKSTRUCT()
                event.vkCode = vk
                next_hook = Mock(return_value=37)
                with patch.object(
                    ctypes, "windll",
                    SimpleNamespace(user32=SimpleNamespace(
                        CallNextHookEx=next_hook,
                    )),
                    create=True,
                ):
                    for _ in range(2):
                        self.assertEqual(
                            registry._keyboard_proc(0, WM_KEYDOWN, ctypes.addressof(event)), 1,
                        )
                        self.assertEqual(
                            registry._keyboard_proc(0, WM_KEYUP, ctypes.addressof(event)), 1,
                        )
                self.assertEqual(
                    [call.args[0] for call in registry.callback.call_args_list],
                    [action_id, action_id],
                )
                next_hook.assert_not_called()
                self.assertEqual(registry._command_key_ups, set())
                self.assertEqual(registry.input_state.active_hotkeys, set())

    def test_plain_letter_remains_native_when_only_navigation_is_registered(self):
        registry = self._registry()
        registry.register_hotkeys([HotkeyAction(
            action_id="next_character", label="Suivant",
            hotkey_text="F9", kind="press",
        )])
        event = KBDLLHOOKSTRUCT()
        event.vkCode = 0x41  # A: gameplay and ordinary typing stay native
        next_hook = Mock(return_value=37)
        with patch.object(
            ctypes, "windll",
            SimpleNamespace(user32=SimpleNamespace(
                CallNextHookEx=next_hook,
            )),
            create=True,
        ):
            self.assertEqual(registry._keyboard_proc(0, WM_KEYDOWN, ctypes.addressof(event)), 37)
            self.assertEqual(registry._keyboard_proc(0, WM_KEYUP, ctypes.addressof(event)), 37)
        registry.callback.assert_not_called()
        self.assertEqual(registry._command_key_ups, set())
        self.assertEqual(next_hook.call_count, 2)

    def test_unowned_key_state_failure_remains_native(self):
        registry = self._registry()
        event = KBDLLHOOKSTRUCT()
        event.vkCode = 65
        next_hook = Mock(return_value=37)
        with (
            patch.object(
                registry.input_state, "set_key",
                side_effect=RuntimeError("bad keyboard state"),
            ),
            patch.object(
                ctypes, "windll",
                SimpleNamespace(user32=SimpleNamespace(CallNextHookEx=next_hook)),
                create=True,
            ),
        ):
            self.assertEqual(
                registry._keyboard_proc(
                    0, WM_KEYUP, ctypes.addressof(event),
                ),
                37,
            )
        next_hook.assert_called_once()
        self.assertEqual(registry._mirrored_key_ups, set())


if __name__ == "__main__":
    unittest.main()
