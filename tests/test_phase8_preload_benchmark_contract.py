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


class DeepAchievementTimingContractTests(unittest.TestCase):
    def test_success_breakdown_keeps_real_render_gate_and_total(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        block = source[
            source.index("    # Achievement: request the first real retained Achievement detail;"):
            source.index("\ndef measure() -> dict[str, Any]:")
        ]
        self.assertIn('achievement_detail_ms = milliseconds(started)', block)
        self.assertIn('label="first rendered Achievement detail"', block)
        self.assertIn('"achievement_detail_phases_ms"', block)
        phases = (
            "achievement_tab_ready_ms",
            "achievement_catalogue_lookup_ms",
            "achievement_navigation_call_ms",
            "achievement_post_navigation_wait_ms",
        )
        for phase in phases:
            self.assertIn(phase, block)
        self.assertLess(
            block.index("achievement_navigation_call_ms = milliseconds(navigate_started)"),
            block.index('label="first rendered Achievement detail"'),
        )


class DeepQuestTimingContractTests(unittest.TestCase):
    def test_quest_breakdown_does_not_replace_real_detail_wait(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        block = source[
            source.index("    # The memory manager may legitimately evict the entire Quests page"):
            source.index("    # Guide: requesting a specific Guide")
        ]
        self.assertIn("quest_detail_ms = milliseconds(started)", block)
        self.assertIn('label="first rendered Quest detail"', block)
        self.assertIn('"quest_detail_phases_ms"', source)
        for field in (
            "quest_tab_ready_ms",
            "quest_catalogue_lookup_ms",
            "quest_navigation_call_ms",
            "quest_post_navigation_wait_ms",
        ):
            self.assertIn(field, block)
        self.assertLess(
            block.index("quest_navigation_call_ms = milliseconds(quest_navigation_started)"),
            block.index('label="first rendered Quest detail"'),
        )


class QuestSourcePhaseProfilingContractTests(unittest.TestCase):
    def test_first_real_quest_detail_exposes_source_compiler_diagnostics(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        self.assertIn('"source_compile_phases": quest_source_phases_ms', source)
        self.assertIn('label="first rendered Quest detail"', source)
        self.assertIn('quest_detail_ms = milliseconds(started)', source)
        compiler = (ROOT / "app" / "quest_catalog.py").read_text(encoding="utf-8")
        for name in (
            "source_mapping_setup", "image_index_and_xp", "global_names_and_links",
            "objective_lookup", "rich_quest_steps", "enrichment",
        ):
            self.assertIn(f'record_phase("{name}")', compiler)
