from __future__ import annotations

"""Compact spec-first facade for major Dofus Atlas work.

This module does not create a second planning or validation authority. It composes
existing scope ownership from ``tools.agent`` with the canonical planning and
validation policy from ``tools.agent_planner``. The result is a short, read-only
work spec that agents can generate before a major feature, refactor, migration or
phase-sized lot.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from tools import agent, agent_planner


ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_VERSION = 1

TOOL_SPEC = {
    "schema_version": 1,
    "id": "large_work_spec",
    "role": "large_work_spec_facade",
    "capabilities": ["ai_context", "planning"],
    "modes": ["auto", "structural"],
    "cost_hint": "variable",
    "side_effects": "read_only",
    "structured_output": True,
    "canonical": True,
    "recommended_tests": ["tests.test_work_spec"],
    "target_scopes": ["quality_ci"],
}


class WorkSpecError(ValueError):
    pass


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _scope_seed_paths(root: Path, scopes: Iterable[str]) -> tuple[list[str], list[dict[str, Any]]]:
    paths: list[str] = []
    details: list[dict[str, Any]] = []
    for scope in _unique(scopes):
        detail = agent.inspect_scope(root, scope)
        working_set = [str(path) for path in detail.get("working_set", [])]
        paths.extend(working_set)
        details.append(
            {
                "scope": scope,
                "kind": detail.get("kind"),
                "manifest": detail.get("manifest"),
                "working_set": working_set,
            }
        )
    return _unique(paths), details


def build_spec(
    root: Path,
    objective: str,
    *,
    scopes: Iterable[str] = (),
    paths: Iterable[str] = (),
    structural: bool = False,
    level: str | None = None,
) -> dict[str, Any]:
    """Build a compact, repository-derived spec for a major work item."""
    root = root.resolve()
    objective = objective.strip()
    if not objective:
        raise WorkSpecError("objective must not be empty")

    requested_scopes = _unique(str(scope).strip() for scope in scopes)
    explicit_paths = _unique(str(path).strip() for path in paths)
    scoped_paths, scope_details = _scope_seed_paths(root, requested_scopes)
    seed_paths = _unique([*scoped_paths, *explicit_paths])
    if not seed_paths:
        raise WorkSpecError(
            "at least one scope or path is required; derive it from tools.agent/repository evidence "
            "before asking the user"
        )

    impact = agent.impact_payload(root, seed_paths)
    plan = agent_planner.build_plan(
        root,
        seed_paths,
        impact,
        level=level,
        structural=structural,
    )

    ownership_review = bool(plan.get("ownership", {}).get("review_required"))
    automation_review = not bool(plan.get("automation_safe"))
    review_reasons = _unique(
        [
            *(f"unowned path: {path}" for path in plan.get("ownership", {}).get("unowned_paths", [])),
            *(f"ambiguous path: {path}" for path in plan.get("ownership", {}).get("ambiguous_paths", [])),
            *(f"unsafe recommended tool: {path}" for path in plan.get("unsafe_recommended_tools", [])),
            *(f"non-automated recommended tool: {path}" for path in plan.get("non_automated_recommended_tools", [])),
            *(f"missing validation tool: {path}" for path in plan.get("missing_validation_tools", [])),
        ]
    )

    return {
        "schema_version": _SCHEMA_VERSION,
        "source": "tools.work_spec",
        "read_only": True,
        "status": "REVIEW_REQUIRED" if ownership_review or automation_review else "READY",
        "objective": objective,
        "intent": {
            "structural": bool(structural),
            "requested_level": level or "AUTO",
        },
        "scope_selection": {
            "requested": requested_scopes,
            "resolved": list(impact.get("scopes", [])),
            "details": scope_details,
        },
        "in_scope": {
            "seed_paths": seed_paths,
            "working_set": list(impact.get("working_set", [])),
            "shared_dependencies": list(impact.get("shared_dependencies", [])),
        },
        "contracts_to_preserve": {
            "rules": list(impact.get("rules", [])),
            "canonical_entries": list(impact.get("canonical_entries", [])),
            "context_entries": list(impact.get("context_entries", [])),
        },
        "execution": {
            "work_level": plan.get("level"),
            "integrity_mode": plan.get("integrity_mode"),
            "required_groups": list(plan.get("required_groups", [])),
            "planning_reasons": list(plan.get("planning_reasons", [])),
            "micro_lot_policy": "implement the smallest coherent lots and validate each before expanding scope",
            "scope_policy": "do not add unrelated cleanup or parallel implementations",
        },
        "validation": {
            "recommended_tests": list(plan.get("recommended_tests", [])),
            "test_command": list(plan.get("test_command", [])),
            "validation_command": list(plan.get("validation_command", [])),
            "tests_delegated_to_integrity": bool(plan.get("tests_delegated_to_integrity")),
        },
        "decision_policy": {
            "ask_user_by_default": False,
            "ask_user_only_when": (
                "a material product/behavior choice changes the outcome and cannot be resolved from "
                "the request, repository, current contracts or tests"
            ),
            "repository_review_required": ownership_review or automation_review,
            "repository_review_reasons": review_reasons,
        },
    }


def _render(spec: dict[str, Any]) -> str:
    scopes = ", ".join(spec["scope_selection"]["resolved"]) or "none"
    paths = spec["in_scope"]["seed_paths"]
    tests = spec["validation"]["recommended_tests"]
    lines = [
        "Dofus Atlas — Large-work spec",
        f"Status: {spec['status']}",
        f"Objective: {spec['objective']}",
        f"Scopes: {scopes}",
        f"Structural: {'yes' if spec['intent']['structural'] else 'no'}",
        f"Work level: {spec['execution']['work_level']}",
        f"Integrity mode: {spec['execution']['integrity_mode']}",
        "Seed paths:",
        *(f"- {path}" for path in paths),
        "Validation:",
        *(f"- {test}" for test in tests),
        "User questions: none by default; ask only for unresolved material product choices.",
    ]
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a compact repository-derived spec before a major Dofus Atlas work item."
    )
    parser.add_argument("--objective", required=True, help="Requested outcome for the major work item.")
    parser.add_argument("--scope", action="append", default=[], help="Known Agent scope; repeatable.")
    parser.add_argument("--path", action="append", default=[], help="Known affected path; repeatable.")
    parser.add_argument("--structural", action="store_true", help="Mark refactor/move/delete/architecture work.")
    parser.add_argument("--level", choices=("SOFT", "MEDIUM", "HARD"), help="Optional minimum work depth.")
    parser.add_argument("--json", action="store_true", help="Emit stable machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        spec = build_spec(
            ROOT,
            args.objective,
            scopes=args.scope,
            paths=args.path,
            structural=args.structural,
            level=args.level,
        )
    except (WorkSpecError, agent.AgentConfigError, ValueError) as exc:
        print(f"ERROR: {exc}")
        return 2

    if args.json:
        print(json.dumps(spec, ensure_ascii=False, indent=2))
    else:
        print(_render(spec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
