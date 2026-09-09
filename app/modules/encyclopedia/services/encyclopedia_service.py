from __future__ import annotations

from app.modules.encyclopedia.providers.achievement_provider import AchievementProvider
from app.modules.encyclopedia.providers.guide_provider import GuideProvider
from app.modules.encyclopedia.providers.indexed_guide_provider import IndexedGuideProvider
from app.modules.encyclopedia.providers.quest_provider import QuestProvider


class EncyclopediaService:
    def __init__(
        self,
        quest_provider: QuestProvider | None = None,
        achievement_provider: AchievementProvider | None = None,
        guide_provider: GuideProvider | None = None,
    ) -> None:
        self.quest_provider = quest_provider or QuestProvider()
        self.achievement_provider = achievement_provider or AchievementProvider(quest_provider=self.quest_provider)
        self.guide_provider = guide_provider or IndexedGuideProvider(
            quest_provider=self.quest_provider,
            achievement_provider=self.achievement_provider,
        )
