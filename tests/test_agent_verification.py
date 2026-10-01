from __future__ import annotations

import argparse
import copy
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import agent, agent_planner, atlas_doctor
from tools.atlas_doctor_lib import verification
from tools.atlas_doctor_lib.core import load_json
from tests import test_agent_planner as fixtures


class AgentVerificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        for arguments in (["init"], ["config", "user.email", "atlas@example.invalid"],
                          ["config", "user.name", "Atlas Tests"]):
            subprocess.run(["git", *arguments], cwd=self.root, check=True, capture_output=True)
        (self.root / ".gitignore").write_text(".ai/runtime/\n", encoding="utf-8")
        (self.root / "tools").mkdir()
        (self.root / "tools/local.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=self.root, check=True, capture_output=True)
        self.plan = {
            "level": "SOFT", "integrity_mode": "FAST", "minimum_integrity_mode": "FAST",
            "paths": ["tools/local.py"], "scopes": ["quality_ci"],
            "execution_tests": ["tests.test_example"], "recommended_tests": ["tests.test_example"],
            "recommended_tools": [{"path": "tools/atlas_integrity.py", "safe_for_agent": True,
                                   "automation_ready": True, "side_effects": "artifact_output"}],
            "ownership": {"review_required": False}, "source_diagnostics": {"status": "PASS"},
            "architecture_preflight": {"required": False}, "risk": {"risk": "LOW"},
        }
        self.commands = self.enterContext(patch.object(verification, "_run_command", side_effect=self.pass_command))
        self.gate = self.enterContext(patch.object(verification, "run_integrity_gate", return_value={
            "status": "PASS", "mode": "FAST", "command": ["canonical-atlas"],
            "report": {"verdict": "PASS", "blockers": []}}))

    @staticmethod
    def pass_command(root, key, command, **options):
        return {"key": key, "status": "PASS", "command": command, "duration_ms": 1,
                "failure_ids": [], "returncode": 0}

    def execute(self):
        return verification.execute_plan(self.root, self.plan, preflight={"status": "PASS"})

    def test_verify_runs_context_targeted_tests_and_one_canonical_gate(self):
        result = self.execute()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["tools_executed"], ["tools/ai_context.py", "tools/atlas_integrity.py"])
        self.assertEqual(result["tests_executed"], ["tests.test_example"])
        self.gate.assert_called_once_with(self.root, "fast", base_ref="HEAD", timeout=900)
        self.assertEqual(load_json(self.root, "latest_verification")["status"], "PASS")

    def test_real_test_failure_stops_before_expensive_engine_without_fake_cause(self):
        def failure(root, key, command, **options):
            result = self.pass_command(root, key, command)
            if key == "tests":
                result.update(status="FAIL", reason="tests exited with code 1.",
                              failure_ids=["tests.test_example.Example.test_contract"],
                              stderr_tail=["AssertionError: observed"])
            return result
        self.commands.side_effect = failure
        result = self.execute()
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["early_stop"])
        self.assertEqual(result["diagnosis"]["certainty"], "OBSERVED_FAILURE")
        self.assertIn("test_contract", result["diagnosis"]["failure_ids"][0])
        self.assertIn("unittest", result["diagnosis"]["command"])
        self.assertEqual(result["diagnostics"][0]["key"], "tests")
        self.assertEqual(result["diagnostics"][0]["reproduction_command"], result["diagnosis"]["command"])
        self.gate.assert_not_called()

    def test_unsafe_or_mutating_engine_is_never_run(self):
        authority = copy.deepcopy(self.plan["recommended_tools"][0])
        for changes in ({"safe_for_agent": False}, {"automation_ready": False},
                        {"side_effects": "repo_mutation_explicit"}):
            with self.subTest(changes=changes):
                self.plan["recommended_tools"][0] = {**authority, **changes}
                self.assertEqual(self.execute()["status"], "REVIEW")
                self.commands.assert_not_called()
                self.gate.assert_not_called()

    def test_unknown_owner_remains_review_but_does_not_waive_validation(self):
        self.plan["ownership"] = {"review_required": True, "unowned_paths": ["docs/note.md"]}
        result = self.execute()
        self.assertEqual(result["status"], "REVIEW")
        self.assertIn("docs/note.md", result["primary_cause"])
        self.gate.assert_called_once()

    def test_failed_context_preflight_early_stops(self):
        result = verification.execute_plan(self.root, self.plan,
                                          preflight={"status": "FAIL", "errors": ["stale context"]})
        self.assertEqual(result["status"], "REVIEW")
        self.assertIn("stale context", result["primary_cause"])
        self.commands.assert_not_called()

    def test_canonical_blockers_are_reported_without_inventing_source_symbols(self):
        self.gate.return_value = {"status": "FAIL", "command": ["canonical-atlas"],
                                 "report": {"verdict": "BLOCKED", "blockers": ["KNOWN_CONTRACT"]}}
        result = self.execute()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["primary_cause"], "KNOWN_CONTRACT")
        self.assertNotIn("symbol", result["diagnosis"])

    def test_missing_report_timeout_or_unavailable_gate_remains_review(self):
        for gate in ({"status": "TIMEOUT", "reason": "timeout"},
                     {"status": "UNAVAILABLE", "reason": "missing"},
                     {"status": "FAIL", "report": None}):
            with self.subTest(gate=gate):
                self.gate.return_value = gate
                self.assertEqual(self.execute()["status"], "REVIEW")

    def test_hard_does_not_run_the_full_suite_twice(self):
        self.plan.update(level="HARD", integrity_mode="FULL",
                         execution_tests=[], tests_delegated_to_integrity=True)
        result = self.execute()
        self.assertTrue(result["tests_delegated_to_integrity"])
        self.assertEqual(result["tests_executed"], [])
        self.assertEqual(self.commands.call_count, 1)
        self.gate.assert_called_once_with(self.root, "full", base_ref="HEAD", timeout=7200)

    def test_specialized_engine_reuses_the_catalog_command_and_current_python(self):
        self.plan["recommended_tools"].append({
            "path": "tools/custom_validator.py", "safe_for_agent": True, "automation_ready": True,
            "side_effects": "artifact_output", "command": ["py", "-3.13", "-m", "tools.custom_validator", "fast"],
        })
        result = self.execute()
        self.assertIn("tools/custom_validator.py", result["tools_executed"])
        command = self.commands.call_args_list[-1].args[2]
        self.assertEqual(command[0], verification.sys.executable)
        self.assertIn("tools.custom_validator", command)
        self.assertNotIn("--json", command)

    def test_source_parse_failure_stops_and_retains_actual_file_evidence(self):
        self.plan["source_diagnostics"] = {"status": "FAIL",
            "errors": [{"path": "tools/local.py", "reason": "observed syntax error at line 2"}]}
        result = self.execute()
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["diagnosis"]["evidence"][0]["path"], "tools/local.py")
        self.commands.assert_not_called()

    def test_worktree_change_during_checks_invalidates_success(self):
        def mutation(root, key, command, **options):
            (root / "tools/local.py").write_text("def f():\n    return 2\n", encoding="utf-8")
            return self.pass_command(root, key, command)
        self.commands.side_effect = mutation
        result = self.execute()
        self.assertEqual(result["status"], "REVIEW")
        self.assertIn("changed during", result["primary_cause"])

    def test_invalid_test_metadata_is_not_executed(self):
        self.plan["execution_tests"] = ["--fake-option"]
        self.assertEqual(self.execute()["status"], "REVIEW")
        self.assertEqual(self.commands.call_count, 1)
        self.gate.assert_not_called()

    def test_validation_is_not_reused_only_because_git_head_is_unchanged(self):
        self.execute()
        self.execute()
        self.assertEqual(self.gate.call_count, 2)

    def test_planning_catalog_cache_reuses_head_and_invalidates_dirty_content(self):
        report = {"schema_version": 1, "tools": []}
        with patch.object(agent_planner, "tooling_catalog", return_value=report) as discover:
            first_cache = {}
            second_cache = {}
            self.assertEqual(agent_planner._planning_catalog(self.root, cache_info=first_cache), report)
            self.assertEqual(agent_planner._planning_catalog(self.root, cache_info=second_cache), report)
            self.assertEqual(discover.call_count, 1)
            self.assertEqual(first_cache["status"], "MISS")
            self.assertEqual(second_cache["status"], "HIT")
            (self.root / "tools/local.py").write_text("x = 2\n", encoding="utf-8")
            agent_planner._planning_catalog(self.root)
            (self.root / "tools/local.py").write_text("x = 3\n", encoding="utf-8")
            agent_planner._planning_catalog(self.root)
            self.assertEqual(discover.call_count, 3)

    def test_real_diff_escalates_a_requested_soft_plan_before_execution(self):
        target = self.root / "app/services/shared_provider.py"
        target.parent.mkdir(parents=True)
        target.write_text("identity = 1\n", encoding="utf-8")
        impact = {"scopes": ["quality_ci"], "recommended_tests": [],
                  "unowned_paths": [], "ambiguous_paths": []}
        policy = agent.atlas_integrity.load_policy(agent.ROOT)
        with patch.object(agent, "impact_payload", return_value=impact), \
             patch.object(agent_planner, "_planning_catalog", return_value=fixtures.AgentPlannerTests._catalog()), \
             patch.object(agent.atlas_integrity, "load_policy", return_value=policy), \
             patch("tools.atlas_doctor_lib.architecture.graph_status", return_value={"status": "MISSING", "reason": "missing"}):
            plan = agent.plan_payload(self.root, ["tools/local.py"], level="SOFT", base_ref="HEAD")
        self.assertIn("app/services/shared_provider.py", plan["paths"])
        self.assertEqual(plan["level"], "MEDIUM")
        self.assertEqual(plan["depth"]["escalations"][0]["from"], "SOFT")

    def test_root_of_trust_diff_escalates_soft_to_hard(self):
        target = self.root / "app/core/character_identity.py"
        target.parent.mkdir(parents=True)
        target.write_text("identity = 1\n", encoding="utf-8")
        impact = {"scopes": ["quality_ci"], "recommended_tests": [],
                  "unowned_paths": [], "ambiguous_paths": []}
        policy = agent.atlas_integrity.load_policy(agent.ROOT)
        with patch.object(agent, "impact_payload", return_value=impact), \
             patch.object(agent_planner, "_planning_catalog", return_value=fixtures.AgentPlannerTests._catalog()), \
             patch.object(agent.atlas_integrity, "load_policy", return_value=policy), \
             patch("tools.atlas_doctor_lib.architecture.graph_status", return_value={"status": "MISSING", "reason": "missing"}):
            plan = agent.plan_payload(self.root, ["tools/local.py"], level="SOFT", base_ref="HEAD")
        self.assertEqual(plan["risk"]["risk"], "CRITICAL")
        self.assertEqual(plan["level"], "HARD")
        self.assertEqual(plan["integrity_mode"], "FULL")
        self.assertEqual(plan["depth"]["escalations"][0]["from"], "SOFT")

    def test_verify_cli_json_and_exit_code_route_to_doctor_executor(self):
        payload = {"schema_version": 1, "kind": "verification", "status": "REVIEW", "level": "MEDIUM"}
        with patch.object(agent, "verify_payload", return_value=payload) as verify, redirect_stdout(io.StringIO()) as out:
            self.assertEqual(agent.main(["verify", "tools/agent.py", "--soft", "--json"]), 1)
        self.assertEqual(json.loads(out.getvalue()), payload)
        self.assertEqual(verify.call_args.kwargs["level"], "SOFT")

    def test_doctor_targeted_verify_is_the_same_facade_and_legacy_remains(self):
        args = atlas_doctor.build_parser().parse_args(["verify", "tools/agent.py", "--medium"])
        args.json = True
        with patch.object(agent, "verify_payload", return_value={"status": "PASS"}) as verify:
            self.assertEqual(atlas_doctor.command_verify(self.root, args)["status"], "PASS")
        self.assertEqual(verify.call_args.kwargs["level"], "MEDIUM")
        self.assertEqual(atlas_doctor.build_parser().parse_args(["verify"]).paths, [])

    def test_cli_help_documents_levels_rebuild_and_base_without_hooks(self):
        with redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit):
            agent.main(["verify", "--help"])
        for flag in ("--soft", "--medium", "--hard", "--base-ref", "--rebuild-graph"):
            self.assertIn(flag, out.getvalue())
        self.assertNotIn("--install-hook", out.getvalue())

    def test_baseline_is_resolved_and_same_contract_is_comparable(self):
        first = self.execute()
        head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.root, text=True
        ).strip()
        self.assertEqual(first["baseline"]["resolved_sha"], head)
        self.assertEqual(first["comparison"]["status"], "UNAVAILABLE")
        second = self.execute()
        self.assertTrue(second["comparison"]["comparable"])
        self.assertEqual(second["comparison"]["status"], "STABLE")
        self.assertEqual(load_json(self.root, "previous_verification")["comparison_key"],
                         first["comparison_key"])

    def test_comparison_rejects_different_explicit_baselines(self):
        previous = {
            "schema_version": 1, "kind": "verification", "status": "PASS",
            "comparison_key": {"base_sha": "before"}, "checks": [],
        }
        current = {
            "schema_version": 1, "kind": "verification", "status": "PASS",
            "comparison_key": {"base_sha": "after"}, "checks": [],
        }
        comparison = verification.compare_verifications(previous, current)
        self.assertFalse(comparison["comparable"])
        self.assertIn("base_sha", comparison["differing_fields"])

    def test_comparison_reports_observed_regression_and_recovery(self):
        key = {"base_sha": "same", "level": "SOFT"}
        passing = {
            "schema_version": 1, "kind": "verification", "status": "PASS",
            "comparison_key": key, "checks": [{"key": "tests", "status": "PASS"}],
        }
        failing = {
            "schema_version": 1, "kind": "verification", "status": "FAIL",
            "comparison_key": key, "checks": [{"key": "tests", "status": "FAIL"}],
        }
        regression = verification.compare_verifications(passing, failing)
        recovery = verification.compare_verifications(failing, passing)
        self.assertEqual(regression["status"], "REGRESSION")
        self.assertEqual(regression["new_non_pass"][0]["key"], "tests")
        self.assertEqual(recovery["status"], "IMPROVED")
        self.assertEqual(recovery["recovered"][0]["key"], "tests")

    def test_cost_and_cache_evidence_are_observational_only(self):
        self.plan["planner_cache"] = {"status": "HIT", "duration_ms": 0.5}
        result = self.execute()
        self.assertEqual(result["cost"]["planner_catalog_cache"]["status"], "HIT")
        self.assertFalse(result["cost"]["validation_reused"])
        self.assertFalse(result["cache"]["validation_reused"])
        self.assertGreaterEqual(result["cost"]["checks_duration_ms"], 2.0)
        self.gate.assert_called_once()


class CommandEvidenceTests(unittest.TestCase):
    def test_actual_unittest_failure_has_stable_test_id_and_reproduction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests/__init__.py").write_text("", encoding="utf-8")
            (root / "tests/test_failure.py").write_text(
                "import unittest\nclass Contract(unittest.TestCase):\n    def test_broken(self):\n        self.assertEqual(1, 2)\n",
                encoding="utf-8")
            result = verification._run_command(root, "tests", [verification.sys.executable,
                "-m", "unittest", "-v", "tests.test_failure"])
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["failure_ids"], ["tests.test_failure.Contract.test_broken"])
        self.assertIn("AssertionError", "\n".join(result["stderr_tail"]))


if __name__ == "__main__":
    unittest.main()
