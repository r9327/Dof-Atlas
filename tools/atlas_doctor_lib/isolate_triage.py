from __future__ import annotations

"""Bounded Doctor triage of isolated Graphify symbols and files.

No evidence of a reference is not evidence that code is dead.
"""
import hashlib
import json
from pathlib import Path
from typing import Any


def triage_isolates(root: Path, *, limit: int = 5) -> dict[str, Any]:
    from .architecture import graph_status
    from .graph_audit import inspect_graph
    from .consumer_sites import inspect_consumer_sites
    if not 1 <= limit <= 10:
        raise ValueError("Expected 1..10 files per isolated-node investigation.")
    root = root.resolve()
    graph = graph_status(root)
    result: dict[str, Any] = {
        "schema_version": 1, "kind": "doctor_isolate_triage",
        "graph_status": graph.get("status"), "limit": limit,
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
        audit = inspect_graph(raw, root=root)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return {**result, "status": "BLOCKED", "reason": str(exc)}
    picked: list[tuple[str, str]] = []
    seen = set()
    for kind, rows in (
        ("ISOLATED_NODE", audit["orphan_nodes"]),
        ("WEAK_NODE", audit["weak_production_candidates"]),
    ):
        for row in rows:
            name = row.get("file")
            if not isinstance(name, str) or not name.startswith("app/") or not name.endswith(".py"):
                continue
            if name.endswith("/__init__.py") or name in seen:
                continue
            seen.add(name)
            picked.append((name, kind))
    entries = []
    for name, reason in picked[:limit]:
        scan = inspect_consumer_sites(root, name)
        confidence = ("HAS_SOURCE_IMPORT_CONSUMERS" if scan["static_confirmed_count"]
                      else "HAS_DYNAMIC_CANDIDATES" if scan["dynamic_lead_count"]
                      else "UNRESOLVED_NO_CONSUMER_PROOF")
        entries.append({
            "file": name, "signal": reason, "review": confidence,
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
        "truncated": len(picked) > limit,
        "findings": entries,
        "next_action": "Inspect tests, plugin entries, Qt signal bindings and runtime traces before any deletion.",
        "coverage": "Graphify candidate page only (max 30 per class); no zero-consumer proof.",
    }
