from __future__ import annotations

from typing import Any


_REAL_ENCYCLOPEDIA_PAGE: type | None = None
_GUIDE_VIEW_LOADED = False


def _ensure_guide_view_loaded() -> None:
    global _GUIDE_VIEW_LOADED
    if _GUIDE_VIEW_LOADED:
        return

    from app.modules.encyclopedia.views.guides_view import GuideHomeCard

    # Load the canonical Guide primitives only when Guides are requested.
    _ = GuideHomeCard
    _GUIDE_VIEW_LOADED = True


def _load_encyclopedia_page_class() -> type:
    global _REAL_ENCYCLOPEDIA_PAGE
    real = _REAL_ENCYCLOPEDIA_PAGE
    if real is not None:
        return real

    from app.modules.encyclopedia.views.encyclopedia_page import (
        EncyclopediaPage as RealEncyclopediaPage,
    )

    _ensure_guide_view_loaded()
    _REAL_ENCYCLOPEDIA_PAGE = RealEncyclopediaPage
    return RealEncyclopediaPage


class _LazyEncyclopediaPageMeta(type):
    def __call__(cls, *args: Any, **kwargs: Any):
        return _load_encyclopedia_page_class()(*args, **kwargs)

    def __instancecheck__(cls, instance: object) -> bool:
        real = _REAL_ENCYCLOPEDIA_PAGE
        return bool(real is not None and isinstance(instance, real))

    def __subclasscheck__(cls, subclass: type) -> bool:
        real = _REAL_ENCYCLOPEDIA_PAGE
        return bool(real is not None and issubclass(subclass, real))


class EncyclopediaPage(metaclass=_LazyEncyclopediaPageMeta):
    """Lazy public constructor/type facade for the runtime Encyclopedia page.

    main.py imports this symbol before QApplication exists. Keeping the facade
    lightweight avoids importing all Qt Encyclopedia/Guides/Successes views
    before the splash while preserving both ``EncyclopediaPage(...)`` and the
    shell's ``isinstance(page, EncyclopediaPage)`` checks.
    """


def __getattr__(name: str):
    if name == "GuidesView":
        _ensure_guide_view_loaded()
        from app.modules.encyclopedia.views.guides_view import GuidesView

        return GuidesView
    if name == "EncyclopediaPlaceholderView":
        from app.modules.encyclopedia.views.placeholder_view import (
            EncyclopediaPlaceholderView,
        )

        return EncyclopediaPlaceholderView
    raise AttributeError(name)


__all__ = ["EncyclopediaPage", "EncyclopediaPlaceholderView", "GuidesView"]
