"""Pure source step ordering shared by catalog route count and renderer.

Provider resolution is shared, but only successfully resolved quests become
seen; failed lookups can be retried by later source steps.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.core.numbers import optional_int


def ordered_route_quest_steps(guide: object) -> Iterator[tuple[Any, int]]:
    for step in sorted(
        getattr(guide, "required_steps", ()) or (),
        key=lambda row: int(getattr(row, "order", 0) or 0),
    ):
        if str(getattr(step, "step_type", "")) != "quest":
            continue
        quest_id = optional_int(getattr(step, "entity_id", None))
        if quest_id is not None:
            yield step, quest_id


def resolved_route_quests(guide: object, provider: Any) -> Iterator[tuple[Any, Any]]:
    """Resolve each existing Quest at most once, in the authored source order."""
    seen_quests: set[int] = set()
    for step, quest_id in ordered_route_quest_steps(guide):
        if quest_id in seen_quests:
            continue
        quest = provider.get_quest(quest_id)
        if quest is None:
            continue
        seen_quests.add(quest_id)
        yield step, quest
