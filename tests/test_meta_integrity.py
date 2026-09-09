from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools.atlas_meta_integrity import (
    DEFAULT_INVENTORY,
    check_ci_contracts,
    check_full_discovery_source,
    check_zero_baselines,
    classify_root_of_trust_changes,
    detect_sensitive_changes,
    inspect_critical_test,
    validate_inventory,
    verify_repository,
)


ROOT = Path(__file__).resolve().parents[1]


class AtlasMetaIntegrityTests(unittest.TestCase):
    def _inventory(self) -> dict:
        return json.loads((ROOT / DEFAULT_INVENTORY).read_text(encoding="utf-8"))

    def _write_test(self, root: Path, body: str) -> Path:
        path = root / "tests" / "test_guard.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "import unittest\n\n"
            "class GuardTests(unittest.TestCase):\n"
            f"{body}",
            encoding="utf-8",
        )
        return path

    def _write_zero_baselines(
        self,
        root: Path,
        *,
        runtime: str = "()",
        identity: str = "()",
    ) -> None:
        tests = root / "tests"
        tests.mkdir(parents=True, exist_ok=True)
        (tests / "test_architecture_debt_baseline.py").write_text(
            "LEGACY_IMPORT_BASELINE = ()\n"
            f"RUNTIME_PATCH_BASELINE = {runtime}\n"
            "RUNTIME_VERSION_BASELINE = ()\n",
            encoding="utf-8",
        )
        (tests / "test_character_identity_guardrails.py").write_text(
            f"KNOWN_SLOT_BUSINESS_DEBT = {identity}\n",
            encoding="utf-8",
        )

    def _write_ci_fixture(self, root: Path) -> None:
        workflows = root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        tools = root / "tools"
        tools.mkdir(parents=True)
        for relative in (
            ".github/workflows/app-ci.yml",
            ".github/workflows/public-pr-ci.yml",
            ".github/workflows/guide-ultime-v5-ui.yml",
            "tools/atlas_integrity.py",
            "tools/atlas_integrity_policy.json",
            "tools/run_guide_ultime_ci.ps1",
        ):
            destination = root / relative
            shutil.copyfile(ROOT / relative, destination)

    def test_current_inventory_is_valid(self) -> None:
        report = verify_repository(ROOT, changed_paths=[])
        self.assertEqual("PASS", report["verdict"], report["protections_missing"])
        self.assertEqual(24, report["critical_test_count"])

    def test_missing_hard_logical_id_is_blocked(self) -> None:
        payload = self._inventory()
        payload["protections"] = [
            item for item in payload["protections"] if item["id"] != "ARCH_RUNTIME_PATCH_ZERO"
        ]
        issues, _ = validate_inventory(payload, ROOT)
        self.assertTrue(any("ARCH_RUNTIME_PATCH_ZERO" in issue for issue in issues), issues)

    def test_missing_critical_owner_file_is_blocked(self) -> None:
        payload = copy.deepcopy(self._inventory())
        payload["protections"][0]["owner"]["path"] = "tests/deleted_guardrail.py"
        issues, _ = validate_inventory(payload, ROOT)
        self.assertTrue(any("owner missing" in issue for issue in issues), issues)

    def test_missing_critical_test_method_is_blocked(self) -> None:
        payload = copy.deepcopy(self._inventory())
        payload["protections"][0]["owner"]["symbol"] = (
            "ArchitectureDebtBaselineTests.test_deleted_guardrail"
        )
        issues, _ = validate_inventory(payload, ROOT)
        self.assertTrue(any("method missing" in issue for issue in issues), issues)

    def test_unittest_skip_on_critical_test_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_test(
                Path(tmp),
                '    @unittest.skip("disabled")\n'
                "    def test_contract(self):\n"
                "        self.assertTrue(1)\n",
            )
            issues = inspect_critical_test(path, "GuardTests.test_contract")
        self.assertTrue(any("skip/xfail" in issue for issue in issues), issues)

    def test_pytest_xfail_on_critical_test_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_test(
                Path(tmp),
                "    @pytest.mark.xfail\n"
                "    def test_contract(self):\n"
                "        self.assertTrue(1)\n",
            )
            issues = inspect_critical_test(path, "GuardTests.test_contract")
        self.assertTrue(any("pytest.mark.xfail" in issue for issue in issues), issues)

    def test_runtime_baseline_greater_than_zero_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_zero_baselines(root, runtime="('allowed:new_patch',)")
            issues, counts = check_zero_baselines(root)
        self.assertEqual(1, counts["ARCH_RUNTIME_PATCH_ZERO"])
        self.assertTrue(any("ARCH_RUNTIME_PATCH_ZERO" in issue for issue in issues), issues)

    def test_identity_baseline_greater_than_zero_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_zero_baselines(root, identity="('app/new_slot.py:slot:1',)")
            issues, counts = check_zero_baselines(root)
        self.assertEqual(1, counts["IDENTITY_LEGACY_DEBT_ZERO"])
        self.assertTrue(any("IDENTITY_LEGACY_DEBT_ZERO" in issue for issue in issues), issues)

    def test_reduced_full_discovery_scope_is_blocked(self) -> None:
        source = (
            'py -3.13 -X faulthandler -m unittest discover -v '
            '-s tests/fast -p "test_guardrails.py"\n'
        )
        issues = check_full_discovery_source(source)
        self.assertIn("full discovery start directory is not tests", issues)
        self.assertIn("full discovery pattern is not test_*.py", issues)

    def test_missing_workflow_or_runner_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            issues = check_ci_contracts(Path(tmp))
        self.assertTrue(any("app-ci.yml" in issue for issue in issues), issues)
        self.assertTrue(any("guide-ultime-v5-ui.yml" in issue for issue in issues), issues)
        self.assertTrue(any("run_guide_ultime_ci.ps1" in issue for issue in issues), issues)

    def test_conditional_full_discovery_step_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_ci_fixture(root)
            path = root / ".github/workflows/app-ci.yml"
            source = path.read_text(encoding="utf-8")
            source = source.replace(
                "      - name: Run full application test suite\n        id: full_tests",
                "      - name: Run full application test suite\n        if: false\n        id: full_tests",
            )
            path.write_text(source, encoding="utf-8")
            issues = check_ci_contracts(root)
        self.assertTrue(any("became conditional" in issue for issue in issues), issues)

    def test_integrity_policy_cannot_drop_mandatory_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_ci_fixture(root)
            policy_path = root / "tools/atlas_integrity_policy.json"
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
            policy["modes"]["FAST"].remove("IDENTITY")
            policy["modes"]["FULL"].remove("DATA_INTEGRITY")
            policy["groups"]["DATA_INTEGRITY"]["blocker_ids"] = {}
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            issues = check_ci_contracts(root)
        self.assertTrue(any("FAST policy" in issue for issue in issues), issues)
        self.assertTrue(any("FULL policy" in issue for issue in issues), issues)
        self.assertTrue(any("blocker IDs" in issue for issue in issues), issues)

    def test_missing_independent_critical_job_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_ci_fixture(root)
            workflow = root / ".github/workflows/app-ci.yml"
            source = workflow.read_text(encoding="utf-8")
            source = source.replace("- name: Run Qt lifecycle and non-accumulation contracts", "- name: Removed lifecycle gate")
            workflow.write_text(source, encoding="utf-8")
            issues = check_ci_contracts(root)
        self.assertTrue(any("Qt Lifecycle / Async" in issue for issue in issues), issues)

    def test_missing_critical_path_trigger_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_ci_fixture(root)
            workflow = root / ".github/workflows/app-ci.yml"
            source = workflow.read_text(encoding="utf-8").replace('      - "launch.py"\n', "")
            workflow.write_text(source, encoding="utf-8")
            issues = check_ci_contracts(root)
        self.assertTrue(any('critical path missing "launch.py"' in issue for issue in issues), issues)

    def test_independent_job_cannot_swallow_red_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_ci_fixture(root)
            workflow = root / ".github/workflows/app-ci.yml"
            source = workflow.read_text(encoding="utf-8")
            marker = "- name: Run architecture guardrails"
            start = source.index(marker)
            end = source.index("\n  identity-persistence:", start)
            weakened = source[start:end].replace(
                "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }", "Write-Host 'ignored'"
            )
            workflow.write_text(source[:start] + weakened + source[end:], encoding="utf-8")
            issues = check_ci_contracts(root)
        self.assertTrue(any("does not propagate failure: Architecture" in issue for issue in issues), issues)

    def test_empty_critical_test_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_test(
                Path(tmp),
                "    def test_contract(self):\n"
                "        pass\n",
            )
            issues = inspect_critical_test(path, "GuardTests.test_contract")
        self.assertTrue(any("is empty" in issue for issue in issues), issues)

    def test_constant_only_assertion_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write_test(
                Path(tmp),
                "    def test_contract(self):\n"
                "        self.assertTrue(True)\n",
            )
            issues = inspect_critical_test(path, "GuardTests.test_contract")
        self.assertTrue(any("constant assertions" in issue for issue in issues), issues)

    def test_sensitive_change_is_detected_without_becoming_an_auto_failure(self) -> None:
        paths = [
            "README.md",
            "tools/atlas_meta_integrity.py",
            ".github/workflows/app-ci.yml",
        ]
        self.assertEqual(
            [".github/workflows/app-ci.yml", "tools/atlas_meta_integrity.py"],
            detect_sensitive_changes(paths),
        )

    def test_inventory_and_critical_test_removed_together_are_blocked(self) -> None:
        payload = self._inventory()
        payload["protections"] = [
            item for item in payload["protections"] if item["id"] != "QT_CROSS_SUITE_TEARDOWN"
        ]
        issues, _ = validate_inventory(payload, ROOT)
        self.assertTrue(any("QT_CROSS_SUITE_TEARDOWN" in issue for issue in issues), issues)

    def test_workflow_and_workflow_test_weakened_together_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_ci_fixture(root)
            workflow = root / ".github/workflows/app-ci.yml"
            source = workflow.read_text(encoding="utf-8")
            source = source.replace('-s tests -p "test_*.py"', '-s tests/fast -p "test_ci*.py"')
            workflow.write_text(source, encoding="utf-8")
            ci_issues = check_ci_contracts(root)

        payload = self._inventory()
        payload["protections"] = [
            item for item in payload["protections"] if item["id"] != "CI_RUNNER_CONTRACT"
        ]
        inventory_issues, _ = validate_inventory(payload, ROOT)
        self.assertTrue(ci_issues)
        self.assertTrue(any("CI_RUNNER_CONTRACT" in issue for issue in inventory_issues))

    def test_zero_baseline_and_its_test_weakened_together_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_zero_baselines(root, runtime="('allowed:new_patch',)")
            zero_issues, _ = check_zero_baselines(root)
            test_path = self._write_test(
                root,
                "    def test_contract(self):\n"
                "        self.assertTrue(True)\n",
            )
            test_issues = inspect_critical_test(test_path, "GuardTests.test_contract")
        self.assertTrue(any("ARCH_RUNTIME_PATCH_ZERO" in issue for issue in zero_issues))
        self.assertTrue(any("constant assertions" in issue for issue in test_issues))

    def test_verifier_and_inventory_changed_together_are_critical(self) -> None:
        result = classify_root_of_trust_changes(
            ["tools/atlas_meta_integrity.py", "tests/critical_regression_inventory.json"]
        )
        self.assertEqual("CRITICAL", result["risk"])
        self.assertEqual(2, len(result["modified"]))

    def test_single_root_of_trust_change_is_high(self) -> None:
        result = classify_root_of_trust_changes([".github/workflows/app-ci.yml"])
        self.assertEqual("HIGH", result["risk"])
        self.assertEqual([".github/workflows/app-ci.yml"], result["modified"])


if __name__ == "__main__":
    unittest.main()
