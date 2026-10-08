from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.deep_intelligence import (
    scan_sources, graph_reachability, architectural_guardrails, inspect_code,
)


class DeepIntelligenceTests(unittest.TestCase):
    def test_exact_ast_duplicates_json_and_silent_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in {
                "app/a.py": "def first():\n    return 123\ntry:\n    x = 1\nexcept Exception:\n    pass\n",
                "app/b.py": "def second():\n    return 123\nthing = 'data/catalog.json'\n",
            }.items():
                p = root / name
                p.parent.mkdir(exist_ok=True)
                p.write_text(content)
            report = scan_sources(root, ["app/a.py", "app/b.py"])
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["counts"]["duplicate_groups"], 1)
            self.assertEqual(report["counts"]["silent_exceptions"], 1)
            self.assertEqual(report["counts"]["literal_json_references"], 1)
            self.assertTrue(report["duplicate_bodies"][0]["review_only"])

    def test_symlink_and_traversal_are_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(scan_sources(root, ["../out.py"])["status"], "BLOCKED")

    def test_reachability_labels_unobserved_not_dead(self):
        graph = {"nodes": [
            {"id": "a", "source_file": "main.py"},
            {"id": "b", "source_file": "app/b.py"},
            {"id": "c", "source_file": "app/c.py"},
        ], "links": [
            {"source": "a", "target": "b", "relation": "imports",
             "confidence": "EXTRACTED", "_origin": "ast"},
        ]}
        report = graph_reachability(graph, ["main.py", "missing.py"])
        self.assertEqual(report["unreached_candidates"], ["app/c.py"])
        self.assertFalse(report["proof_of_dead_code"])
        self.assertEqual(report["status"], "REVIEW")

    def test_old_architecture_debt_is_separate(self):
        g = {"nodes": [
            {"id": "a", "source_file": "app/a.py"},
            {"id": "b", "source_file": "tools/b.py"},
        ], "links": [
            {"source": "a", "target": "b", "relation": "imports",
             "confidence": "EXTRACTED"},
        ]}
        self.assertEqual(architectural_guardrails(g, g)["historical_candidates"], 1)
        self.assertEqual(architectural_guardrails(g, g)["new_candidate_violations"], [])
        self.assertEqual(architectural_guardrails(g)["status"], "REVIEW")

    def test_old_debt_does_not_block_when_exact_baseline_contains_it(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").write_text("pass\n")
            graph = {"nodes": [{"id": "a", "source_file": "main.py"},
                               {"id": "b", "source_file": "app/x.py"},
                               {"id": "c", "source_file": "tools/y.py"}],
                     "links": [{"source": "b", "target": "c", "relation": "imports",
                                "confidence": "EXTRACTED", "_origin": "ast"}]}
            baseline = root / "before.json"
            baseline.write_text(json.dumps(graph))
            evidence = {"status": "PASS", "graph": str(baseline)}
            confirmed = {"blocking_findings": [{"source": "app/x.py", "target": "tools/y.py"}]}
            with patch("tools.atlas_doctor_lib.architecture.graph_status", return_value=evidence), \
                 patch("tools.atlas_doctor_lib.graph_audit.inspect_graph", return_value=confirmed):
                report = inspect_code(root, paths=["main.py"], baseline=baseline)
            self.assertEqual(report["architectural_rules"]["confirmed_blockers"], [])
            self.assertEqual(report["architectural_rules"]["historical_candidates"], 1)

    def test_missing_graph_does_not_claim_reachability(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = root / "main.py"
            p.write_text("pass\n")
            with patch("tools.atlas_doctor_lib.architecture.graph_status", return_value={"status": "MISSING"}):
                report = inspect_code(root, paths=["main.py"])
            self.assertEqual(report["status"], "REVIEW")
            self.assertEqual(report["reachability"]["status"], "UNAVAILABLE")
            self.assertFalse(report["tests_executed"])


if __name__ == "__main__":
    unittest.main()
