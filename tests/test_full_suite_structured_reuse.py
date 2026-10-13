from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import atlas_full_suite_proof as proof
from tools import atlas_integrity
from tools.ci_guide_full_evidence import REUSED_MODULES, REUSED_MULTI_STAGES, prove_ledger


class FullSuiteStructuredReuseTests(unittest.TestCase):
    def test_real_unittest_result_ledger_is_complete_and_excludes_skips(self):
        # This synthetic class must NOT enter the repository's FULL discovery:
        # its skip/xfail are unit fixtures, not real skipped application tests.
        # A dynamically-created class has a normal canonical unittest ID
        # without <locals>, but is invisible to normal module discovery.
        def passing(self):
            return None

        def skipping(self):
            return None

        def expected_failure(self):
            self.fail("expected")

        SyntheticCases = type("SyntheticCases", (unittest.TestCase,), {
            "__module__": "test_full_suite_structured_reuse",
            "test_pass": passing,
            "test_skipped": unittest.skip("not part of reusable proof")(skipping),
            "test_expected_failure": unittest.expectedFailure(expected_failure),
        })

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

    def test_native_unittest_durations_preserve_structured_pass_ledger(self):
        def passing(self):
            self.assertTrue(True)

        SyntheticCases = type("SyntheticCases", (unittest.TestCase,), {
            "__module__": "test_full_suite_structured_reuse",
            "test_pass": passing,
        })
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SyntheticCases)
        result = unittest.TextTestRunner(
            stream=io.StringIO(), resultclass=proof.ProofResult,
            verbosity=2, durations=20,
        ).run(suite)
        self.assertTrue(result.wasSuccessful())
        self.assertEqual(len(result.collectedDurations), 1)
        self.assertGreaterEqual(result.collectedDurations[0][1], 0)
        self.assertEqual(len(result.completed), 1)
        self.assertEqual(result.completed[0][1], "ok")

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
        for stage, modules in REUSED_MULTI_STAGES.items():
            expected[stage] = [f"{module}.Example.test_one" for module in modules]
        all_ids = sorted(k for group in expected.values() for k in group)
        p = proof.validated_ledger(
            all_ids, [(x, "ok") for x in all_ids], tests_run=len(all_ids),
            successful=True, sha="a" * 40,
        )
        self.assertEqual(prove_ledger(p, expected),
                         {stage: len(cases) for stage, cases in expected.items()})
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

    def test_guide_multi_stage_falls_back_on_missing_or_skipped_full_cases(self):
        stages = {
            stage: [f"{module}.Case.test_ok" for module in modules]
            for stage, modules in REUSED_MULTI_STAGES.items()
        }
        expected = {**{s: [f"{m}.Case.test_ok"] for s, m in REUSED_MODULES.items()}, **stages}
        all_ids = sorted(x for group in expected.values() for x in group)
        good = proof.validated_ledger(
            all_ids, [(case, "ok") for case in all_ids],
            tests_run=len(all_ids), successful=True, sha="a" * 40,
        )
        self.assertEqual(prove_ledger(good, expected),
                         {stage: len(cases) for stage, cases in expected.items()})
        for bad_id in [stages["02_guide_ultime_core_tests"][0],
                       stages["03_manual_route_composition_tests"][0]]:
            with self.subTest(case=bad_id):
                skipped = dict(good, successful_test_ids=[x for x in all_ids if x != bad_id],
                               non_successful_test_ids=[bad_id])
                with self.assertRaisesRegex(ValueError, "missing|skipped"):
                    prove_ledger(skipped, expected)
                incomplete = dict(good, expected_test_ids=[x for x in all_ids if x != bad_id])
                with self.assertRaisesRegex(ValueError, "missing|skipped"):
                    prove_ledger(incomplete, expected)

    def test_guide_runner_multi_stage_fallback_invokes_unittest_once(self):
        script = (Path(__file__).resolve().parents[1] / "tools"
                  / "run_guide_ultime_ci.ps1").read_text(encoding="utf-8")
        self.assertIn('Invoke-PythonCheck $Name (@("-m", "unittest") + $Module)', script)
        for stage in REUSED_MULTI_STAGES:
            marker = 'Invoke-GuideTestOrReuse "' + stage + '" @('
            self.assertIn(marker, script)
            lines = script.split(marker, 1)[1].split(')', 1)[0]
            self.assertNotIn('"-m", "unittest"', lines)

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
