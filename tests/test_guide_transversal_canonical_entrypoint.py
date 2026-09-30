from __future__ import annotations

import unittest

from tools import guide_integrity
from tools import validate_guide_ultime_manual_transversals as canonical


class GuideTransversalCanonicalEntrypointTests(unittest.TestCase):
    def test_guide_integrity_uses_unversioned_transversal_validator(self) -> None:
        check = next(row for row in guide_integrity.CHECKS if row.key == "transversals")
        self.assertIn("tools.validate_guide_ultime_manual_transversals", check.argv)
        self.assertNotIn("tools.validate_guide_ultime_manual_transversals_v16", check.argv)

    def test_canonical_validator_exposes_current_audit(self) -> None:
        report = canonical.audit(skip_catalog=True)
        self.assertIn("status", report)
        self.assertIn("hard_error_count", report)
        self.assertEqual(report.get("schema_version"), 16)


if __name__ == "__main__":
    unittest.main()
