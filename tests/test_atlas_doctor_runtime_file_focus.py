from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.runtime_file_focus import runtime_file_focus
from tools.atlas_doctor_lib.graph_intelligence import remediation_plan
from tools.atlas_doctor_lib.graph_audit import inspect_graph


def fixture():
    shared = "app/constants.py"
    guide = "app/modules/encyclopedia/views/guides_view.py"
    callers = [f"app/pages/caller_{i}.py" for i in range(14)]
    deps = [f"app/modules/encyclopedia/services/dependency_{i}.py" for i in range(12)]
    paths = ([shared, guide, *callers, *deps, "app/core/orphan.py",
              "app/ui/__init__.py", "tests/test_sample.py", "tools/graphify.py"])
    nodes = [{"id": f"n{i}", "source_file": path, "file_type": "code",
              "community": i % 3} for i, path in enumerate(paths)]
    idx = {node["source_file"]: node["id"] for node in nodes}
    edges = []
    for caller in callers:
        edges.append({"source": idx[caller], "target": idx[shared],
                      "relation": "imports", "confidence": "EXTRACTED", "_origin": "ast"})
    for dependency in deps:
        edges.append({"source": idx[guide], "target": idx[dependency],
                      "relation": "imports_from", "confidence": "EXTRACTED", "_origin": "ast"})
    # App -> test, inferred, non-import relationships must not count.
    edges.extend([
        {"source": idx[guide], "target": idx[deps[0]],
         "relation": "imports", "confidence": "INFERRED", "_origin": "ast"},
        {"source": idx[guide], "target": idx[shared],
         "relation": "calls", "confidence": "EXTRACTED", "_origin": "ast"},
        {"source": idx["tools/graphify.py"], "target": idx[guide],
         "relation": "imports", "confidence": "EXTRACTED", "_origin": "ast"},
        {"source": idx[guide], "target": idx["tests/test_sample.py"],
         "relation": "imports", "confidence": "EXTRACTED", "_origin": "ast"},
        # Duplicate symbol-level import: file-level graph must deduplicate.
        dict(edges[0]),
    ])
    return {"nodes": nodes, "links": edges, "built_at_commit": "a" * 40}


class RuntimeFileFocusTests(unittest.TestCase):
    def test_projection_counts_only_extracted_application_imports(self):
        focus = runtime_file_focus(fixture())
        self.assertEqual(focus["file_nodes"], 30)
        self.assertEqual(focus["confirmed_ast_import_file_pairs"], 26)
        self.assertEqual(len(focus["file_import_edges"]), 26)
        self.assertFalse(focus["file_import_edges_truncated"])
        self.assertEqual(focus["ignored_inferred_app_import_edges"], 1)
        self.assertEqual(focus["ignored_nonimport_app_relations"], 1)
        self.assertEqual(focus["source_sha"], "a" * 40)
        self.assertTrue(focus["cross_domain_bridges"])
        self.assertTrue(all(row["automatic_merge"] is False for row in focus["cross_domain_bridges"]))
        self.assertTrue(all(row["example_files"] for row in focus["cross_domain_bridges"]))
        self.assertTrue(focus["limits"]["projection_not_deletion"])
        self.assertTrue(focus["limits"]["graph_communities_unchanged"])
        self.assertTrue(focus["limits"]["static_coupling_not_a_cpu_ram_bottleneck"])

    def test_shared_leaf_is_not_a_bottleneck_and_outbound_view_is_review(self):
        focus = runtime_file_focus(fixture())
        self.assertEqual(focus["shared_leaf_apis"][0]["file"], "app/constants.py")
        self.assertEqual(focus["shared_leaf_apis"][0]["consumer_files"], 14)
        hotspot = next(r for r in focus["hotspots"] if r["file"].endswith("/guides_view.py"))
        self.assertEqual(hotspot["dependency_files"], 12)
        self.assertFalse(hotspot["proof_of_runtime_bottleneck"])
        self.assertEqual(hotspot["domain"], "app/modules/encyclopedia/views")
        self.assertIn("app/core/orphan.py", {r["file"] for r in focus["isolate_candidates"]})
        self.assertNotIn("app/ui/__init__.py", {r["file"] for r in focus["isolate_candidates"]})
        self.assertGreaterEqual(focus["boundary_files_without_static_import_edges"], 1)
        self.assertGreaterEqual(focus["package_boundary_files"], 1)
        self.assertEqual(focus["files_without_static_import_edges"], 1)
        self.assertNotIn("app/constants.py", {r["file"] for r in focus["hotspots"]})
        self.assertTrue(all(not x["proof_of_dead_code"] for x in focus["isolate_candidates"]))

    def test_remediation_plan_does_not_promote_hotspot_to_code_change(self):
        focus = runtime_file_focus(fixture())
        plan = remediation_plan({}, {"cycles": []}, {"candidates": []}, runtime_focus=focus)
        self.assertEqual(plan["actionability"]["static_hotspot_count"], 1)
        hotspots = [task for task in plan["tasks"] if task["kind"] == "STATIC_HOTSPOT_REVIEW"]
        self.assertEqual(len(hotspots), 1)
        self.assertEqual(hotspots[0]["decision"], "INVESTIGATE_NO_CODE_CHANGE_YET")
        self.assertFalse(hotspots[0]["code_change_authorized"])
        self.assertTrue(plan["actionability"]["static_coupling_is_not_performance_evidence"])

    def test_current_graph_audit_exposes_projection_without_renaming_raw_graph(self):
        report = inspect_graph(fixture())
        self.assertEqual(report["metrics"]["node_count"], len(fixture()["nodes"]))
        self.assertEqual(report["runtime_file_focus"]["file_nodes"], 30)
        self.assertEqual(report["runtime_file_focus"]["confirmed_ast_import_file_pairs"], 26)


if __name__ == "__main__":
    unittest.main()
