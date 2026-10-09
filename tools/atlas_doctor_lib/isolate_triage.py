from __future__ import annotations

"""Bounded Doctor triage of isolated Graphify symbols and files.

No evidence of a reference is not evidence that code is dead.
"""
import hashlib
import json
from pathlib import Path
from typing import Any


def _trace_observations(root: Path, trace_paths: list[Path], graph_sha: str) -> dict[str, dict[str, Any]]:
    """Positive evidence by file, strictly scoped to complete exact-SHA traces.

    No negative inference can be made about unobserved files. This reads traces
    only, and never launches UI, tests, workers or Graphify.
    """
    if not 1 <= len(trace_paths) <= 8:
        raise ValueError("Pass 1..8 runtime traces")
    if not isinstance(graph_sha, str) or len(graph_sha) != 40 or any(
        char not in "0123456789abcdef" for char in graph_sha
    ):
        raise ValueError("Current graph must have full Git SHA")
    from .doctor_graph_ui import merge_runtime_traces
    boundary = (root / ".ai/runtime").resolve()
    traces: list[dict[str, Any]] = []
    for original in trace_paths:
        candidate = Path(original)
        path = candidate if candidate.is_absolute() else root / candidate
        resolved = path.resolve()
        if (path.is_symlink() or not resolved.is_relative_to(boundary)
                or not resolved.is_file() or resolved.stat().st_size > 10_000_000):
            raise ValueError("Trace must be a regular <=10 MB file within .ai/runtime")
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Runtime trace must contain a JSON object")
        traces.append(payload)
    if len(traces) == 1:
        item = traces[0]
        events = item.get("events")
        if (item.get("kind") != "doctor_runtime_observation"
                or item.get("candidate_sha") != graph_sha
                or item.get("worktree_clean") is not True
                or item.get("truncated") is not False
                or not isinstance(events, list) or len(events) > 50000
                or any(not isinstance(row, dict) for row in events)):
            raise ValueError("Runtime trace is stale, truncated or incomplete")
        selected_events = ({**event, "_trace_group": 0} for event in events)
    else:
        selected_events = iter(merge_runtime_traces(traces, graph_sha=graph_sha)["events"])
    observed: dict[str, dict[str, Any]] = {}
    for event in selected_events:
        kind = event.get("type")
        source, target = event.get("source"), event.get("target")
        path: str | None = None
        proof: str | None = None
        if kind == "python_call_edge":
            path, proof = target, "PYTHON_CALL_ENTERED"
        elif (kind == "qt_callback_invoked"
              and event.get("confidence") == "WRAPPED_PYTHON_CALLBACK_ENTERED"):
            path, proof = target, "QT_CALLBACK_ENTERED"
        elif (kind == "module_import_returned"
              and event.get("confidence") == "IMPORTLIB_RETURNED_REPOSITORY_MODULE"):
            path, proof = target, "DYNAMIC_MODULE_RESOLVED_NOT_EXECUTED"
        elif kind == "qt_destroyed_observed":
            path, proof = source, "QT_DESTROYED_SIGNAL"
        elif (kind in {"qt_worker_started", "qt_worker_finished"} and
              event.get("confidence") == ("QT_STARTED_SIGNAL_DELIVERED" if kind == "qt_worker_started"
                                             else "QT_FINISHED_SIGNAL_DELIVERED")):
            path, proof = source, "QT_WORKER_STARTED" if kind == "qt_worker_started" else "QT_WORKER_FINISHED"
        elif kind == "json_decoded" and event.get("confidence") == "JSON_DECODE_RETURNED":
            path, proof = source, "JSON_DECODE_RETURNED"
        elif kind == "import_attempt":
            path, proof = source, "IMPORT_ATTEMPT_SITE_ONLY"
        if (not isinstance(path, str) or not path.endswith(".py")
                or path.startswith("/") or "\\" in path
                or any(part in ("", ".", "..") for part in path.split("/"))):
            continue
        group = event.get("_trace_group", 0)
        if not isinstance(group, int) or isinstance(group, bool) or group < 0 or group >= len(traces):
            continue
        row = observed.setdefault(path, {"kinds": set(), "scenarios": set()})
        row["kinds"].add(proof)
        row["scenarios"].add(group)
    return {file: {"kinds": sorted(v["kinds"]), "scenario_count": len(v["scenarios"]),
                   "entered_as_consumer": bool({"PYTHON_CALL_ENTERED", "QT_CALLBACK_ENTERED"}
                                               & v["kinds"])}
            for file, v in observed.items()}


