from __future__ import annotations

import ast
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
    assert "achievements_retained_tree_delta_mb" in source
    assert "guide_retained_tree_delta_mb" in source
    assert "craft_retained_tree_delta_mb" in source
    assert "equipment_tree_delta_active_mb" in source
    assert "equipment_tree_delta_stabilized_mb" in source


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


def test_memory_workflow_enforces_phase8_budgets() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    for label, budget in (
        ("after_preload", "95.0"),
        ("after_quests_home", "100.0"),
        ("after_achievements_home", "100.0"),
        ("after_guide_home", "100.0"),
        ("after_craft_home", "100.0"),
        ("after_equipment_home_stabilized", "100.0"),
    ):
        assert f'"{label}": {budget}' in source
    assert "peak_tree > 220.0" in source
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
