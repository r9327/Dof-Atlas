from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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

    def test_phase_verdict_never_waives_full_suite_or_unknown_blockers(self) -> None:
        source = self.phase_verdict
        self.assertIn('name == "DATA_INTEGRITY"', source)
        self.assertIn('groups.get("FULL_SUITE")', source)
        self.assertIn("FULL_SUITE is not absolute PASS", source)
        self.assertIn("unexpected integrity blockers", source)
        self.assertIn("Guide baseline owners changed", source)
        self.assertIn("prerequisite baseline fingerprint drift", source)
        self.assertIn("final coverage baseline fingerprint drift", source)
        self.assertIn("PASS_BASELINE_NON_REGRESSION", source)

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
