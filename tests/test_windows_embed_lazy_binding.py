from __future__ import annotations

import json
import subprocess
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
