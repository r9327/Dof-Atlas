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

    def test_scope_policy_reaches_all_30_nonexcluded_candidates(self):
        from tools.atlas_doctor_lib.oss_intelligence import _SCOPES
        candidates = {key for values in _SCOPES.values() for key in values}
        expected = {f"ATOSS-{n:02d}" for n in range(1, 26)}
        expected.update(f"AT-SUP-{n:02d}" for n in range(1, 6))
        self.assertEqual(expected - candidates, set())
        self.assertTrue({"ATOSS-26", "ATOSS-27", "ATOSS-28", "ATOSS-29"}.isdisjoint(candidates))
        self.assertIn("test_tools", classify_scope(["tests/test_doctor_auto_oss.py"]))
        self.assertIn("agent_eval", classify_scope(["tools/atlas_doctor_lib/agent_protocol.py"]))
        self.assertIn("perf", classify_scope(["tools/benchmark_phase8_memory.py"]))

    def test_truncated_shortlist_keeps_every_candidate_visible_but_unexecuted(self):
        paths = [
            "tools/benchmark_phase8_memory.py",
            "app/distribution/launcher.py",
            "tools/atlas_json_benchmark.py",
            ".github/workflows/check.yml",
            "tests/test_atlas_doctor_qt_smoke.py",
        ]
        plan = intelligent_plan(paths, study())
        self.assertGreater(plan["omitted_count"], 0)
        self.assertEqual(len(plan["recommended"]), 8)
        self.assertEqual(len(plan["evaluated_candidates"]),
                         len(plan["recommended"]) + plan["omitted_count"])
        self.assertEqual(plan["omitted_candidates"], plan["evaluated_candidates"][8:])
        from tools.atlas_doctor_lib.oss_intelligence import ai_tool_workflow
        workflow = ai_tool_workflow("plan", {"status": "REVIEW", "exit_code": 1},
                                    plan)
        visible = {row["tool_id"]: row for row in workflow["oss_recommendations"]}
        self.assertEqual(len(visible), len(plan["evaluated_candidates"]))
        for row in plan["omitted_candidates"]:
            self.assertFalse(visible[row["id"]]["shortlisted"])
            self.assertIsNone(visible[row["id"]]["locally_available"])
            self.assertFalse(visible[row["id"]]["automatic_execution"])
        self.assertFalse(workflow["may_claim_full_certification"])

    def test_ai_execution_requires_real_named_integrity_witness(self):
        from tools.atlas_doctor_lib.oss_intelligence import ai_tool_workflow
        plan = intelligent_plan(["tools/test_tool.py"], study())
        core = {"status": "REVIEW", "exit_code": 1}
        fake = {"execution_results": [{"tool": "ruff", "status": "CLEAN"}],
                "execution_summary": {"status": "COMPLETE",
                                      "expected_tools": ["ruff"]},
                "status": "ADVISORY_ONLY"}
        result = ai_tool_workflow("check", core, plan, advisory=fake)
        self.assertFalse(result["approved_oss_execution"]["all_executed"])
        self.assertEqual(result["approved_oss_execution"]["tools"][0]["status"],
                         "UNVERIFIED")

        complete = dict(fake,
            source="tools.atlas_doctor_lib.oss_router.route_oss",
            input_integrity_verified=True, files_modified=False)
        result = ai_tool_workflow("check", core, plan, advisory=complete)
        self.assertTrue(result["approved_oss_execution"]["all_executed"])
        self.assertTrue(result["approved_oss_execution"]["witness_integrity_verified"])
        self.assertTrue(result["approved_oss_execution"]["tools"][0]["executed"])

        for bad in (dict(complete, files_modified=True),
                    dict(complete, input_integrity_verified=False),
                    dict(complete, execution_results=[
                        {"tool": "zizmor", "status": "CLEAN"}])):
            report = ai_tool_workflow("check", core, plan, advisory=bad)
            self.assertFalse(report["approved_oss_execution"]["all_executed"])
            self.assertFalse(report["approved_oss_execution"]["witness_integrity_verified"])

    def test_partial_scan_preserves_real_ruff_but_not_zizmor_attestation(self):
        from tools.atlas_doctor_lib.oss_intelligence import ai_tool_workflow
        plan = intelligent_plan(
            ["tools/test_tool.py", ".github/workflows/check.yml"], study())
        advisory = {
            "source": "tools.atlas_doctor_lib.oss_router.route_oss",
            "status": "ADVISORY_ONLY",
            "input_integrity_verified": True,
            "files_modified": False,
            "execution_results": [
                {"tool": "ruff", "status": "FINDINGS"},
                {"tool": "zizmor", "status": "NOT_AVAILABLE"},
            ],
            "execution_summary": {
                "status": "INCOMPLETE",
                "expected_tools": ["ruff", "zizmor"],
            },
        }
        result = ai_tool_workflow("check", {"status": "REVIEW", "exit_code": 1},
                                  plan, advisory=advisory)
        proof = result["approved_oss_execution"]
        self.assertTrue(proof["witness_integrity_verified"])
        self.assertTrue(proof["tools"][0]["executed"])
        self.assertFalse(proof["tools"][1]["executed"])
        self.assertFalse(proof["all_executed"])
        self.assertEqual(proof["gaps"], [
            {"tool": "zizmor", "status": "NOT_AVAILABLE"},
        ])

    def test_guide_dev_and_json_trials_use_existing_owners_without_certify(self):
        scope = ["tools/ganymede_guide.py",
                 "tools/atlas_json_benchmark.py",
                 "app/distribution/install_location.py",
                 "data/assets/banner.png"]
        plan = intelligent_plan(scope, study())
        routes = plan["native_routes"]
        self.assertTrue(any("Guide scoped owner" in item for item in routes))
        self.assertTrue(any("atlas_json_benchmark" in item for item in routes))
        self.assertTrue(any("Launcher scoped owner" in item for item in routes))
        self.assertTrue(any("asset review" in item for item in routes))
        self.assertTrue(any("--asset-trial" in item for item in routes))
        self.assertTrue(any("--font-trial" in item for item in routes))
        self.assertFalse(any("certify" in item.casefold() for item in routes))
        self.assertFalse(plan["certified"])

    def test_real_optional_trials_are_routed_but_never_auto_executed(self):
        from tools.atlas_doctor_lib.oss_intelligence import ai_tool_workflow
        paths = [
            "tools/atlas_json_benchmark.py",
            "app/assets/themes/dofus_unity/somefont.ttf",
            "tests/test_guide_stage.py",
        ]
        plan = intelligent_plan(paths, study())
        observed = {row["id"]: row for row in plan["evaluated_candidates"]}
        optional = {
            "ATOSS-02", "ATOSS-11", "ATOSS-12", "ATOSS-13",
            "ATOSS-14", "ATOSS-16", "ATOSS-17",
        }
        self.assertTrue(optional.issubset(observed))
        for cid in optional:
            with self.subTest(cid=cid):
                row = observed[cid]
                self.assertEqual(row["decision"], "OPT_IN_TRIAL_AVAILABLE")
                self.assertTrue(row["opt_in_trial_route"])
                self.assertFalse(row["trial_executed"])
                self.assertFalse(row["tool_executed"])
                self.assertFalse(row["adoption_qualified"])
        summary = ai_tool_workflow("plan", {"status": "REVIEW", "exit_code": 1},
                                   plan)
        routed = {row["tool_id"]: row for row in summary["oss_recommendations"]}
        for cid in optional:
            self.assertEqual(routed[cid]["opt_in_trial_route"],
                             observed[cid]["opt_in_trial_route"])
            self.assertFalse(routed[cid]["adoption_qualified"])
            self.assertFalse(routed[cid]["trial_executed"])
        self.assertFalse(summary["may_claim_full_certification"])

    def test_final_policy_rejections_prohibit_optional_preflight(self):
        inventory = study()
        for row in inventory["candidates"]:
            if row["id"] == "ATOSS-02":
                row["final_decision"] = "REJECTED"
        plan = intelligent_plan(["tests/test_doctor_auto_oss.py"], inventory)
        selected = {r["id"]: r for r in plan["evaluated_candidates"]}
        self.assertEqual(selected["ATOSS-02"]["decision"], "REJECTED")
        self.assertEqual(selected["ATOSS-02"]["final_policy_decision"], "REJECTED")
        self.assertNotIn("ATOSS-02",
                         {probe["id"] for probe in plan["local_package_probes"]})
        self.assertFalse(plan["certified"])

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
