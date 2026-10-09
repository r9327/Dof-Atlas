from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GraphifyWorkflowBudgetTests(unittest.TestCase):
    def test_full_graphify_is_event_and_path_scoped(self):
        code = (ROOT / ".github/workflows/graphify-map.yml").read_text(encoding="utf-8")
        trigger = code.split("permissions:", 1)[0]
        self.assertIn("workflow_dispatch:", trigger)
        self.assertIn("paths:", trigger)
        self.assertIn('"tools/graphify.py"', trigger)
        self.assertIn('"tools/atlas_doctor_lib/graph_intelligence.py"', trigger)
        self.assertNotIn('"tools/atlas_doctor_lib/live_graph.py"', trigger)
        self.assertIn('timeout-minutes: 20', code)

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

    def test_heavy_memory_and_preload_are_explicit_for_graphify_ui_only_changes(self):
        # Graphify code/UI iterations must not re-run 45-minute Windows
        # benchmarks every push. Manual final Phase 8 certification remains.
        for name in ("phase8-memory-benchmark.yml", "phase8-preload-benchmark.yml"):
            workflow = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
            self.assertIn("workflow_dispatch:", workflow)
            self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
            self.assertNotIn(
                "github.event.pull_request.head.ref == 'phase8/graphify-staged-cleanup-v1'",
                workflow,
            )
            self.assertIn("startsWith(github.event.pull_request.title, 'Phase 8')", workflow)

    def test_focused_ci_still_runs_on_every_dev_push(self):
        code = (ROOT / ".github/workflows/graphify-targeted-ci.yml").read_text(encoding="utf-8")
        self.assertIn("phase8/graphify-staged-cleanup-v1", code)
        self.assertIn("test_atlas_doctor_dev_events.py", code)
        self.assertIn("test_atlas_doctor_live_graph.py", code)


if __name__ == "__main__":
    unittest.main()
