from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GuideToolsHarnessContractTests(unittest.TestCase):
    def test_harness_uses_canonical_entrypoints(self) -> None:
        # The versioned V5 wrapper was retired. Keep validating the active
        # CI harness and the canonical GPS/forensic facade separately.
        harness = (ROOT / "tools/run_guide_ultime_ci.ps1").read_text(encoding="utf-8")
        entrypoints = (ROOT / "tools/guide_integrity_entrypoints.py").read_text(encoding="utf-8")
        self.assertFalse((ROOT / "tools/run_guide_ultime_v5.ps1").exists())
        self.assertIn('"tools.validate_guide_ultime_manual_transversals"', harness)
        self.assertIn('"tools.audit_guide_ultime_canonical_lock"', harness)
        self.assertIn("from tools.guide_gps import main as build_gps_route", entrypoints)
        self.assertIn("from tools.guide_forensic import GuideForensicAudit", entrypoints)
        self.assertNotIn("build_guide_ultime_gps_route_strict.py", harness)
        self.assertNotIn("audit_guide_ultime_route_forensic_v2.py", harness)


if __name__ == "__main__":
    unittest.main()
