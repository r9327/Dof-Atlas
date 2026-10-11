from __future__ import annotations

import unittest

from tools.phase_adaptive_gate import choose_route, critical_changed, verify_scoped

BASE = "a" * 40
HEAD = "b" * 40
FINGERPRINT = "c" * 64


def plan(status: str = "READY_TO_RUN_SCOPED"):
    return {
        "candidate_sha": HEAD,
        "base_sha": BASE,
        "status": status,
        "independent_verdict": {"status": "POLICY_CONFORMING"},
        "independent_policy": {"root_of_trust_changed": False, "canonical_risk": "MEDIUM"},
        "test_modules": ["tests.test_example"],
        "plan_fingerprint": FINGERPRINT,
        "reasons": [],
    }


class PhaseAdaptiveGateTests(unittest.TestCase):
    def test_scoped_for_low_risk_with_complete_doctor_plan(self):
        route = choose_route(plan(), ["app/pages/safe_helper.py"],
                             base_sha=BASE, candidate_sha=HEAD)
        self.assertEqual(route["route"], "SCOPED")
        self.assertEqual(route["test_modules"], ["tests.test_example"])
        self.assertFalse(route["phase_certified"])
        self.assertFalse(route["merge_authorized"])

    def test_trust_changes_force_full_even_when_doctor_claims_scoped(self):
        for path in (
            ".github/workflows/phase-certification.yml",
            ".github/workflows/new-workflow.yml",
            "tools/phase_adaptive_gate.py",
            "tools/atlas_doctor_lib/certification_policy.py",
            "tools/ci_scope_gate.py",
            "tools/run_guide_ultime_ci.ps1",
            "tools/atlas_integrity.py",
            "tools/atlas_full_suite_proof.py",
        ):
            with self.subTest(path=path):
                route = choose_route(plan(), [path], base_sha=BASE, candidate_sha=HEAD)
                self.assertEqual(route["route"], "FULL")
                self.assertIn("ROOT_OF_TRUST_CHANGED", route["reasons"])
        self.assertIn("tools/phase_adaptive_gate.py",
                      critical_changed(["tools/phase_adaptive_gate.py"]))

    def test_unverified_planner_cannot_downscope(self):
        for status in ("FULL_REQUIRED", "BLOCKED", "unexpected"):
            with self.subTest(status=status):
                self.assertEqual(
                    choose_route(plan(status), ["app/x.py"], base_sha=BASE,
                                 candidate_sha=HEAD)["route"], "FULL",
                )
        self.assertEqual(
            choose_route(None, ["app/x.py"], base_sha=BASE, candidate_sha=HEAD)["route"],
            "FULL",
        )

    def test_planner_identity_coverage_and_risk_are_mandatory(self):
        for mutation in (
            lambda p: p.update(candidate_sha=BASE),
            lambda p: p.update(test_modules=[]),
            lambda p: p.update(test_modules=["tests.x", "tests.x"]),
            lambda p: p.update(independent_verdict={"status": "BLOCKED"}),
            lambda p: p.update(independent_policy={"root_of_trust_changed": True}),
            lambda p: p.update(independent_policy={"canonical_risk": "HIGH"}),
            lambda p: p.update(reasons=["unknown dependency"]),
            lambda p: p.update(plan_fingerprint=None),
        ):
            p = plan()
            mutation(p)
            self.assertEqual(choose_route(p, ["app/x.py"],
                                          base_sha=BASE, candidate_sha=HEAD)["route"], "FULL")
        with self.assertRaises(ValueError):
            choose_route(plan(), [], base_sha="", candidate_sha=HEAD)

    def test_push_and_manual_are_full_even_if_plan_scoped(self):
        r = choose_route(plan(), ["app/x.py"], base_sha=BASE,
                         candidate_sha=HEAD, forced=True)
        self.assertEqual(r["route"], "FULL")
        self.assertIn("FULL_DISPATCH_EXPLICIT_OR_MAIN_PUSH", r["reasons"])

    def test_scoped_evidence_verification_enforces_exact_modules_and_passport(self):
        route = choose_route(plan(), ["app/x.py"], base_sha=BASE, candidate_sha=HEAD)
        report = {
            **plan(),
            "execution": {
                "status": "SCOPED_TESTS_PASS",
                "exit_code": 0,
                "executed_modules": ["tests.test_example"],
            },
            "passport": {
                "verdict": "SCOPED_PASS_NOT_FULL",
                "phase_certified": False,
                "merge_authorized": False,
                "full_suite_waived": False,
            },
            "passport_validation": {"status": "INTEGRITY_CHECKED_NOT_ATTESTED"},
        }
        verify_scoped(route, report)
        bad = {**report, "execution": {**report["execution"], "exit_code": 1}}
        with self.assertRaisesRegex(ValueError, "incomplete"):
            verify_scoped(route, bad)
        bad = {**report, "candidate_sha": BASE}
        with self.assertRaisesRegex(ValueError, "Stale"):
            verify_scoped(route, bad)
        bad = {**report, "passport": {**report["passport"], "phase_certified": True}}
        with self.assertRaises(ValueError):
            verify_scoped(route, bad)

    def test_workflow_routes_full_only_when_required(self):
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / ".github/workflows/phase-certification.yml"
        workflow = path.read_text(encoding="utf-8")
        self.assertIn("tools.phase_adaptive_gate decide", workflow)
        self.assertIn("steps.route.outputs.run_full == 'true'", workflow)
        self.assertIn("steps.route.outputs.run_scoped == 'true'", workflow)
        self.assertIn("tools.phase_adaptive_gate verify-scoped", workflow)
        self.assertIn("tools.atlas_integrity full", workflow)
        self.assertIn("SCOPED_TESTS_PASS_NOT_PHASE_CERTIFIED", workflow)
        self.assertIn('"--force-full"', workflow)


if __name__ == "__main__":
    unittest.main()
