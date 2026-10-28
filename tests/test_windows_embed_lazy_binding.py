from __future__ import annotations

import json
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path


class WindowsEmbedLazyBindingTests(unittest.TestCase):
    def test_import_is_lazy_and_first_explicit_use_is_idempotent(self) -> None:
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json
import os
import app.windows_embed as module

before = {
    "ready": module._WINDOWS_API_READY,
    "user32": module.user32 is not None,
    "kernel32": module.kernel32 is not None,
    "enum": module.EnumWindowsProc is not None,
    "event": module.WinEventProc is not None,
}
first = module._ensure_windows_api()
first_ids = (
    id(module.user32),
    id(module.kernel32),
    id(module.EnumWindowsProc),
    id(module.WinEventProc),
)
second = module._ensure_windows_api()
second_ids = (
    id(module.user32),
    id(module.kernel32),
    id(module.EnumWindowsProc),
    id(module.WinEventProc),
)
print(json.dumps({
    "platform": os.name,
    "before": before,
    "first": bool(first),
    "second": bool(second),
    "ready": bool(module._WINDOWS_API_READY),
    "bound": all(value is not None for value in (
        module.user32,
        module.kernel32,
        module.EnumWindowsProc,
        module.WinEventProc,
    )),
    "same": first_ids == second_ids,
}))
'''
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout.strip().splitlines()[-1])

        self.assertEqual(
            payload["before"],
            {
                "ready": False,
                "user32": False,
                "kernel32": False,
                "enum": False,
                "event": False,
            },
        )
        if payload["platform"] == "nt":
            self.assertTrue(payload["first"])
            self.assertTrue(payload["second"])
            self.assertTrue(payload["ready"])
            self.assertTrue(payload["bound"])
            self.assertTrue(payload["same"])
        else:
            self.assertFalse(payload["first"])
            self.assertFalse(payload["second"])
            self.assertFalse(payload["ready"])
            self.assertFalse(payload["bound"])

    def test_uniquify_session_names_contract_is_unchanged(self) -> None:
        from app.windows_embed import uniquify_session_names

        rows = [
            {"nom": "Alpha - Dofus", "hwnd": 1},
            {"nom": "Beta - Dofus", "hwnd": 2},
            {"nom": "Alpha - Dofus", "hwnd": 3},
        ]
        result = uniquify_session_names(rows)
        self.assertEqual(
            [row["nom"] for row in result],
            ["Alpha - Dofus 1", "Beta - Dofus", "Alpha - Dofus 2"],
        )
        self.assertEqual(rows[0]["nom"], "Alpha - Dofus")
        self.assertEqual(rows[2]["nom"], "Alpha - Dofus")


    def test_scanner_preserves_raw_titles_and_distinct_window_ownership(self) -> None:
        import app.windows_embed as windows

        user32 = SimpleNamespace(
            IsWindowVisible=lambda _hwnd: True,
            EnumWindows=lambda callback, _param: (
                callback(101, 0),
                callback(202, 0),
            ),
        )
        with (
            patch.object(windows, "_ensure_windows_api", return_value=True),
            patch.object(windows, "user32", user32),
            patch.object(windows, "EnumWindowsProc", lambda callback: callback),
            patch.object(windows, "window_class", return_value="UnityWndClass"),
            patch.object(
                windows, "window_title",
                side_effect=[
                    "Alice - Feca - Release 1",
                    "Alice - Feca - Release 2",
                ],
            ),
            patch.object(windows, "window_process_id", side_effect=[900, 901]),
        ):
            sessions = windows.scan_unity_sessions()

        self.assertEqual(
            [row["nom"] for row in sessions],
            ["Alice - Feca 1", "Alice - Feca 2"],
        )
        self.assertEqual(
            [row["raw_title"] for row in sessions],
            ["Alice - Feca - Release 1", "Alice - Feca - Release 2"],
        )
        self.assertEqual([row["detected_title"] for row in sessions], ["Alice - Feca"] * 2)
        self.assertEqual([(row["hwnd"], row["pid"]) for row in sessions], [(101, 900), (202, 901)])



if __name__ == "__main__":
    unittest.main()
