from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from tools.atlas_doctor import build_parser, command_agent
from tools.atlas_doctor_lib.oss_router import select_eligible_diagnostics
from tools.atlas_doctor_lib.oss_intelligence import intelligent_plan


class AutomaticDoctorOssTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in (
            "tools/example.py", "tools/second.py", "tests/test_example.py",
            ".github/workflows/check.yml", "docs/intro.md",
        ):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("pass\n", encoding="utf-8")

    def _command(self, *argv, status="REVIEW", exit_code=1):
        args = build_parser().parse_args(["agent", *argv])
        original = {"status": status, "exit_code": exit_code,
                    "certification": {"full_certified": False}}
        with (
            patch("tools.atlas_doctor_lib.agent_protocol.run_agent_action",
                  return_value=original),
            patch("tools.atlas_doctor_lib.oss_router._open_source_inventory",
                  return_value={"status": "INVENTORIED_NOT_CERTIFIED",
                                "count": 29, "supplemental_count": 5,
                                "candidates": [{"id": "ATOSS-20", "name": "Ruff",
                                                "study_decision": "ASSESS"},
                                               {"id": "ATOSS-21", "name": "zizmor",
                                                "study_decision": "ASSESS"}],
                                "supplemental": []}),
            patch("tools.atlas_doctor_lib.oss_router.route_oss",
                  return_value={"status": "ADVISORY_ONLY",
                                "execution_results": [{"tool": "ruff",
                                                        "status": "FINDINGS"}],
                                "phase_certified": False}) as route,
        ):
            payload = command_agent(self.root, args)
        return payload, route, original

    def test_check_run_tests_automatically_executes_relevant_oss(self):
        p, route, original = self._command(
            "check", "tools/example.py", "--run-tests")
        route.assert_called_once()
        self.assertEqual(route.call_args.args[1], ["tools/example.py"])
        self.assertTrue(route.call_args.kwargs["run"])
        self.assertLessEqual(route.call_args.kwargs["timeout_seconds"], 20)
        self.assertEqual(p["status"], original["status"])
        self.assertEqual(p["exit_code"], original["exit_code"])
        self.assertFalse(p["certification"]["full_certified"])
        self.assertEqual(p["oss_dispatch"]["selected_count"], 1)
        self.assertEqual(p["oss_advisory"]["status"], "ADVISORY_ONLY")

    def test_plan_reports_relevant_installed_metadata_without_execution(self):
        candidates = {"ruff": {"name": "ruff", "available": True, "version": "0.17.3"},
                      "semgrep": {"name": "semgrep", "available": False, "version": None}}
        def preflight(*, packages=(), binaries=()):
            self.assertFalse(binaries)
            return {"results": [candidates[name] for name in packages]}
        with patch("tools.tool_catalog.local_candidate_preflight",
                   side_effect=preflight) as observed:
            report, route, _ = self._command("plan", "tools/example.py")
        observed.assert_called_once()
        route.assert_not_called()
        self.assertEqual(report["oss_local_preflight"]["status"],
                         "OBSERVED_NOT_QUALIFIED")
        self.assertFalse(report["oss_local_preflight"]["network_used"])
        self.assertEqual({x["id"] for x in report["oss_local_preflight"]["tools"]},
                         {"ATOSS-20", "ATOSS-19"})
        self.assertTrue(all(not row["license_verified"] and
                            not row["execution_verified"]
                            for row in report["oss_local_preflight"]["tools"]))
        statuses = {row["tool_id"]: row for row in
                    report["ai_tool_workflow"]["oss_recommendations"]}
        self.assertTrue(statuses["ATOSS-20"]["locally_available"])
        self.assertFalse(statuses["ATOSS-19"]["locally_available"])
        self.assertEqual(statuses["ATOSS-20"]["installed_version_claim"], "0.17.3")
        self.assertFalse(statuses["ATOSS-20"]["automatic_execution"])

    def test_check_without_test_optin_does_not_run_third_party_tool(self):
        p, route, _ = self._command("check", "tools/example.py")
        route.assert_not_called()
        self.assertEqual(p["oss_advisory"]["status"], "NOT_RUN")
        self.assertIn("--run-tests", p["oss_advisory"]["reason"])

    def test_no_oss_disables_even_explicit_run(self):
        p, route, _ = self._command(
            "check", "tools/example.py", "--run-tests", "--run-oss", "--no-oss")
        route.assert_not_called()
        self.assertEqual(p["oss_advisory"]["status"], "NOT_RUN")
        self.assertIn("--no-oss", p["oss_advisory"]["reason"])

    def test_blocked_check_or_noncheck_never_runs_oss(self):
        p, route, _ = self._command(
            "check", "tools/example.py", "--run-tests", status="BLOCKED",
            exit_code=2)
        route.assert_not_called()
        self.assertEqual(p["oss_advisory"]["status"], "NOT_RUN")
        p, route, _ = self._command(
            "plan", "tools/example.py", "--run-oss")
        route.assert_not_called()
        self.assertEqual(p["oss_advisory"]["status"], "NOT_RUN")

    def test_only_explicit_existing_source_paths_are_scanned(self):
        requested = [
            "tools/example.py", "tools/example.py", "docs/intro.md",
            "tools/../secret.py", "tools/missing.py",
            ".github/workflows/check.yml",
        ]
        result = select_eligible_diagnostics(self.root, requested)
        self.assertEqual(result["files"], [
            "tools/example.py", ".github/workflows/check.yml"])
        self.assertEqual(result["ignored_count"], 3)
        self.assertTrue(result["coverage_complete"])

    def test_out_of_scope_check_does_not_spawn_scanners(self):
        p, route, _ = self._command("check", "docs/intro.md", "--run-tests")
        route.assert_not_called()
        self.assertEqual(p["oss_advisory"]["status"], "NOT_APPLICABLE")
        self.assertEqual(p["oss_dispatch"]["selected_count"], 0)

    def test_truncated_auto_scan_explicitly_marks_incomplete_coverage(self):
        for i in range(17):
            (self.root / "tools" / f"module_{i}.py").write_text(
                "x=1\n", encoding="utf-8")
        paths = [f"tools/module_{i}.py" for i in range(17)]
        found = select_eligible_diagnostics(self.root, paths)
        self.assertEqual(found["selected_count"], 16)
        self.assertEqual(found["truncated_count"], 1)
        self.assertFalse(found["coverage_complete"])

    def test_missing_supplemental_is_not_a_false_qualified_integration(self):
        plan = intelligent_plan(
            ["requirements-pyside.txt"],
            {"status": "REVIEW", "count": 29, "candidates": [],
             "supplemental_count": 0, "supplemental": []})
        self.assertEqual(plan["status"], "REVIEW")
        self.assertFalse(plan["certified"])
        self.assertEqual(plan["inventory_coverage"]["candidate_total"], 0)
        self.assertEqual(plan["inventory_coverage"]["execution_evidence_count"], 0)


if __name__ == "__main__":
    unittest.main()
