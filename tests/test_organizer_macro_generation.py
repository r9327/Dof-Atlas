from __future__ import annotations

import logging
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.core.macro_lock import MacroLock
from app.core.runtime_state import AtlasRuntime


class MacroGenerationOwnershipTests(unittest.TestCase):
    def test_mirror_stays_disarmed_until_click_or_shortcut_and_disarms_after_stop(self):
        for count in (2, 4, 6, 8):
            with self.subTest(count=count):
                clients = [SimpleNamespace(handle=101 + index) for index in range(count)]
                settings = SimpleNamespace(
                    macro_mode="mirror", primary_handle=101, clients=clients,
                )
                runtime = SimpleNamespace(
                    settings=settings, _mirror_armed=False, _running=True,
                    _admin_ok=True, macro_lock=MacroLock(Mock()),
                    _emit_active=Mock(), _emit_status=Mock(),
                )
                runtime.emergency_stop = lambda reason, *, latch=False: (
                    setattr(runtime, "_mirror_armed", False),
                    runtime.macro_lock.request_stop(reason, latch=latch),
                )
                # Opening the mode is never authorization to mirror input.
                with patch("app.windows.unity_windows.foreground_window") as native:
                    self.assertFalse(AtlasRuntime._handle_mirror_key(
                        runtime, 0x41, True,
                    ))
                native.assert_not_called()
                self.assertTrue(AtlasRuntime.toggle_mirror(runtime))
                self.assertTrue(runtime._mirror_armed)
                self.assertFalse(AtlasRuntime.toggle_mirror(runtime))
                self.assertFalse(runtime._mirror_armed)
                self.assertTrue(runtime.macro_lock.should_stop())
                self.assertTrue(AtlasRuntime.toggle_mirror(runtime))
                self.assertTrue(runtime._mirror_armed)
                runtime.macro_lock.request_stop("urgence", latch=True)
                self.assertFalse(AtlasRuntime.toggle_mirror(runtime))
                self.assertFalse(runtime._mirror_armed)

    def test_mirror_requires_valid_favorite_and_runtime_ready(self):
        settings = SimpleNamespace(
            macro_mode="mirror", primary_handle=999,
            clients=[SimpleNamespace(handle=101), SimpleNamespace(handle=102)],
        )
        runtime = SimpleNamespace(
            settings=settings, _mirror_armed=False, _running=True, _admin_ok=True,
            macro_lock=MacroLock(Mock()),
            _emit_active=Mock(), _emit_status=Mock(),
        )
        self.assertFalse(AtlasRuntime.toggle_mirror(runtime))
        self.assertFalse(runtime._mirror_armed)
        settings.primary_handle = 101
        runtime._running = False
        self.assertFalse(AtlasRuntime.toggle_mirror(runtime))
        runtime._emit_active.assert_not_called()
        runtime._running = True
        self.assertTrue(AtlasRuntime.toggle_mirror(runtime))

    def test_mirror_refuses_malformed_or_duplicate_native_rosters_before_arm(self):
        candidates = (
            (101, 101),
            (101, True),
            (101, 101.0),
            (101, 2**64),
            (101, None),
            (101, "202"),
            (101,),
            tuple(range(101, 110)),
        )
        for handles in candidates:
            with self.subTest(handles=handles):
                profile = SimpleNamespace(
                    macro_mode="mirror", primary_handle=101,
                    clients=[SimpleNamespace(handle=hwnd) for hwnd in handles],
                )
                runtime = SimpleNamespace(
                    settings=profile, _mirror_armed=False, _running=True,
                    _admin_ok=True, macro_lock=MacroLock(Mock()),
                    _emit_active=Mock(), _emit_status=Mock(),
                )
                self.assertFalse(AtlasRuntime.toggle_mirror(runtime))
                self.assertFalse(runtime._mirror_armed)
                runtime._emit_active.assert_not_called()
                self.assertIn("Miroir indisponible", runtime._emit_status.call_args.args[0])

    def test_mirror_refuses_empty_runtime_bindings_even_if_stale_roster_remains(self):
        runtime = SimpleNamespace(
            settings=SimpleNamespace(
                macro_mode="mirror", primary_handle=101,
                clients=[SimpleNamespace(handle=101), SimpleNamespace(handle=202)],
            ),
            _mirror_armed=False, _running=True, _admin_ok=True,
            _runtime_bindings_available=False,
            macro_lock=MacroLock(Mock()), _emit_active=Mock(), _emit_status=Mock(),
        )
        self.assertFalse(AtlasRuntime.toggle_mirror(runtime))
        self.assertFalse(runtime._mirror_armed)
        runtime._emit_active.assert_not_called()

    def test_emergency_stop_stays_latched_until_safe_explicit_resume(self):
        for accounts in (1, 2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                lock = MacroLock(Mock())
                first = lock.try_begin_generation("Miroir")
                self.assertIs(type(first), int)
                lock.request_stop("bouton stop", latch=True)
                self.assertTrue(lock.emergency_latched)
                self.assertTrue(lock.should_stop())
                self.assertIsNone(lock.try_begin_generation("Auto zaap"))
                # A live worker cannot be revived while it is finishing.
                self.assertFalse(lock.resume_after_stop())
                self.assertTrue(lock.emergency_latched)
                lock.end("Miroir", generation=first)
                self.assertIsNone(lock.try_begin_generation("Auto groupe"))
                self.assertTrue(lock.resume_after_stop())
                self.assertFalse(lock.emergency_latched)
                self.assertFalse(lock.should_stop())
                second = lock.try_begin_generation("Auto zaap")
                self.assertIs(type(second), int)
                self.assertGreater(second, first)
                lock.end("Auto zaap", generation=second)

    def test_temporary_reconfiguration_stop_keeps_legacy_restart_semantics(self):
        lock = MacroLock(Mock())
        first = lock.try_begin_generation("Miroir")
        lock.request_stop("changement profil")
        self.assertFalse(lock.emergency_latched)
        lock.end("Miroir", generation=first)
        self.assertIs(type(lock.try_begin_generation("Miroir")), int)

    def test_macro_lock_state_survives_failed_logger_during_admission_stop_cleanup(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                logger = Mock()
                for level in ("debug", "info", "warning", "exception"):
                    getattr(logger, level).side_effect = RuntimeError(
                        "diagnostic sink unavailable"
                    )
                lock = MacroLock(logger)
                first = lock.try_begin_generation("Miroir")
                self.assertIs(type(first), int)
                self.assertTrue(lock.owns("Miroir", first))
                # Busy admission and stale completion are rejected even
                # when their warning/debug sinks both raise.
                self.assertIsNone(lock.try_begin_generation("Miroir"))
                lock.end("Miroir", generation=first + 1)
                lock.end("wrong label", generation=first)
                self.assertTrue(lock.owns("Miroir", first))

                lock.request_stop("test stop")
                self.assertTrue(lock.should_stop())

                def broken_cleanup():
                    raise RuntimeError("synthetic guard cleanup failed")

                lock.end(
                    "Miroir", generation=first, on_owner_end=broken_cleanup,
                )
                self.assertIsNone(lock.snapshot_active())
                self.assertEqual(lock.active_label, "")
                # Even after Stop and failed cleanup logging, the next
                # intentional admission owns a fresh generation.
                second = lock.try_begin_generation("Miroir")
                self.assertIs(type(second), int)
                self.assertGreater(second, first)
                self.assertFalse(lock.should_stop())
                self.assertTrue(lock.owns("Miroir", second))
                lock.end("Miroir", generation=second)
                self.assertIsNone(lock.snapshot_active())

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



    def test_pointer_collision_interrupts_bounded_settle_wait_2_4_6_8(self):
        from app.input.input_state import InputState

        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                lock = MacroLock(Mock())
                state = InputState()
                generation = lock.try_begin_generation("Miroir")
                self.assertIs(type(generation), int)
                state.begin_mouse_block("Miroir")
                observed = []

                def collide_after_first_slice(seconds):
                    observed.append(seconds)
                    state.note_blocked_physical_gesture()
                    return False

                try:
                    with patch.object(
                        lock.stop_event, "wait",
                        side_effect=collide_after_first_slice,
                    ):
                        self.assertTrue(lock.wait(
                            5000, interrupted=state.mouse_block_interrupted,
                        ))
                    self.assertEqual(len(observed), 1)
                    self.assertGreater(observed[0], 0)
                    self.assertLessEqual(observed[0], 0.005)
                    self.assertTrue(lock.owns("Miroir", generation))
                    self.assertFalse(lock.should_stop())
                finally:
                    state.end_mouse_block()
                    lock.end("Miroir", generation=generation)

    def test_mirror_collision_wait_is_fast_but_normal_wait_stays_bounded(self):
        from app.input.input_state import InputState

        for accounts in (1, 2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                lock = MacroLock(Mock())
                state = InputState()
                generation = lock.try_begin_generation("Miroir")
                state.begin_mouse_block("Miroir")
                slices = []

                def collect_slice(seconds):
                    slices.append(seconds)
                    if len(slices) == 1:
                        state.note_blocked_physical_gesture()
                    return False

                try:
                    with patch.object(lock.stop_event, "wait",
                                      side_effect=collect_slice):
                        self.assertTrue(lock.wait(
                            2000, interrupted=state.mouse_block_interrupted,
                        ))
                    self.assertEqual(len(slices), 1)
                    self.assertLessEqual(slices[0], 0.005)
                    self.assertTrue(state.mouse_block_interrupted())
                    self.assertTrue(lock.owns("Miroir", generation))
                    self.assertFalse(lock.should_stop())
                finally:
                    state.end_mouse_block()
                    lock.end("Miroir", generation=generation)

        lock = MacroLock(Mock())
        slices = []
        original_wait = lock.stop_event.wait

        def record_slice(seconds):
            slices.append(seconds)
            return original_wait(seconds)

        with patch.object(lock.stop_event, "wait",
                          side_effect=record_slice):
            self.assertFalse(lock.wait(32))
        self.assertTrue(slices)
        self.assertGreater(slices[0], 0.005)
        self.assertLessEqual(slices[0], 0.025)

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



    def test_runtime_failed_synthetic_reset_keeps_next_macro_admissible(self):
        import app.core.runtime_state as runtime_module

        class ImmediateWorker:
            def __init__(self, *, target, name, daemon):
                self.target = target

            def start(self):
                self.target()

            def is_alive(self):
                return False

        logger = Mock()
        runtime = SimpleNamespace(
            logger=logging.getLogger("macro-reset-failure-runtime"),
            macro_lock=MacroLock(logger),
            synthetic_guard=Mock(),
            _threads=[],
            _emit_status=Mock(),
        )
        runtime.synthetic_guard.reset.side_effect = RuntimeError("guard error")
        completed = []
        with patch.object(runtime_module.threading, "Thread", ImmediateWorker):
            self.assertTrue(AtlasRuntime._spawn_macro(
                runtime, "Miroir", lambda: completed.append("first"),
            ))
            self.assertIsNone(runtime.macro_lock.snapshot_active())
            self.assertTrue(AtlasRuntime._spawn_macro(
                runtime, "Miroir", lambda: completed.append("second"),
            ))
        self.assertEqual(completed, ["first", "second"])
        self.assertIsNone(runtime.macro_lock.snapshot_active())
        self.assertEqual(logger.exception.call_count, 2)



if __name__ == "__main__":
    unittest.main()
