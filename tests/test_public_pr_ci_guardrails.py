from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "public-pr-ci.yml"


class PublicPrCiGuardrailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = WORKFLOW.read_text(encoding="utf-8")

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

    def test_public_pr_executes_repository_guards(self) -> None:
        required = (
            "git diff --check",
            "tools.check_generated_files --root . --tracked",
            "tools.atlas_meta_integrity --root . --base-ref",
            "tests.test_architecture_debt_baseline",
            "tests.test_clean_foundation_guardrails",
            "tests.test_character_identity_contract",
            "tests.test_character_identity_guardrails",
            "tests.test_character_identity_invariants",
            "tests.test_character_write_boundaries",
            "tests.test_progress_concurrent_instances",
            "tests.test_quest_progress_batch_contract",
            "tests.test_project_guardrails",
            "tests.test_generated_files_guard",
            "tests.test_generated_file_guardrails",
            "tests.test_repository_git_hooks",
            "tests.test_meta_integrity",
            "tests.test_atlas_integrity",
            "tests.test_ci_runner_guardrails",
            "tests.test_performance_guardrails",
            "tests.test_public_pr_ci_guardrails",
        )
        for token in required:
            with self.subTest(token=token):
                self.assertIn(token, self.source)
        self.assertNotIn("continue-on-error: true", self.source)

    def test_public_pr_checkout_preserves_history_without_lfs_payloads(self) -> None:
        self.assertIn("uses: actions/checkout@v4", self.source)
        self.assertIn("lfs: false", self.source)
        self.assertIn("fetch-depth: 0", self.source)

    def test_required_status_context_name_is_stable(self) -> None:
        self.assertIn("name: Public PR / Safe Validation", self.source)


if __name__ == "__main__":
    unittest.main()
