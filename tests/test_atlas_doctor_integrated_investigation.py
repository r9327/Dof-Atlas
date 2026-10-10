from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.integrated_investigation import investigate_files


class IntegratedDoctorInvestigationTests(unittest.TestCase):
    def test_no_graph_still_reports_current_ast_without_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "app/core/catalog.py"
            path.parent.mkdir(parents=True)
            path.write_text("def get(): return 42\n", encoding="utf-8")
            with patch("tools.atlas_doctor_lib.architecture.graph_status",
                       return_value={"status": "STALE", "reason": "Old graph"}):
                result = investigate_files(root, ["app/core/catalog.py"])
            self.assertEqual(result["status"], "PARTIAL_REVIEW")
            self.assertEqual(result["paths"], ["app/core/catalog.py"])
            self.assertEqual(result["graphify"]["status"], "STALE")
            self.assertFalse(result["safe_to_delete"])
            self.assertFalse(result["tests_executed"])
            self.assertFalse(result["graph_rebuilt"])
            self.assertFalse(result["final_certification"])

    def test_canonical_planning_is_advisory_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "app/a.py"
            path.parent.mkdir()
            path.write_text("pass\n", encoding="utf-8")
            plan = {"status": "READY", "execution_tests": ["tests.test_a"],
                    "required_groups": ["AST_FOCUSED"],
                    "integrity_mode": "CRITICAL", "scopes": ["app"]}
            with patch("tools.atlas_doctor_lib.architecture.graph_status",
                       return_value={"status": "MISSING"}), \
                 patch("tools.agent.plan_payload", return_value=plan):
                report = investigate_files(root, ["app/a.py"])
            self.assertEqual(report["canonical_test_intelligence"]["recommended_tests"],
                             ["tests.test_a"])
            self.assertEqual(report["canonical_test_intelligence"]["integrity_mode"],
                             "CRITICAL")
            self.assertFalse(report["canonical_test_intelligence"]["full_suite_waived"])
            self.assertFalse(report["canonical_test_intelligence"]["tests_executed"])

    def test_requested_interactive_view_uses_exact_sha_graph_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / "app/guide.py"
            target.parent.mkdir()
            target.write_text("def page(): pass\n", encoding="utf-8")
            with patch("tools.atlas_doctor_lib.architecture.graph_status",
                       return_value={"status": "STALE"}):
                report = investigate_files(root, ["app/guide.py"], graph_ui=True)
            self.assertEqual(report["graphify_interactive_view"]["status"], "UNAVAILABLE")
            self.assertFalse(report["graphify_interactive_view"]["graph_rebuilt"])
            self.assertFalse(report["tests_executed"])

    def test_bad_trace_cannot_inject_positive_runtime_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "app/entry.py"
            path.parent.mkdir(parents=True)
            path.write_text("pass\n", encoding="utf-8")
            runtime = root / ".ai/runtime"
            runtime.mkdir(parents=True)
            trace = runtime / "stale.json"
            trace.write_text(json.dumps({
                "kind": "doctor_runtime_observation", "candidate_sha": "b" * 40,
                "worktree_clean": True, "truncated": False,
                "events": [{"type": "python_symbol_call", "source": "app/entry.py",
                            "target": "app/entry.py", "callee_symbol": "run",
                            "confidence": "OBSERVED_CALL_ENTRY"}],
            }), encoding="utf-8")
            with patch("tools.atlas_doctor_lib.architecture.graph_status",
                       return_value={"status": "STALE"}):
                report = investigate_files(root, ["app/entry.py"], trace_path=trace)
            self.assertEqual(report["runtime"]["status"], "BLOCKED_STALE_OR_INCOMPLETE_TRACE")
            self.assertFalse(report["final_certification"])


if __name__ == "__main__":
    unittest.main()
