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

    def test_runtime_provenance_rejects_dirty_source_even_with_same_sha(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Atlas"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "doctor@example.invalid"], cwd=root, check=True)
            source = root / "source.py"
            source.write_text("pass\\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=root, check=True)
            observer = RuntimeObserver(root)
            self.assertTrue(observer.worktree_clean)
            with observer:
                source.write_text("changed = True\\n")
            result = observer.report()
            self.assertEqual(len(result["candidate_sha"]), 40)
            self.assertFalse(result["worktree_clean"])

    def test_explicit_qt_signal_registration_records_callback_source(self):
        import runpy

        class Signal:
            def __init__(self):
                self.callbacks = []

            def connect(self, callback):
                self.callbacks.append(callback)
                return "registered"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "window.py"
            script.write_text(
                "def slot():\n    return None\n"
                "connection = observer.connect_qt_signal(signal, slot)\n"
            )
            observer = RuntimeObserver(root)
            signal = Signal()
            with observer:
                scope = runpy.run_path(str(script), init_globals={
                    "observer": observer, "signal": signal,
                })
            self.assertEqual(scope["connection"], "registered")
            self.assertEqual(len(signal.callbacks), 1)
            rows = [event for event in observer.report()["events"]
                    if event["type"] == "qt_signal_connect_returned"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source"], "window.py")
            self.assertEqual(rows[0]["target"], "window.py")
            self.assertEqual(rows[0]["confidence"], "CONNECT_RETURNED_NOT_CALLBACK_INVOKED")

    def test_no_sensitive_outside_paths_or_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observer = RuntimeObserver(root)
            self.assertIsNone(observer._path("/home/somewhere/private.txt"))
            self.assertIsNone(observer._path(root / ".ai/runtime/secret.json"))

    def test_real_source_file_open_is_attributed_to_test_script(self):
        import runpy
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sample = root / "sample.py"
            sample.write_text("with open('sample.py', 'r', encoding='utf-8') as stream:\n    stream.read()\n")
            observer = RuntimeObserver(root, max_events=2000)
            import os
            before = os.getcwd()
            try:
                os.chdir(root)
                with observer:
                    runpy.run_path(str(sample))
            finally:
                os.chdir(before)
            found = [row for row in observer.report()["events"]
                     if row["type"] == "file_open" and row["target"] == "sample.py"]
            self.assertTrue(found, "Python audit events should be captured for the originating script")
            self.assertEqual(found[0]["source"], "sample.py")

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
        sha = "a" * 40
        trace = {"candidate_sha": sha, "worktree_clean": True,
                 "events": [{"type": "python_call_edge", "source": "a.py", "target": "b.py"}]}
        graph = {"built_at_commit": sha,
                 "nodes": [{"id": 1, "source_file": "a.py"}, {"id": 2, "source_file": "b.py"}],
                 "links": [{"source": 1, "target": 2}]}
        result = compare_runtime_to_graph(trace, graph)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["static_edges_with_runtime_evidence"], 1)
        self.assertFalse(result["static_coverage_claim"])
        trace["worktree_clean"] = False
        stale = compare_runtime_to_graph(trace, graph)
        self.assertEqual(stale["status"], "REVIEW")
        self.assertFalse(stale["runtime_evidence_valid"])
        self.assertEqual(stale["static_edges_with_runtime_evidence"], 0)
        trace["worktree_clean"] = True
        graph["built_at_commit"] = "b" * 40
        self.assertEqual(compare_runtime_to_graph(trace, graph)["status"], "REVIEW")

    def test_qt_call_site_does_not_claim_a_receiver(self):
        import sys
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            observer = RuntimeObserver(Path(directory))
            signal = type("SignalInstance", (), {"__module__": "PySide6.QtCore"})()
            callback = SimpleNamespace(__name__="connect", __self__=signal)
            with observer:
                original = observer._path
                observer._path = lambda path: "app/view.py"
                try:
                    observer._profile(sys._getframe(), "c_call", callback)
                finally:
                    observer._path = original
            rows = [e for e in observer.report()["events"] if e["type"] == "qt_c_call_site"]
            self.assertEqual(rows[-1]["confidence"], "CALL_SITE_ONLY")
            self.assertNotIn("receiver", rows[-1])

    def test_repeated_sessions_reuse_single_audit_dispatcher(self):
        from tools.atlas_doctor_lib import runtime_observation as module
        with tempfile.TemporaryDirectory() as directory:
            first = RuntimeObserver(Path(directory))
            second = RuntimeObserver(Path(directory))
            with first:
                self.assertIs(module._ACTIVE_AUDIT_REF(), first)
                with self.assertRaises(RuntimeError):
                    second.__enter__()
            self.assertIsNone(module._ACTIVE_AUDIT_REF)
            with second:
                self.assertIs(module._ACTIVE_AUDIT_REF(), second)
            self.assertTrue(module._AUDIT_HOOK_INSTALLED)
            self.assertIsNone(module._ACTIVE_AUDIT_REF)

    def test_bound_enforced_and_bad_markers_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                RuntimeObserver(Path(directory), max_events=0)
            observer = RuntimeObserver(Path(directory), max_events=1)
            with self.assertRaises(ValueError):
                observer.mark("arbitrary", source="a.py")


if __name__ == "__main__":
    unittest.main()
