from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "public-pr-ci.yml"
POLICY = ROOT / "tools" / "atlas_integrity_policy.json"


class PublicPrCiGuardrailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))

    def test_public_pr_runner_stays_github_hosted_and_read_only(self) -> None:
        self.assertIn("pull_request:", self.source)
        self.assertNotIn("pull_request_target:", self.source)
        self.assertIn("runs-on: windows-latest", self.source)
        self.assertNotIn("self-hosted", self.source)
        self.assertRegex(
            self.source,
            r"(?ms)^permissions:\s*\n\s+contents:\s+read\s*$",
        )
        self.assertNotRegex(self.source, r"(?m)^\s+[A-Za-z_-]+:\s*write\s*$")

    def test_public_pr_uses_doctor_fast_as_canonical_merge_gate(self) -> None:
        for token in (
            "tools.atlas_doctor verify",
            "--gate fast",
            '--base-ref "$env:BASE_SHA"',
            "doctor-fast.json",
            "payload.integrity.status",
            "payload.audit.severity.CRITICAL",
            "actions/dependency-review-action@",
            "fail-on-severity: low",
            "pip install --require-hashes --no-deps -r requirements-pyside.txt",
            "git diff --check",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.source)

        fast_groups = set(self.policy["modes"]["FAST"])
        self.assertEqual(
            fast_groups,
            {
                "META_INTEGRITY",
                "SYNTAX",
                "GENERATED_FILES",
                "ARCHITECTURE",
                "IDENTITY",
                "DIFF_TARGETS",
            },
        )

    def test_critical_pr_materializes_heavy_fixtures_conditionally(self) -> None:
        for token in (
            "name: Classify Doctor risk",
            "from tools.atlas_integrity import changed_files, classify_risk",
            "if: steps.doctor_risk.outputs.risk == 'CRITICAL'",
            "git lfs pull --include=",
            "tools/doduda/doduda.exe",
            "QuestCatalog.load()",
            "count < 1900",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.source)

        classify_index = self.source.index("name: Classify Doctor risk")
        materialize_index = self.source.index("name: Materialize CRITICAL Doctor fixtures")
        doctor_index = self.source.index("name: Run canonical Doctor FAST merge gate")
        self.assertLess(classify_index, materialize_index)
        self.assertLess(materialize_index, doctor_index)

    def test_non_doctor_merge_contracts_remain_explicit(self) -> None:
        for module in (
            "tests.test_atlas_integrity",
            "tests.test_ci_runner_guardrails",
            "tests.test_phase_certification_guardrails",
            "tests.test_repository_git_hooks",
            "tests.test_public_pr_ci_guardrails",
            "tests.test_security_hardening_guardrails",
        ):
            self.assertIn(module, self.source)

        ci_modules = set(self.policy["groups"]["CI_INTEGRITY"]["modules"])
        self.assertIn("tests.test_ci_runner_guardrails", ci_modules)
        self.assertIn("tests.test_phase_certification_guardrails", ci_modules)

    def test_doctor_review_is_advisory_but_hard_failure_blocks(self) -> None:
        self.assertIn("$doctorExit -ge 2", self.source)
        self.assertIn('$integrityStatus -ne "PASS"', self.source)
        self.assertIn("$criticalCount -gt 0", self.source)
        self.assertIn("$doctorExit -eq 1", self.source)
        self.assertIn("Doctor returned REVIEW", self.source)
        self.assertRegex(
            self.source,
            r"(?s)Doctor returned REVIEW.*?\n\s+}\s*\n\s+.*REVIEW has been explicitly accepted.*?\n\s+exit 0",
        )

    def test_dependency_review_failure_is_deferred_but_never_swallowed(self) -> None:
        self.assertEqual(self.source.count("continue-on-error: true"), 1)
        self.assertIn("id: dependency_review", self.source)
        self.assertIn("name: Enforce dependency review verdict", self.source)
        self.assertIn("if: ${{ always() }}", self.source)
        self.assertIn("steps.dependency_review.outcome", self.source)
        self.assertIn("throw \"Dependency Review must succeed", self.source)

    def test_public_pr_checkout_preserves_history_without_lfs_or_credentials(self) -> None:
        self.assertRegex(
            self.source,
            r"uses: actions/checkout@[0-9a-f]{40}",
        )
        self.assertIn("ref: ${{ env.CANDIDATE_SHA }}", self.source)
        self.assertIn("git rev-parse HEAD", self.source)
        self.assertIn("lfs: false", self.source)
        self.assertIn("fetch-depth: 0", self.source)
        self.assertIn("persist-credentials: false", self.source)

    def test_required_status_context_name_is_stable(self) -> None:
        self.assertIn("name: Public PR / Safe Validation", self.source)


if __name__ == "__main__":
    unittest.main()