def triage_isolates(root: Path, *, limit: int = 5, kind: str = 'mixed', offset: int = 0,
                    trace_paths: list[Path] | None = None) -> dict[str, Any]:
    from .architecture import graph_status
    from .graph_audit import inspect_graph
    from .consumer_sites import inspect_consumer_sites
    if not 1 <= limit <= 10:
        raise ValueError("Expected 1..10 files per isolated-node investigation.")
    if kind not in {"mixed", "weak", "orphan", "community"} or not 0 <= offset <= 100000:
        raise ValueError("Invalid candidate kind or offset.")
    root = root.resolve()
    graph = graph_status(root)
    result: dict[str, Any] = {
        "schema_version": 1, "kind": "doctor_isolate_triage",
        "graph_status": graph.get("status"), "limit": limit, "kind": kind, "offset": offset,
        "dead_code_proven": False, "automatic_edits": False,
        "tests_executed": False, "graph_rebuilt": False,
    }
    if graph.get("status") != "PASS":
        return {**result, "status": "BLOCKED", "reason": "Current exact-SHA Graphify required."}
    path = Path(graph["graph"])
    try:
        raw_bytes = path.read_bytes()
        if hashlib.sha256(raw_bytes).hexdigest() != graph["graph_signature"]:
            raise ValueError("Graph fingerprint changed; no stale evidence.")
        raw = json.loads(raw_bytes)
        if kind == 'orphan':
            audit = inspect_graph(raw, root=root, orphan_offset=offset)
        elif kind == 'weak':
            audit = inspect_graph(raw, root=root, weak_offset=offset)
        elif kind == 'community':
            audit = inspect_graph(raw, root=root, community_offset=offset)
        else:
            audit = inspect_graph(raw, root=root)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return {**result, "status": "BLOCKED", "reason": str(exc)}
    picked: list[tuple[str, str]] = []
    seen: set[str] = set()
    inspected_rows = 0
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    if kind in {"mixed", "orphan"}:
        groups.append(("ISOLATED_NODE", audit["orphan_nodes"]))
    if kind in {"mixed", "weak"}:
        groups.append(("WEAK_NODE", audit["weak_production_candidates"]))
    if kind == "community":
        groups.append(("ISOLATED_COMMUNITY", audit["isolated_communities"]))
    for classification, candidates in groups:
        for row in candidates:
            if len(picked) >= limit:
                break
            inspected_rows += 1
            choices = row.get("sample_source_files", []) if classification == "ISOLATED_COMMUNITY" else [row.get("file")]
            for name in choices:
                if not isinstance(name, str) or not name.startswith("app/") or not name.endswith(".py"):
                    continue
                if name.endswith("/__init__.py") or name in seen:
                    continue
                seen.add(name)
                picked.append((name, classification))
                break
        if len(picked) >= limit:
            break
    raw_total = ((audit.get("limits") or {}).get("weak_total") if kind == "weak"
                 else (audit.get("limits") or {}).get("orphan_total", len(audit["orphan_nodes"])) if kind == "orphan"
                 else (audit.get("limits") or {}).get("community_total", len(audit["isolated_communities"])) if kind == "community"
                 else None)
    next_offset = (offset + inspected_rows if isinstance(raw_total, int)
                   and offset + inspected_rows < raw_total and inspected_rows > 0 else None)
    trace_evidence: dict[str, dict[str, Any]] = {}
    if trace_paths:
        try:
            trace_evidence = _trace_observations(root, trace_paths, raw.get("built_at_commit"))
        except (OSError, ValueError, UnicodeError, TypeError) as exc:
            return {**result, "status": "BLOCKED",
                    "reason": f"Invalid exact-SHA trace: {exc}"}
    entries = []
    for name, reason in picked[:limit]:
        scan = inspect_consumer_sites(root, name)
        confidence = ("HAS_SOURCE_IMPORT_CONSUMERS" if scan["static_confirmed_count"]
                      else "HAS_DYNAMIC_CANDIDATES" if scan["dynamic_lead_count"]
                      else "UNRESOLVED_NO_CONSUMER_PROOF")
        runtime = trace_evidence.get(name, {})
        entries.append({
            "file": name, "signal": reason, "review": confidence,
            "runtime_review": ("OBSERVED_CONSUMER_IN_SUPPLIED_SCENARIO"
                               if runtime.get("entered_as_consumer")
                               else "DYNAMIC_MODULE_RESOLVED_NOT_EXECUTED"
                               if "DYNAMIC_MODULE_RESOLVED_NOT_EXECUTED" in runtime.get("kinds", [])
                               else "POSITIVE_RUNTIME_SIDE_EFFECT_ONLY"
                               if runtime else "NOT_OBSERVED_NOT_DEAD_CODE"
                               if trace_paths else "NO_RUNTIME_TRACES_PROVIDED"),
            "runtime_scenarios_observed": runtime.get("scenario_count", 0),
            "runtime_evidence_kinds": runtime.get("kinds", []),
            "static_confirmed_count": scan["static_confirmed_count"],
            "dynamic_lead_count": scan["dynamic_lead_count"],
            "candidate_files": scan["candidate_files"],
            "scan_truncated": scan["truncated"],
            "source_errors": scan["source_errors"],
            "safe_to_remove": False,
        })
    return {
        **result, "status": "REVIEW", "candidates_available": len(picked),
        "candidates_inspected": len(entries),
        "truncated": bool(next_offset) or (kind == "mixed" and (inspected_rows < len(audit["orphan_nodes"]) + len(audit["weak_production_candidates"]) or bool((audit.get("limits") or {}).get("unreported_weak_nodes")))),
        "findings": entries, "next_offset": next_offset, "candidate_total_raw": raw_total,
        "runtime_traces_provided": len(trace_paths or []),
        "next_action": "Inspect tests, plugin entries, Qt signal bindings and runtime traces before any deletion.",
        "coverage": "Bounded 30-item candidate window; --kind orphan/weak/community --offset pages raw candidates. Not proof of dead code.",
    }
