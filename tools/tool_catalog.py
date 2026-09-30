from __future__ import annotations

"""AI-oriented, read-only catalog derived from the repository tooling inventory.

The catalog is intentionally generated from code and repository references instead
of a hand-maintained manifest. It helps agents choose safe/canonical entry points
without creating a second source of truth or executing the tools it describes.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from tools.tool_audit import ROOT, audit as tooling_audit


_SCHEMA_VERSION = 1
_PREFERRED_ENTRYPOINTS = {
    "tools/agent.py": "agent_context_and_routing",
    "tools/ai_context.py": "ai_context_maintenance",
    "tools/atlas_integrity.py": "repository_validation_orchestrator",
    "tools/guide_integrity.py": "guide_validation_orchestrator",
    "tools/tool_audit.py": "tooling_inventory",
    "tools/tool_catalog.py": "ai_tool_discovery",
}
_EXPENSIVE_HINTS = (
    "deep",
    "full",
    "mutation",
    "fault",
    "performance",
    "certification",
    "run_guide_ultime_ci",
)
_VARIABLE_HINTS = ("agent.py", "atlas_integrity.py", "guide_integrity.py")
_COST_ORDER = {"cheap": 0, "unknown": 1, "variable": 2, "expensive": 3}
_CAPABILITY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ai_context", ("ai_context", "agent")),
    ("validation", ("integrity", "validate", "validation", "audit", "check", "certification")),
    ("guide", ("guide",)),
    ("performance", ("performance", "startup", "budget")),
    ("coverage", ("coverage",)),
    ("mutation_testing", ("mutation", "fault_injection", "random_order")),
    ("git", ("git_hook", "pre_commit", "pre_push")),
    ("worldmap", ("worldmap", "world_scan")),
    ("quest_data", ("quest",)),
    ("generation", ("build_", "generate_", "apply_", "repair_", "promote_")),
)
_LEGACY_ACTIONS = {
    "absorb_or_remove_thin_wrapper_after_contract_review",
    "collapse_version_family_after_consumer_review",
}
_BLOCKING_AGENT_ACTIONS = {
    "fix_parse_error",
    "make_default_read_only_and_require_explicit_apply_flag",
}


def _read_source(root: Path, relative: str) -> str:
    try:
        return (root / relative).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def _supports_json(source: str) -> bool:
    lowered = source.casefold()
    return "--json" in lowered or "json.dumps(" in lowered or "convertto-json" in lowered


def _supports_describe(source: str) -> bool:
    lowered = source.casefold()
    return "--describe" in lowered or ("describe" in lowered and "argparse" in lowered)


def _supports_help(source: str, kind: str) -> bool:
    lowered = source.casefold()
    if kind in {"python", "py"}:
        return "argparse.argumentparser" in lowered or "click." in lowered or "typer." in lowered
    return "param(" in lowered or "--help" in lowered or "-help" in lowered


def _invocation(path: str, kind: str) -> str:
    if kind in {"python", "py"} and path.endswith(".py"):
        return "py -3.13 -m " + path[:-3].replace("/", ".")
    return path.replace("/", "\\")


def _cost_hint(path: str) -> str:
    lowered = path.casefold()
    if any(token in lowered for token in _VARIABLE_HINTS):
        return "variable"
    if any(token in lowered for token in _EXPENSIVE_HINTS):
        return "expensive"
    if any(token in lowered for token in ("doctor", "context", "check_generated", "tool_audit", "tool_catalog")):
        return "cheap"
    return "unknown"


def _capabilities(path: str) -> list[str]:
    lowered = path.casefold()
    result: list[str] = []
    for capability, hints in _CAPABILITY_HINTS:
        if any(hint in lowered for hint in hints):
            result.append(capability)
    return result or ["maintenance"]


def _upgrade_actions(
    row: dict[str, Any],
    *,
    source: str,
    version_members: set[str],
) -> list[str]:
    actions: list[str] = []
    path = str(row["path"])
    if row.get("parse_error"):
        actions.append("fix_parse_error")
    if row.get("path_hack"):
        actions.append("remove_sys_path_hack")
    if row.get("cwd_dependency"):
        actions.append("anchor_paths_to_repository_root")
    if row.get("mutation_capable") and not row.get("explicit_mutation_gate"):
        actions.append("make_default_read_only_and_require_explicit_apply_flag")
    if row.get("executable") and not _supports_json(source):
        actions.append("add_stable_json_output")
    if row.get("executable") and not _supports_help(source, str(row.get("kind", ""))):
        actions.append("add_discoverable_cli_help")
    if row.get("executable") and not row.get("test_references"):
        actions.append("add_targeted_contract_tests")
    if row.get("wrapper"):
        actions.append("absorb_or_remove_thin_wrapper_after_contract_review")
    if path in version_members:
        actions.append("collapse_version_family_after_consumer_review")
    return actions


def _readiness_score(row: dict[str, Any], source: str, version_members: set[str]) -> int:
    score = 100
    if row.get("parse_error"):
        score -= 60
    if row.get("path_hack"):
        score -= 15
    if row.get("cwd_dependency"):
        score -= 15
    if row.get("mutation_capable") and not row.get("explicit_mutation_gate"):
        score -= 30
    if row.get("executable") and not _supports_json(source):
        score -= 15
    if row.get("executable") and not row.get("test_references"):
        score -= 15
    if row.get("wrapper"):
        score -= 10
    if row.get("path") in version_members:
        score -= 10
    return max(0, min(100, score))


def _readiness_label(score: int, actions: list[str]) -> str:
    action_set = set(actions)
    if action_set & _BLOCKING_AGENT_ACTIONS:
        return "review_before_agent_use"
    if action_set & _LEGACY_ACTIONS:
        return "legacy_review"
    if actions or score < 85:
        return "usable_with_upgrade"
    return "agent_ready"


def catalog(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    inventory = tooling_audit(root)
    version_members = {
        member
        for family in inventory.get("versioned_families", [])
        for member in family.get("members", [])
    }
    tools: list[dict[str, Any]] = []
    for row in inventory.get("tools", []):
        path = str(row["path"])
        source = _read_source(root, path)
        actions = _upgrade_actions(row, source=source, version_members=version_members)
        score = _readiness_score(row, source, version_members)
        readiness = _readiness_label(score, actions)
        preferred_role = _PREFERRED_ENTRYPOINTS.get(path)
        structured_output = _supports_json(source)
        mutation_state = (
            "none"
            if not row.get("mutation_capable")
            else "guarded"
            if row.get("explicit_mutation_gate")
            else "unguarded"
        )
        legacy = bool(row.get("wrapper")) or path in version_members
        role = "entrypoint" if row.get("executable") else "library"
        safe_for_agent = (
            mutation_state != "unguarded"
            and readiness != "review_before_agent_use"
        )
        automation_ready = (
            role == "entrypoint"
            and safe_for_agent
            and readiness == "agent_ready"
            and not legacy
        )
        tools.append(
            {
                "path": path,
                "role": role,
                "preferred_role": preferred_role,
                "preferred_for_agent": preferred_role is not None,
                "canonicality": (
                    "preferred" if preferred_role is not None else "legacy" if legacy else "specialized"
                ),
                "invocation": _invocation(path, str(row.get("kind", ""))),
                "capabilities": _capabilities(path),
                "cost_hint": _cost_hint(path),
                "structured_output": structured_output,
                "describe_contract": _supports_describe(source),
                "discoverable_help": _supports_help(source, str(row.get("kind", ""))),
                "mutation_state": mutation_state,
                "repository_root_anchored": not bool(row.get("cwd_dependency")),
                "import_path_clean": not bool(row.get("path_hack")),
                "targeted_tests": list(row.get("test_references", [])),
                "references": list(row.get("references", [])),
                "readiness_score": score,
                "readiness": readiness,
                "safe_for_agent": safe_for_agent,
                "automation_ready": automation_ready,
                "upgrade_actions": actions,
            }
        )

    ready = [row for row in tools if row["readiness"] == "agent_ready"]
    automation_ready = [row for row in tools if row["automation_ready"]]
    review = [
        row
        for row in tools
        if row["readiness"] in {"review_before_agent_use", "legacy_review"}
    ]
    preferred = [row for row in tools if row["preferred_for_agent"]]
    structured = [row for row in tools if row["structured_output"]]
    unguarded = [row for row in tools if row["mutation_state"] == "unguarded"]
    return {
        "schema_version": _SCHEMA_VERSION,
        "source": "derived_from_tools.tool_audit_and_repository_sources",
        "read_only": True,
        "tool_count": len(tools),
        "agent_ready_count": len(ready),
        "automation_ready_count": len(automation_ready),
        "structured_output_count": len(structured),
        "preferred_entrypoint_count": len(preferred),
        "unguarded_mutator_count": len(unguarded),
        "preferred_entrypoints": [
            {
                "path": row["path"],
                "role": row["preferred_role"],
                "invocation": row["invocation"],
                "readiness": row["readiness"],
                "readiness_score": row["readiness_score"],
                "safe_for_agent": row["safe_for_agent"],
                "automation_ready": row["automation_ready"],
            }
            for row in preferred
        ],
        "agent_use_review_required": [row["path"] for row in review],
        "tools": tools,
        "policy": {
            "default": "prefer preferred_entrypoints; use specialized tools only when their capability is required",
            "automatic_execution": "require automation_ready=true; safe_for_agent alone is not enough",
            "mutations": "never call an unguarded mutator automatically",
            "legacy": "versioned/wrapper/unreferenced tools require contract and consumer review before deletion or AI automation",
            "heavy_checks": "respect cost_hint and route expensive validation through canonical orchestrators",
        },
    }


def select_tools(
    report: dict[str, Any],
    *,
    capability: str | None = None,
    max_cost: str | None = None,
    safe_only: bool = False,
    ready_only: bool = False,
    preferred_only: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    if max_cost is not None and max_cost not in _COST_ORDER:
        raise ValueError(f"unsupported max_cost: {max_cost}")
    rows: list[dict[str, Any]] = []
    for row in report["tools"]:
        if capability and capability not in row["capabilities"]:
            continue
        if preferred_only and not row["preferred_for_agent"]:
            continue
        if safe_only and not row["safe_for_agent"]:
            continue
        if ready_only and not row["automation_ready"]:
            continue
        if max_cost is not None and _COST_ORDER[row["cost_hint"]] > _COST_ORDER[max_cost]:
            continue
        rows.append(row)

    rows.sort(
        key=lambda row: (
            0 if row["preferred_for_agent"] else 1,
            0 if row["automation_ready"] else 1,
            -int(row["readiness_score"]),
            _COST_ORDER[row["cost_hint"]],
            row["path"],
        )
    )
    if limit is not None:
        rows = rows[: max(0, limit)]
    return {
        "schema_version": _SCHEMA_VERSION,
        "source": "tools.tool_catalog.select_tools",
        "read_only": True,
        "filters": {
            "capability": capability,
            "max_cost": max_cost,
            "safe_only": safe_only,
            "ready_only": ready_only,
            "preferred_only": preferred_only,
            "limit": limit,
        },
        "match_count": len(rows),
        "tools": rows,
    }


def _print_summary(report: dict[str, Any]) -> None:
    print(
        "AI tool catalog: tools={tool_count} ready={agent_ready_count} "
        "automation_ready={automation_ready_count} structured={structured_output_count} "
        "preferred={preferred_entrypoint_count} unguarded_mutators={unguarded_mutator_count}".format(**report)
    )
    print("preferred entrypoints:")
    for row in report["preferred_entrypoints"]:
        print(
            f"  - {row['path']}: {row['role']} | {row['readiness']} "
            f"({row['readiness_score']}/100) | safe={row['safe_for_agent']} "
            f"| auto={row['automation_ready']} | {row['invocation']}"
        )


def _print_selection(selection: dict[str, Any]) -> None:
    print(f"AI tool selection: matches={selection['match_count']}")
    for row in selection["tools"]:
        print(
            f"  - {row['path']} | {row['readiness']} | cost={row['cost_hint']} "
            f"| safe={row['safe_for_agent']} | auto={row['automation_ready']} "
            f"| mutation={row['mutation_state']} | {row['invocation']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only AI catalog of Dofus Atlas repository tools."
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    parser.add_argument("--tool", default=None, help="Restrict output to one exact tools/... path.")
    parser.add_argument("--capability", default=None, help="Select tools exposing one derived capability.")
    parser.add_argument("--max-cost", choices=tuple(_COST_ORDER), default=None)
    parser.add_argument("--safe-only", action="store_true", help="Exclude tools requiring a safety review.")
    parser.add_argument("--ready-only", action="store_true", help="Return only automation-ready entry points.")
    parser.add_argument("--preferred-only", action="store_true", help="Return canonical agent entry points only.")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    report = catalog(ROOT)
    selection_requested = any(
        (
            args.capability,
            args.max_cost,
            args.safe_only,
            args.ready_only,
            args.preferred_only,
            args.limit is not None,
        )
    )
    if args.tool:
        rows = [row for row in report["tools"] if row["path"] == args.tool]
        if not rows:
            parser.error(f"unknown tool path: {args.tool}")
        payload: Any = rows[0]
        output_kind = "tool"
    elif selection_requested:
        payload = select_tools(
            report,
            capability=args.capability,
            max_cost=args.max_cost,
            safe_only=args.safe_only,
            ready_only=args.ready_only,
            preferred_only=args.preferred_only,
            limit=args.limit,
        )
        output_kind = "selection"
    else:
        payload = report
        output_kind = "catalog"

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif output_kind == "tool":
        for key, value in payload.items():
            print(f"{key}: {value}")
    elif output_kind == "selection":
        _print_selection(payload)
    else:
        _print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
