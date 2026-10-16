from __future__ import annotations

"""Structured Guide Integrity adapter for Phase 7E contracts.

This is the canonical boundary used by runtime/UI payloads and validation.  It
accepts either GuideAction values or dictionaries carrying the same semantic
schema, so validators do not need to inspect rendered French text.
"""

from collections.abc import Iterable, Mapping
from dataclasses import asdict
from typing import Any

from tools.guide_action_contract import group_consecutive_talks, validate_actions
from tools.guide_action_model import GuideAction
from tools.guide_action_normalizer import normalize_action


def _actions(values: Iterable[GuideAction | Mapping[str, Any]]) -> list[GuideAction]:
    result: list[GuideAction] = []
    for value in values:
        result.append(value if isinstance(value, GuideAction) else normalize_action(value))
    return result


def validate_structured_actions(
    actions: Iterable[GuideAction | Mapping[str, Any]],
) -> dict[str, object]:
    rows = _actions(actions)
    violations = validate_actions(rows)
    talk_groups = [
        group for group in group_consecutive_talks(rows)
        if len(group) > 1
    ]
    return {
        "schema_version": 1,
        "engine": "guide_integrity_structured",
        "action_count": len(rows),
        "grouped_talk_count": len(talk_groups),
        "hard_error_count": len(violations),
        "hard_errors": [asdict(row) for row in violations],
    }


def validate_runtime_lines(lines: Iterable[Mapping[str, Any]]) -> dict[str, object]:
    """Validate structured actions attached to rendered runtime lines.

    Lines without ``guide_actions`` are intentionally ignored during migration;
    once a runtime surface emits structured actions, its semantic contracts are
    HARD and no regex downgrade is involved.
    """
    actions: list[GuideAction | Mapping[str, Any]] = []
    structured_line_count = 0
    for line in lines:
        raw = line.get("guide_actions")
        if not isinstance(raw, list):
            continue
        structured_line_count += 1
        actions.extend(row for row in raw if isinstance(row, (GuideAction, Mapping)))
    report = validate_structured_actions(actions)
    report["structured_line_count"] = structured_line_count
    return report
