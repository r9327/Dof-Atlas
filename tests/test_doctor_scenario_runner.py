from __future__ import annotations

import tempfile
import unittest
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
        self.assertEqual(set(target.SCENARIOS), {
            "guide_quest_succes", "home_qt_lifecycle",
            "progress_persistence", "startup_preload", "guide_full_fixture_budget",
        })
        output = target.contract_plan(self.root, SHA, list(target.SCENARIOS))
        self.assertEqual(output["status"], "READY_TO_RUN_CONTRACTS")
        self.assertIn("steady_rss_home", output["required_metrics"])
        self.assertIn("tests.test_guide_ultime_manual_success_sync",
                      output["required_test_modules"])
        self.assertFalse(output["tests_executed"])
        self.assertFalse(output["all_end_to_end_certified"])
        self.assertFalse(output["full_suite_waived"])

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
