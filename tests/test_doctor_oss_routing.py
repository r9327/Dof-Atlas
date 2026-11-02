from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools.atlas_doctor_lib.oss_router import route_oss


class DoctorOssRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "tools").mkdir()
        (self.root / "tools" / "example.py").write_text("x = 1\n", encoding="utf-8")
        (self.root / ".github" / "workflows").mkdir(parents=True)
        (self.root / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")

    def _native(self, *args, **kwargs):
        return {"tools": [{"path": "tools/atlas_doctor.py",
                           "capabilities": ["validation"]}]}

    def _probe(self, packages=(), binaries=()):
        return {"results": [{"name": "ruff", "available": True, "version": "0.14",
                             "license_verified": False, "platform_verified": False}]
                if packages else []}

    def test_plan_reuses_catalog_and_never_launches_candidate(self):
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value={"tools": []}) as c,
              patch("tools.atlas_doctor_lib.oss_router.select_tools", side_effect=self._native) as sel,
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight", side_effect=self._probe),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run") as run):
            report = route_oss(self.root, ["tools/example.py"])
        self.assertEqual(report["status"], "ADVISORY_ONLY")
        self.assertFalse(report["phase_certified"])
        self.assertEqual(report["execution"]["status"], "NOT_RUN")
        self.assertFalse(report["native_tools_executed"])
        self.assertEqual(report["native_tools"][0]["path"], "tools/atlas_doctor.py")
        c.assert_called_once()
        sel.assert_called_once()
        run.assert_not_called()

    def test_ruff_is_selected_by_scope_and_argv_cannot_modify_files(self):
        sample = SimpleNamespace(returncode=1, stdout=json.dumps([
            {"code": "F401", "message": "private source content", "filename": "tools/example.py"}]),
            stderr="secret")
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value={}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools", side_effect=self._native),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight", side_effect=self._probe),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run", return_value=sample) as run):
            payload = route_oss(self.root, ["tools/example.py"], run=True)
        args = run.call_args.args[0]
        self.assertIn("--no-fix", args)
        self.assertIn("--no-cache", args)
        self.assertIn("--isolated", args)
        self.assertEqual(args[-2:], ["--", "tools/example.py"])
        self.assertNotIn("private source content", json.dumps(payload))
        self.assertNotIn("secret", json.dumps(payload))
        self.assertEqual(payload["execution"]["status"], "FINDINGS")
        self.assertEqual(payload["execution"]["rule_counts"]["F401"], 1)
        self.assertFalse(payload["phase_certified"])

    def test_missing_package_does_not_execute_or_install(self):
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value={}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools", side_effect=self._native),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight",
                    return_value={"results": [{"name": "ruff", "available": False, "version": None}]}),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run") as run):
            payload = route_oss(self.root, ["tools/example.py"], run=True)
        self.assertEqual(payload["execution"]["status"], "NOT_AVAILABLE")
        run.assert_not_called()

    def test_workflow_selects_native_ci_but_not_unsupported_oss_executor(self):
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value={}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools", side_effect=self._native) as sel,
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight", side_effect=self._probe),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run") as run):
            report = route_oss(self.root, [".github/workflows/ci.yml"], run=True)
        self.assertEqual(report["execution"]["status"], "NOT_AVAILABLE")
        self.assertEqual(sel.call_args.kwargs["capability"], "ci_intelligence")
        run.assert_not_called()

    def test_bad_paths_rejected_before_discovery_and_execution(self):
        for bad in ("../secret.py", "tools/../secret.py", "tools/@options.py",
                    "tools/example.py;touch", "/tools/example.py", "tools/missing.py"):
            with self.subTest(bad=bad), patch("tools.atlas_doctor_lib.oss_router.catalog") as cat:
                with self.assertRaises(ValueError):
                    route_oss(self.root, [bad], run=True)
                cat.assert_not_called()
        # Windows runners cannot always create symlinks without privileges.
        with patch("pathlib.Path.is_symlink", return_value=True):
            with self.assertRaises(ValueError):
                route_oss(self.root, ["tools/example.py"], run=True)
        with self.assertRaises(ValueError):
            route_oss(self.root, ["tools/example.py"] * 17, run=True)

    def test_timeout_is_not_a_fake_success(self):
        from subprocess import TimeoutExpired
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value={}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools", side_effect=self._native),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight", side_effect=self._probe),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run",
                    side_effect=TimeoutExpired("ruff", 1))):
            payload = route_oss(self.root, ["tools/example.py"], run=True, timeout_seconds=1)
        self.assertEqual(payload["execution"]["status"], "TIMEOUT")
        self.assertFalse(payload["phase_certified"])


    def test_doctor_cli_exposes_oss_without_changing_agent_contract(self):
        from tools.atlas_doctor import build_parser
        parsed = build_parser().parse_args(
            ["oss", "tools/example.py", "--run", "--timeout-seconds", "10"])
        self.assertEqual(parsed.command, "oss")
        self.assertTrue(parsed.run)
        self.assertEqual(parsed.paths, ["tools/example.py"])
        self.assertEqual(parsed.timeout_seconds, 10)
        parsed_agent = build_parser().parse_args(["agent", "check", "tools/example.py", "--run-oss"])
        self.assertTrue(parsed_agent.run_oss)

    def test_agent_check_can_invoke_advisor_without_modifying_doctor_verdict(self):
        from tools.atlas_doctor import command_agent
        from tools.atlas_doctor import build_parser
        args = build_parser().parse_args(
            ["agent", "check", "tools/example.py", "--run-oss"])
        core = {"status": "REVIEW", "exit_code": 1, "phase_certified": False}
        with (patch("tools.atlas_doctor_lib.agent_protocol.run_agent_action",
                    return_value=core) as agent,
              patch("tools.atlas_doctor_lib.oss_router.route_oss",
                    return_value={"status": "ADVISORY_ONLY"}) as oss):
            result = command_agent(self.root, args)
        self.assertEqual(result["status"], "REVIEW")
        self.assertEqual(result["exit_code"], 1)
        self.assertEqual(result["oss_advisory"]["status"], "ADVISORY_ONLY")
        oss.assert_called_once()
        agent.assert_called_once()

    def test_agent_blocked_never_invokes_oss(self):
        from tools.atlas_doctor import command_agent
        args = SimpleNamespace(agent_action="check", paths=["tools/example.py"],
                               base_ref="HEAD", structural=False, level=None,
                               run_tests=False, max_tests=4, timeout_seconds=30,
                               run_oss=True)
        with (patch("tools.atlas_doctor_lib.agent_protocol.run_agent_action",
                    return_value={"status": "BLOCKED", "exit_code": 2}),
              patch("tools.atlas_doctor_lib.oss_router.route_oss") as oss):
            result = command_agent(self.root, args)
        self.assertEqual(result["oss_advisory"]["status"], "NOT_RUN")
        oss.assert_not_called()

    def test_inventory_has_29_study_rows_without_claiming_installation(self):
        from tools.atlas_doctor_lib.oss_router import _open_source_inventory
        study = self.root / "docs" / "roadmap"
        study.mkdir(parents=True)
        rows = []
        for number in range(1, 30):
            decision = "REJECT" if number in {28, 29} else "ASSESS"
            rows.append(
                f"| ATOSS-{number:02d} | [tool{number}](https://github.com/org/tool{number}) "
                f"| {decision} | Owner |\n")
        for number in range(1, 6):
            rows.append(
                f"| AT-SUP-{number:02d} | [extra{number}](https://github.com/org/extra{number}) "
                f"| ASSESS | Owner |\n")
        (study / "GITHUB_OPEN_SOURCE_INTEGRATION_2026-10-31.md").write_text(
            "".join(rows), encoding="utf-8")
        report = _open_source_inventory(self.root)
        self.assertEqual(report["status"], "INVENTORIED_NOT_CERTIFIED")
        self.assertEqual(report["count"], 29)
        self.assertEqual(report["supplemental_count"], 5)
        self.assertEqual(len(report["supplemental"]), 5)
        self.assertEqual(report["candidates"][20]["integration"], "DOCTOR_OPT_IN_ONLY")
        self.assertEqual(report["execution_witnesses"], 0)
        self.assertEqual(report["candidates"][19]["integration"], "DOCTOR_OPT_IN_ONLY")
        self.assertEqual(report["candidates"][-1]["integration"], "REJECTED")

    def test_catalog_reports_unready_tools_without_running_them(self):
        catalog = {"tool_count": 2, "agent_ready_count": 1,
                   "automation_ready_count": 1, "unguarded_mutator_count": 1,
                   "tools": [
                       {"path": "tools/atlas_doctor.py", "automation_ready": True},
                       {"path": "tools/legacy.py", "automation_ready": False,
                        "readiness": "review_before_agent_use"},
                   ]}
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value=catalog),
              patch("tools.atlas_doctor_lib.oss_router.select_tools", side_effect=self._native),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight",
                    side_effect=self._probe),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run") as run):
            result = route_oss(self.root, ["tools/example.py"])
        self.assertEqual(result["native_catalog"]["tool_count"], 2)
        self.assertEqual(result["native_catalog"]["automation_ready_count"], 1)
        self.assertEqual(result["native_catalog"]["unready_total"], 1)
        self.assertFalse(result["native_tools_executed"])
        run.assert_not_called()

if __name__ == "__main__":
    unittest.main()
