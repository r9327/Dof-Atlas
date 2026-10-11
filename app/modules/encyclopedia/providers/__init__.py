from __future__ import annotations

from typing import Any

_REAL_ACHIEVEMENT_PROVIDER: type | None = None
_REAL_GUIDE_PROVIDER: type | None = None


def _load_achievement_provider_class() -> type:
    global _REAL_ACHIEVEMENT_PROVIDER
    real = _REAL_ACHIEVEMENT_PROVIDER
    if real is not None:
        return real
    from app.modules.encyclopedia.providers.memory_bound_achievement_provider import (
        MemoryBoundAchievementProvider as RealAchievementProvider,
    )

    _REAL_ACHIEVEMENT_PROVIDER = RealAchievementProvider
    return RealAchievementProvider


def _load_guide_provider_class() -> type:
    global _REAL_GUIDE_PROVIDER
    real = _REAL_GUIDE_PROVIDER
    if real is not None:
        return real
    from app.modules.encyclopedia.providers.guide_provider import (
        GuideProvider as RealGuideProvider,
    )

    _REAL_GUIDE_PROVIDER = RealGuideProvider
    return RealGuideProvider


class _LazyAchievementProviderMeta(type):
    def __call__(cls, *args: Any, **kwargs: Any):
        return _load_achievement_provider_class()(*args, **kwargs)

    def __instancecheck__(cls, instance: object) -> bool:
        return isinstance(instance, _load_achievement_provider_class())

    def __subclasscheck__(cls, subclass: type) -> bool:
        return issubclass(subclass, _load_achievement_provider_class())


class AchievementProvider(metaclass=_LazyAchievementProviderMeta):
    """Lazy public facade for the achievement provider."""


class _LazyGuideProviderMeta(type):
    def __call__(cls, *args: Any, **kwargs: Any):
        return _load_guide_provider_class()(*args, **kwargs)

    def __instancecheck__(cls, instance: object) -> bool:
        return isinstance(instance, _load_guide_provider_class())

    def __subclasscheck__(cls, subclass: type) -> bool:
        return issubclass(subclass, _load_guide_provider_class())


class GuideProvider(metaclass=_LazyGuideProviderMeta):
    """Lazy public facade for the guide provider.

    The shell imports GuideProvider for type checks long before any Guide data is
    requested. Delaying the concrete module also delays DofusItemProvider and the
    full Guide model family until the first actual provider construction.
    """


def __getattr__(name: str):
    if name == "QuestProvider":
        # Do not hydrate the Quest catalog simply by importing the provider
        # package for Guide or Achievement facades. Resolve the *real* class
        # on first request; preserve isinstance/subclass identity.
        from app.modules.encyclopedia.providers.quest_provider import QuestProvider

        globals()[name] = QuestProvider
        return QuestProvider
    if name == "DofusItemProvider":
        from app.modules.encyclopedia.providers.dofus_item_provider import DofusItemProvider

        globals()[name] = DofusItemProvider
        return DofusItemProvider
    raise AttributeError(name)


__all__ = ["AchievementProvider", "DofusItemProvider", "GuideProvider", "QuestProvider"]
