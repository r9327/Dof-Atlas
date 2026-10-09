from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor import UI_SCENARIOS, build_parser, command_capture_ui


class DoctorUiCaptureContracts(unittest.TestCase):
    def test_registered_scenarios_are_safe_bounded_entrypoints(self):
        self.assertEqual(set(UI_SCENARIOS), {"qt", "equipment", "encyclopedia", "webengine"})
        self.assertEqual(
            UI_SCENARIOS["webengine"],
            "tools.atlas_doctor_lib.webengine_lifecycle_scenario",
        )
        isolated = build_parser().parse_args(["capture-ui", "webengine"])
        self.assertEqual(isolated.scenario, "webengine")
        args = build_parser().parse_args(["capture-ui", "equipment"])
        self.assertEqual(args.scenario, "equipment")
        self.assertEqual(args.max_events, 50000)
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["capture-ui", "main"])

    def test_offscreen_required_without_running_any_scenario(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(scenario="equipment", max_events=50000, json=True)
            with patch.dict("os.environ", {"QT_QPA_PLATFORM": ""}):
                report = command_capture_ui(Path(directory), args)
            self.assertEqual(report["status"], "BLOCKED")
            self.assertFalse(report["tests_executed"])
            self.assertFalse(report["benchmarks_executed"])

    def test_opt_in_route_uses_only_allowlisted_module_and_runtime_location(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(scenario="encyclopedia", max_events=50000, json=True)
            expected = {"status": "RECORDED", "events_captured": 15, "truncated": False}
            with patch.dict("os.environ", {"QT_QPA_PLATFORM": "offscreen"}), \
                 patch("tools.atlas_doctor_lib.runtime_observation.run_traced_module",
                       return_value=expected) as execute:
                report = command_capture_ui(root, args)
            self.assertEqual(report["status"], "RECORDED")
            self.assertFalse(report["benchmarks_executed"])
            self.assertFalse(report["normal_app_instrumented"])
            self.assertEqual(report["scenario"], "encyclopedia")
            self.assertTrue(report["trace_path"].endswith("atlas_ui_encyclopedia.json"))
            execute.assert_called_once_with(
                root, UI_SCENARIOS["encyclopedia"],
                root / ".ai/runtime/atlas_doctor/traces/atlas_ui_encyclopedia.json",
                max_events=50000,
            )


if __name__ == "__main__":
    unittest.main()
