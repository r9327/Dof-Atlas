from __future__ import annotations

import unittest

from tools import guide_tools
from tools.guide_forensic import GuideForensicAudit


class GuideToolsFacadeTests(unittest.TestCase):
    def test_facade_exports_canonical_tools(self) -> None:
        self.assertIs(guide_tools.GuideForensicAudit, GuideForensicAudit)
        self.assertTrue(callable(guide_tools.build_gps_route))
        self.assertTrue(callable(guide_tools.validate_transversals))


if __name__ == "__main__":
    unittest.main()
