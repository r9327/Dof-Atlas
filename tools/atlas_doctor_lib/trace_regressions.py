from __future__ import annotations

"""Historical comparison of *observed* scenario edges, never functional proof."""
import json
import re
from pathlib import Path
from typing import Any

MAX_EVENTS = 50000
MAX_RESULTS = 100
MAX_BYTES = 10_000_000
SHA = re.compile(r"[0-9a-f]{40}\Z")
MODULE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*\Z")


def _observed_edges(trace: dict[str, Any]) -> set[tuple[str, str, str]]:
    rows: set[tuple[str, str, str]] = set()
    for event in trace["events"]:
        kind = event.get("type")
        if kind not in {"python_call_edge", "qt_callback_invoked", "module_import_returned"}:
            continue
        if kind == "qt_callback_invoked" and event.get("confidence") != "WRAPPED_PYTHON_CALLBACK_ENTERED":
            continue
        if kind == "module_import_returned" and event.get("confidence") != "IMPORTLIB_RETURNED_REPOSITORY_MODULE":
            continue
        source, target = event.get("source"), event.get("target")
        if (isinstance(source, str) and isinstance(target, str)
                and source.endswith(".py") and target.endswith(".py")
                and not source.startswith("/") and not target.startswith("/")
                and "\\" not in source and "\\" not in target
                and ".." not in source.split("/") and ".." not in target.split("/")):
            rows.add((kind, source, target))
    return rows


def compare_scenario_traces(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    def valid(trace: dict[str, Any]) -> bool:
        return (
            isinstance(trace, dict) and trace.get("kind") == "doctor_runtime_observation"
            and isinstance(trace.get("candidate_sha"), str)
            and bool(SHA.fullmatch(trace["candidate_sha"]))
            and trace.get("worktree_clean") is True
            and trace.get("truncated") is False
            and isinstance(trace.get("scenario_module"), str)
            and bool(MODULE.fullmatch(trace["scenario_module"]))
            and isinstance(trace.get("events"), list)
            and len(trace["events"]) <= MAX_EVENTS
            and all(isinstance(e, dict) for e in trace["events"])
        )
    if not valid(before) or not valid(after):
        return {"status": "UNAVAILABLE", "reason": "Complete exact-SHA tagged scenarios required",
                "lost_observed_edges": [], "regression_proven": False}
    if before["scenario_module"] != after["scenario_module"]:
        return {"status": "UNAVAILABLE", "reason": "Different scenario modules are not comparable",
                "lost_observed_edges": [], "regression_proven": False}
    left, right = _observed_edges(before), _observed_edges(after)
    vanished, added = sorted(left - right), sorted(right - left)
    def rows(items: list[tuple[str, str, str]]) -> list[dict[str, str]]:
        return [{"kind": kind, "source": source, "target": target,
                 "confidence": "SCENARIO_OBSERVATION_ONLY"}
                for kind, source, target in items[:MAX_RESULTS]]
    return {
        "schema_version": 1, "kind": "doctor_historical_scenario_difference",
        "status": "REVIEW" if vanished else "NO_OBSERVATION_DROP",
        "scenario_module": before["scenario_module"],
        "baseline_sha": before["candidate_sha"],
        "candidate_sha": after["candidate_sha"],
        "observed_edges_before": len(left), "observed_edges_after": len(right),
        "lost_observed_edges": rows(vanished), "new_observed_edges": rows(added),
        "lost_total": len(vanished), "new_total": len(added),
        "truncated": len(vanished) > MAX_RESULTS or len(added) > MAX_RESULTS,
        "regression_proven": False, "tests_executed": False,
        "limits": "Same tagged scenario only, 50k events each, 100 displayed changes. Missing events can reflect test coverage, nondeterminism or execution path changes; never proof of dead code or functional regression.",
    }


def load_historical_scenario_diff(root: Path, before: Path, after: Path) -> dict[str, Any]:
    root = root.resolve()
    boundary = (root / ".ai/runtime").resolve()
    traces = []
    for path in (before, after):
        original = Path(path)
        candidate = original if original.is_absolute() else root / original
        resolved = candidate.resolve()
        if candidate.is_symlink() or not resolved.is_relative_to(boundary):
            raise ValueError("Scenario traces must stay inside .ai/runtime")
        if not resolved.is_file() or resolved.stat().st_size > MAX_BYTES:
            raise ValueError("Trace missing or larger than 10 MB")
        trace = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(trace, dict):
            raise ValueError("Trace JSON must be an object")
        traces.append(trace)
    return compare_scenario_traces(*traces)
