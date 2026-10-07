from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GuideToolsNoVersionedWrappersTests(unittest.TestCase):
    def test_retired_wrappers_stay_deleted(self) -> None:
        self.assertFalse((ROOT / "tools/build_guide_ultime_gps_route_strict.py").exists())
        self.assertFalse((ROOT / "tools/audit_guide_ultime_route_forensic_v2.py").exists())
        self.assertFalse((ROOT / "tools/run_guide_ultime_v5.ps1").exists())


if __name__ == "__main__":
    unittest.main()
