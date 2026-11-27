"""Pure source step ordering shared by catalog route count and renderer.

Provider resolution is shared, but only successfully resolved quests become
seen; failed lookups can be retried by later source steps.
"""
from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from app.core.map_coordinates import extract_bracketed_position
from app.core.numbers import optional_int
from app.core.text import normalize_key


def _route_position_key_uncached(text: str) -> str:
    return extract_bracketed_position(text) or normalize_key(text)


@lru_cache(maxsize=4096)
def _route_position_key_short(text: str) -> str:
    return _route_position_key_uncached(text)


def route_position_key(value: object) -> str:
    """Use the same bounded position cache for route sheets and their count."""
    text = " ".join(str(value or "").split()).strip()
    return _route_position_key_short(text) if len(text) <= 160 else _route_position_key_uncached(text)


def route_positions_merge(previous: str, current: str) -> bool:
    """Unknown positions never merge, even with another unknown position."""
    return bool(current and current == previous)


def route_positions_split(previous: str, current: str) -> bool:
    """Only a known changed position starts another route sheet."""
    return bool(previous and current and previous != current)


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
