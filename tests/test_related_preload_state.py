from __future__ import annotations

import unittest

from app.modules.encyclopedia.views.related_preload_state import (
    RelatedPreloadGate,
    RelatedPreloadState,
)


class RelatedPreloadStateTests(unittest.TestCase):
    def test_success_moves_loading_to_ready_and_does_not_start_second_worker(self) -> None:
        gate = RelatedPreloadGate()
        workers = 0

        if gate.begin():
            workers += 1
        self.assertEqual(gate.state, RelatedPreloadState.LOADING)
        self.assertEqual(workers, 1)

        gate.mark_ready()
        self.assertEqual(gate.state, RelatedPreloadState.READY)
        self.assertFalse(gate.begin())
        self.assertEqual(workers, 1)
        self.assertEqual(gate.attempts, 1)

    def test_permanent_failure_is_terminal_and_bounds_worker_count(self) -> None:
        gate = RelatedPreloadGate()
        workers = 0

        for _timer_tick in range(50):
            if gate.begin():
                workers += 1
                gate.mark_failed()

        self.assertEqual(workers, 1)
        self.assertEqual(gate.attempts, 1)
        self.assertEqual(gate.state, RelatedPreloadState.FAILED)

    def test_double_request_does_not_start_concurrent_preloads(self) -> None:
        gate = RelatedPreloadGate()

        self.assertTrue(gate.begin())
        self.assertFalse(gate.begin())
        self.assertEqual(gate.state, RelatedPreloadState.LOADING)
        self.assertEqual(gate.attempts, 1)


if __name__ == "__main__":
    unittest.main()
