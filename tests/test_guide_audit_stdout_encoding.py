from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GuideAuditStdoutEncodingTests(unittest.TestCase):
    def _run(self, module: str, *args: str) -> subprocess.CompletedProcess[bytes]:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT)
        env["PYTHONIOENCODING"] = "cp1252"
        with tempfile.TemporaryDirectory() as tmp:
            return subprocess.run(
                [sys.executable, "-m", module, *args],
                cwd=tmp,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def test_runtime_audit_survives_cp1252_stdout(self) -> None:
        completed = self._run("tools.audit_guide_ultime_manual_runtime", "--strict-fields")
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", errors="replace"))
        self.assertNotIn(b"UnicodeEncodeError", completed.stderr)

    def test_action_quality_audit_survives_cp1252_stdout(self) -> None:
        completed = self._run("tools.audit_guide_ultime_action_quality")
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", errors="replace"))
        self.assertNotIn(b"UnicodeEncodeError", completed.stderr)


if __name__ == "__main__":
    unittest.main()
