from __future__ import annotations

import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from tools import validate_guide_ultime_manual_bundle as bundle


class CanonicalManualBundleValidationTests(unittest.TestCase):
    def test_complete_locations_and_positive_resources_are_valid(self) -> None:
        payload = {
            "stages": [{"id": "route", "start": {"x": 0, "y": 0},
                        "end": {"x": "-10000", "y": 10000},
                        "waypoints": [{"x": None, "y": None}, {"label": "no coordinate"}]}],
            "resource_plan": {"collect_before_leaving_incarnam": [{"quantity": 1}]},
        }
        self.assertEqual(bundle.route_field_errors(payload), [])

    def test_incomplete_start_end_and_waypoint_are_identified(self) -> None:
        for field in ("start", "end", "waypoints"):
            with self.subTest(field=field):
                location = {"x": 0}
                stage = {"id": "stage", field: [location] if field == "waypoints" else location}
                errors = bundle.route_field_errors({"stages": [stage]})
                self.assertEqual(len(errors), 1)
                self.assertEqual(errors[0]["code"], "coordinate_pair_incomplete")
                self.assertEqual(errors[0]["stage_id"], "stage")
                self.assertEqual(errors[0]["location"], "waypoints[0]" if field == "waypoints" else field)

    def test_invalid_numeric_coordinates_are_rejected(self) -> None:
        for x in (-2147483648, 10001, -10001, "not a number", float("inf")):
            with self.subTest(x=x):
                errors = bundle.route_field_errors({"stages": [{"id": "stage", "start": {"x": x, "y": 0}}]})
                self.assertEqual([row["code"] for row in errors], ["invalid_coordinate"])

    def test_invalid_resource_quantities_are_rejected(self) -> None:
        for quantity in (None, 0, -1, "1", 1.5, True):
            with self.subTest(quantity=quantity):
                errors = bundle.route_field_errors({
                    "resource_plan": {"collect_before_leaving_incarnam": [{"quantity": quantity}]}
                })
                self.assertEqual([row["code"] for row in errors], ["invalid_resource_quantity"])

    def test_real_canonical_bundle_passes_strict_gate(self) -> None:
        output = io.StringIO()
        with patch.object(sys, "argv", ["bundle", "--strict", "--skip-catalog"]), redirect_stdout(output):
            bundle.main()
        report = json.loads(output.getvalue())
        self.assertTrue(report["ok"], report["hard_errors"])
        self.assertEqual(report["hard_error_count"], 0)

    def test_strict_gate_rejects_regression_in_resolved_chapter(self) -> None:
        original = bundle.load_manual_chapter
        injected = []

        def broken_chapter(path):
            payload = copy.deepcopy(original(path))
            if not injected and payload.get("stages"):
                payload["stages"][0]["start"] = {"x": 0}
                payload["resource_plan"] = {"collect_before_leaving_incarnam": [{"quantity": 0}]}
                injected.append(path.name)
            return payload

        output = io.StringIO()
        with patch.object(bundle, "load_manual_chapter", side_effect=broken_chapter), \
                patch.object(sys, "argv", ["bundle", "--strict", "--skip-catalog"]), redirect_stdout(output):
            with self.assertRaises(SystemExit) as raised:
                bundle.main()
        self.assertEqual(raised.exception.code, 1)
        report = json.loads(output.getvalue())
        for code in ("coordinate_pair_incomplete", "invalid_resource_quantity"):
            error = next(row for row in report["hard_errors"] if row["code"] == code)
            self.assertEqual(error["file"], injected[0])
            self.assertTrue(error["chapter"])


if __name__ == "__main__":
    unittest.main()
