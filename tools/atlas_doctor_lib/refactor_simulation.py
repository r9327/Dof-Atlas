from __future__ import annotations

"""Non-mutating architectural refactor preview using the canonical Agent graph."""
from pathlib import Path
from typing import Any
import json
import subprocess

MAX_TARGETS = 10


def _path_uses_symlink(root: Path, relative: Path) -> bool:
    """Reject symlink sources and symlinked parent directories before resolve."""
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False




MAX_RUNTIME_EVENTS = 50000
MAX_RUNTIME_CONSUMERS = 60


def _runtime_consumer_evidence(
    root: Path, targets: list[str], trace_path: Path | None,
) -> dict[str, Any]:
    """Correlate opt-in positives only; never derive deletion safety from silence."""
    empty = {
        "status": "NOT_PROVIDED" if trace_path is None else "UNAVAILABLE",
        "observed_python_consumers": [],
        "qt_registration_sites": [],
        "qt_callback_invocations": [],
        "events_examined": 0,
        "truncated": False,
        "absence_proves_unused": False,
    }
    if trace_path is None:
        return empty
    try:
        original = Path(trace_path)
        selected = original.resolve()
        trace_dir = (root / ".ai" / "runtime").resolve()
        if not selected.is_relative_to(trace_dir) or original.is_symlink():
            raise ValueError("Trace must be a regular file inside .ai/runtime")
        if not selected.is_file() or selected.stat().st_size > 10_000_000:
            raise ValueError("Trace missing or larger than 10 MB")
        trace = json.loads(selected.read_text(encoding="utf-8"))
        if not isinstance(trace, dict) or trace.get("kind") != "doctor_runtime_observation":
            raise ValueError("Invalid Doctor runtime trace payload")
        events = trace.get("events")
        if not isinstance(events, list) or len(events) > MAX_RUNTIME_EVENTS:
            raise ValueError("Invalid or oversized runtime event list")
        if any(not isinstance(event, dict) for event in events):
            raise ValueError("Malformed runtime event")
        head = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=root,
            capture_output=True, text=True, check=False, timeout=5,
        )
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=root,
            capture_output=True, text=True, check=False, timeout=8,
        )
        if (head.returncode != 0 or status.returncode != 0
                or len(head.stdout.strip()) != 40
                or trace.get("candidate_sha") != head.stdout.strip()
                or trace.get("worktree_clean") is not True
                or trace.get("truncated") is not False
                or status.stdout.strip()):
            return {**empty, "status": "STALE",
                    "reason": "Exact HEAD, clean worktree and complete runtime trace required.",
                    "events_examined": len(events)}
        python_rows: set[tuple[str, str]] = set()
        qt_rows: set[tuple[str, str]] = set()
        qt_callback_rows: set[tuple[str, str]] = set()
        for event in events:
            kind = event.get("type")
            if kind not in {"python_call_edge", "python_symbol_call", "qt_signal_connect_returned", "qt_callback_invoked"}:
                continue
            source, target = event.get("source"), event.get("target")
            if not isinstance(source, str) or not isinstance(target, str) or target not in targets:
                continue
            path = Path(source)
            if (not source.endswith(".py") or path.is_absolute()
                    or ".." in path.parts or "\\" in source
                    or source == target or not (root / path).is_file()):
                continue
            if kind == "qt_signal_connect_returned":
                qt_rows.add((source, target))
            elif kind == "qt_callback_invoked":
                if event.get("confidence") == "WRAPPED_PYTHON_CALLBACK_ENTERED":
                    qt_callback_rows.add((source, target))
            else:
                python_rows.add((source, target))
        python_sorted, qt_sorted = sorted(python_rows), sorted(qt_rows)
        return {
            "status": "MATCHED", "candidate_sha": head.stdout.strip(),
            "observed_python_consumers": [
                {"source": source, "target": target, "confidence": "OBSERVED_PYTHON_CALL"}
                for source, target in python_sorted[:MAX_RUNTIME_CONSUMERS]
            ],
            "qt_registration_sites": [
                {"source": source, "target": target,
                 "confidence": "CONNECT_RETURNED_NOT_CALLBACK_INVOKED"}
                for source, target in qt_sorted[:MAX_RUNTIME_CONSUMERS]
            ],
            "qt_callback_invocations": [
                {"source": source, "target": target, "confidence": "WRAPPED_PYTHON_CALLBACK_ENTERED"}
                for source, target in sorted(qt_callback_rows)[:MAX_RUNTIME_CONSUMERS]
            ],
            "events_examined": len(events),
            "truncated": (len(qt_callback_rows) > MAX_RUNTIME_CONSUMERS
                          or len(python_rows) > MAX_RUNTIME_CONSUMERS
                          or len(qt_rows) > MAX_RUNTIME_CONSUMERS
                          or trace.get("symbol_edges_truncated") is True),
            "absence_proves_unused": False,
            "limits": "Observed positives only; Qt connect is not callback execution or native ownership.",
        }
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
        return {**empty, "reason": f"Runtime evidence unavailable: {type(exc).__name__}"}


