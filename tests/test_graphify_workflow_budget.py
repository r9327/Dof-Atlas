from __future__ import annotations

import unittest
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GraphifyWorkflowBudgetTests(unittest.TestCase):
    def test_full_graphify_is_event_and_path_scoped(self):
        code = (ROOT / ".github/workflows/graphify-map.yml").read_text(encoding="utf-8")
        trigger = code.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertIn("workflow_call:", trigger)
        self.assertNotIn("pull_request:", trigger)
        paths = json.loads((ROOT / "tools/atlas_doctor_lib/ci_routes.json").read_text())["graphify-map"]
        self.assertIn("tools/graphify.py", paths)
        self.assertIn("tools/atlas_doctor_lib/**", paths)
        self.assertIn('timeout-minutes: 20', code)

    def test_graphify_structural_paths_are_triggered_for_pr_and_push(self):
        code = (ROOT / ".github/workflows/graphify-map.yml").read_text(encoding="utf-8")
        trigger = code.split("permissions:", 1)[0]
        paths = json.loads((ROOT / "tools/atlas_doctor_lib/ci_routes.json").read_text())["graphify-map"]
        structural = ("app/**", "main.py", "launch.py", "sitecustomize.py", "local_dofus_data/**", "tools/graphify.py", "tools/agent_graph.py", "tools/atlas_doctor.py", "tools/atlas_doctor_lib/**", ".graphifyignore", ".github/workflows/graphify-map.yml")
        for path in structural:
            self.assertIn(path, paths)
        self.assertNotIn("docs/**", paths)
        self.assertNotIn("**", paths)
        central = (ROOT / ".github/workflows/phase-certification.yml").read_text()
        self.assertIn("pull_request:", central)
        self.assertIn("push:", central)
        self.assertIn("uses: ./.github/workflows/graphify-map.yml", central)

    def test_graph_provenance_never_passes_with_unknown_sha_or_wrong_tool(self):
        import hashlib
        import json
        import tempfile
        from unittest.mock import patch
        from tools.atlas_doctor_lib import architecture

        candidate = "a" * 40
        git = {"head": candidate, "dirty_digest": "", "dirty": False}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "graphify-out"
            output.mkdir()
            (output / "graph.html").write_text("<html>ready</html>", encoding="utf-8")
            (output / "GRAPH_REPORT.md").write_text("ready", encoding="utf-8")
            for graph_head, tool_status, expected in (
                (None, "PASS", "STALE"),
                (candidate, "WRONG_VERSION", "STALE"),
                ("b" * 40, "PASS", "STALE"),
                (candidate, "PASS", "PASS"),
            ):
                with self.subTest(graph_head=graph_head, tool_status=tool_status):
                    data = {"nodes": [{"id": "root", "source_file": "main.py"}], "links": []}
                    if graph_head:
                        data["built_at_commit"] = graph_head
                    encoded = json.dumps(data)
                    (output / "graph.json").write_text(encoded, encoding="utf-8")
                    cache = {
                        "git": git,
                        "version": "0.9.72",
                        "graph_signature": hashlib.sha256(encoded.encode()).hexdigest(),
                    }
                    with patch.object(architecture, "git_state", return_value=git), \
                         patch.object(architecture, "load_json", return_value=cache), \
                         patch.object(architecture, "run_git", side_effect=lambda *_args, **_kw: graph_head), \
                         patch.object(architecture.graphify, "detect",
                                      return_value={"status": tool_status, "version": "0.9.72"}):
                        status = architecture.graph_status(root)
                    self.assertEqual(status["status"], expected)
                    self.assertEqual(status["provenance"]["status"],
                                     "EXACT" if expected == "PASS" else "STALE")

    def test_full_map_persists_exact_sha_build_duration(self):
        code = (ROOT / ".github/workflows/graphify-map.yml").read_text(encoding="utf-8")
        self.assertIn("started=$SECONDS", code)
        self.assertIn("graphify-out/graph_build_seconds.txt", code)
        self.assertIn('"graph_build_seconds": int(', code)
        self.assertIn('Graphify exact-SHA build time:', code)

    def test_full_graph_map_certifies_interactive_doctor_ui_at_exact_sha(self):
        workflow = (ROOT / ".github/workflows/graphify-map.yml").read_text(encoding="utf-8")
        self.assertIn("Verify Doctor interactive export against exact Graphify SHA", workflow)
        self.assertIn("from tools.atlas_doctor_lib.doctor_graph_ui import export_interactive_graph", workflow)
        self.assertIn('result.get("candidate_sha") != os.environ["CANDIDATE_SHA"]', workflow)
        self.assertIn("graphify-out/doctor_graph_ui_metrics.json", workflow)
        self.assertIn("source_scan_truncated", workflow)

    def test_heavy_memory_and_preload_are_selected_by_doctor_impact(self):
        from tools.atlas_doctor_lib.ci_orchestrator import select_workflows
        low = select_workflows(["tools/atlas_json_raw.py"], event="pull_request",
                               phase_route={"route": "SCOPED"}, ui_plan={"status": "NOT_APPLICABLE"})
        high = select_workflows(["app/preload.py"], event="pull_request",
                                phase_route={"route": "FULL"}, ui_plan={"status": "NOT_APPLICABLE"})
        for name in ("phase8-memory-benchmark", "phase8-preload-benchmark"):
            workflow = (ROOT / f".github/workflows/{name}.yml").read_text()
            self.assertIn("workflow_call:", workflow)
            self.assertIn("timeout-minutes: 45", workflow)
            self.assertNotIn("startsWith(github.event.pull_request.title", workflow)
            self.assertFalse(low["workflows"][name]["selected"])
            self.assertTrue(high["workflows"][name]["selected"])

    def test_focused_ci_still_runs_on_every_dev_push(self):
        code = (ROOT / ".github/workflows/graphify-targeted-ci.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_call:", code)
        central = (ROOT / ".github/workflows/phase-certification.yml").read_text()
        self.assertIn("uses: ./.github/workflows/graphify-targeted-ci.yml", central)
        self.assertIn("test_atlas_doctor_dev_events.py", code)
        self.assertIn("test_atlas_doctor_live_graph.py", code)


if __name__ == "__main__":
    unittest.main()
