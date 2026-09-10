from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.check_generated_files import find_sensitive_content


ROOT = Path(__file__).resolve().parents[1]


class GeneratedFileGuardrailsTests(unittest.TestCase):
    def _scan_text(self, text: str) -> list[dict[str, str]]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fixture = root / "fixture.txt"
            fixture.write_text(text, encoding="utf-8")
            return find_sensitive_content(root, ["fixture.txt"])

    def test_probable_tokens_and_secret_jwts_are_blocked(self) -> None:
        jwt = ".".join(("eyJ" + "A" * 24, "eyJ" + "B" * 24, "C" * 32))
        cases = {
            "github classic": "TOKEN=" + "ghp_" + "A" * 36,
            "github oauth": "TOKEN=" + "gho_" + "A" * 36,
            "github user": "TOKEN=" + "ghu_" + "A" * 36,
            "github server": "TOKEN=" + "ghs_" + "A" * 36,
            "github refresh": "TOKEN=" + "ghr_" + "A" * 36,
            "github fine-grained": "TOKEN=" + "github_pat_" + "A" * 82,
            "openai": "OPENAI_API_KEY=" + "sk-" + "A" * 48,
            "aws": "AWS_ACCESS_KEY_ID=" + "AKIA" + "A" * 16,
            "google": "GOOGLE_API_KEY=" + "AIza" + "A" * 35,
            "npm": "NPM_TOKEN=" + "npm_" + "A" * 40,
            "slack": "SLACK_TOKEN=" + "xoxb-" + "A" * 32,
            "stripe": "STRIPE_SECRET=" + "sk_live_" + "A" * 32,
            "supabase secret": "SUPABASE_KEY=" + "sb_secret_" + "A" * 32,
            "supabase service role": "SUPABASE_SERVICE_ROLE_KEY=" + jwt,
            "secret jwt": "auth_token=" + jwt,
            "client secret jwt": "client_secret=" + jwt,
            "private token jwt": "private_token=" + jwt,
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                findings = self._scan_text(text)
                self.assertTrue(findings, label)
                self.assertIn("probable", findings[0]["reason"])

    def test_documentation_placeholders_are_not_blocked(self) -> None:
        placeholders = (
            "TOKEN=ghp_EXAMPLE",
            "OPENAI_API_KEY=sk-<your-key>",
            "SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>",
            "secret=placeholder",
        )
        for text in placeholders:
            with self.subTest(text=text):
                self.assertEqual([], self._scan_text(text))

    def test_staged_scan_reads_the_git_index_not_the_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            fixture = root / "fixture.txt"
            fixture.write_text("TOKEN=" + "ghp_" + "A" * 36, encoding="utf-8")
            subprocess.run(["git", "add", "fixture.txt"], cwd=root, check=True, capture_output=True)

            # Remove the token only from the working tree. The staged blob must still be rejected.
            fixture.write_text("TOKEN=placeholder", encoding="utf-8")
            self.assertEqual([], find_sensitive_content(root, ["fixture.txt"]))
            findings = find_sensitive_content(root, ["fixture.txt"], staged=True)
            self.assertTrue(findings)
            self.assertIn("GitHub personal access token", findings[0]["reason"])

    def test_repository_does_not_require_signed_commits(self) -> None:
        ruleset = (ROOT / ".github/rulesets/integration-branch.json").read_text(encoding="utf-8")
        self.assertNotIn('"type": "required_signatures"', ruleset)

    def test_signature_reporting_is_explicitly_informational(self) -> None:
        workflow = (ROOT / ".github/workflows/signature-report.yml").read_text(encoding="utf-8")
        self.assertIn("Signature / Informational", workflow)
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("informational only", workflow)


if __name__ == "__main__":
    unittest.main()