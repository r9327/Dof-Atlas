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

    def test_contract_separates_code_validation_and_certification(self) -> None:
        for token in (
            "CODE_DONE",
            "VALIDATED",
            "CERTIFIED",
            "Public PR / Safe Validation",
            "PHASE CERTIFICATION: PASS",
            "NOT RUN",
            "BLOCKED",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.contract)

    def test_agents_requires_certification_before_declaring_phase_finished(self) -> None:
        self.assertIn("PHASE_CERTIFICATION.md", self.agents)
        self.assertIn("CERTIFIED", self.agents)
        self.assertIn("phase terminée", self.agents)

    def test_policy_declares_machine_readable_certification_contract(self) -> None:
        certification = self.policy["certification"]
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
        self.assertIn(
            "tests.test_phase_certification_guardrails",
            self.policy["groups"]["CI_INTEGRITY"]["modules"],
        )

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
        self.assertIn("github.event.pull_request.head.sha", source)
        self.assertIn("github.event.pull_request.base.sha", source)
        self.assertIn("name: Phase Certification / Full Validation", source)
        self.assertIn("runs-on: windows-latest", source)
        self.assertIn("persist-credentials: false", source)
        self.assertIn("fetch-depth: 0", source)
        self.assertIn("tools.atlas_integrity full", source)
        self.assertIn("GITHUB_SHA", source)
        self.assertIn("PHASE CERTIFICATION: NOT CERTIFIED", source)
        self.assertIn("PHASE CERTIFICATION: PASS", source)
        self.assertIn("steps.lfs.outcome", source)
        self.assertIn("steps.catalog.outcome", source)
        self.assertIn("steps.certification.outcome", source)


if __name__ == "__main__":
    unittest.main()
