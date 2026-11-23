"""Qt-free source fields shared by eager and lazy Quest search views.

The graph, cache and deferred indexing remain owned by the caller.
"""
from __future__ import annotations

from typing import Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from app.quest_catalog import QuestRecord


def quest_search_fields(quest: QuestRecord, achievement_names: Iterable[str]) -> tuple[str, str, str, str, str]:
    """Return raw search fields in the original order; callers own normalization."""
    return (
        quest.search_text,
        " ".join(step.name for step in quest.steps),
        " ".join(objective.text for step in quest.steps for objective in step.objectives),
        " ".join(reward.name for reward in quest.rewards),
        " ".join(achievement_names),
    )
