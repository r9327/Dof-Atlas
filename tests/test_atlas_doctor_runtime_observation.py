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

    def test_runtime_edge_deduplication_stays_bounded_after_event_cap(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as directory:
            observer = RuntimeObserver(Path(directory), max_events=2)
            observer._active = True
            observer._path = lambda source: source
            for index in range(300):
                caller = SimpleNamespace(
                    f_code=SimpleNamespace(co_filename="app/caller.py",
                                           co_qualname="caller"),
                    f_lineno=23,
                )
                frame = SimpleNamespace(
                    f_code=SimpleNamespace(co_filename=f"app/target_{index}.py",
                                           co_qualname="target",
                                           co_firstlineno=1),
                    f_back=caller,
                )
                observer._profile(frame, "call", None)
            observer._active = False
            self.assertTrue(observer._overflow)
            self.assertLessEqual(len(observer.events), observer.max_events)
            self.assertLessEqual(len(observer._edges), observer.max_events)
            self.assertLessEqual(len(observer._symbol_edges), observer.max_events)

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

    def test_runtime_head_change_invalidates_observation_even_when_worktree_clean(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Atlas"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "doctor@example.invalid"], cwd=root, check=True)
            (root / "a.py").write_text("pass\n")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "first"], cwd=root, check=True)
            observer = RuntimeObserver(root)
            first_sha = observer.candidate_sha
            self.assertTrue(observer.worktree_clean)
            with observer:
                subprocess.run(["git", "commit", "--allow-empty", "-qm", "second"], cwd=root, check=True)
            self.assertNotEqual(observer._head_sha(), first_sha)
            self.assertTrue(observer._clean_worktree())
            self.assertFalse(observer.report()["worktree_clean"])

    def test_short_sha_prefix_cannot_validate_runtime_comparison(self):
        sha = "a" * 40
        graph = {"built_at_commit": sha[:7], "nodes": [
            {"id": 1, "source_file": "app/a.py"},
            {"id": 2, "source_file": "app/b.py"},
        ], "links": [{"source": 1, "target": 2}]}
        trace = {"candidate_sha": sha, "worktree_clean": True, "truncated": False,
                 "events": [{"type": "python_call_edge",
                             "source": "app/a.py", "target": "app/b.py"}]}
        report = compare_runtime_to_graph(trace, graph)
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["static_edges_with_runtime_evidence"], 0)
        self.assertFalse(report["runtime_evidence_valid"])

    def test_lifecycle_marker_pairing_is_bounded_and_not_leak_proof(self):
        from tools.atlas_doctor_lib.runtime_observation import summarize_runtime_lifecycle
        trace = {"events": [
            {"type": "worker_start", "source": "app/worker.py", "target": "app/job.py"},
            {"type": "worker_stop", "source": "app/worker.py", "target": "app/job.py"},
            {"type": "worker_start", "source": "app/worker.py", "target": "app/job.py"},
            {"type": "cache_release", "source": "app/cache.py"},
        ], "truncated": False}
        result = summarize_runtime_lifecycle(trace)
        self.assertEqual(result["worker_start_events"], 2)
        self.assertEqual(result["worker_stop_events"], 1)
        self.assertEqual(result["worker_starts_unpaired"], [
            {"source": "app/worker.py", "target": "app/job.py", "unpaired_starts": 1}
        ])
        self.assertEqual(result["cache_release_sources"], ["app/cache.py"])
        self.assertEqual(result["status"], "REVIEW")
        self.assertFalse(result["proof_of_memory_leak"])
        trace["events"].append({"type": "worker_stop",
                                "source": "app/worker.py", "target": "app/job.py"})
        self.assertEqual(summarize_runtime_lifecycle(trace)["status"], "OBSERVED")

    def test_lifecycle_rejects_oversized_and_malformed_runtime(self):
        from tools.atlas_doctor_lib.runtime_observation import summarize_runtime_lifecycle
        for trace in ({"events": [None]}, {"events": [None] * 50001}):
            result = summarize_runtime_lifecycle(trace)
            self.assertEqual(result["status"], "REVIEW")
            self.assertTrue(result["truncated"])
            self.assertEqual(result["worker_starts_unpaired"], [])

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

    def test_qt_partial_callback_recovers_real_target_without_invocation(self):
        import runpy

        class Signal:
            def __init__(self):
                self.callbacks = []

            def connect(self, callback):
                self.callbacks.append(callback)
                return "connected"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            callback_file = root / "slot.py"
            caller_file = root / "caller.py"
            callback_file.write_text("def callback(value):\n    return value\n")
            caller_file.write_text(
                "from functools import partial\n"
                "result = observer.connect_qt_signal(signal, partial(callback, 7))\n"
            )
            callback = runpy.run_path(str(callback_file))["callback"]
            observer = RuntimeObserver(root)
            signal = Signal()
            with observer:
                scope = runpy.run_path(str(caller_file), init_globals={
                    "observer": observer, "signal": signal, "callback": callback,
                })
            self.assertEqual(scope["result"], "connected")
            self.assertEqual(len(signal.callbacks), 1)
            events = [row for row in observer.report()["events"]
                      if row["type"] == "qt_signal_connect_returned"]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["source"], "caller.py")
            self.assertEqual(events[0]["target"], "slot.py")
            self.assertEqual(events[0]["confidence"], "CONNECT_RETURNED_NOT_CALLBACK_INVOKED")

    def test_real_cross_file_function_call_is_recorded_by_symbol(self):
        import runpy
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.py"
            caller = root / "caller.py"
            namespace = {}
            exec(compile("def invoked():\n    return 42\n", str(target), "exec"), namespace)
            caller.write_text("def launch():\n    return invoked()\nlaunch()\n")
            watcher = RuntimeObserver(root, max_events=1000)
            with watcher:
                runpy.run_path(str(caller), init_globals={"invoked": namespace["invoked"]})
            result = watcher.report()
            matches = [e for e in result["events"]
                       if e["type"] == "python_symbol_call"
                       and e["source"] == "caller.py" and e["target"] == "target.py"]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["caller_symbol"], "launch")
            self.assertEqual(matches[0]["callee_symbol"], "invoked")
            self.assertEqual(matches[0]["callee_line"], 1)
            self.assertEqual(matches[0]["confidence"], "OBSERVED_CALL_ENTRY")
            self.assertFalse(result["symbol_edges_truncated"])
            self.assertFalse(watcher._active)

    def test_symbol_recording_has_explicit_independent_budget(self):
        from tools.atlas_doctor_lib.runtime_observation import MAX_SYMBOL_EDGES
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            observer = RuntimeObserver(root, max_events=MAX_SYMBOL_EDGES + 100)
            observer._active = True
            observer._symbol_edges = {
                ("a.py", "caller", i, "b.py", "callee") for i in range(MAX_SYMBOL_EDGES)
            }
            # The next observation must never increase the symbol-edge budget.
            import types
            source = compile(
                "def fresh():\n    observer._profile(__import__('sys')._getframe(), 'call', None)\n",
                str(root / "a.py"), "exec",
            )
            namespace = {"observer": observer}
            exec(source, namespace)
            original = observer._path
            observer._path = lambda value: "a.py" if "a.py" in str(value) else "b.py"
            try:
                namespace["fresh"]()
            finally:
                observer._path = original
                observer._active = False
            self.assertEqual(len(observer._symbol_edges), MAX_SYMBOL_EDGES)
            self.assertTrue(observer._symbol_overflow)

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

    def test_worker_created_during_trace_drops_profile_after_exit(self):
        import sys
        import threading
        with tempfile.TemporaryDirectory() as directory:
            observer = RuntimeObserver(Path(directory), max_events=1000)
            old_thread_profile = threading.getprofile()
            started = threading.Event()
            resume = threading.Event()
            seen = []

            def worker():
                started.set()
                resume.wait(3)
                def get_profile():
                    return sys.getprofile()
                seen.append(get_profile())

            with observer:
                thread = threading.Thread(target=worker, daemon=True)
                thread.start()
                self.assertTrue(started.wait(3))
            try:
                resume.set()
                thread.join(timeout=4)
                self.assertFalse(thread.is_alive())
                self.assertEqual(seen, [old_thread_profile])
                self.assertIs(threading.getprofile(), old_thread_profile)
            finally:
                resume.set()
                thread.join(timeout=2)

    def test_bound_enforced_and_bad_markers_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                RuntimeObserver(Path(directory), max_events=0)
            observer = RuntimeObserver(Path(directory), max_events=1)
            with self.assertRaises(ValueError):
                observer.mark("arbitrary", source="a.py")


    def test_opt_in_qt_destroyed_signal_marks_actual_delivery_without_ownership_claim(self):
        import runpy

        class Signal:
            def __init__(self):
                self.callbacks = []
            def connect(self, callback):
                self.callbacks.append(callback)
            def fire(self):
                for callback in self.callbacks:
                    callback()

        class QObjectLike:
            def __init__(self):
                self.destroyed = Signal()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script = root / "window.py"
            script.write_text("registered = watcher.watch_qt_destroyed(obj, label='view')\n"
                              "obj.destroyed.fire()\n", encoding="utf-8")
            watcher = RuntimeObserver(root, max_events=500)
            obj = QObjectLike()
            with watcher:
                result = runpy.run_path(str(script), init_globals={"watcher": watcher, "obj": obj})
            self.assertTrue(result["registered"])
            records = [e for e in watcher.report()["events"] if e["type"] == "qt_destroyed_observed"]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["source"], "window.py")
            lifecycle = watcher.report()["lifecycle"]
            self.assertEqual(lifecycle["qt_destroyed_sources"], ["window.py"])
            self.assertTrue(lifecycle["qt_destroyed_is_not_ownership_proof"])
            obj.destroyed.fire()
            self.assertEqual(len([e for e in watcher.report()["events"]
                                  if e["type"] == "qt_destroyed_observed"]), 1)
            with self.assertRaisesRegex(RuntimeError, "active observer"):
                watcher.watch_qt_destroyed(obj, label="late")

    def test_wrapped_qt_slot_records_actual_entry_and_preserves_result(self):
        import runpy
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / "qt_window.py"
            script.write_text("def slot(value):\n    return value * 2\n"
                              "wrapped = observer.wrap_qt_slot(slot)\n"
                              "answer = wrapped(21)\n", encoding="utf-8")
            observer = RuntimeObserver(root, max_events=400)
            with observer:
                result = runpy.run_path(str(script), init_globals={"observer": observer})
            self.assertEqual(result["answer"], 42)
            entries = [row for row in observer.report()["events"]
                       if row["type"] == "qt_callback_invoked"]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["target"], "qt_window.py")
            self.assertEqual(entries[0]["confidence"], "WRAPPED_PYTHON_CALLBACK_ENTERED")
            self.assertEqual(result["wrapped"](5), 10)
            self.assertEqual(len([row for row in observer.report()["events"]
                                  if row["type"] == "qt_callback_invoked"]), 1)

    def test_wrapped_slot_preserves_exception_and_requires_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            watcher = RuntimeObserver(Path(folder))
            def broken():
                raise RuntimeError("slot failed")
            with watcher:
                slot = watcher.wrap_qt_slot(broken)
                with self.assertRaisesRegex(RuntimeError, "slot failed"):
                    slot()
            with self.assertRaisesRegex(RuntimeError, "active observer"):
                watcher.wrap_qt_slot(broken)


if __name__ == "__main__":
    unittest.main()
