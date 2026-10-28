from __future__ import annotations

import json
import unittest
from tools.startup_trace_report import collect, collect_counters, durations_ms, percentile, summarize


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

    def test_counters_only_from_completed_operations(self) -> None:
        rows = [
            {"session": "a", "event": "download_archive_ready", "network_bytes": 0, "t_ns": 1},
            {"session": "a", "event": "install_stage_verified", "reused_bytes": 1024,
             "decompressed_bytes": 12, "staged_bytes": 1036, "t_ns": 2},
            {"session": "b", "event": "download_archive_ready", "network_bytes": 34, "t_ns": 1},
            {"session": "b", "event": "full_download_begin", "network_bytes": 1000, "t_ns": 2},
        ]
        lines = [json.dumps(row) for row in rows]
        totals = collect_counters(lines)
        self.assertEqual(totals["a"]["network_bytes"], 0)
        self.assertEqual(totals["a"]["reused_bytes"], 1024)
        self.assertEqual(totals["b"]["network_bytes"], 34)
        self.assertNotIn("reused_bytes", totals["b"])
        data = summarize(lines)
        self.assertEqual(data["completed_operation_counters"]["network_bytes"]["p50"], 17)
        self.assertEqual(data["completed_operation_counters"]["reused_bytes"]["n"], 1)

    def test_first_paint_not_inferred_from_home_event_loop(self) -> None:
        lines = [
            json.dumps({"session": "a", "event": "launcher_entry", "t_ns": 100}),
            json.dumps({"session": "a", "event": "home_event_loop", "t_ns": 200}),
        ]
        self.assertIsNone(summarize(lines)["segments"]["launcher_entry_to_home_first_paint"])

    def test_nearest_rank_p95(self) -> None:
        self.assertEqual(percentile([10, 20, 30, 40, 50], 95), 50)


if __name__ == "__main__":
    unittest.main()
