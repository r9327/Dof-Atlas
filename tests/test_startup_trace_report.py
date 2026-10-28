from __future__ import annotations

import json
import unittest
from tools.startup_trace_report import collect, durations_ms, percentile


class StartupTraceReportTests(unittest.TestCase):
    def test_groups_sessions_without_joining_unrelated_processes(self) -> None:
        rows = [
            {"session": "one", "event": "launcher_entry", "t_ns": 100},
            {"session": "two", "event": "home_event_loop", "t_ns": 250},
            {"session": "one", "event": "home_event_loop", "t_ns": 2_000_100},
        ]
        sessions = collect([json.dumps(x) for x in rows] + ["corrupt"])
        self.assertEqual(durations_ms(sessions, "launcher_entry", "home_event_loop"), [2.0])

    def test_rejects_backwards_clocks(self) -> None:
        rows = [
            {"session": "one", "event": "launcher_entry", "t_ns": 100},
            {"session": "one", "event": "home_event_loop", "t_ns": 1},
        ]
        self.assertEqual(durations_ms(collect([json.dumps(x) for x in rows]),
                                      "launcher_entry", "home_event_loop"), [])

    def test_nearest_rank_p95(self) -> None:
        self.assertEqual(percentile([10, 20, 30, 40, 50], 95), 50)


if __name__ == "__main__":
    unittest.main()
