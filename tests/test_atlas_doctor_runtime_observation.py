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


    def test_active_observer_only_available_during_opt_in_session(self):
        from tools.atlas_doctor_lib.runtime_observation import active_observer
        with tempfile.TemporaryDirectory() as directory:
            watcher = RuntimeObserver(Path(directory))
            self.assertIsNone(active_observer())
            with watcher:
                self.assertIs(active_observer(), watcher)
            self.assertIsNone(active_observer())

    def test_qt_connection_unwraps_instrumentation_to_real_callback_file(self):
        import runpy

        class Signal:
            def connect(self, callback):
                self.callback = callback
                return "registered"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / "window.py"
            file.write_text(
                "def slot():\n    return 73\n"
                "wrapped = watcher.wrap_qt_slot(slot)\n"
                "connected = watcher.connect_qt_signal(signal, wrapped)\n"
                "answer = wrapped()\n", encoding="utf-8")
            watcher, signal = RuntimeObserver(root, max_events=500), Signal()
            with watcher:
                scope = runpy.run_path(str(file), init_globals={
                    "watcher": watcher, "signal": signal})
            self.assertEqual(scope["connected"], "registered")
            self.assertEqual(scope["answer"], 73)
            rows = [row for row in watcher.report()["events"]
                    if row["type"] == "qt_signal_connect_returned"]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["source"], "window.py")
            self.assertEqual(rows[0]["target"], "window.py")
            self.assertEqual([row["target"] for row in watcher.report()["events"]
                              if row["type"] == "qt_callback_invoked"], ["window.py"])

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

    def test_explicit_json_decode_and_ui_binding_emit_no_payload(self):
        import runpy
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data/catalog.json").write_text('{"secret":"do-not-log"}', encoding="utf-8")
            source = root / "app_ui.py"
            source.write_text("obj, token = observer.read_json('data/catalog.json')\n"
                              "did_bind = observer.mark_ui_bound(token)\n", encoding="utf-8")
            observer = RuntimeObserver(root, max_events=1000)
            with observer:
                scope = runpy.run_path(str(source), init_globals={"observer": observer})
            report = observer.report()
            self.assertEqual(scope["obj"], {"secret": "do-not-log"})
            self.assertTrue(scope["did_bind"])
            self.assertEqual(len([e for e in report["events"] if e["type"] == "json_decoded"]), 1)
            self.assertEqual(len([e for e in report["events"] if e["type"] == "json_ui_bound"]), 1)
            self.assertNotIn("do-not-log", json.dumps(report))
            self.assertFalse(observer.mark_ui_bound(scope["token"]))

    def test_json_decode_rejects_invalid_traversal_and_malformed_json(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "bad.json").write_text("{broken", encoding="utf-8")
            observer = RuntimeObserver(root)
            with observer:
                with self.assertRaises(ValueError):
                    observer.read_json("../bad.json")
                with self.assertRaises(json.JSONDecodeError):
                    observer.read_json("bad.json")
                self.assertFalse(observer.mark_ui_bound("unknown"))
            self.assertFalse(any(e["type"] == "json_decoded" for e in observer.report()["events"]))

    def test_weak_watch_snapshot_is_observational_not_leak_evidence(self):
        import gc
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = root / "scenario.py"
            script.write_text("class Item: pass\n"
                              "instance = Item()\n"
                              "watched = observer.watch(instance, label='item')\n"
                              "before = observer.snapshot_watches(label='before')\n"
                              "del instance\n"
                              "import gc; gc.collect()\n"
                              "after = observer.snapshot_watches(label='after')\n")
            observer = RuntimeObserver(root, max_events=1000)
            with observer:
                scope = __import__("runpy").run_path(str(script), init_globals={"observer": observer})
            self.assertTrue(scope["watched"])
            self.assertEqual(scope["before"]["alive"], 1)
            self.assertEqual(scope["after"]["alive"], 0)
            self.assertEqual(len([e for e in observer.report()["events"]
                                  if e["type"] == "weak_watch_snapshot"]), 2)
    def test_process_tree_sample_is_opt_in_and_does_not_claim_ownership(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import sys
        class Proc:
            def __init__(self, name, rss, children=None):
                self._name, self._rss, self._children = name, rss, children or []
            def children(self, recursive=False):
                return self._children
            def memory_info(self):
                return SimpleNamespace(rss=self._rss)
            def name(self):
                return self._name
        root = Proc("Python", 12, [Proc("QtWebEngineProcess.exe", 45)])
        fake_psutil = SimpleNamespace(Process=lambda: root, Error=Exception)
        with tempfile.TemporaryDirectory() as folder:
            observer = RuntimeObserver(Path(folder))
            with self.assertRaisesRegex(RuntimeError, "active observer"):
                observer.snapshot_process_tree(label="early")
            scenario = Path(folder) / "snapshot_scenario.py"
            scenario.write_text("result = observer.snapshot_process_tree(label='view')\\n",
                                encoding="utf-8")
            with patch.dict(sys.modules, {"psutil": fake_psutil}):
                with observer:
                    result = __import__("runpy").run_path(
                        str(scenario), init_globals={"observer": observer}
                    )["result"]
            self.assertEqual(result["status"], "OBSERVED")
            self.assertEqual(result["rss_tree_bytes"], 57)
            self.assertEqual(result["webengine_children_named"], 1)
            self.assertTrue(result["not_native_qt_ownership_proof"])
            self.assertEqual(len([x for x in observer.report()["events"]
                                  if x["type"] == "process_tree_snapshot"]), 1)


    def test_bounded_qt_watch_distinguishes_invalid_cpp_wrapper_without_leak_claim(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        import sys
        class QWidgetLike:
            pass
        obj = QWidgetLike()
        fake = SimpleNamespace(isValid=lambda _: False)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            scenario = root / "qt_check.py"
            scenario.write_text("observer.watch(obj, label='widget', kind='qwidget')\n"
                                "state = observer.snapshot_qt_objects(label='after-destroy')\n")
            observer = RuntimeObserver(root, max_events=500)
            with patch.dict(sys.modules, {"shiboken6": fake}):
                with observer:
                    state = __import__("runpy").run_path(str(scenario), init_globals={
                        "observer": observer, "obj": obj})["state"]
            self.assertEqual(state["native_invalid_wrappers"], 1)
            self.assertEqual(state["native_valid_wrappers"], 0)
            self.assertTrue(state["not_memory_leak_proof"])
            self.assertEqual(len([e for e in observer.report()["events"]
                                  if e.get("type") == "qt_native_snapshot"]), 1)
            with self.assertRaisesRegex(RuntimeError, "active observer"):
                observer.snapshot_qt_objects(label="after")

    def test_weak_watch_cap_is_bounded_without_retaining_objects(self):
        class Watched:
            pass
        with tempfile.TemporaryDirectory() as folder:
            observer = RuntimeObserver(Path(folder))
            values = [Watched() for _ in range(130)]
            successful = [observer.watch(row, label="test", kind="qobject") for row in values]
            self.assertEqual(sum(successful), 128)
            self.assertEqual(len(observer._watched), 128)

    def test_json_qt_label_binding_proves_setter_without_storing_secret(self):
        import runpy
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "data").mkdir()
            (root / "data/settings.json").write_text('{"label":"secret-text"}')
            script = root / "page.py"
            script.write_text(
                "class Window:\n    pass\n"
                "class Label:\n"
                "    def __init__(self): self._text = ''; self.owner = Window()\n"
                "    def setText(self, text): self._text = text\n"
                "    def text(self): return self._text\n"
                "    def parentWidget(self): return self.owner\n"
                "data, token = observer.read_json('data/settings.json')\n"
                "label = Label()\n"
                "bound = observer.bind_json_label_text(token, label, data['label'])\n"
            )
            observer = RuntimeObserver(root, max_events=1000)
            with observer:
                result = runpy.run_path(str(script), init_globals={"observer": observer})
            self.assertTrue(result["bound"])
            self.assertEqual(result["label"].text(), "secret-text")
            events = [e for e in observer.report()["events"] if e["type"] == "json_ui_bound"]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["confidence"], "EXPLICIT_QT_LABEL_SETTEXT_RETURNED")
            self.assertEqual(events[0]["source"], "page.py")
            self.assertNotIn("secret-text", json.dumps(observer.report()))

    def test_process_checkpoints_only_compare_stable_sampled_processes(self):
        from tools.atlas_doctor_lib.runtime_observation import summarize_process_checkpoints
        trace = {"truncated": False, "events": [
            {"type": "process_tree_snapshot", "status": "OBSERVED",
             "label": "Home", "rss_tree_bytes": 1000, "processes_counted": 2,
             "cpu_time_cumulative_seconds": 1.2,
             "process_group_fingerprint": "a" * 24},
            {"type": "process_tree_snapshot", "status": "OBSERVED",
             "label": "Guide", "rss_tree_bytes": 1500, "processes_counted": 2,
             "cpu_time_cumulative_seconds": 1.45,
             "process_group_fingerprint": "a" * 24},
            {"type": "process_tree_snapshot", "status": "OBSERVED",
             "label": "After WebEngine", "rss_tree_bytes": 1900, "processes_counted": 3,
             "cpu_time_cumulative_seconds": 1.8,
             "process_group_fingerprint": "b" * 24}]}
        report = summarize_process_checkpoints(trace)
        self.assertEqual(report["status"], "OBSERVED_SNAPSHOTS")
        self.assertEqual(report["comparisons"][0]["rss_delta_bytes"], 500)
        self.assertAlmostEqual(report["comparisons"][0]["cpu_time_delta_seconds"], 0.25)
        self.assertIsNone(report["comparisons"][1]["rss_delta_bytes"])
        self.assertFalse(report["comparisons"][1]["same_sampled_process_set"])
        self.assertFalse(report["peak_rss_proven"])
        trace["truncated"] = True
        self.assertEqual(summarize_process_checkpoints(trace)["status"], "INCOMPLETE")

    def test_qt_worker_started_finished_signals_observed_without_strong_ownership(self):
        import runpy
        class Signal:
            def __init__(self): self.handlers = []
            def connect(self, handler): self.handlers.append(handler)
            def emit(self):
                for handler in self.handlers: handler()
        class Worker:
            def __init__(self): self.started = Signal(); self.finished = Signal()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "worker_scenario.py"
            source.write_text("ok = observer.watch_qt_thread(worker, label='catalog')\n"
                              "worker.started.emit()\nworker.finished.emit()\n")
            observer = RuntimeObserver(root, max_events=800)
            worker = Worker()
            with observer:
                r = runpy.run_path(str(source), init_globals={
                    "observer": observer, "worker": worker})
            self.assertTrue(r["ok"])
            report = observer.report()
            events = [e for e in report["events"] if e.get("type") in {
                "qt_worker_started", "qt_worker_finished"}]
            self.assertEqual([e["type"] for e in events],
                             ["qt_worker_started", "qt_worker_finished"])
            self.assertEqual(report["lifecycle"]["qt_worker_started_events"], 1)
            self.assertEqual(report["lifecycle"]["qt_worker_finished_events"], 1)
            self.assertEqual(report["lifecycle"]["qt_worker_unpaired"], [])
            self.assertFalse(report["lifecycle"]["proof_of_memory_leak"])
            worker.started.emit()
            self.assertEqual(len([e for e in observer.report()["events"]
                                  if e.get("type") == "qt_worker_started"]), 1)

    def test_qt_worker_unpaired_is_review_and_scenarios_do_not_cancel_each_other(self):
        from tools.atlas_doctor_lib.runtime_observation import summarize_runtime_lifecycle
        started = {"type": "qt_worker_started", "source": "app/worker.py",
                   "target": "app/worker.py", "qt_worker_token": "qt-thread-1",
                   "confidence": "QT_STARTED_SIGNAL_DELIVERED", "_trace_group": 0}
        finished = {"type": "qt_worker_finished", "source": "app/worker.py",
                    "target": "app/worker.py", "qt_worker_token": "qt-thread-1",
                    "confidence": "QT_FINISHED_SIGNAL_DELIVERED", "_trace_group": 1}
        report = summarize_runtime_lifecycle({"events": [started, finished],
                                             "truncated": False})
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["qt_worker_started_events"], 1)
        self.assertEqual(len(report["qt_worker_unpaired"]), 1)
        self.assertEqual(report["qt_worker_unmatched_finished"], 1)
        self.assertFalse(report["proof_of_memory_leak"])


if __name__ == "__main__":
    unittest.main()
