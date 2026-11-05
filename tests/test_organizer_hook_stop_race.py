from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.input.hotkeys import HotkeyRegistry, KBDLLHOOKSTRUCT, WM_KEYUP
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


if __name__ == "__main__":
    unittest.main()
