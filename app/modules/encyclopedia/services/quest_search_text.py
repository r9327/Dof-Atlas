"""Qt-free source fields shared by eager and lazy Quest search views.

The graph, cache and deferred indexing remain owned by the caller.
"""
from __future__ import annotations

from typing import Iterable, TYPE_CHECKING

from app.core.text import normalize_key

if TYPE_CHECKING:
    from app.quest_catalog import QuestRecord


def quest_repeatability_text(quest: QuestRecord) -> str:
    """Source text shared by repeatability classification and graph lookup."""
    return " ".join([quest.category, quest.start_criterion, *quest.info])


def quest_search_fields(quest: QuestRecord, achievement_names: Iterable[str]) -> tuple[str, str, str, str, str]:
    """Return raw search fields in the original order; callers own normalization."""
    return (
        quest.search_text,
        " ".join(step.name for step in quest.steps),
        " ".join(objective.text for step in quest.steps for objective in step.objectives),
        " ".join(reward.name for reward in quest.rewards),
        " ".join(achievement_names),
    )


def quest_document_text(quest: QuestRecord) -> str:
    """Persist only documentary fields; related entities are live context."""
    return normalize_key(" ".join(quest_search_fields(quest, ())[:4]))


def quest_context_search_text(
    quest: QuestRecord, achievement_names: Iterable[str], guide_titles: Iterable[str],
    *, document: str | None = None,
) -> str:
    """Merge the same live relations into eager and prebuilt documents."""
    base = quest_document_text(quest) if document is None else document
    return normalize_key(" ".join((base, " ".join(guide_titles), " ".join(achievement_names))))
