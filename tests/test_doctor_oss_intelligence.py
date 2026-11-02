from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.atlas_doctor_lib.oss_intelligence import classify_scope, intelligent_plan
from tools.atlas_doctor_lib.oss_router import route_oss


def study():
    return {"status": "INVENTORIED_NOT_CERTIFIED", "candidates": [
        {"id": f"ATOSS-{i:02d}", "name": f"candidate{i}",
         "study_decision": "REJECT" if i in (28, 29) else "ASSESS"}
        for i in range(1, 30)]}


class DoctorOssIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for path, content in (
            ("tools/test_tool.py", "print('safe')\n"),
            (".github/workflows/check.yml", "name: check\n"),
            ("data/test.json", '{"ok": true}'),
            ("requirements-pyside.txt", "pyside6==6.7.0\n"),
        ):
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    def _native(self, *_args, **_kwargs):
        return {"tools": []}

    def test_scope_routes_are_deterministic_and_do_not_install(self):
        paths = [".github/workflows/check.yml", "tools/test_tool.py"]
        result = intelligent_plan(paths, study())
        self.assertEqual(result["status"], "ADVISORY_ONLY")
        self.assertEqual(result["scopes"], ["python", "workflow"])
        ids = [r["id"] for r in result["recommended"]]
        self.assertIn("ATOSS-20", ids)
        self.assertIn("ATOSS-21", ids)
        self.assertEqual(result["recommended"][0]["decision"], "OPT_IN_APPROVED_ADAPTER")
        self.assertTrue(result["no_automatic_installation"])
        self.assertFalse(result["certified"])
        self.assertFalse(any(r["tool_executed"] for r in result["recommended"]))
        self.assertIn("tools.atlas_doctor ci (canonical CI plan)", result["native_routes"])

    def test_specialists_keep_existing_owners_and_protect_rejected_tools(self):
        paths = ["tools/benchmark_phase8_memory.py", "app/distribution/launcher.py",
                 "data/test.json", "app/ui/theme.py"]
        self.assertIn("launcher", classify_scope(paths))
        self.assertIn("perf", classify_scope(paths))
        result = intelligent_plan(paths, study())
        statuses = {r["id"]: r["decision"] for r in result["recommended"]}
        self.assertEqual(statuses.get("ATOSS-06"), "REUSE_EXISTING")
        self.assertNotIn("ATOSS-28", statuses)
        self.assertNotIn("ATOSS-29", statuses)
        self.assertIn("tools.atlas_doctor perf (single Perf Lab)",
                      result["native_routes"])

    def test_invalid_or_partial_study_cannot_claim_certification(self):
        plan = intelligent_plan(["tools/test_tool.py"], {"status": "REVIEW", "candidates": []})
        self.assertEqual(plan["status"], "REVIEW")
        self.assertEqual(plan["recommended"], [])
        self.assertFalse(plan["certified"])
        with self.assertRaises(ValueError):
            intelligent_plan(["tools/test_tool.py"], study(), limit=0)

    def test_only_preselected_installed_workflow_tool_runs_with_offline_flags(self):
        output = SimpleNamespace(returncode=0, stdout=json.dumps([
            {"ident": "artipacked", "message": "possible secret"}]), stderr="secret")
        probe = {"results": [{"kind": "path_executable", "name": "zizmor",
                               "available": True, "version": None}]}
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value={"tools": []}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools",
                    side_effect=self._native),
              patch("tools.atlas_doctor_lib.oss_router._open_source_inventory",
                    return_value=study()),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight",
                    return_value=probe),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run",
                    return_value=output) as run):
            result = route_oss(self.root, [".github/workflows/check.yml"], run=True)
        args = run.call_args.args[0]
        self.assertEqual(args[0], "zizmor")
        for flag in ("--offline", "--no-config", "--no-progress", "--no-exit-codes"):
            self.assertIn(flag, args)
        self.assertEqual(args[-2:], ["--", ".github/workflows/check.yml"])
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["ZIZMOR_OFFLINE"], "1")
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("GH_TOKEN", env)
        self.assertEqual(result["execution"]["status"], "FINDINGS")
        self.assertEqual(result["execution_count"], 1)
        self.assertNotIn("possible secret", json.dumps(result))
        self.assertFalse(result["phase_certified"])

    def test_workflow_tool_absent_no_install_or_launch(self):
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value={}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools",
                    side_effect=self._native),
              patch("tools.atlas_doctor_lib.oss_router._open_source_inventory",
                    return_value=study()),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight",
                    return_value={"results": []}),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run") as run):
            result = route_oss(self.root, [".github/workflows/check.yml"], run=True)
        run.assert_not_called()
        self.assertEqual(result["execution"]["status"], "NOT_AVAILABLE")
        self.assertTrue(result["dependencies_installed"] is False)

    def test_workflow_invalid_output_and_timeout_cannot_pass(self):
        from subprocess import TimeoutExpired
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value={}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools",
                    side_effect=self._native),
              patch("tools.atlas_doctor_lib.oss_router._open_source_inventory",
                    return_value=study()),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight",
                    return_value={"results": [{"kind": "path_executable", "name": "zizmor",
                                               "available": True}]}),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run",
                    side_effect=TimeoutExpired("zizmor", 2))):
            result = route_oss(self.root, [".github/workflows/check.yml"], run=True)
        self.assertEqual(result["execution"]["status"], "TIMEOUT")
        self.assertEqual(result["execution_count"], 0)

    def test_non_executable_scopes_do_not_launch_candidates(self):
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value={}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools",
                    side_effect=self._native),
              patch("tools.atlas_doctor_lib.oss_router._open_source_inventory",
                    return_value=study()),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight",
                    return_value={"results": []}),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run") as run):
            report = route_oss(self.root, ["data/test.json"], run=True)
        run.assert_not_called()
        self.assertEqual(report["execution_count"], 0)
        self.assertFalse(report["phase_certified"])
        self.assertIn("json", report["intelligent_selection"]["scopes"])

    def test_explicit_files_only_and_reject_escape(self):
        with patch("tools.atlas_doctor_lib.oss_router.catalog") as cat:
            with self.assertRaises(ValueError):
                route_oss(self.root, [".github/workflows/../secrets.yml"], run=True)
        cat.assert_not_called()



    def test_mixed_scanners_keep_separate_results_and_failing_cli_exit(self):
        import contextlib
        import io
        from tools.atlas_doctor import main
        from tools import atlas_doctor
        fake = {"status": "ADVISORY_ONLY",
                "execution": {"status": "CLEAN"},
                "execution_results": [
                    {"tool": "ruff", "status": "CLEAN"},
                    {"tool": "zizmor", "status": "NOT_AVAILABLE"}]}
        with (patch.object(atlas_doctor, "command_oss", return_value=fake),
              contextlib.redirect_stdout(io.StringIO())):
            code = main(["oss", "tools/test_tool.py", "--run", "--json"])
        self.assertEqual(code, 1)


    def test_agent_plan_exposes_selection_without_triggering_external_tools(self):
        from tools.atlas_doctor import build_parser, command_agent
        args = build_parser().parse_args(
            ["agent", "plan", "tools/test_tool.py"])
        core = {"status": "REVIEW", "exit_code": 1,
                "certification": {"full_certified": False}}
        with (patch("tools.atlas_doctor_lib.agent_protocol.run_agent_action",
                    return_value=core),
              patch("tools.atlas_doctor_lib.oss_router._open_source_inventory",
                    return_value=study()),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run") as subprocess_run):
            result = command_agent(self.root, args)
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("ATOSS-20",
                      [row["id"] for row in result["oss_selection"]["recommended"]])
        self.assertFalse(result["oss_selection"]["certified"])
        subprocess_run.assert_not_called()

if __name__ == "__main__":
    unittest.main()
