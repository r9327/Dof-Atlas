from __future__ import annotations

import logging
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.macro_lock import MacroLock
from app.core.runtime_state import AtlasRuntime


class MacroGenerationOwnershipTests(unittest.TestCase):
    def test_old_identically_named_worker_cannot_unlock_new_lease(self):
        for name in ("Miroir", "Miroir clavier", "Miroir molette", "Auto zaap"):
            with self.subTest(name=name):
                lock = MacroLock(Mock())
                self.assertTrue(lock.try_begin(name))
                previous = lock.active_generation
                self.assertTrue(lock.owns(name, previous))
                lock.request_stop()
                lock.end(name, generation=previous)
                self.assertTrue(lock.try_begin(name))
                current = lock.active_generation
                self.assertNotEqual(previous, current)
                self.assertFalse(lock.owns(name, previous))
                lock.end(name, generation=previous)
                self.assertEqual(lock.active_label, name)
                self.assertTrue(lock.owns(name, current))
                lock.end(name, generation=current)
                self.assertFalse(lock.active_label)

    def test_malformed_generation_cannot_release_another_worker(self):
        lock = MacroLock(Mock())
        self.assertTrue(lock.try_begin("Miroir"))
        current = lock.active_generation
        for malformed in (True, 1.0, "1", None):
            if malformed is None:
                continue  # Administrative/legacy callers use the label path.
            with self.subTest(malformed=repr(malformed)):
                lock.end("Miroir", generation=malformed)
                self.assertEqual(lock.active_generation, current)
        lock.end("Miroir", generation=current)
        self.assertFalse(lock.active_label)

    def test_runtime_old_runner_cannot_reset_new_guard_or_unlock_same_label(self):
        for account_count in (2, 4, 6, 8):
            with self.subTest(accounts=account_count):
                runtime = SimpleNamespace(
                    logger=logging.getLogger("organizer_generation"),
                    macro_lock=MacroLock(Mock()),
                    synthetic_guard=Mock(),
                    _threads=[],
                    _emit_status=Mock(),
                )
                old_started = threading.Event()
                finish_old = threading.Event()
                finish_new = threading.Event()
                new_started = threading.Event()

                def old_work():
                    old_started.set()
                    self.assertTrue(finish_old.wait(2))

                def new_work():
                    new_started.set()
                    self.assertTrue(finish_new.wait(2))

                self.assertTrue(AtlasRuntime._spawn_macro(
                    runtime, "Miroir", old_work,
                ))
                try:
                    self.assertTrue(old_started.wait(2))
                    previous = runtime.macro_lock.active_generation
                    # Simulate an out-of-band early completion; stale thread
                    # still owns its Python finally and must not touch new.
                    runtime.macro_lock.end("Miroir", generation=previous)
                    self.assertTrue(AtlasRuntime._spawn_macro(
                        runtime, "Miroir", new_work,
                    ))
                    self.assertTrue(new_started.wait(2))
                    current = runtime.macro_lock.active_generation
                    finish_old.set()
                    for worker in runtime._threads:
                        if worker.name == "DofusAtlas-Miroir" and worker.is_alive():
                            pass
                    # The previous runner is allowed to exit first, but its
                    # stale finally cannot reset or unlock the live new one.
                    old_thread = runtime._threads[0]
                    old_thread.join(2)
                    self.assertFalse(old_thread.is_alive())
                    self.assertTrue(runtime.macro_lock.owns("Miroir", current))
                    runtime.synthetic_guard.reset.assert_not_called()
                finally:
                    finish_old.set()
                    finish_new.set()
                    for worker in runtime._threads:
                        worker.join(2)
                self.assertEqual(runtime.synthetic_guard.reset.call_count, 1)
                self.assertEqual(runtime.macro_lock.active_label, "")


    def test_stale_worker_remains_stopped_after_new_generation_clears_stop(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                lock = MacroLock(Mock())
                self.assertTrue(lock.try_begin("Miroir"))
                previous = lock.active_generation
                ready = threading.Event()
                go = threading.Event()
                outcomes = []

                def old_runner():
                    self.assertTrue(lock.bind_worker("Miroir", previous))
                    ready.set()
                    if not go.wait(2):
                        outcomes.append("timeout")
                        return
                    outcomes.append((
                        lock.should_stop(), lock.wait(0),
                    ))
                    lock.unbind_worker()

                worker = threading.Thread(target=old_runner)
                worker.start()
                try:
                    self.assertTrue(ready.wait(2))
                    lock.request_stop()
                    lock.end("Miroir", generation=previous)
                    self.assertTrue(lock.try_begin("Miroir"))
                    current = lock.active_generation
                    go.set()
                    worker.join(2)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(outcomes, [(True, True)])
                    self.assertTrue(lock.owns("Miroir", current))
                    lock.end("Miroir", generation=current)
                finally:
                    go.set()
                    worker.join(2)

    def test_queued_old_runner_never_executes_after_same_label_reused(self):
        import app.core.runtime_state as runtime_module

        pending = []

        class PendingThread:
            def __init__(self, *, target, name, daemon):
                self.target = target
                self.name = name
                self.daemon = daemon
                pending.append(self)

            def start(self):
                return None

            def is_alive(self):
                return False

        runtime = SimpleNamespace(
            logger=logging.getLogger("test-queued-mirror-generation"),
            macro_lock=MacroLock(Mock()),
            synthetic_guard=Mock(),
            _threads=[],
            _emit_status=Mock(),
        )
        sent = Mock()
        with patch.object(runtime_module.threading, "Thread", PendingThread):
            self.assertTrue(AtlasRuntime._spawn_macro(
                runtime, "Miroir", sent,
            ))
            previous = runtime.macro_lock.active_generation
            runtime.macro_lock.request_stop()
            runtime.macro_lock.end("Miroir", generation=previous)
            self.assertTrue(AtlasRuntime._spawn_macro(
                runtime, "Miroir", lambda: None,
            ))
        current = runtime.macro_lock.active_generation
        self.assertNotEqual(previous, current)
        pending[0].target()
        sent.assert_not_called()
        self.assertTrue(runtime.macro_lock.owns("Miroir", current))
        runtime.synthetic_guard.reset.assert_not_called()
        pending[1].target()
        self.assertFalse(runtime.macro_lock.active_label)
        runtime.synthetic_guard.reset.assert_called_once()



if __name__ == "__main__":
    unittest.main()
