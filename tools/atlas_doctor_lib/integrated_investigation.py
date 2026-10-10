from __future__ import annotations

"""Unified read-only Doctor investigation. Graphify is evidence, never a gate shortcut."""
import json
import subprocess
from pathlib import Path
from typing import Any


MAX_PATHS = 8
MAX_TRACE = 10_000_000
MAX_EVENTS = 50000
MAX_GRAPH_EVIDENCE = 80


def _git_head(root: Path) -> str | None:
    try:
        run = subprocess.run(["git", "rev-parse", "--verify", "HEAD"],
                             cwd=root, capture_output=True, text=True,
                             timeout=8, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    sha = run.stdout.strip()
    if run.returncode or len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        return None
    return sha


def _graph_file_evidence(graph: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    ids: dict[str | int, str] = {}
    target = set(paths)
    selected_nodes: dict[str, int] = {p: 0 for p in paths}
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        identity, path = node.get("id"), node.get("source_file")
        if not isinstance(identity, (int, str)) or not isinstance(path, str):
            continue
        ids[identity] = path
        if path in target:
            selected_nodes[path] += 1
    incoming: set[tuple[str, str, str]] = set()
    outgoing: set[tuple[str, str, str]] = set()
    for edge in graph.get("links", []):
        if not isinstance(edge, dict):
            continue
        source, destination = ids.get(edge.get("source")), ids.get(edge.get("target"))
        if not source or not destination or source == destination:
            continue
        relation = edge.get("relation")
        if not isinstance(relation, str):
            continue
        # Keep each relation type explicit, never make calls into imports.
        if source in target:
            outgoing.add((source, destination, relation))
        if destination in target:
            incoming.add((source, destination, relation))
    return {
        "status": "EXACT_SHA_GRAPH_EVIDENCE",
        "nodes_per_file": selected_nodes,
        "incoming_edges": [
            {"source": source, "target": destination, "relation": relation}
            for source, destination, relation in sorted(incoming)[:MAX_GRAPH_EVIDENCE]],
        "outgoing_edges": [
            {"source": source, "target": destination, "relation": relation}
            for source, destination, relation in sorted(outgoing)[:MAX_GRAPH_EVIDENCE]],
        "incoming_total": len(incoming), "outgoing_total": len(outgoing),
        "truncated": len(incoming) > MAX_GRAPH_EVIDENCE or len(outgoing) > MAX_GRAPH_EVIDENCE,
        "not_reachable_does_not_mean_unused": True,
    }


def _read_trace(root: Path, trace_path: Path, sha: str | None) -> tuple[dict[str, Any] | None, str]:
    original = trace_path if trace_path.is_absolute() else root / trace_path
    boundary = (root / ".ai" / "runtime").resolve()
    selected = original.resolve()
    if (original.is_symlink() or not selected.is_relative_to(boundary)
            or not selected.is_file() or selected.stat().st_size > MAX_TRACE):
        return None, "BLOCKED_INVALID_TRACE_PATH"
    try:
        trace = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None, "BLOCKED_MALFORMED_TRACE_JSON"
    if not isinstance(trace, dict):
        return None, "BLOCKED_MALFORMED_TRACE"
    events = trace.get("events")
    if (not sha or trace.get("candidate_sha") != sha
            or trace.get("kind") != "doctor_runtime_observation"
            or trace.get("worktree_clean") is not True
            or trace.get("truncated") is not False
            or not isinstance(events, list) or len(events) > MAX_EVENTS
            or not all(isinstance(row, dict) for row in events)):
        return None, "BLOCKED_STALE_OR_INCOMPLETE_TRACE"
    return trace, "MATCHED"


def investigate_files(root: Path, paths: list[str], *,
                      trace_path: Path | None = None,
                      cost_reports: list[Path] | None = None,
                      graph_ui: bool = False) -> dict[str, Any]:
    """One small, opt-in cross-engine investigation without tests or rebuild."""
    from .deep_intelligence import scan_sources
    from .source_impact import source_reverse_impact
    from .resource_lifecycle import inspect_resource_lifecycle
    from .boundary_intelligence import layer_boundary_review
    from .architecture import graph_status

    root = root.resolve()
    requested = list(dict.fromkeys(paths))
    if not 1 <= len(requested) <= MAX_PATHS:
        raise ValueError("Investigate 1 to 8 Python files")
    for raw in requested:
        if not isinstance(raw, str) or "\\" in raw:
            raise ValueError("Expected repository-relative Python source")
        relative = Path(raw)
        path = root / relative
        if (relative.is_absolute() or relative.suffix != ".py"
                or any(piece in {"", ".", ".."} for piece in relative.parts)
                or path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(root)):
            return {
                "status": "BLOCKED", "reason": "Unsafe or unavailable Python source",
                "paths": [], "read_only": True, "tests_executed": False,
                "graph_rebuilt": False, "safe_to_delete": False,
            }
    source = scan_sources(root, requested)
    boundary = layer_boundary_review(root, requested)
    resources = inspect_resource_lifecycle(root, requested)
    try:
        consumers = source_reverse_impact(root, requested, depth=2)
    except (OSError, RuntimeError, ValueError) as exc:
        consumers = {"status": "UNAVAILABLE", "reason": type(exc).__name__,
                     "consumer_files": [], "safe_to_delete": False}

    # Atlas Agent selects real scope/test obligations. Advisory only.
    from tools import agent
    tests: dict[str, Any] = {
        "status": "UNAVAILABLE", "recommended_tests": [],
        "required_groups": [], "tests_executed": False,
        "full_suite_waived": False,
    }
    try:
        plan = agent.plan_payload(root, requested)
        tests = {
            "status": plan.get("status", "REVIEW"),
            "recommended_tests": list(plan.get("execution_tests") or [])[:64],
            "required_groups": list(plan.get("required_groups") or [])[:64],
            "integrity_mode": plan.get("integrity_mode"),
            "scopes": list(plan.get("scopes") or [])[:32],
            "tests_executed": False, "full_suite_waived": False,
        }
    except Exception as exc:
        tests["reason"] = f"Canonical Agent unavailable: {type(exc).__name__}"
    if cost_reports:
        from .test_intelligence import test_cost_report, suggest_targeted_test_order
        try:
            costs = test_cost_report(root, cost_reports)
            tests["historical_costs"] = costs
            tests["advisory_order"] = suggest_targeted_test_order(
                tests.get("required_groups", []), costs)
        except (OSError, ValueError, UnicodeError) as exc:
            tests["historical_costs"] = {
                "status": "UNAVAILABLE", "reason": type(exc).__name__,
                "tests_executed": False,
            }
    sha = _git_head(root)
    graph_status_result = graph_status(root)
    graph_summary: dict[str, Any] = {
        "status": graph_status_result.get("status", "UNAVAILABLE"),
        "reason": graph_status_result.get("reason"),
        "rebuild_automatically": False,
    }
    loaded_graph = None
    if (graph_status_result.get("status") == "PASS"
            and graph_status_result.get("git", {}).get("head") == sha):
        try:
            candidate = Path(graph_status_result["graph"])
            if not candidate.is_file() or candidate.stat().st_size > 32_000_000:
                raise ValueError("Graph exceeds on-demand inspection budget")
            loaded_graph = json.loads(candidate.read_text(encoding="utf-8"))
            if (not isinstance(loaded_graph, dict)
                    or loaded_graph.get("built_at_commit") != sha):
                raise ValueError("Graph source SHA mismatch")
            graph_summary = _graph_file_evidence(loaded_graph, requested)
            graph_summary["candidate_sha"] = sha
        except (OSError, ValueError, UnicodeError, TypeError):
            graph_summary = {
                "status": "UNAVAILABLE", "reason": "Graph source cannot be trusted",
                "rebuild_automatically": False,
            }

    runtime: dict[str, Any] = {"status": "NOT_PROVIDED"}
    if trace_path is not None:
        trace, trace_status = _read_trace(root, Path(trace_path), sha)
        runtime = {"status": trace_status, "proven_execution_only": False}
        if trace is not None and sha is not None:
            from .scenario_coverage import summarize_scenarios
            from .runtime_observation import summarize_runtime_lifecycle
            from .function_inventory import compare_source_functions
            coverage = summarize_scenarios(
                [trace], expected_sha=sha, required_files=requested)
            runtime = {
                "status": "MATCHED",
                "scenario_module": trace.get("scenario_module"),
                "coverage": coverage,
                "function_entries": compare_source_functions(
                    root, requested, trace, expected_sha=sha),
                "lifecycle": summarize_runtime_lifecycle(trace),
                "returned_modules_not_new_execution_proof": True,
            }
            if loaded_graph is not None:
                from .deep_intelligence import trace_explicit_json_bindings
                runtime["explicit_json_ui_bindings"] = trace_explicit_json_bindings(
                    loaded_graph, trace)

    incomplete = (
        source.get("status") != "PASS"
        or boundary.get("status") in {"BLOCKED", "UNAVAILABLE"}
        or resources.get("status") in {"BLOCKED", "UNAVAILABLE"}
        or consumers.get("status") not in {"SOURCE_CONFIRMED", "REVIEW"}
        or graph_summary["status"] != "EXACT_SHA_GRAPH_EVIDENCE"
        or tests["status"] not in {"READY", "PASS"}
        or runtime["status"] not in {"NOT_PROVIDED", "MATCHED"}
    )
    graph_visualization: dict[str, Any] = {"status": "NOT_REQUESTED"}
    if graph_ui:
        if graph_summary.get("status") != "EXACT_SHA_GRAPH_EVIDENCE":
            graph_visualization = {
                "status": "UNAVAILABLE",
                "reason": "Interactive file view needs an exact-SHA Graphify graph.",
                "graph_rebuilt": False,
            }
        else:
            from .doctor_graph_ui import export_interactive_graph
            graph_visualization = export_interactive_graph(
                root, trace_path=trace_path, inspect_files=requested)
    # No PASS status here: successful source inspection never certifies
    # functional availability, Graphify correctness or memory release.
    return {
        "schema_version": 1, "kind": "doctor_integrated_investigation",
        "status": "REVIEW" if not incomplete else "PARTIAL_REVIEW",
        "candidate_sha": sha, "paths": requested,
        "source": source, "layer_boundaries": boundary,
        "resource_lifecycle": resources,
        "source_confirmed_consumers": consumers,
        "graphify": graph_summary, "runtime": runtime,
        "graphify_interactive_view": graph_visualization,
        "canonical_test_intelligence": tests,
        "read_only": True, "tests_executed": False, "benchmarks_executed": False,
        "graph_rebuilt": False, "safe_to_delete": False, "final_certification": False,
        "next_action": "Review linked consumers, runtime entry evidence, and domain tests before modifying files.",
        "limits": "Only 8 files. Current-source imports and exact-SHA graph/trace when available. No runtime absence proves dead code; source review cannot certify UI, RAM or preload.",
    }
