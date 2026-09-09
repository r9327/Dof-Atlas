from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "audit_guide_ultime_action_quality.py"


class GuideUltimeActionQualityCliTests(unittest.TestCase):
    def test_cli_runs_outside_repo_cwd_and_writes_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            output = tmp_path / "action_quality.json"
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--output", str(output)],
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
            self.assertEqual(report["stage_count"], 267)
            self.assertEqual(report["chapter_count"], 13)
            self.assertIn("hard_issue_count", report)
            self.assertIn("review_issue_count", report)


if __name__ == "__main__":
    unittest.main()
