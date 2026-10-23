"""The Tk launcher must report true completion, not the last progress value."""
from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from app.distribution import launcher
from app.distribution.release_client import UpdateError


class _Variable:
    def __init__(self, value=None):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class _ImmediateThread:
    def __init__(self, *, target, **_kwargs):
        self.target = target

    def start(self):
        self.target()


class LauncherExitCodeTests(unittest.TestCase):
    def _main_result(self, *, launch_fails: bool) -> int:
        fake_tk = MagicMock()
        fake_ttk = MagicMock()
        fake_tk.ttk = fake_ttk
        fake_tk.IntVar.side_effect = _Variable
        fake_tk.StringVar.side_effect = _Variable
        # Process queued events deterministically without opening a GUI.
        fake_tk.Tk.return_value.after.side_effect = lambda _delay, fn: fn()

        def update(report, *, verify_installation=False):
            # Relocation may finish before the updater attempts to start Atlas.
            report("Copie terminee", 100)
            if launch_fails:
                raise UpdateError("Atlas n'a pas confirme son demarrage")

        with (
            patch.dict(sys.modules, {"tkinter": fake_tk, "tkinter.ttk": fake_ttk}),
            patch.object(sys, "argv", ["DofusAtlas.exe", "--atlas-auto-install"]),
            patch.object(launcher, "read_state", return_value={"active": "v1"}),
            patch.object(launcher, "run_update", side_effect=update),
            patch.object(launcher, "_logger", return_value=MagicMock()),
            patch.object(launcher.threading, "Thread", _ImmediateThread),
        ):
            return launcher.main()

    def test_100_percent_before_launch_failure_returns_error(self):
        self.assertEqual(self._main_result(launch_fails=True), 1)

    def test_completed_launch_returns_success(self):
        self.assertEqual(self._main_result(launch_fails=False), 0)


if __name__ == "__main__":
    unittest.main()
