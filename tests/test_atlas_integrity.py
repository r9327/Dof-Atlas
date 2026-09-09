from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from tools import atlas_integrity


ROOT = Path(__file__).resolve().parents[1]


class FakeExecutor:
    def __init__(self, *, failing_token: str | None = None, guide_blockers: bool = False) -> None:
        self.failing_token = failing_token
        self.guide_blockers = guide_blockers
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd: Path) -> dict[str, object]:
        self.commands.append(command)
        exit_code = 1 if self.failing_token and self.failing_token in " ".join(command) else 0
        stdout = "Ran 3 tests in 0.001s\nOK\n" if "unittest" in command else ""
        if "tools.atlas_meta_integrity" in command:
            stdout = json.dumps(
                {
                    "zero_debt": {"runtime": 0, "legacy": 0, "versions": 0, "identity": 0},
                    "protections_missing": [],
                    "root_of_trust": {"modified": [], "risk": "NONE"},
                }
            )
        if command[0].lower() == "powershell":
            log_dir = cwd / "artifacts/ci_guide_ultime_logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            checks = []
            if self.guide_blockers:
                exit_code = 1
                checks = [
                    {"name": "07_prerequisite_order_audit", "exit_code": 1},
                    {"name": "09_final_success_coverage_audit", "exit_code": 1},
                ]
            (log_dir / "ci_summary.json").write_text(
                json.dumps({"total_checks": 16, "checks": checks}), encoding="utf-8"
            )
        return {
            "command": command,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": "",
            "duration_seconds": 0.001,
        }


class AtlasIntegrityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = atlas_integrity.load_policy(ROOT)

    def _temporary_root(self) -> tempfile.TemporaryDirectory[str]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        inventory = root / "tests/critical_regression_inventory.json"
        inventory.parent.mkdir(parents=True)
        inventory.write_text(
            (ROOT / "tests/critical_regression_inventory.json").read_text(encoding="utf-8-sig"),
            encoding="utf-8",
        )
        return temporary

    def _run(
        self,
        mode: str,
        changed: list[str],
        *,
        executor: FakeExecutor | None = None,
        policy: dict[str, object] | None = None,
    ) -> tuple[dict[str, object], FakeExecutor]:
        fake = executor or FakeExecutor()
        with self._temporary_root() as directory:
            report = atlas_integrity.execute_gate(
                root=Path(directory),
                mode=mode,
                base_ref="base",
                changed=changed,
                policy=policy or self.policy,
                executor=fake,
            )
        return report, fake

    def test_docs_diff_is_low_risk(self) -> None:
        self.assertEqual(atlas_integrity.classify_risk(["docs/validation.md"])["risk"], "LOW")

    def test_ui_diff_is_medium_risk(self) -> None:
        self.assertEqual(atlas_integrity.classify_risk(["app/pages/home_page.py"])["risk"], "MEDIUM")

    def test_persistence_diff_is_high_risk(self) -> None:
        result = atlas_integrity.classify_risk(
            ["app/modules/encyclopedia/services/quest_progress_service.py"]
        )
        self.assertEqual(result["risk"], "HIGH")

    def test_root_of_trust_diff_is_critical(self) -> None:
        result = atlas_integrity.classify_risk(["tools/atlas_meta_integrity.py"])
        self.assertEqual(result["risk"], "CRITICAL")
        self.assertEqual(result["root_of_trust"]["modified"], ["tools/atlas_meta_integrity.py"])

    def test_high_risk_imposes_sensitive_validations(self) -> None:
        report, _ = self._run(
            "fast", ["app/modules/encyclopedia/services/quest_progress_service.py"]
        )
        self.assertTrue(
            {"PERSISTENCE", "STARTUP", "LAZY_LOADING", "ASYNC_LIFECYCLE"}.issubset(
                report["validations_required"]
            )
        )

    def test_critical_failure_blocks_verdict(self) -> None:
        report, _ = self._run(
            "fast",
            ["docs/validation.md"],
            executor=FakeExecutor(failing_token="compileall"),
        )
        self.assertEqual(report["verdict"], "BLOCKED")
        self.assertIn("SYNTAX_FAILED", report["blockers"])

    def test_known_guide_blockers_have_nonzero_exit(self) -> None:
        report, _ = self._run("full", ["docs/validation.md"], executor=FakeExecutor(guide_blockers=True))
        self.assertEqual(atlas_integrity.exit_code_for_report(report), 1)
        self.assertEqual(
            report["blockers"], ["GUIDE_FINAL_COVERAGE", "GUIDE_PREREQUISITE_DATA"]
        )
        data_policy = self.policy["groups"]["DATA_INTEGRITY"]
        self.assertEqual(data_policy["failure_semantics"], "BLOCKING")
        self.assertNotIn("allowed_blockers", data_policy)

    def test_measured_only_performance_is_never_reported_as_pass(self) -> None:
        report, _ = self._run("full", ["docs/validation.md"])
        self.assertEqual(report["performance"]["resource_budgets"]["classification"], "BUDGETED")
        self.assertEqual(report["performance"]["timing_rss_cpu"]["status"], "MEASURED_ONLY")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            atlas_integrity._print_human(report)
        self.assertIn("Timing performance           MEASURED_ONLY", output.getvalue())

    def test_internal_configuration_error_has_exit_two(self) -> None:
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            code = atlas_integrity.main(["fast", "--root", directory, "--json"])
        self.assertEqual(code, 2)

    def test_report_is_valid_json(self) -> None:
        report, _ = self._run("fast", ["docs/validation.md"])
        decoded = json.loads(json.dumps(report))
        self.assertEqual(decoded["schema_version"], 1)
        self.assertEqual(decoded["verdict"], "PASS")
        self.assertIn("head", decoded)
        self.assertIn("github_protection", decoded)
        self.assertIn("guardrails", decoded)
        self.assertIn("budgets", decoded)
        self.assertIn("coverage", decoded)
        self.assertIn("mutation", decoded)

    def test_fast_does_not_execute_full_discovery(self) -> None:
        _, fake = self._run("fast", ["docs/validation.md"])
        self.assertFalse(any("discover" in command for command in fake.commands))

    def test_full_executes_canonical_full_discovery(self) -> None:
        _, fake = self._run("full", ["docs/validation.md"])
        discoveries = [command for command in fake.commands if "discover" in command]
        self.assertEqual(len(discoveries), 1)
        self.assertIn("tests", discoveries[0])
        self.assertIn("test_*.py", discoveries[0])

    def test_full_calls_canonical_guide_runner(self) -> None:
        _, fake = self._run("full", ["docs/validation.md"])
        self.assertTrue(
            any("tools/run_guide_ultime_ci.ps1" in command for command in fake.commands)
        )

    def test_deep_includes_reproducible_periodic_validations(self) -> None:
        report, fake = self._run("deep", ["docs/validation.md"])
        required = set(report["validations_required"])
        self.assertTrue({"RANDOM_ORDER", "FAULT_INJECTION", "TARGETED_MUTATION", "CRITICAL_COVERAGE", "TIMING_PERFORMANCE"}.issubset(required))
        random_commands = [command for command in fake.commands if "tools.random_order_tests" in command]
        self.assertEqual(len(random_commands), 1)
        self.assertIn("9327", random_commands[0])

    def test_measured_timing_failure_does_not_become_performance_pass_or_hide_itself(self) -> None:
        report, _ = self._run("deep", ["docs/validation.md"], executor=FakeExecutor(failing_token="benchmark_guides_performance"))
        self.assertEqual(report["groups"]["TIMING_PERFORMANCE"]["status"], "MEASURED_ONLY_FAILED")
        self.assertNotIn("TIMING_PERFORMANCE_FAILED", report["blockers"])

    def test_unknown_runner_is_not_silently_ignored(self) -> None:
        policy = deepcopy(self.policy)
        policy["groups"]["SYNTAX"]["runner"] = "missing_runner"
        with self.assertRaises(atlas_integrity.IntegrityConfigError):
            self._run("fast", ["docs/validation.md"], policy=policy)

    def test_required_not_run_group_prevents_acceptable(self) -> None:
        groups = {"IDENTITY": {"status": "NOT_RUN", "blockers": []}}
        verdict, blockers = atlas_integrity.verdict_from_groups(groups, ["IDENTITY"])
        self.assertEqual(verdict, "BLOCKED")
        self.assertEqual(blockers, ["IDENTITY_NOT_RUN"])

    def test_root_of_trust_critical_is_visible_in_human_report(self) -> None:
        report, _ = self._run("fast", ["tools/atlas_meta_integrity.py"])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            atlas_integrity._print_human(report)
        self.assertIn("Risk                         CRITICAL", output.getvalue())
        self.assertIn("Root of trust changed        YES", output.getvalue())


if __name__ == "__main__":
    unittest.main()
