from __future__ import annotations

from importlib import import_module
from typing import Any

from app.modules.encyclopedia.services.guide_progress_service import (
    GUIDE_PROGRESS_FILE,
    GuideProgressService,
)
from app.modules.encyclopedia.services.guide_progress_calculator import (
    GuideProgressCalculator,
    ProgressCount,
)
from app.modules.encyclopedia.services.serialized_achievement_progress_service import (
    ACHIEVEMENT_PROGRESS_FILE,
    AchievementProgressService,
)
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService


_REAL_QUEST_GRAPH_SERVICE: type | None = None


def _load_quest_graph_service_class() -> type:
    global _REAL_QUEST_GRAPH_SERVICE
    real = _REAL_QUEST_GRAPH_SERVICE
    if real is not None:
        return real
    from app.modules.encyclopedia.services.quest_graph_service import (
        QuestGraphService as RealQuestGraphService,
    )

    _REAL_QUEST_GRAPH_SERVICE = RealQuestGraphService
    return RealQuestGraphService


class _LazyQuestGraphServiceMeta(type):
    def __call__(cls, *args: Any, **kwargs: Any):
        return _load_quest_graph_service_class()(*args, **kwargs)

    def __instancecheck__(cls, instance: object) -> bool:
        return isinstance(instance, _load_quest_graph_service_class())

    def __subclasscheck__(cls, subclass: type) -> bool:
        return issubclass(subclass, _load_quest_graph_service_class())


class QuestGraphService(metaclass=_LazyQuestGraphServiceMeta):
    """Lazy public facade for the quest graph service.

    main.py imports this symbol before QApplication only for type checks. The
    concrete graph module also imports AchievementProvider helpers, so loading it
    here would pull the Successes model stack into startup for no user-visible
    benefit.
    """


_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "EncyclopediaService": (
        "app.modules.encyclopedia.services.encyclopedia_service",
        "EncyclopediaService",
    ),
    "LinkService": (
        "app.modules.encyclopedia.services.link_service",
        "LinkService",
    ),
    "QuestCategoryGroup": (
        "app.modules.encyclopedia.services.quest_hierarchy_service",
        "QuestCategoryGroup",
    ),
    "QuestHierarchy": (
        "app.modules.encyclopedia.services.quest_hierarchy_service",
        "QuestHierarchy",
    ),
    "QuestHierarchyPath": (
        "app.modules.encyclopedia.services.quest_hierarchy_service",
        "QuestHierarchyPath",
    ),
    "QuestHierarchyService": (
        "app.modules.encyclopedia.services.quest_hierarchy_service",
        "QuestHierarchyService",
    ),
    "QuestSeries": (
        "app.modules.encyclopedia.services.quest_hierarchy_service",
        "QuestSeries",
    ),
    "RelatedEncyclopediaData": (
        "app.modules.encyclopedia.services.related_data_service",
        "RelatedEncyclopediaData",
    ),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


def build_related_encyclopedia_data(*args, **kwargs):
    """Load the related-data builder only when the preload worker actually runs."""

    from app.modules.encyclopedia.services.related_data_service import (
        build_related_encyclopedia_data as build,
    )

    return build(*args, **kwargs)


def related_data_build_count() -> int:
    from app.modules.encyclopedia.services.related_data_service import (
        related_data_build_count as build_count,
    )

    return int(build_count())


__all__ = [
    "ACHIEVEMENT_PROGRESS_FILE",
    "GUIDE_PROGRESS_FILE",
    "AchievementProgressService",
    "EncyclopediaService",
    "GuideProgressCalculator",
    "GuideProgressService",
    "LinkService",
    "ProgressCount",
    "QuestProgressService",
    "QuestGraphService",
    "QuestCategoryGroup",
    "QuestHierarchy",
    "QuestHierarchyPath",
    "QuestHierarchyService",
    "QuestSeries",
    "RelatedEncyclopediaData",
    "build_related_encyclopedia_data",
    "related_data_build_count",
]
