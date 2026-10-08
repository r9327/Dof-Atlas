from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.atlas_doctor_lib.graph_audit import audit_current_graph, inspect_graph


def fixture():
    nodes = [
        {"id": "a", "label": "caller", "source_file": "app/views/page.py", "community": 1},
        {"id": "b", "label": "service", "source_file": "app/core/service.py", "community": 2},
        {"id": "c", "label": "entry", "source_file": "app/ui/__init__.py", "community": 3},
        {"id": "d", "label": "orphan", "source_file": "app/unused.py", "community": 4},
        {"id": "t", "label": "helper", "source_file": "tools/helper.py", "community": 5},
    ]
    links = [
        {"source": "a", "target": "b", "relation": "calls", "confidence": "INFERRED"},
        {"source": "a", "target": "t", "relation": "imports_from", "confidence": "EXTRACTED", "_origin": "ast"},
    ]
    return {"nodes": nodes, "links": links, "built_at_commit": "x" * 40}


class DoctorGraphAuditTests(unittest.TestCase):
    def test_graph_candidates_never_prove_dead_code_or_merge(self):
        report = inspect_graph(fixture())
        self.assertEqual(report["metrics"]["raw_community_count"], 5)
        self.assertEqual(report["metrics"]["raw_communities_lt3_nodes"], 5)
        orphan = {x["file"]: x for x in report["orphan_nodes"]}
        self.assertEqual(orphan["app/ui/__init__.py"]["classification"], "BOUNDARY_OR_EXTERNAL_ENTRY_CANDIDATE")
        self.assertFalse(orphan["app/unused.py"]["proof_of_dead_code"])
        self.assertEqual(report["metrics"]["inferred_edges"], 1)
        self.assertEqual(report["metrics"]["confirmed_runtime_to_tools_imports"], 0)
        self.assertFalse(report["unconfirmed_import_candidates"][0]["blocking"])

    def test_source_confirmed_import_is_a_real_blocker(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "app/views/page.py"
            source.parent.mkdir(parents=True)
            source.write_text("from tools.helper import something\n", encoding="utf-8")
            report = inspect_graph(fixture(), root=root)
            self.assertEqual(report["status"], "FAIL")
            self.assertEqual(report["blocking_findings"][0]["confidence"], "CURRENT_SOURCE_IMPORT")
            self.assertEqual(report["blocking_findings"][0]["source"], "app/views/page.py")
            source.write_text("from app.core import service\n", encoding="utf-8")
            report = inspect_graph(fixture(), root=root)
            self.assertFalse(report["blocking_findings"])
            self.assertEqual(report["status"], "REVIEW")

    def test_only_extracted_ast_import_can_be_blocking(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            f = root / "app/views/page.py"
            f.parent.mkdir(parents=True)
            f.write_text("from tools.helper import something\n", encoding="utf-8")
            graph = fixture()
            graph["links"][1]["confidence"] = "INFERRED"
            self.assertEqual(inspect_graph(graph, root=root)["blocking_findings"], [])

    def test_bad_edges_and_duplicate_nodes_are_rejected(self):
        graph = fixture()
        graph["links"][0]["target"] = "missing"
        with self.assertRaises(ValueError):
            inspect_graph(graph)
        graph = fixture()
        graph["nodes"].append(dict(graph["nodes"][0]))
        with self.assertRaises(ValueError):
            inspect_graph(graph)

    def test_stale_graph_blocks_without_reading_source(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("tools.atlas_doctor_lib.graph_audit.graph_status", return_value={
                "status": "STALE", "reason": "not same SHA",
            }):
                report = audit_current_graph(Path(d))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("rebuild", report["rebuild_command"])

    def test_hub_and_community_bridge_are_advisory(self):
        graph = {"nodes": [], "links": []}
        for i in range(23):
            graph["nodes"].append({"id": i, "source_file": "app/core/hub.py" if i == 0 else f"app/views/v{i}.py",
                                   "community": 0 if i == 0 else 1})
            if i:
                graph["links"].append({"source": i, "target": 0, "relation": "imports", "confidence": "EXTRACTED"})
        report = inspect_graph(graph)
        self.assertTrue(report["high_fanout_files"])
        self.assertTrue(report["cross_community_bridges"])
        self.assertEqual(report["status"], "REVIEW")

if __name__ == "__main__":
    unittest.main()