def simulate_refactor(
    root: Path, paths: list[str], *, action: str = "remove",
    replacement: str | None = None, depth: int = 2,
    trace_path: Path | None = None,
) -> dict[str, Any]:
    from tools import agent
    root = root.resolve()
    if action not in {"remove", "move", "consolidate"}:
        raise ValueError("action must be remove, move or consolidate")
    if not 1 <= len(set(paths)) <= MAX_TARGETS:
        raise ValueError(f"Expected 1..{MAX_TARGETS} paths")
    if depth not in {1, 2}:
        raise ValueError("Only dependency depths 1 and 2 are supported.")
    normalized: list[str] = []
    for item in sorted(set(paths)):
        candidate = Path(item.replace("\\", "/"))
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("Repository-relative paths required")
        if _path_uses_symlink(root, candidate):
            raise ValueError(f"Refactor source is a symlink: {item}")
        target = (root / candidate).resolve()
        if not target.is_relative_to(root) or not target.is_file() or target.suffix != ".py":
            raise ValueError(f"Not an existing Python module: {item}")
        normalized.append(target.relative_to(root).as_posix())
    if action != "remove":
        if not replacement:
            raise ValueError("New relative destination path required")
        destination = Path(replacement.replace(chr(92), "/"))
        if (destination.is_absolute() or ".." in destination.parts
                or ":" in destination.parts[0] or destination.suffix != ".py"):
            raise ValueError("New repository-relative Python destination required")
        unresolved = root / destination
        if _path_uses_symlink(root, destination):
            raise ValueError("Destination or ancestor is a symlink")
        resolved = unresolved.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("Destination escapes repository")
        replacement = resolved.relative_to(root).as_posix()
        if replacement in normalized:
            raise ValueError("Destination cannot overwrite a source under review")
        if action == "move" and len(normalized) != 1:
            raise ValueError("Moving multiple files to one destination is ambiguous")
        if action == "move" and resolved.exists():
            raise ValueError("Move destination already exists")
        if action == "consolidate" and resolved.exists() and not resolved.is_file():
            raise ValueError("Consolidation destination is not a file")
    else:
        replacement = None
    impact = agent.reverse_impact_payload(root, normalized, depth=depth)
    runtime = _runtime_consumer_evidence(root, normalized, trace_path)
    consolidation_similarity: dict[str, Any] | None = None
    if action == "consolidate":
        from .deep_intelligence import scan_sources
        compared = normalized + ([replacement] if replacement and (root / replacement).is_file() else [])
        evidence = scan_sources(root, compared)
        consolidation_similarity = {
            "status": evidence["status"],
            "exact_body_groups": evidence.get("duplicate_bodies", [])[:20],
            "similar_body_groups": evidence.get("near_duplicate_candidates", [])[:20],
            "truncated": evidence.get("truncated", False),
            "semantic_equivalence_proven": False,
            "automatic_consolidation_allowed": False,
            "reason": "Matching AST bodies are candidates; APIs, side effects and callers still require review.",
        }
    base = {
        "schema_version": 1, "kind": "doctor_refactor_simulation",
        "read_only": True, "automatic_edit": False, "tests_executed": False,
        "graph_rebuilt": False, "action": action, "targets": normalized,
        "replacement": replacement, "depth": depth,
        "graph_status": (impact.get("graph") or {}).get("status"),
        "consumer_evidence": {
            "confirmed": impact.get("confirmed_relationships", [])[:50],
            "unconfirmed": impact.get("unconfirmed_relationships", [])[:30],
            "truncated": impact.get("truncated", False),
            "source_errors": impact.get("source_errors", []),
        },
        "consumer_files": sorted((set(impact.get("impacted_files", [])) | (
            {row["source"] for kind in ("observed_python_consumers", "qt_registration_sites", "qt_callback_invocations")
             for row in runtime[kind]} if runtime["status"] == "MATCHED" else set()
        )) - set(normalized)),
        "runtime_evidence": runtime,
        "consolidation_similarity": consolidation_similarity,
        "limitations": [
            "Graph-derived relations are confirmed against literal Python imports, not arbitrary runtime callbacks.",
            "A preview cannot prove absence of dynamic consumers or that consolidation preserves behavior.",
            "No file will be modified without a reviewed implementation plan.",
            "Observed Python calls, Qt registrations and explicitly wrapped callback entries are scenario-specific positives, not complete coverage.",
        ],
    }
    if impact.get("status") not in {"PASS", "REVIEW"} or (impact.get("graph") or {}).get("status") != "PASS":
        base.update(status="BLOCKED", reason=impact.get("reason") or "Current exact-SHA Graphify is required.",
                    proposed_edits=[], targeted_tests=[], certification={"status": "NOT_RUN"})
        return base
    # The existing Agent/Integrity planner remains the authority on test floor.
    plan = agent.plan_payload(root, normalized, structural=True)
    base.update(
        status="REVIEW",
        reason="Source-confirmed consumers and required validation are identified; approval needed.",
        proposed_edits=[
            {"path": path, "action": "review import/contract and update consumer"}
            for path in base["consumer_files"]
        ] + [{"path": path, "action": action} for path in normalized],
        targeted_tests=plan.get("execution_tests", []),
        recommended_tests=plan.get("recommended_tests", []),
        certification={
            "status": "DEFERRED_NOT_WAIVED", "minimum_mode": plan.get("integrity_mode"),
            "required_groups": plan.get("required_groups", []),
        },
        ownership_review=plan.get("ownership", {}),
        planning_status=plan.get("status"),
        next_action="Review unknown runtime consumers, approve edits, then run targeted tests and required certification.",
    )
    return base
