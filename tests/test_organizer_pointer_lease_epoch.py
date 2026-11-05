from __future__ import annotations

import threading
import unittest

from app.input.input_state import InputState


class OrganizerPointerLeaseEpochTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
