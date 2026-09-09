from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "audit_guide_ultime_manual_runtime.py"


class GuideUltimeRuntimeAuditCliTests(unittest.TestCase):
    def test_cli_accepts_ci_output_contract_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output = tmp_path / "runtime_audit.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--strict-fields",
                    "--output",
                    str(output),
                ],
                cwd=tmp_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertTrue(output.is_file(), completed.stdout + completed.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["card_count"], 267)
            self.assertEqual(report["chapter_count"], 13)
            self.assertEqual(report["empty_cards"], [])
            self.assertEqual(report["count_mismatches"], [])
            self.assertEqual(report["unsupported_stage_fields"], {})


if __name__ == "__main__":
    unittest.main()
