from __future__ import annotations

import unittest

from tools.audit_guide_ultime_support_routes import audit


class GuideUltimeSupportRoutesAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Immutable canonical-route inventory: one real audit, shared by
        # independent read-only assertions in this class.
        cls._canonical_report = audit()

    def test_support_route_inventory_is_complete(self) -> None:
        report = self._canonical_report
        self.assertEqual(report["conditional_route_count"], 6)
        self.assertEqual(report["transversal_route_count"], 1)
        self.assertEqual(report["transversal_stage_count"], 49)
        self.assertEqual(report["class_branch_count"], 19)
        self.assertEqual(report["order_option_count"], 15)
        self.assertGreater(report["temporal_hook_count"], 0)
        if report["catalog_available"]:
            self.assertEqual(report["class_branch_enriched_count"], 19)
            self.assertTrue(report["catalog_enrichment_complete"])
        else:
            self.assertEqual(report["class_branch_enriched_count"], 0)
            self.assertFalse(report["catalog_enrichment_complete"])
            self.assertEqual(report["status"], "CATALOG_UNAVAILABLE")

    def test_support_routes_have_no_hard_issue(self) -> None:
        report = self._canonical_report
        self.assertEqual(report["hard_issue_count"], 0, report["issues"])
        self.assertNotIn("class_quest_missing_from_catalog", report["issue_counts"] if not report["catalog_available"] else {})


if __name__ == "__main__":
    unittest.main()
