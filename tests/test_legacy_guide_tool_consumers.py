from __future__ import annotations

import unittest
from pathlib import Path

from tools.tool_audit import audit


ROOT = Path(__file__).resolve().parents[1]


class LegacyGuideToolConsumerTests(unittest.TestCase):
    def test_old_v5_runner_is_removed_while_current_ci_runner_stays_consumed(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}

        self.assertNotIn("tools/run_guide_ultime_v5.ps1", rows)
        current = rows["tools/run_guide_ultime_ci.ps1"]
        self.assertTrue(
            current["references"],
            msg="current Guide CI runner unexpectedly has no repository consumers",
        )

    def test_gps_strict_and_forensic_v2_are_now_unreferenced_cleanup_candidates(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}

        gps = rows["tools/build_guide_ultime_gps_route_strict.py"]
        forensic = rows["tools/audit_guide_ultime_route_forensic_v2.py"]

        self.assertEqual(
            gps["references"],
            [],
            msg=f"GPS strict still has consumers: {gps['references']}",
        )
        self.assertEqual(
            forensic["references"],
            [],
            msg=f"forensic V2 still has consumers: {forensic['references']}",
        )

    def test_legacy_gps_base_is_only_consumed_by_its_orphan_strict_wrapper(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        base = rows["tools/build_guide_ultime_gps_route.py"]

        self.assertEqual(
            base["references"],
            ["tools/build_guide_ultime_gps_route_strict.py"],
            msg=f"GPS base has unexpected consumers: {base['references']}",
        )

    def test_legacy_forensic_base_is_only_consumed_by_its_orphan_v2_wrapper(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        base = rows["tools/audit_guide_ultime_route_forensic.py"]

        self.assertEqual(
            base["references"],
            ["tools/audit_guide_ultime_route_forensic_v2.py"],
            msg=f"forensic base has unexpected consumers: {base['references']}",
        )


if __name__ == "__main__":
    unittest.main()
