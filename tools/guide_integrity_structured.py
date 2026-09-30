from __future__ import annotations

"""Structured Guide Integrity adapter for Phase 7E contracts."""

from dataclasses import asdict
from typing import Iterable

from tools.guide_action_contract import validate_actions
from tools.guide_action_model import GuideAction


def validate_structured_actions(actions: Iterable[GuideAction]) -> dict[str, object]:
    violations = validate_actions(actions)
    return {
        "engine": "guide_integrity_structured",
        "hard_error_count": len(violations),
        "hard_errors": [asdict(row) for row in violations],
    }
