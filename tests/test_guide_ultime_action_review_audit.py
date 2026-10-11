from __future__ import annotations

import unittest

from tools.audit_guide_ultime_manual_runtime import audit


class GuideUltimeActionReviewAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Immutable canonical-route inventory: one real audit, shared by
        # independent read-only assertions in this class.
        cls._canonical_report = audit()

    def test_action_review_inventory_covers_all_locked_chapters(self) -> None:
        report = self._canonical_report
        self.assertEqual(report["chapter_count"], 13)
        self.assertEqual(report["card_count"], 267)
        chapters = report["action_review"]["chapters"]
        self.assertEqual(set(chapters), set(report["chapter_ids"]))
        self.assertEqual(sum(int(row["stage_count"]) for row in chapters.values()), 267)

    def test_action_review_status_is_derived_from_real_structure(self) -> None:
        report = self._canonical_report
        allowed = {
            "STRUCTURE_BLOCKED",
            "ACTION_REVIEW_WITH_STRUCTURING_GAPS",
            "ACTION_REVIEW_READY",
        }
        for chapter_id, row in report["action_review"]["chapters"].items():
            self.assertIn(row["status"], allowed, chapter_id)
            self.assertGreaterEqual(int(row["instruction_line_count"]), 0, chapter_id)
            self.assertGreaterEqual(int(row["positioned_stage_count"]), 0, chapter_id)
            self.assertGreaterEqual(int(row["structured_target_stage_count"]), 0, chapter_id)
            if row["empty_stage_ids"] or row["unsupported_stage_fields"]:
                self.assertEqual(row["status"], "STRUCTURE_BLOCKED", chapter_id)
            elif row["gap_stage_ids"]:
                self.assertEqual(row["status"], "ACTION_REVIEW_WITH_STRUCTURING_GAPS", chapter_id)
            else:
                self.assertEqual(row["status"], "ACTION_REVIEW_READY", chapter_id)

    def test_gap_stage_count_matches_unique_stage_ids(self) -> None:
        report = self._canonical_report
        for chapter_id, row in report["action_review"]["chapters"].items():
            stage_ids = list(row["gap_stage_ids"])
            self.assertEqual(len(stage_ids), len(set(stage_ids)), chapter_id)
            self.assertEqual(int(row["gap_stage_count"]), len(stage_ids), chapter_id)


if __name__ == "__main__":
    unittest.main()
