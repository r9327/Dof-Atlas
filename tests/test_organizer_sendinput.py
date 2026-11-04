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
        events = []
        guard = Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos",
                         side_effect=lambda *_: events.append("move")),
            patch.object(clicks, "wait_ms",
                         side_effect=lambda ms, _: events.append(("hover", ms)) or False),
            patch.object(clicks, "_send_mouse_flag",
                         side_effect=lambda flag: events.append(("input", flag)) or True),
        ):
            self.assertTrue(clicks.send_screen_click(
                320, 240, "Left", 1, 40, 0, 45, 0, guard, Mock(),
            ))
        self.assertEqual(events, [
            "move", ("hover", 45),
            ("input", clicks.MOUSEEVENTF_LEFTDOWN),
            ("hover", 40),
            ("input", clicks.MOUSEEVENTF_LEFTUP),
        ])
        guard.end.assert_called_once_with(120)

    def test_unity_hover_stop_after_move_sends_no_down(self) -> None:
        events = []
        guard = Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos",
                         side_effect=lambda *_: events.append("move")),
            patch.object(clicks, "wait_ms",
                         side_effect=lambda *_: events.append("stop") or True),
            patch.object(clicks, "_send_mouse_flag",
                         side_effect=AssertionError("clicked after stop")),
        ):
            self.assertFalse(clicks.send_screen_click(
                320, 240, "Left", 1, 40, 0, 45, 0,
                guard, Mock(), should_stop=lambda: False,
            ))
        self.assertEqual(events, ["move", "stop"])
        guard.end.assert_called_once_with(120)


    def test_failed_mouse_up_retries_and_reports_final_failure(self) -> None:
        for retry_works in (True, False):
            with self.subTest(retry_works=retry_works):
                guard = Mock()
                logger = Mock()
                with (
                    patch.object(clicks.os, "name", "nt"),
                    patch.object(clicks, "set_cursor_pos"),
                    patch.object(clicks, "_send_mouse_flag",
                                 side_effect=[True, False, retry_works]) as sender,
                ):
                    result = clicks.send_screen_click(
                        300, 200, "Left", 1, 0, 0, 0, 0, guard, logger,
                    )
                self.assertFalse(result)
                self.assertEqual(
                    [c.args[0] for c in sender.call_args_list],
                    [clicks.MOUSEEVENTF_LEFTDOWN,
                     clicks.MOUSEEVENTF_LEFTUP,
                     clicks.MOUSEEVENTF_LEFTUP],
                )
                guard.end.assert_called_once_with(120)
                if retry_works:
                    logger.warning.assert_not_called()
                else:
                    logger.warning.assert_called_once_with(
                        "Relachement souris de secours refuse: button=%s",
                        "Left",
                    )

    def test_refused_mouse_down_does_not_send_unpaired_up(self) -> None:
        sent = []
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos"),
            patch.object(clicks, "_send_mouse_flag",
                         side_effect=lambda flag: sent.append(flag) or False),
        ):
            result = clicks.send_screen_click(
                300, 200, "Left", 1, 0, 0, 0, 0, Mock(), Mock(),
            )
        self.assertFalse(result)
        self.assertEqual(sent, [clicks.MOUSEEVENTF_LEFTDOWN])

    def test_second_mouse_down_refusal_does_not_emit_second_up(self) -> None:
        sent = []
        def sender(flag):
            sent.append(flag)
            return flag != clicks.MOUSEEVENTF_LEFTDOWN or len(sent) == 1

        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "set_cursor_pos"),
            patch.object(clicks, "_send_mouse_flag", side_effect=sender),
        ):
            result = clicks.send_screen_click(
                300, 200, "Left", 2, 0, 0, 0, 0, Mock(), Mock(),
            )
        self.assertFalse(result)
        self.assertEqual(sent, [
            clicks.MOUSEEVENTF_LEFTDOWN,
            clicks.MOUSEEVENTF_LEFTUP,
            clicks.MOUSEEVENTF_LEFTDOWN,
        ])

    def test_client_click_aborts_on_focus_theft_during_hover(self) -> None:
        focused = [202]
        guard = Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "is_unity_window", return_value=True),
            patch.object(clicks, "clamp_client_point", return_value=(10, 20)),
            patch.object(clicks, "client_to_screen", return_value=(300, 200)),
            patch.object(clicks, "foreground_window",
                         side_effect=lambda: focused[0]),
            patch.object(clicks, "set_cursor_pos",
                         side_effect=lambda *_: focused.__setitem__(0, 999)),
            patch.object(clicks, "wait_ms",
                         side_effect=lambda ms, stop: stop()),
            patch.object(clicks, "_send_mouse_flag") as sender,
        ):
            result = clicks.send_client_click(
                202, 10, 20, "Left", 1, 35, 0, 50, 0, guard, Mock(),
                should_stop=lambda: False,
            )
        self.assertFalse(result)
        sender.assert_not_called()
        guard.end.assert_called_once_with(120)

    def test_client_click_respects_emergency_stop_before_cursor_move(self) -> None:
        guard = Mock()
        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "is_unity_window", return_value=True),
            patch.object(clicks, "clamp_client_point", return_value=(10, 20)),
            patch.object(clicks, "client_to_screen", return_value=(300, 200)),
            patch.object(clicks, "foreground_window",
                         side_effect=AssertionError("focus after stop")),
            patch.object(clicks, "set_cursor_pos") as move,
            patch.object(clicks, "_send_mouse_flag") as sender,
        ):
            result = clicks.send_client_click(
                202, 10, 20, "Right", 1, 35, 0, 50, 0, guard, Mock(),
                should_stop=lambda: True,
            )
        self.assertFalse(result)
        move.assert_not_called()
        sender.assert_not_called()
        guard.end.assert_called_once_with(120)

    def test_client_double_click_checks_focus_before_second_down(self) -> None:
        focused = [202]
        events = []
        guard = Mock()
        def send(flag):
            events.append(flag)
            if flag == clicks.MOUSEEVENTF_LEFTUP:
                focused[0] = 999
            return True

        with (
            patch.object(clicks.os, "name", "nt"),
            patch.object(clicks, "is_unity_window", return_value=True),
            patch.object(clicks, "clamp_client_point", return_value=(10, 20)),
            patch.object(clicks, "client_to_screen", return_value=(300, 200)),
            patch.object(clicks, "foreground_window",
                         side_effect=lambda: focused[0]),
            patch.object(clicks, "set_cursor_pos"),
            patch.object(clicks, "wait_ms",
                         side_effect=lambda ms, stop: stop()),
            patch.object(clicks, "_send_mouse_flag", side_effect=send),
        ):
            result = clicks.send_client_click(
                202, 10, 20, "Left", 2, 35, 60, 50, 0, guard, Mock(),
                should_stop=lambda: False,
            )
        self.assertFalse(result)
        self.assertEqual(events, [
            clicks.MOUSEEVENTF_LEFTDOWN,
            clicks.MOUSEEVENTF_LEFTUP,
        ])
        guard.end.assert_called_once_with(120)

    def test_physical_source_up_reaches_unity_after_replay_starts(self) -> None:
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
            addr = ctypes.addressof(mouse)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 51)
            self.assertFalse(state.is_mouse_blocked())
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 51)
            self.assertEqual(calls, [("Left", 300, 240)])
            self.assertTrue(state.is_mouse_blocked())
            self.assertEqual(hook._mouse_proc(0, WM_RBUTTONUP, addr), 1)
            # Synthesized releases never trigger physical replay.
            mouse.flags = LLMHF_INJECTED
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 51)
            self.assertEqual(len(calls), 1)

    def test_native_up_from_press_before_busy_worker_is_not_swallowed(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP,
            WM_RBUTTONDOWN, WM_RBUTTONUP,
            WM_MBUTTONDOWN, WM_MBUTTONUP,
            WM_XBUTTONDOWN, WM_XBUTTONUP,
        )

        for down, up in (
            (WM_LBUTTONDOWN, WM_LBUTTONUP),
            (WM_RBUTTONDOWN, WM_RBUTTONUP),
            (WM_MBUTTONDOWN, WM_MBUTTONUP),
            (WM_XBUTTONDOWN, WM_XBUTTONUP),
        ):
            with self.subTest(down=down):
                state = InputState()
                logger = logging.getLogger("test_pressed_before_busy")
                callback = Mock(return_value=False)
                release = Mock(return_value=False)
                hook = MouseHook(
                    state, SyntheticInputGuard(logger), logger,
                    callback, release_callback=release,
                )
                event = MSLLHOOKSTRUCT()
                event.pt.x, event.pt.y = 10, 20
                user32 = Mock()
                user32.CallNextHookEx.return_value = 42
                with patch.object(
                    ctypes, "windll", SimpleNamespace(user32=user32),
                    create=True,
                ):
                    addr = ctypes.addressof(event)
                    # Physical press starts in the client before the worker.
                    self.assertEqual(hook._mouse_proc(0, down, addr), 42)
                    self.assertEqual(hook._consumed_releases, set())
                    state.begin_mouse_block("Miroir")
                    # This must pass; swallowing only UP can leave a held
                    # button in the client that received the native DOWN.
                    self.assertEqual(hook._mouse_proc(0, up, addr), 42)
                    self.assertEqual(hook._consumed_releases, set())
                    self.assertEqual(hook._blocked_click_count, 0)
                    state.end_mouse_block()
                if down in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
                    callback.assert_called_once()
                    release.assert_called_once()
                else:
                    callback.assert_not_called()
                    release.assert_not_called()

    def test_native_up_during_block_never_creates_a_false_drop_count(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import MSLLHOOKSTRUCT, MouseHook, WM_LBUTTONUP

        state = InputState()
        logger = logging.getLogger("test_busy_release_counts")
        hook = MouseHook(state, SyntheticInputGuard(logger), logger, Mock())
        event = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 99
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32),
            create=True,
        ):
            state.begin_mouse_block("Miroir")
            self.assertEqual(
                hook._mouse_proc(0, WM_LBUTTONUP, ctypes.addressof(event)),
                99,
            )
            state.end_mouse_block()
        self.assertEqual(hook._blocked_click_count, 0)
        self.assertEqual(hook._blocked_wheel_count, 0)

    def test_busy_down_keeps_matching_up_consumed_after_worker_finishes(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP,
            WM_RBUTTONDOWN, WM_RBUTTONUP,
            WM_MBUTTONDOWN, WM_MBUTTONUP,
            WM_XBUTTONDOWN, WM_XBUTTONUP,
        )

        for down, up in (
            (WM_LBUTTONDOWN, WM_LBUTTONUP),
            (WM_RBUTTONDOWN, WM_RBUTTONUP),
            (WM_MBUTTONDOWN, WM_MBUTTONUP),
            (WM_XBUTTONDOWN, WM_XBUTTONUP),
        ):
            with self.subTest(down=down):
                logger = logging.getLogger("test_busy_mouse_pairs")
                state = InputState()
                click = Mock(return_value=False)
                released = Mock(return_value=False)
                hook = MouseHook(
                    state, SyntheticInputGuard(logger), logger, click,
                    release_callback=released,
                )
                event = MSLLHOOKSTRUCT()
                event.pt.x, event.pt.y = 30, 40
                user32 = Mock()
                user32.CallNextHookEx.return_value = 51
                with patch.object(
                    ctypes, "windll",
                    SimpleNamespace(user32=user32), create=True,
                ):
                    state.begin_mouse_block("Miroir")
                    addr = ctypes.addressof(event)
                    self.assertEqual(hook._mouse_proc(0, down, addr), 1)
                    self.assertEqual(hook._consumed_releases, {up})
                    state.end_mouse_block()
                    # The worker is gone, but the physical UP still belongs
                    # to the swallowed DOWN, not to the active Unity window.
                    self.assertEqual(hook._mouse_proc(0, up, addr), 1)
                    self.assertEqual(hook._consumed_releases, set())
                    self.assertEqual(hook._mouse_proc(0, up, addr), 51)
                click.assert_not_called()
                released.assert_not_called()

    def test_emergency_clear_keeps_blocked_physical_pair_balanced(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook, WM_LBUTTONDOWN, WM_LBUTTONUP,
        )

        logger = logging.getLogger("test_blocked_stop_pairs")
        state = InputState()
        click = Mock(return_value=False)
        hook = MouseHook(
            state, SyntheticInputGuard(logger), logger, click,
        )
        event = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 51
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            addr = ctypes.addressof(event)
            state.begin_mouse_block("Miroir")
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1)
            self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
            # Emergency stop clears the mouse block asynchronously.
            state.clear_mouse_block()
            self.assertFalse(state.is_mouse_blocked())
            # The native UP is still paired with the swallowed DOWN.
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 1)
            self.assertEqual(hook._consumed_releases, set())
            # A NEW native click after Stop remains untouched.
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 51)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 51)
        click.assert_called_once_with("Left", 0, 0)

    def test_synthetic_up_cannot_unlock_busy_physical_down(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            LLMHF_INJECTED, MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP,
        )

        logger = logging.getLogger("test_synthetic_up_busy_pair")
        state = InputState()
        hook = MouseHook(
            state, SyntheticInputGuard(logger), logger, Mock(),
        )
        event = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 51
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            state.begin_mouse_block("Miroir")
            addr = ctypes.addressof(event)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1)
            state.end_mouse_block()
            event.flags = LLMHF_INJECTED
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 51)
            self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
            event.flags = 0
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 1)
            self.assertEqual(hook._consumed_releases, set())

    def test_native_release_callback_keeps_consumed_pairs_balanced(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook, WM_LBUTTONDOWN, WM_LBUTTONUP,
        )

        logger = logging.getLogger("test_native_switch_pair")
        click = Mock(return_value=True)
        release = Mock(return_value=False)
        hook = MouseHook(
            InputState(), SyntheticInputGuard(logger), logger,
            click, release_callback=release,
        )
        mouse = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 41
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            addr = ctypes.addressof(mouse)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 1)
        # A swallowed DOWN keeps ownership of its UP. Releasing it to
        # Unity (or dispatching physical-source replay) would split the pair.
        release.assert_not_called()
        self.assertEqual(hook._consumed_releases, set())

    def test_consumed_down_up_pair_is_not_stolen_by_native_release(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            LLMHF_INJECTED, MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP,
        )

        logger = logging.getLogger("test_native_consumed_release_order")
        click = Mock(return_value=True)
        release = Mock(return_value=True)
        hook = MouseHook(
            InputState(), SyntheticInputGuard(logger), logger, click,
            release_callback=release,
        )
        event = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 37
        with patch.object(ctypes, "windll",
                          SimpleNamespace(user32=user32), create=True):
            addr = ctypes.addressof(event)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1)
            self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
            # Synthetic UP must never discharge the physical release lease.
            event.flags = LLMHF_INJECTED
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 37)
            self.assertEqual(hook._consumed_releases, {WM_LBUTTONUP})
            event.flags = 0
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 1)
            self.assertEqual(hook._consumed_releases, set())
        release.assert_not_called()
        click.assert_called_once()

    def test_busy_input_counters_include_events_hidden_by_warning_throttle(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MouseHook, WM_LBUTTONDOWN, WM_MOUSEWHEEL, WM_MOUSEMOVE,
            WM_LBUTTONUP, WM_RBUTTONDOWN,
        )

        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                logger = Mock()
                hook = MouseHook(
                    InputState(), SyntheticInputGuard(logger), logger, Mock(),
                )
                with patch("app.input.mouse_hooks.time.monotonic",
                           return_value=1.0):
                    for _ in range(count):
                        hook._log_blocked_event(WM_LBUTTONDOWN, 12, 15)
                        hook._log_blocked_event(WM_MOUSEWHEEL, 12, 15)
                        hook._log_blocked_event(WM_MOUSEMOVE, 12, 15)
                        hook._log_blocked_event(WM_LBUTTONUP, 12, 15)
                self.assertEqual(hook._blocked_click_count, count)
                self.assertEqual(hook._blocked_wheel_count, count)
                self.assertEqual(logger.info.call_count, 1)
                logger.info.assert_called_once_with(
                    "Organizer entrées physiques bloquées: clics=%s molettes=%s",
                    1, 0,
                )
                with patch("app.input.mouse_hooks.time.monotonic",
                           return_value=1.5):
                    hook._log_blocked_event(WM_RBUTTONDOWN, 12, 15)
                self.assertEqual(hook._blocked_click_count, count + 1)
                logger.info.assert_called_with(
                    "Organizer entrées physiques bloquées: clics=%s molettes=%s",
                    count + 1, count,
                )

    def test_stop_preserves_native_release_lease_until_hook_is_removed(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import MouseHook, WM_LBUTTONUP

        logger = Mock()
        hook = MouseHook(InputState(), SyntheticInputGuard(logger), logger, Mock())
        hook._consumed_releases.add(WM_LBUTTONUP)
        observed = []
        with patch(
            "app.input.mouse_hooks.stop_message_hook",
            side_effect=lambda current: observed.append(
                set(current._consumed_releases)
            ),
        ):
            hook.stop()
        self.assertEqual(observed, [{WM_LBUTTONUP}])
        self.assertEqual(hook._consumed_releases, set())
        self.assertEqual(hook._last_block_log, 0.0)

    def test_busy_input_telemetry_resets_on_mouse_hook_stop(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import MouseHook, WM_LBUTTONDOWN, WM_MOUSEWHEEL

        logger = Mock()
        hook = MouseHook(InputState(), SyntheticInputGuard(logger), logger, Mock())
        with patch("app.input.mouse_hooks.time.monotonic", return_value=1.0):
            hook._log_blocked_event(WM_LBUTTONDOWN, 10, 20)
            hook._log_blocked_event(WM_MOUSEWHEEL, 10, 20)
        self.assertEqual((hook._blocked_click_count, hook._blocked_wheel_count),
                         (1, 1))
        with patch("app.input.mouse_hooks.stop_message_hook") as stop_hook:
            hook.stop()
        stop_hook.assert_called_once_with(hook)
        logger.info.assert_any_call(
            "Organizer hooks arrêtés: clics bloqués=%s molettes bloquées=%s",
            1, 1,
        )
        self.assertEqual((hook._blocked_click_count, hook._blocked_wheel_count),
                         (0, 0))

    def test_busy_native_click_warning_not_hidden_by_mouse_move_flood(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MouseHook, WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_RBUTTONDOWN,
        )

        logger = Mock()
        state = InputState()
        state.begin_mouse_block("Miroir")
        hook = MouseHook(state, SyntheticInputGuard(logger), logger, Mock())
        with patch("app.input.mouse_hooks.time.monotonic",
                   side_effect=[1.0, 1.1, 1.5]):
            for _ in range(500):
                hook._log_blocked_event(WM_MOUSEMOVE, 12, 15)
            hook._log_blocked_event(WM_LBUTTONDOWN, 12, 15)
            hook._log_blocked_event(WM_RBUTTONDOWN, 12, 15)
            hook._log_blocked_event(WM_RBUTTONDOWN, 12, 15)
        self.assertEqual(logger.warning.call_count, 2)
        logger.warning.assert_any_call(
            "Clic physique non diffusé (macro occupée=%s): event=%s",
            "Miroir", "left_down",
        )
        self.assertEqual(logger.debug.call_count, 0)

    def test_busy_mouse_up_cannot_hide_next_down_warning(self) -> None:
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MouseHook, WM_LBUTTONUP, WM_RBUTTONUP,
            WM_LBUTTONDOWN, WM_MOUSEWHEEL,
        )

        logger = Mock()
        state = InputState()
        state.begin_mouse_block("Miroir")
        hook = MouseHook(state, SyntheticInputGuard(logger), logger, Mock())
        with patch("app.input.mouse_hooks.time.monotonic",
                   side_effect=[1.0, 1.5]):
            for _ in range(100):
                hook._log_blocked_event(WM_LBUTTONUP, 10, 20)
                hook._log_blocked_event(WM_RBUTTONUP, 10, 20)
            hook._log_blocked_event(WM_LBUTTONDOWN, 10, 20)
            hook._log_blocked_event(WM_MOUSEWHEEL, 10, 20)
        logger.warning.assert_any_call(
            "Clic physique non diffusé (macro occupée=%s): event=%s",
            "Miroir", "left_down",
        )
        logger.warning.assert_any_call(
            "Molette physique non diffusée (macro occupée=%s): event=%s",
            "Miroir", "wheel",
        )
        self.assertEqual(logger.warning.call_count, 2)

    def test_physical_click_and_wheel_survive_residual_synthetic_time_guard(self) -> None:
        import logging
        from app.input.input_state import (
            ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO, InputState, SyntheticInputGuard,
        )
        from app.input.mouse_hooks import (
            LLMHF_INJECTED, MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEWHEEL,
        )

        logger = logging.getLogger("test_native_event_after_sendinput")
        guard = SyntheticInputGuard(logger)
        guard.begin(10000)
        click = Mock(return_value=True)
        wheel = Mock(return_value=True)
        hook = MouseHook(
            InputState(), guard, logger, click, wheel_callback=wheel,
        )
        mouse = MSLLHOOKSTRUCT()
        mouse.pt.x = 15
        mouse.pt.y = 20
        mouse.mouseData = 120 << 16
        user32 = Mock()
        user32.CallNextHookEx.return_value = 37
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            addr = ctypes.addressof(mouse)
            # The temporal guard is active, but Win32 identifies these
            # events as PHYSICAL. Do not silently miss a fast second gesture.
            self.assertEqual(hook._mouse_proc(0, WM_MOUSEWHEEL, addr), 1)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 1)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 1)
            wheel.assert_called_once_with(120, 15, 20, False)
            click.assert_called_once_with("Left", 15, 20)
            # Actually injected events still never enter user callbacks.
            mouse.flags = LLMHF_INJECTED
            self.assertEqual(hook._mouse_proc(0, WM_MOUSEWHEEL, addr), 37)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 37)
            mouse.flags = 0
            mouse.dwExtraInfo = ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 37)
            self.assertEqual(hook._mouse_proc(0, WM_MOUSEWHEEL, addr), 37)
        click.assert_called_once()
        wheel.assert_called_once()
        guard.reset()

    def test_actual_mouse_block_still_rejects_physical_clicks(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook, WM_LBUTTONDOWN,
        )

        logger = logging.getLogger("test_mirror_block_stays_active")
        state = InputState()
        state.begin_mouse_block("Miroir")
        click = Mock(return_value=True)
        hook = MouseHook(state, SyntheticInputGuard(logger), logger, click)
        mouse = MSLLHOOKSTRUCT()
        user32 = Mock()
        user32.CallNextHookEx.return_value = 37
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            self.assertEqual(
                hook._mouse_proc(0, WM_LBUTTONDOWN, ctypes.addressof(mouse)), 1,
            )
        click.assert_not_called()
        state.end_mouse_block()

    def test_native_release_and_mirror_wheel_callbacks_coexist(self) -> None:
        import logging
        from app.input.input_state import InputState, SyntheticInputGuard
        from app.input.mouse_hooks import (
            MSLLHOOKSTRUCT, MouseHook,
            WM_LBUTTONDOWN, WM_LBUTTONUP, WM_MOUSEWHEEL,
        )

        logger = logging.getLogger("test_organizer_combined_mouse_callbacks")
        click = Mock(return_value=False)
        wheel = Mock(return_value=True)
        release = Mock(return_value=True)
        hook = MouseHook(
            InputState(), SyntheticInputGuard(logger), logger, click,
            wheel_callback=wheel, release_callback=release,
        )
        mouse = MSLLHOOKSTRUCT()
        mouse.pt.x = 30
        mouse.pt.y = 40
        mouse.mouseData = 120 << 16
        user32 = Mock()
        user32.CallNextHookEx.return_value = 51
        with patch.object(
            ctypes, "windll", SimpleNamespace(user32=user32), create=True,
        ):
            addr = ctypes.addressof(mouse)
            self.assertEqual(hook._mouse_proc(0, WM_MOUSEWHEEL, addr), 1)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, addr), 51)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, addr), 51)
        wheel.assert_called_once_with(120, 30, 40, False)
        click.assert_called_once_with("Left", 30, 40)
        release.assert_called_once_with("Left", 30, 40)
        self.assertEqual(hook._consumed_releases, set())



if __name__ == "__main__":
    unittest.main()
