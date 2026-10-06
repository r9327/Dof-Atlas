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
    assert "equipment_tree_delta_active_mb" in source
    assert "equipment_tree_delta_stabilized_mb" in source


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
        ("after_quests_home", "105.0"),
        ("after_achievements_home", "115.0"),
        ("after_guide_home", "120.0"),
        ("after_equipment_home_stabilized", "120.0"),
    ):
        assert f'"{label}": {budget}' in source
    assert "peak_tree > 400.0" in source
    assert '"achievements_retained_tree_delta_mb": 15.0' in source
    assert '"guide_retained_tree_delta_mb": 20.0' in source
    assert '"equipment_tree_delta_stabilized_mb": 1.0' in source
