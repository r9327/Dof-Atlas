from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.atlas_doctor import build_parser, command_agent
from tools.atlas_doctor_lib.oss_intelligence import (
    ai_tool_workflow, intelligent_plan,
)
from tools.atlas_doctor_lib.oss_router import _zizmor_executable


class DoctorAiUsageContractTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        f = self.root / "tools" / "probe.py"
        f.parent.mkdir(parents=True)
        f.write_text("x = 1\n", encoding="utf-8")
        wf = self.root / ".github/workflows/ci.yml"
        wf.parent.mkdir(parents=True)
        wf.write_text("name: CI\non: push\njobs: {}\n", encoding="utf-8")

    @staticmethod
    def _selection():
        inventory = {
            "status": "INVENTORIED_NOT_CERTIFIED", "count": 29,
            "supplemental_count": 5,
            "candidates": [
                {"id": f"ATOSS-{i:02d}", "name": f"OSS-{i}",
                 "study_decision": "ASSESS"} for i in range(1, 30)
            ],
            "supplemental": [],
        }
        return intelligent_plan(
            ["tools/probe.py", ".github/workflows/ci.yml"], inventory)

    def test_ai_protocol_does_not_confuse_recommendations_with_executions(self):
        selected = self._selection()
        contract = ai_tool_workflow(
            "plan", {"status": "READY", "exit_code": 0}, selected)
        self.assertEqual(contract["doctor_status"], "READY")
        self.assertEqual(len(contract["required_phases"]), 5)
        self.assertTrue(all(item["required"] for item in contract["required_phases"]))
        self.assertFalse(contract["native_routes_executed_by_selection"])
        self.assertEqual(contract["approved_oss_execution"]["expected_tools"],
                         ["ruff", "zizmor"])
        self.assertEqual([t["status"] for t in
                          contract["approved_oss_execution"]["tools"]],
                         ["NOT_RUN", "NOT_RUN"])
        self.assertFalse(contract["approved_oss_execution"]["all_executed"])
        self.assertFalse(contract["may_claim_full_certification"])

    def test_check_records_only_real_successful_scanner_responses(self):
        plan = self._selection()
        status = {
            "execution_results": [
                {"tool": "ruff", "status": "CLEAN"},
                {"tool": "zizmor", "status": "NOT_AVAILABLE"},
            ],
            "execution_summary": {"status": "INCOMPLETE"},
        }
        result = ai_tool_workflow(
            "check", {"status": "REVIEW", "exit_code": 1}, plan,
            advisory=status, dispatch={"truncated_count": 0})
        self.assertEqual(result["doctor_status"], "REVIEW")
        self.assertEqual(result["approved_oss_execution"]["reported_execution_summary_status"],
                         "INCOMPLETE")
        self.assertEqual([t["executed"] for t in
                          result["approved_oss_execution"]["tools"]], [True, False])
        self.assertEqual(result["approved_oss_execution"]["gaps"],
                         [{"tool": "zizmor", "status": "NOT_AVAILABLE"}])
        self.assertFalse(result["approved_oss_execution"]["all_executed"])

    def test_truncation_blocks_all_executed_claim(self):
        status = {"execution_results": [
            {"tool": "ruff", "status": "CLEAN"},
            {"tool": "zizmor", "status": "FINDINGS"},
        ], "execution_summary": {"status": "COMPLETE"}}
        result = ai_tool_workflow(
            "check", {"status": "PASS", "exit_code": 0}, self._selection(),
            advisory=status, dispatch={"truncated_count": 2})
        self.assertFalse(result["approved_oss_execution"]["all_executed"])
        self.assertTrue(result["approved_oss_execution"]["coverage_incomplete"])
        self.assertIn({"tool": "scope", "status": "TRUNCATED"},
                      result["approved_oss_execution"]["gaps"])
        self.assertFalse(result["may_claim_full_certification"])

    def test_agent_command_emits_ai_contract_without_weakening_doctor_verdict(self):
        args = build_parser().parse_args(
            ["agent", "check", "tools/probe.py", "--run-tests"])
        core = {"status": "REVIEW", "exit_code": 1,
                "certification": {"full_certified": False}}
        with (patch("tools.atlas_doctor_lib.agent_protocol.run_agent_action",
                    return_value=core),
              patch("tools.atlas_doctor_lib.oss_router._open_source_inventory",
                    return_value={"status": "REVIEW", "candidates": [],
                                  "supplemental": []}),
              patch("tools.atlas_doctor_lib.oss_router.route_oss",
                    return_value={
                        "status": "ADVISORY_ONLY",
                        "execution_results": [
                            {"tool": "ruff", "status": "NOT_AVAILABLE"}
                        ]})):
            output = command_agent(self.root, args)
        self.assertEqual(output["status"], "REVIEW")
        self.assertEqual(output["exit_code"], 1)
        self.assertFalse(output["certification"]["full_certified"])
        self.assertIn("ai_tool_workflow", output)
        self.assertIn("required_phases", output["ai_tool_workflow"])


    def test_no_oss_override_remains_not_run_and_never_invokes_tools(self):
        args = build_parser().parse_args(
            ["agent", "check", "tools/probe.py", "--run-tests", "--no-oss"])
        core = {"status": "PASS", "exit_code": 0}
        with (patch("tools.atlas_doctor_lib.agent_protocol.run_agent_action",
                    return_value=core),
              patch("tools.atlas_doctor_lib.oss_router._open_source_inventory",
                    return_value={"status": "REVIEW", "candidates": [],
                                  "supplemental": []}),
              patch("tools.atlas_doctor_lib.oss_router.route_oss",
                    side_effect=AssertionError("unexpected scanner execution"))):
            output = command_agent(self.root, args)
        self.assertEqual(output["status"], "PASS")
        self.assertEqual(output["oss_advisory"]["status"], "NOT_RUN")
        self.assertEqual(
            output["ai_tool_workflow"]["approved_oss_execution"]["tools"][0]["status"],
            "NOT_RUN")
        self.assertFalse(
            output["ai_tool_workflow"]["approved_oss_execution"]["all_executed"])

    def test_zizmor_python_user_scripts_on_windows_without_path_changes(self):
        scripts = self.root / "Scripts"
        scripts.mkdir()
        exe = scripts / "zizmor.exe"
        exe.write_bytes(b"dummy executable for path test")
        with (patch("shutil.which", return_value=None),
              patch("tools.atlas_doctor_lib.oss_router.sys.platform", "win32"),
              patch("tools.atlas_doctor_lib.oss_router.site.getuserbase",
                    return_value=str(self.root))):
            self.assertEqual(_zizmor_executable(), str(exe))
        exe.unlink()
        with (patch("shutil.which", return_value=None),
              patch("tools.atlas_doctor_lib.oss_router.sys.platform", "win32"),
              patch("tools.atlas_doctor_lib.oss_router.site.getuserbase",
                    return_value=str(self.root))):
            self.assertIsNone(_zizmor_executable())

    def test_documentation_and_bootstrap_are_explicit_and_consistent(self):
        root = Path(__file__).resolve().parents[1]
        names = ["AI_ENTRYPOINT.md", "AI_CONTEXT.md",
                 "tools/skills/dofus-atlas-tools/SKILL.md",
                 ".agents/skills/evidence-driven-validation/SKILL.md",
                 "CLAUDE.md", ".github/copilot-instructions.md",
                 ".cursor/rules/atlas-doctor.mdc"]
        for name in names:
            with self.subTest(name=name):
                content = (root / name).read_text(encoding="utf-8")
                self.assertIn("ai_tool_workflow", content)
        script = (root / "tools/setup_doctor_oss.ps1").read_text(encoding="utf-8")
        self.assertIn("param([switch]$Install)", script)
        self.assertIn("--verify-live", script)
        self.assertIn("--only-binary=:all:", script)
        self.assertIn("ruff==0.17.3", script)
        self.assertIn("zizmor==1.30.1", script)


if __name__ == "__main__":
    unittest.main()
