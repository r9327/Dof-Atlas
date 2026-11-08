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
        self.assertEqual(args[1:4], ["-P", "-m", "ruff"])
        self.assertNotIn("PYTHONNOUSERSITE", run.call_args.kwargs["env"])
        self.assertEqual(run.call_args.kwargs["env"]["PYTHONPATH"], "")
        self.assertEqual(args[-2:], ["--", "tools/example.py"])
        self.assertNotIn("private source content", json.dumps(payload))
        self.assertNotIn("secret", json.dumps(payload))
        self.assertEqual(payload["execution"]["status"], "FINDINGS")
        self.assertEqual(payload["execution"]["rule_counts"]["F401"], 1)
        self.assertFalse(payload["phase_certified"])

    def test_ruff_inconsistent_exit_and_json_never_claim_clean(self):
        from types import SimpleNamespace
        for returncode, findings in ((1, []), (0, [{"code": "F401"}])):
            with self.subTest(code=returncode):
                fake = SimpleNamespace(
                    returncode=returncode, stdout=json.dumps(findings), stderr="")
                with (patch("tools.atlas_doctor_lib.oss_router.catalog",
                            return_value={"tools": []}),
                      patch("tools.atlas_doctor_lib.oss_router.select_tools",
                            side_effect=self._native),
                      patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight",
                            side_effect=self._probe),
                      patch("tools.atlas_doctor_lib.oss_router.subprocess.run",
                            return_value=fake)):
                    report = route_oss(self.root, ["tools/example.py"], run=True)
                self.assertEqual(report["execution"]["status"], "ERROR")
                self.assertEqual(report["execution_count"], 0)
                self.assertEqual(report["execution_summary"]["status"], "INCOMPLETE")

    def test_scanner_mutation_cancels_all_execution_witnesses(self):
        sample = SimpleNamespace(returncode=0, stdout="[]", stderr="")
        def alter_input(*args, **kwargs):
            (self.root / "tools/example.py").write_text("x = 42\n", encoding="utf-8")
            return sample
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value={}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools",
                    side_effect=self._native),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight",
                    side_effect=self._probe),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run",
                    side_effect=alter_input)):
            payload = route_oss(self.root, ["tools/example.py"], run=True)
        self.assertEqual(payload["execution"]["status"], "ERROR")
        self.assertTrue(payload["files_modified"])
        self.assertFalse(payload["input_integrity_verified"])
        self.assertEqual(payload["execution_count"], 0)
        self.assertEqual(payload["execution_summary"]["status"], "INCOMPLETE")
        self.assertNotIn("x = 42", json.dumps(payload))

    def test_unverifiable_large_input_never_reaches_third_party(self):
        (self.root / "tools/example.py").write_bytes(b"#" * 2_000_001)
        with (patch("tools.atlas_doctor_lib.oss_router.catalog", return_value={}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools",
                    side_effect=self._native),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight",
                    side_effect=self._probe),
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run") as run):
            payload = route_oss(self.root, ["tools/example.py"], run=True)
        run.assert_not_called()
        self.assertEqual(payload["execution"]["status"], "ERROR")
        self.assertEqual(payload["execution_count"], 0)
        self.assertIsNone(payload["files_modified"])
        self.assertFalse(payload["input_integrity_verified"])

    def test_ruff_version_probe_uses_user_site_but_not_project_cwd(self):
        from tools.atlas_doctor_lib.oss_router import _observed_tool_version
        sample = SimpleNamespace(returncode=0, stdout="ruff 0.17.3\n", stderr="")
        with patch("tools.atlas_doctor_lib.oss_router.subprocess.run",
                   return_value=sample) as run:
            version = _observed_tool_version(self.root, "ruff")
        self.assertEqual(version, "0.17.3")
        self.assertEqual(run.call_args.args[0][1:4], ["-P", "-m", "ruff"])
        self.assertNotIn("PYTHONNOUSERSITE", run.call_args.kwargs["env"])
        self.assertEqual(run.call_args.kwargs["env"]["PYTHONPATH"], "")

    def test_windows_developer_install_is_explicit_and_verifies_wheels(self):
        from pathlib import Path
        script = (Path(__file__).resolve().parents[1] /
                  "tools/setup_doctor_oss.ps1").read_text(encoding="utf-8")
        self.assertIn("param([switch]$Install)", script)
        self.assertIn("if ($Install)", script)
        self.assertIn("tools.doctor_oss_wheels --install", script)
        self.assertIn("if ($LASTEXITCODE -ne 0)", script)
        self.assertNotIn("--hash=sha256:", script)
        self.assertNotIn("pip install --user", script)

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

    def test_imagehash_is_explicit_readonly_and_reports_visual_candidates(self):
        from types import ModuleType
        from tools.atlas_doctor_lib.oss_router import trial_imagehash
        a = self.root / "tests" / "first.png"
        b = self.root / "tests" / "second.png"
        a.parent.mkdir(parents=True, exist_ok=True)
        a.write_bytes(b"example a")
        b.write_bytes(b"example b")

        class Picture:
            width = 10
            height = 10
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
        image = ModuleType("PIL.Image")
        image.open = lambda path: Picture()
        image.DecompressionBombError = ValueError
        pil = ModuleType("PIL")
        pil.Image = image
        imagehash = ModuleType("imagehash")
        class Hash:
            def __sub__(self, other):
                return 2
        imagehash.phash = lambda picture: Hash()
        with patch.dict("sys.modules", {"PIL": pil, "PIL.Image": image,
                                         "imagehash": imagehash}):
            report = trial_imagehash(self.root, ["tests/first.png",
                                                  "tests/second.png"])
        self.assertEqual(report["status"], "TRIAL_COMPLETE")
        self.assertEqual(report["execution_count"], 1)
        self.assertEqual(report["possible_visual_duplicates"][0]["distance"], 2)
        self.assertFalse(report["automated_deletion_allowed"])
        self.assertFalse(report["runtime_consumers_verified"])
        self.assertTrue(a.is_file() and b.is_file())

    def test_imagehash_is_never_automatic_or_silent_without_dependency(self):
        from tools.atlas_doctor_lib.oss_router import trial_imagehash
        image = self.root / "tests" / "first.png"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"example a")
        with patch.dict("sys.modules", {"imagehash": None}):
            report = trial_imagehash(self.root, ["tests/first.png"])
        self.assertEqual(report["status"], "NOT_AVAILABLE")
        self.assertEqual(report["execution_count"], 0)
        with self.assertRaises(ValueError):
            trial_imagehash(self.root, ["tools/example.py"])

        from tools.atlas_doctor import build_parser
        parsed = build_parser().parse_args([
            "oss", "tests/first.png", "--asset-trial"])
        self.assertTrue(parsed.asset_trial)
        self.assertFalse(parsed.run)
        self.assertFalse(parsed.verify_live)

    def test_fonttools_reads_bounded_metadata_without_modifying_fonts(self):
        import sys
        from types import ModuleType
        from tools.atlas_doctor_lib.oss_router import trial_fonttools
        fontfile = self.root / "tests" / "unity.ttf"
        fontfile.parent.mkdir(parents=True, exist_ok=True)
        fontfile.write_bytes(b"synthetic-font")
        class Names:
            def getDebugName(self, key):
                return {1: "Unity Family", 2: "Medium", 13: "do-not-trust"}[key]
        class Font:
            def __init__(self, path, *, lazy, recalcBBoxes, recalcTimestamp):
                self.path = path
                self.names = Names()
                self.closed = False
                self.settings = (lazy, recalcBBoxes, recalcTimestamp)
                self_test.assertEqual(self.settings, (True, False, False))
            def __getitem__(self, name):
                self_test.assertEqual(name, "name")
                return self.names
            def close(self):
                self.closed = True
        self_test = self
        package = ModuleType("fontTools")
        package.__path__ = []
        ttlib = ModuleType("fontTools.ttLib")
        ttlib.TTFont = Font
        package.ttLib = ttlib
        with patch.dict(sys.modules, {"fontTools": package,
                                      "fontTools.ttLib": ttlib}):
            report = trial_fonttools(self.root, ["tests/unity.ttf"])
        self.assertEqual(report["status"], "TRIAL_COMPLETE")
        self.assertTrue(report["input_integrity_verified"])
        self.assertEqual(report["fonts"][0]["family"], "Unity Family")
        self.assertTrue(report["fonts"][0]["license_metadata_present"])
        self.assertFalse(report["fonts"][0]["license_verified"])
        self.assertFalse(report["qt_rendering_verified"])
        self.assertFalse(report["runtime_consumers_verified"])
        self.assertNotIn("do-not-trust", json.dumps(report))
        self.assertEqual(fontfile.read_bytes(), b"synthetic-font")

    def test_fonttools_rejects_bad_font_or_missing_optional_dependency(self):
        import sys
        from tools.atlas_doctor_lib.oss_router import trial_fonttools
        fontfile = self.root / "tests" / "unity.ttf"
        fontfile.parent.mkdir(parents=True, exist_ok=True)
        fontfile.write_bytes(b"synthetic-font")
        with patch.dict(sys.modules, {"fontTools": None,
                                      "fontTools.ttLib": None}):
            unavailable = trial_fonttools(self.root, ["tests/unity.ttf"])
        self.assertEqual(unavailable["status"], "NOT_AVAILABLE")
        self.assertEqual(unavailable["execution_count"], 0)
        with self.assertRaises(ValueError):
            trial_fonttools(self.root, ["tools/example.py"])
        # A malformed local font must never yield a metadata or license PASS.
        from types import ModuleType
        package = ModuleType("fontTools")
        package.__path__ = []
        ttlib = ModuleType("fontTools.ttLib")
        ttlib.TTFont = lambda *a, **k: (_ for _ in ()).throw(ValueError("source secret"))
        package.ttLib = ttlib
        with patch.dict(sys.modules, {"fontTools": package,
                                      "fontTools.ttLib": ttlib}):
            failed = trial_fonttools(self.root, ["tests/unity.ttf"])
        self.assertEqual(failed["status"], "ERROR")
        self.assertNotIn("source secret", json.dumps(failed))

    def test_fonttools_cli_is_exclusive_and_not_a_fake_pass(self):
        import contextlib
        import io
        from tools import atlas_doctor
        args = atlas_doctor.build_parser().parse_args([
            "oss", "tests/unity.ttf", "--font-trial"])
        self.assertTrue(args.font_trial)
        self.assertFalse(args.run)
        with (patch.object(atlas_doctor, "command_oss",
                           return_value={"status": "NOT_AVAILABLE"}),
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(atlas_doctor.main([
                "oss", "tests/unity.ttf", "--font-trial"]), 1)
        with (patch.object(atlas_doctor, "command_oss",
                           return_value={"status": "TRIAL_COMPLETE"}),
              contextlib.redirect_stdout(io.StringIO())):
            self.assertEqual(atlas_doctor.main([
                "oss", "tests/unity.ttf", "--font-trial"]), 0)
        with patch("tools.atlas_doctor_lib.oss_router.trial_fonttools") as trial:
            payload = atlas_doctor.command_oss(self.root,
                atlas_doctor.build_parser().parse_args([
                    "oss", "tests/unity.ttf", "--font-trial", "--run"]))
        self.assertEqual(payload["status"], "BLOCKED")
        trial.assert_not_called()

    def test_imagehash_cli_errors_are_nonzero_not_fake_success(self):
        import contextlib
        import io
        from tools import atlas_doctor
        with (patch.object(atlas_doctor, "command_oss",
                           return_value={"status": "NOT_AVAILABLE"}) as command,
              contextlib.redirect_stdout(io.StringIO())):
            result = atlas_doctor.main([
                "oss", "tests/first.png", "--asset-trial"])
        self.assertEqual(result, 1)
        command.assert_called_once()
        with (patch.object(atlas_doctor, "command_oss",
                           return_value={"status": "TRIAL_COMPLETE"}),
              contextlib.redirect_stdout(io.StringIO())):
            result = atlas_doctor.main([
                "oss", "tests/first.png", "--asset-trial"])
        self.assertEqual(result, 0)

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

    def test_optional_preflight_exception_blocks_both_scanners_without_exception_leak(self):
        with (patch("tools.atlas_doctor_lib.oss_router.catalog",
                    return_value={"tools": []}),
              patch("tools.atlas_doctor_lib.oss_router.select_tools",
                    return_value={"tools": []}),
              patch("tools.atlas_doctor_lib.oss_router.local_candidate_preflight",
                    side_effect=OSError("sensitive local package path")),
              patch("tools.atlas_doctor_lib.oss_router._zizmor_executable") as fallback,
              patch("tools.atlas_doctor_lib.oss_router.subprocess.run") as run):
            report = route_oss(self.root, [
                "tools/example.py", ".github/workflows/ci.yml"], run=True)
        run.assert_not_called()
        fallback.assert_not_called()
        self.assertEqual(report["local_preflight_status"], "ERROR")
        self.assertEqual(report["local_preflight_error_type"], "OSError")
        self.assertEqual([row["tool"] for row in report["execution_results"]],
                         ["ruff", "zizmor"])
        self.assertEqual([row["status"] for row in report["execution_results"]],
                         ["ERROR", "ERROR"])
        self.assertEqual(report["execution_count"], 0)
        self.assertEqual(report["execution_summary"]["status"], "INCOMPLETE")
        self.assertFalse(report["phase_certified"])
        self.assertNotIn("sensitive local package path", json.dumps(report))

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

    def test_substituted_candidate_id_is_review_even_when_counts_match(self):
        from tools.atlas_doctor_lib.oss_router import _open_source_inventory
        study = self.root / "docs" / "roadmap"
        study.mkdir(parents=True)
        lines = [
            f"| ATOSS-{number:02d} | [tool](https://github.com/org/tool) | ASSESS | Owner |"
            for number in range(1, 30)
        ]
        lines.extend(
            f"| AT-SUP-{number:02d} | [extra](https://github.com/org/extra) | ASSESS | Owner |"
            for number in range(1, 6)
        )
        lines[28] = lines[28].replace("ATOSS-29", "ATOSS-30")
        (study / "GITHUB_OPEN_SOURCE_INTEGRATION_2026-10-31.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
        report = _open_source_inventory(self.root)
        self.assertEqual(report["count"], 29)
        self.assertEqual(report["supplemental_count"], 5)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["missing_ids"], ["ATOSS-29"])
        self.assertEqual(report["unexpected_ids"], ["ATOSS-30"])
        self.assertEqual(report["execution_witnesses"], 0)

    def test_repository_study_covers_all_34_exact_ids(self):
        from tools.tool_audit import ROOT
        from tools.atlas_doctor_lib.oss_router import _open_source_inventory
        report = _open_source_inventory(ROOT)
        expected = {f"ATOSS-{number:02d}" for number in range(1, 30)}
        expected.update(f"AT-SUP-{number:02d}" for number in range(1, 6))
        actual = {row["id"] for row in report["candidates"] + report["supplemental"]}
        self.assertEqual(report["status"], "INVENTORIED_NOT_CERTIFIED")
        self.assertEqual(actual, expected)
        self.assertEqual(report["missing_ids"], [])
        self.assertEqual(report["unexpected_ids"], [])
        self.assertEqual(report["execution_witnesses"], 0)

    def test_legacy_study_without_final_table_remains_inventory_only(self):
        from tools.atlas_doctor_lib.oss_router import _open_source_inventory
        study = self.root / "docs" / "roadmap"
        study.mkdir(parents=True, exist_ok=True)
        rows = [
            f"| ATOSS-{number:02d} | [x](https://github.com/a/x) | ASSESS | Owner |"
            for number in range(1, 30)
        ] + [
            f"| AT-SUP-{number:02d} | [x](https://github.com/a/x) | ASSESS | Owner |"
            for number in range(1, 6)
        ]
        (study / "GITHUB_OPEN_SOURCE_INTEGRATION_2026-10-31.md").write_text(
            "\n".join(rows) + "\n", encoding="utf-8")
        report = _open_source_inventory(self.root)
        self.assertEqual(report["status"], "INVENTORIED_NOT_CERTIFIED")
        self.assertEqual(report["final_decision_status"], "NOT_RECORDED")
        self.assertEqual(report["execution_witnesses"], 0)
        self.assertTrue(all(row["final_decision"] is None for row in
                            report["candidates"] + report["supplemental"]))

    def test_final_study_decisions_cover_all_ids_without_claiming_execution(self):
        from tools.tool_audit import ROOT
        from tools.atlas_doctor_lib.oss_router import _open_source_inventory
        report = _open_source_inventory(ROOT)
        decisions = {row["id"]: row["final_decision"]
                     for row in report["candidates"] + report["supplemental"]}
        self.assertEqual(len(decisions), 34)
        self.assertEqual(report["final_decision_status"],
                         "DOCUMENTED_NOT_QUALIFIED")
        self.assertEqual(sum(report["final_decision_counts"].values()), 34)
        self.assertEqual(report["final_decision_counts"]["ADOPTED"], 1)
        self.assertEqual(report["final_decision_counts"]["HOLDING_ONLY"], 2)
        self.assertEqual(report["final_decision_counts"]["DEFERRED_WITH_REASON"], 7)
        self.assertFalse(report["final_decisions_are_execution_evidence"])
        self.assertEqual(report["execution_witnesses"], 0)
        self.assertEqual(decisions["ATOSS-20"], "ADOPTED")
        self.assertEqual(decisions["ATOSS-28"], "REJECTED")

    def test_partial_final_decision_section_cannot_claim_complete(self):
        from tools.atlas_doctor_lib.oss_router import _open_source_inventory
        study_dir = self.root / "docs" / "roadmap"
        study_dir.mkdir(parents=True, exist_ok=True)
        original = "\n".join(
            [f"| ATOSS-{i:02d} | [x](https://github.com/a/x) | ASSESS | Owner |"
             for i in range(1, 30)] +
            [f"| AT-SUP-{i:02d} | [x](https://github.com/a/x) | ASSESS | Owner |"
             for i in range(1, 6)])
        (study_dir / "GITHUB_OPEN_SOURCE_INTEGRATION_2026-10-31.md").write_text(
            original + "\n### Décision de maintenance pour chacun des 34 candidats\n"
            "| **ATOSS-01** | ADOPTED | reason | NOT_RUN |\n"
            "### Exécution par gros lots\n", encoding="utf-8")
        report = _open_source_inventory(self.root)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["final_decision_status"], "REVIEW")
        self.assertEqual(len(report["final_decision_missing_ids"]), 33)
        self.assertFalse(report["final_decisions_are_execution_evidence"])

    def test_corrupt_final_decision_cannot_be_silently_qualified(self):
        from tools.atlas_doctor_lib.oss_router import _open_source_inventory
        study_dir = self.root / "docs" / "roadmap"
        study_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            f"| ATOSS-{i:02d} | [x](https://github.com/a/x) | ASSESS | Owner |"
            for i in range(1, 30)
        ] + [
            f"| AT-SUP-{i:02d} | [x](https://github.com/a/x) | ASSESS | Owner |"
            for i in range(1, 6)
        ]
        lines.append("### Décision de maintenance pour chacun des 34 candidats")
        lines.append("| **ATOSS-01** | SOMETHING_UNKNOWN | reason | NOT_RUN |")
        lines.append("| **ATOSS-01** | ADOPTED | reason | NOT_RUN |")
        lines.append("### Exécution par gros lots")
        path = study_dir / "GITHUB_OPEN_SOURCE_INTEGRATION_2026-10-31.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report = _open_source_inventory(self.root)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["final_decision_status"], "REVIEW")
        self.assertIn("malformed final decision row",
                      report["final_decision_errors"])
        self.assertEqual(report["execution_witnesses"], 0)

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
