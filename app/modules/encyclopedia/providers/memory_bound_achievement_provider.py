from __future__ import annotations

from typing import Any

from app.modules.encyclopedia.providers.achievement_provider import (
    AchievementProvider as BaseAchievementProvider,
)
from app.quest_source_index import QuestSources


class MemoryBoundAchievementProvider(BaseAchievementProvider):
    """Rich Success runtime with reconstructible bulk data kept off the heap."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._catalog_loading = False
        super().__init__(*args, **kwargs)

    def _reset_sources(self) -> None:
        cache_root = self._sources.cache_root
        try:
            self._sources.close()
        finally:
            self._sources = QuestSources(cache_root)
            self._entries = None

    def _image_for_icon(self, icon_id: int | None, folders: tuple[str, ...]) -> str:
        # The Success catalogue UI never renders one decoded icon per Success.
        # Building a recursive global image-path dictionary here used to allocate
        # a large amount of memory before any detail was opened. Keep catalogue
        # models metadata-only; documentary reward images remain detail-lazy.
        if self._catalog_loading:
            return ""
        return super()._image_for_icon(icon_id, folders)

    def _trim_catalogue_payload(self) -> None:
        # The full Doduda row was retained once per Success although the runtime
        # only needs the source category id later for stable sorting. Preserve
        # that one value in place so every existing list/map keeps the same
        # Achievement object without duplicating replacements.
        for achievement in self._achievements:
            raw = achievement.raw if isinstance(achievement.raw, dict) else {}
            source_category_id = raw.get("categoryId")
            object.__setattr__(
                achievement,
                "raw",
                ({"categoryId": source_category_id} if source_category_id is not None else {}),
            )

        # These maps duplicate relations already stored on each Achievement.
        # Public accessors below read the canonical object instead.
        self._linked_quests = {}
        self._linked_monsters = {}
        self._linked_dungeons = {}
        self._linked_achievements = {}
        self._image_indexes.clear()

    def _load(self) -> None:
        self._catalog_loading = True
        try:
            super()._load()
        finally:
            self._catalog_loading = False
        self._trim_catalogue_payload()
        self._reset_sources()

    def prepare_detail_sources(self) -> None:
        if self._detail_sources_ready:
            return
        try:
            super().prepare_detail_sources()
        finally:
            # Durable byte-offset indexes stay on disk. The dictionaries that
            # describe them are reconstructible and therefore not long-lived.
            self._reset_sources()

    def get_detail_by_id(self, achievement_id: int):
        self._ensure_loaded()
        achievement_id = int(achievement_id)
        if self._detail_cache_id == achievement_id and self._detail_cache is not None:
            return self._detail_cache

        self._entries = self._sources.mapping(
            self.data_dir / "languages" / "fr.json",
            "entries",
            required=True,
        )
        try:
            return super().get_detail_by_id(achievement_id)
        finally:
            self._reset_sources()

    def get_linked_quests(self, achievement_id: int):
        achievement = self.get_by_id(int(achievement_id))
        return list(achievement.linked_quests) if achievement is not None else []

    def get_linked_monsters(self, achievement_id: int):
        achievement = self.get_by_id(int(achievement_id))
        return list(achievement.linked_monsters) if achievement is not None else []

    def get_linked_dungeons(self, achievement_id: int):
        achievement = self.get_by_id(int(achievement_id))
        return list(achievement.linked_dungeons) if achievement is not None else []

    def get_linked_achievements(self, achievement_id: int):
        achievement = self.get_by_id(int(achievement_id))
        return list(achievement.linked_achievements) if achievement is not None else []


__all__ = ["MemoryBoundAchievementProvider"]
