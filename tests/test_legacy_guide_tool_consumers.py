from __future__ import annotations

import unittest
from pathlib import Path

from tools.tool_audit import audit


ROOT = Path(__file__).resolve().parents[1]
PROOF_TEST = "tests/test_legacy_guide_tool_consumers.py"


class LegacyGuideToolConsumerTests(unittest.TestCase):
    def test_old_v4_and_v5_runners_have_no_live_consumers(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}

        for path in ("tools/run_guide_ultime_v4.ps1", "tools/run_guide_ultime_v5.ps1"):
            runner = rows[path]
            self.assertEqual(
                runner["consumer_references"],
                [],
                msg=f"legacy runner still has live consumers: {path} -> {runner['consumer_references']}",
            )

    def test_legacy_final_builder_is_only_invoked_by_old_v4_v5_runners(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        builder = rows["tools/build_guide_ultime_final.py"]
        expected = ["tools/run_guide_ultime_v4.ps1", "tools/run_guide_ultime_v5.ps1"]

        self.assertEqual(
            builder["consumer_references"],
            expected,
            msg=f"final builder has unexpected live consumers: {builder['consumer_references']}",
        )
        self.assertEqual(builder["import_references"], [])
        self.assertEqual(builder["invocation_references"], expected)

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
        self.assertEqual(gps["invocation_references"], expected)
        self.assertEqual(
            forensic["consumer_references"],
            expected,
            msg=f"forensic V2 has unexpected live consumers: {forensic['consumer_references']}",
        )
        self.assertEqual(forensic["invocation_references"], expected)

    def test_legacy_gps_base_has_only_old_wrapper_and_v4_consumers(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        base = rows["tools/build_guide_ultime_gps_route.py"]
        expected = [
            "tools/build_guide_ultime_gps_route_strict.py",
            "tools/run_guide_ultime_v4.ps1",
        ]

        self.assertEqual(
            base["consumer_references"],
            expected,
            msg=f"GPS base has unexpected live consumers: {base['consumer_references']}",
        )
        self.assertEqual(base["import_references"], ["tools/build_guide_ultime_gps_route_strict.py"])
        self.assertEqual(base["invocation_references"], ["tools/run_guide_ultime_v4.ps1"])

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

    def test_no_product_test_reads_legacy_v4_v5_builder_sources(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        legacy_paths = (
            "tools/run_guide_ultime_v4.ps1",
            "tools/run_guide_ultime_v5.ps1",
            "tools/build_guide_ultime_final.py",
            "tools/build_guide_ultime_gps_route.py",
            "tools/build_guide_ultime_gps_route_strict.py",
            "tools/audit_guide_ultime_route_forensic.py",
            "tools/audit_guide_ultime_route_forensic_v2.py",
        )

        for path in legacy_paths:
            self.assertEqual(
                rows[path]["test_references"],
                [PROOF_TEST],
                msg=f"legacy source still has another test reference: {path} -> {rows[path]['test_references']}",
            )
            self.assertEqual(
                rows[path]["test_consumer_references"],
                [],
                msg=f"legacy source still has a test consumer: {path} -> {rows[path]['test_consumer_references']}",
            )


if __name__ == "__main__":
    unittest.main()
