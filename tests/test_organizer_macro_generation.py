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



    def test_concurrent_reservations_admit_only_one_generation_2_4_6_8(self):
        # A high load on Organizer must never admit two identically named
        # SendInput workers, nor reuse a previous generation number.
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                lock = MacroLock(Mock())
                previous = 0
                for _round in range(5):
                    barrier = threading.Barrier(accounts + 1)
                    admitted = []
                    list_lock = threading.Lock()

                    def contender():
                        barrier.wait(2)
                        claim = lock.try_begin_generation("Miroir")
                        with list_lock:
                            admitted.append(claim)

                    workers = [threading.Thread(target=contender)
                               for _ in range(accounts)]
                    for worker in workers:
                        worker.start()
                    try:
                        barrier.wait(2)
                        for worker in workers:
                            worker.join(2)
                        self.assertTrue(all(not w.is_alive() for w in workers))
                        claimed = [value for value in admitted
                                   if type(value) is int]
                        self.assertEqual(len(admitted), accounts)
                        self.assertEqual(len(claimed), 1)
                        self.assertGreater(claimed[0], previous)
                        previous = claimed[0]
                        lock.end("Miroir", generation=previous)
                    finally:
                        for worker in workers:
                            worker.join(2)
                self.assertFalse(lock.active_label)



    def test_cancelled_generation_wait_is_bounded_when_shared_stop_was_cleared(self):
        for account_count in (2, 4, 6, 8):
            with self.subTest(accounts=account_count):
                lock = MacroLock(Mock())
                self.assertTrue(lock.try_begin("Miroir"))
                stale_generation = lock.active_generation
                waiting = threading.Event()
                done = threading.Event()
                result = []

                def old_worker():
                    self.assertTrue(lock.bind_worker("Miroir", stale_generation))
                    waiting.set()
                    result.append(lock.wait(500))
                    lock.unbind_worker()
                    done.set()

                worker = threading.Thread(target=old_worker)
                worker.start()
                try:
                    self.assertTrue(waiting.wait(1))
                    lock.request_stop()
                    lock.end("Miroir", generation=stale_generation)
                    self.assertTrue(lock.try_begin("Miroir"))
                    self.assertTrue(done.wait(0.25))
                    self.assertEqual(result, [True])
                    self.assertTrue(lock.owns(
                        "Miroir", lock.active_generation,
                    ))
                finally:
                    lock.request_stop()
                    worker.join(1)
                    lock.end("Miroir", generation=lock.active_generation)

    def test_wait_uses_bounded_native_event_slices_and_preserves_duration(self):
        from unittest.mock import patch as mock_patch

        lock = MacroLock(Mock())
        self.assertTrue(lock.try_begin("Miroir"))
        observed = []
        original_wait = lock.stop_event.wait

        def observed_wait(seconds):
            observed.append(seconds)
            return original_wait(seconds)

        with mock_patch.object(lock.stop_event, "wait", side_effect=observed_wait):
            self.assertFalse(lock.wait(86))
        self.assertGreaterEqual(len(observed), 3)
        self.assertTrue(all(0 < value <= 0.025 for value in observed))
        self.assertFalse(lock.wait(0))
        lock.request_stop()
        self.assertTrue(lock.wait(2000))



    def test_stop_reasserts_event_if_concurrent_start_clears_first_signal(self):
        from unittest.mock import patch as mock_patch

        for count in (2, 4, 6, 8):
            with self.subTest(accounts=count):
                lock = MacroLock(Mock())
                native_set = lock.stop_event.set
                calls = []

                def interleaved_stop_signal():
                    native_set()
                    calls.append("set")
                    if len(calls) == 1:
                        # Simulate a scheduler switch before Stop acquires
                        # the lease lock and before the final status report.
                        self.assertIsInstance(
                            lock.try_begin_generation("Miroir"), int,
                        )
                        self.assertFalse(lock.should_stop())

                with mock_patch.object(
                    lock.stop_event, "set", side_effect=interleaved_stop_signal,
                ):
                    lock.request_stop("raccourci")
                self.assertEqual(calls, ["set", "set"])
                self.assertTrue(lock.should_stop())
                self.assertEqual(lock.active_label, "Miroir")
                lock.end("Miroir", generation=lock.active_generation)



    def test_macro_lease_snapshot_keeps_label_and_generation_together(self):
        lock = MacroLock(Mock())
        self.assertIsNone(lock.snapshot_active())
        first = lock.try_begin_generation("Miroir")
        self.assertEqual(lock.snapshot_active(), ("Miroir", first))
        lock.request_stop()
        lock.end("Miroir", generation=first)
        second = lock.try_begin_generation("Miroir")
        self.assertEqual(lock.snapshot_active(), ("Miroir", second))
        self.assertGreater(second, first)
        lock.end("Miroir", generation=second)
        self.assertIsNone(lock.snapshot_active())



    def test_end_cleanup_blocks_reuse_until_old_owner_reset_finishes(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                lock = MacroLock(Mock())
                old = lock.try_begin_generation("Miroir")
                inside_cleanup = threading.Event()
                permit_cleanup = threading.Event()
                new_admitted = threading.Event()
                new_attempted = threading.Event()
                result = []

                def slow_reset():
                    inside_cleanup.set()
                    self.assertTrue(permit_cleanup.wait(2))
                    result.append("old_reset")

                def old_cleanup():
                    lock.end("Miroir", generation=old, on_owner_end=slow_reset)

                def new_admission():
                    new_attempted.set()
                    generation = lock.try_begin_generation("Miroir")
                    result.append(("new", generation))
                    new_admitted.set()
                    if generation is not None:
                        lock.end("Miroir", generation=generation)

                worker = threading.Thread(target=old_cleanup)
                newcomer = threading.Thread(target=new_admission)
                worker.start()
                try:
                    self.assertTrue(inside_cleanup.wait(2))
                    newcomer.start()
                    self.assertTrue(new_attempted.wait(2))
                    # A new macro cannot be admitted while the previous
                    # owner's reset is still running under the lease lock.
                    self.assertFalse(new_admitted.wait(0.02))
                    permit_cleanup.set()
                    worker.join(2)
                    newcomer.join(2)
                    self.assertFalse(worker.is_alive())
                    self.assertFalse(newcomer.is_alive())
                    self.assertEqual(result[0], "old_reset")
                    self.assertEqual(result[1][0], "new")
                    self.assertGreater(result[1][1], old)
                finally:
                    permit_cleanup.set()
                    worker.join(2)
                    if newcomer.ident is not None:
                        newcomer.join(2)

    def test_stale_worker_cleanup_cannot_reset_new_guard(self):
        lock = MacroLock(Mock())
        old = lock.try_begin_generation("Miroir")
        lock.end("Miroir", generation=old)
        current = lock.try_begin_generation("Miroir")
        stale_reset = Mock(side_effect=AssertionError("old reset leaked"))
        lock.end("Miroir", generation=old, on_owner_end=stale_reset)
        stale_reset.assert_not_called()
        self.assertTrue(lock.owns("Miroir", current))
        good_reset = Mock()
        lock.end("Miroir", generation=current, on_owner_end=good_reset)
        good_reset.assert_called_once_with()
        self.assertIsNone(lock.snapshot_active())



    def test_owner_cleanup_exception_is_logged_and_does_not_stick_lease(self):
        logger = Mock()
        lock = MacroLock(logger)
        old = lock.try_begin_generation("Miroir")
        failed_reset = Mock(side_effect=RuntimeError("synthetic guard failure"))
        lock.end("Miroir", generation=old, on_owner_end=failed_reset)
        failed_reset.assert_called_once_with()
        logger.exception.assert_called_once_with(
            "Macro nettoyage propriétaire impossible: action=%s", "Miroir",
        )
        self.assertIsNone(lock.snapshot_active())
        new = lock.try_begin_generation("Miroir")
        self.assertGreater(new, old)
        lock.end("Miroir", generation=new)
        self.assertIsNone(lock.snapshot_active())



if __name__ == "__main__":
    unittest.main()
