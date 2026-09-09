from __future__ import annotations

from app.modules.encyclopedia.models.reward import Reward
from app.modules.encyclopedia.widgets.reward_card import RewardCard


class AchievementRewardWidget(RewardCard):
    def __init__(self, reward: Reward, parent=None) -> None:
        super().__init__(reward, parent)
        self.setObjectName("AchievementRewardWidget")
