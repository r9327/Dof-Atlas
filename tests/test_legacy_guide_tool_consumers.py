from __future__ import annotations

import unittest
from pathlib import Path

from tools.tool_audit import audit


ROOT = Path(__file__).resolve().parents[1]


class LegacyGuideToolConsumerTests(unittest.TestCase):
    def test_old_v5_runner_has_no_live_import_or_invocation_consumers(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}

        runner = rows["tools/run_guide_ultime_v5.ps1"]
        self.assertEqual(
            runner["consumer_references"],
            [],
            msg=f"old V5 runner still has live consumers: {runner['consumer_references']}",
        )
        self.assertTrue(
            runner["text_references"],
            msg="expected historical/source-contract mentions to remain visible as text evidence",
        )

    def test_gps_strict_and_forensic_v2_are_only_invoked_by_old_v5_runner(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        expected = ["tools/run_guide_ultime_v5.ps1"]

        gps = rows["tools/build_guide_ultime_gps_route_strict.py"]
        forensic = rows["tools/audit_guide_ultime_route_forensic_v2.py"]

        self.assertEqual(
            gps["consumer_references"],
            expected,
            msg=f"GPS strict has unexpected live consumers: {gps['consumer_references']}",
        )
        self.assertEqual(
            gps["invocation_references"],
            expected,
        )
        self.assertEqual(
            forensic["consumer_references"],
            expected,
            msg=f"forensic V2 has unexpected live consumers: {forensic['consumer_references']}",
        )
        self.assertEqual(
            forensic["invocation_references"],
            expected,
        )

    def test_legacy_gps_base_is_only_imported_by_orphan_strict_wrapper(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        base = rows["tools/build_guide_ultime_gps_route.py"]
        expected = ["tools/build_guide_ultime_gps_route_strict.py"]

        self.assertEqual(
            base["consumer_references"],
            expected,
            msg=f"GPS base has unexpected live consumers: {base['consumer_references']}",
        )
        self.assertEqual(base["import_references"], expected)
        self.assertEqual(base["invocation_references"], [])

    def test_legacy_forensic_base_is_only_imported_by_orphan_v2_wrapper(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        base = rows["tools/audit_guide_ultime_route_forensic.py"]
        expected = ["tools/audit_guide_ultime_route_forensic_v2.py"]

        self.assertEqual(
            base["consumer_references"],
            expected,
            msg=f"forensic base has unexpected live consumers: {base['consumer_references']}",
        )
        self.assertEqual(base["import_references"], expected)
        self.assertEqual(base["invocation_references"], [])


if __name__ == "__main__":
    unittest.main()
