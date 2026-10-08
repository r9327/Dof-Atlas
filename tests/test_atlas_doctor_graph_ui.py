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
        trace = {"candidate_sha": sha, "events": [
            {"type": "python_call_edge", "source": "app/a.py", "target": "app/b.py"}
        ]}
        payload = compact_graph(graph, {}, trace)
        self.assertEqual(payload["trace_status"], "MATCHED")
        self.assertEqual(payload["edges"][0]["relation"], "OBSERVED_PYTHON_CALL")
        self.assertTrue(payload["nodes"][0]["runtime_observed"])
        trace["candidate_sha"] = "b" * 40
        self.assertEqual(compact_graph(graph, {}, trace)["trace_status"], "STALE_OR_INCOMPLETE")
        self.assertEqual(compact_graph(graph, {}, trace)["edges"], [])

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

    def test_labels_cannot_escape_json_script(self):
        graph = {"nodes": [{"id": 1, "label": "</script><img src=x onerror=alert(1)>",
                            "source_file": "app/x.py"}], "links": []}
        html = render_html(compact_graph(graph, {}))
        self.assertNotIn("</script><img", html)
        self.assertIn("\\u003c", html)


if __name__ == "__main__":
    unittest.main()
