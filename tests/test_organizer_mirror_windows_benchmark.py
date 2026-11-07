from __future__ import annotations

import unittest

from tools.benchmark_organizer_mirror_windows import COUNTS, GESTURES, percentiles


class OrganizerMirrorWindowsBenchmarkTests(unittest.TestCase):
    def test_supported_sizes_and_event_matrix_are_bounded(self):
        self.assertEqual(COUNTS, (1, 2, 4, 6, 8))
        self.assertEqual(GESTURES, ("left", "right", "double", "wheel", "key"))
        self.assertEqual(sum(COUNTS) * len(GESTURES) * 6, 630)

    def test_unacknowledged_input_does_not_appear_in_latency_distribution(self):
        self.assertIsNone(percentiles([]))
        self.assertEqual(
            percentiles([20, 10, 30, 40, 50]),
            {"count": 5, "p50_ms": 30, "p95_ms": 50, "p99_ms": 50},
        )

    def test_tail_percentiles_use_nearest_rank(self):
        actual = percentiles([float(i) for i in range(1, 101)])
        self.assertEqual(
            actual, {"count": 100, "p50_ms": 50, "p95_ms": 95, "p99_ms": 99},
        )


if __name__ == "__main__":
    unittest.main()
