from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ConstantsImportSideEffectsTests(unittest.TestCase):
    def test_import_keeps_sys_path_and_excepthook_unchanged(self) -> None:
        code = (
            "import json, sys; "
            "before_path=list(sys.path); before_hook=sys.excepthook; "
            "import app.constants; "
            "print(json.dumps({\"path\": before_path == sys.path, "
            "\"hook\": before_hook is sys.excepthook}))"
        )
        completed = subprocess.run([sys.executable, "-c", code], cwd=ROOT, text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertTrue(payload["path"])
        self.assertTrue(payload["hook"])

if __name__ == "__main__":
    unittest.main()
