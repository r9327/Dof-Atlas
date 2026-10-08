from __future__ import annotations

"""Non-mutating architectural refactor preview using the canonical Agent graph."""
from pathlib import Path
from typing import Any

MAX_TARGETS = 10


def simulate_refactor(
    root: Path, paths: list[str], *, action: str = "remove",
    replacement: str | None = None, depth: int = 2,
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
        target = (root / candidate).resolve()
        if not target.is_relative_to(root) or not target.is_file() or target.suffix != ".py":
            raise ValueError(f"Not an existing Python module: {item}")
        normalized.append(target.relative_to(root).as_posix())
    if action != "remove":
        if not replacement:
            raise ValueError("New relative destination path required")
        destination = Path(replacement.replace("\\\\", "/"))
        if (destination.is_absolute() or ".." in destination.parts
                or ":" in destination.parts[0] or destination.suffix != ".py"):
            raise ValueError("New repository-relative Python destination required")
        resolved = (root / destination).resolve()
        if not resolved.is_relative_to(root) or resolved.is_symlink():
            raise ValueError("Destination escapes repository or is a symlink")
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
        "consumer_files": sorted(set(impact.get("impacted_files", [])) - set(normalized)),
        "limitations": [
            "Graph-derived relations are confirmed against literal Python imports, not arbitrary runtime callbacks.",
            "A preview cannot prove absence of dynamic consumers or that consolidation preserves behavior.",
            "No file will be modified without a reviewed implementation plan.",
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
