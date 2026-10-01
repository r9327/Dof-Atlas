from __future__ import annotations

"""Read-only planning engine for AI-assisted repository changes.

This module deliberately does not own scope matching, risk classification, tool
inventory, or validation execution. It composes the canonical Agent impact data,
Atlas Integrity policy/classification, and the AI tool catalog into one stable
plan that callers can inspect before editing or validating the repository.
"""

from pathlib import Path
from typing import Any, Iterable

from tools import atlas_integrity
from tools.tool_catalog import catalog as tooling_catalog


ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_VERSION = 1
_MODE_ORDER = ("FAST", "CRITICAL", "FULL", "DEEP")


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def required_groups(
    policy: dict[str, Any],
    classification: dict[str, Any],
) -> list[str]:
    risk = str(classification.get("risk", "LOW")).upper()
    risk_requirements = policy.get("risk_requirements", {}).get(risk, [])
    affected = classification.get("affected_groups", [])
    return sorted(set(str(group) for group in [*risk_requirements, *affected]))


def minimum_integrity_mode(
    policy: dict[str, Any],
    classification: dict[str, Any],
) -> str:
    required = set(required_groups(policy, classification))
    modes = policy.get("modes", {})
    for mode in _MODE_ORDER:
        groups = set(str(group) for group in modes.get(mode, []))
        if required.issubset(groups):
            return mode
    return "DEEP"


def _preferred_validation_tools(
    report: dict[str, Any],
    *,
    scopes: Iterable[str],
    paths: Iterable[str],
) -> list[dict[str, Any]]:
    scope_values = {str(scope) for scope in scopes}
    path_values = [str(path).casefold() for path in paths]
    guide_related = any("guide" in scope.casefold() for scope in scope_values) or any(
        "guide" in path for path in path_values
    )
    ai_context_related = any(path.startswith(".ai/") for path in path_values)

    wanted = {"tools/atlas_integrity.py"}
    if guide_related:
        wanted.add("tools/guide_integrity.py")
    if ai_context_related:
        wanted.add("tools/ai_context.py")

    rows = [
        row
        for row in report.get("tools", [])
        if row.get("path") in wanted
    ]
    rows.sort(
        key=lambda row: (
            0 if row.get("path") == "tools/atlas_integrity.py" else 1,
            str(row.get("path")),
        )
    )
    return [
        {
            "path": row.get("path"),
            "invocation": row.get("invocation"),
            "readiness": row.get("readiness"),
            "safe_for_agent": bool(row.get("safe_for_agent")),
            "automation_ready": bool(row.get("automation_ready")),
            "cost_hint": row.get("cost_hint"),
        }
        for row in rows
    ]


def _test_command(modules: Iterable[str]) -> list[str]:
    tests = _unique(str(module) for module in modules)
    if not tests:
        return []
    return ["py", "-3.13", "-m", "unittest", *tests]


def build_plan(
    root: Path,
    paths: Iterable[str],
    impact: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    catalog_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    normalized = atlas_integrity.normalize_paths(paths)
    classification = atlas_integrity.classify_risk(normalized)
    resolved_policy = policy or atlas_integrity.load_policy(root)
    minimum_mode = minimum_integrity_mode(resolved_policy, classification)
    groups = required_groups(resolved_policy, classification)
    report = catalog_report or tooling_catalog(root)
    tools = _preferred_validation_tools(
        report,
        scopes=impact.get("scopes", []),
        paths=normalized,
    )

    unowned = list(impact.get("unowned_paths", []))
    ambiguous = list(impact.get("ambiguous_paths", []))
    ownership_review_required = bool(unowned or ambiguous)
    unsafe_tools = [
        str(row.get("path"))
        for row in tools
        if not row.get("safe_for_agent")
    ]
    non_automated_tools = [
        str(row.get('path')) for row in tools if not row.get('automation_ready')
    ]
    missing_validation_tools = [] if any(
        row.get('path') == 'tools/atlas_integrity.py' for row in tools
    ) else ['tools/atlas_integrity.py']
    automation_safe = not (ownership_review_required or unsafe_tools or non_automated_tools or missing_validation_tools)
    tests = _unique(str(module) for module in impact.get("recommended_tests", []))
    mode_argument = minimum_mode.casefold()

    return {
        "schema_version": _SCHEMA_VERSION,
        "source": "tools.agent_planner",
        "read_only": True,
        "status": "READY" if automation_safe else "REVIEW_REQUIRED",
        "automation_safe": automation_safe,
        "paths": normalized,
        "scopes": list(impact.get("scopes", [])),
        "ownership": {
            "review_required": ownership_review_required,
            "unowned_paths": unowned,
            "ambiguous_paths": ambiguous,
        },
        "risk": classification,
        "required_groups": groups,
        "minimum_integrity_mode": minimum_mode,
        "recommended_tests": tests,
        "test_command": _test_command(tests),
        "validation_command": [
            "py",
            "-3.13",
            "-m",
            "tools.agent",
            "validate",
            mode_argument,
            "--json",
        ],
        "recommended_tools": tools,
        "unsafe_recommended_tools": unsafe_tools,
        "non_automated_recommended_tools": non_automated_tools,
        "missing_validation_tools": missing_validation_tools,
        "rules": list(impact.get("rules", [])),
        "canonical_entries": list(impact.get("canonical_entries", [])),
        "context_entries": list(impact.get("context_entries", [])),
        "working_set": list(impact.get("working_set", [])),
        "policy": {
            "automatic_editing": (
                "allowed_by_plan" if automation_safe else "requires_human_or_agent_review"
            ),
            "validation": "minimum_integrity_mode is derived from Atlas Integrity policy and affected groups",
            "tests": "recommended_tests combines explicit scope tests and AI-context fallbacks",
        },
    }
