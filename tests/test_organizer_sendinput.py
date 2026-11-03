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

    def test_windows_input_layout_and_extended_modifier_flags(self) -> None:
        import os
        if os.name == "nt":
            expected = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
            self.assertEqual(ctypes.sizeof(clicks.INPUT), expected)
        # Right-side modifiers and divide have an E0 scancode in Win32.
        for vk in (0x5C, 0x6F, 0xA3, 0xA5):
            self.assertIn(vk, input_tools.EXTENDED_VKS)
        user32 = Mock()
        user32.MapVirtualKeyW.return_value = 0x38
        observed = []
        def emit(_count, ptr, _size):
            item = ctypes.cast(ptr, ctypes.POINTER(clicks.INPUT)).contents
            observed.append(int(item.union.ki.dwFlags))
            return 1
        user32.SendInput.side_effect = emit
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.object(input_tools.ctypes, "windll",
                         SimpleNamespace(user32=user32), create=True),
        ):
            input_tools.key_down(0xA5)
            input_tools.key_up(0xA5)
        self.assertEqual(observed, [0x0001, 0x0003])

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

    def test_failed_sendinput_includes_immediate_win32_diagnostic(self) -> None:
        user32 = Mock()
        user32.MapVirtualKeyW.return_value = 0x1E
        user32.SendInput.return_value = 0
        kernel32 = Mock()
        kernel32.GetLastError.return_value = 5
        with (
            patch.object(input_tools.os, "name", "nt"),
            patch.object(input_tools.ctypes, "windll",
                         SimpleNamespace(user32=user32, kernel32=kernel32), create=True),
        ):
            with self.assertRaisesRegex(OSError, "win32_error=5"):
                input_tools.key_down(0x41)
        kernel32.GetLastError.assert_called_once_with()

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

    def test_single_key_preserves_hold_exception_if_release_refused(self) -> None:
        with (
            patch.object(input_tools, "_vk", return_value=0x41),
            patch.object(input_tools, "key_down") as down,
            patch.object(input_tools.time, "sleep",
                         side_effect=RuntimeError("hold interrupted")),
            patch.object(input_tools, "key_up",
                         side_effect=OSError("release refused")) as release,
        ):
            with self.assertRaisesRegex(RuntimeError, "hold interrupted"):
                input_tools.press_key("A", hold_ms=100)
        down.assert_called_once_with(0x41)
        release.assert_called_once_with(0x41)

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


    def test_unity_hover_settle_follows_pointer_move_before_mouse_down(self) -> None:
        events: list[tuple[str, int]] = []
        guard = Mock()
        logger = Mock()

        def move(x: int, y: int) -> None:
            self.assertEqual((x, y), (320, 240))
            events.append(("move", x))

        def pause(ms: int, _should_stop) -> bool:
            events.append(("hover", ms))
            return False

        def send(flag: int) -> bool:
            events.append(("input", flag))
            return True

        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos", side_effect=move),
            patch.object(clicks, "wait_ms", side_effect=pause),
            patch.object(clicks, "_send_mouse_flag", side_effect=send),
        ):
            delivered = clicks.send_screen_click(
                320, 240, "Left", 1, 40, 0, 45, 0,
                guard, logger,
            )

        self.assertTrue(delivered)
        self.assertEqual(events, [
            ("move", 320),
            ("hover", 45),
            ("input", clicks.MOUSEEVENTF_LEFTDOWN),
            ("hover", 40),
            ("input", clicks.MOUSEEVENTF_LEFTUP),
        ])
        guard.begin.assert_called_once()
        guard.end.assert_called_once_with(120)

    def test_unity_hover_stop_prevents_mouse_down_after_cursor_move(self) -> None:
        events: list[str] = []
        guard = Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos", side_effect=lambda *_: events.append("move")),
            patch.object(clicks, "wait_ms", side_effect=lambda *_: events.append("stop") or True),
            patch.object(clicks, "_send_mouse_flag", side_effect=AssertionError("clicked after stop")),
        ):
            delivered = clicks.send_screen_click(
                320, 240, "Left", 1, 40, 0, 45, 0,
                guard, Mock(), should_stop=lambda: False,
            )
        self.assertFalse(delivered)
        self.assertEqual(events, ["move", "stop"])
        guard.end.assert_called_once_with(120)


    def test_physical_source_mouse_up_passes_hook_after_replay_starts(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            LLMHF_INJECTED, MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONUP,
        )

        state = InputState()
        logger = logging.getLogger("test_native_switch_click")
        calls = []
        def released(button, x, y):
            calls.append((button, x, y))
            state.begin_mouse_block("Switch clique")
            return True

        hook = MouseHook(
            state, SyntheticInputGuard(logger), logger,
            Mock(return_value=False), release_callback=released,
        )
        mouse = MSLLHOOKSTRUCT()
        mouse.pt.x, mouse.pt.y = 300, 240
        user32 = Mock()
        user32.CallNextHookEx.return_value = 51
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            address = ctypes.addressof(mouse)
            # Native DOWN is not swallowed on the foreground source window.
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, address), 51)
            self.assertFalse(state.is_mouse_blocked())
            # The release callback starts replay, but this same native UP must
            # still reach Unity so world objects can activate.
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, address), 51)
            self.assertEqual(calls, [("Left", 300, 240)])
            self.assertTrue(state.is_mouse_blocked())
            # Other physical events remain protected during synthetic replay.
            self.assertEqual(hook._mouse_proc(0, WM_RBUTTONUP, address), 1)
            # Synthetic output must never retrigger the physical release path.
            mouse.flags = LLMHF_INJECTED
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, address), 51)
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
