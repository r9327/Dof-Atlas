from __future__ import annotations

import copy
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.graph_intelligence import (
    inspect_import_cycles, analyze_community_boundaries, inspect_consumers,
    compare_graphs, correlate_performance, remediation_plan,
)


def fixture(sha="a" * 40):
    return {
        "nodes": [
            {"id": "a", "source_file": "app/core/a.py", "file_type": "code",
             "label": "Alpha", "community": 0, "_origin": "ast"},
            {"id": "b", "source_file": "app/core/b.py", "file_type": "code",
             "label": "Beta", "community": 1, "_origin": "ast"},
            {"id": "c", "source_file": "app/core/orphan.py", "file_type": "code",
             "label": "Orphan", "community": 2, "_origin": "ast"},
        ],
        "links": [
            {"source": "a", "target": "b", "relation": "imports_from",
             "confidence": "EXTRACTED", "_origin": "ast"},
            {"source": "b", "target": "a", "relation": "imports_from",
             "confidence": "EXTRACTED", "_origin": "ast"},
        ],
        "built_at_commit": sha,
    }


class GraphIntelligenceTests(unittest.TestCase):
    def test_directed_extracted_import_cycles_only(self):
        self.assertEqual(inspect_import_cycles(fixture())["suspected_cycles"], 1)
        g = fixture()
        g["links"][1]["confidence"] = "INFERRED"
        self.assertEqual(inspect_import_cycles(g)["suspected_cycles"], 0)

    def test_current_sources_confirm_cycle_or_reduce_to_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "app/core"
            path.mkdir(parents=True)
            (path / "a.py").write_text("from app.core import b\n", encoding="utf-8")
            (path / "b.py").write_text("from app.core import a\n", encoding="utf-8")
            report = inspect_import_cycles(fixture(), root)
            self.assertEqual(report["source_confirmed_cycles"], 1)
            self.assertFalse(report["cycles"][0]["blocking"])
            plan = remediation_plan({}, report, {"candidates": []})
            self.assertEqual(plan["tasks"][0]["priority"], "P1")
            (path / "b.py").write_text("print('no import')\n", encoding="utf-8")
            self.assertEqual(inspect_import_cycles(fixture(), root)["source_confirmed_cycles"], 0)

    def test_baseline_diff_ignores_arbitrary_community_numbers(self):
        original = fixture("a" * 40)
        now = fixture("b" * 40)
        for node in now["nodes"]:
            node["community"] = 999
        comparison = compare_graphs(original, now)
        self.assertEqual(comparison["status"], "PASS")
        self.assertEqual(comparison["new_orphan_symbols"], [])
        self.assertEqual(comparison["new_candidate_import_cycles"], [])
        self.assertTrue(comparison["limits"]["community_ids_not_comparable"])

    def test_diff_requires_two_distinct_exact_commits(self):
        with self.assertRaises(ValueError):
            compare_graphs(fixture(), fixture())
        with self.assertRaises(ValueError):
            compare_graphs(fixture("short"), fixture("b" * 40))

    def test_removed_edges_create_orphan_regression_candidate(self):
        before = fixture()
        before["links"] = [{"source": "a", "target": "c", "relation": "calls",
                            "confidence": "EXTRACTED", "_origin": "ast"}]
        after = copy.deepcopy(before)
        after["built_at_commit"] = "b" * 40
        after["links"] = []
        result = compare_graphs(before, after)
        self.assertIn({"path": "app/core/a.py", "symbol": "Alpha", "origin": "ast"}, result["new_orphan_symbols"])
        self.assertEqual(result["status"], "REVIEW")

    def test_community_review_never_forces_merges(self):
        result = analyze_community_boundaries(fixture())
        self.assertEqual(result["status"], "PASS")

    def test_tracked_consumer_sweep_never_calls_absence_dead_code(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            path = root / "app/core"
            path.mkdir(parents=True)
            (path / "unused.py").write_text("def lonely_symbol():\n    pass\n", encoding="utf-8")
            other = path / "other.py"
            other.write_text("getattr(obj, 'lonely_symbol')\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            row = [{"file": "app/core/unused.py", "symbol": "lonely_symbol"}]
            used = inspect_consumers(root, row)
            self.assertEqual(used["reviewed"][0]["classification"], "POSSIBLE_EXTERNAL_CONSUMER")
            self.assertFalse(used["reviewed"][0]["confirmed_dead_code"])
            self.assertNotIn("excerpt", used["reviewed"][0]["references"][0])
            other.write_text("pass\n", encoding="utf-8")
            none = inspect_consumers(root, row)
            self.assertEqual(none["reviewed"][0]["classification"], "NO_EXTERNAL_TEXT_MATCH_UNPROVEN")
            self.assertFalse(none["reviewed"][0]["confirmed_dead_code"])

    def test_missing_memory_metrics_are_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(correlate_performance(Path(folder), "a" * 40)["status"], "UNAVAILABLE")

    def test_plan_requires_tests_and_never_deletes(self):
        triage = {"blocking_findings": [{"source": "app/views/page.py", "target": "tools/util.py"}]}
        plan = remediation_plan(triage, {"cycles": []}, {"candidates": []})
        task = plan["tasks"][0]
        self.assertEqual(task["priority"], "P0")
        self.assertFalse(task["automatic_edit"])
        self.assertIn("Phase 8 RAM benchmark", task["require_tests"])
        self.assertTrue(plan["policy"]["no_automatic_merge"])


if __name__ == "__main__":
    unittest.main()
