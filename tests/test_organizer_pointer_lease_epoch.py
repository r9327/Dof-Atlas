from __future__ import annotations

import threading
import unittest
from unittest.mock import Mock

from app.input.input_state import InputState, SyntheticInputGuard


class OrganizerPointerLeaseEpochTests(unittest.TestCase):
    def test_synthetic_guard_log_failure_cannot_strand_or_mask_release_2_to_8(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                logger = Mock()
                logger.debug.side_effect = RuntimeError("logger unavailable")
                guard = SyntheticInputGuard(logger)
                for _ in range(accounts):
                    guard.begin(0)
                self.assertEqual(guard._active_count, accounts)
                self.assertTrue(guard.is_synthetic_window())
                for _ in range(accounts):
                    guard.end(0)
                self.assertEqual(guard._active_count, 0)
                self.assertFalse(guard.is_synthetic_window())
                self.assertEqual(logger.debug.call_count, accounts * 2)
                guard.begin(0)
                guard.reset()
                self.assertEqual(guard._active_count, 0)
                self.assertFalse(guard.is_synthetic_window())

    def test_each_blocked_gesture_is_counted_per_lease_2_to_8(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                state = InputState()
                state.begin_mouse_block("Miroir")
                for gesture in range(accounts):
                    self.assertTrue(state.note_blocked_physical_gesture())
                self.assertEqual(state.end_mouse_block(), 0)
                self.assertTrue(state.last_release_interrupted())
                self.assertEqual(state.last_release_blocked_count(), accounts)
                state.begin_mouse_block("Nouvelle action")
                self.assertFalse(state.last_release_interrupted())
                self.assertEqual(state.last_release_blocked_count(), 0)
                self.assertEqual(state.end_mouse_block(), 0)
                self.assertEqual(state.last_release_blocked_count(), 0)

    def test_blocked_gestures_do_not_cross_stop_generation_or_thread(self):
        state = InputState()
        state.begin_mouse_block("ancien")
        for _ in range(4):
            state.note_blocked_physical_gesture()
        state.clear_mouse_block()
        state.begin_mouse_block("nouveau")
        state.note_blocked_physical_gesture()
        state.note_blocked_physical_gesture()
        self.assertEqual(state.end_mouse_block(), 0)
        self.assertEqual(state.last_release_blocked_count(), 2)
        # The old generation's release cannot reuse the new count.
        self.assertEqual(state.end_mouse_block(), 0)
        self.assertEqual(state.last_release_blocked_count(), 0)
        recorded = []
        thread = threading.Thread(target=lambda: recorded.append(
            state.last_release_blocked_count()
        ))
        thread.start()
        thread.join(2)
        self.assertEqual(recorded, [0])

    def test_release_collision_snapshot_is_atomic_for_2_to_8(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                state = InputState()
                self.assertFalse(state.last_release_interrupted())
                state.begin_mouse_block("Miroir")
                # The hook sees a new DOWN AFTER the worker's last poll,
                # immediately before the lease release.
                self.assertTrue(state.note_blocked_physical_gesture())
                self.assertEqual(state.end_mouse_block(), 0)
                self.assertFalse(state.is_mouse_blocked())
                self.assertFalse(state.mouse_block_interrupted())
                self.assertTrue(state.last_release_interrupted())
                state.begin_mouse_block("Miroir suivant")
                self.assertFalse(state.last_release_interrupted())
                self.assertEqual(state.end_mouse_block(), 0)
                self.assertFalse(state.last_release_interrupted())

    def test_stale_epoch_and_foreign_thread_cannot_steal_collision_snapshot(self):
        state = InputState()
        state.begin_mouse_block("Ancien")
        state.note_blocked_physical_gesture()
        state.clear_mouse_block()
        state.begin_mouse_block("Nouveau")
        observed = []
        def foreign():
            observed.append((state.end_mouse_block(), state.last_release_interrupted()))
        foreign_thread = threading.Thread(target=foreign)
        foreign_thread.start()
        foreign_thread.join(2)
        self.assertEqual(observed, [(1, False)])
        self.assertFalse(state.last_release_interrupted())
        state.note_blocked_physical_gesture()
        self.assertEqual(state.end_mouse_block(), 0)
        self.assertTrue(state.last_release_interrupted())
        # Stale previous generation is last on the current thread's stack.
        self.assertEqual(state.end_mouse_block(), 0)
        self.assertFalse(state.last_release_interrupted())

    def test_nested_release_reports_collision_without_clearing_live_lease(self):
        state = InputState()
        state.begin_mouse_block("Miroir outer")
        state.begin_mouse_block("Miroir inner")
        state.note_blocked_physical_gesture()
        self.assertEqual(state.end_mouse_block(), 1)
        self.assertTrue(state.last_release_interrupted())
        self.assertTrue(state.mouse_block_interrupted())
        self.assertEqual(state.end_mouse_block(), 0)
        self.assertTrue(state.last_release_interrupted())
        self.assertFalse(state.mouse_block_interrupted())

    def test_stale_worker_cannot_unblock_new_mirror_after_emergency_stop(self):
        for old_label, new_label in (
            ("Miroir molette", "Miroir"),
            ("Switch clique", "Miroir molette"),
            ("Miroir", "Switch clique"),
        ):
            with self.subTest(old_label=old_label, new_label=new_label):
                state = InputState()
                old_started = threading.Event()
                release_old = threading.Event()
                old_results = []

                def old_worker():
                    self.assertEqual(state.begin_mouse_block(old_label), 1)
                    old_started.set()
                    self.assertTrue(release_old.wait(2))
                    old_results.append(state.end_mouse_block())

                worker = threading.Thread(target=old_worker)
                worker.start()
                try:
                    self.assertTrue(old_started.wait(2))
                    self.assertTrue(state.is_mouse_blocked())
                    state.clear_mouse_block()  # Emergency Stop, another thread.
                    self.assertFalse(state.is_mouse_blocked())
                    self.assertEqual(state.begin_mouse_block(new_label), 1)
                    release_old.set()
                    worker.join(2)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(old_results, [1])
                    self.assertTrue(state.is_mouse_blocked())
                    self.assertEqual(state.mouse_block_label(), new_label)
                    self.assertEqual(state.end_mouse_block(), 0)
                    self.assertFalse(state.is_mouse_blocked())
                finally:
                    release_old.set()
                    worker.join(2)

    def test_nested_blocks_release_in_owner_order(self):
        state = InputState()
        self.assertEqual(state.begin_mouse_block("Miroir"), 1)
        self.assertEqual(state.begin_mouse_block("Switch clique"), 2)
        self.assertEqual(state.end_mouse_block(), 1)
        self.assertTrue(state.is_mouse_blocked())
        self.assertEqual(state.end_mouse_block(), 0)
        self.assertFalse(state.is_mouse_blocked())
        self.assertEqual(state.mouse_block_label(), "")

    def test_wrong_thread_cannot_release_live_pointer_block(self):
        state = InputState()
        state.begin_mouse_block("Miroir molette")
        observed = []
        thread = threading.Thread(target=lambda: observed.append(
            state.end_mouse_block()
        ))
        thread.start()
        thread.join(2)
        self.assertEqual(observed, [1])
        self.assertTrue(state.is_mouse_blocked())
        self.assertEqual(state.end_mouse_block(), 0)

    def test_same_thread_stop_and_reentry_never_revives_old_lease(self):
        state = InputState()
        self.assertEqual(state.begin_mouse_block("ancien"), 1)
        state.clear_mouse_block()
        self.assertEqual(state.begin_mouse_block("nouveau"), 1)
        self.assertEqual(state.end_mouse_block(), 0)
        self.assertEqual(state.end_mouse_block(), 0)
        self.assertFalse(state.is_mouse_blocked())

    def test_expected_epoch_rejects_stale_hook_events_after_stop(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                state = InputState()
                self.assertIsNone(state.mouse_block_epoch_if_active())
                state.begin_mouse_block("ancien")
                old_epoch = state.mouse_block_epoch_if_active()
                self.assertIsInstance(old_epoch, int)
                state.clear_mouse_block()
                state.begin_mouse_block("nouveau")
                self.assertGreater(state.mouse_block_epoch_if_active(), old_epoch)
                # Old native DOWN must not cancel a new replay worker.
                self.assertFalse(state.note_blocked_physical_gesture(
                    expected_epoch=old_epoch,
                ))
                self.assertFalse(state.mouse_block_interrupted())
                self.assertEqual(state.end_mouse_block(), 0)
                self.assertEqual(state.last_release_blocked_count(), 0)
                self.assertIsNone(state.mouse_block_epoch_if_active())

    def test_sequential_pointer_leases_reject_delayed_hook_probe_2_to_8(self):
        # A native hook may sample the old lease just before that worker
        # releases it; the next worker can start without an emergency Stop.
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                state = InputState()
                state.begin_mouse_block("Miroir precedent")
                old_epoch = state.mouse_block_epoch_if_active()
                self.assertEqual(state.end_mouse_block(), 0)
                state.begin_mouse_block("Miroir suivant")
                new_epoch = state.mouse_block_epoch_if_active()
                self.assertNotEqual(old_epoch, new_epoch)
                self.assertFalse(state.note_blocked_physical_gesture(
                    expected_epoch=old_epoch,
                ))
                self.assertFalse(state.mouse_block_interrupted())
                self.assertTrue(state.note_blocked_physical_gesture(
                    expected_epoch=new_epoch,
                ))
                self.assertEqual(state.end_mouse_block(), 0)
                self.assertTrue(state.last_release_interrupted())
                self.assertEqual(state.last_release_blocked_count(), 1)

    def test_nested_pointer_blocks_keep_the_outer_epoch_2_to_8(self):
        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                state = InputState()
                state.begin_mouse_block("Miroir outer")
                original_epoch = state.mouse_block_epoch_if_active()
                state.begin_mouse_block("Miroir inner")
                self.assertEqual(state.mouse_block_epoch_if_active(), original_epoch)
                self.assertEqual(state.end_mouse_block(), 1)
                self.assertEqual(state.mouse_block_epoch_if_active(), original_epoch)
                self.assertEqual(state.end_mouse_block(), 0)
                state.begin_mouse_block("Next independent gesture")
                self.assertNotEqual(
                    state.mouse_block_epoch_if_active(), original_epoch,
                )
                self.assertEqual(state.end_mouse_block(), 0)

    def test_lease_generation_can_be_claimed_only_while_active(self):
        for count in (2, 4, 6, 8):
            with self.subTest(clients=count):
                state = InputState()
                self.assertFalse(state.note_blocked_physical_gesture(
                    expected_epoch=0,
                ))
                state.begin_mouse_block("Miroir")
                generation = state.mouse_block_epoch_if_active()
                for _ in range(count):
                    self.assertTrue(state.note_blocked_physical_gesture(
                        expected_epoch=generation,
                    ))
                self.assertTrue(state.mouse_block_interrupted())
                self.assertEqual(state.end_mouse_block(), 0)
                self.assertEqual(state.last_release_blocked_count(), count)
                self.assertFalse(state.note_blocked_physical_gesture(
                    expected_epoch=generation,
                ))
                self.assertIsNone(state.mouse_block_epoch_if_active())

    def test_repeated_stop_invalidates_all_old_nested_leases(self):
        state = InputState()
        state.begin_mouse_block("ancien")
        state.begin_mouse_block("ancien-nested")
        state.clear_mouse_block()
        state.clear_mouse_block()
        state.begin_mouse_block("nouveau")
        # The new lease is the innermost one and must be released normally.
        self.assertEqual(state.end_mouse_block(), 0)
        self.assertEqual(state.end_mouse_block(), 0)
        self.assertEqual(state.end_mouse_block(), 0)


    def test_native_hook_handoff_does_not_cancel_new_lease(self):
        import ctypes
        from types import SimpleNamespace
        from unittest.mock import patch
        from app.input.mouse_hooks import (
            MouseHook, MSLLHOOKSTRUCT, WM_LBUTTONDOWN, WM_LBUTTONUP,
        )

        for accounts in (2, 4, 6, 8):
            with self.subTest(accounts=accounts):
                state = InputState()
                state.begin_mouse_block("ancien")
                old_epoch = state.mouse_block_epoch_if_active()
                original_note = state.note_blocked_physical_gesture

                def switch_lease(*, expected_epoch=None):
                    if expected_epoch == old_epoch:
                        self.assertEqual(state.end_mouse_block(), 0)
                        self.assertEqual(state.begin_mouse_block("nouveau"), 1)
                    return original_note(expected_epoch=expected_epoch)

                hook = MouseHook(state, Mock(), Mock(), Mock(return_value=False))
                event = MSLLHOOKSTRUCT()
                event.pt.x, event.pt.y = 20, 25
                native = Mock(return_value=37)
                with (
                    patch.object(state, "note_blocked_physical_gesture",
                                 side_effect=switch_lease),
                    patch.object(
                        ctypes, "windll",
                        SimpleNamespace(user32=SimpleNamespace(CallNextHookEx=native)),
                        create=True,
                    ),
                ):
                    ptr = ctypes.addressof(event)
                    self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, ptr), 1)
                    self.assertFalse(state.mouse_block_interrupted())
                    self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, ptr), 1)
                # A stale hook event cannot interrupt an unrelated fresh lease.
                # The intercepted source gesture remains a known MIRR-007 limit.
                native.assert_not_called()
                self.assertFalse(hook._consumed_releases)
                self.assertEqual(state.end_mouse_block(), 0)
                self.assertFalse(state.last_release_interrupted())
                self.assertEqual(state.last_release_blocked_count(), 0)

    def test_native_hook_handoff_keeps_click_if_old_lease_ended(self):
        import ctypes
        from types import SimpleNamespace
        from unittest.mock import patch
        from app.input.mouse_hooks import (
            MouseHook, MSLLHOOKSTRUCT, WM_LBUTTONDOWN, WM_LBUTTONUP,
        )

        state = InputState()
        state.begin_mouse_block("ancien")
        old_epoch = state.mouse_block_epoch_if_active()
        original_note = state.note_blocked_physical_gesture

        def release_before_claim(*, expected_epoch=None):
            if expected_epoch == old_epoch:
                self.assertEqual(state.end_mouse_block(), 0)
            return original_note(expected_epoch=expected_epoch)

        hook = MouseHook(state, Mock(), Mock(), Mock(return_value=False))
        event = MSLLHOOKSTRUCT()
        native = Mock(return_value=37)
        with (
            patch.object(state, "note_blocked_physical_gesture",
                         side_effect=release_before_claim),
            patch.object(
                ctypes, "windll",
                SimpleNamespace(user32=SimpleNamespace(CallNextHookEx=native)),
                create=True,
            ),
        ):
            ptr = ctypes.addressof(event)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONDOWN, ptr), 37)
            self.assertEqual(hook._mouse_proc(0, WM_LBUTTONUP, ptr), 37)
        self.assertFalse(hook._consumed_releases)
        self.assertFalse(state.is_mouse_blocked())
        self.assertEqual(native.call_count, 2)


if __name__ == "__main__":
    unittest.main()
