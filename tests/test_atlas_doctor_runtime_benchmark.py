from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tools.atlas_doctor_lib.runtime_benchmark import (
    aggregate_samples,
    attach_baseline_comparison,
    compare_to_baseline,
)


class AtlasDoctorRuntimeBenchmarkTests(unittest.TestCase):
    def detail_benchmarks(self):
        from tools.atlas_doctor_lib import runtime_benchmark as doctor
        from app.modules.encyclopedia.tools import benchmark_guides_performance as phase

        return ((doctor, doctor._first_achievement_detail, "_current_encyclopedia_page", "_pump_events"),
                (phase, phase.first_achievement_detail, "current_encyclopedia_page", "pump_events"))

    def test_first_detail_selects_paginated_reference_without_eager_catalogue(self):
        view = SimpleNamespace(_runtime_ready=True, achievements=[],
                               filtered=[SimpleNamespace(id=42)],
                               select_achievement=Mock(return_value=True))
        page = SimpleNamespace(get_achievements_view=lambda: view)
        for module, measure, page_name, pump_name in self.detail_benchmarks():
            with self.subTest(module=module.__name__), patch.object(
                module, page_name, return_value=page
            ), patch.object(module, pump_name):
                view.select_achievement.reset_mock()
                elapsed, ident, block = measure(object(), object())
                self.assertEqual(ident, 42)
                self.assertGreaterEqual(elapsed, 0)
                self.assertGreaterEqual(block, 0)
                view.select_achievement.assert_called_once_with(42)
                self.assertEqual(view.achievements, [])

    def test_first_detail_still_rejects_empty_invalid_or_unselectable_catalogue(self):
        for module, measure, page_name, pump_name in self.detail_benchmarks():
            for refs, selected, error in (([], True, "no selectable achievement"),
                                          ([SimpleNamespace(id=0)], True, "invalid achievement id"),
                                          ([SimpleNamespace(id=42)], False, "Unable to select Success")):
                view = SimpleNamespace(_runtime_ready=True, achievements=[SimpleNamespace(id=99)],
                                       filtered=refs, select_achievement=Mock(return_value=selected))
                page = SimpleNamespace(get_achievements_view=lambda: view)
                with self.subTest(module=module.__name__, error=error), patch.object(
                    module, page_name, return_value=page
                ), patch.object(module, pump_name):
                    with self.assertRaisesRegex(RuntimeError, error):
                        measure(object(), object())

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
