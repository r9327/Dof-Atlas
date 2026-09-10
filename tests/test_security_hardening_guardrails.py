from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class SecurityHardeningGuardrailsTests(unittest.TestCase):
    def _workflow(self, name: str) -> str:
        return (WORKFLOWS / name).read_text(encoding="utf-8")

    def test_every_external_github_action_is_pinned_to_full_commit_sha(self) -> None:
        violations: list[str] = []
        for path in sorted(WORKFLOWS.glob("*.yml")):
            source = path.read_text(encoding="utf-8")
            for line_number, line in enumerate(source.splitlines(), start=1):
                match = re.match(r"^\s*uses:\s*([^\s#]+)", line)
                if not match:
                    continue
                value = match.group(1)
                if value.startswith("./"):
                    continue
                action, separator, ref = value.partition("@")
                if not separator or not action or not re.fullmatch(r"[0-9a-f]{40}", ref):
                    violations.append(f"{path.name}:{line_number}:{value}")
        self.assertEqual([], violations, f"Mutable/unpinned GitHub Actions refs: {violations}")

    def test_checkout_never_persists_github_credentials(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            source = path.read_text(encoding="utf-8")
            checkout_count = source.count("uses: actions/checkout@")
            with self.subTest(path=path.name):
                self.assertEqual(checkout_count, source.count("persist-credentials: false"))

    def test_workflow_tokens_remain_read_only_and_pr_target_is_forbidden(self) -> None:
        for path in sorted(WORKFLOWS.glob("*.yml")):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("pull_request_target:", source)
                self.assertNotRegex(source, r"(?m)^\s+[A-Za-z_-]+:\s*write\s*$")
                if "permissions:" in source:
                    self.assertIn("contents: read", source)

    def test_public_pr_blocks_vulnerable_dependency_changes_fail_closed(self) -> None:
        source = self._workflow("public-pr-ci.yml")
        self.assertIn("actions/dependency-review-action@", source)
        self.assertIn("fail-on-severity: moderate", source)
        self.assertIn("fail-on-scopes: development, runtime, unknown", source)
        self.assertIn("id: dependency_review", source)
        self.assertEqual(source.count("continue-on-error: true"), 1)
        self.assertIn("steps.dependency_review.outcome", source)
        self.assertIn("throw \"Dependency Review must succeed", source)
        self.assertIn("tests.test_security_hardening_guardrails", source)

    def test_self_hosted_workflows_only_execute_owner_main(self) -> None:
        required_guard = "github.actor == github.repository_owner && github.ref == 'refs/heads/main'"
        for name in ("deep-validation.yml", "guide-ultime-v5-ui.yml"):
            source = self._workflow(name)
            with self.subTest(name=name):
                self.assertIn("workflow_dispatch:", source)
                self.assertIn("runs-on: [self-hosted, Windows, X64]", source)
                self.assertIn(required_guard, source)
                self.assertNotIn("pull_request:", source)
                self.assertNotIn("push:", source)
                self.assertNotIn("schedule:", source)

    def test_dependabot_covers_actions_and_python_dependencies(self) -> None:
        source = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        self.assertIn('package-ecosystem: "github-actions"', source)
        self.assertIn('package-ecosystem: "pip"', source)
        self.assertGreaterEqual(source.count('interval: "weekly"'), 2)

    def test_python_runtime_lock_pins_every_package_and_artifact_hash(self) -> None:
        source = (ROOT / "requirements-pyside.txt").read_text(encoding="utf-8")
        entries: list[str] = []
        hashes: list[str] = []
        for raw_line in source.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("--hash="):
                hashes.append(line)
            else:
                entries.append(line)

        expected_packages = {
            "pyside6",
            "pyside6_addons",
            "pyside6_essentials",
            "shiboken6",
            "pillow",
            "pywin32",
            "pyautogui",
            "pymsgbox",
            "pytweening",
            "pyscreeze",
            "pygetwindow",
            "mouseinfo",
            "pyrect",
            "pyperclip",
        }
        names = {entry.split("==", 1)[0].strip().casefold() for entry in entries}
        self.assertEqual(expected_packages, names)
        self.assertEqual(len(entries), len(hashes))
        self.assertTrue(all("==" in entry for entry in entries))
        self.assertTrue(all(entry.endswith("\\") for entry in entries))
        self.assertTrue(all(re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", value) for value in hashes))

    def test_ci_installs_authenticated_lock_without_dependency_resolution(self) -> None:
        command = "pip install --require-hashes --no-deps -r requirements-pyside.txt"
        for name in ("app-ci.yml", "public-pr-ci.yml", "deep-validation.yml"):
            source = self._workflow(name)
            with self.subTest(name=name):
                self.assertIn(command, source)

    def test_bootstrap_installs_and_validates_the_authenticated_runtime(self) -> None:
        source = (ROOT / "bootstrap_dofus_atlas.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("--require-hashes --no-deps -r $RequirementsFile", source)
        self.assertIn("import PIL.Image", source)
        self.assertIn("import pyautogui", source)
        self.assertIn("Get-FileHash -Path $installer -Algorithm SHA256", source)
        self.assertIn("$PythonInstallerSha256", source)

    def test_equipment_webview_blocks_local_custom_and_popup_navigation(self) -> None:
        source = (ROOT / "app" / "pages" / "equipment_page.py").read_text(encoding="utf-8")
        self.assertIn('scheme in {"https", "about", "data", "blob"}', source)
        self.assertIn('if scheme == "https" and (', source)
        self.assertIn('NavigationTypeLinkClicked and scheme == "https"', source)
        self.assertIn("def createWindow(self, _window_type):", source)
        self.assertNotIn('scheme in {"http", "https"}', source)

    def test_security_sensitive_surfaces_are_code_owned(self) -> None:
        source = (ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
        for path in (
            ".github/workflows/**",
            ".github/dependabot.yml",
            "requirements-pyside.txt",
            "bootstrap_dofus_atlas.ps1",
            "app/pages/equipment_page.py",
            "app/services/maps/cartography_asset_recovery.py",
            "local_dofus_data/data_store.py",
            "local_dofus_data/migrations.py",
        ):
            with self.subTest(path=path):
                self.assertIn(f"{path} @r9327", source)


if __name__ == "__main__":
    unittest.main()
