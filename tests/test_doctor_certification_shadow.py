from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.certification_shadow import (
    evaluate_shadow, load_full_report, aggregate_shadows,
)

HEAD = "b" * 40


def plan(status="READY_TO_RUN_SCOPED", executed="SCOPED_TESTS_PASS"):
    return {
        "candidate_sha": HEAD, "plan_fingerprint": "fingerprint",
        "status": status,
        "execution": {"status": executed},
    }


def full(verdict="PASS", *, full_suite="PASS", data="PASS", head=HEAD):
    return {
        "head": head, "verdict": verdict,
        "validations_required": ["FULL_SUITE", "DATA_INTEGRITY"],
        "groups": {
            "FULL_SUITE": {"status": full_suite},
            "DATA_INTEGRITY": {"status": data},
        },
        "blockers": [] if verdict == "PASS" else ["RUNTIME_FAILURE"],
    }


class ShadowValidationTests(unittest.TestCase):
    def test_full_success_does_not_grant_certificate(self):
        r = evaluate_shadow(plan(), full())
        self.assertEqual(r["status"], "NO_OBSERVED_DIVERGENCE")
        self.assertTrue(r["full_suite_not_waived"])
        self.assertFalse(r["phase_certified"])
        self.assertFalse(r["merge_authorized"])

    def test_hidden_failure_is_detected(self):
        r = evaluate_shadow(plan(), full("FAIL", data="FAIL"))
        self.assertEqual(r["status"], "POTENTIAL_MISSED_REGRESSION")
        self.assertIn("DATA_INTEGRITY", r["failed_or_blocked_groups"])
        total = aggregate_shadows([r])
        self.assertEqual(total["status"], "BLOCKED")
        self.assertEqual(total["potential_missed_regressions"], 1)

    def test_full_required_was_not_downgraded(self):
        r = evaluate_shadow(plan(status="FULL_REQUIRED", executed="FULL_REQUIRED_NOT_DISPATCHED"), full())
        self.assertEqual(r["status"], "FULL_REMAINED_REQUIRED")

    def test_full_failure_without_scoped_pass_is_not_hidden(self):
        r = evaluate_shadow(plan(executed="FAILED"), full("BLOCKED", full_suite="BLOCKED"))
        self.assertEqual(r["status"], "FULL_BLOCKED")

    def test_incompatible_shas_are_unusable(self):
        r = evaluate_shadow(plan(), full(head="a" * 40))
        self.assertEqual(r["status"], "INVALID_EVIDENCE")
        self.assertIn("CANDIDATE_SHA_MISMATCH", r["errors"])

    def test_missing_full_groups_are_never_accepted(self):
        evidence = full()
        del evidence["groups"]["DATA_INTEGRITY"]
        r = evaluate_shadow(plan(), evidence)
        self.assertEqual(r["status"], "INVALID_EVIDENCE")
        self.assertIn("FULL_EVIDENCE_MISSING:DATA_INTEGRITY", r["errors"])

    def test_empty_shadow_samples_prove_nothing(self):
        self.assertEqual(aggregate_shadows([])["status"], "INSUFFICIENT_EVIDENCE")
        self.assertFalse(aggregate_shadows([evaluate_shadow(plan(), full())])["safe_to_relax_full"])

    def test_report_loader_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "full.json"
            path.write_text(json.dumps(full()), encoding="utf-8")
            self.assertEqual(load_full_report(path)["head"], HEAD)
            path.write_text("[]" ,encoding="utf-8")
            with self.assertRaises(ValueError):
                load_full_report(path)
            path.write_text("x" * (5_000_001), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_full_report(path)

    def test_no_implicit_benchmarks_or_full_in_new_workflow(self):
        source = (Path(__file__).resolve().parents[1] /
                  ".github/workflows/doctor-certification.yml").read_text(encoding="utf-8")
        self.assertNotIn("run_guide_ultime_ci.ps1", source)
        self.assertNotIn("tools.atlas_integrity full", source)
        self.assertIn("tests.test_doctor_certification_shadow", source)


if __name__ == "__main__":
    unittest.main()
