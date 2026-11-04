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
        stops = iter((False, False, True))
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


if __name__ == "__main__":
    unittest.main()
