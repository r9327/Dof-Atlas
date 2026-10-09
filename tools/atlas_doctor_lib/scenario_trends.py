from __future__ import annotations

"""Bounded historical trends of existing Doctor scenario observations.

No scenario is executed. Repeated absence is a review lead, never a proven
regression: Qt scheduling and scenario coverage can change observations.
"""
import json
from pathlib import Path
from typing import Any

from .trace_regressions import (_observed_edges, compare_scenario_traces,
                                MAX_BYTES)

MAX_TRACES = 8
MAX_TOTAL_BYTES = 32_000_000
MAX_CANDIDATES = 80


def summarize_scenario_trend(traces: list[dict[str, Any]]) -> dict[str, Any]:
    if not 2 <= len(traces) <= MAX_TRACES:
        return {"status": "UNAVAILABLE", "reason": "Expected 2..8 ordered traces",
                "regression_proven": False, "tests_executed": False}
    transitions = [
        compare_scenario_traces(first, second)
        for first, second in zip(traces, traces[1:])
    ]
    if any(row.get("status") == "UNAVAILABLE" for row in transitions):
        return {"status": "UNAVAILABLE",
                "reason": "Every trace must be complete, exact-SHA tagged and for one identical scenario",
                "regression_proven": False, "tests_executed": False}
    observed = [_observed_edges(trace) for trace in traces]
    first = observed[0]
    last = observed[-1]
    candidates: list[dict[str, Any]] = []
    for kind, source, target in sorted(first - last):
        edge = (kind, source, target)
        baseline_repeat = len(observed) >= 4 and edge in observed[1]
        end_repeat = len(observed) >= 4 and edge not in observed[-2]
        classification = ("REPEATED_ABSENCE_REVIEW" if baseline_repeat and end_repeat
                          else "SINGLE_WINDOW_ABSENCE_REVIEW")
        candidates.append({
            "kind": kind, "source": source, "target": target,
            "classification": classification,
            "observed_in": sum(edge in row for row in observed),
            "scenarios_compared": len(observed),
            "functional_regression_proven": False,
        })
    candidates.sort(key=lambda row: (
        row["classification"] != "REPEATED_ABSENCE_REVIEW",
        row["source"], row["target"], row["kind"],
    ))
    repeated = sum(x["classification"] == "REPEATED_ABSENCE_REVIEW"
                   for x in candidates)
    return {
        "schema_version": 1, "kind": "doctor_historical_scenario_trend",
        "status": "REVIEW" if candidates else "NO_OBSERVATION_DROP",
        "scenario_module": traces[0]["scenario_module"],
        "ordered_shas": [row["candidate_sha"] for row in traces],
        "run_count": len(traces),
        "edge_counts": [len(row) for row in observed],
        "transitions": [{
            "before_sha": row["baseline_sha"],
            "after_sha": row["candidate_sha"],
            "lost_total": row["lost_total"],
            "new_total": row["new_total"],
        } for row in transitions],
        "candidates": candidates[:MAX_CANDIDATES],
        "candidates_total": len(candidates),
        "repeated_absence_candidates": repeated,
        "truncated": len(candidates) > MAX_CANDIDATES,
        "regression_proven": False, "tests_executed": False,
        "next_verification": ("Repeat the same scenario on the target SHA and compare"
                              " the affected source/Qt callbacks before classifying a defect."),
        "limits": "Ordered complete scenarios only; a missing call is not proof of dead code, functional regression, or release readiness.",
    }


def load_scenario_trend(root: Path, paths: list[Path]) -> dict[str, Any]:
    root = root.resolve()
    boundary = (root / ".ai/runtime").resolve()
    if not 2 <= len(paths) <= MAX_TRACES:
        raise ValueError("Expected between two and eight historical traces")
    traces: list[dict[str, Any]] = []
    total_bytes = 0
    for item in paths:
        original = Path(item)
        selected = original if original.is_absolute() else root / original
        resolved = selected.resolve()
        if selected.is_symlink() or not resolved.is_relative_to(boundary):
            raise ValueError("Trace outside .ai/runtime or symlink")
        if not resolved.is_file():
            raise ValueError("Missing Doctor historical trace")
        size = resolved.stat().st_size
        total_bytes += size
        if size > MAX_BYTES or total_bytes > MAX_TOTAL_BYTES:
            raise ValueError("Scenario trend read budget exceeded")
        trace = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(trace, dict):
            raise ValueError("Scenario trace must be a JSON object")
        traces.append(trace)
    return summarize_scenario_trend(traces)
