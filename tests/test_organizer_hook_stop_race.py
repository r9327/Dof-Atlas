from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.input.hotkeys import HotkeyRegistry, KBDLLHOOKSTRUCT, WM_KEYDOWN, WM_KEYUP
from app.input.input_state import InputState


class OrganizerKeyboardStopRaceTests(unittest.TestCase):
    def _registry(self):
        return HotkeyRegistry(InputState(), Mock(), Mock())

    def test_live_hook_retains_consumed_release_until_physical_up(self):
        registry = self._registry()
        registry._mirrored_key_ups.add(65)
        registry._thread = Mock()
        registry._thread.is_alive.return_value = True

        with patch("app.input.hotkeys.stop_message_hook") as stop:
            registry.stop()
        stop.assert_called_once_with(registry)
        self.assertEqual(registry._mirrored_key_ups, {65})

        event = KBDLLHOOKSTRUCT()
        event.vkCode = 65
        next_hook = Mock(return_value=37)
        with patch.object(
            ctypes, "windll",
            SimpleNamespace(user32=SimpleNamespace(CallNextHookEx=next_hook)),
            create=True,
        ):
            self.assertEqual(
                registry._keyboard_proc(0, WM_KEYUP, ctypes.addressof(event)), 1,
            )
        next_hook.assert_not_called()
        self.assertEqual(registry._mirrored_key_ups, set())

    def test_stopped_hook_discards_ownership_after_thread_ends(self):
        registry = self._registry()
        registry._mirrored_key_ups.update((65, 66))
        registry._thread = Mock()
        registry._thread.is_alive.return_value = False

        with patch("app.input.hotkeys.stop_message_hook") as stop:
            registry.stop()
            registry.stop()
        self.assertEqual(stop.call_count, 2)
        self.assertEqual(registry._mirrored_key_ups, set())

    def test_live_hook_repeated_stop_never_leaks_held_key(self):
        registry = self._registry()
        registry._mirrored_key_ups.add(65)
        registry._thread = Mock()
        registry._thread.is_alive.return_value = True

        with patch("app.input.hotkeys.stop_message_hook"):
            registry.stop()
            registry.stop()
        self.assertEqual(registry._mirrored_key_ups, {65})
        # The owning thread finally block clears this set on actual exit.


    def test_callback_exceptions_never_release_consumed_keyboard_pair(self):
        # A worker can change the active Unity client between the physical
        # DOWN and UP. Failing hotkey callbacks must not leak the original UP.
        for event_type in (WM_KEYDOWN, WM_KEYUP):
            for failing_callback in (
                "_dispatch_priority_stop", "_dispatch_matching_hotkeys",
            ):
                with self.subTest(event_type=event_type, callback=failing_callback):
                    registry = self._registry()
                    registry._mirrored_key_ups.add(65)
                    event = KBDLLHOOKSTRUCT()
                    event.vkCode = 65
                    next_hook = Mock(return_value=37)
                    with (
                        patch.object(
                            ctypes, "windll",
                            SimpleNamespace(user32=SimpleNamespace(CallNextHookEx=next_hook)),
                            create=True,
                        ),
                        patch.object(
                            registry, failing_callback,
                            side_effect=RuntimeError("injected callback fault"),
                        ),
                    ):
                        self.assertEqual(
                            registry._keyboard_proc(
                                0, event_type, ctypes.addressof(event),
                            ),
                            1,
                        )
                    next_hook.assert_not_called()
                    registry.logger.exception.assert_called()
                    self.assertEqual(
                        registry._mirrored_key_ups,
                        ({65} if event_type == WM_KEYDOWN else set()),
                    )

    def test_consumed_keyboard_pair_stays_consumed_if_logger_fails(self):
        for event_type in (WM_KEYDOWN, WM_KEYUP):
            with self.subTest(event_type=event_type):
                registry = self._registry()
                registry._mirrored_key_ups.add(65)
                registry.logger.exception.side_effect = RuntimeError("logging broken")
                event = KBDLLHOOKSTRUCT()
                event.vkCode = 65
                next_hook = Mock(return_value=37)
                with (
                    patch.object(
                        ctypes, "windll",
                        SimpleNamespace(user32=SimpleNamespace(CallNextHookEx=next_hook)),
                        create=True,
                    ),
                    patch.object(
                        registry, "_dispatch_matching_hotkeys",
                        side_effect=RuntimeError("shortcut callback failed"),
                    ),
                ):
                    self.assertEqual(
                        registry._keyboard_proc(
                            0, event_type, ctypes.addressof(event),
                        ),
                        1,
                    )
                next_hook.assert_not_called()
                self.assertEqual(
                    registry._mirrored_key_ups,
                    ({65} if event_type == WM_KEYDOWN else set()),
                )

    def test_unowned_keyboard_failure_passes_native_when_logger_fails(self):
        registry = self._registry()
        registry.logger.exception.side_effect = RuntimeError("logging broken")
        event = KBDLLHOOKSTRUCT()
        event.vkCode = 65
        next_hook = Mock(return_value=37)
        with (
            patch.object(
                ctypes, "windll",
                SimpleNamespace(user32=SimpleNamespace(CallNextHookEx=next_hook)),
                create=True,
            ),
            patch.object(
                registry, "_dispatch_matching_hotkeys",
                side_effect=RuntimeError("shortcut callback failed"),
            ),
        ):
            self.assertEqual(
                registry._keyboard_proc(0, WM_KEYUP, ctypes.addressof(event)),
                37,
            )
        next_hook.assert_called_once()

    def test_unowned_key_still_passes_through_after_hotkey_failure(self):
        registry = self._registry()
        event = KBDLLHOOKSTRUCT()
        event.vkCode = 65
        next_hook = Mock(return_value=37)
        with (
            patch.object(
                ctypes, "windll",
                SimpleNamespace(user32=SimpleNamespace(CallNextHookEx=next_hook)),
                create=True,
            ),
            patch.object(
                registry, "_dispatch_matching_hotkeys",
                side_effect=RuntimeError("broken shortcut"),
            ),
        ):
            self.assertEqual(
                registry._keyboard_proc(0, WM_KEYUP, ctypes.addressof(event)),
                37,
            )
        next_hook.assert_called_once()
        registry.logger.exception.assert_called()


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
