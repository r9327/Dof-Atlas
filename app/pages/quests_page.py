# -*- coding: utf-8 -*-
"""Canonical Quests page with lazy materialization for large catalogs."""

from __future__ import annotations

from contextlib import suppress

from app.pages._quests_page_impl import (
    HIERARCHY_ID_ROLE,
    HIERARCHY_KIND_ROLE,
    MIN_QUEST_SEARCH_CHARS,
    QuestsPage as _EagerQuestsPage,
    linkify_travel_coordinates,
    load_owned_items,
    quest_detail_html,
    quest_required_items,
)
from PySide6.QtCore import QTimer


_MIN_LAZY_QUESTS = 500
_LARGE_CATALOG_SEARCH_DEBOUNCE_MS = 120

__all__ = [
    "HIERARCHY_ID_ROLE",
    "HIERARCHY_KIND_ROLE",
    "MIN_QUEST_SEARCH_CHARS",
    "QuestsPage",
    "linkify_travel_coordinates",
    "quest_detail_html",
    "quest_required_items",
]


class QuestsPage(_EagerQuestsPage):
    """Quests page that keeps large-catalog work proportional to what is visible.

    Large catalogs materialize quest leaves one series at a time. The page keeps
    the initial detail empty, debounces rich search, caches normalized search
    documents and builds compatibility-only HTML only when a legacy consumer
    explicitly asks for it.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._quest_search_text_cache: dict[int, str] = {}
        detail_view_defaulted = "defer_detail_view" not in kwargs
        kwargs.setdefault("defer_detail_view", True)
        if detail_view_defaulted:
            candidate_catalog = kwargs.get("catalog")
            if candidate_catalog is None:
                provider = kwargs.get("quest_provider")
                candidate_catalog = getattr(provider, "_catalog", None)
            quest_count = len(getattr(candidate_catalog, "quests", ()) or ())
            if candidate_catalog is not None and quest_count < _MIN_LAZY_QUESTS:
                kwargs["defer_detail_view"] = False
        super().__init__(*args, **kwargs)

        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(_LARGE_CATALOG_SEARCH_DEBOUNCE_MS)
        self._search_debounce_timer.timeout.connect(self._flush_search_refresh)
        with suppress(RuntimeError, TypeError):
            self.search.textChanged.disconnect()
        self.search.textChanged.connect(self._on_search_text_changed)

    def _large_hierarchy_catalog(self) -> bool:
        return (
            len(getattr(getattr(self, "catalog", None), "quests", ()) or ())
            >= _MIN_LAZY_QUESTS
        )

    def restore_last_quest(self) -> None:
        """Keep construction cheap; history must not force a full quest render."""

        quest_id = self.load_last_quest_id()
        self._restored_quest_id = (
            int(quest_id)
            if quest_id is not None and int(quest_id) in self.catalog.by_id
            else None
        )
        self.selected_quest_id = None
        self.active_series_id = ""
        self.render_breadcrumb()

    def _on_search_text_changed(self, text: str) -> None:
        if not self._large_hierarchy_catalog() or len(str(text or "").strip()) < MIN_QUEST_SEARCH_CHARS:
            self._search_debounce_timer.stop()
            super().refresh_quests()
            return
        self._search_debounce_timer.start()

    def _flush_search_refresh(self) -> None:
        super().refresh_quests()

    def close_search_results(self) -> None:
        self._search_debounce_timer.stop()
        super().close_search_results()

    def quest_search_text(self, quest: QuestRecord) -> str:
        quest_id = int(quest.id)
        cached = self._quest_search_text_cache.get(quest_id)
        if cached is None:
            cached = super().quest_search_text(quest)
            self._quest_search_text_cache[quest_id] = cached
        return cached

    def update_related_context(self, *args, **kwargs) -> None:
        self._quest_search_text_cache.clear()
        super().update_related_context(*args, **kwargs)
