from __future__ import annotations

# CI-only perf trigger for certified main c2ab9124f22182bf744918f1224e43e9544b593e.

import unittest

from tools.atlas_doctor_lib.runtime_benchmark import (
    aggregate_samples,
    attach_baseline_comparison,
    compare_to_baseline,
)


class AtlasDoctorRuntimeBenchmarkTests(unittest.TestCase):
    @staticmethod
    def sample(*, head: str, startup_ms: float, rss_mb: float) -> dict[str, object]:
        return {
            "schema_version": 1,
            "kind": "atlas_doctor_runtime_sample",
            "environment": {
                "platform": "Windows-test",
                "python": "3.13.15",
                "pyside": "6.11.1",
                "qt_qpa_platform": "offscreen",
                "git_head": head,
            },
            "metrics": {
                "startup_stabilized_ms": startup_ms,
                "startup_stabilized_rss_mb": rss_mb,
                "hot_round_trip_guide": {
                    "avg_ms": startup_ms / 10.0,
                    "max_ms": startup_ms / 8.0,
                },
                "startup_preload_state": "DEFERRED_ON_DEMAND",
                "achievement_detail_sources_ready": True,
            },
        }

    def test_aggregate_samples_uses_medians_and_preserves_compatibility_after(self) -> None:
        benchmark = aggregate_samples(
            [
                self.sample(head="abc", startup_ms=120.0, rss_mb=101.0),
                self.sample(head="abc", startup_ms=100.0, rss_mb=99.0),
                self.sample(head="abc", startup_ms=110.0, rss_mb=100.0),
            ]
        )

        self.assertEqual(benchmark["sample_count"], 3)
        self.assertEqual(benchmark["environment"]["git_head"], "abc")
        self.assertEqual(benchmark["environment"]["sample_count"], 3)
        self.assertEqual(benchmark["medians"]["startup_stabilized_ms"], 110.0)
        self.assertEqual(benchmark["medians"]["startup_stabilized_rss_mb"], 100.0)
        self.assertEqual(benchmark["medians"]["hot_round_trip_guide"]["avg_ms"], 11.0)
        self.assertEqual(benchmark["after"], benchmark["medians"])

    def test_compare_to_legacy_baseline_reports_cost_deltas(self) -> None:
        current = aggregate_samples(
            [self.sample(head="new", startup_ms=120.0, rss_mb=100.0)]
        )
        baseline = {
            "environment": {
                "platform": "Windows-test",
                "python": "3.13.15",
                "pyside": "6.11.1",
                "qt_qpa_platform": "offscreen",
                "git_head": "old",
            },
            "after": {
                "startup_stabilized_ms": 100.0,
                "startup_stabilized_rss_mb": 100.0,
            },
        }

        comparison = compare_to_baseline(current, baseline)

        self.assertEqual(comparison["status"], "WARN")
        self.assertEqual(comparison["baseline_git_head"], "old")
        startup = next(
            row
            for row in comparison["metrics"]
            if row["metric"] == "startup_stabilized_ms"
        )
        self.assertEqual(startup["delta_percent"], 20.0)
        self.assertEqual(len(comparison["regressions_15pct"]), 1)

    def test_environment_mismatch_refuses_false_comparison(self) -> None:
        current = aggregate_samples(
            [self.sample(head="new", startup_ms=100.0, rss_mb=100.0)]
        )
        baseline = {
            "environment": {
                "platform": "Linux-test",
                "python": "3.13.15",
                "pyside": "6.11.1",
                "qt_qpa_platform": "offscreen",
                "git_head": "old",
            },
            "medians": {
                "startup_stabilized_ms": 90.0,
                "startup_stabilized_rss_mb": 90.0,
            },
        }

        comparison = compare_to_baseline(current, baseline)

        self.assertEqual(comparison["status"], "UNAVAILABLE")
        self.assertEqual(comparison["environment_mismatches"], ["platform"])

    def test_attach_baseline_keeps_reproducible_baseline_snapshot(self) -> None:
        current = aggregate_samples(
            [self.sample(head="new", startup_ms=100.0, rss_mb=100.0)]
        )
        baseline = aggregate_samples(
            [self.sample(head="old", startup_ms=95.0, rss_mb=99.0)]
        )

        result = attach_baseline_comparison(current, baseline)
        baseline["medians"]["startup_stabilized_ms"] = 1.0

        self.assertEqual(result["baseline"]["environment"]["git_head"], "old")
        self.assertEqual(result["baseline"]["medians"]["startup_stabilized_ms"], 95.0)
        self.assertEqual(result["comparison"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
