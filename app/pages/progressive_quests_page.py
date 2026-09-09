from __future__ import annotations

from PySide6.QtWidgets import QTreeWidgetItem

from app.pages.lazy_quests_page import LazyQuestsPage
from app.pages.quests_page import HIERARCHY_ID_ROLE, HIERARCHY_KIND_ROLE


class ProgressiveQuestsPage(LazyQuestsPage):
    """Quest hierarchy that materializes one visible level at a time.

    Initial paint creates category names only. Expanding a category creates its
    quest-series names, expanding one series creates only that series' quest
    names, and the inherited LazyQuestsPage loads the rich quest detail from the
    deferred data source only after the player selects a quest.
    """

    def __init__(self, *args, **kwargs) -> None:
        self._loaded_category_names: set[str] = set()
        super().__init__(*args, **kwargs)

        # Keep the Quêtes search visually inside the tab body. The base page is
        # intentionally marginless, which made the search row touch the tabs.
        root = self.layout()
        if root is not None:
            margins = root.contentsMargins()
            root.setContentsMargins(
                margins.left(),
                max(8, margins.top()),
                margins.right(),
                margins.bottom(),
            )

    def update_related_context(self, *args, **kwargs) -> None:
        # Guide and Success stages can converge on the exact same shared graph.
        # Do not rebuild the whole Category -> Suite hierarchy a second time when
        # the page already owns every object supplied by the completion callback.
        if not args:
            guide_provider = kwargs.get("guide_provider")
            achievement_provider = kwargs.get("achievement_provider")
            graph = kwargs.get("graph")
            if (
                (guide_provider is None or guide_provider is self.guide_provider)
                and (
                    achievement_provider is None
                    or achievement_provider is self.achievement_provider
                )
                and (graph is None or graph is self.graph)
            ):
                return
        super().update_related_context(*args, **kwargs)

    def _category_model(self, category_name: str):
        target = str(category_name or "")
        return next(
            (category for category in self.hierarchy.categories if category.name == target),
            None,
        )

    def _category_for_series(self, series_id: str):
        target = str(series_id or "")
        for category in self.hierarchy.categories:
            if any(series.id == target for series in category.series):
                return category
        return None

    def rebuild_hierarchy(self) -> None:
        selected_id = self.selected_quest_id
        preferred_series = self.active_series_id
        completed_quest_ids = (
            self.quest_progress_service.completed_quest_ids(self.current_character_key)
            if self.current_character_key
            else set()
        )
        self._completed_hierarchy_quest_ids = set(completed_quest_ids)
        self._quest_state_cache.clear()

        hierarchy_token = id(self.hierarchy)
        if (
            hierarchy_token == self._rendered_hierarchy_token
            and self.hierarchy_tree.topLevelItemCount() > 0
        ):
            self._refresh_loaded_hierarchy_labels()
            if selected_id is not None:
                self.sync_hierarchy_selection(selected_id, preferred_series)
            self.render_breadcrumb()
            return

        self._loaded_category_names.clear()
        self._loaded_series_ids.clear()
        previous_blocked = self.hierarchy_tree.blockSignals(True)
        previous_updates = self.hierarchy_tree.updatesEnabled()
        self.hierarchy_tree.setUpdatesEnabled(False)
        try:
            self.hierarchy_tree.clear()
            self.category_items.clear()
            self.series_items.clear()
            self.quest_tree_items.clear()
            for category in self.hierarchy.categories:
                category_item = QTreeWidgetItem([category.name])
                category_item.setData(0, HIERARCHY_KIND_ROLE, "category")
                category_item.setData(0, HIERARCHY_ID_ROLE, category.name)
                category_item.setToolTip(0, f"{len(category.series)} suites")
                if category.series:
                    placeholder = QTreeWidgetItem([""])
                    placeholder.setData(0, HIERARCHY_KIND_ROLE, "placeholder")
                    category_item.addChild(placeholder)
                self.hierarchy_tree.addTopLevelItem(category_item)
                self.category_items[category.name] = category_item
            self._rendered_hierarchy_token = hierarchy_token
        finally:
            self.hierarchy_tree.setUpdatesEnabled(previous_updates)
            self.hierarchy_tree.blockSignals(previous_blocked)

        if selected_id is not None:
            self.sync_hierarchy_selection(selected_id, preferred_series)
        self.render_breadcrumb()

    def ensure_category_series_loaded(self, category_name: str) -> QTreeWidgetItem | None:
        category_name = str(category_name or "")
        category_item = self.category_items.get(category_name)
        if category_item is None or category_name in self._loaded_category_names:
            return category_item
        category = self._category_model(category_name)
        if category is None:
            return category_item

        previous_blocked = self.hierarchy_tree.blockSignals(True)
        previous_updates = self.hierarchy_tree.updatesEnabled()
        self.hierarchy_tree.setUpdatesEnabled(False)
        try:
            while category_item.childCount():
                category_item.takeChild(0)
            for series in category.series:
                series_item = QTreeWidgetItem([series.name])
                series_item.setData(0, HIERARCHY_KIND_ROLE, "series")
                series_item.setData(0, HIERARCHY_ID_ROLE, series.id)
                series_item.setToolTip(0, f"{len(series.quest_ids)} quêtes")
                if series.quest_ids:
                    placeholder = QTreeWidgetItem([""])
                    placeholder.setData(0, HIERARCHY_KIND_ROLE, "placeholder")
                    series_item.addChild(placeholder)
                category_item.addChild(series_item)
                self.series_items[series.id] = series_item
            self._loaded_category_names.add(category_name)
        finally:
            self.hierarchy_tree.setUpdatesEnabled(previous_updates)
            self.hierarchy_tree.blockSignals(previous_blocked)
        return category_item

    def on_hierarchy_item_expanded(self, item: QTreeWidgetItem) -> None:
        kind = item.data(0, HIERARCHY_KIND_ROLE)
        if kind == "category":
            self.ensure_category_series_loaded(str(item.data(0, HIERARCHY_ID_ROLE) or ""))
            return
        if kind == "series":
            self.ensure_series_quests_loaded(str(item.data(0, HIERARCHY_ID_ROLE) or ""))

    def ensure_series_quests_loaded(self, series_id: str) -> QTreeWidgetItem | None:
        series_id = str(series_id or "")
        if series_id not in self.series_items:
            category = self._category_for_series(series_id)
            if category is not None:
                self.ensure_category_series_loaded(category.name)
        return super().ensure_series_quests_loaded(series_id)

    def sync_hierarchy_selection(self, quest_id: int, preferred_series_id: str = ""):
        path = self.hierarchy.path_for(int(quest_id), preferred_series_id)
        if path is None:
            self.active_series_id = ""
            return None
        self.ensure_category_series_loaded(path.category.name)
        return super().sync_hierarchy_selection(quest_id, preferred_series_id)

    def focus_hierarchy_series(self, series_id: str) -> None:
        series_id = str(series_id or "")
        if series_id not in self.series_items:
            category = self._category_for_series(series_id)
            if category is not None:
                self.ensure_category_series_loaded(category.name)
        super().focus_hierarchy_series(series_id)


__all__ = ["ProgressiveQuestsPage"]
