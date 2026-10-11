from __future__ import annotations

import unittest

from tools.ci_guide_full_evidence import prove, REUSED_MODULES


def _expected():
    return {
        "11_existing_guides_tests": ["tests.test_guides_phase3.G.test_a"],
        "12_existing_success_tests": ["tests.test_achievements_lot7.A.test_b"],
        "13_existing_shell_tests": ["tests.test_pyside_shell.S.test_c"],
    }


def _full(*, line_a="... ok", suffix="OK"):
    return (
        "test_a (test_guides_phase3.G.test_a) " + line_a + "\n"
        "test_b (test_achievements_lot7.A.test_b) ... ok\n"
        "test_c (test_pyside_shell.S.test_c) ... ok\n"
        "----------------------------------------------------------------------\n"
        "Ran 3 tests in 0.002s\n\n" + suffix + "\n"
    )


class GuideExactFullEvidenceTests(unittest.TestCase):
    def test_complete_full_exact_ids_can_be_reused(self):
        self.assertEqual(
            prove(_full(), _expected()),
            {name: 1 for name in REUSED_MODULES},
        )

    def test_windows_crlf_log_is_validated_exactly(self):
        self.assertEqual(
            prove(_full().replace("\n", "\r\n"), _expected()),
            {name: 1 for name in REUSED_MODULES},
        )

    def test_failed_full_cannot_be_reused(self):
        with self.assertRaises(ValueError):
            prove(_full(suffix="FAILED (failures=1)"), _expected())

    def test_skipped_target_test_cannot_be_reused(self):
        with self.assertRaises(ValueError):
            prove(_full(line_a="... skipped 'reason'"), _expected())

    def test_missing_target_test_cannot_be_reused(self):
        changed = _full().replace(
            "test_b (test_achievements_lot7.A.test_b) ... ok\n", ""
        )
        with self.assertRaises(ValueError):
            prove(changed, _expected())

    def test_duplicate_or_different_target_test_cannot_be_reused(self):
        with self.assertRaises(ValueError):
            prove(_full().replace(
                "test_c (test_pyside_shell.S.test_c) ... ok",
                "test_c (test_pyside_shell.S.test_unknown) ... ok",
            ), _expected())

    def test_recursively_repeated_successful_tests_do_not_invalidate_proof(self):
        line = "test_c (test_pyside_shell.S.test_c) ... ok\n"
        repeated = _full().replace(line, line + line)
        self.assertEqual(
            prove(repeated, _expected()),
            {name: 1 for name in REUSED_MODULES},
        )

    def test_incomplete_discovery_cannot_be_reused(self):
        incomplete = _expected()
        incomplete["12_existing_success_tests"] = []
        with self.assertRaises(ValueError):
            prove(_full(), incomplete)


if __name__ == "__main__":
    unittest.main()
