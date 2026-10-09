from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.function_inventory import compare_source_functions


class FocusedFunctionInventoryTests(unittest.TestCase):
    SHA = "a" * 40

    def test_source_functions_against_real_entered_symbols_not_imports(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "app/guide.py"
            path.parent.mkdir()
            path.write_text(
                "class Guide:\n"
                "    def enter(self): return 1\n"
                "    def not_entered(self): return 2\n"
                "def prepare(): pass\n",
                encoding="utf-8",
            )
            trace = {
                "kind": "doctor_runtime_observation", "candidate_sha": self.SHA,
                "worktree_clean": True, "truncated": False,
                "events": [
                    {"type": "python_symbol_call", "source": "app/main.py",
                     "target": "app/guide.py", "callee_symbol": "Guide.enter",
                     "confidence": "OBSERVED_CALL_ENTRY"},
                    {"type": "qt_signal_connect_returned", "source": "app/main.py",
                     "target": "app/guide.py", "callee_symbol": "Guide.not_entered"},
                ],
            }
            report = compare_source_functions(root, ["app/guide.py"],
                                              trace, expected_sha=self.SHA)
            self.assertEqual(report["defined_total"], 3)
            self.assertEqual(report["entered_total"], 1)
            self.assertEqual(report["not_observed_total"], 2)
            self.assertFalse(report["dead_code_proven"])
            self.assertFalse(report["safe_to_delete"])
            trace["worktree_clean"] = False
            invalid = compare_source_functions(root, ["app/guide.py"],
                                               trace, expected_sha=self.SHA)
            self.assertEqual(invalid["status"], "UNAVAILABLE")

    def test_invalid_paths_never_become_source_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            result = compare_source_functions(
                Path(folder), ["../outside.py"],
                {"kind": "doctor_runtime_observation",
                 "candidate_sha": self.SHA,
                 "worktree_clean": True,
                 "truncated": False, "events": []},
                expected_sha=self.SHA)
            self.assertEqual(result["status"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
