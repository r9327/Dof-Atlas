from __future__ import annotations

import unittest

from tools import guide_integrity_entrypoints, guide_tools
from tools.guide_forensic import GuideForensicAudit


class GuideToolsFacadeTests(unittest.TestCase):
    def test_facade_exports_canonical_tools(self) -> None:
        self.assertIs(guide_tools.GuideForensicAudit, GuideForensicAudit)
        self.assertIs(
            guide_tools.GuideForensicAudit,
            guide_integrity_entrypoints.GuideForensicAudit,
        )
        self.assertIs(
            guide_tools.build_gps_route,
            guide_integrity_entrypoints.build_gps_route,
        )
        self.assertIs(
            guide_tools.validate_transversals,
            guide_integrity_entrypoints.validate_transversals,
        )


if __name__ == "__main__":
    unittest.main()
