"""Pure source step ordering shared by catalog route count and renderer.

Keep provider lookup, absent quests and duplicate filtering with callers:
only successfully resolved quests become seen.
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
