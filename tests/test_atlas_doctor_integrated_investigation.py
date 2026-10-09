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
