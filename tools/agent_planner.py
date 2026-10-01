from __future__ import annotations

"""Read-only planning engine for AI-assisted repository changes.

This module deliberately does not own scope matching, risk classification, tool
inventory, or validation execution. It composes the canonical Agent impact data,
Atlas Integrity policy/classification, and the AI tool catalog into one stable
plan that callers can inspect before editing or validating the repository.
"""

import time
from pathlib import Path
from typing import Any, Iterable

from tools import atlas_integrity
from tools.tool_catalog import catalog as tooling_catalog, select_tools


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
    minimum_mode: str,
) -> list[dict[str, Any]]:
    """Select canonical facades from catalog metadata, never path-name hints."""
    scope_values = set(scopes)
    path_values = set(paths)
    authority = next(
        (row for row in report.get("tools", [])
         if row.get("path") == "tools/atlas_integrity.py"),
        None,
    )
    selected = [authority] if authority is not None else []
    for row in select_tools(report, capability="validation")["tools"]:
        spec = row.get("tool_spec") or {}
        role = str(row.get("preferred_role") or spec.get("role") or "")
        canonical = bool(row.get("preferred_for_agent") or spec.get("canonical"))
        if row.get("path") == "tools/atlas_integrity.py" or not canonical:
            continue
        if role == "repository_validation_orchestrator" or not role.endswith("validation_orchestrator"):
            continue
        targets = set(row.get("target_scopes") or spec.get("target_scopes") or [])
        if targets.intersection(scope_values) or row.get("path") in path_values:
            selected.append(row)

    output = []
    for row in selected:
        path = str(row["path"])
        is_authority = path == "tools/atlas_integrity.py"
        modes = [str(mode).casefold() for mode in row.get("modes", [])]
        if is_authority:
            mode = minimum_mode.casefold()
            if modes and mode not in modes:
                mode = None
        elif minimum_mode in {"FULL", "DEEP"} and "full" in modes:
            mode = "full"
        else:
            mode = "fast" if "fast" in modes else None
        matches = sorted(set(row.get("target_scopes") or []).intersection(scope_values))
        reason = (
            "Canonical Atlas Integrity authority; mode derived from its policy."
            if is_authority else
            "Declared target scope matches: " + ", ".join(matches)
            if matches else
            "The specialized facade itself is being changed."
        )
        command = (
            ["py", "-3.13", "-m", path[:-3].replace("/", "."), mode]
            + (["--json"] if row.get("json_cli_flag") else [])
            if mode else []
        )
        output.append({
            "path": path, "invocation": row.get("invocation"),
            "readiness": row.get("readiness"),
            "safe_for_agent": bool(row.get("safe_for_agent")),
            "automation_ready": bool(row.get("automation_ready")) and mode is not None,
            "cost_hint": row.get("cost_hint"), "side_effects": row.get("side_effects"),
            "capabilities": list(row.get("capabilities", [])),
            "mode": mode, "command": command, "reason": reason,
            "declared_tests": list(row.get("declared_tests", [])),
            "target_scopes": matches,
        })
    return output


def _test_command(modules: Iterable[str]) -> list[str]:
    tests = _unique(str(module) for module in modules)
    if not tests:
        return []
    return ["py", "-3.13", "-m", "unittest", *tests]


def choose_work_depth(
    paths: list[str], impact: dict[str, Any], classification: dict[str, Any],
    minimum_mode: str, *, requested: str | None = None, structural: bool = False,
) -> dict[str, Any]:
    """Depth is a routing choice; the canonical integrity floor is never lowered."""
    order = ("SOFT", "MEDIUM", "HARD")
    if requested is not None:
        requested = requested.upper()
        if requested not in order:
            raise ValueError("work level must be SOFT, MEDIUM or HARD")
    floor = "HARD" if minimum_mode in {"FULL", "DEEP"} else "MEDIUM" if minimum_mode == "CRITICAL" else "SOFT"
    reasons = [f"Atlas Integrity policy requires at least {minimum_mode}."]
    if structural or classification.get("risk") == "CRITICAL":
        floor = "HARD"
        reasons.append("Structural work or critical risk requires comprehensive validation.")
    elif len(paths) > 1 or len(impact.get("scopes", [])) > 1:
        if floor == "SOFT":
            floor = "MEDIUM"
        reasons.append("Multiple changed files or affected scopes require wider targeted checks.")
    selected = max((floor, requested or "SOFT"), key=order.index)
    mode_floor = {"SOFT": "FAST", "MEDIUM": "CRITICAL", "HARD": "FULL"}[selected]
    mode = max((minimum_mode, mode_floor), key=_MODE_ORDER.index)
    start = requested or "SOFT"
    escalations = []
    if order.index(selected) > order.index(start):
        escalations.append({"from": start, "to": selected, "reasons": reasons})
    return {"requested": requested or "AUTO", "level": selected,
            "integrity_mode": mode, "reasons": reasons,
            "escalations": escalations, "graph_depth": 2 if selected == "HARD" else 1,
            "performance": "Only canonical policy-required groups; no extra runtime benchmark."}


