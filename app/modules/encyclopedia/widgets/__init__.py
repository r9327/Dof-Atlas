"""Public encyclopedia-widget exports, loaded only when requested.

Python imports a package __init__ before any widgets.<submodule>. Keeping this
facade lightweight avoids importing the entire Qt widget tree for a single
dashboard, guide or quest widget. Attribute access and star imports retain the
same public objects; no application data is hydrated here.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORT_MODULES: dict[str, str] = {
    "AchievementDetailWidget": "achievement_detail_widget",
    "AchievementEntityRow": "achievement_entity_section",
    "AchievementEntitySection": "achievement_entity_section",
    "AchievementObjectiveWidget": "achievement_objective_widget",
    "AchievementRewardWidget": "achievement_reward_widget",
    "AchievementSummaryWidget": "achievement_summary_widget",
    "DetailPanel": "detail_panel",
    "ActivityBadge": "dashboard",
    "ActivitySummary": "dashboard",
    "CollapsedColumnRail": "dashboard",
    "CompactScroll": "dashboard",
    "EmptyState": "dashboard",
    "EncyclopediaPanel": "dashboard",
    "EncyclopediaThreePanelDashboard": "dashboard",
    "FixedColumnSplitter": "dashboard",
    "HideCompletedButton": "dashboard",
    "RequiredItemRow": "dashboard",
    "RequiredItemsWidget": "dashboard",
    "StatusBadge": "dashboard",
    "EntityLinkButton": "entity_link_button",
    "AchievementFilterPanel": "filter_panel",
    "GUIDE_GROUP_ROLE": "guide_card",
    "GUIDE_ID_ROLE": "guide_card",
    "GUIDE_ROLE": "guide_card",
    "GuideCardDelegate": "guide_card",
    "GuideListModel": "guide_card",
    "GuideProgressHeader": "guide_progress_header",
    "GuideSectionWidget": "guide_section_widget",
    "GuideStepWidget": "guide_step_widget",
    "ProgressCard": "progress_card",
    "item_row": "quest_item_row",
    "ACHIEVEMENT_ID_ROLE": "result_list",
    "ACHIEVEMENT_ROLE": "result_list",
    "AchievementListModel": "result_list",
    "ResultList": "result_list",
    "QUEST_ID_ROLE": "quest_widgets",
    "QUEST_ROLE": "quest_widgets",
    "QUEST_STATE_ROLE": "quest_widgets",
    "QuestListModel": "quest_widgets",
    "QuestDetailView": "quest_detail_view",
    "QuestViewContext": "quest_detail_view",
    "RewardCard": "reward_card",
}

__all__ = [
    "ACHIEVEMENT_ID_ROLE",
    "ACHIEVEMENT_ROLE",
    "GUIDE_ID_ROLE",
    "GUIDE_GROUP_ROLE",
    "GUIDE_ROLE",
    "AchievementDetailWidget",
    "AchievementEntityRow",
    "AchievementEntitySection",
    "AchievementFilterPanel",
    "AchievementListModel",
    "AchievementObjectiveWidget",
    "AchievementRewardWidget",
    "AchievementSummaryWidget",
    "DetailPanel",
    "ActivityBadge",
    "ActivitySummary",
    "CompactScroll",
    "CollapsedColumnRail",
    "EmptyState",
    "EncyclopediaPanel",
    "EncyclopediaThreePanelDashboard",
    "EntityLinkButton",
    "FixedColumnSplitter",
    "GuideCardDelegate",
    "GuideListModel",
    "GuideProgressHeader",
    "GuideSectionWidget",
    "GuideStepWidget",
    "HideCompletedButton",
    "ProgressCard",
    "QUEST_ID_ROLE",
    "QUEST_ROLE",
    "QUEST_STATE_ROLE",
    "QuestListModel",
    "QuestDetailView",
    "QuestViewContext",
    "ResultList",
    "RewardCard",
    "RequiredItemRow",
    "RequiredItemsWidget",
    "StatusBadge",
    "item_row",
]


def __getattr__(name: str) -> Any:
    module_name = _LAZY_EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f"{__name__}.{module_name}"), name)
    globals()[name] = value  # Cache the stable public API once resolved.
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
