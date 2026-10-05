from __future__ import annotations

from PySide6.QtWidgets import QWidget

from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage as BaseEncyclopediaPage


class EncyclopediaPage(BaseEncyclopediaPage):
    """Keep providers warm while releasing inactive heavy Qt view trees.

    The catalogue/runtime providers stay resident so reopening a tab does not
    rebuild data from disk. Only the heavyweight widget representation is
    hibernated when another Encyclopedia tab becomes active or the whole page
    leaves the screen.

    The runtime class deliberately keeps the historical public type name
    ``EncyclopediaPage``. ``MemoryBoundEncyclopediaPage`` remains an alias for
    the Phase 8 implementation so lazy facades and memory-policy contracts keep
    their explicit implementation reference without breaking shell identity
    checks based on the concrete Qt widget type name.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._memory_restore_guide_id = ""
        self._memory_restore_guide_quest_id: int | None = None
        self._memory_restore_guide_state = ""
        self._memory_restore_achievement_id: int | None = None
        self._memory_restore_quest_id: int | None = None
        self._memory_restore_quest_series = ""
        self._memory_restore_quest_search = ""
        super().__init__(*args, **kwargs)

    def _replace_with_lazy_slot(self, label: str, widget: QWidget) -> None:
        labels = self.tab_labels()
        if label not in labels:
            return
        index = labels.index(label)
        if self.tabs.widget(index) is not widget:
            return

        current_label = self.current_tab_label()
        slot = QWidget()
        slot.setObjectName("EncyclopediaLazySlot")

        blocked = self.tabs.blockSignals(True)
        try:
            self.tabs.removeTab(index)
            self.tabs.insertTab(index, slot, label)
            labels_after = self.tab_labels()
            if current_label in labels_after:
                self.tabs.setCurrentIndex(labels_after.index(current_label))
        finally:
            self.tabs.blockSignals(blocked)

        self._lazy_slots[label] = slot
        widget.setParent(None)
        widget.deleteLater()

    def _hibernate_quests(self) -> None:
        page = getattr(self, "quest_page", None)
        if page is None:
            return
        current_id = getattr(page, "selected_quest_id", None)
        try:
            self._memory_restore_quest_id = int(current_id) if current_id is not None else None
        except (TypeError, ValueError):
            self._memory_restore_quest_id = None
        self._memory_restore_quest_series = str(getattr(page, "active_series_id", "") or "")
        search = getattr(page, "search", None)
        self._memory_restore_quest_search = str(search.text() if search is not None else "")
        self._replace_with_lazy_slot(QUESTS_TAB, page)
        self.quest_page = None

    def _restore_quests_view(self):
        if self.quest_page is not None:
            return self.quest_page
        # The resident QuestProvider keeps the SQLite-backed compact catalogue
        # warm. Rebuild only the Qt representation; never reparse documentary
        # quest sources just because the user comes back to the tab.
        if getattr(self.quest_provider, "_catalog", None) is None:
            return None
        page = self._build_quests_page_progressive()
        self.replace_tab_widget(QUESTS_TAB, page)
        if self._memory_restore_quest_series:
            page.active_series_id = self._memory_restore_quest_series
        if self._memory_restore_quest_search and hasattr(page, "search"):
            page.search.setText(self._memory_restore_quest_search)
        quest_id = self._memory_restore_quest_id
        self._memory_restore_quest_id = None
        if quest_id is not None:
            page.select_quest(quest_id)
        return page

    def _hibernate_achievements(self) -> None:
        if not bool(getattr(self, "_achievement_ready", False)):
            return
        view = self.get_achievements_view()
        if view is None:
            return
        current_id = getattr(view, "current_achievement_id", None)
        try:
            self._memory_restore_achievement_id = int(current_id) if current_id is not None else None
        except (TypeError, ValueError):
            self._memory_restore_achievement_id = None
        self._replace_with_lazy_slot(ACHIEVEMENTS_TAB, view)

    def _hibernate_guides(self) -> None:
        if not bool(getattr(self, "_guide_runtime_ready", False)):
            return
        view = getattr(self, "guides_view", None)
        if view is None:
            return
        self._memory_restore_guide_id = str(getattr(view, "current_guide_id", "") or "")
        current_quest_id = getattr(view, "current_quest_id", None)
        try:
            self._memory_restore_guide_quest_id = (
                int(current_quest_id) if current_quest_id is not None else None
            )
        except (TypeError, ValueError):
            self._memory_restore_guide_quest_id = None
        self._memory_restore_guide_state = str(getattr(view, "state", "") or "")
        self._replace_with_lazy_slot(GUIDES_TAB, view)
        self.guides_view = None
        provider = getattr(getattr(self, "service", None), "guide_provider", None)
        release_detail = getattr(provider, "release_detail_cache", None)
        if callable(release_detail):
            release_detail()

    def hibernate_heavy_views(self, *, active_label: str = "") -> None:
        if active_label != QUESTS_TAB:
            self._hibernate_quests()
        if active_label != ACHIEVEMENTS_TAB:
            self._hibernate_achievements()
        if active_label != GUIDES_TAB:
            self._hibernate_guides()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.hibernate_heavy_views()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Restore the active heavy tab after page-level hibernation.

        Hiding the whole Encyclopedia intentionally releases its widget tree.
        Showing it again does not emit QTabWidget.currentChanged when the tab
        index stayed identical, so restore the active tab explicitly here.
        """

        super().showEvent(event)
        index = self.tabs.currentIndex()
        if index < 0:
            return
        label = self.tabs.tabText(index)
        if label == QUESTS_TAB and self.quest_page is None:
            self._restore_quests_view()
        elif label == ACHIEVEMENTS_TAB and self.get_achievements_view() is None:
            self.ensure_achievements_view()
        elif label == GUIDES_TAB and getattr(self, "guides_view", None) is None:
            self.ensure_guides_view()
        self.sync_character_to_children()

    def on_tab_changed(self, index: int) -> None:
        label = self.tabs.tabText(index) if index >= 0 else ""
        self.hibernate_heavy_views(active_label=label)
        if label == QUESTS_TAB and self.quest_page is None:
            restored = self._restore_quests_view()
            if restored is not None:
                labels = self.tab_labels()
                index = labels.index(QUESTS_TAB)
        super().on_tab_changed(index)

    def ensure_achievements_view(self):
        existing = self.get_achievements_view()
        view = super().ensure_achievements_view()
        if existing is None and self._memory_restore_achievement_id is not None:
            achievement_id = self._memory_restore_achievement_id
            self._memory_restore_achievement_id = None
            if bool(getattr(self, "_achievement_ready", False)):
                view.show_achievement(achievement_id)
        return view

    def ensure_guides_view(self):
        created = getattr(self, "guides_view", None) is None
        view = super().ensure_guides_view()
        if created and bool(getattr(self, "_guide_runtime_ready", False)) and not bool(
            getattr(view, "_runtime_ready", False)
        ):
            view.hydrate_runtime(
                graph=getattr(self, "_quest_graph", None),
                initial_progress_by_guide=getattr(self, "_guide_progress_by_guide", None),
                initial_progress_character_key=getattr(
                    self,
                    "_guide_progress_character_key",
                    "",
                ),
            )
            if bool(getattr(self, "_achievement_ready", False)):
                apply_runtime = getattr(view, "apply_achievement_runtime", None)
                if callable(apply_runtime):
                    apply_runtime()

        if created and self._memory_restore_guide_id:
            guide_id = self._memory_restore_guide_id
            quest_id = self._memory_restore_guide_quest_id
            previous_state = self._memory_restore_guide_state
            self._memory_restore_guide_id = ""
            self._memory_restore_guide_quest_id = None
            self._memory_restore_guide_state = ""
            view.select_guide(guide_id)
            quest_detail_state = str(getattr(view, "QUEST_DETAIL", ""))
            if (
                quest_id is not None
                and (not previous_state or previous_state == quest_detail_state)
            ):
                view.show_quest_detail(quest_id)
        return view


MemoryBoundEncyclopediaPage = EncyclopediaPage


__all__ = ["EncyclopediaPage", "MemoryBoundEncyclopediaPage"]
