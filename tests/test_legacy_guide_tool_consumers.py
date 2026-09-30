from __future__ import annotations

import unittest
from pathlib import Path

from tools.tool_audit import audit


ROOT = Path(__file__).resolve().parents[1]
PROOF_TEST = "tests/test_legacy_guide_tool_consumers.py"
RETIRED_WRAPPERS = (
    "tools/build_guide_ultime_gps_route_strict.py",
    "tools/audit_guide_ultime_route_forensic_v2.py",
)
DEFERRED_LEGACY = (
    "tools/run_guide_ultime_v5.ps1",
    "tools/build_guide_ultime_final.py",
    "tools/build_guide_ultime_gps_route.py",
    "tools/audit_guide_ultime_route_forensic.py",
)


class LegacyGuideToolConsumerTests(unittest.TestCase):
    def test_retired_wrappers_are_gone(self) -> None:
        for path in RETIRED_WRAPPERS:
            self.assertFalse((ROOT / path).exists(), msg=f"retired wrapper restored: {path}")

    def test_v5_runner_has_no_live_consumers(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        self.assertEqual(rows["tools/run_guide_ultime_v5.ps1"]["consumer_references"], [])

    def test_final_builder_is_only_invoked_by_v5_harness(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        builder = rows["tools/build_guide_ultime_final.py"]
        self.assertEqual(builder["consumer_references"], ["tools/run_guide_ultime_v5.ps1"])
        self.assertEqual(builder["import_references"], [])

    def test_gps_base_is_only_imported_by_canonical_gps(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        base = rows["tools/build_guide_ultime_gps_route.py"]
        self.assertEqual(base["consumer_references"], ["tools/guide_gps.py"])
        self.assertEqual(base["import_references"], ["tools/guide_gps.py"])
        self.assertEqual(base["invocation_references"], [])

    def test_forensic_base_is_only_imported_by_canonical_forensic(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        base = rows["tools/audit_guide_ultime_route_forensic.py"]
        self.assertEqual(base["consumer_references"], ["tools/guide_forensic.py"])
        self.assertEqual(base["import_references"], ["tools/guide_forensic.py"])
        self.assertEqual(base["invocation_references"], [])

    def test_no_product_test_consumes_deferred_legacy_sources(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        for path in DEFERRED_LEGACY:
            self.assertEqual(rows[path]["test_consumer_references"], [], msg=path)


if __name__ == "__main__":
    unittest.main()
