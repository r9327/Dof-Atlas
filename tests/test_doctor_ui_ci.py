from __future__ import annotations

"""Stdlib discovery: intentionally runnable without importing tests or Qt."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.doctor_ui import required_assertions, verdict
from tools.atlas_doctor_lib.doctor_ui_ci import (
    ALL_GUIDES, ROOT, REGRESSION_REQUIREMENTS, campaign_verdict, classify_ui,
    dependency_map, read_evidence, watch_ui_regressions,
)

SHA = "a" * 40
BASE = "b" * 40


class DoctorUiSelectionTests(unittest.TestCase):
    def plan(self, *paths, **kwargs):
        return classify_ui(ROOT, paths, candidate_sha=SHA, base_sha=BASE, **kwargs)

    def test_docs_independent_json_auditor_and_non_ui_test_skip_deliberately(self):
        for path in ("docs/roadmap/new.md", "data/routes/guide_ultime_manual/README.md",
                     "tools/atlas_json_raw.py", "tests/test_ci_scope_gate.py"):
            with self.subTest(path=path):
                plan = self.plan(path)
                self.assertEqual(plan["selected_scenarios"], [])
                self.assertEqual(plan["status"], "NOT_APPLICABLE")
                self.assertFalse(plan["tests_executed"])
                self.assertEqual(campaign_verdict(plan, [], SHA)["status"], "NOT_APPLICABLE")

    def test_ci_infrastructure_selects_validator_without_unrelated_product_journeys(self):
        paths = ['.github/workflows/phase-certification.yml', '.github/workflows/public-pr-ci.yml',
                 'tools/atlas_doctor_lib/ci_orchestrator.py', 'tools/atlas_doctor_lib/ci_routes.json',
                 'tools/atlas_meta_integrity.py', 'tools/ci_main_phase_evidence.py',
                 'tools/ci_verified_pr_full.py', 'tools/atlas_integrity_policy.json']
        plan = self.plan(*paths, deleted=['.github/workflows/public-pr-ci.yml'])
        self.assertEqual(plan['status'], 'UI_REQUIRED')
        self.assertEqual(plan['selected_scenarios'], ['validator-smoke'])
        self.assertEqual(plan['uncertainty'], [])
        self.assertEqual(plan['deleted_paths'], ['.github/workflows/public-pr-ci.yml'])

    def test_infrastructure_does_not_hide_runtime_ui_or_unknown_deletion(self):
        mixed = self.plan('.github/workflows/app-ci.yml', 'app/ui/theme.py')
        self.assertEqual(set(mixed['selected_scenarios']), set(ALL_GUIDES) | {'validator-smoke'})
        for path in ['app/ui/old_view.py', 'tools/unknown.py']:
            plan = self.plan('.github/workflows/app-ci.yml', deleted=[path])
            self.assertEqual(plan['status'], 'REVIEW_REQUIRED')

    def test_ci_auditor_whitelist_rejects_new_application_or_dynamic_import(self):
        for content in ['from app.ui import theme\n', 'from PySide6 import QtWidgets\n', '__import__("app.ui.theme")\n']:
            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                target = root / 'tools/atlas_meta_integrity.py'
                target.parent.mkdir()
                target.write_text(content)
                plan = classify_ui(root, ['tools/atlas_meta_integrity.py'], candidate_sha=SHA, base_sha=BASE)
                self.assertEqual(plan['status'], 'REVIEW_REQUIRED')

    def test_doctor_capability_ci_scope_uses_real_ui_planner_without_full(self):
        # Regression: the previous exact-SHA PR plan was REVIEW_REQUIRED and FULL
        # for changes confined to Doctor diagnostics and their source tests.
        from tools.atlas_doctor_lib.ci_orchestrator import select_workflows

        paths = [
            "tools/atlas_doctor.py",
            "tools/atlas_doctor_lib/capability_matrix.py",
            "tools/atlas_doctor_lib/capability_evidence.py",
            "tools/atlas_doctor_lib/agent_protocol.py",
            "tools/atlas_doctor_lib/doctor_ui_ci.py",
            "tests/test_atlas_doctor_capabilities.py",
            "tests/test_atlas_doctor_capability_evidence.py",
            "tests/test_atlas_doctor_agent_protocol.py",
            "tests/test_doctor_ci_orchestrator.py",
            "tests/test_doctor_ui_ci.py",
            ".ai/context_index.json",
            "docs/audit-remediation/2026-10-17/07-doctor-capability-ci-evidence.md",
        ]
        ui = self.plan(*paths)
        self.assertEqual(ui["status"], "UI_REQUIRED")
        self.assertEqual(ui["selected_scenarios"], ["validator-smoke"])
        self.assertEqual(ui["uncertainty"], [])
        routed = select_workflows(
            paths, event="pull_request", phase_route={"route": "FULL"}, ui_plan=ui,
        )
        self.assertTrue(routed["tooling_only"])
        self.assertFalse(routed["full"])
        self.assertFalse(routed["phase"])
        self.assertFalse(routed["specialist_fallback"])
        self.assertTrue(routed["workflows"]["doctor-ui"]["selected"])
        for extra in ("app/ui/theme.py", "tools/atlas_doctor_lib/runtime_observation.py"):
            with self.subTest(extra=extra):
                changed = [*paths, extra]
                impacted_ui = self.plan(*changed)
                mixed = select_workflows(
                    changed, event="pull_request", phase_route={"route": "FULL"},
                    ui_plan=impacted_ui,
                )
                self.assertTrue(mixed["full"])
                self.assertTrue(mixed["phase"])

    def test_doctor_diagnostic_import_boundary_stays_fail_closed(self):
        for path in (
            "tools/atlas_doctor_lib/capability_matrix.py",
            "tools/atlas_doctor_lib/capability_evidence.py",
            "tools/atlas_doctor_lib/agent_protocol.py",
        ):
            for source in (
                "from app.ui import theme\n",
                "from PySide6 import QtWidgets\n",
                "__import__(\"app.ui.theme\")\n",
                "import importlib\nimportlib.import_module(\"unknown\")\n",
            ):
                with self.subTest(path=path, source=source):
                    with tempfile.TemporaryDirectory() as folder:
                        root = Path(folder)
                        target = root / path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_text(source)
                        plan = classify_ui(
                            root, [path], candidate_sha=SHA, base_sha=BASE,
                        )
                        self.assertEqual(plan["status"], "REVIEW_REQUIRED")

    def test_both_real_renderers_selected_for_shared_view(self):
        plan = self.plan("app/modules/encyclopedia/views/shared_manual_guide_view.py")
        self.assertEqual(set(plan["selected_scenarios"]), set(ALL_GUIDES))
        self.assertEqual(plan["status"], "UI_REQUIRED")

    def test_quest_bridge_theme_and_canonical_data_have_explicit_consumers(self):
        cases = {
            "app/modules/encyclopedia/services/link_service.py": {"guide-quests"},
            "app/modules/encyclopedia/views/encyclopedia_page.py": set(ALL_GUIDES),
            "app/ui/theme.py": set(ALL_GUIDES),
            "data/routes/guide_ultime_manual/chapter_01.json": {"guides-success", "guide-quests"},
            "data/encyclopedia/guides/dofus_sylvestre.json": {"guides-lanyel", "guide-quests"},
        }
        for path, selected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(set(self.plan(path)["selected_scenarios"]), selected)

    def test_validator_change_selects_self_tests_and_one_smoke(self):
        for path in ("tools/atlas_doctor_lib/doctor_ui_qt.py", "tools/atlas_doctor_lib/doctor_ui_ci.py",
                     "tests/test_doctor_ui_qt.py", ".github/workflows/doctor-ui.yml"):
            self.assertEqual(self.plan(path)["selected_scenarios"], ["validator-smoke"])

    def test_independent_tool_cannot_silently_introduce_a_qt_dependency(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "tools/atlas_json_raw.py"
            path.parent.mkdir()
            path.write_text("from PySide6.QtWidgets import QWidget\n")
            plan = classify_ui(root, ["tools/atlas_json_raw.py"], candidate_sha=SHA, base_sha=BASE)
            self.assertEqual(plan["status"], "REVIEW_REQUIRED")

    def test_mixed_changes_union_without_duplicate_captures(self):
        plan = self.plan("docs/test.md", "app/ui/theme.py",
                         "app/modules/encyclopedia/services/link_service.py")
        self.assertEqual(len(plan["selected_scenarios"]), 3)
        self.assertEqual(set(plan["selected_scenarios"]), set(ALL_GUIDES))

    def test_unknown_deleted_renamed_invalid_and_unverified_cannot_skip(self):
        for plan in (self.plan("unmapped.xyz"), self.plan("../escape.py"),
                     self.plan("docs/a.md", deleted=["app/ui/deleted.py"]),
                     self.plan("docs/a.md", diff_valid=False)):
            self.assertEqual(plan["status"], "REVIEW_REQUIRED")
            self.assertEqual(campaign_verdict(plan, [], SHA)["status"], "BLOCKED")

    def test_transitive_dependency_and_relative_imports_reach_actual_ui_consumer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = {
                "app/core/model.py": "def state(): return 1\n",
                "app/core/bridge.py": "from .model import state\n",
                "app/ui/theme.py": "from app.core.bridge import state\n",
            }
            for path, content in files.items():
                file = root / path
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            plan = classify_ui(root, ["app/core/model.py"], candidate_sha=SHA, base_sha=BASE)
            self.assertEqual(set(plan["selected_scenarios"]), set(ALL_GUIDES))
            self.assertIn("AST import dependency", plan["reason_per_scenario"]["guide-quests"][0])
            self.assertEqual(dependency_map(root)[1], [])

    def test_no_qt_or_application_imported_by_planner(self):
        code = ("import sys; from tools.atlas_doctor_lib import doctor_ui_ci; "
                "assert not any(x.startswith(('PySide6','app.')) for x in sys.modules)")
        completed = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)



class DoctorUiRegressionWatchTests(unittest.TestCase):
    def make_session(self, root: Path, sha: str, *, scenario_ids=None,
                     status="PASS", failed_id=None, missing_capture=False):
        import hashlib

        folder = root / sha[:4]
        folder.mkdir(parents=True, exist_ok=True)
        ids = list(scenario_ids if scenario_ids is not None else dict.fromkeys(
            ident for controls in REGRESSION_REQUIREMENTS.values() for ident in controls
        ))
        rows = [{"assertion_id": ident, "scenario_id": ident.split("/")[0],
                 "assertion_status": "FAIL" if ident == failed_id else "PASS",
                 "evidence_ids": [] if missing_capture and ident == ids[0] else ["capture.png"]}
                for ident in ids]
        report = {
            "candidate_sha": sha, "dirty": False, "status": status,
            "tests_executed": True, "selected_scenarios": sorted({i.split("/")[0] for i in ids}),
            "assertions": rows, "required_assertions": ids,
            "required_evidence": ["capture.png"],
        }
        import struct
        import zlib

        files = {"ui_verdict.json": json.dumps(report), "actions.json": "[]",
                 "request.json": "{}", "worker.log": "log", "capture.png": ""}
        for name, content in files.items():
            if name != "capture.png":
                (folder / name).write_text(content, encoding="utf-8")

        def png_chunk(kind, data):
            signed = kind + data
            return (struct.pack(">I", len(data)) + signed
                    + struct.pack(">I", zlib.crc32(signed) & 0xFFFFFFFF))

        png = (bytes.fromhex("89504e470d0a1a0a")
               + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
               + png_chunk(b"IDAT", zlib.compress(bytes.fromhex("00000000ff")))
               + png_chunk(b"IEND", b""))
        (folder / "capture.png").write_bytes(png)
        manifest = {"candidate_sha": sha, "dirty": False,
                    "artifacts": {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                                  for name in files}}
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return folder

    def test_smoke_success_and_no_baseline_do_not_certify_four_journeys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            smoke = self.make_session(root, SHA, scenario_ids=["validator-smoke/open"])
            report = watch_ui_regressions(
                baseline_sha=BASE, candidate_sha=SHA,
                baseline_sessions=[], candidate_sessions=[smoke],
            )
            self.assertEqual(report["status"], "NOT_COVERED")
            self.assertEqual(len(report["controls"]), 4)
            self.assertTrue(all(row["status"] == "NOT_COVERED"
                                for row in report["controls"].values()))
            self.assertFalse(report["phase_certified"])
            self.assertFalse(report["release_certified"])
            self.assertFalse(report["tests_executed"])

    def test_exact_sha_evidence_compares_all_four_controls_and_detects_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = self.make_session(root, BASE)
            candidate = self.make_session(root, SHA)
            kw = {"baseline_sha": BASE, "candidate_sha": SHA,
                  "baseline_sessions": [baseline], "candidate_sessions": [candidate]}
            good = watch_ui_regressions(**kw)
            self.assertEqual(good["status"], "NO_REGRESSION_OBSERVED")
            self.assertTrue(all(row["status"] == "NO_REGRESSION_OBSERVED"
                                for row in good["controls"].values()))

            failed = "achievement-detail/click-opens-detail"
            candidate = self.make_session(root, SHA, status="FAIL", failed_id=failed)
            bad = watch_ui_regressions(**kw)
            self.assertEqual(bad["status"], "REGRESSION_REVIEW")
            self.assertEqual(bad["controls"]["achievement-click"]["status"], "REGRESSION_REVIEW")
            self.assertNotEqual(bad["controls"]["achievement-first-open"]["status"], "REGRESSION_REVIEW")

            # Report claims PASS despite an observed failed mandatory assertion:
            # hash consistency alone must not launder the false PASS.
            self.make_session(root, SHA, status="PASS", failed_id=failed)
            forged = watch_ui_regressions(**kw)
            self.assertEqual(forged["status"], "BLOCKED")
            self.assertIn("INCONSISTENT_PASS_REPORT", " ".join(forged["errors"]))

            self.assertEqual(watch_ui_regressions(**{**kw, "baseline_sha": SHA})["status"], "BLOCKED")

    def test_no_cross_sha_stale_or_missing_png_for_regression_watch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = self.make_session(root, BASE)
            candidate = self.make_session(root, SHA)
            kw = {"baseline_sha": BASE, "candidate_sha": SHA,
                  "baseline_sessions": [baseline], "candidate_sessions": [candidate]}
            (candidate / "capture.png").unlink()
            self.assertEqual(watch_ui_regressions(**kw)["status"], "BLOCKED")
            self.make_session(root, SHA, missing_capture=True)
            self.assertEqual(watch_ui_regressions(**kw)["status"], "BLOCKED")

            # Recalculate the hash of a fake image: integrity alone is not
            # evidence of a valid screenshot.
            import hashlib
            self.make_session(root, SHA)
            (candidate / "capture.png").write_bytes(b"not an image")
            manifest_path = candidate / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"]["capture.png"] = hashlib.sha256(b"not an image").hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = watch_ui_regressions(**kw)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertIn("INVALID_SCREENSHOT_PNG", " ".join(result["errors"]))

    def test_regression_watch_cli_is_fail_closed_until_evidence_exists(self):
        from tools.atlas_doctor_lib.doctor_ui_ci import main
        import contextlib
        import io

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            output = Path(tmp) / "watch.json"
            code = main(["regression-watch", "--baseline-sha", BASE,
                         "--candidate-sha", SHA, "--watch-output", str(output)])
            self.assertEqual(code, 2)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "NOT_COVERED")



class DoctorUiVerdictTests(unittest.TestCase):
    def test_omitted_or_duplicate_assertion_never_passes(self):
        passed = {"assertion_id": "a", "assertion_status": "PASS"}
        self.assertEqual(verdict([passed], ["a"]), "PASS")
        self.assertEqual(verdict([passed], ["a", "b"]), "BLOCKED")
        self.assertEqual(verdict([passed, passed], ["a"]), "REVIEW")
        for status in ("FAIL", "BLOCKED", "REVIEW", "NOT_COVERED"):
            self.assertNotEqual(verdict([{**passed, "assertion_status": status}], ["a"]), "PASS")

    def test_required_windows_scenario_skipped_wrong_sha_dirty_or_capture_only_blocks(self):
        plan = classify_ui(ROOT, ["app/modules/encyclopedia/services/link_service.py"],
                           candidate_sha=SHA, base_sha=BASE)
        required = required_assertions(["guide-quests"])
        report = {"candidate_sha": SHA, "dirty": False, "status": "PASS", "tests_executed": True,
                  "selected_scenarios": ["guide-quests"], "required_assertions": required,
                  "assertions": [{"assertion_id": key, "scenario_id": key.split('/')[0], "assertion_status": "PASS"} for key in required]}
        self.assertEqual(campaign_verdict(plan, [report], SHA)["status"], "PASS")
        self.assertEqual(campaign_verdict(plan, [], SHA)["status"], "BLOCKED")
        for change in ({"candidate_sha": BASE}, {"dirty": True}, {"status": "FAIL"},
                       {"tests_executed": False}, {"assertions": []}):
            self.assertEqual(campaign_verdict(plan, [{**report, **change}], SHA)["status"], "BLOCKED")
        self.assertEqual(campaign_verdict(plan, [report, report], SHA)["status"], "BLOCKED")

    def test_missing_or_tampered_capture_artifact_cannot_be_reused(self):
        import hashlib

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            files = {"ui_verdict.json": json.dumps({"required_evidence": ["capture.png"]}),
                     "request.json": "{}", "actions.json": "[]", "worker.log": "log", "capture.png": "pixels"}
            for name, content in files.items():
                (root / name).write_text(content)
            manifest = {"candidate_sha": SHA, "dirty": False,
                        "artifacts": {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in files}}
            (root / "manifest.json").write_text(json.dumps(manifest))
            read_evidence(root, SHA)
            (root / "capture.png").write_text("modified")
            with self.assertRaisesRegex(ValueError, "modified"):
                read_evidence(root, SHA)
            (root / "capture.png").unlink()
            with self.assertRaises(OSError):
                read_evidence(root, SHA)

    def test_cli_writes_blocked_report_even_if_selection_artifact_is_missing(self):
        import contextlib
        import io
        from tools.atlas_doctor_lib.doctor_ui_ci import main
        for contents in (None, '[1]', 'not JSON'):
            with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
                plan = Path(folder) / 'selection.json'
                if contents is not None:
                    plan.write_text(contents)
                self.assertEqual(main(['verdict', '--candidate-sha', SHA, '--plan', str(plan),
                                       '--evidence-root', str(Path(folder) / 'ui')]), 1)
                report = json.loads(plan.with_name('ui_campaign_verdict.json').read_text())
                self.assertEqual(report['status'], 'BLOCKED')
                self.assertFalse(report['tests_executed'])
                self.assertFalse(report['phase_certified'])
                self.assertEqual(report['candidate_sha'], SHA)

    def test_failed_ui_job_still_executes_evidence_verdict(self):
        text = (ROOT / '.github/workflows/doctor-ui.yml').read_text(encoding='utf-8')
        block = text.split('      - name: Verify selection, assertions, real PNG and hashes at candidate SHA', 1)[1].split('      - uses:', 1)[0]
        self.assertIn('if: always()', block)
        self.assertIn('doctor_ui_ci verdict', block)

    def test_workflow_is_impact_selected_and_preserves_existing_gates(self):
        text = (ROOT / ".github/workflows/doctor-ui.yml").read_text(encoding="utf-8")
        self.assertIn("needs.plan.outputs.run_ui == 'true'", text)
        self.assertIn("tools.atlas_doctor_lib.doctor_ui_ci plan", text)
        self.assertIn("tools.atlas_doctor_lib.doctor_ui_ci verdict", text)
        self.assertIn("if: always()", text)
        self.assertIn("lfs: false", text)
        self.assertNotIn("push:", text)
        self.assertNotIn("continue-on-error", text)
        self.assertNotIn("atlas_integrity", text)


if __name__ == "__main__":
    unittest.main()
