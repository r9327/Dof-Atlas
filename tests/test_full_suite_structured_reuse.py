from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import atlas_full_suite_proof as proof
from tools import atlas_integrity
from tools.ci_guide_full_evidence import REUSED_MODULES, prove_ledger


class FullSuiteStructuredReuseTests(unittest.TestCase):
    def test_real_unittest_result_ledger_is_complete_and_excludes_skips(self):
        # This synthetic class must NOT enter the repository's FULL discovery:
        # its skip/xfail are unit fixtures, not real skipped application tests.
        class SyntheticCases(unittest.TestCase):
            def test_pass(self): pass

            @unittest.skip("not part of reusable proof")
            def test_skipped(self): pass

            @unittest.expectedFailure
            def test_expected_failure(self):
                self.fail("expected")

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SyntheticCases)
        expected = proof.ids(suite)
        result = unittest.TextTestRunner(stream=io.StringIO(), verbosity=2,
                                         resultclass=proof.ProofResult).run(suite)
        self.assertTrue(result.wasSuccessful())
        payload = proof.validated_ledger(expected, result.completed,
                                         tests_run=result.testsRun,
                                         successful=result.wasSuccessful(),
                                         sha="a" * 40)
        self.assertEqual(payload["tests_run"], 3)
        self.assertEqual(len(payload["successful_test_ids"]), 1)
        self.assertEqual(len(payload["non_successful_test_ids"]), 2)
        self.assertEqual(proof.module_proofs(payload), {})

    def test_exact_ledger_survives_log_noise_and_proves_complete_module(self):
        a, b = "tests.test_slow.A.test_a", "tests.test_slow.A.test_b"
        p = proof.validated_ledger([a, b], [(a, "ok"), (b, "ok")],
                                   tests_run=2, successful=True, sha="a" * 40)
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "ledger.json"
            f.write_text(json.dumps(p), encoding="utf-8")
            verified = proof.load_verified(f, sha="a" * 40)
            self.assertEqual(proof.module_proofs(verified), {"tests.test_slow": 2})
            with self.assertRaises(ValueError):
                proof.load_verified(f, sha="b" * 40)
            p["successful_test_ids"].pop()
            f.write_text(json.dumps(p), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "account"):
                proof.load_verified(f, sha="a" * 40)

    def test_missing_duplicate_skipped_or_failed_test_never_certified(self):
        a, b = "tests.test_slow.A.test_a", "tests.test_slow.A.test_b"
        scenarios = (
            ([(a, "ok")], 2, True),
            ([(a, "ok"), (a, "ok")], 2, True),
            ([(a, "ok"), (b, "fail")], 2, True),
            ([(a, "ok"), (b, "ok")], 2, False),
        )
        for events, count, passed in scenarios:
            with self.subTest(events=events, passed=passed):
                with self.assertRaises(ValueError):
                    proof.validated_ledger([a, b], events,
                                           tests_run=count, successful=passed,
                                           sha="a" * 40)
        p = proof.validated_ledger([a, b], [(a, "ok"), (b, "skip")],
                                   tests_run=2, successful=True, sha="a" * 40)
        self.assertEqual(proof.module_proofs(p), {})

    def test_guide_exact_case_ids_verified_against_full_ledger(self):
        expected = {
            stage: [f"{module}.Example.test_one", f"{module}.Example.test_two"]
            for stage, module in REUSED_MODULES.items()
        }
        all_ids = sorted(k for group in expected.values() for k in group)
        p = proof.validated_ledger(
            all_ids, [(x, "ok") for x in all_ids], tests_run=len(all_ids),
            successful=True, sha="a" * 40,
        )
        self.assertEqual(prove_ledger(p, expected),
                         {stage: 2 for stage in REUSED_MODULES})
        bad = dict(p)
        bad["successful_test_ids"] = all_ids[:-1]
        with self.assertRaisesRegex(ValueError, "missing"):
            prove_ledger(bad, expected)
        extra = dict(p)
        extra["expected_test_ids"] = all_ids + [
            f"{next(iter(REUSED_MODULES.values()))}.Example.test_unknown",
        ]
        with self.assertRaisesRegex(ValueError, "unexpected"):
            prove_ledger(extra, expected)

    def test_full_uses_structured_runner_and_critical_inventory_stays_independent(self):
        policy = atlas_integrity.load_policy(Path(__file__).resolve().parents[1])
        command = atlas_integrity._command_for_group(
            "FULL_SUITE", policy["groups"]["FULL_SUITE"],
            root=Path(__file__).resolve().parents[1],
            base_ref="main", changed=[],
        )
        self.assertIn("tools.atlas_full_suite_proof", command)
        self.assertIn("discover", command)
        critical = atlas_integrity._command_for_group(
            "TEST_INTEGRITY", policy["groups"]["TEST_INTEGRITY"],
            root=Path(__file__).resolve().parents[1],
            base_ref="main", changed=[],
        )
        self.assertIn("unittest", critical)
        self.assertNotIn("tools.atlas_full_suite_proof", critical)

    def test_dangerous_guide_proof_fallback_is_never_claimed_as_full(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "proof.json"
            with patch.object(proof, "SCHEMA", 1):
                with self.assertRaises(ValueError):
                    proof.load_verified(path, sha="a" * 40)


if __name__ == "__main__":
    unittest.main()
