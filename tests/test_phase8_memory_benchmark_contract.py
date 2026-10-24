from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "tools" / "benchmark_phase8_memory.py"
WORKFLOW = ROOT / ".github" / "workflows" / "phase8-memory-benchmark.yml"


def test_memory_benchmark_keeps_required_stage_labels() -> None:
    source = BENCHMARK.read_text(encoding="utf-8")
    tree = ast.parse(source)
    strings = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    expected = {
        "startup_stabilized",
        "after_preload",
        "quests_active",
        "after_quests_home",
        "achievements_active",
        "after_achievements_home",
        "guide_active",
        "after_guide_home",
        "after_guide_home_stabilized",
        "craft_active",
        "after_craft_home",
        "before_equipment_home",
        "equipment_active",
        "after_equipment_home",
        "after_equipment_home_stabilized",
    }
    assert expected <= strings


def test_memory_benchmark_measures_process_tree_and_equipment_delta() -> None:
    source = BENCHMARK.read_text(encoding="utf-8")
    assert "_descendant_rows" in source
    assert "tree_rss_mb" in source
    assert "child_rss_mb" in source
    assert "peak_tree_rss_mb" in source
    assert '"python_threads_alive"' in source
    assert '"qt_widgets_alive"' in source
    assert '"qt_widget_classes"' in source
    assert '"warmup_processes"' in source
    assert "QApplication.allWidgets()" in source
    assert "achievements_retained_tree_delta_mb" in source
    assert "guide_retained_tree_delta_mb" in source
    assert "craft_retained_tree_delta_mb" in source
    assert "equipment_tree_delta_active_mb" in source
    assert "equipment_tree_delta_stabilized_mb" in source


