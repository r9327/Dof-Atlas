"""Canonical Doctor percent attribution for measured non-overlapping phases.

CPU shares use current-process CPU time, not peak percentages or child CPU.
RSS peaks are non-additive and cannot truthfully be divided into percentages.
This module analyzes one Doctor measurement without running a second engine.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def cost_attribution(report: dict[str, Any]) -> dict[str, Any]:
    phases: list[tuple[str, str, float, float]] = []
    for name, wall_field, cpu_field in (
        ("app_constructor_and_visible", "constructor_to_visible_ms", "constructor_cpu_ms"),
        ("functional_preload", "preload_ms", "preload_cpu_ms"),
        ("post_home_idle", "idle_observation_ms", "idle_cpu_ms"),
    ):
        wall, cpu = report.get(wall_field), report.get(cpu_field)
        if isinstance(wall, (int, float)) and wall >= 0 and isinstance(cpu, (int, float)) and cpu >= 0:
            phases.append((name, "lifecycle", float(wall), float(cpu)))
    for row in report.get("routes", []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("id") or "")
        for suffix, field in (("open", "open_ms"), ("home", "return_home_ms")):
            cpu_field = "open_cpu_ms" if suffix == "open" else "return_home_cpu_ms"
            wall, cpu = row.get(field), row.get(cpu_field)
            if name and isinstance(wall, (int, float)) and wall >= 0 and isinstance(cpu, (int, float)) and cpu >= 0:
                phases.append((name if suffix == "open" else "home_return", suffix, float(wall), float(cpu)))

    wall_total = report.get("elapsed_seconds")
    cpu_total = report.get("process_cpu_total_ms")
    if (not isinstance(wall_total, (int, float)) or wall_total <= 0
            or not isinstance(cpu_total, (int, float)) or cpu_total < 0):
        return {
            "status": "NOT_MEASURED", "reason": "MISSING_PROCESS_CLOCK_BASELINE",
            "is_certification": False,
        }
    wall_total = float(wall_total) * 1000.0
    cpu_total = float(cpu_total)
    assigned_wall = sum(x[2] for x in phases)
    assigned_cpu = sum(x[3] for x in phases)
    # Clock rounding can produce tiny boundary overruns; large overruns block
    # cost percentages because the spans are not actually exclusive.
    if assigned_wall > wall_total + max(100.0, wall_total * 0.03) or assigned_cpu > cpu_total + max(100.0, cpu_total * 0.03):
        return {"status": "BLOCKED", "reason": "OVERLAPPING_OR_INVALID_TIMING_SPANS",
                "assigned_wall_ms": round(assigned_wall, 2),
                "total_wall_ms": round(wall_total, 2),
                "assigned_cpu_ms": round(assigned_cpu, 2),
                "total_cpu_ms": round(cpu_total, 2), "is_certification": False}

    groups: dict[tuple[str, str], dict[str, float]] = defaultdict(
        lambda: {"wall_ms": 0.0, "cpu_ms": 0.0, "samples": 0}
    )
    for phase, category, wall, cpu in phases:
        row = groups[(phase, category)]
        row["wall_ms"] += wall
        row["cpu_ms"] += cpu
        row["samples"] += 1
    overhead_wall = max(0.0, wall_total - assigned_wall)
    overhead_cpu = max(0.0, cpu_total - assigned_cpu)
    if overhead_wall or overhead_cpu:
        groups[("other_or_uninstrumented", "unattributed")] = {
            "wall_ms": overhead_wall, "cpu_ms": overhead_cpu, "samples": 0,
        }
    ranked: list[dict[str, Any]] = []
    for (phase, kind), metric in groups.items():
        ranked.append({
            "phase": phase, "kind": kind,
            "samples": metric["samples"],
            "wall_ms": round(metric["wall_ms"], 2),
            "wall_pct_of_entire_probe": round(metric["wall_ms"] / wall_total * 100, 2),
            "process_cpu_ms": round(metric["cpu_ms"], 2),
            "cpu_pct_of_measured_process_cpu": (
                round(metric["cpu_ms"] / cpu_total * 100, 2) if cpu_total else None
            ),
        })
    ranked.sort(key=lambda item: (-item["wall_ms"], item["phase"], item["kind"]))

    # A high repeat cost is a signal to inspect initialization again,
    # not proof that source functions or memory buffers are duplicated.
    repeat_suspects = []
    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report.get("routes", []):
        if isinstance(row, dict) and row.get("status") == "PASS":
            by_route[str(row.get("id"))].append(row)
    for route, samples in sorted(by_route.items()):
        ordered = sorted(samples, key=lambda x: x.get("cycle", 0))
        if len(ordered) < 3:
            continue
        warm = [float(r.get("open_ms") or 0) for r in ordered[1:]]
        high = [v for v in warm if v >= 250]
        if len(high) >= 2 and len(high) >= (len(warm) + 1) // 2:
            repeat_suspects.append({
                "route": route, "warm_open_samples": len(warm),
                "warm_ge_250ms": len(high), "max_warm_ms": round(max(warm), 2),
                "classification": "REPEATED_EXPENSIVE_ROUTE_NOT_PROVEN_DUPLICATE",
            })
    return {
        "status": "OBSERVED",
        "scope": "single_atlas_process_cpu_no_child_workers",
        "denominators": {"wall_ms": round(wall_total, 2),
                         "measured_process_cpu_ms": round(cpu_total, 2)},
        "shares": ranked,
        "repeated_work_suspects": repeat_suspects,
        "memory": {
            "rss_percent_split": None,
            "reason": "RSS/Qt process-tree peaks and module deltas are shared, overlapping and not additive",
            "process_tree_peak_mib": report.get("peak_process_tree_rss_mib"),
            "worst_tree_phase": report.get("worst_tree_phase"),
        },
        "limitations": [
            "wall percentages are shares of one measured probe; concurrent tasks may overlap in elapsed time",
            "CPU percentages represent the main Atlas process only; worker subprocess CPU is not included",
            "cProfile/tracemalloc deep attribution requires a separate Doctor diagnostic run",
            "repeated warm-route cost does not prove duplicate code or leaked memory",
        ],
        "is_certification": False,
    }
