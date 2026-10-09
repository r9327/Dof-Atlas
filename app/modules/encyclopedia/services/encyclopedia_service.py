from __future__ import annotations

from typing import TYPE_CHECKING

from app.modules.encyclopedia.providers import AchievementProvider, QuestProvider

if TYPE_CHECKING:
    from app.modules.encyclopedia.providers.guide_provider import GuideProvider


class EncyclopediaService:
    """Own lazy provider boundaries for the Encyclopedia runtime."""

    def __init__(
        self,
        quest_provider: QuestProvider | None = None,
        achievement_provider: AchievementProvider | None = None,
        guide_provider: "GuideProvider | None" = None,
    ) -> None:
        self.quest_provider = quest_provider or QuestProvider()
        self._achievement_provider = achievement_provider
        self._guide_provider = guide_provider

    @property
    def achievement_provider(self):
        provider = self._achievement_provider
        if provider is None:
            provider = AchievementProvider(quest_provider=self.quest_provider)
            self._achievement_provider = provider
        return provider

    @achievement_provider.setter
    def achievement_provider(self, provider) -> None:
        self._achievement_provider = provider

    @property
    def guide_provider(self):
        provider = self._guide_provider
        if provider is None:
            from app.modules.encyclopedia.providers.memory_bound_guide_provider import (
                MemoryBoundGuideProvider,
            )

            provider = MemoryBoundGuideProvider(
                quest_provider=self.quest_provider,
                achievement_provider=self.achievement_provider,
            )
            self._guide_provider = provider
        return provider

    @guide_provider.setter
    def guide_provider(self, provider) -> None:
        self._guide_provider = provider

    def peek_achievement_provider(self):
        return self._achievement_provider

    def peek_guide_provider(self):
        return self._guide_provider
