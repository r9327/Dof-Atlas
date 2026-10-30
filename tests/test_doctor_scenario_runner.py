from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tools import doctor_scenario_runner as target

SHA = "b" * 40


class UserJourneyCertificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for spec in target.SCENARIOS.values():
            for module in spec["modules"]:
                file = self.root / Path(*module.split(".")).with_suffix(".py")
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("import unittest\nclass Scenario(unittest.TestCase):\n"
                                "    def test_real(self): self.assertTrue(True)\n", encoding="utf-8")

    def test_existing_contracts_wired_to_all_four_critical_journeys(self):
        legacy = {
            "guide_quest_succes", "home_qt_lifecycle",
            "progress_persistence", "startup_preload", "guide_full_fixture_budget",
        }
        self.assertTrue(legacy.issubset(set(target.SCENARIOS)))
        output = target.contract_plan(self.root, SHA, sorted(legacy))
        self.assertEqual(output["status"], "READY_TO_RUN_CONTRACTS")
        self.assertIn("steady_rss_home", output["required_metrics"])
        self.assertIn("tests.test_guide_ultime_manual_success_sync",
                      output["required_test_modules"])
        self.assertFalse(output["tests_executed"])
        self.assertFalse(output["all_end_to_end_certified"])
        self.assertFalse(output["full_suite_waived"])

    def test_cold_detail_and_doctor_scenarios_have_real_modules(self):
        added = (
            "quest_cold_detail", "success_cold_detail",
            "guide_cold_detail", "doctor_intelligence",
        )
        root = Path(__file__).resolve().parents[1]
        for name in added:
            with self.subTest(name=name):
                self.assertIn(name, target.SCENARIOS)
                for module in target.SCENARIOS[name]["modules"]:
                    path = root / Path(*module.split(".")).with_suffix(".py")
                    self.assertTrue(path.is_file(), str(path))
                report = target.contract_plan(self.root, SHA, [name])
                self.assertEqual(report["status"], "READY_TO_RUN_CONTRACTS")
                self.assertFalse(report["tests_executed"])
                self.assertFalse(report["phase_certified"])

    def test_extra_scenario_preserves_clean_sha_and_process_isolation(self):
        runs = []
        with mock.patch.object(target, "_git", side_effect=[SHA, ""]):
            report = target.execute_scenarios(
                self.root, SHA, ["success_cold_detail"],
                runner=lambda _root, modules: runs.append(modules) or 0,
            )
        self.assertEqual(report["status"], "CONTRACTS_PASS_METRICS_NOT_RUN")
        self.assertEqual(len(runs),
                         len(target.SCENARIOS["success_cold_detail"]["modules"]))
        self.assertTrue(all(len(module) == 1 for module in runs))
        self.assertFalse(report["all_end_to_end_certified"])
        self.assertEqual(report["metrics_executed"], [])

    @staticmethod
    def _doctor_document(*, sha: str = SHA, scenario: str = "success_cold_detail"):
        return {
            "kind": "atlas_doctor_optimization_report",
            "git_head": sha,
            "status": "DIAGNOSTIC_READY",
            "diagnostic_correlation": {
                "candidate_sha": sha,
                "status": "REVIEW",
                "certification": False,
                "tests_executed": False,
                "evidence_gaps": ["guides: NOT_PROVIDED"],
                "hypotheses": [{"id": "COLD_ACHIEVEMENT_DETAIL"}],
                "investigation_plan": {
                    "candidate_sha": sha,
                    "tests_executed": False,
                    "unresolved": ["tool_unavailable: graphify"],
                    "scenario_contracts": {
                        "status": "PLANNED_NOT_RUN",
                        "uncovered_hypotheses": [],
                        "selected": [{
                            "scenario": scenario,
                            "covered_hypotheses": ["COLD_ACHIEVEMENT_DETAIL"],
                            "runner": "tools.doctor_scenario_runner",
                            "test_modules": list(target.SCENARIOS[scenario]["modules"]),
                            "execution_status": "NOT_RUN",
                            "required_sha_check": True,
                        }],
                    },
                },
            },
        }

    def test_diagnostic_report_can_plan_contracts_without_running_tests(self):
        doc = self._doctor_document()
        report = target.execute_doctor_report(self.root, SHA, doc)
        self.assertEqual(report["status"], "READY_TO_RUN_CONTRACTS")
        self.assertFalse(report["tests_executed"])
        self.assertFalse(report["phase_certified"])
        self.assertFalse(report["all_end_to_end_certified"])
        self.assertEqual(report["selected_scenarios"], ["success_cold_detail"])
        self.assertIn("guides: NOT_PROVIDED", report["diagnostic_evidence_gaps"])
        self.assertEqual(report["doctor_report_selection"]["completeness"], "PARTIAL_REVIEW")

    def test_diagnostic_explicit_run_reuses_same_sha_isolated_runner(self):
        runs = []
        with mock.patch.object(target, "_git", side_effect=[SHA, ""]):
            report = target.execute_doctor_report(
                self.root, SHA, self._doctor_document(), run=True,
                runner=lambda _root, modules: runs.append(modules) or 0,
            )
        self.assertEqual(report["status"], "CONTRACTS_PASS_METRICS_NOT_RUN")
        self.assertTrue(report["tests_executed"])
        self.assertTrue(all(len(batch) == 1 for batch in runs))
        self.assertEqual(len(runs), len(target.SCENARIOS["success_cold_detail"]["modules"]))
        self.assertFalse(report["phase_certified"])
        self.assertFalse(report["all_end_to_end_certified"])
        self.assertIn("tool_unavailable: graphify", report["diagnostic_evidence_gaps"])

    def test_diagnostic_report_guards_stale_malformed_and_forged_contracts(self):
        stale = self._doctor_document(sha="a" * 40)
        forged = self._doctor_document()
        forged["diagnostic_correlation"]["investigation_plan"]["scenario_contracts"][
            "selected"][0]["test_modules"] = ["tests.test_nonexistent"]
        incomplete = self._doctor_document()
        incomplete["diagnostic_correlation"]["hypotheses"].append(
            {"id": "UNMAPPED"}
        )
        invalid = self._doctor_document()
        invalid["diagnostic_correlation"]["investigation_plan"]["scenario_contracts"][
            "selected"][0]["scenario"] = ["not-a-hashable-string"]
        for doc in (stale, forged, incomplete, invalid):
            with self.subTest(rejected=doc):
                runs = []
                report = target.execute_doctor_report(
                    self.root, SHA, doc, run=True,
                    runner=lambda _root, module: runs.append(module) or 0,
                )
                self.assertEqual(report["status"], "BLOCKED")
                self.assertEqual(runs, [])
                self.assertFalse(report["tests_executed"])
                self.assertFalse(report["certification_granted"])

    def test_diagnostic_report_cli_never_runs_without_explicit_run_flag(self):
        output = io.StringIO()
        artifacts = self.root / "artifacts"
        artifacts.mkdir()
        path = artifacts / "doctor.json"
        path.write_text(json.dumps(self._doctor_document()), encoding="utf-8")
        with mock.patch.object(target, "ROOT", self.root), redirect_stdout(output):
            exit_code = target.main([
                "--doctor-report", "artifacts/doctor.json", "--expected-sha", SHA,
            ])
        self.assertEqual(exit_code, 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["status"], "READY_TO_RUN_CONTRACTS")
        self.assertFalse(plan["tests_executed"])

    def test_real_runner_eligible_only_on_exact_sha_and_clean_worktree(self):
        selected = []
        batches = []
        def runner(root, modules):
            batches.append(list(modules))
            selected.extend(modules)
            return 0
        with mock.patch.object(target, "_git", side_effect=[SHA, ""]):
            output = target.execute_scenarios(
                self.root, SHA, ["guide_quest_succes"], runner=runner
            )
        self.assertEqual(output["status"], "CONTRACTS_PASS_METRICS_NOT_RUN")
        self.assertGreater(len(selected), 2)
        self.assertEqual(output["executed_test_modules"], selected)
        self.assertTrue(output["isolated_process_per_module"])
        self.assertTrue(all(len(batch) == 1 for batch in batches))
        self.assertEqual(len(output["module_results"]), len(selected))
        self.assertTrue(all(row["exit_code"] == 0 for row in output["module_results"]))
        self.assertFalse(output["all_end_to_end_certified"])
        self.assertEqual(output["metrics_executed"], [])

    def test_failed_runner_does_not_pass(self):
        with mock.patch.object(target, "_git", side_effect=[SHA, ""]):
            output = target.execute_scenarios(
                self.root, SHA, ["progress_persistence"], runner=lambda *_: 1
            )
        self.assertEqual(output["status"], "BLOCKED")
        self.assertIn("SCENARIO_TESTS_FAILED", output["errors"])
        self.assertEqual(output["failed_modules"], output["required_test_modules"])
        self.assertTrue(all(row["exit_code"] == 1 for row in output["module_results"]))

    def test_wrong_git_candidate_or_dirty_tree_never_runs(self):
        called = []
        with mock.patch.object(target, "_git", side_effect=["a" * 40, ""]):
            report = target.execute_scenarios(self.root, SHA, ["guide_quest_succes"],
                                              runner=lambda *_: called.append(True))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["tests_executed"])
        self.assertEqual(called, [])
        with mock.patch.object(target, "_git", side_effect=[SHA, " M tools/guide.py"]):
            report = target.execute_scenarios(self.root, SHA, ["guide_quest_succes"],
                                              runner=lambda *_: called.append(True))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(called, [])

    def test_unknown_or_missing_contract_blocks(self):
        self.assertEqual(target.contract_plan(self.root, SHA, ["unknown"])["status"], "BLOCKED")
        self.assertEqual(target.contract_plan(self.root, SHA, [])["status"], "BLOCKED")
        (self.root / "tests/test_guide_ultime_manual_success_sync.py").unlink()
        out = target.contract_plan(self.root, SHA, ["guide_quest_succes"])
        self.assertIn("MISSING_SCENARIO_CONTRACTS", out["errors"])

    def test_real_navigation_requires_catalog_materialization(self):
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/doctor-certification.yml").read_text(
                        encoding="utf-8")
        self.assertIn("quest_categories.json", workflow)
        self.assertIn("tools/doduda/doduda.exe", workflow)
        self.assertIn("data/encyclopedia/images/quests/2464", workflow)
        self.assertIn("data/encyclopedia/images/quests/691", workflow)
        self.assertIn("Independent Doctor journey catalog", workflow)
        self.assertLess(workflow.index("Materialize canonical quest data"),
                        workflow.index("Exercise independent user journey contracts"))


if __name__ == "__main__":
    unittest.main()