def _execution_tests(
    root: Path, paths: list[str], tests: list[str], report: dict[str, Any], level: str,
) -> list[str]:
    if level == "HARD":
        return []  # FULL_SUITE stays owned and executed by Atlas Integrity.
    if level != "SOFT":
        return tests
    direct = []
    for row in report.get("tools", []):
        if row.get("path") in paths:
            direct.extend(row.get("declared_tests", []))
            direct.extend(
                path[:-3].replace("/", ".")
                for path in row.get("targeted_tests", [])
                if path.startswith("tests/test_") and path.endswith(".py")
                and (root / path).is_file()
            )
    direct.extend(path[:-3].replace("/", ".") for path in paths
                  if path.startswith("tests/test_") and path.endswith(".py")
                  and (root / path).is_file())
    return _unique(direct) or tests


def _planning_catalog(
    root: Path, *, cache_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the current tool catalog and optionally expose cache evidence.

    The public return shape stays the catalog itself so existing callers/tests keep
    their contract. Cache metadata is observational only and never authorizes a
    validation result to be reused.
    """
    from tools.atlas_doctor_lib.core import cache_matches_git, git_state, load_json, write_json

    started = time.perf_counter()
    try:
        state = git_state(root)
    except RuntimeError:
        report = tooling_catalog(root)
        if cache_info is not None:
            cache_info.update({
                "status": "BYPASS",
                "reason": "Git state unavailable; catalog discovered directly.",
                "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
            })
        return report

    cached = load_json(root, "planner_catalog")
    if (cached and cached.get("schema_version") == 1
            and cached.get("kind") == "planner_catalog"
            and cache_matches_git(cached, state)):
        report = cached.get("catalog")
        if isinstance(report, dict) and report.get("schema_version") == 1:
            if cache_info is not None:
                cache_info.update({
                    "status": "HIT",
                    "head": state.get("head"),
                    "dirty_digest": state.get("dirty_digest", ""),
                    "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
                })
            return report

    report = tooling_catalog(root)
    write_json(root, "planner_catalog", {
        "schema_version": 1, "kind": "planner_catalog", "git": state, "catalog": report,
    })
    if cache_info is not None:
        cache_info.update({
            "status": "MISS",
            "head": state.get("head"),
            "dirty_digest": state.get("dirty_digest", ""),
            "duration_ms": round((time.perf_counter() - started) * 1000.0, 3),
        })
    return report


def build_plan(
    root: Path,
    paths: Iterable[str],
    impact: dict[str, Any],
    *,
    policy: dict[str, Any] | None = None,
    catalog_report: dict[str, Any] | None = None,
    level: str | None = None,
    structural: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    normalized = atlas_integrity.normalize_paths(paths)
    classification = atlas_integrity.classify_risk([*normalized, *impact.get("risk_paths", [])])
    resolved_policy = policy or atlas_integrity.load_policy(root)
    minimum_mode = minimum_integrity_mode(resolved_policy, classification)
    depth = choose_work_depth(normalized, impact, classification, minimum_mode, requested=level, structural=structural)
    groups = required_groups(resolved_policy, classification)
    planner_cache: dict[str, Any] = {}
    if catalog_report is not None:
        report = catalog_report
        planner_cache = {"status": "PROVIDED", "duration_ms": 0.0}
    else:
        report = _planning_catalog(root, cache_info=planner_cache)
        if not planner_cache:
            planner_cache = {"status": "UNKNOWN"}
    tools = _preferred_validation_tools(
        report,
        scopes=impact.get("scopes", []),
        paths=normalized,
        minimum_mode=depth["integrity_mode"],
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
    tests = _unique([
        *(str(module) for module in impact.get("recommended_tests", [])),
        *(str(module) for row in tools for module in row.get("declared_tests", [])),
    ])
    execution_tests = _execution_tests(root, normalized, tests, report, depth["level"])
    mode_argument = depth["integrity_mode"].casefold()

    return {
        "schema_version": _SCHEMA_VERSION,
        "source": "tools.agent_planner",
        "selection_source": "tools.tool_catalog.select_tools",
        "read_only": True,
        "status": "READY" if automation_safe else "REVIEW_REQUIRED",
        "automation_safe": automation_safe,
        "level": depth["level"],
        "depth": depth,
        "integrity_mode": depth["integrity_mode"],
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
        "execution_tests": execution_tests,
        "tests_delegated_to_integrity": depth["level"] == "HARD",
        "test_command": _test_command(execution_tests),
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
        "planner_cache": planner_cache,
        "planning_reasons": [
            "Scope and ownership come from the existing Agent map.",
            "Risk and minimum mode come from Atlas Integrity classification/policy.",
            *(row["reason"] for row in tools),
        ],
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
