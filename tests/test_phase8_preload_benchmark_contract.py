from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Phase8PreloadBenchmarkContractTests(unittest.TestCase):
    def test_benchmark_covers_startup_memory_preload_and_first_accesses(self) -> None:
        source = (ROOT / "tools" / "benchmark_phase8_preload.py").read_text(encoding="utf-8")
        for metric in (
            "startup_stabilized_ms",
            "startup_stabilized_rss_mb",
            "preload_wait_from_stabilized_ms",
            "preload_completed_from_constructor_ms",
            "rss_after_preload_mb",
            "peak_rss_mb",
            "quests_open_ms",
            "achievements_open_ms",
            "guide_open_ms",
            "craft_open_ms",
            "equipment_open_ms",
            "rss_after_first_accesses_mb",
        ):
            with self.subTest(metric=metric):
                self.assertIn(metric, source)

    def test_workflow_compares_base_and_candidate_on_one_runner(self) -> None:
        source = (ROOT / ".github" / "workflows" / "phase8-preload-benchmark.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("Phase 8 / Comparable Preload Benchmark", source)
        self.assertIn('git checkout --force "$env:BASE_SHA"', source)
        self.assertIn('git checkout --force "$env:CANDIDATE_SHA"', source)
        self.assertIn("comparison.json", source)
        self.assertIn("candidate benchmark SHA mismatch", source)
        self.assertIn("candidate preload did not reach terminal states", source)


if __name__ == "__main__":
    unittest.main()
