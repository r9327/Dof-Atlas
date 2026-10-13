from __future__ import annotations

"""Cheap contract tests for FULL per-case/fixture timing diagnostics."""

import io
import unittest

from tools import atlas_full_suite_proof as full


def _cases(*, fail: bool = False) -> unittest.TestSuite:
    def first(self):
        self.assertTrue(True)

    def second(self):
        if fail:
            self.fail("deliberate profiling fixture failure")

    Synthetic = type(
        "ProfileCases",
        (unittest.TestCase,),
        {
            "__module__": "test_full_suite_timing_profile",
            "test_first": first,
            "test_second": second,
        },
    )
    return unittest.defaultTestLoader.loadTestsFromTestCase(Synthetic)


class FullSuiteTimingProfileTests(unittest.TestCase):
    def test_all_real_tests_are_timed_and_bound_to_sha(self):
        suite = _cases()
        expected = full.ids(suite)
        result = unittest.TextTestRunner(
            stream=io.StringIO(), resultclass=full.ProofResult,
        ).run(suite)
        self.assertTrue(result.wasSuccessful())
        report = full.timing_report(
            expected, result.timings,
            sha="a" * 40, suite_seconds=1.0, successful=True,
        )
        self.assertEqual(report["kind"], "atlas_full_unittest_timing_diagnostic")
        self.assertEqual(report["status"], "COMPLETE")
        self.assertEqual(report["tests_timed"], 2)
        self.assertEqual({row["test_id"] for row in report["per_test"]}, set(expected))
        self.assertEqual(len(report["slowest_20"]), 2)
        for row in report["per_test"]:
            self.assertGreaterEqual(row["test_seconds"], 0)
            self.assertGreaterEqual(row["preceding_fixture_seconds"], 0)
            self.assertGreaterEqual(row["total_seconds"], row["test_seconds"])
        proof = full.validated_ledger(
            expected, result.completed, tests_run=result.testsRun,
            successful=result.wasSuccessful(), sha="a" * 40,
        )
        self.assertEqual(proof["tests_run"], report["tests_timed"])

    def test_failed_suite_is_only_diagnostic_never_certified(self):
        suite = _cases(fail=True)
        expected = full.ids(suite)
        result = unittest.TextTestRunner(
            stream=io.StringIO(), resultclass=full.ProofResult,
        ).run(suite)
        self.assertFalse(result.wasSuccessful())
        report = full.timing_report(
            expected, result.timings,
            sha="b" * 40, suite_seconds=1.0, successful=False,
        )
        self.assertEqual(report["status"], "FAILED")
        with self.assertRaises(ValueError):
            full.validated_ledger(
                expected, result.completed, tests_run=result.testsRun,
                successful=result.wasSuccessful(), sha="b" * 40,
            )

    def test_missing_duplicate_or_stale_timing_is_rejected(self):
        names = ["tests.test_example.Sample.test_a", "tests.test_example.Sample.test_b"]
        a = {"test_id": names[0], "test_seconds": 0.1,
             "preceding_fixture_seconds": 0.4, "total_seconds": 0.5}
        b = {"test_id": names[1], "test_seconds": 0.3,
             "preceding_fixture_seconds": 0.0, "total_seconds": 0.3}
        report = full.timing_report(
            names, [b, a], sha="c" * 40,
            suite_seconds=0.9, successful=True,
        )
        self.assertEqual(report["slowest_20"][0]["test_id"], names[0])
        self.assertEqual(report["unattributed_tail_seconds"], 0.1)
        for broken in ([a], [a, a]):
            with self.subTest(broken=broken):
                with self.assertRaises(ValueError):
                    full.timing_report(
                        names, broken, sha="c" * 40,
                        suite_seconds=0.9, successful=True,
                    )
        with self.assertRaises(ValueError):
            full.timing_report(
                names, [a, b], sha="wrong",
                suite_seconds=0.9, successful=True,
            )


if __name__ == "__main__":
    unittest.main()
