# -*- coding: utf-8 -*-
"""Canonical Quests page with lazy materialization for large catalogs."""

from __future__ import annotations

from app.pages._quests_page_impl import *  # noqa: F401,F403
from app.pages._quests_page_impl import (
    HIERARCHY_ID_ROLE,
    HIERARCHY_KIND_ROLE,
    NativeQuestDetailPanel,
    QuestsPage as _EagerQuestsPage,
    quest_detail_html,
)
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTreeWidgetItem


_MIN_LAZY_QUESTS = 500
_LAZY_POPULATED_ROLE = HIERARCHY_ID_ROLE + 1000
_LARGE_CATALOG_SEARCH_DEBOUNCE_MS = 120


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
        self._owned_items_file_signature: tuple[int, int] | None = None
        super().__init__(*args, **kwargs)

        old_detail = self.detail
        self.detail = _LazyCompatQuestDetailPanel(self)
        self.detail.setVisible(False)
        old_detail.deleteLater()

        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(_LARGE_CATALOG_SEARCH_DEBOUNCE_MS)
        self._search_debounce_timer.timeout.connect(self._flush_search_refresh)
        try:
            self.search.textChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.search.textChanged.connect(self._on_search_text_changed)

    def _large_hierarchy_catalog(self) -> bool:
        return (
            len(getattr(getattr(self, "catalog", None), "quests", ()) or ())
            >= _MIN_LAZY_QUESTS
        )

    def _completed_hierarchy_snapshot(self) -> set[int]:
        return (
            self.quest_progress_service.completed_quest_ids(self.current_character_key)
            if self.current_character_key
            else set()
        )

    def _refresh_materialized_hierarchy_labels(self) -> None:
        completed = self._completed_hierarchy_snapshot()
        for quest_id, items in tuple(self.quest_tree_items.items()):
            quest = self.catalog.by_id.get(int(quest_id))
            if quest is None:
                continue
            label = self.hierarchy_quest_label(quest, completed)
            for item in tuple(items):
                item.setText(0, label)

    def _populate_hierarchy_series(self, series_item: QTreeWidgetItem) -> None:
        if series_item.data(0, HIERARCHY_KIND_ROLE) != "series":
            return
        if bool(series_item.data(0, _LAZY_POPULATED_ROLE)):
            return

        series_id = str(series_item.data(0, HIERARCHY_ID_ROLE) or "")
        series = self.hierarchy.series_by_id.get(series_id)
        if series is None:
            return

        while series_item.childCount():
            series_item.takeChild(0)

        completed = self._completed_hierarchy_snapshot()
        for quest_id in series.quest_ids:
            quest = self.catalog.by_id.get(int(quest_id))
            if quest is None:
                continue
            quest_item = QTreeWidgetItem(
                [self.hierarchy_quest_label(quest, completed)]
            )
            quest_item.setData(0, HIERARCHY_KIND_ROLE, "quest")
            quest_item.setData(0, HIERARCHY_ID_ROLE, int(quest.id))
            quest_item.setToolTip(0, quest.name)
            series_item.addChild(quest_item)
            self.quest_tree_items.setdefault(int(quest.id), []).append(quest_item)
        series_item.setData(0, _LAZY_POPULATED_ROLE, True)

    def _on_hierarchy_item_expanded(self, item: QTreeWidgetItem) -> None:
        if self._large_hierarchy_catalog():
            self._populate_hierarchy_series(item)

    def rebuild_hierarchy(self) -> None:
        if not self._large_hierarchy_catalog():
            super().rebuild_hierarchy()
            return

        selected_id = self.selected_quest_id
        preferred_series = self.active_series_id
        hierarchy_token = id(self.hierarchy)

        if (
            getattr(self, "_lazy_hierarchy_token", None) == hierarchy_token
            and self.hierarchy_tree.topLevelItemCount() > 0
        ):
            self._refresh_materialized_hierarchy_labels()
            if selected_id is not None:
                self.sync_hierarchy_selection(selected_id, preferred_series)
            self.render_breadcrumb()
            return

        tree = self.hierarchy_tree
        tree.blockSignals(True)
        tree.setUpdatesEnabled(False)
        try:
            tree.clear()
            self.category_items.clear()
            self.series_items.clear()
            self.quest_tree_items.clear()
            for category in self.hierarchy.categories:
                category_item = QTreeWidgetItem([category.name])
                category_item.setData(0, HIERARCHY_KIND_ROLE, "category")
                category_item.setData(0, HIERARCHY_ID_ROLE, category.name)
                category_item.setToolTip(0, f"{len(category.series)} suites")
                tree.addTopLevelItem(category_item)
                self.category_items[category.name] = category_item
                for series in category.series:
                    series_item = QTreeWidgetItem([series.name])
                    series_item.setData(0, HIERARCHY_KIND_ROLE, "series")
                    series_item.setData(0, HIERARCHY_ID_ROLE, series.id)
                    series_item.setToolTip(0, f"{len(series.quest_ids)} quêtes")
                    if series.quest_ids:
                        placeholder = QTreeWidgetItem([""])
                        placeholder.setData(0, HIERARCHY_KIND_ROLE, "lazy")
                        series_item.addChild(placeholder)
                    category_item.addChild(series_item)
                    self.series_items[series.id] = series_item
            self._lazy_hierarchy_token = hierarchy_token
        finally:
            tree.blockSignals(False)
            tree.setUpdatesEnabled(True)

        if not getattr(self, "_lazy_hierarchy_signal_installed", False):
            tree.itemExpanded.connect(
                lambda item, owner=self: owner._on_hierarchy_item_expanded(item)
            )
            self._lazy_hierarchy_signal_installed = True

        if selected_id is not None:
            self.sync_hierarchy_selection(selected_id, preferred_series)
        self.render_breadcrumb()

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

    def sync_hierarchy_selection(
        self,
        quest_id: int,
        preferred_series_id: str = "",
    ) -> QuestHierarchyPath | None:
        if not self._large_hierarchy_catalog():
            return super().sync_hierarchy_selection(quest_id, preferred_series_id)

        path = self.hierarchy.path_for(int(quest_id), preferred_series_id)
        if path is None:
            self.active_series_id = ""
            return None
        self.active_series_id = path.series.id
        series_item = self.series_items.get(path.series.id)
        if series_item is None:
            return path
        self._populate_hierarchy_series(series_item)
        parent = series_item.parent()
        if parent is not None:
            parent.setExpanded(True)
        series_item.setExpanded(True)
        quest_item = next(
            (
                item
                for item in self.quest_tree_items.get(int(quest_id), ())
                if item.parent() is series_item
            ),
            None,
        )
        if quest_item is not None:
            self.hierarchy_tree.blockSignals(True)
            self.hierarchy_tree.setCurrentItem(quest_item)
            self.hierarchy_tree.scrollToItem(quest_item)
            self.hierarchy_tree.blockSignals(False)
        return path

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

    def focus_hierarchy_series(self, series_id: str) -> None:
        if not self._large_hierarchy_catalog():
            super().focus_hierarchy_series(series_id)
            return

        item = self.series_items.get(str(series_id))
        if item is None:
            return
        self._populate_hierarchy_series(item)
        parent = item.parent()
        if parent is not None:
            parent.setExpanded(True)
        item.setExpanded(True)
        self.hierarchy_tree.setCurrentItem(item)
        self.hierarchy_tree.scrollToItem(item)
        self.hierarchy_tree.setFocus()

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

    def refresh_owned_items(self) -> None:
        path = self.owned_items_path
        try:
            stat = path.stat()
        except OSError:
            return
        signature = (int(stat.st_mtime_ns), int(stat.st_size))
        if signature == self._owned_items_file_signature:
            return
        self.owned_items = load_owned_items(path)
        self._owned_items_file_signature = signature

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
        self.quest_detail_view.set_character_key(self.current_character_key)
        active_series = self.hierarchy.series_by_id.get(self.active_series_id)
        self.quest_detail_view.show_quest(
            int(quest.id),
            QuestViewContext(
                host="quests",
                ordered_quest_ids=active_series.quest_ids if active_series is not None else (),
            ),
        )
