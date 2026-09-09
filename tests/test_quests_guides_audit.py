from __future__ import annotations

import unittest

from app.modules.encyclopedia.tools.audit_quests_guides import build_audit


class QuestsGuidesAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = build_audit()
        cls.inventory = cls.audit["summary"]["inventory"]
        cls.severities = cls.audit["summary"]["issues_by_severity"]

    def test_active_quest_catalog_identity_is_consistent(self):
        self.assertEqual(self.inventory["active_quests"], self.inventory["raw_quest_rows"])
        self.assertEqual(self.inventory["active_quests"], self.inventory["active_quest_ids_unique"])
        self.assertEqual(self.inventory["raw_quests_without_id"], 0)
        self.assertEqual(self.inventory["active_duplicate_quest_ids"], 0)
        self.assertEqual(self.inventory["raw_duplicate_quest_ids"], 0)

    def test_guides_resolve_to_active_quest_catalog(self):
        self.assertGreater(self.inventory["active_guides"], 0)
        self.assertGreater(self.inventory["guide_quest_references_total"], 0)
        self.assertEqual(self.inventory["dead_guide_quest_references"], 0)
        self.assertEqual(self.inventory["guides_without_chapters"], 0)
        self.assertEqual(self.inventory["guides_without_quests"], 0)

    def test_prerequisites_images_and_progress_have_no_blocking_breakage(self):
        self.assertEqual(self.inventory["graph_missing_edges"], 0)
        self.assertEqual(self.inventory["graph_self_edges"], 0)
        self.assertEqual(self.inventory["missing_referenced_images"], 0)
        self.assertEqual(self.inventory["bad_format_referenced_images"], 0)
        self.assertEqual(self.inventory["guide_progress_inconsistencies"], 0)
        self.assertEqual(self.inventory["user_progress_invalid_quest_refs"], 0)
        self.assertEqual(self.inventory["user_progress_invalid_objective_refs"], 0)

    def test_no_critical_or_automatic_fixable_issue_remains(self):
        self.assertEqual(self.severities.get("critical", 0), 0)
        self.assertEqual(self.severities.get("fixable", 0), 0)

    def test_manual_review_entries_are_actionable(self):
        for row in self.audit["manual_review"]:
            self.assertTrue(row["subject_id"])
            self.assertTrue(row["title"])
            self.assertTrue(row["field"])
            self.assertTrue(row["reason"])


if __name__ == "__main__":
    unittest.main()
