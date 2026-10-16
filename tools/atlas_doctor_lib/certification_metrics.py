from __future__ import annotations

"""Read-only interpretation of existing Phase 8 memory benchmark JSON.

The benchmark's JSON contains no Git SHA: a separate authenticated GitHub
Actions run+artifact is required before attributing results to a candidate.
Numbers in a locally supplied JSON must never create a phase certificate.
"""
import math
from typing import Any

# Mirror *stricter currently enforced* values from phase8-memory-benchmark.yml.
# Changing these must undergo independent policy/source review.
STAGE_BUDGETS = {
    "after_preload": (95.0, False),
    "after_quests_home": (100.0, True),
    "after_achievements_home": (100.0, True),
    "after_guide_home": (100.0, True),
    "after_craft_home": (100.0, True),
    "after_equipment_home_stabilized": (100.0, True),
}
PEAK_TREE_BUDGET = 220.0
RETAINED_BUDGETS = {
    "achievements_retained_tree_delta_mb": 15.0,
    "guide_retained_tree_delta_mb": 20.0,
    "craft_retained_tree_delta_mb": 2.0,
    "equipment_tree_delta_stabilized_mb": 1.0,
}


def _nonnegative(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    value = float(value)
    return value if math.isfinite(value) and value >= 0 else None


def assess_memory_benchmark(payload: dict[str, Any]) -> dict[str, Any]:
    """Check all recorded stages; never assert runtime execution provenance."""
    errors = []
    observed = {}
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        errors.append("INVALID_MEMORY_SCHEMA")
        payload = {}
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        errors.append("MISSING_MEMORY_METRICS")
        metrics = {}
    stages = metrics.get("stages")
    if not isinstance(stages, list) or len(stages) > 250:
        errors.append("INVALID_MEMORY_STAGES")
        stages = []
    by_label: dict[str, dict[str, Any]] = {}
    for entry in stages:
        if not isinstance(entry, dict) or not isinstance(entry.get("label"), str):
            errors.append("INVALID_STAGE_RECORD")
            continue
        label = entry["label"]
        if label in by_label:
            errors.append("DUPLICATE_MEMORY_STAGE")
        else:
            by_label[label] = entry
    for name, (budget, strict) in STAGE_BUDGETS.items():
        record = by_label.get(name)
        if not record:
            errors.append("REQUIRED_MEMORY_STAGE_MISSING:" + name)
            continue
        value = _nonnegative(record.get("tree_rss_mb"))
        if value is None:
            errors.append("INVALID_MEMORY_STAGE_RSS:" + name)
            continue
        observed[name] = value
        exceeded = value >= budget if strict else value > budget
        if exceeded:
            errors.append("MEMORY_STAGE_OVER_BUDGET:" + name)
    peak = _nonnegative(metrics.get("peak_tree_rss_mb"))
    if peak is None:
        errors.append("INVALID_PROCESS_TREE_PEAK")
    elif peak > PEAK_TREE_BUDGET:
        errors.append("PROCESS_TREE_PEAK_OVER_BUDGET")
    for name, budget in RETAINED_BUDGETS.items():
        value = _nonnegative(metrics.get(name))
        if value is None:
            errors.append("INVALID_RETAINED_DELTA:" + name)
        elif value > budget:
            errors.append("RETAINED_MEMORY_OVER_BUDGET:" + name)
    return {
        "kind": "doctor_phase8_memory_measurement_review",
        "status": "LOCAL_NUMBERS_IN_BUDGET_UNATTESTED" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "observed_stage_tree_mb": observed,
        "peak_tree_rss_mb": peak,
        "stage_budgets_mb": {k: x[0] for k, x in STAGE_BUDGETS.items()},
        "peak_tree_budget_mb": PEAK_TREE_BUDGET,
        "benchmark_sha_embedded": False,
        "github_provenance_verified": False,
        "performance_certified": False,
        "phase_certified": False,
        "full_suite_waived": False,
        "note": "Independent GitHub provenance + original CI gates required.",
    }
