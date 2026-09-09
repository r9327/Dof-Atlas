from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.atlas_critical_coverage import load_policy


ROOT = Path(__file__).resolve().parents[1]


class CriticalCoverageTests(unittest.TestCase):
    def test_thresholds_are_nonzero_and_owned_by_real_modules_and_tests(self) -> None:
        policy = load_policy(ROOT)
        for target in policy["targets"]:
            self.assertGreater(target["minimum_percent"], 0)
            self.assertTrue((ROOT / target["module"]).is_file())
            for module in target["tests"]:
                self.assertTrue((ROOT / Path(*module.split(".")).with_suffix(".py")).is_file())

    def test_policy_records_measured_floors_not_global_hundred_percent(self) -> None:
        payload = json.loads((ROOT / "tools/atlas_critical_coverage.json").read_text(encoding="utf-8"))
        floors = {row["module"]: row["minimum_percent"] for row in payload["targets"]}
        self.assertEqual(floors["app/core/character_identity.py"], 90)
        self.assertEqual(floors["app/network/progress_bridge.py"], 60)
        self.assertTrue(all(value < 95 for value in floors.values()))


if __name__ == "__main__":
    unittest.main()
