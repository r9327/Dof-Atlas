from __future__ import annotations

import contextlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from tools.atlas_doctor import build_parser, main
from tools.atlas_doctor_lib.oss_router import qualify_live, route_oss


class DoctorLiveEvidenceTests(unittest.TestCase):
    """Mocked *contract* tests. Real executable qualification is separate."""

    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name, content in (
            ("tools/probe.py", "x = 1\n"),
            (".github/workflows/probe.yml", "name: probe\non: push\njobs: {}\n"),
        ):
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(content, encoding="utf-8")
        self.files = ["tools/probe.py", ".github/workflows/probe.yml"]

    @staticmethod
    def _valid():
        return {
            "status": "ADVISORY_ONLY",
            "execution_results": [
                {"tool": "ruff", "status": "CLEAN", "finding_count": 0},
                {"tool": "zizmor", "status": "FINDINGS", "finding_count": 1},
            ],
            "oss_candidates": [
                {"id": "ruff", "version_claim": "0.17.0"},
                {"id": "zizmor", "version_claim": None},
            ],
            "execution_summary": {"gaps": []},
            "phase_certified": False,
        }

    def test_two_real_adapters_are_required_for_a_live_attestation(self):
        with (patch("tools.atlas_doctor_lib.oss_router.route_oss",
                    return_value=self._valid()) as run,
              patch("tools.atlas_doctor_lib.oss_router._observed_tool_version",
                    side_effect=lambda root, name: "1.8.0" if name == "zizmor" else "0.17.0")):
            report = qualify_live(self.root, self.files, timeout_seconds=30)
        self.assertEqual(report["status"], "LIVE_PASS")
        self.assertEqual(report["actual_executions"], 2)
        self.assertTrue(report["input_files_unchanged"])
        self.assertEqual(len(report["input_sha256"]), 2)
        self.assertEqual(report["versions_observed"]["ruff"], "0.17.0")
        self.assertFalse(report["phase_certified"])
        self.assertFalse(report["network_verified_by_traffic_capture"])
        run.assert_called_once_with(self.root, self.files, run=True,
                                    timeout_seconds=30)

    def test_missing_zizmor_cannot_qualify_live(self):
        result = self._valid()
        result["execution_results"][1]["status"] = "NOT_AVAILABLE"
        result["execution_summary"]["gaps"] = [
            {"tool": "zizmor", "status": "NOT_AVAILABLE"}]
        with patch("tools.atlas_doctor_lib.oss_router.route_oss",
                   return_value=result):
            report = qualify_live(self.root, self.files)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["actual_executions"], 1)
        self.assertEqual(report["gaps"][0]["tool"], "zizmor")
        self.assertFalse(report["windows_13_qualified"])

    def test_live_scan_with_missing_version_is_not_fully_qualified(self):
        with (patch("tools.atlas_doctor_lib.oss_router.route_oss",
                    return_value=self._valid()),
              patch("tools.atlas_doctor_lib.oss_router._observed_tool_version",
                    side_effect=lambda root, name: "0.17.0" if name == "ruff" else None)):
            report = qualify_live(self.root, self.files)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["actual_executions"], 2)
        self.assertIsNone(report["versions_observed"]["zizmor"])
        self.assertFalse(report["windows_13_qualified"])

    def test_mutation_is_a_failure_not_a_success(self):
        def mutator(_root, _files, **_):
            (self.root / self.files[0]).write_text("x = 99\n", encoding="utf-8")
            return self._valid()
        with patch("tools.atlas_doctor_lib.oss_router.route_oss",
                   side_effect=mutator):
            report = qualify_live(self.root, self.files)
        self.assertEqual(report["status"], "FAIL")
        self.assertFalse(report["input_files_unchanged"])
        self.assertEqual(report["input_sha256"], {})
        self.assertFalse(report["windows_13_qualified"])

    def test_python_only_cannot_fake_two_tool_live_acceptance(self):
        with patch("tools.atlas_doctor_lib.oss_router.route_oss") as run:
            report = qualify_live(self.root, ["tools/probe.py"])
        run.assert_not_called()
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["actual_executions"], 0)

    def test_version_probe_is_bound_and_does_not_inherit_github_secrets(self):
        from types import SimpleNamespace
        from tools.atlas_doctor_lib.oss_router import _observed_tool_version
        with (patch("tools.atlas_doctor_lib.oss_router.subprocess.run",
                    return_value=SimpleNamespace(returncode=0,
                                                stdout="zizmor 1.32.0\n",
                                                stderr="TOKEN")) as run,
              patch.dict("tools.atlas_doctor_lib.oss_router.os.environ",
                         {"GITHUB_TOKEN": "secret", "HTTP_PROXY": "localhost"},
                         clear=False)):
            version = _observed_tool_version(self.root, "zizmor")
        self.assertEqual(version, "1.32.0")
        self.assertIn("--version", run.call_args.args[0])
        self.assertNotIn("GITHUB_TOKEN", run.call_args.kwargs["env"])
        self.assertNotIn("HTTP_PROXY", run.call_args.kwargs["env"])
        self.assertEqual(run.call_args.kwargs["env"]["ZIZMOR_OFFLINE"], "1")

    def test_version_probe_does_not_trust_arbitrary_tool_output(self):
        from types import SimpleNamespace
        from tools.atlas_doctor_lib.oss_router import _observed_tool_version
        with patch("tools.atlas_doctor_lib.oss_router.subprocess.run",
                   return_value=SimpleNamespace(returncode=0,
                                               stdout="zizmor 1.32.0 secret\n",
                                               stderr="")):
            self.assertIsNone(_observed_tool_version(self.root, "zizmor"))
        self.assertIsNone(_observed_tool_version(self.root, "other-binary"))

    def test_unsafe_input_is_rejected_before_any_execution(self):
        with patch("tools.atlas_doctor_lib.oss_router.route_oss") as run:
            with self.assertRaises(ValueError):
                qualify_live(self.root, ["tools/../probe.py", self.files[1]])
        run.assert_not_called()

    def test_mixed_diagnostic_summary_never_hides_a_missing_tool(self):
        from types import SimpleNamespace
        probe = {"results": [{"kind": "python_distribution", "name": "ruff",
                               "available": True, "version": "0.17.0"},
                              {"kind": "path_executable", "name": "zizmor",
                               "available": False, "version": None}]}
        with (patch("tools.atlas_doctor_lib.oss_router.catalog",
                    return_value={"tools": []}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools",
                    return_value={"tools": []}),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight",
                    return_value=probe),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run",
                    return_value=SimpleNamespace(returncode=0, stdout="[]", stderr=""))):
            result = route_oss(self.root, self.files, run=True)
        summary = result["execution_summary"]
        self.assertEqual(summary["expected_tools"], ["ruff", "zizmor"])
        self.assertEqual(summary["status"], "INCOMPLETE")
        self.assertEqual(summary["confirmed_executions"], 1)
        self.assertEqual(summary["gaps"], [{"tool": "zizmor", "status": "NOT_AVAILABLE"}])
        self.assertEqual(result["status"], "ADVISORY_ONLY")
        self.assertFalse(result["phase_certified"])

    def test_oss_command_live_verification_has_nonzero_exit_unless_live_pass(self):
        for status, exit_expected in (
            ("LIVE_PASS", 0), ("REVIEW", 1), ("FAIL", 2), ("BLOCKED", 2)):
            with self.subTest(status=status):
                with (patch("tools.atlas_doctor_lib.oss_router.qualify_live",
                            return_value={"status": status}) as live,
                      contextlib.redirect_stdout(io.StringIO())):
                    exit_code = main(["oss", *self.files, "--verify-live", "--json"])
                self.assertEqual(exit_code, exit_expected)
                live.assert_called_once()

    def test_cli_explicit_option_does_not_install_or_set_standard_run(self):
        parsed = build_parser().parse_args(
            ["oss", *self.files, "--verify-live", "--timeout-seconds", "40"])
        self.assertTrue(parsed.verify_live)
        self.assertFalse(parsed.run)
        self.assertEqual(parsed.timeout_seconds, 40)


if __name__ == "__main__":
    unittest.main()
