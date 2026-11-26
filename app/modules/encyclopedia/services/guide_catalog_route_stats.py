from __future__ import annotations

from app.modules.encyclopedia.services.guide_catalog_step_index import (
    resolved_route_quests, route_position_key, route_positions_merge, route_positions_split,
)

from app.modules.encyclopedia.services.guide_catalog_hints import (
    catalog_route_map_count_hint,
)
from app.modules.encyclopedia.services.guide_quest_view_model import (
    quest_solution_steps,
    quest_start_info,
)


def _position_key(value) -> str:
    return route_position_key(value)


def catalog_route_map_count(guide, quest_provider) -> int:
    """Compute the exact optimized route-sheet count on explicit route work.

    This mirrors GuideCatalogManualRuntimeService's segment splitting/merge rule:
    a sheet is created for the quest start, a new sheet starts only when a later
    objective moves to another known position, and consecutive sheets on the
    same position are merged across quests. This function intentionally remains
    detail-heavy and must not be called by the Guide catalogue/home renderer.
    """
    merged_count = 0
    previous_key = ""

    def accept(key: str) -> None:
        nonlocal merged_count, previous_key
        if merged_count and route_positions_merge(previous_key, key):
            return
        merged_count += 1
        previous_key = key

    for _step, quest in resolved_route_quests(guide, quest_provider):
        start = quest_start_info(quest, include_map_images=False)
        start_position = start.declared_launch_position
        current_position = start_position
        current_key = _position_key(current_position)

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
                objective_key = _position_key(objective_position)
                if route_positions_split(current_key, objective_key):
                    accept(current_key)
                    current_position = objective_position
                    current_key = objective_key

        accept(current_key)
    return merged_count


__all__ = ["catalog_route_map_count", "catalog_route_map_count_hint"]
