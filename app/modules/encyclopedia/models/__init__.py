from __future__ import annotations

from importlib import import_module
from typing import Any


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "Achievement": ("app.modules.encyclopedia.models.achievement", "Achievement"),
    "AchievementCategory": (
        "app.modules.encyclopedia.models.achievement",
        "AchievementCategory",
    ),
    "AchievementObjective": (
        "app.modules.encyclopedia.models.achievement",
        "AchievementObjective",
    ),
    "DofusItem": ("app.modules.encyclopedia.models.dofus_item", "DofusItem"),
    "EntityRef": ("app.modules.encyclopedia.models.entity_ref", "EntityRef"),
    "Guide": ("app.modules.encyclopedia.models.guide", "Guide"),
    "GUIDE_ACTIVITY_TYPES": (
        "app.modules.encyclopedia.models.guide_activity",
        "GUIDE_ACTIVITY_TYPES",
    ),
    "GuideActivity": (
        "app.modules.encyclopedia.models.guide_activity",
        "GuideActivity",
    ),
    "GuideChapter": (
        "app.modules.encyclopedia.models.guide_chapter",
        "GuideChapter",
    ),
    "GuideObjective": (
        "app.modules.encyclopedia.models.guide_objective",
        "GuideObjective",
    ),
    "GuidePart": ("app.modules.encyclopedia.models.guide_part", "GuidePart"),
    "GuideRequiredItem": (
        "app.modules.encyclopedia.models.guide_required_item",
        "GuideRequiredItem",
    ),
    "GuideSection": (
        "app.modules.encyclopedia.models.guide_section",
        "GuideSection",
    ),
    "GuideSeries": (
        "app.modules.encyclopedia.models.guide_series",
        "GuideSeries",
    ),
    "GUIDE_STEP_TYPES": (
        "app.modules.encyclopedia.models.guide_step",
        "GUIDE_STEP_TYPES",
    ),
    "GuideStep": ("app.modules.encyclopedia.models.guide_step", "GuideStep"),
    "ProgressState": (
        "app.modules.encyclopedia.models.progress_state",
        "ProgressState",
    ),
    "Reward": ("app.modules.encyclopedia.models.reward", "Reward"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "GUIDE_STEP_TYPES",
    "GUIDE_ACTIVITY_TYPES",
    "Achievement",
    "AchievementCategory",
    "AchievementObjective",
    "DofusItem",
    "EntityRef",
    "Guide",
    "GuideActivity",
    "GuideChapter",
    "GuideObjective",
    "GuidePart",
    "GuideRequiredItem",
    "GuideSection",
    "GuideSeries",
    "GuideStep",
    "ProgressState",
    "Reward",
]