class GuideHomeStabilizationContractTests(unittest.TestCase):
    def test_stage_introspection_does_not_contaminate_rss_sample(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        stage_capture = source[
            source.index("def _capture("):source.index("def _open_guide_with_probe(")
        ]
        flush = stage_capture.index("QApplication.sendPostedEvents(None, QEvent.DeferredDelete)")
        rss = stage_capture.index("sample = memory_snapshot(label)")
        self.assertLess(flush, rss)
        threads = stage_capture.index('sample["python_threads_alive"]')
        widgets = stage_capture.index('sample["qt_widgets_alive"]')
        self.assertLess(rss, threads)
        self.assertLess(rss, widgets)
        self.assertIn("QApplication.allWidgets()", stage_capture)
        self.assertIn('"qt_widget_classes"', stage_capture)

    def test_repeated_real_navigation_retention_is_measured(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        flow = source[source.index('after_equipment_stable = _capture('):]
        for evidence in (
            "round_trip_home_samples",
            "for cycle in range(1, 3)",
            '("quests", QUESTS_TAB)',
            '("achievements", ACHIEVEMENTS_TAB)',
            "_open_rich_guide_with_probe(app, window, stages)",
            'f"repeat_{cycle}_guide_home"',
            '"round_trip_guide_tree_drift_mb"',
        ):
            self.assertIn(evidence, flow)
        self.assertLess(
            flow.index("for cycle in range(1, 3)"),
            flow.index("sampler.stop()"),
        )

    def test_memory_measures_repeated_home_cycles_without_blocking_at_100mb(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("advisory_home_budgets_mb = {", source)
        for label in (
            "after_guide_home_stabilized",
            "repeat_1_quests_home",
            "repeat_1_achievements_home",
            "repeat_1_guide_home",
            "repeat_2_quests_home",
            "repeat_2_achievements_home",
            "repeat_2_guide_home",
        ):
            self.assertIn(f'"{label}": 100.0', source)
        self.assertIn('HOME_TARGET_ADVISORY:', source)
        self.assertIn("::warning title=Memory Home target (advisory)", source)
        self.assertIn("peak_hard_limit_mb = hard_limit(peak_target_mb)", source)
        self.assertIn('classify(peak_tree, peak_target_mb) == "FAIL"', source)
        self.assertIn("::warning title=Peak RAM above target (5% tolerance)", source)

    def test_stabilized_guide_home_has_observable_evidence(self) -> None:
        source = BENCHMARK.read_text(encoding="utf-8")
        flow = source[source.index('sampler.set_phase("guide_catalogue_open")'):]
        first_home = flow.index('after_guide_home = _capture(')
        stable = flow.index('"after_guide_home_stabilized"')
        next_module = flow.index('sampler.set_phase("craft_open")')
        self.assertLess(first_home, stable)
        self.assertLess(stable, next_module)
        self.assertIn('sampler.set_phase("guide_home_stabilized")', flow)
        for metric in (
            "guide_retained_tree_delta_stabilized_mb",
            "guide_incremental_retained_tree_delta_mb",
            "guide_home_stabilization_delta_mb",
        ):
            self.assertIn(f'"{metric}"', flow)


def test_memory_benchmark_avoids_sampler_observer_effect_during_external_warmup() -> None:
    source = BENCHMARK.read_text(encoding="utf-8")
    assert 'os.environ.get("DOFUS_ATLAS_CACHE_WARMUP_TOKEN", "").strip()' in source
    assert "defer_tree_sampler" in source
    assert 'if task == "quests" and defer_tree_sampler:' in source
    assert "sampler.start()" in source
    assert "time.sleep(0.02)" in source


def test_memory_benchmark_counts_external_warmup_process_tree() -> None:
    benchmark = BENCHMARK.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'DOFUS_ATLAS_WARMUP_PID' in benchmark
    assert 'DOFUS_ATLAS_WARMUP_PID' in workflow
    assert '_descendant_rows(warmup_pid, rows)' in benchmark
    assert 'counted_pids.add(row.pid)' in benchmark
    assert 'child_mb + warmup_mb' in benchmark
    assert 'and not bool(os.environ.get("DOFUS_ATLAS_WARMUP_PID", "").strip())' in benchmark



def test_memory_benchmark_opens_real_guide_detail_before_home() -> None:
    source = BENCHMARK.read_text(encoding="utf-8")
    assert 'GUIDE_DETAIL_BENCHMARK_ID = "guide_complet"' in source
    helper = source[
        source.index("def _open_rich_guide_with_probe"):
        source.index("def measure")
    ]
    assert "navigate_to_guide" in helper
    assert '"guide_detail_ready"' in helper
    assert 'bool(getattr(view, "_runtime_ready", False))' in helper

    flow = source[source.index('sampler.set_phase("guide_catalogue_open")'):]
    detail = flow.index("_open_rich_guide_with_probe(")
    home = flow.index('window.show_page("Home")')
    assert detail < home


def test_memory_workflow_publishes_and_uploads_evidence() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "tools/benchmark_phase8_memory.py" in source
    assert "Publish memory summary" in source
    assert "Upload memory evidence" in source
    assert "phase8-memory-" in source


def test_memory_workflow_keeps_critical_budgets_hard_and_home_advisory() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    for label in (
        "after_quests_home",
        "after_achievements_home",
        "after_guide_home",
        "after_craft_home",
        "after_equipment_home_stabilized",
    ):
        assert f'"{label}": 100.0' in source
    assert 'advisory_home_budgets_mb = {' in source
    assert 'preload_status = classify(preload_mb, preload_target_mb)' in source
    assert 'preload memory tolerance exceeded' in source
    assert 'classify(peak_tree, peak_target_mb) == "FAIL"' in source
    assert 'state = classify(measured, budget)' in source
    assert 'if state == "FAIL":' in source
    assert 'if state == "WARNING":' in source
    assert 'if metric not in metrics or metrics[metric] is None:' in source
    assert '"achievements_retained_tree_delta_mb": 15.0' in source
    assert '"guide_retained_tree_delta_mb": 20.0' in source
    assert '"craft_retained_tree_delta_mb": 2.0' in source
    assert '"equipment_tree_delta_stabilized_mb": 1.0' in source


def test_windows_rss_sampler_reuses_native_bindings() -> None:
    source = BENCHMARK.read_text(encoding="utf-8")
    assert "@lru_cache(maxsize=1)" in source
    assert "def _windows_api_dlls():" in source
    assert "class _ProcessEntry32W(ctypes.Structure):" in source
    assert "class _ProcessMemoryCounters(ctypes.Structure):" in source
    assert "kernel32, psapi = _windows_api_dlls()" in source


def test_memory_benchmark_cannot_skip_a_fast_external_warmup() -> None:
    benchmark = BENCHMARK.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    warmup = (ROOT / "app" / "startup_cache_warmup.py").read_text(encoding="utf-8")
    assert "DOFUS_ATLAS_WARMUP_GO_FILE" in benchmark
    assert "DOFUS_ATLAS_WARMUP_GO_FILE" in warmup
    assert "DOFUS_ATLAS_WARMUP_GO_FILE" in workflow
    assert "_wait_for_memory_sampler(go_file)" in warmup
    assert "sampler.warmup_worker_seen" in benchmark
    assert "Invalid RAM evidence: external warmup child was never sampled" in benchmark
    assert "Path(go_file).touch(exist_ok=False)" in benchmark
    assert "Remove-Item Env:DOFUS_ATLAS_WARMUP_GO_FILE" in workflow
