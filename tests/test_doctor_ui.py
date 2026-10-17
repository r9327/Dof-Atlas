from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor import build_parser
from tools.atlas_doctor_lib.doctor_ui import required_assertions, run_ui


class DoctorUiCoordinatorTests(unittest.TestCase):
    def test_cli_is_opt_in_bounded_and_preserves_historical_capture_scenarios(self):
        parser = build_parser()
        args = parser.parse_args(["ui", "guides"])
        self.assertEqual(args.mode, "all")
        self.assertEqual(args.repeats, 2)
        self.assertIsNone(args.select)
        for scenario in ("qt", "equipment", "encyclopedia", "webengine"):
            self.assertEqual(parser.parse_args(["capture-ui", scenario]).scenario, scenario)
        with self.assertRaises(SystemExit):
            parser.parse_args(["ui", "arbitrary-module"])
        with self.assertRaises(SystemExit):
            parser.parse_args(["ui", "guides", "--repeats", "6"])

    def test_selected_scenarios_have_fixed_mandatory_assertions(self):
        required = required_assertions(["guides-success", "guides-lanyel", "guide-quests"])
        self.assertEqual(len(required), len(set(required)))
        self.assertIn("guides-lanyel/combat", required)
        self.assertIn("guides-success/geometry-3-960", required)
        self.assertIn("guide-quests/dofus_sylvestre-quest-1", required)
        success = required_assertions(["achievement-detail"])
        self.assertEqual(
            success,
            ["achievement-detail/first-open-lazy",
             "achievement-detail/click-opens-detail",
             "achievement-detail/geometry-1200",
             "achievement-detail/geometry-960",
             "session/qt-exceptions",
             "session/glyph-rendering"],
        )
        self.assertNotIn("achievement-detail/click-opens-detail",
                         required_assertions(["validator-smoke"]))
        smoke = required_assertions(["validator-smoke"])
        self.assertNotIn("validator-smoke/guide-return", smoke)
        self.assertIn("validator-smoke/manual-persist", smoke)

    def test_timeout_or_native_crash_without_report_is_blocked_with_manifest_and_log(self):
        for effect in (subprocess.TimeoutExpired("worker", 1), subprocess.CompletedProcess([], -11)):
            with self.subTest(effect=type(effect).__name__), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                with patch("tools.atlas_doctor_lib.doctor_ui.git_value", return_value="a" * 40), \
                     patch("tools.atlas_doctor_lib.doctor_ui.subprocess.run", side_effect=effect if isinstance(effect, Exception) else None,
                           return_value=effect):
                    report = run_ui(root, scenarios=["validator-smoke"], timeout=1)
                self.assertEqual(report["status"], "BLOCKED")
                self.assertFalse(report["tests_executed"])
                session = Path(report["session_path"])
                self.assertTrue((session / "worker.log").exists())
                manifest = json.loads((session / "manifest.json").read_text())
                self.assertIn("ui_verdict.json", manifest["artifacts"])

    def test_unknown_scenario_and_out_of_bounds_inputs_rejected_before_process(self):
        with tempfile.TemporaryDirectory() as folder:
            for kwargs in ({"scenarios": ["malicious.module"]}, {"repeats": 0}, {"timeout": 241}):
                with self.assertRaises(ValueError):
                    run_ui(Path(folder), **kwargs)
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
