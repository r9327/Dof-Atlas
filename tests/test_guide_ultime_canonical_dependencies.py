from __future__ import annotations

import unittest

from tools.audit_guide_ultime_canonical_dependencies import (
    BONTA_DEPENDENT_CHAPTERS,
    CANONICAL_BONTA_FILE,
    EXPECTED_CANONICAL_SUPPORT_FILES,
    EXPECTED_KRALAMOURE_HOOK,
    OCRE_COMPLETION_FILE,
    audit,
)


class GuideUltimeCanonicalDependenciesTests(unittest.TestCase):
    def test_canonical_dependency_audit_passes(self) -> None:
        report = audit()
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["chapter_count"], 13)
        self.assertEqual(report["critical_dependency_count"], 12)
        self.assertEqual(report["errors"], [])

    def test_all_bonta_hook_chapters_use_only_current_bonta_route(self) -> None:
        report = audit()
        by_id = {row["id"]: row for row in report["chapters"]}
        self.assertEqual(set(BONTA_DEPENDENT_CHAPTERS), set(by_id).intersection(BONTA_DEPENDENT_CHAPTERS))
        for chapter_id in BONTA_DEPENDENT_CHAPTERS:
            self.assertEqual(
                by_id[chapter_id]["bonta_dependencies"],
                [CANONICAL_BONTA_FILE],
                chapter_id,
            )

    def test_no_canonical_dependency_points_to_missing_json(self) -> None:
        report = audit()
        missing = [row for row in report["errors"] if row.get("code") == "dependency_file_missing"]
        self.assertEqual(missing, [])

    def test_all_manifest_supports_are_exact_current_versions(self) -> None:
        report = audit()
        self.assertEqual(report["status"], "PASS", report["errors"])
        supports = {row["id"]: row for row in report["critical_supports"]}
        for item_id, filename in EXPECTED_CANONICAL_SUPPORT_FILES.items():
            self.assertIn(item_id, supports)
            self.assertEqual(supports[item_id]["file"], filename)
            self.assertTrue(supports[item_id]["exists"])

    def test_ocre_completion_uses_current_capture_temporal_and_kralamoure_hook(self) -> None:
        report = audit()
        supports = {row["id"]: row for row in report["critical_supports"]}
        ocre = supports["ocre_completion_route"]
        self.assertEqual(ocre["file"], OCRE_COMPLETION_FILE)
        self.assertEqual(
            set(ocre["dependencies"]),
            {
                EXPECTED_CANONICAL_SUPPORT_FILES["ocre_capture_registry"],
                EXPECTED_CANONICAL_SUPPORT_FILES["temporal_registry"],
            },
        )
        self.assertEqual(ocre["kralamoure_temporal_hook"], EXPECTED_KRALAMOURE_HOOK)


if __name__ == "__main__":
    unittest.main()
