from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.windows import focus


def _win32_activation_modules():
    """Only model the Win32 members needed by the already-foreground path."""
    return {
        "win32con": SimpleNamespace(),
        "win32gui": SimpleNamespace(IsWindow=Mock(return_value=True)),
        "win32api": SimpleNamespace(),
        "win32process": SimpleNamespace(),
    }


class OrganizerFocusPreflightTests(unittest.TestCase):
    def test_stop_before_focus_preflight_never_queries_windows(self) -> None:
        logger = Mock()
        with (
            patch.object(focus.os, "name", "nt"),
            patch.object(focus, "is_unity_window", side_effect=AssertionError("probed")),
            patch.object(focus, "foreground_window", side_effect=AssertionError("probed")),
        ):
            self.assertFalse(focus.activate_window(
                101, 0, 1, 0, logger, "Miroir", should_stop=lambda: True,
            ))
        logger.info.assert_called_once_with(
            "%s activation stoppee avant preflight hwnd=%s", "Miroir", 101,
        )

    def test_invalid_focus_timings_never_change_foreground(self) -> None:
        for field in ("settle", "attempts", "retry"):
            for invalid in (float("nan"), float("inf"), None):
                with self.subTest(field=field, invalid=invalid):
                    values = {"settle": 12, "attempts": 8, "retry": 10}
                    values[field] = invalid
                    modules = _win32_activation_modules()
                    logger = Mock()
                    with (
                        patch.object(focus.os, "name", "nt"),
                        patch.dict("sys.modules", modules),
                        patch.object(focus, "is_unity_window", return_value=True),
                        patch.object(focus, "foreground_window") as foreground,
                    ):
                        self.assertFalse(focus.activate_window(
                            101, values["settle"], values["attempts"],
                            values["retry"], logger, "Miroir",
                        ))
                    modules["win32gui"].IsWindow.assert_not_called()
                    foreground.assert_not_called()
                    logger.warning.assert_called_once_with(
                        "%s activation refusee: temporisations ou hwnd invalides.",
                        "Miroir",
                    )

    def test_already_foreground_focus_theft_during_settle_never_reports_success(self) -> None:
        with (
            patch.object(focus.os, "name", "nt"),
            patch.dict("sys.modules", _win32_activation_modules()),
            patch.object(focus, "is_unity_window", return_value=True),
            patch.object(focus, "foreground_window", side_effect=[101, 999]) as current,
            patch.object(focus, "wait_ms", return_value=False) as settle,
        ):
            self.assertFalse(focus.activate_window(
                101, 35, 3, 10, Mock(), "Miroir",
            ))
        self.assertEqual(current.call_count, 2)
        settle.assert_called_once_with(35, None)

    def test_excessive_finite_focus_delays_refuse_before_native_checks(self) -> None:
        for field in ("settle", "retry"):
            for value in (1001, 10**9):
                with self.subTest(field=field, value=value):
                    modules = _win32_activation_modules()
                    logger = Mock()
                    settle, retry = (value, 18) if field == "settle" else (24, value)
                    with (
                        patch.object(focus.os, "name", "nt"),
                        patch.dict("sys.modules", modules),
                        patch.object(focus, "is_unity_window", return_value=True),
                        patch.object(focus, "foreground_window") as current,
                        patch.object(focus, "wait_ms") as wait,
                    ):
                        self.assertFalse(focus.activate_window(
                            101, settle, 8, retry, logger, "Miroir",
                        ))
                    modules["win32gui"].IsWindow.assert_not_called()
                    current.assert_not_called()
                    wait.assert_not_called()
                    logger.warning.assert_called_once_with(
                        "%s activation refusee: temporisation excessive settle=%s retry=%s.",
                        "Miroir", settle, retry,
                    )

    def test_corrupt_huge_attempt_count_stays_bounded_to_eight(self) -> None:
        win32gui = SimpleNamespace(
            IsWindow=Mock(return_value=True),
            IsIconic=Mock(return_value=False),
            GetForegroundWindow=Mock(return_value=999),
            ShowWindow=Mock(),
            BringWindowToTop=Mock(),
            SetWindowPos=Mock(),
            SetActiveWindow=Mock(),
            SetForegroundWindow=Mock(),
            SetFocus=Mock(),
        )
        con = SimpleNamespace(
            SW_RESTORE=9, SW_SHOW=5, HWND_TOP=0,
            HWND_TOPMOST=-1, HWND_NOTOPMOST=-2,
            SWP_NOMOVE=2, SWP_NOSIZE=1, SWP_SHOWWINDOW=0x40,
        )
        modules = {
            "win32con": con,
            "win32gui": win32gui,
            "win32api": SimpleNamespace(GetCurrentThreadId=Mock(return_value=1)),
            "win32process": SimpleNamespace(
                GetWindowThreadProcessId=Mock(return_value=(2, 999)),
                AttachThreadInput=Mock(return_value=True),
            ),
        }
        logger = Mock()
        with (
            patch.object(focus.os, "name", "nt"),
            patch.dict("sys.modules", modules),
            patch.object(focus, "is_unity_window", return_value=True),
            patch.object(focus, "foreground_window", return_value=999),
        ):
            self.assertFalse(focus.activate_window(
                101, 0, 10**9, 0, logger, "Miroir",
            ))
        self.assertEqual(win32gui.BringWindowToTop.call_count, 8)
        self.assertEqual(win32gui.SetForegroundWindow.call_count, 9)
        logger.info.assert_any_call(
            "%s activation echec hwnd=%s foreground=%s", "Miroir", 101, 999,
        )

    def test_stop_during_thread_attach_detaches_without_showing_window(self) -> None:
        win32gui = SimpleNamespace(
            IsWindow=Mock(return_value=True),
            IsIconic=Mock(side_effect=AssertionError("showed a stopped window")),
            GetForegroundWindow=Mock(return_value=999),
            ShowWindow=Mock(side_effect=AssertionError("show after Stop")),
            BringWindowToTop=Mock(side_effect=AssertionError("focus after Stop")),
        )
        process = SimpleNamespace(
            GetWindowThreadProcessId=Mock(return_value=(2, 999)),
            AttachThreadInput=Mock(return_value=True),
        )
        modules = {
            "win32con": SimpleNamespace(),
            "win32gui": win32gui,
            "win32api": SimpleNamespace(GetCurrentThreadId=Mock(return_value=1)),
            "win32process": process,
        }
        stops = iter((False, False, True))
        logger = Mock()
        with (
            patch.object(focus.os, "name", "nt"),
            patch.dict("sys.modules", modules),
            patch.object(focus, "is_unity_window", return_value=True),
            patch.object(focus, "foreground_window", return_value=999),
        ):
            self.assertFalse(focus.activate_window(
                101, 0, 1, 0, logger, "Miroir",
                should_stop=lambda: next(stops),
            ))
        self.assertEqual(
            [entry.args for entry in process.AttachThreadInput.call_args_list],
            [(1, 2, True), (1, 2, False)],
        )
        win32gui.IsIconic.assert_not_called()
        win32gui.ShowWindow.assert_not_called()
        win32gui.BringWindowToTop.assert_not_called()
        logger.info.assert_any_call(
            "%s activation stoppee avant manipulation hwnd=%s", "Miroir", 101,
        )

    def test_stop_after_window_show_cannot_trigger_foreground_set(self) -> None:
        win32gui = SimpleNamespace(
            IsWindow=Mock(return_value=True),
            IsIconic=Mock(return_value=False),
            GetForegroundWindow=Mock(return_value=999),
            ShowWindow=Mock(),
            BringWindowToTop=Mock(),
            SetWindowPos=Mock(),
            SetActiveWindow=Mock(),
            SetForegroundWindow=Mock(),
            SetFocus=Mock(),
        )
        process = SimpleNamespace(
            GetWindowThreadProcessId=Mock(return_value=(2, 999)),
            AttachThreadInput=Mock(return_value=True),
        )
        modules = {
            "win32con": SimpleNamespace(
                SW_SHOW=5, SW_RESTORE=9, HWND_TOP=0,
                SWP_NOMOVE=2, SWP_NOSIZE=1, SWP_SHOWWINDOW=0x40,
            ),
            "win32gui": win32gui,
            "win32api": SimpleNamespace(GetCurrentThreadId=Mock(return_value=1)),
            "win32process": process,
        }
        stops = iter((False, False, False, True))
        logger = Mock()
        with (
            patch.object(focus.os, "name", "nt"),
            patch.dict("sys.modules", modules),
            patch.object(focus, "is_unity_window", return_value=True),
            patch.object(focus, "foreground_window", return_value=999),
        ):
            self.assertFalse(focus.activate_window(
                101, 0, 1, 0, logger, "Miroir",
                should_stop=lambda: next(stops),
            ))
        win32gui.ShowWindow.assert_called_once_with(101, 5)
        win32gui.BringWindowToTop.assert_not_called()
        win32gui.SetWindowPos.assert_not_called()
        win32gui.SetActiveWindow.assert_not_called()
        win32gui.SetForegroundWindow.assert_not_called()
        self.assertEqual(process.AttachThreadInput.call_count, 2)
        logger.info.assert_any_call(
            "%s activation stoppee apres ShowWindow hwnd=%s", "Miroir", 101,
        )

    def test_stop_before_last_resort_topmost_prevents_focus_override(self) -> None:
        win32gui = SimpleNamespace(
            IsWindow=Mock(return_value=True),
            IsIconic=Mock(return_value=False),
            GetForegroundWindow=Mock(return_value=999),
            ShowWindow=Mock(),
            BringWindowToTop=Mock(),
            SetWindowPos=Mock(),
            SetActiveWindow=Mock(),
            SetForegroundWindow=Mock(),
            SetFocus=Mock(),
        )
        process = SimpleNamespace(
            GetWindowThreadProcessId=Mock(return_value=(2, 999)),
            AttachThreadInput=Mock(return_value=True),
        )
        modules = {
            "win32con": SimpleNamespace(
                SW_SHOW=5, SW_RESTORE=9, HWND_TOP=0,
                HWND_TOPMOST=-1, HWND_NOTOPMOST=-2,
                SWP_NOMOVE=2, SWP_NOSIZE=1, SWP_SHOWWINDOW=0x40,
            ),
            "win32gui": win32gui,
            "win32api": SimpleNamespace(GetCurrentThreadId=Mock(return_value=1)),
            "win32process": process,
        }
        stops = iter((False, False, False, False, False, False, False, True))
        logger = Mock()
        with (
            patch.object(focus.os, "name", "nt"),
            patch.dict("sys.modules", modules),
            patch.object(focus, "is_unity_window", return_value=True),
            patch.object(focus, "foreground_window", return_value=999),
        ):
            self.assertFalse(focus.activate_window(
                101, 0, 1, 0, logger, "Miroir",
                should_stop=lambda: next(stops),
            ))
        # Standard SetWindowPos already happened; neither TOPMOST pass ran.
        win32gui.SetWindowPos.assert_called_once()
        win32gui.SetForegroundWindow.assert_called_once_with(101)
        self.assertEqual(process.AttachThreadInput.call_count, 2)
        logger.info.assert_any_call(
            "%s activation stoppee avant topmost hwnd=%s", "Miroir", 101,
        )

    def test_stop_after_native_foreground_success_never_reports_activation(self) -> None:
        win32gui = SimpleNamespace(
            IsWindow=Mock(return_value=True),
            IsIconic=Mock(return_value=False),
            GetForegroundWindow=Mock(return_value=999),
            ShowWindow=Mock(),
            BringWindowToTop=Mock(),
            SetWindowPos=Mock(),
            SetActiveWindow=Mock(),
            SetForegroundWindow=Mock(),
            SetFocus=Mock(),
        )
        con = SimpleNamespace(
            SW_RESTORE=9, SW_SHOW=5, HWND_TOP=0,
            SWP_NOMOVE=2, SWP_NOSIZE=1, SWP_SHOWWINDOW=0x40,
        )
        modules = {
            "win32con": con,
            "win32gui": win32gui,
            "win32api": SimpleNamespace(GetCurrentThreadId=Mock(return_value=1)),
            "win32process": SimpleNamespace(
                GetWindowThreadProcessId=Mock(return_value=(2, 999)),
                AttachThreadInput=Mock(return_value=True),
            ),
        }
        stops = iter((False, False, False, False, False, False, False, True))
        logger = Mock()
        with (
            patch.object(focus.os, "name", "nt"),
            patch.dict("sys.modules", modules),
            patch.object(focus, "is_unity_window", return_value=True),
            patch.object(focus, "foreground_window",
                         side_effect=[999, 101, 101]),
        ):
            self.assertFalse(focus.activate_window(
                101, 0, 1, 0, logger, "Miroir",
                should_stop=lambda: next(stops),
            ))
        win32gui.SetForegroundWindow.assert_called_once_with(101)
        logger.info.assert_any_call(
            "%s activation stoppee apres tentative hwnd=%s", "Miroir", 101,
        )
        self.assertEqual(
            modules["win32process"].AttachThreadInput.call_count, 2,
        )

    def test_already_foreground_two_four_six_eight_clients_need_no_native_retry(self) -> None:
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                modules = _win32_activation_modules()
                with (
                    patch.object(focus.os, "name", "nt"),
                    patch.dict("sys.modules", modules),
                    patch.object(focus, "is_unity_window", return_value=True),
                    patch.object(focus, "foreground_window") as foreground,
                    patch.object(focus, "wait_ms", return_value=False) as wait,
                ):
                    for hwnd in range(101, 101 + count):
                        foreground.return_value = hwnd
                        self.assertTrue(focus.activate_window(
                            hwnd, 12, 8, 18, Mock(), "Miroir",
                        ))
                self.assertEqual(foreground.call_count, 2 * count)
                self.assertEqual(wait.call_count, count)
                modules["win32gui"].IsWindow.assert_has_calls(
                    [unittest.mock.call(hwnd) for hwnd in range(101, 101 + count)]
                )
                self.assertEqual(
                    modules["win32gui"].IsWindow.call_count, count,
                )

    def test_already_foreground_unstolen_focus_remains_successful(self) -> None:
        with (
            patch.object(focus.os, "name", "nt"),
            patch.dict("sys.modules", _win32_activation_modules()),
            patch.object(focus, "is_unity_window", return_value=True),
            patch.object(focus, "foreground_window", side_effect=[101, 101]),
            patch.object(focus, "wait_ms", return_value=False),
        ):
            self.assertTrue(focus.activate_window(
                101, 15, 1, 0, Mock(), "Miroir",
            ))

    def test_stop_arriving_after_already_foreground_settle_returns_false(self) -> None:
        checks = iter((False, True))
        with (
            patch.object(focus.os, "name", "nt"),
            patch.dict("sys.modules", _win32_activation_modules()),
            patch.object(focus, "is_unity_window", return_value=True),
            patch.object(focus, "foreground_window", return_value=101) as current,
            patch.object(focus, "wait_ms", return_value=False) as settle,
        ):
            self.assertFalse(focus.activate_window(
                101, 25, 2, 0, Mock(), "Miroir",
                should_stop=lambda: next(checks),
            ))
        settle.assert_called_once()
        current.assert_called_once()

    def test_stop_during_settle_returns_false_without_late_activation(self) -> None:
        with (
            patch.object(focus.os, "name", "nt"),
            patch.dict("sys.modules", _win32_activation_modules()),
            patch.object(focus, "is_unity_window", return_value=True),
            patch.object(focus, "foreground_window", return_value=101) as current,
            patch.object(focus, "wait_ms", return_value=True),
        ):
            self.assertFalse(focus.activate_window(
                101, 40, 2, 0, Mock(), "Miroir",
                should_stop=lambda: False,
            ))
        current.assert_called_once()


    def test_optional_already_foreground_skips_only_the_noop_settle(self):
        for active, expected in ((101, True), (999, False)):
            if active == 999:
                # Native activation is needed: the optimized branch must
                # not suppress the configured transition delay.
                continue
            with self.subTest(active=active):
                with (
                    patch.object(focus.os, "name", "nt"),
                    patch.dict("sys.modules", _win32_activation_modules()),
                    patch.object(focus, "is_unity_window", return_value=True),
                    patch.object(focus, "foreground_window",
                                 side_effect=[101, 101]) as foreground,
                    patch.object(focus, "wait_ms") as wait,
                ):
                    self.assertTrue(focus.activate_window(
                        101, 43, 3, 10, Mock(), "Auto zaap",
                        skip_settle_if_active=True,
                    ))
                wait.assert_not_called()
                self.assertEqual(foreground.call_count, 2)

    def test_fast_already_foreground_still_rejects_stolen_focus(self):
        with (
            patch.object(focus.os, "name", "nt"),
            patch.dict("sys.modules", _win32_activation_modules()),
            patch.object(focus, "is_unity_window", return_value=True),
            patch.object(focus, "foreground_window",
                         side_effect=[101, 999]) as foreground,
            patch.object(focus, "wait_ms") as wait,
        ):
            self.assertFalse(focus.activate_window(
                101, 43, 2, 10, Mock(), "Auto groupe",
                skip_settle_if_active=True,
            ))
        wait.assert_not_called()
        self.assertEqual(foreground.call_count, 2)



if __name__ == "__main__":
    unittest.main()
