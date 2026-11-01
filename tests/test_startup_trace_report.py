from __future__ import annotations

import json
import unittest
from tools.startup_trace_report import compare_traces, collect, collect_counters, durations_ms, percentile, summarize


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

    def test_relocation_duration_requires_a_committed_copy(self) -> None:
        rows = [
            {"session": "success", "event": "install_relocation_begin",
             "t_ns": 1_000_000},
            {"session": "success", "event": "install_relocation_committed",
             "t_ns": 8_500_000},
            {"session": "failed", "event": "install_relocation_begin",
             "t_ns": 2_000_000},
            {"session": "failed", "event": "install_relocation_aborted",
             "t_ns": 30_000_000},
        ]
        segment = summarize([json.dumps(item) for item in rows])[
            "segments"]["install_relocation_begin_to_install_relocation_committed"]
        self.assertEqual(segment["n"], 1)
        self.assertEqual(segment["p50_ms"], 7.5)
        self.assertEqual(segment["p99_ms"], 7.5)

    def test_relocation_counter_excludes_aborted_attempts(self) -> None:
        rows = [
            {"session": "completed", "event": "install_relocation_committed",
             "t_ns": 50, "copied_bytes": 800},
            {"session": "aborted", "event": "install_relocation_aborted",
             "t_ns": 70, "copied_bytes": 90000},
            {"session": "completed", "event": "install_relocation_aborted",
             "t_ns": 72, "copied_bytes": 500},
        ]
        summary = summarize([json.dumps(item) for item in rows])
        self.assertEqual(summary["completed_operation_counters"]["copied_bytes"],
                         {"n": 1, "p50": 800, "p95": 800, "p99": 800,
                          "min": 800, "max": 800})

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

    def test_multipart_network_and_cached_bytes_are_counted(self) -> None:
        rows = [
            {"session": "patch", "event": "multipart_archive_ready",
             "network_bytes": 42, "cached_bytes": 90},
            {"session": "patch", "event": "download_archive_ready", "network_bytes": 8},
            {"session": "warm", "event": "multipart_archive_ready",
             "network_bytes": 0, "cached_bytes": 132},
        ]
        counters = collect_counters([json.dumps(row) for row in rows])
        self.assertEqual(counters["patch"]["network_bytes"], 50)
        self.assertEqual(counters["patch"]["cached_bytes"], 90)
        self.assertEqual(counters["warm"]["network_bytes"], 0)
        self.assertEqual(summarize([json.dumps(row) for row in rows])[
            "completed_operation_counters"]["network_bytes"]["p50"], 25)

    def test_first_paint_not_inferred_from_home_event_loop(self) -> None:
        lines = [
            json.dumps({"session": "a", "event": "launcher_entry", "t_ns": 100}),
            json.dumps({"session": "a", "event": "home_event_loop", "t_ns": 200}),
        ]
        self.assertIsNone(summarize(lines)["segments"]["launcher_entry_to_home_first_paint"])

    def test_comparison_requires_samples_and_never_calls_missing_a_pass(self) -> None:
        old = [json.dumps({"session": "a", "event": "launcher_entry", "t_ns": 0}),
               json.dumps({"session": "a", "event": "home_first_paint", "t_ns": 2_000_000})]
        result = compare_traces(old, [], min_samples=2)
        segment = result["segments"]["launcher_entry_to_home_first_paint"]
        self.assertEqual(segment["status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(segment["candidate_n"], 0)

    def test_comparison_detects_over_five_percent_without_claiming_certification(self) -> None:
        def sample(ns: int) -> list[str]:
            return [json.dumps({"session": str(i), "event": event, "t_ns": value})
                    for i in range(5) for event, value in
                    (("launcher_entry", 100), ("home_first_paint", ns + 100))]
        result = compare_traces(sample(100_000_000), sample(111_000_000))
        segment = result["segments"]["launcher_entry_to_home_first_paint"]
        self.assertEqual(segment["status"], "INVESTIGATE_OVER_5_PERCENT")
        self.assertEqual(segment["p50_change_percent"], 11.0)
        self.assertEqual(result["kind"], "advisory_comparison_not_certification")

    def test_comparison_detects_improvement_without_claiming_pass(self) -> None:
        def sample(ns: int) -> list[str]:
            return [json.dumps({"session": str(i), "event": event, "t_ns": value})
                    for i in range(5) for event, value in
                    (("launcher_entry", 0), ("home_first_paint", ns))]
        result = compare_traces(sample(100_000_000), sample(80_000_000))
        segment = result["segments"]["launcher_entry_to_home_first_paint"]
        self.assertEqual(segment["status"], "NO_5_PERCENT_ALERT")
        self.assertEqual(segment["p50_change_percent"], -20.0)

    def test_p99_is_reported_without_overriding_p50_p95_gate(self) -> None:
        def sample(durations: list[int]) -> list[str]:
            return [
                json.dumps({"session": str(i), "event": event, "t_ns": value})
                for i, ns in enumerate(durations)
                for event, value in (
                    ("launcher_entry", 0), ("home_first_paint", ns * 1_000_000),
                )
            ]

        baseline = sample([100] * 20)
        candidate = sample([100] * 19 + [140])
        summary = summarize(candidate)["segments"]["launcher_entry_to_home_first_paint"]
        self.assertEqual(summary["p50_ms"], 100)
        self.assertEqual(summary["p95_ms"], 100)
        self.assertEqual(summary["p99_ms"], 140)
        comparison = compare_traces(baseline, candidate)
        result = comparison["segments"]["launcher_entry_to_home_first_paint"]
        self.assertEqual(result["candidate_p99_ms"], 140)
        self.assertEqual(result["p99_change_percent"], 40.0)
        self.assertEqual(result["status"], "NO_5_PERCENT_ALERT")

        # P99 can exaggerate a single outlier; it must be a displayed metric,
        # not a new source of automatic certification or a changed CI gate.
        counters = summarize([json.dumps({
            "session": str(i), "event": "download_archive_ready",
            "network_bytes": n,
        }) for i, n in enumerate((0, 1, 2, 3, 4))])
        self.assertEqual(counters["completed_operation_counters"]["network_bytes"]["p99"], 4)

    def test_nearest_rank_p95(self) -> None:
        self.assertEqual(percentile([10, 20, 30, 40, 50], 95), 50)
        self.assertEqual(percentile([10, 20, 30, 40, 50], 99), 50)


if __name__ == "__main__":
    unittest.main()
