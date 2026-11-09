from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import benchmark_organizer_mirror_windows as benchmark
from tools.benchmark_organizer_mirror_windows import (
    COUNTS, GESTURES, percentiles, summarize_fanout,
)


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

    def test_full_roster_fanout_latency_requires_all_clients(self):
        self.assertEqual(
            summarize_fanout(5, 3, [110.2, 204.1, 170.0]),
            {
                "sequential_fanout_trials": 5,
                "sequential_fanout_complete": 3,
                "sequential_fanout_incomplete": 2,
                "source_to_last_fixture_ack_ms": {
                    "count": 3, "p50_ms": 170.0,
                    "p95_ms": 204.1, "p99_ms": 204.1,
                },
            },
        )
        # A missing last-client acknowledgment cannot be advertised as
        # either a successful fanout or a fabricated 0ms latency.
        self.assertEqual(
            summarize_fanout(4, 0, []),
            {
                "sequential_fanout_trials": 4,
                "sequential_fanout_complete": 0,
                "sequential_fanout_incomplete": 4,
                "source_to_last_fixture_ack_ms": None,
            },
        )

    def test_fanout_evidence_refuses_inconsistent_completion_counts(self):
        for trials, complete, samples in (
            (3, 4, [1.0, 2.0, 3.0, 4.0]),
            (3, 2, [1.0]),
            (3, 0, [1.0]),
            (-1, 0, []),
            (True, 1, [1.0]),
        ):
            with self.subTest(trials=trials, complete=complete, samples=samples):
                with self.assertRaises(ValueError):
                    summarize_fanout(trials, complete, samples)

    def test_runner_never_reports_missing_desktop_as_success(self):
        # The former CLI returned zero for UNAVAILABLE_INTERACTIVE_DESKTOP
        # and made a missing Win32 interactive session look like PASS.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.json"
            for status, expected_code in (
                ("PASS", 0),
                ("FAIL", 1),
                ("NOT_RUN", 1),
                ("UNAVAILABLE_INTERACTIVE_DESKTOP", 1),
            ):
                with self.subTest(status=status):
                    argv = [
                        "bench", "--expected-sha", "a" * 40, "--iterations",
                        "1", "--output", str(path),
                    ]
                    with (
                        patch.object(sys, "argv", argv),
                        patch.object(benchmark, "run", return_value={"status": status}),
                        contextlib.redirect_stdout(io.StringIO()),
                    ):
                        self.assertEqual(benchmark.main(), expected_code)

    def test_tail_percentiles_use_nearest_rank(self):
        actual = percentiles([float(i) for i in range(1, 101)])
        self.assertEqual(
            actual, {"count": 100, "p50_ms": 50, "p95_ms": 95, "p99_ms": 99},
        )


if __name__ == "__main__":
    unittest.main()
