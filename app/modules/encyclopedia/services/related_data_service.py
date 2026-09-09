from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService
from app.quest_catalog import QuestCatalog


@dataclass(frozen=True, slots=True)
class RelatedEncyclopediaData:
    achievement_provider: AchievementProvider
    guide_provider: GuideProvider
    quest_graph: QuestGraphService


_CACHE_LOCK = RLock()
_CACHED_CATALOG: QuestCatalog | None = None
_CACHED_DATA: RelatedEncyclopediaData | None = None
_BUILD_COUNT = 0


def build_related_encyclopedia_data(catalog: QuestCatalog) -> RelatedEncyclopediaData:
    """Build immutable related providers once for the active catalog/session.

    The first build is safe to run from a worker. Subsequent callers, including
    Guides and Quetes, receive the exact same providers and graph instead of
    reparsing the large local JSON sources. This cache intentionally stays
    in-process: automatic executable deserialization (pickle) is forbidden for
    reconstructible runtime caches by the project guardrails.
    """

    global _BUILD_COUNT, _CACHED_CATALOG, _CACHED_DATA
    with _CACHE_LOCK:
        if _CACHED_CATALOG is catalog and _CACHED_DATA is not None:
            return _CACHED_DATA

        quest_provider = QuestProvider(catalog=catalog)
        achievement_provider = AchievementProvider(quest_provider=quest_provider)
        guide_provider = GuideProvider(
            quest_provider=quest_provider,
            achievement_provider=achievement_provider,
        )
        achievement_provider.load_all()
        guide_provider.load_all()
        data = RelatedEncyclopediaData(
            achievement_provider=achievement_provider,
            guide_provider=guide_provider,
            quest_graph=QuestGraphService(quest_provider, guide_provider, achievement_provider),
        )
        _CACHED_CATALOG = catalog
        _CACHED_DATA = data
        _BUILD_COUNT += 1
        return data


def related_data_build_count() -> int:
    with _CACHE_LOCK:
        return _BUILD_COUNT


__all__ = [
    "RelatedEncyclopediaData",
    "build_related_encyclopedia_data",
    "related_data_build_count",
]
