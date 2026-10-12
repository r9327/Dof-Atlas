from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "tools" / "benchmark_phase8_preload.py"


def test_preload_benchmark_wait_does_not_sample_memory_in_poll_loop() -> None:
    source = BENCHMARK.read_text(encoding="utf-8")
    helper = source[
        source.index("def wait_until("),
        source.index("def page_loaded("),
    ]
    assert "memory_mb()" not in helper
    assert "poll_seconds" in helper
    assert "time.sleep(interval)" in helper


def test_functional_preload_uses_low_churn_poll_interval() -> None:
    source = BENCHMARK.read_text(encoding="utf-8")
    measurement = source[
        source.index("preload_duration_ms"),
        source.index("preload_completed_from_constructor_ms"),
    ]
    assert "poll_seconds=0.02" in measurement

WORKFLOW = ROOT / ".github" / "workflows" / "phase8-preload-benchmark.yml"


def test_preload_workflow_enforces_phase8_memory_budget() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "rss_after_preload > 95.0" in source
    assert "rss_after_preload - startup_rss > 20.0" in source
    assert "130.00 MB" not in source
    assert "+60.00 MB" not in source


import unittest


class ComparablePreloadCacheIsolationTests(unittest.TestCase):
    def test_base_and_candidate_reset_generated_caches_independently(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        block = workflow[
            workflow.index("      - name: Measure base and candidate on the same runner"):
            workflow.index("      - name: Validate and compare benchmark evidence")
        ]
        base = block.index('git checkout --force "$env:BASE_SHA"')
        candidate = block.index('git checkout --force "$env:CANDIDATE_SHA"')
        resets = [
            i for i in range(len(block))
            if block.startswith('Remove-Item -LiteralPath $cacheRoot', i)
        ]
        self.assertEqual(len(resets), 2)
        self.assertLess(base, resets[0])
        self.assertLess(resets[0], candidate)
        self.assertLess(candidate, resets[1])
        self.assertEqual(block.count('$cacheRoot = ".cache/dofus_atlas"'), 1)
