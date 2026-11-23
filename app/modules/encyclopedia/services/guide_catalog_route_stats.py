from __future__ import annotations

from app.core.map_coordinates import extract_bracketed_position
from app.modules.encyclopedia.services.guide_catalog_step_index import ordered_route_quest_steps

from app.modules.encyclopedia.services.guide_catalog_hints import (
    catalog_route_map_count_hint,
)
from app.modules.encyclopedia.services.guide_quest_view_model import (
    first_position_from_quest,
    quest_solution_steps,
    quest_start_info,
)


def _position_key(value) -> str:
    return extract_bracketed_position(value) or ""


def catalog_route_map_count(guide, quest_provider) -> int:
    """Compute the exact optimized route-sheet count on explicit route work.

    This mirrors GuideCatalogManualRuntimeService's segment splitting/merge rule:
    a sheet is created for the quest start, a new sheet starts only when a later
    objective moves to another explicit coordinate, and consecutive sheets on the
    same coordinate are merged across quests. This function intentionally remains
    detail-heavy and must not be called by the Guide catalogue/home renderer.
    """
    raw_keys: list[str] = []
    seen_quests: set[int] = set()

    for step, quest_id in ordered_route_quest_steps(guide):
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


__all__ = ["catalog_route_map_count", "catalog_route_map_count_hint"]
