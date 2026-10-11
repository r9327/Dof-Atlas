from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.certification_readiness import readiness

SHA = "b" * 40


class CertificationReadinessTests(unittest.TestCase):
    def sample(self):
        return {
            "candidate_sha": SHA,
            "status": "READY_TO_RUN_SCOPED",
            "execution": {"status": "SCOPED_TESTS_PASS"},
            "independent_verdict": {"status": "POLICY_CONFORMING"},
            "independent_policy": {"required_metrics": ["steady_rss_home"]},
        }

    def test_green_scoped_is_not_phase_certificate(self):
        verdict = readiness(self.sample())
        self.assertIn("MANDATORY_EXACT_SHA_FULL_UNVERIFIED", verdict["blocking_reasons"])
        self.assertIn("RESOURCE_METRICS_NOT_ATTESTED", verdict["blocking_reasons"])
        self.assertFalse(verdict["merge_authorized"])
        self.assertFalse(verdict["full_suite_waived"])
        self.assertFalse(verdict["phase_certified"])
        self.assertFalse(verdict["tests_reused"])
        self.assertTrue(verdict["next_checks"])

    def test_all_advisory_evidence_still_never_authorizes_merge(self):
        r = self.sample()
        r["runtime_observation"] = {"status": "OBSERVED_NOT_CERTIFIED"}
        r["scenario_execution"] = {"status": "CONTRACTS_PASS_METRICS_NOT_RUN"}
        r["metrics_executed"] = ["steady_rss_home"]
        r["github_origin_verification"] = {
            "status": "ARTIFACT_ORIGIN_VERIFIED_NOT_POLICY_TRUSTED"
        }
        r["policy_authority"] = {"status": "SAME_CODE_ON_PROTECTED_MAIN"}
        r["shadow_comparison"] = {"status": "NO_OBSERVED_DIVERGENCE"}
        r["independent_full_attestation"] = {
            "status": "EXACT_SHA_FULL_VERIFIED", "candidate_sha": SHA,
            "authenticated": True,
        }
        outcome = readiness(r)
        self.assertEqual(outcome["blocking_reasons"], [])
        self.assertEqual(outcome["status"], "EVIDENCE_REVIEW_REQUIRED")
        self.assertFalse(outcome["merge_authorized"])
        self.assertFalse(outcome["phase_certified"])

    def test_wrong_sha_full_attestation_does_not_count(self):
        r = self.sample()
        r["independent_full_attestation"] = {
            "status": "EXACT_SHA_FULL_VERIFIED",
            "candidate_sha": "a" * 40, "authenticated": True,
        }
        out = readiness(r)
        self.assertIn("MANDATORY_EXACT_SHA_FULL_UNVERIFIED", out["blocking_reasons"])

    def test_blocked_safety_policy_shows_actionable_reason(self):
        r = self.sample()
        r["status"] = "BLOCKED"
        r["independent_verdict"] = {"status": "BLOCKED"}
        outcome = readiness(r)
        self.assertIn("DOCTOR_PLANNER_BLOCKED", outcome["blocking_reasons"])
        self.assertIn("INDEPENDENT_POLICY_NOT_CONFORMING", outcome["blocking_reasons"])
        self.assertIn("FULL_REQUIRED_BY_SCOPE", outcome["blocking_reasons"])

    def test_no_missing_memory_metrics_when_not_required(self):
        r = self.sample()
        r["independent_policy"] = {"required_metrics": []}
        self.assertNotIn("RESOURCE_METRICS_NOT_ATTESTED", readiness(r)["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
