from __future__ import annotations

import unittest

from tools import guide_integrity_entrypoints
from tools.guide_forensic import GuideForensicAudit


class GuideIntegrityEntrypointsTests(unittest.TestCase):
    def test_exports_canonical_dependencies(self) -> None:
        self.assertIs(guide_integrity_entrypoints.GuideForensicAudit, GuideForensicAudit)
        self.assertTrue(callable(guide_integrity_entrypoints.build_gps_route))
        self.assertTrue(callable(guide_integrity_entrypoints.validate_transversals))


if __name__ == "__main__":
    unittest.main()
