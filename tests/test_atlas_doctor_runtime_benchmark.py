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

        return (
            (doctor, doctor._first_achievement_detail,
             "_current_encyclopedia_page", "_wait_until_with_ui_block"),
            (phase, phase.first_achievement_detail,
             "current_encyclopedia_page", "wait_until_with_ui_block"),
        )

    def test_first_detail_waits_until_worker_renders_without_eager_catalogue(self):
        view = SimpleNamespace(
            _runtime_ready=True, achievements=[],
            filtered=[SimpleNamespace(id=42)],
            select_achievement=Mock(return_value=True),
            current_achievement_id=42, _detail_open=False,
            _detail_requested=(1, 42), _detail_worker_running=True,
        )
        page = SimpleNamespace(get_achievements_view=lambda: view)

        def simulate_worker_completion(app, predicate, timeout, description):
            self.assertEqual(timeout, 30.0)
            self.assertIn("42", description)
            self.assertFalse(predicate())  # Worker is still running.
            view._detail_worker_running = False
            view._detail_requested = None
            view._detail_open = True
            self.assertTrue(predicate())  # Actual detail now displayed.
            return 7.5  # Qt UI-block measurement, not only click time.

        for module, measure, page_name, wait_name in self.detail_benchmarks():
            with self.subTest(module=module.__name__), patch.object(
                module, page_name, return_value=page
            ), patch.object(
                module, wait_name, side_effect=simulate_worker_completion
            ) as wait:
                view.select_achievement.reset_mock()
                view._detail_open = False
                view._detail_requested = (1, 42)
                view._detail_worker_running = True
                elapsed, ident, block = measure(object(), object())
                self.assertEqual(ident, 42)
                self.assertGreaterEqual(elapsed, 0)
                self.assertGreaterEqual(block, 7.5)
                wait.assert_called_once()
                view.select_achievement.assert_called_once_with(42)
                self.assertEqual(view.achievements, [])

    def test_first_detail_rejects_empty_invalid_or_unselectable_catalogue(self):
        for module, measure, page_name, wait_name in self.detail_benchmarks():
            for refs, selected, error in (
                ([], True, "no selectable achievement"),
                ([SimpleNamespace(id=0)], True, "invalid achievement id"),
                ([SimpleNamespace(id=42)], False, "Unable to select Success"),
            ):
                view = SimpleNamespace(
                    _runtime_ready=True, achievements=[SimpleNamespace(id=99)],
                    filtered=refs, select_achievement=Mock(return_value=selected),
                )
                page = SimpleNamespace(get_achievements_view=lambda: view)
                with self.subTest(module=module.__name__, error=error), patch.object(
                    module, page_name, return_value=page
                ), patch.object(module, wait_name) as wait:
                    with self.assertRaisesRegex(RuntimeError, error):
                        measure(object(), object())
                    wait.assert_not_called()

    def test_first_detail_does_not_report_a_failed_worker_as_loaded(self):
        for module, measure, page_name, wait_name in self.detail_benchmarks():
            view = SimpleNamespace(
                _runtime_ready=True, achievements=[],
                filtered=[SimpleNamespace(id=42)],
                select_achievement=Mock(return_value=True),
                current_achievement_id=42,
                _detail_open=False, _detail_requested=None,
                _detail_worker_running=False,
            )
            page = SimpleNamespace(get_achievements_view=lambda: view)
            def assert_worker_completion(app, predicate, timeout, description):
                return predicate()
            with self.subTest(module=module.__name__), patch.object(
                module, page_name, return_value=page
            ), patch.object(
                module, wait_name, side_effect=assert_worker_completion
            ):
                with self.assertRaisesRegex(RuntimeError, "detail failed to render"):
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

    def test_success_distributions_report_exact_ranks_and_sample_quality(self) -> None:
        samples = [
            self.sample(head="sha", startup_ms=120, rss_mb=100),
            self.sample(head="sha", startup_ms=140, rss_mb=101),
            self.sample(head="sha", startup_ms=160, rss_mb=102),
        ]
        for value, sample in zip((90.0, 120.0, 210.0), samples):
            sample["metrics"]["first_achievement_detail_ms"] = value
            sample["metrics"]["rss_after_first_achievement_detail_mb"] = 101.0

        benchmark = aggregate_samples(samples)
        timings = benchmark["distributions"]["first_achievement_detail_ms"]
        self.assertEqual(timings["sample_count"], 3)
        self.assertEqual(timings["p50"], 120.0)
        self.assertEqual(timings["p95"], 210.0)
        self.assertEqual(timings["p99"], 210.0)
        self.assertEqual(timings["unit"], "ms")
        self.assertEqual(timings["p99_quality"], "DESCRIPTIVE_ONLY")
        self.assertEqual(benchmark["medians"]["first_achievement_detail_ms"], 120.0)
        rss = benchmark["distributions"]["rss_after_first_achievement_detail_mb"]
        self.assertEqual(rss["unit"], "MB")
        self.assertEqual(rss["p95"], 101.0)
        self.assertNotIn("achievements_open_ms", benchmark["distributions"])
        self.assertEqual(benchmark["after"], benchmark["medians"])

    def test_reject_mixed_sha_or_qt_environment_before_benchmark_aggregation(self) -> None:
        first = self.sample(head="a1", startup_ms=100, rss_mb=95)
        different = self.sample(head="b2", startup_ms=120, rss_mb=96)
        with self.assertRaisesRegex(ValueError, "git_head"):
            aggregate_samples([first, different])

        different["environment"]["git_head"] = "a1"
        different["environment"]["pyside"] = "other-Qt"
        with self.assertRaisesRegex(ValueError, "pyside"):
            aggregate_samples([first, different])

        different["environment"]["pyside"] = first["environment"]["pyside"]
        self.assertEqual(aggregate_samples([first, different])["sample_count"], 2)

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
