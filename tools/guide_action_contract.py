from __future__ import annotations

"""Deterministic Phase 7E contracts over structured Guide actions.

These checks intentionally avoid parsing rendered player text. Runtime/UI can
progressively emit GuideAction values and Guide Integrity can validate the same
semantics.
"""

from dataclasses import dataclass
from typing import Iterable

from tools.guide_action_model import GuideAction, GuideActionType


@dataclass(frozen=True, slots=True)
class GuideActionViolation:
    code: str
    index: int
    detail: str


def validate_actions(actions: Iterable[GuideAction]) -> list[GuideActionViolation]:
    rows = list(actions)
    violations: list[GuideActionViolation] = []
    preparation_targets: set[tuple[str, object]] = set()

    for index, action in enumerate(rows):
        target = action.canonical_target
        if action.requires_preparation:
            preparation_targets.add(target)
        if action.action_type is GuideActionType.DROP and not action.purchase_alternative:
            violations.append(GuideActionViolation("drop_without_purchase_alternative", index, str(target)))
        if action.requires_preparation and action.natural_acquisition_step:
            violations.append(GuideActionViolation("premature_preparation", index, str(target)))

    for index, action in enumerate(rows):
        if not action.requires_preparation and action.canonical_target in preparation_targets:
            violations.append(GuideActionViolation("preparation_action_duplicate", index, str(action.canonical_target)))

    return violations


def group_consecutive_talks(actions: Iterable[GuideAction]) -> list[list[GuideAction]]:
    """Group adjacent interactions with the same canonical actor/map."""
    groups: list[list[GuideAction]] = []
    for action in actions:
        if action.action_type is not GuideActionType.TALK:
            groups.append([action])
            continue
        if groups:
            previous = groups[-1][-1]
            if (
                previous.action_type is GuideActionType.TALK
                and previous.actor_id == action.actor_id
                and previous.map_id == action.map_id
            ):
                groups[-1].append(action)
                continue
        groups.append([action])
    return groups
