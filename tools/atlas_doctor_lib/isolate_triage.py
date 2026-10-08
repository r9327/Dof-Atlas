from __future__ import annotations

"""Bounded Doctor triage of isolated Graphify symbols and files.

No evidence of a reference is not evidence that code is dead.
"""
import hashlib
import json
from pathlib import Path
from typing import Any


def triage_isolates(root: Path, *, limit: int = 5, kind: str = 'mixed', offset: int = 0) -> dict[str, Any]:
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
        audit = inspect_graph(raw, root=root, weak_offset=offset if kind == 'weak' else 0)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        return {**result, "status": "BLOCKED", "reason": str(exc)}
    picked: list[tuple[str, str]] = []
    seen: set[str] = set()
    inspected_rows = 0
    groups: list[tuple[str, list[dict[str, Any]]]] = []
    if kind in {"mixed", "orphan"}:
        groups.append(("ISOLATED_NODE", audit["orphan_nodes"][offset:] if kind == "orphan" else audit["orphan_nodes"]))
    if kind in {"mixed", "weak"}:
        groups.append(("WEAK_NODE", audit["weak_production_candidates"]))
    if kind == "community":
        groups.append(("ISOLATED_COMMUNITY", audit["isolated_communities"][offset:]))
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
                 else len(audit["orphan_nodes"]) if kind == "orphan"
                 else len(audit["isolated_communities"]) if kind == "community"
                 else None)
    next_offset = (offset + inspected_rows if isinstance(raw_total, int)
                   and offset + inspected_rows < raw_total and inspected_rows > 0 else None)
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
        "truncated": bool(next_offset) or (kind == "mixed" and (inspected_rows < len(audit["orphan_nodes"]) + len(audit["weak_production_candidates"]) or bool((audit.get("limits") or {}).get("unreported_weak_nodes")))),
        "findings": entries, "next_offset": next_offset, "candidate_total_raw": raw_total,
        "next_action": "Inspect tests, plugin entries, Qt signal bindings and runtime traces before any deletion.",
        "coverage": "Bounded 30-item candidate window; --kind weak --offset paginates raw nodes. Not proof of dead code.",
    }
