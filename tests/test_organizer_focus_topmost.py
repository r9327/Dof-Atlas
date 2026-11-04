from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.windows import focus


def _topmost_modules(set_pos):
    gui = SimpleNamespace(
        IsWindow=Mock(return_value=True),
        IsIconic=Mock(return_value=False),
        GetForegroundWindow=Mock(return_value=999),
        ShowWindow=Mock(),
        BringWindowToTop=Mock(),
        SetWindowPos=Mock(side_effect=set_pos),
        SetActiveWindow=Mock(),
        SetForegroundWindow=Mock(),
        SetFocus=Mock(),
    )
    process = SimpleNamespace(
        GetWindowThreadProcessId=Mock(return_value=(2, 999)),
        AttachThreadInput=Mock(return_value=True),
    )
    con = SimpleNamespace(
        SW_SHOW=5, SW_RESTORE=9,
        HWND_TOP=0, HWND_TOPMOST=-1, HWND_NOTOPMOST=-2,
        SWP_NOMOVE=2, SWP_NOSIZE=1, SWP_SHOWWINDOW=0x40,
    )
    return {
        "win32gui": gui, "win32process": process,
        "win32con": con,
        "win32api": SimpleNamespace(GetCurrentThreadId=Mock(return_value=1)),
    }


class OrganizerTopmostCleanupTests(unittest.TestCase):
    def _activate(self, modules, logger=None, should_stop=None):
        logger = logger or Mock()
        with (
            patch.object(focus.os, "name", "nt"),
            patch.dict("sys.modules", modules),
            patch.object(focus, "is_unity_window", return_value=True),
            patch.object(focus, "foreground_window", return_value=999),
        ):
            self.assertFalse(focus.activate_window(
                101, 0, 1, 0, logger, "Miroir", should_stop=should_stop,
            ))
        self.assertEqual(
            [c.args[-1] for c in modules["win32process"].AttachThreadInput.call_args_list],
            [True, False],
        )
        return logger

    def test_topmost_refusal_still_attempts_notopmost(self):
        def setter(hwnd, zorder, *_args):
            if zorder == -1:
                raise OSError("TOPMOST refused")

        modules = _topmost_modules(setter)
        self._activate(modules)
        orders = [c.args[1] for c in modules["win32gui"].SetWindowPos.call_args_list]
        self.assertEqual(orders, [0, -1, -2])
        # The ordinary foreground attempt happened first; no second one.
        self.assertEqual(modules["win32gui"].SetForegroundWindow.call_count, 1)

    def test_failed_first_unpin_is_retried_once_before_final_focus(self):
        fails = [True]

        def setter(hwnd, zorder, *_args):
            if zorder == -2 and fails[0]:
                fails[0] = False
                raise OSError("first NOTOPMOST refused")

        modules = _topmost_modules(setter)
        logger = self._activate(modules)
        orders = [c.args[1] for c in modules["win32gui"].SetWindowPos.call_args_list]
        self.assertEqual(orders, [0, -1, -2, -2])
        self.assertEqual(modules["win32gui"].SetForegroundWindow.call_count, 2)
        logger.exception.assert_called_once_with(
            "%s: retrait topmost echec hwnd=%s, nouvel essai.", "Miroir", 101,
        )

    def test_two_failed_unpins_skip_final_foreground(self):
        def setter(hwnd, zorder, *_args):
            if zorder == -2:
                raise OSError("NOTOPMOST refused")

        modules = _topmost_modules(setter)
        logger = self._activate(modules)
        orders = [c.args[1] for c in modules["win32gui"].SetWindowPos.call_args_list]
        self.assertEqual(orders, [0, -1, -2, -2])
        self.assertEqual(modules["win32gui"].SetForegroundWindow.call_count, 1)
        logger.exception.assert_called_once()

    def test_stop_after_unpin_does_not_force_a_second_foreground(self):
        stopped = [False]

        def setter(hwnd, zorder, *_args):
            if zorder == -2:
                stopped[0] = True

        modules = _topmost_modules(setter)
        logger = self._activate(modules, should_stop=lambda: stopped[0])
        orders = [c.args[1] for c in modules["win32gui"].SetWindowPos.call_args_list]
        self.assertEqual(orders, [0, -1, -2])
        self.assertEqual(modules["win32gui"].SetForegroundWindow.call_count, 1)
        logger.info.assert_any_call(
            "%s activation stoppee apres topmost hwnd=%s", "Miroir", 101,
        )


if __name__ == "__main__":
    unittest.main()
