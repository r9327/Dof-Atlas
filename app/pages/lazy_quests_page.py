from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QTreeWidgetItem

from app.pages.quest_character_cache import quest_character_source_signature
from app.pages.quests_page import (
    HIERARCHY_ID_ROLE,
    HIERARCHY_KIND_ROLE,
    MIN_QUEST_SEARCH_CHARS,
    QuestsPage,
)
from app.quest_catalog import QuestRecord, normalize_text


class LazyQuestsPage(QuestsPage):
    """Materialize the quest hierarchy only as each visible level is requested."""

    def __init__(self, *args, **kwargs) -> None:
        self._loaded_category_names: set[str] = set()
        self._loaded_series_ids: set[str] = set()
        self._completed_hierarchy_quest_ids: set[int] = set()
        self._quest_search_text_cache: dict[int, str] = {}
        self._quest_state_cache: dict[int, str] = {}
        self._repeatability_cache: dict[int, str] = {}
        self._character_sources_signature: tuple[object, ...] | None = None
        self._last_quest_detail_signature: tuple[object, ...] | None = None
        self._rendered_hierarchy_token = 0
        self._detail_results = Queue()
        self._detail_worker = None
        self._requested_detail_id = None
        self._detail_pending = False
        self._search_worker = None
        self._search_results = Queue()
        super().__init__(*args, **kwargs)
        self._detail_timer = QTimer(self)
        self._detail_timer.setInterval(30)
        self._detail_timer.timeout.connect(self._collect_detail)
        self._search_index_timer = QTimer(self)
        self._search_index_timer.setInterval(30)
        self._search_index_timer.timeout.connect(self._collect_search_index)
        self.hierarchy_tree.itemExpanded.connect(self.on_hierarchy_item_expanded)

        # Keep the embedded search visually inside the tab body. The base page
        # is intentionally marginless, which otherwise makes the row touch tabs.
        root = self.layout()
        if root is not None:
            margins = root.contentsMargins()
            root.setContentsMargins(
                margins.left(),
                max(8, margins.top()),
                margins.right(),
                margins.bottom(),
            )

    @staticmethod
    def _file_stamp(path: Path) -> tuple[int, int, int]:
        try:
            stat = Path(path).stat()
        except OSError:
            return (0, 0, 0)
        return (int(stat.st_mtime_ns), int(stat.st_ctime_ns), int(stat.st_size))

    def _current_character_sources_signature(self) -> tuple[object, ...]:
        return quest_character_source_signature(
            self.profile_path,
            self.client_index_path,
        )

    def _quest_detail_signature(self, quest_id: int) -> tuple[object, ...]:
        return (
            int(quest_id),
            self.current_character_key,
            self.active_series_id,
            id(self.hierarchy),
            id(self.graph),
            id(self.guide_provider),
            id(self.achievement_provider),
            self._file_stamp(Path(self.quest_progress_service.path)),
            self._file_stamp(Path(self.achievement_progress_service.path)),
            self._file_stamp(Path(self.owned_items_path)),
        )

    def refresh_characters(self) -> None:
        signature = self._current_character_sources_signature()
        if signature == self._character_sources_signature and getattr(self, "characters", None):
            return
        QuestsPage.refresh_characters(self)
        self._character_sources_signature = self._current_character_sources_signature()

    def update_related_context(self, *args, **kwargs) -> None:
        # Guide and Success stages can converge on the exact same shared graph.
        # Avoid rebuilding Category -> Suite when the page already owns all of
        # the objects supplied by the completion callback.
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
        self._quest_search_text_cache.clear()
        self._quest_state_cache.clear()
        self._last_quest_detail_signature = None
        super().update_related_context(*args, **kwargs)

    def save_last_quest_id(self, quest_id: int) -> None:
        quest_id = int(quest_id)
        if self.load_last_quest_id() == quest_id:
            return
        QuestsPage.save_last_quest_id(self, quest_id)

    def show_quest_detail(self, quest_id: int) -> None:
        quest_id = int(quest_id)
        self._requested_detail_id = quest_id
        if getattr(self.catalog, "deferred_details", False) and not self.catalog.is_detail_cached(quest_id):
            self._detail_pending = True
            self.clear_detail_columns()
            self.status_callback("Chargement de la quête sélectionnée…")
            self._start_detail_worker(quest_id)
            return
        self._detail_pending = False
        signature = self._quest_detail_signature(quest_id)
        if (
            signature == self._last_quest_detail_signature
            and self.quest_detail_view.current_quest_id == quest_id
        ):
            return
        QuestsPage.show_quest_detail(self, quest_id)
        if self.quest_detail_view.current_quest_id == quest_id:
            self._last_quest_detail_signature = self._quest_detail_signature(quest_id)
        else:
            self._last_quest_detail_signature = None

    def _start_detail_worker(self, quest_id: int) -> None:
        if self._detail_worker is not None:
            return
        catalog, results = self.catalog, self._detail_results

        def load() -> None:
            error = None
            try:
                catalog.get_detail(quest_id)
            except Exception as exc:
                from app.constants import LOGGER
                LOGGER.exception("Quest detail load failed: quest_id=%s", quest_id)
                error = str(exc)
            finally:
                results.put((quest_id, error))

        self._detail_worker = Thread(target=load, name="DofusAtlasQuestDetail", daemon=True)
        try:
            self._detail_worker.start()
        except RuntimeError:
            from app.constants import LOGGER
            LOGGER.exception("Quest detail worker could not start: quest_id=%s", quest_id)
            self._detail_worker = None
            self._detail_pending = False
            self.status_callback("Impossible de démarrer le chargement de cette quête.")
            return
        self._detail_timer.start()

    def _collect_detail(self) -> None:
        try:
            quest_id, error = self._detail_results.get_nowait()
        except Empty:
            return
        self._detail_worker.join()
        self._detail_worker = None
        self._detail_timer.stop()
        target = self._requested_detail_id
        if target != self.selected_quest_id:
            self._detail_pending = False
            return
        if target != quest_id:
            if self._detail_pending and target is not None:
                self.show_quest_detail(target)
            return
        self._detail_pending = False
        if error is not None:
            self.status_callback(f"Impossible de charger cette quête : {error}")
            return
        self.show_quest_detail(quest_id)

    def _refresh_loaded_hierarchy_labels(self) -> None:
        for quest_id, items in tuple(self.quest_tree_items.items()):
            quest = self.catalog.by_id.get(int(quest_id))
            if quest is None:
                continue
            label = self.hierarchy_quest_label(
                quest,
                self._completed_hierarchy_quest_ids,
            )
            for item in tuple(items):
                item.setText(0, label)

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
        series_item = self.series_items.get(series_id)
        if series_item is None or series_id in self._loaded_series_ids:
            return series_item
        series = self.hierarchy.series_by_id.get(series_id)
        if series is None:
            return series_item

        previous_blocked = self.hierarchy_tree.blockSignals(True)
        previous_updates = self.hierarchy_tree.updatesEnabled()
        self.hierarchy_tree.setUpdatesEnabled(False)
        try:
            while series_item.childCount():
                series_item.takeChild(0)
            for quest_id in series.quest_ids:
                quest = self.catalog.by_id.get(int(quest_id))
                if quest is None:
                    continue
                quest_item = QTreeWidgetItem(
                    [self.hierarchy_quest_label(quest, self._completed_hierarchy_quest_ids)]
                )
                quest_item.setData(0, HIERARCHY_KIND_ROLE, "quest")
                quest_item.setData(0, HIERARCHY_ID_ROLE, int(quest.id))
                quest_item.setToolTip(0, quest.name)
                series_item.addChild(quest_item)
                self.quest_tree_items.setdefault(int(quest.id), []).append(quest_item)
            self._loaded_series_ids.add(series_id)
        finally:
            self.hierarchy_tree.setUpdatesEnabled(previous_updates)
            self.hierarchy_tree.blockSignals(previous_blocked)
        return series_item

    def sync_hierarchy_selection(self, quest_id: int, preferred_series_id: str = ""):
        path = self.hierarchy.path_for(int(quest_id), preferred_series_id)
        if path is None:
            self.active_series_id = ""
            return None
        self.ensure_category_series_loaded(path.category.name)
        self.active_series_id = path.series.id
        series_item = self.series_items.get(path.series.id)
        if series_item is None:
            return path

        parent = series_item.parent()
        if parent is not None:
            parent.setExpanded(True)
        self.ensure_series_quests_loaded(path.series.id)
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
            previous_blocked = self.hierarchy_tree.blockSignals(True)
            try:
                self.hierarchy_tree.setCurrentItem(quest_item)
                self.hierarchy_tree.scrollToItem(quest_item)
            finally:
                self.hierarchy_tree.blockSignals(previous_blocked)
        return path

    def focus_hierarchy_series(self, series_id: str) -> None:
        series_id = str(series_id or "")
        if series_id not in self.series_items:
            category = self._category_for_series(series_id)
            if category is not None:
                self.ensure_category_series_loaded(category.name)
        super().focus_hierarchy_series(series_id)

    def refresh_hierarchy_quest_state(self, quest_id: int) -> None:
        quest_id = int(quest_id)
        self._quest_state_cache.clear()
        if self.current_character_key and self.is_quest_done(quest_id):
            self._completed_hierarchy_quest_ids.add(quest_id)
        else:
            self._completed_hierarchy_quest_ids.discard(quest_id)
        super().refresh_hierarchy_quest_state(quest_id)

    def quest_state(self, quest: QuestRecord) -> str:
        quest_id = int(quest.id)
        cached = self._quest_state_cache.get(quest_id)
        if cached is not None:
            return cached
        state = super().quest_state(quest)
        self._quest_state_cache[quest_id] = state
        return state

    def repeatability_kind(self, quest: QuestRecord) -> str:
        quest_id = int(quest.id)
        cached = self._repeatability_cache.get(quest_id)
        if cached is not None:
            return cached
        kind = super().repeatability_kind(quest)
        self._repeatability_cache[quest_id] = kind
        return kind

    def quest_search_text(self, quest: QuestRecord) -> str:
        quest_id = int(quest.id)
        cached = self._quest_search_text_cache.get(quest_id)
        if cached is not None:
            return cached

        prebuilt = getattr(self.catalog, "_prebuilt_quest_search_text", None)
        base = str(prebuilt.get(quest_id) or "") if isinstance(prebuilt, dict) else ""
        if not base:
            values = [
                quest.search_text,
                " ".join(step.name for step in quest.steps),
                " ".join(objective.text for step in quest.steps for objective in step.objectives),
                " ".join(reward.name for reward in quest.rewards),
                " ".join(self.graph.achievement_names(quest.id)),
            ]
            base = normalize_text(" ".join(values))

        guides = (
            self.guide_provider.get_guides_for_entity("quest", quest.id)
            if self.guide_provider is not None
            else []
        )
        guide_text = normalize_text(" ".join(guide.title for guide in guides))
        text = f"{base}_{guide_text}" if base and guide_text else base or guide_text
        self._quest_search_text_cache[quest_id] = text
        return text

    def matching_quests(self):
        if (
            getattr(self.catalog, "deferred_details", False)
            and len(self.search.text().strip()) >= MIN_QUEST_SEARCH_CHARS
            and not getattr(self.catalog, "_prebuilt_quest_search_text", None)
        ):
            if self._search_worker is None:
                catalog, results = self.catalog, self._search_results

                def build():
                    try:
                        results.put((catalog.load_search_documents(), None))
                    except Exception as exc:
                        from app.constants import LOGGER
                        LOGGER.exception("Quest search index failed")
                        results.put((None, str(exc)))

                self._search_worker = Thread(target=build, name="DofusAtlasQuestSearch", daemon=True)
                try:
                    self._search_worker.start()
                except RuntimeError:
                    from app.constants import LOGGER
                    LOGGER.exception("Quest search worker could not start")
                    self._search_worker = None
                    self.status_callback("Impossible de démarrer la recherche dans les quêtes.")
                    return []
                self._search_index_timer.start()
                self.status_callback("Préparation de la recherche dans les quêtes…")
            return []
        return super().matching_quests()

    def _collect_search_index(self):
        try:
            documents, error = self._search_results.get_nowait()
        except Empty:
            return
        self._search_worker.join()
        self._search_worker = None
        self._search_index_timer.stop()
        if error is not None:
            self.status_callback(f"Recherche indisponible : {error}")
            return
        self.catalog._prebuilt_quest_search_text = documents
        self._quest_search_text_cache.clear()
        self.refresh_quests()


__all__ = ["LazyQuestsPage"]
