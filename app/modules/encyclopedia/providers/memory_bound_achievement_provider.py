from __future__ import annotations

from app.modules.encyclopedia.providers.achievement_provider import (
    AchievementProvider as BaseAchievementProvider,
)
from app.quest_source_index import QuestSources


class MemoryBoundAchievementProvider(BaseAchievementProvider):
    """Keep rich Success models hot without retaining monolithic source indexes.

    Source byte-offset maps are reconstructible disk caches. They are useful while
    hydrating the catalogue or one detail, but keeping every map resident after
    that work wastes tens of megabytes. Drop those mappings after each hydration;
    the next detail recreates only the mappings it needs from the already-warm
    gzip index files.
    """

    def _reset_sources(self) -> None:
        try:
            self._sources.close()
        finally:
            self._sources = QuestSources(
                self._sources.cache_root
            )
            self._entries = None

    def _load(self) -> None:
        super()._load()
        self._reset_sources()

    def prepare_detail_sources(self) -> None:
        if self._detail_sources_ready:
            return
        try:
            super().prepare_detail_sources()
        finally:
            # The durable indexes are now on disk. Do not retain all of their
            # offset dictionaries merely to make one future detail lookup fast.
            self._reset_sources()

    def get_detail_by_id(self, achievement_id: int):
        self._ensure_loaded()
        achievement_id = int(achievement_id)
        if self._detail_cache_id == achievement_id and self._detail_cache is not None:
            return self._detail_cache

        # Reward/entity helpers expect the localized entry mapping while one
        # detail is materialized. Load that mapping from the warm offset cache,
        # then release it together with all per-detail source mappings.
        self._entries = self._sources.mapping(
            self.data_dir / "languages" / "fr.json",
            "entries",
            required=True,
        )
        try:
            return super().get_detail_by_id(achievement_id)
        finally:
            self._reset_sources()


__all__ = ["MemoryBoundAchievementProvider"]
