from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.atlas_doctor_lib.runtime_observation import (
    RuntimeObserver, compare_runtime_to_graph,
)


class RuntimeObservationTests(unittest.TestCase):
    def test_python_calls_are_observed_only_while_active(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            module = root / "example.py"
            module.write_text("def example():\n    return 4\nexample()\n")
            import runpy
            watcher = RuntimeObserver(root, max_events=100)
            with watcher:
                runpy.run_path(str(module))
            report = watcher.report()
            self.assertEqual(report["status"], "RECORDED")
            self.assertTrue(any(e["type"] == "python_call_edge" for e in report["events"]))
            self.assertFalse(watcher._active)

    def test_no_sensitive_outside_paths_or_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observer = RuntimeObserver(root)
            self.assertIsNone(observer._path("/home/somewhere/private.txt"))
            self.assertIsNone(observer._path(root / ".ai/runtime/secret.json"))

    def test_explicit_lifecycle_uses_non_owning_refs(self):
        class Target:
            pass
        with tempfile.TemporaryDirectory() as directory:
            observer = RuntimeObserver(Path(directory))
            with observer:
                item = Target()
                self.assertTrue(observer.watch(item, label="guide-worker", kind="worker"))
                self.assertTrue(observer.report()["object_watches"][0]["still_referenced"])
                del item
            self.assertFalse(observer.report(collect=True)["object_watches"][0]["still_referenced"])

    def test_runtime_graph_overlap_is_not_completeness(self):
        trace = {"events": [{"type": "python_call_edge", "source": "a.py", "target": "b.py"}]}
        graph = {"nodes": [{"id": 1, "source_file": "a.py"}, {"id": 2, "source_file": "b.py"}],
                 "links": [{"source": 1, "target": 2}]}
        result = compare_runtime_to_graph(trace, graph)
        self.assertEqual(result["static_edges_with_runtime_evidence"], 1)
        self.assertFalse(result["static_coverage_claim"])

    def test_bound_enforced_and_bad_markers_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                RuntimeObserver(Path(directory), max_events=0)
            observer = RuntimeObserver(Path(directory), max_events=1)
            with self.assertRaises(ValueError):
                observer.mark("arbitrary", source="a.py")


if __name__ == "__main__":
    unittest.main()
