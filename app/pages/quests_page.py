# -*- coding: utf-8 -*-
"""Canonical Quests page with lazy materialization for large catalogs."""

from __future__ import annotations

from contextlib import suppress

from app.pages._quests_page_impl import (
    HIERARCHY_ID_ROLE,
    HIERARCHY_KIND_ROLE,
    MIN_QUEST_SEARCH_CHARS,
    NativeQuestDetailPanel,
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


class _LazyCompatQuestDetailPanel(NativeQuestDetailPanel):
    """Preserve legacy ``toHtml`` without paying for hidden HTML on every click."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lazy_payload = None
        self._lazy_html = ""

    def set_lazy_payload(self, payload) -> None:
        self._lazy_payload = payload
        self._lazy_html = ""
        self._html = ""

    def set_compat_html(self, html: str) -> None:
        self._lazy_payload = None
        self._lazy_html = ""
        super().set_compat_html(html)

    def toHtml(self) -> str:
        if self._lazy_html:
            return self._lazy_html
        if self._lazy_payload is None:
            return super().toHtml()
        (
            quest,
            done,
            owned_items,
            related_guides,
            related_achievements,
            achievement_state,
        ) = self._lazy_payload
        self._lazy_html = quest_detail_html(
            quest,
            done,
            owned_items,
            related_guides=related_guides,
            related_achievements=related_achievements,
            achievement_state=achievement_state,
        )
        return self._lazy_html


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

        old_detail = self.detail
        self.detail = _LazyCompatQuestDetailPanel(self)
        self.detail.setVisible(False)
        old_detail.deleteLater()

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

    def _refresh_after_quest_progress_change(
        self,
        quest_id: int,
        *,
        reload_progress: bool,
        refresh_list: bool,
        refresh_detail: bool,
    ) -> None:
        quest_id = int(quest_id)
        self.progress = (
            self.quest_progress_service.reload()
            if reload_progress
            else self.quest_progress_service.progress
        )
        self._sync_achievement_progress()
        self.refresh_hierarchy_quest_state(quest_id)
        if refresh_list:
            self.refresh_quests()
        if refresh_detail:
            self.show_quest_detail(quest_id)

    def on_shared_quest_progress_changed(self, quest_id: int) -> None:
        quest_id = int(quest_id)
        self._refresh_after_quest_progress_change(
            quest_id,
            reload_progress=True,
            refresh_list=len(self.search.text().strip()) >= MIN_QUEST_SEARCH_CHARS,
            refresh_detail=False,
        )
        self.selected_quest_id = quest_id

    def set_quest_checked(self, quest_id: int, done: bool) -> None:
        quest_id = int(quest_id)
        self.quest_progress_service.set_quest_completed(
            self.current_character_key,
            quest_id,
            bool(done),
        )
        self._refresh_after_quest_progress_change(
            quest_id,
            reload_progress=False,
            refresh_list=True,
            refresh_detail=True,
        )

    def _on_search_text_changed(self, text: str) -> None:
        if not self._large_hierarchy_catalog() or len(str(text or "").strip()) < MIN_QUEST_SEARCH_CHARS:
            self._search_debounce_timer.stop()
            super().refresh_quests()
            return
        self._search_debounce_timer.start()

    def _flush_search_refresh(self) -> None:
        super().refresh_quests()

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

    def show_quest_detail(self, quest_id: int) -> None:
        quest = self.catalog.by_id.get(int(quest_id))
        if not quest:
            self.quest_items_panel.setVisible(False)
            self.clear_detail_columns()
            return
        done = self.is_quest_done(quest.id)
        self.refresh_owned_items()
        related_guides = (
            self.guide_provider.get_guides_for_entity("quest", quest.id)
            if self.guide_provider is not None
            else []
        )
        related_achievements = (
            self.achievement_provider.get_by_quest(quest.id)
            if self.achievement_provider is not None
            else []
        )
        achievement_state = self.achievement_progress_service.state_for(
            self.current_character_key
        )
        self.detail.set_lazy_payload(
            (
                quest,
                done,
                dict(self.owned_items),
                list(related_guides),
                list(related_achievements),
                achievement_state,
            )
        )
        view = self._ensure_quest_detail_view()
        from app.modules.encyclopedia.widgets.quest_detail_view import QuestViewContext

        view.set_character_key(self.current_character_key)
        active_series = self.hierarchy.series_by_id.get(self.active_series_id)
        view.show_quest(
            int(quest.id),
            QuestViewContext(
                host="quests",
                ordered_quest_ids=active_series.quest_ids if active_series is not None else (),
            ),
        )
