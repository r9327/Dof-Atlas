from __future__ import annotations

import re

from app.modules.encyclopedia.services.guide_quest_view_model import (
    first_position_from_quest,
    quest_solution_steps,
    quest_start_info,
)


_COORD_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")


def _position_key(value) -> str:
    match = _COORD_RE.search(str(value or ""))
    if match is None:
        return ""
    return f"{int(match.group(1))},{int(match.group(2))}"


def catalog_route_map_count(guide, quest_provider) -> int:
    """Count optimized route sheets without materializing the full manual UI route.

    This mirrors GuideCatalogManualRuntimeService's segment splitting/merge rule:
    a sheet is created for the quest start, a new sheet starts only when a later
    objective moves to another explicit coordinate, and consecutive sheets on the
    same coordinate are merged across quests.
    """
    raw_keys: list[str] = []
    seen_quests: set[int] = set()

    for step in sorted(
        getattr(guide, "required_steps", ()) or (),
        key=lambda row: int(getattr(row, "order", 0) or 0),
    ):
        if str(getattr(step, "step_type", "")) != "quest":
            continue
        try:
            quest_id = int(getattr(step, "entity_id", None))
        except (TypeError, ValueError):
            continue
        if quest_id in seen_quests:
            continue
        quest = quest_provider.get_quest(quest_id)
        if quest is None:
            continue
        seen_quests.add(quest_id)

        start = quest_start_info(quest)
        start_position = str(
            start.position
            or first_position_from_quest(quest)
            or ""
        ).strip()
        current_position = start_position

        for solution_step in quest_solution_steps(quest):
            for objective in solution_step.objectives:
                text = str(objective.text or "").strip()
                if not text:
                    continue
                objective_position = str(
                    objective.position
                    or current_position
                    or start_position
                    or ""
                ).strip()
                current_key = _position_key(current_position)
                objective_key = _position_key(objective_position)
                if current_key and objective_key and objective_key != current_key:
                    raw_keys.append(current_key)
                    current_position = objective_position

        raw_keys.append(_position_key(current_position))

    merged_count = 0
    previous_key = ""
    for key in raw_keys:
        if merged_count and key and key == previous_key:
            continue
        merged_count += 1
        previous_key = key
    return merged_count


__all__ = ["catalog_route_map_count"]
