from __future__ import annotations

"""Cheap, isolated contracts for full-suite timing diagnostics."""

import io
import unittest

from tools.atlas_full_suite_proof import ProofResult, ids, validated_timings


class FullSuiteTimingsTests(unittest.TestCase):
    def test_real_unittest_runner_records_all_individual_durations(self):
        def succeed(self):
            self.assertTrue(True)

        def also_succeed(self):
            self.assertEqual(1 + 1, 2)

        # A runtime-created TestCase is not collected by repository discovery.
        Synthetic = type("Synthetic", (unittest.TestCase,), {
            "__module__": "test_full_suite_timings",
            "test_a": succeed,
            "test_b": also_succeed,
        })
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Synthetic)
        expected = ids(suite)
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=2,
                                         resultclass=ProofResult).run(suite)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(len(result.test_duration_seconds), 2)
        report = validated_timings(expected, result.test_duration_seconds,
                                   sha="a" * 40)
        self.assertEqual(report["tests_run"], 2)
        self.assertEqual({row["test"] for row in report["individual_tests"]},
                         set(expected))
        self.assertEqual(len(report["module_totals"]), 1)
        self.assertTrue(all(row["seconds"] >= 0 for row in report["individual_tests"]))

    def test_slowest_test_and_module_are_sorted_without_claiming_coverage(self):
        cases = ["tests.test_fast.A.test_a",
                 "tests.test_slow.B.test_b",
                 "tests.test_slow.B.test_c"]
        elapsed = {cases[0]: 0.05, cases[1]: 3.0, cases[2]: 2.0}
        report = validated_timings(cases, elapsed, sha="a" * 40)
        self.assertEqual(report["kind"], "atlas_full_test_timings_diagnostic")
        self.assertEqual(report["slowest_20_tests"][0]["test"], cases[1])
        self.assertEqual(report["module_totals"][0],
                         {"module": "tests.test_slow", "seconds": 5.0})
        self.assertEqual(report["tests_run"], 3)

    def test_stale_missing_invalid_or_duplicate_timing_records_fail_closed(self):
        a, b = "tests.test_a.A.test_one", "tests.test_b.B.test_two"
        cases = [a, b]
        for records, sha in (
            ({a: 1.0}, "a" * 40),
            ({a: 1.0, b: float("nan")}, "a" * 40),
            ({a: 1.0, b: -1.0}, "a" * 40),
            ({a: 1.0, b: True}, "a" * 40),
            ({a: 1.0, b: 2.0}, "invalid"),
        ):
            with self.subTest(records=records, sha=sha):
                with self.assertRaises(ValueError):
                    validated_timings(cases, records, sha=sha)
        with self.assertRaises(ValueError):
            validated_timings([a, a], {a: 0.1}, sha="a" * 40)


if __name__ == "__main__":
    unittest.main()
