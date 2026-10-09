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

    def test_focused_ci_still_runs_on_every_dev_push(self):
        code = (ROOT / ".github/workflows/graphify-targeted-ci.yml").read_text(encoding="utf-8")
        self.assertIn("phase8/graphify-staged-cleanup-v1", code)
        self.assertIn("test_atlas_doctor_dev_events.py", code)
        self.assertIn("test_atlas_doctor_live_graph.py", code)


if __name__ == "__main__":
    unittest.main()
