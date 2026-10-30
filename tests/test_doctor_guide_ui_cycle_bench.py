"""Pure-stdlib checks for the optional real Qt Guide lifecycle benchmark."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib import guide_ui_cycle_bench as benchmark


class DoctorGuideUiCycleBenchmarkTests(unittest.TestCase):
    def test_cli_preserves_failure_as_json_without_claiming_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.json"
            with patch.object(sys, "argv", ["doctor-guide-bench", "--cycles", "30",
                                             "--output", str(output)]), \
                 patch.object(benchmark, "measure", side_effect=RuntimeError("Qt unavailable")):
                self.assertEqual(benchmark.main(), 1)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(report["requested_cycles"], 30)
            self.assertIn("Qt unavailable", report["error"])

    def test_cli_accepts_only_a_complete_verified_cycle_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.json"
            with patch.object(sys, "argv", ["doctor-guide-bench", "--cycles", "30",
                                             "--output", str(output)]), \
                 patch.object(benchmark, "measure", return_value={
                     "status": "PASS", "requested_cycles": 30, "cycles_completed": 29,
                 }):
                self.assertEqual(benchmark.main(), 1)
            with patch.object(sys, "argv", ["doctor-guide-bench", "--cycles", "30",
                                             "--output", str(output)]), \
                 patch.object(benchmark, "measure", return_value={
                     "status": "PASS", "requested_cycles": 30, "cycles_completed": 30,
                 }):
                self.assertEqual(benchmark.main(), 0)

    def test_out_of_range_cycle_limit_is_rejected_before_qt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "invalid.json"
            with patch.object(sys, "argv", ["doctor-guide-bench", "--cycles", "31",
                                             "--output", str(output)]):
                with self.assertRaises(SystemExit) as captured:
                    benchmark.main()
            self.assertNotEqual(captured.exception.code, 0)
            self.assertFalse(output.exists())

    def test_native_rss_has_explicit_unavailable_state(self) -> None:
        with patch.object(benchmark.os, "name", "other"), \
             patch.object(benchmark.platform, "system", return_value="Other"):
            self.assertIsNone(benchmark.resident_bytes())


if __name__ == "__main__":
    unittest.main()
