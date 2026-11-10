from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.input.hotkeys import (
    HotkeyRegistry, KBDLLHOOKSTRUCT, WM_KEYDOWN, WM_KEYUP,
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
                    registry._mirror_toggle_ups.add(0x77)  # F8 toggle
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
                        registry._mirror_toggle_ups,
                        ({0x77} if w_param == WM_KEYDOWN else set()),
                    )

    def test_owned_toggle_up_skips_registry_dispatch_and_remains_consumed(self):
        registry = self._registry()
        registry._mirror_toggle_ups.add(0x77)
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
        self.assertEqual(registry._mirror_toggle_ups, set())
        stop.assert_not_called()
        dispatch.assert_not_called()
        next_hook.assert_not_called()

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
