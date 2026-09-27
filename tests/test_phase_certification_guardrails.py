from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.phase_certification_verdict import _digest, evaluate_phase


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_PROVIDER = "app/modules/encyclopedia/providers/achievement_provider.py"
FROZEN_BASELINE_PATH = "tools/guide_phase2_baseline.json"


class PhaseCertificationGuardrailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = (ROOT / "PHASE_CERTIFICATION.md").read_text(encoding="utf-8")
        cls.agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        cls.public_pr = (
            ROOT / ".github" / "workflows" / "public-pr-ci.yml"
        ).read_text(encoding="utf-8")
        cls.certification_workflow = (
            ROOT / ".github" / "workflows" / "phase-certification.yml"
        ).read_text(encoding="utf-8")
        cls.policy = json.loads(
            (ROOT / "tools" / "atlas_integrity_policy.json").read_text(encoding="utf-8")
        )
        cls.phase2_baseline = json.loads(
            (ROOT / "tools" / "guide_phase2_baseline.json").read_text(encoding="utf-8")
        )
        cls.phase_verdict = (
            ROOT / "tools" / "phase_certification_verdict.py"
        ).read_text(encoding="utf-8")

    def test_contract_separates_code_validation_and_certification(self) -> None:
        for token in (
            "CODE_DONE",
            "VALIDATED",
            "CERTIFIED",
            "Public PR / Safe Validation",
            "PHASE CERTIFICATION: PASS",
            "DATA_INTEGRITY",
            "FULL_SUITE",
            "NOT RUN",
            "BLOCKED",
            "PASS_BASELINE_NON_REGRESSION",
            "GUIDE CERTIFIED",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.contract)

    def test_agents_requires_certification_before_declaring_phase_finished(self) -> None:
        self.assertIn("PHASE_CERTIFICATION.md", self.agents)
        self.assertIn("CERTIFIED", self.agents)
        self.assertIn("phase terminée", self.agents)

    def test_policy_declares_machine_readable_certification_contract(self) -> None:
        certification = self.policy["certification"]
        self.assertEqual(certification["scope"], "APPLICATION")
        self.assertEqual(certification["minimum_mode"], "FULL")
        self.assertEqual(certification["required_status"], "PASS")
        self.assertEqual(
            set(certification["forbidden_statuses"]),
            {"BLOCKED", "NOT_RUN", "FAILED"},
        )
        required_groups = set(certification["required_groups"])
        self.assertTrue(
            {"GOLDEN_FLOWS", "DIFF_TARGETS", "FULL_SUITE", "DATA_INTEGRITY"}
            <= required_groups
        )
        self.assertTrue(required_groups <= set(self.policy["modes"]["FULL"]))
        self.assertIn("DATA_INTEGRITY", self.policy["modes"]["FULL"])
        self.assertIn(
            "tests.test_phase_certification_guardrails",
            self.policy["groups"]["CI_INTEGRITY"]["modules"],
        )

    def test_phase2_guide_baseline_is_exact_and_non_generic(self) -> None:
        baseline = self.phase2_baseline
        self.assertEqual(baseline["schema_version"], 1)
        self.assertEqual(baseline["baseline_id"], "phase2_guide_building_a7242f6")
        self.assertEqual(
            baseline["base_commit"],
            "a7242f6da5f0a393c2e6a921a2cadf02a36d6b16",
        )
        self.assertEqual(baseline["required_manifest_status"], "BUILDING")
        self.assertEqual(
            set(baseline["allowed_blockers"]),
            {"GUIDE_PREREQUISITE_DATA", "GUIDE_FINAL_COVERAGE"},
        )
        self.assertEqual(baseline["prerequisite"]["hard_error_count"], 10)
        self.assertEqual(baseline["final_coverage"]["partial_count"], 86)
        self.assertEqual(baseline["final_coverage"]["uncovered_count"], 548)
        self.assertIn("data/routes/guide_ultime_manual/**", baseline["protected_globs"])
        self.assertIn("app/modules/encyclopedia/providers/**", baseline["protected_globs"])
        self.assertNotIn(
            "data/routes/guide_ultime_manual/manifest_v1.json",
            baseline["allowed_changed_paths"],
        )

    @staticmethod
    def _baseline_non_regression_case() -> dict[str, object]:
        blockers = ["GUIDE_FINAL_COVERAGE", "GUIDE_PREREQUISITE_DATA"]
        hard_errors = [{"quest_id": 1, "reason": "missing prerequisite"}]
        debt_row = {
            "id": 42,
            "state": "uncovered",
            "missing": ["quest:1"],
        }
        baseline = {
            "schema_version": 1,
            "baseline_id": "test-frozen-baseline",
            "base_commit": "frozen-base",
            "required_manifest_status": "BUILDING",
            "allowed_blockers": blockers,
            "protected_globs": ["app/modules/encyclopedia/providers/**"],
            "allowed_changed_paths": [],
            "prerequisite": {
                "hard_error_count": 1,
                "hard_errors_sha256": _digest(hard_errors),
            },
            "final_coverage": {
                "achievement_count": 1,
                "partial_count": 0,
                "uncovered_count": 1,
                "debt_sha256": _digest([debt_row]),
                "contract_status": "CONTRACTS_COVERED",
                "failed_contract_count": 0,
            },
        }
        integrity = {
            "verdict": "BLOCKED",
            "head": "candidate",
            "blockers": blockers,
            "validations_required": ["DATA_INTEGRITY", "FULL_SUITE"],
            "groups": {
                "DATA_INTEGRITY": {
                    "status": "BLOCKED",
                    "blockers": blockers,
                },
                "FULL_SUITE": {
                    "status": "PASS",
                },
            },
        }
        prerequisite = {
            "hard_error_count": 1,
            "hard_errors": hard_errors,
        }
        coverage = {
            "achievement_count": 1,
            "state_counts": {
                "partial": 0,
                "uncovered": 1,
            },
            "verified_success_contracts": {
                "status": "CONTRACTS_COVERED",
                "failed_contract_count": 0,
            },
            "partial_achievements": [],
            "uncovered_achievements": [debt_row],
        }
        return {
            "integrity": integrity,
            "baseline": baseline,
            "prerequisite": prerequisite,
            "action": {
                "manifest_status": "BUILDING",
                "hard_issue_count": 0,
                "issues": [],
            },
            "coverage": coverage,
            "manifest": {"status": "BUILDING"},
            "base_ref": "phase-base",
            "resolved_base": "descendant-base",
            "candidate_sha": "candidate",
            "changed": [],
        }

    @staticmethod
    def _evaluate(case: dict[str, object]) -> dict[str, object]:
        return evaluate_phase(
            **case,
            baseline_is_ancestor=True,
            baseline_changed=[],
        )

    def test_phase_verdict_carries_frozen_baseline_to_clean_descendant_base(self) -> None:
        report = self._evaluate(self._baseline_non_regression_case())

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["guide_status"], "GUIDE_NOT_CERTIFIED")
        self.assertEqual(report["baseline_protected_changes"], [])
        self.assertEqual(report["protected_changes"], [])

    def test_protected_owner_with_exact_guide_evidence_is_allowed(self) -> None:
        case = self._baseline_non_regression_case()
        case["changed"] = [PROTECTED_PROVIDER]

        report = self._evaluate(case)

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["guide_status"], "GUIDE_NOT_CERTIFIED")
        self.assertEqual(report["protected_changes"], [PROTECTED_PROVIDER])

    def test_absolute_pass_allows_protected_guide_changes_without_baseline_waiver(self) -> None:
        case = self._baseline_non_regression_case()
        case["changed"] = [PROTECTED_PROVIDER]
        integrity = copy.deepcopy(case["integrity"])
        integrity["verdict"] = "PASS"
        integrity["blockers"] = []
        integrity["groups"]["DATA_INTEGRITY"] = {
            "status": "PASS",
            "blockers": [],
        }
        case["integrity"] = integrity
        case["manifest"] = {"status": "CERTIFIED"}
        case["prerequisite"] = {
            "status": "COMPLETE_BY_PROVIDER_ORDER",
            "manifest_status": "CERTIFIED",
            "audit_complete": True,
            "catalog_available": True,
            "provider_quest_count": 1976,
            "hard_error_count": 0,
            "hard_errors": [],
        }
        case["action"] = {
            "manifest_status": "CERTIFIED",
            "hard_issue_count": 0,
            "issues": [],
        }
        case["coverage"] = {
            "status": "COMPLETE_BY_EVIDENCE",
            "audit_complete": True,
            "achievement_catalog_available": True,
            "provider_achievement_count": 2780,
            "achievement_count": 1418,
            "state_counts": {"partial": 0, "uncovered": 0},
            "partial_achievements": [],
            "uncovered_achievements": [],
            "verified_success_contracts": {
                "status": "CONTRACTS_COVERED",
                "contract_count": 38,
                "failed_contract_count": 0,
            },
        }

        report = self._evaluate(case)

        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["guide_status"], "GUIDE_CERTIFIED")
        self.assertEqual(report["raw_integrity_verdict"], "PASS")
        self.assertEqual(report["baseline_debt"], [])
        self.assertEqual(report["errors"], [])

    def test_absolute_pass_rejects_hard_guide_action_issue(self) -> None:
        case = self._baseline_non_regression_case()
        case["changed"] = [PROTECTED_PROVIDER]
        integrity = copy.deepcopy(case["integrity"])
        integrity["verdict"] = "PASS"
        integrity["blockers"] = []
        integrity["groups"]["DATA_INTEGRITY"] = {"status": "PASS", "blockers": []}
        case["integrity"] = integrity
        case["manifest"] = {"status": "CERTIFIED"}
        case["prerequisite"] = {
            "status": "COMPLETE_BY_PROVIDER_ORDER",
            "manifest_status": "CERTIFIED",
            "audit_complete": True,
            "catalog_available": True,
            "provider_quest_count": 1976,
            "hard_error_count": 0,
            "hard_errors": [],
        }
        case["action"] = {
            "manifest_status": "CERTIFIED",
            "hard_issue_count": 1,
            "issues": [{"severity": "hard"}],
        }
        case["coverage"] = {
            "status": "COMPLETE_BY_EVIDENCE",
            "audit_complete": True,
            "achievement_catalog_available": True,
            "provider_achievement_count": 2780,
            "achievement_count": 1418,
            "state_counts": {"partial": 0, "uncovered": 0},
            "partial_achievements": [],
            "uncovered_achievements": [],
            "verified_success_contracts": {
                "status": "CONTRACTS_COVERED",
                "contract_count": 38,
                "failed_contract_count": 0,
            },
        }

        report = self._evaluate(case)

        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["guide_status"], "GUIDE_NOT_CERTIFIED")
        self.assertIn("Guide action audit has hard issues", report["errors"])

    def test_absolute_pass_still_rejects_frozen_baseline_tampering(self) -> None:
        case = self._baseline_non_regression_case()
        case["changed"] = [PROTECTED_PROVIDER, FROZEN_BASELINE_PATH]
        integrity = copy.deepcopy(case["integrity"])
        integrity["verdict"] = "PASS"
        integrity["blockers"] = []
        integrity["groups"]["DATA_INTEGRITY"] = {
            "status": "PASS",
            "blockers": [],
        }
        case["integrity"] = integrity

        report = self._evaluate(case)

        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "frozen Guide baseline modified in current phase diff: " + FROZEN_BASELINE_PATH,
            report["errors"],
        )

    def test_protected_owner_with_prerequisite_fingerprint_drift_fails(self) -> None:
        case = self._baseline_non_regression_case()
        case["changed"] = [PROTECTED_PROVIDER]
        prerequisite = copy.deepcopy(case["prerequisite"])
        prerequisite["hard_errors"][0]["reason"] = "different prerequisite debt"
        case["prerequisite"] = prerequisite

        report = self._evaluate(case)

        self.assertEqual(report["status"], "FAIL")
        self.assertIn("prerequisite baseline fingerprint drift", report["errors"])

    def test_protected_owner_with_final_coverage_fingerprint_drift_fails(self) -> None:
        case = self._baseline_non_regression_case()
        case["changed"] = [PROTECTED_PROVIDER]
        coverage = copy.deepcopy(case["coverage"])
        coverage["uncovered_achievements"][0]["missing"] = ["quest:999"]
        case["coverage"] = coverage

        report = self._evaluate(case)

        self.assertEqual(report["status"], "FAIL")
        self.assertIn("final coverage baseline fingerprint drift", report["errors"])

    def test_protected_owner_with_contract_metric_drift_fails(self) -> None:
        case = self._baseline_non_regression_case()
        case["changed"] = [PROTECTED_PROVIDER]
        coverage = copy.deepcopy(case["coverage"])
        coverage["achievement_count"] = 2
        case["coverage"] = coverage

        report = self._evaluate(case)

        self.assertEqual(report["status"], "FAIL")
        self.assertIn("achievement scope count drift", report["errors"])

    def test_protected_owner_with_missing_guide_evidence_fails_closed(self) -> None:
        case = self._baseline_non_regression_case()
        case["changed"] = [PROTECTED_PROVIDER]
        case["prerequisite"] = {}

        report = self._evaluate(case)

        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(
            any("protected Guide owner evidence incomplete" in error for error in report["errors"]),
            report["errors"],
        )

    def test_protected_owner_with_incomplete_guide_evidence_fails_closed(self) -> None:
        case = self._baseline_non_regression_case()
        case["changed"] = [PROTECTED_PROVIDER]
        coverage = copy.deepcopy(case["coverage"])
        del coverage["verified_success_contracts"]["failed_contract_count"]
        case["coverage"] = coverage

        report = self._evaluate(case)

        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "protected Guide owner evidence incomplete: verified_success_contracts.failed_contract_count missing",
            report["errors"],
        )

    def test_frozen_guide_baseline_tampering_is_always_rejected(self) -> None:
        case = self._baseline_non_regression_case()
        case["changed"] = [FROZEN_BASELINE_PATH]

        report = self._evaluate(case)

        self.assertEqual(report["status"], "FAIL")
        self.assertIn(
            "frozen Guide baseline modified in current phase diff: " + FROZEN_BASELINE_PATH,
            report["errors"],
        )

    def test_real_guide_debt_change_fails_even_when_product_groups_pass(self) -> None:
        case = self._baseline_non_regression_case()
        case["changed"] = [PROTECTED_PROVIDER]
        coverage = copy.deepcopy(case["coverage"])
        coverage["state_counts"]["partial"] = 1
        coverage["partial_achievements"] = [
            {"id": 7, "state": "partial", "missing": ["quest:7"]},
        ]
        case["coverage"] = coverage

        report = self._evaluate(case)

        self.assertEqual(case["integrity"]["groups"]["FULL_SUITE"]["status"], "PASS")
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("partial achievement count drift", report["errors"])
        self.assertIn("final coverage baseline fingerprint drift", report["errors"])
        self.assertFalse(
            any("required group is not PASS" in error for error in report["errors"]),
            report["errors"],
        )

    def test_phase_verdict_rejects_invalid_ancestry_or_inherited_protected_change(self) -> None:
        case = self._baseline_non_regression_case()
        unrelated = evaluate_phase(
            **case,
            baseline_is_ancestor=False,
            baseline_changed=[],
        )
        self.assertEqual(unrelated["status"], "FAIL")
        self.assertTrue(
            any("not descended from frozen Guide baseline" in error for error in unrelated["errors"])
        )

        drifted = evaluate_phase(
            **case,
            baseline_is_ancestor=True,
            baseline_changed=[
                "app/modules/encyclopedia/providers/guide_provider.py",
            ],
        )
        self.assertEqual(drifted["status"], "FAIL")
        self.assertEqual(
            drifted["baseline_protected_changes"],
            ["app/modules/encyclopedia/providers/guide_provider.py"],
        )
        self.assertTrue(
            any("changed since frozen baseline" in error for error in drifted["errors"])
        )

    def test_phase_verdict_never_waives_full_suite_unknown_blockers_or_incomplete_evidence(self) -> None:
        source = self.phase_verdict
        self.assertIn('name == "DATA_INTEGRITY"', source)
        self.assertIn('groups.get("FULL_SUITE")', source)
        self.assertIn("FULL_SUITE is not absolute PASS", source)
        self.assertIn("unexpected integrity blockers", source)
        self.assertIn("changed since frozen baseline", source)
        self.assertIn("merge-base", source)
        self.assertIn("protected Guide owner evidence incomplete", source)
        self.assertIn("frozen Guide baseline modified in current phase diff", source)
        self.assertIn("prerequisite baseline fingerprint drift", source)
        self.assertIn("final coverage baseline fingerprint drift", source)
        self.assertIn("PASS_BASELINE_NON_REGRESSION", source)
        self.assertIn("GUIDE_CERTIFIED", source)
        self.assertIn("GUIDE_NOT_CERTIFIED", source)
        self.assertIn("Guide quest catalog is unavailable", source)

    def test_public_pr_is_explicitly_not_phase_certification(self) -> None:
        self.assertIn("PR SAFE VALIDATION ONLY", self.public_pr)
        self.assertIn("NOT PHASE CERTIFICATION", self.public_pr)
        self.assertIn("tests.test_phase_certification_guardrails", self.public_pr)

    def test_phase_certification_is_exact_head_full_gate_for_phase_prs(self) -> None:
        source = self.certification_workflow
        self.assertIn("workflow_dispatch:", source)
        self.assertIn("pull_request:", source)
        self.assertNotIn("push:\n", source)
        self.assertIn("synchronize", source)
        self.assertIn("startsWith(github.event.pull_request.title, 'Phase ')", source)
        self.assertIn(
            "github.event.pull_request.head.repo.full_name == github.repository",
            source,
        )
        self.assertIn("CANDIDATE_SHA:", source)
        self.assertIn("CERT_BASE_REF:", source)
        self.assertIn("github.event.pull_request.head.sha", source)
        self.assertIn("github.event.pull_request.base.sha", source)
        self.assertIn("name: Verify exact certification checkout", source)
        self.assertIn("git rev-parse HEAD", source)
        self.assertIn("Certification checkout mismatch", source)
        self.assertIn("name: Phase Certification / Full Validation", source)
        self.assertIn("runs-on: windows-latest", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("fetch-depth: 0", source)
        self.assertIn("tools.atlas_integrity full", source)
        self.assertIn("--json", source)
        self.assertIn("tools.phase_certification_verdict", source)
        self.assertIn("03_atlas_integrity_full.json", source)
        self.assertIn("04_phase_verdict.json", source)
        self.assertIn("$env:CANDIDATE_SHA", source)
        self.assertIn("PHASE CERTIFICATION: NOT CERTIFIED", source)
        self.assertIn("PHASE CERTIFICATION: PASS", source)
        self.assertIn("PASS_BASELINE_NON_REGRESSION", source)
        self.assertIn("steps.lfs.outcome", source)
        self.assertIn("steps.catalog.outcome", source)


if __name__ == "__main__":
    unittest.main()
