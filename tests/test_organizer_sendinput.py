from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from app.input import hotkeys as _hotkeys  # preload before monkeypatching os.name
from app.macros import input_tools
from app.windows import clicks


class OrganizerSendInputTests(unittest.TestCase):
    def test_keyboard_union_keeps_mouse_sized_native_input(self) -> None:
        self.assertGreaterEqual(ctypes.sizeof(clicks.INPUT_UNION), ctypes.sizeof(clicks.MOUSEINPUT))
        self.assertGreaterEqual(ctypes.sizeof(clicks.INPUT_UNION), ctypes.sizeof(clicks.KEYBDINPUT))

    def test_key_down_and_up_use_sendinput_with_extended_key_and_marker(self) -> None:
        recorded = []
        user32 = Mock()
        user32.MapVirtualKeyW.return_value = 0x47

        def emit(count, ptr, size):
            item = ctypes.cast(ptr, ctypes.POINTER(clicks.INPUT)).contents
            self.assertEqual(count, 1)
            self.assertEqual(size, ctypes.sizeof(clicks.INPUT))
            recorded.append((
                int(item.type),
                int(item.union.ki.wVk),
                int(item.union.ki.wScan),
                int(item.union.ki.dwFlags),
                int(item.union.ki.dwExtraInfo or 0),
            ))
            return 1

        user32.SendInput.side_effect = emit
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.object(input_tools.ctypes, "windll", SimpleNamespace(user32=user32), create=True),
        ):
            input_tools.key_down(0x24)
            input_tools.key_up(0x24)

        marker = input_tools.ATLAS_SYNTHETIC_KEYBOARD_EXTRA_INFO
        self.assertEqual(recorded, [
            (1, 0x24, 0x47, 0x0001, marker),
            (1, 0x24, 0x47, 0x0003, marker),
        ])

    def test_failed_sendinput_does_not_claim_key_delivered(self) -> None:
        user32 = Mock()
        user32.MapVirtualKeyW.return_value = 0x1E
        user32.SendInput.return_value = 0
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.object(input_tools.ctypes, "windll", SimpleNamespace(user32=user32), create=True),
        ):
            with self.assertRaisesRegex(OSError, "SendInput refused"):
                input_tools.key_down(0x41)

    def test_non_windows_path_never_sends_synthetic_input(self) -> None:
        with patch.object(input_tools.os, "name", "posix"):
            with patch.object(input_tools, "_configure_keyboard_api", side_effect=AssertionError("wrong OS")):
                input_tools.key_down(0x41)
                input_tools.key_up(0x41)

    def test_hotkey_releases_first_key_if_second_down_fails(self) -> None:
        with (
            patch.object(input_tools, "_vk", side_effect=[0x11, 0x41]),
            patch.object(input_tools, "key_down", side_effect=[None, OSError("blocked")]) as down,
            patch.object(input_tools, "key_up") as up,
        ):
            with self.assertRaisesRegex(OSError, "blocked"):
                input_tools.press_hotkey("CTRL", "A")
        self.assertEqual(down.call_args_list, [call(0x11), call(0x41)])
        up.assert_called_once_with(0x11)

    def test_original_sendinput_error_survives_release_error(self) -> None:
        with (
            patch.object(input_tools, "_vk", side_effect=[0x11, 0x41]),
            patch.object(input_tools, "key_down",
                         side_effect=[None, OSError("original keyboard failure")]),
            patch.object(input_tools, "key_up",
                         side_effect=OSError("cleanup failure")) as release,
        ):
            with self.assertRaisesRegex(OSError, "original keyboard failure"):
                input_tools.press_hotkey("CTRL", "A")
        release.assert_called_once_with(0x11)

    def test_emergency_release_attempts_every_button_and_modifier(self) -> None:
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.object(clicks, "_send_mouse_flag", side_effect=[False, True, True]) as mouse,
            patch.object(input_tools, "key_up", side_effect=[OSError("blocked"), None, None]) as key,
        ):
            input_tools.release_common_inputs()
        self.assertEqual(mouse.call_args_list, [call(0x0004), call(0x0010), call(0x0040)])
        self.assertEqual(key.call_count, 3)


if __name__ == "__main__":
    unittest.main()
