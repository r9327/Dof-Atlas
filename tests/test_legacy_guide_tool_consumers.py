from __future__ import annotations

import unittest
from pathlib import Path

from tools.tool_audit import audit


ROOT = Path(__file__).resolve().parents[1]


class LegacyGuideToolConsumerTests(unittest.TestCase):
    def test_old_v5_runner_is_not_consumed_by_current_repository_paths(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}

        runner = rows["tools/run_guide_ultime_v5.ps1"]
        self.assertEqual(
            runner["references"],
            [],
            msg=f"old V5 runner still has consumers: {runner['references']}",
        )

    def test_gps_strict_and_forensic_v2_are_only_reached_from_old_v5_runner(self) -> None:
        report = audit(ROOT)
        rows = {row["path"]: row for row in report["tools"]}
        expected = ["tools/run_guide_ultime_v5.ps1"]

        gps = rows["tools/build_guide_ultime_gps_route_strict.py"]
        forensic = rows["tools/audit_guide_ultime_route_forensic_v2.py"]

        self.assertEqual(
            gps["references"],
            expected,
            msg=f"GPS strict has unexpected consumers: {gps['references']}",
        )
        self.assertEqual(
            forensic["references"],
            expected,
            msg=f"forensic V2 has unexpected consumers: {forensic['references']}",
        )


if __name__ == "__main__":
    unittest.main()
