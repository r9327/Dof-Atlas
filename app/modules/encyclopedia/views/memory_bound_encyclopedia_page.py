from __future__ import annotations

import sys

from PySide6.QtWidgets import QWidget

from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, GUIDES_TAB, QUESTS_TAB
from app.modules.encyclopedia.views.encyclopedia_page import EncyclopediaPage as BaseEncyclopediaPage
from app.modules.encyclopedia.views.related_preload_state import RelatedPreloadGate


class EncyclopediaPage(BaseEncyclopediaPage):
    """Keep heavy runtime warm only while Encyclopedia is active.

    Heavy Qt view trees are hibernated between tabs. When the whole Encyclopedia
    leaves the screen, reconstructible Success/Guide catalogues are released too;
    the existing background stages rebuild them only when the player returns.

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
        self._memory_has_been_shown = False
        self._memory_release_runtime_when_idle = False
        self._memory_pending_tab_label = ""
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
        # The provider may have released its resident summaries while Home was
        # visible. Rehydrate from the already-built SQLite store on demand.
        self.quest_provider.get_catalog()
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

    @staticmethod
    def _clear_reconstructible_image_cache() -> None:
        """Release decoded Encyclopedia thumbnails when the whole page sleeps."""

        module = sys.modules.get("app.modules.encyclopedia.services.image_service")
        if module is None:
            return
        service = getattr(module, "ENCYCLOPEDIA_IMAGE_SERVICE", None)
        clear = getattr(service, "clear", None)
        if callable(clear):
            clear()

    def _release_runtime_providers(self) -> bool:
        if bool(getattr(self, "_achievement_load_started", False)) or bool(
            getattr(self, "_related_preload_started", False)
        ):
            return False

        achievement_provider = getattr(getattr(self, "service", None), "achievement_provider", None)
        guide_provider = getattr(getattr(self, "service", None), "guide_provider", None)
        for provider in (achievement_provider, guide_provider):
            release = getattr(provider, "release_catalogue", None)
            if callable(release):
                release()

        graph = getattr(self, "_quest_graph", None)
        if graph is not None:
            graph.achievement_provider = None
            graph.guide_provider = None
            graph.catalog = None
            graph.quest_provider = None
        self._quest_graph = None

        release_quests = getattr(self.quest_provider, "release_catalogue", None)
        if callable(release_quests):
            release_quests()

        # Thumbnails are fully reconstructible. Keeping the shared Guide image
        # LRU alive after Home pins several megabytes of QPixmap backing memory
        # even though every Guide widget has already been hibernated.
        self._clear_reconstructible_image_cache()

        self._achievement_ready = False
        self._guide_runtime_ready = False
        self._related_ready = False
        self._achievement_provider_supplied = False
        self._guide_provider_supplied = False
        self._catalog_context_published = False
        self._full_guide_tab_requested = False
        self._success_runtime_requested = False
        self._pending_lazy_tab = ""
        self._related_preload_gate = RelatedPreloadGate()
        self._memory_release_runtime_when_idle = False
        return True

    def prepare_external_tab_navigation(self, label: str) -> None:
        """Prioritize an explicit shell tab request over stale hidden-tab state."""

        requested = str(label or "").strip()
        self._memory_pending_tab_label = requested if requested in self.tab_labels() else ""
        # A visible return cancels a deferred off-screen release request. A worker
        # already running may finish, but its result must remain usable now.
        self._memory_release_runtime_when_idle = False

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API
        # QStackedWidget can emit a hide event while a freshly-created page is
        # inserted behind the current page. That is construction, not a user
        # departure: keep the preloaded Quests view intact until the page has
        # genuinely been shown at least once.
        if self._memory_has_been_shown:
            self.hibernate_heavy_views()
            self._memory_release_runtime_when_idle = True
            self._release_runtime_providers()
        super().hideEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Restore the active heavy tab after page-level hibernation.

        Hiding the whole Encyclopedia intentionally releases its widget tree.
        Showing it again does not emit QTabWidget.currentChanged when the tab
        index stayed identical, so restore the active tab explicitly here.
        """

        self._memory_has_been_shown = True
        self._memory_release_runtime_when_idle = False
        super().showEvent(event)

        # AtlasWindow sets pending_encyclopedia_tab before showing this page.
        # Do not rebuild the previously active heavy tab just before the queued
        # navigation switches to a different one.
        owner = self.window()
        pending_label = str(getattr(owner, "pending_encyclopedia_tab", "") or "")
        if pending_label and pending_label in self.tab_labels():
            return

        index = self.tabs.currentIndex()
        if index < 0:
            return
        label = self._memory_pending_tab_label or self.tabs.tabText(index)
        if label == QUESTS_TAB and self.quest_page is None:
            self._restore_quests_view()
        elif label == ACHIEVEMENTS_TAB:
            if not bool(getattr(self, "_achievement_ready", False)):
                self._start_full_achievement_runtime()
            elif self.get_achievements_view() is None:
                self.ensure_achievements_view()
        elif label == GUIDES_TAB:
            if not bool(getattr(self, "_guide_runtime_ready", False)):
                self._start_full_guide_runtime()
            elif getattr(self, "guides_view", None) is None:
                self.ensure_guides_view()
        self.sync_character_to_children()

    def on_tab_changed(self, index: int) -> None:
        label = self.tabs.tabText(index) if index >= 0 else ""
        if label and label == self._memory_pending_tab_label:
            self._memory_pending_tab_label = ""
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

    def _collect_achievement_runtime(self, result: object) -> None:
        super()._collect_achievement_runtime(result)
        if self._memory_release_runtime_when_idle and not self.isVisible():
            self.hibernate_heavy_views()
            self._release_runtime_providers()

    def collect_related_preload(self, result: object) -> None:
        super().collect_related_preload(result)
        if self._memory_release_runtime_when_idle and not self.isVisible():
            self.hibernate_heavy_views()
            self._release_runtime_providers()

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
            view = super().ensure_full_guides_view()
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
