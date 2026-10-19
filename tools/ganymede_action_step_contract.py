"""Fail-closed structural checks for Ganymède action hints.

These checks only confirm well-formed *source candidate* metadata. They never
establish Doduda objective truth or auto-completion eligibility.
"""
from __future__ import annotations

from typing import Any

_BOOLEAN_FLAGS = frozenset({
    "optional", "can_obtain_on_route", "group_fight", "cumulative_target",
    "stay_at_end", "capture_required", "daily_reset", "ally_must_survive",
    "stop_before_boss", "quest_update_even_if_lost", "optional_branch",
})
_POSITIVE_COUNTS = frozenset({
    "quantity_per_character", "repeat_count", "participants_min",
    "quantity",
})
_TEXT_IDENTIFIERS = frozenset({
    "conditional", "alternative_group", "counter_scope", "quantity_scope",
    "relation", "group_mode", "mechanic",
})


def validate_step_action(
    action: dict[str, Any], *, step_number: int, source_step_count: int,
    observed_monster_ids: list[int] | None = None,
) -> list[str]:
    """Return review errors, preserving the candidate as non-playable.

    An object needed later may be collected in a previous step, never after
    its stated deadline. Back-references must be strictly earlier and present.
    The source step count is mandatory to prevent dangling external links.
    """
    errors: list[str] = []
    if (type(step_number) is not int or type(source_step_count) is not int
            or not 1 <= step_number <= source_step_count):
        return ["invalid source stage bounds"]

    def in_range(field: str, lower: int, upper: int) -> None:
        if field not in action:
            return
        value = action[field]
        if type(value) is not int or not lower <= value <= upper:
            errors.append(f"invalid {field}: expected step {lower}..{upper}")

    in_range("needed_at_source_step", step_number, source_step_count)
    in_range("collection_window_end", step_number, source_step_count)
    in_range("references_previous_stage", 1, step_number - 1)

    for field in _POSITIVE_COUNTS:
        if field in action and (
            type(action[field]) is not int or action[field] < 1
        ):
            errors.append(f"invalid positive count: {field}")
    if "cooldown_if_failed_seconds" in action and (
        type(action["cooldown_if_failed_seconds"]) is not int
        or action["cooldown_if_failed_seconds"] <= 0
    ):
        errors.append("invalid cooldown_if_failed_seconds")
    for field in _BOOLEAN_FLAGS:
        if field in action and type(action[field]) is not bool:
            errors.append(f"invalid boolean flag: {field}")
    for field in _TEXT_IDENTIFIERS:
        if field in action and (
            not isinstance(action[field], str) or not action[field].strip()
        ):
            errors.append(f"invalid conditional/group field: {field}")
    if "alternative_monster_ids" in action:
        ids = action["alternative_monster_ids"]
        if (not isinstance(ids, list) or not ids
                or any(type(value) is not int or value <= 0 for value in ids)
                or len(ids) != len(set(ids))
                or observed_monster_ids is None
                or any(value not in observed_monster_ids for value in ids)):
            errors.append("unobserved alternative_monster_ids")
    return errors


__all__ = ["validate_step_action"]
