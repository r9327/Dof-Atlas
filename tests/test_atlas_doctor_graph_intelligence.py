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

    def test_source_cycle_survives_one_stale_edge_inside_graph_component(self):
        graph = fixture()
        graph["nodes"].append({
            "id": "d", "source_file": "app/core/d.py",
            "file_type": "code", "label": "Delta", "community": 3, "_origin": "ast",
        })
        graph["links"].extend([
            {"source": "b", "target": "d", "relation": "imports",
             "confidence": "EXTRACTED", "_origin": "ast"},
            {"source": "d", "target": "a", "relation": "imports",
             "confidence": "EXTRACTED", "_origin": "ast"},
        ])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            p = root / "app/core"
            p.mkdir(parents=True)
            (p / "a.py").write_text("from app.core import b\n", encoding="utf-8")
            (p / "b.py").write_text("from app.core import a, d\n", encoding="utf-8")
            (p / "d.py").write_text("pass\n", encoding="utf-8")
            report = inspect_import_cycles(graph, root=root)
        self.assertEqual(report["suspected_cycles"], 1)
        self.assertEqual(report["source_confirmed_cycles"], 1)
        self.assertEqual(report["cycles"][0]["source_confirmed_subcycles"], 1)
        self.assertEqual(report["cycles"][0]["confirmed_cycle_samples"], [["app/core/a.py", "app/core/b.py"]])

    def test_relative_import_cycles_require_valid_package_depth(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            directory = root / "app/core"
            directory.mkdir(parents=True)
            (directory / "a.py").write_text("from . import b\n", encoding="utf-8")
            (directory / "b.py").write_text("from .a import something\n", encoding="utf-8")
            report = inspect_import_cycles(fixture(), root=root)
            self.assertEqual(report["source_confirmed_cycles"], 1)
            (directory / "a.py").write_text(
                "from ....app.core import b\n", encoding="utf-8")
            invalid = inspect_import_cycles(fixture(), root=root)
            self.assertEqual(invalid["source_confirmed_cycles"], 0)
            self.assertEqual(invalid["suspected_cycles"], 1)

    def test_graph_comparison_checks_cycles_past_display_limit(self):
        def many(n, sha):
            nodes, links = [], []
            for i in range(n):
                for letter in ("a", "b"):
                    nodes.append({"id": f"{letter}{i}", "source_file": f"app/z{i}/{letter}.py",
                                  "file_type": "code", "label": f"{letter}{i}",
                                  "_origin": "ast", "community": i})
                for a, b in (("a", "b"), ("b", "a")):
                    links.append({"source": f"{a}{i}", "target": f"{b}{i}",
                                  "relation": "imports", "confidence": "EXTRACTED", "_origin": "ast"})
            return {"nodes": nodes, "links": links, "built_at_commit": sha}
        before = many(35, "a" * 40)
        after = many(36, "b" * 40)
        report = compare_graphs(before, after)
        self.assertEqual(len(report["new_candidate_import_cycles"]), 1)
        self.assertEqual(report["new_candidate_import_cycles"][0], ["app/z35/a.py", "app/z35/b.py"])
        self.assertEqual(report["status"], "REVIEW")

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

    def test_graphify_method_labels_are_searched_without_claiming_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            path = root / "app/core"
            path.mkdir(parents=True)
            (path / "owner.py").write_text("def publish_status(): pass\n", encoding="utf-8")
            (path / "user.py").write_text("obj.publish_status()\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            scan = inspect_consumers(root, [{"file": "app/core/owner.py", "symbol": ".publish_status()"}])
            self.assertEqual(len(scan["reviewed"]), 1)
            item = scan["reviewed"][0]
            self.assertEqual(item["normalized_symbol"], "publish_status")
            self.assertEqual(item["classification"], "POSSIBLE_EXTERNAL_CONSUMER")
            self.assertFalse(item["confirmed_dead_code"])

    def test_same_file_callback_and_ctypes_reference_are_not_unused_leads(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            owner = root / "app/input/hotkeys.py"
            owner.parent.mkdir(parents=True)
            owner.write_text(
                "import ctypes\n"
                "class KBDLLHOOKSTRUCT(ctypes.Structure):\n"
                "    _fields_ = [('key', ctypes.c_int)]\n"
                "class Hooks:\n"
                "    def __init__(self):\n"
                "        self.handler = self._handle_mouse_click\n"
                "    def _handle_mouse_click(self, event):\n"
                "        return event\n"
                "    def consume(self, raw):\n"
                "        return ctypes.POINTER(KBDLLHOOKSTRUCT)\n",
                encoding="utf-8",
            )
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            report = inspect_consumers(root, [
                {"file": "app/input/hotkeys.py", "symbol": "._handle_mouse_click()"},
                {"file": "app/input/hotkeys.py", "symbol": "KBDLLHOOKSTRUCT"},
            ])
            self.assertEqual(
                [row["classification"] for row in report["reviewed"]],
                ["LOCAL_SOURCE_REFERENCE_REVIEW", "LOCAL_SOURCE_REFERENCE_REVIEW"],
            )
            for row in report["reviewed"]:
                self.assertTrue(row["local_references"])
                self.assertFalse(row["confirmed_dead_code"])
            plan = remediation_plan({}, {"cycles": []}, {"candidates": []},
                                    source_review=report)
            self.assertEqual(plan["actionability"]["confirmed_fix_candidates"], 0)
            self.assertEqual(len(plan["actionability"]["local_source_used_symbols"]), 2)
            self.assertFalse(any(t["kind"] == "UNPROVEN_UNUSED_SYMBOL"
                                 for t in plan["tasks"]))

    def test_doctor_plan_separates_proven_fixes_from_advisory_candidates(self):
        plan = remediation_plan(
            {"blocking_findings": [{"source": "app/core/a.py", "target": "tools/b.py"}],
             "high_fanout_files": [{"file": "app/core/a.py", "runtime_neighbor_files": 30}]},
            {"cycles": [{"files": ["app/core/a.py", "app/core/b.py"],
                          "confidence": "CURRENT_SOURCE_IMPORT_CYCLE"}]},
            {"candidates": []},
        )
        self.assertEqual(plan["actionability"]["confirmed_fix_candidates"], 1)
        self.assertEqual(plan["actionability"]["investigation_candidates"], 2)
        self.assertEqual(plan["tasks"][0]["decision"], "FIX_CONFIRMED_CONTRACT_VIOLATION")
        self.assertEqual(plan["tasks"][1]["decision"], "INVESTIGATE_NO_CODE_CHANGE_YET")
        self.assertIn("TYPE_CHECKING", plan["tasks"][1]["next_proof"])
        self.assertTrue(all(not task["code_change_authorized"] for task in plan["tasks"]))

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
