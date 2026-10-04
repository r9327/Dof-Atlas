from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR, ROOT_DIR
from app.modules.encyclopedia.providers import QuestProvider
from app.modules.encyclopedia.services.quest_graph_service import QuestGraphService
from app.quest_catalog import QuestCatalog
from app.quest_source_index import QuestSources


class _EmptyGuideProvider:
    """Progress-preload adapter that deliberately keeps full Guides cold."""

    __slots__ = ()

    @staticmethod
    def load_all() -> list[Any]:
        return []


_EMPTY_GUIDE_PROVIDER = _EmptyGuideProvider()


@dataclass(frozen=True, slots=True)
class RelatedEncyclopediaData:
    achievement_provider: Any | None
    guide_provider: Any
    quest_graph: QuestGraphService
    warmed_source_count: int = 0
    warmed_guide_file_count: int = 0


_CACHE_LOCK = RLock()
_CACHED_CATALOG: QuestCatalog | None = None
_CACHED_DATA: RelatedEncyclopediaData | None = None
_BUILD_COUNT = 0


def _warm_achievement_source_indexes() -> int:
    """Prepare reconstructible byte-offset indexes without retaining rich Success objects."""

    sources = QuestSources(
        ROOT_DIR / ".cache" / "dofus_atlas" / "achievement_sources_v1"
    )
    mappings = (
        sources.mapping(
            RAW_QUEST_DATA_DIR / "languages" / "fr.json",
            "entries",
            required=True,
        ),
        sources.rows(RAW_QUEST_DATA_DIR / "achievements.json"),
        sources.rows(RAW_QUEST_DATA_DIR / "achievement_categories.json"),
        sources.rows(RAW_QUEST_DATA_DIR / "achievement_objectives.json"),
        sources.rows(RAW_QUEST_DATA_DIR / "quests.json"),
        sources.rows(RAW_QUEST_DATA_DIR / "monsters.json"),
        sources.rows(RAW_QUEST_DATA_DIR / "dungeons.json"),
    )
    try:
        for mapping in mappings:
            len(mapping)
        return len(mappings)
    finally:
        sources.close()


def _warm_guide_files() -> int:
    """Warm small Guide JSON files in the filesystem cache, then release their bytes."""

    guides_dir = DATA_DIR / "encyclopedia" / "guides"
    if not guides_dir.is_dir():
        return 0
    count = 0
    for path in sorted(guides_dir.glob("*.json")):
        try:
            path.read_bytes()
        except OSError:
            continue
        count += 1
    return count


def build_related_encyclopedia_data(catalog: QuestCatalog) -> RelatedEncyclopediaData:
    """Warm reusable related data while keeping the heavy providers click-lazy.

    Phase 8 intentionally does not keep the fully materialized Success and Guide
    providers alive in the background: that made first access very fast but kept
    roughly another hundred megabytes resident after preload. The worker instead
    prepares the durable byte-offset indexes and filesystem cache that make the
    first real provider build cheaper, plus the compact quest dependency graph.
    """

    global _BUILD_COUNT, _CACHED_CATALOG, _CACHED_DATA
    with _CACHE_LOCK:
        if _CACHED_CATALOG is catalog and _CACHED_DATA is not None:
            return _CACHED_DATA

        quest_provider = QuestProvider(catalog=catalog)
        warmed_source_count = _warm_achievement_source_indexes()
        warmed_guide_file_count = _warm_guide_files()
        data = RelatedEncyclopediaData(
            achievement_provider=None,
            guide_provider=_EMPTY_GUIDE_PROVIDER,
            quest_graph=QuestGraphService(quest_provider),
            warmed_source_count=warmed_source_count,
            warmed_guide_file_count=warmed_guide_file_count,
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
