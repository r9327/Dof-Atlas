from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GuideToolsHarnessContractTests(unittest.TestCase):
    def test_harness_uses_canonical_entrypoints(self) -> None:
        text = (ROOT / "tools/run_guide_ultime_v5.ps1").read_text(encoding="utf-8")
        self.assertIn("-m tools.guide_gps", text)
        self.assertIn("-m tools.guide_forensic", text)
        self.assertNotIn("build_guide_ultime_gps_route_strict.py", text)
        self.assertNotIn("audit_guide_ultime_route_forensic_v2.py", text)


if __name__ == "__main__":
    unittest.main()
