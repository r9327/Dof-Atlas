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
