from __future__ import annotations

import unittest

from tools.atlas_doctor_lib.doctor_graph_ui import compact_graph, render_html


class DoctorGraphUiTests(unittest.TestCase):
    def test_interactive_view_has_real_navigation_and_filters(self):
        graph = {"nodes": [
            {"id": "a", "label": "guide", "source_file": "app/modules/encyclopedia/view.py", "community": 5},
            {"id": "b", "label": "db", "source_file": "app/core/db.py", "community": 5},
        ], "links": [{"source": "a", "target": "b", "relation": "imports"}],
                 "built_at_commit": "a" * 40}
        audit = {"orphan_nodes": [{"file": "app/core/db.py"}]}
        data = compact_graph(graph, audit)
        html = render_html(data)
        self.assertIn('id="search"', html)
        self.assertIn('id="domain"', html)
        self.assertIn("canvas.addEventListener('wheel'", html)
        self.assertIn("Doctor Atlas × Graphify", html)
        self.assertEqual(len(data["edges"]), 1)
        self.assertTrue(data["nodes"][1]["reasons"])
        self.assertFalse(data["truncated"])

    def test_matching_runtime_trace_adds_observed_calls_without_faking_imports(self):
        sha = "a" * 40
        graph = {"nodes": [{"id": 1, "source_file": "app/a.py"},
                           {"id": 2, "source_file": "app/b.py"}],
                 "links": [], "built_at_commit": sha}
        trace = {"candidate_sha": sha, "worktree_clean": True, "events": [
            {"type": "python_call_edge", "source": "app/a.py", "target": "app/b.py"}
        ]}
        payload = compact_graph(graph, {}, trace)
        self.assertEqual(payload["trace_status"], "MATCHED")
        self.assertEqual(payload["edges"][0]["relation"], "OBSERVED_PYTHON_CALL")
        self.assertTrue(payload["nodes"][0]["runtime_observed"])
        trace["worktree_clean"] = False
        self.assertEqual(compact_graph(graph, {}, trace)["trace_status"], "STALE_OR_INCOMPLETE")
        self.assertEqual(compact_graph(graph, {}, trace)["edges"], [])
        trace["worktree_clean"] = True
        trace["candidate_sha"] = "b" * 40
        self.assertEqual(compact_graph(graph, {}, trace)["trace_status"], "STALE_OR_INCOMPLETE")
        self.assertEqual(compact_graph(graph, {}, trace)["edges"], [])

    def test_legacy_runtime_trace_without_cleanliness_is_not_trusted(self):
        sha = "c" * 40
        graph = {"nodes": [{"id": 1, "source_file": "app/a.py"},
                           {"id": 2, "source_file": "app/b.py"}],
                 "links": [], "built_at_commit": sha}
        trace = {"candidate_sha": sha, "events": [
            {"type": "python_call_edge", "source": "app/a.py", "target": "app/b.py"}
        ]}
        result = compact_graph(graph, {}, trace)
        self.assertEqual(result["trace_status"], "STALE_OR_INCOMPLETE")
        self.assertEqual(result["observed_runtime_file_pairs"], 0)

    def test_instrumented_qt_connection_has_separate_non_invocation_edge(self):
        sha = "d" * 40
        graph = {"built_at_commit": sha,
                 "nodes": [{"id": 1, "source_file": "app/signal.py"},
                           {"id": 2, "source_file": "app/slot.py"}],
                 "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "events": [{
            "type": "qt_signal_connect_returned", "source": "app/signal.py",
            "target": "app/slot.py",
            "confidence": "CONNECT_RETURNED_NOT_CALLBACK_INVOKED",
        }]}
        payload = compact_graph(graph, {}, trace)
        self.assertEqual(payload["trace_status"], "MATCHED")
        self.assertEqual(payload["edges"][0]["relation"], "QT_CONNECT_RETURNED")
        self.assertTrue(payload["nodes"][1]["qt_connection_observed"])
        self.assertFalse(payload["nodes"][1]["runtime_observed"])
        trace["worktree_clean"] = False
        self.assertEqual(compact_graph(graph, {}, trace)["edges"], [])

    def test_symbol_observations_are_opt_in_positive_evidence_only(self):
        sha = "f" * 40
        graph = {"built_at_commit": sha,
                 "nodes": [{"id": 1, "source_file": "app/a.py"},
                           {"id": 2, "source_file": "app/b.py"}], "links": []}
        trace = {"candidate_sha": sha, "worktree_clean": True, "events": [{
            "type": "python_symbol_call", "source": "app/a.py",
            "target": "app/b.py", "caller_symbol": "send",
            "callee_symbol": "receive", "caller_line": 10, "callee_line": 30,
            "confidence": "OBSERVED_CALL_ENTRY",
        }]}
        result = compact_graph(graph, {}, trace)
        self.assertEqual(len(result["observed_symbol_calls"]), 1)
        self.assertEqual(result["observed_symbol_calls"][0]["callee_symbol"], "receive")
        self.assertIn("Appels de fonctions observés", render_html(result))
        trace["worktree_clean"] = False
        self.assertEqual(compact_graph(graph, {}, trace)["observed_symbol_calls"], [])

    def test_live_uses_focus_events_not_periodic_git_polling(self):
        html = render_html(compact_graph({"nodes": [], "links": []}, {}))
        self.assertIn("addEventListener('focus'", html)
        self.assertIn("visibilitychange", html)
        self.assertIn('id="refreshGit"', html)
        self.assertNotIn("setInterval(refreshLive,2500)", html)
        self.assertIn("/api/ping", html)

    def test_can_open_historical_graph_read_only_without_source_confirmed_findings(self):
        import json
        import subprocess
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from tools.atlas_doctor_lib.doctor_graph_ui import export_interactive_graph
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Atlas"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "doctor@example.invalid"], cwd=root, check=True)
            (root / "main.py").write_text("pass\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            folder = root / "graphify-out"
            folder.mkdir()
            path = folder / "graph.json"
            path.write_text(json.dumps({
                "nodes": [{"id": "a", "source_file": "main.py", "label": "main", "community": 0}],
                "links": [], "built_at_commit": sha,
            }))
            evidence = {"status": "STALE", "graph": str(path), "git": {"head": sha}}
            with patch("tools.atlas_doctor_lib.architecture.graph_status", return_value=evidence):
                self.assertEqual(export_interactive_graph(root)["status"], "BLOCKED")
                result = export_interactive_graph(root, allow_stale=True)
            self.assertEqual(result["status"], "REVIEW")
            self.assertEqual(result["candidate_sha"], sha)
            self.assertEqual(result["graph_status"], "STALE")
            self.assertTrue((folder / "doctor_graph.html").is_file())

    def test_full_real_graph_budget_keeps_all_11366_nodes_and_33269_edges(self):
        from tools.atlas_doctor_lib.doctor_graph_ui import MAX_NODES, MAX_LINKS
        self.assertGreaterEqual(MAX_NODES, 11366)
        self.assertGreaterEqual(MAX_LINKS, 33269)
        nodes = [{"id": i, "source_file": "app/ui/sample.py"} for i in range(11366)]
        links = [{"source": i, "target": i+1, "relation": "uses"} for i in range(11365)]
        payload = compact_graph({"nodes": nodes, "links": links}, {})
        self.assertFalse(payload["truncated"])
        self.assertEqual(len(payload["nodes"]), 11366)
        self.assertEqual(len(payload["edges"]), 11365)

    def test_file_coverage_panel_is_read_only_and_escapes_file_names(self):
        from tools.atlas_doctor_lib.doctor_graph_ui import render_html
        graph = {"nodes": [], "edges": [], "candidate_sha": "a" * 40,
                 "file_coverage": {"tracked": 2, "represented": 1, "missing_total": 1,
                                   "missing_examples": ["app/<missing>.py"],
                                   "status": "HISTORICAL", "runtime_proof": False}}
        html = render_html(graph)
        self.assertIn("coverageDetails", html)
        self.assertIn("Fichiers Python couverts", html)
        self.assertIn("Pas une preuve de code utilisé ou mort", html)
        self.assertNotIn("app/<missing>.py", html)
        self.assertIn("app/\\u003cmissing\\u003e.py", html)

    def test_community_island_marks_files_without_claiming_dead_code(self):
        graph = {"nodes": [{"id": 1, "source_file": "app/widget.py", "label": "Widget"}],
                 "links": []}
        report = {"isolated_communities": [{
            "sample_source_files": ["app/widget.py"],
            "sample_linked_production_files": ["app/widget.py"],
        }]}
        data = compact_graph(graph, report)
        self.assertIn("file linked elsewhere", data["nodes"][0]["reasons"][0])
        self.assertIn("not proof of dead code", data["disclaimer"])

    def test_labels_cannot_escape_json_script(self):
        graph = {"nodes": [{"id": 1, "label": "</script><img src=x onerror=alert(1)>",
                            "source_file": "app/x.py"}], "links": []}
        html = render_html(compact_graph(graph, {}))
        self.assertNotIn("</script><img", html)
        self.assertIn("\\u003c", html)


if __name__ == "__main__":
    unittest.main()
