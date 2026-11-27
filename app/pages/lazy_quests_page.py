from __future__ import annotations

from pathlib import Path
from queue import Empty, Queue
from threading import Thread

from PySide6.QtCore import QTimer

from app.core.file_stamp import mtime_ctime_size_stamp_or_zero
from app.pages.quest_character_cache import quest_character_source_signature
from app.pages.quests_page import (
    MIN_QUEST_SEARCH_CHARS,
    QuestsPage,
)
from app.quest_catalog import QuestRecord


class LazyQuestsPage(QuestsPage):
    """Materialize the quest hierarchy only as each visible level is requested."""

    def __init__(self, *args, **kwargs) -> None:
        self._quest_state_cache: dict[int, str] = {}
        self._repeatability_cache: dict[int, str] = {}
        self._character_sources_signature: tuple[object, ...] | None = None
        self._last_quest_detail_signature: tuple[object, ...] | None = None
        self._detail_results = Queue()
        self._detail_worker = None
        self._requested_detail_id = None
        self._detail_pending = False
        self._search_worker = None
        self._search_results = Queue()
        self._navigation_suspended = False
        self._resume_detail = False
        self._resume_search = False
        super().__init__(*args, **kwargs)
        self._detail_timer = QTimer(self)
        self._detail_timer.setInterval(30)
        self._detail_timer.timeout.connect(self._collect_detail)
        self._search_index_timer = QTimer(self)
        self._search_index_timer.setInterval(30)
        self._search_index_timer.timeout.connect(self._collect_search_index)

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

    def hideEvent(self, event) -> None:
        self._navigation_suspended = True
        self._resume_detail = self._resume_detail or self._detail_pending
        self._detail_pending = False
        self._resume_search = (
            self._resume_search or self._search_worker is not None
            or self._search_debounce_timer.isActive()
        )
        self._detail_timer.stop()
        self._search_index_timer.stop()
        self._search_debounce_timer.stop()
        # Never join a catalogue worker in the UI navigation path.
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._navigation_suspended:
            return
        self._navigation_suspended = False
        if self._detail_worker is not None:
            self._detail_timer.start()
        if self._search_worker is not None:
            self._search_index_timer.start()
        resume_detail, self._resume_detail = self._resume_detail, False
        resume_search, self._resume_search = self._resume_search, False
        if resume_detail and self.selected_quest_id is not None:
            self.show_quest_detail(self.selected_quest_id)
        if resume_search and len(self.search.text().strip()) >= MIN_QUEST_SEARCH_CHARS:
            self.refresh_quests()

    def release_runtime(self) -> None:
        """Detach this UI from outstanding workers; their queues are UI-free."""
        self._navigation_suspended = True
        self._detail_pending = False
        self._resume_detail = False
        self._resume_search = False
        self._requested_detail_id = None
        self._detail_timer.stop()
        self._search_index_timer.stop()
        self._search_debounce_timer.stop()
        self._detail_results = Queue()
        self._search_results = Queue()
        self._detail_worker = None
        self._search_worker = None

    @staticmethod
    def _file_stamp(path: Path) -> tuple[int, int, int]:
        return mtime_ctime_size_stamp_or_zero(path)

    def _current_character_sources_signature(self) -> tuple[object, ...]:
        return quest_character_source_signature(
            self.profile_path,
            self.client_index_path,
            connected_only=True,
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
        self._repeatability_cache.clear()
        self._last_quest_detail_signature = None
        super().update_related_context(*args, **kwargs)

    def show_quest_detail(self, quest_id: int) -> None:
        quest_id = int(quest_id)
        self._requested_detail_id = quest_id
        if self._navigation_suspended:
            self._resume_detail = True
            return
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
            and getattr(self.quest_detail_view, "current_quest_id", None) == quest_id
        ):
            return
        QuestsPage.show_quest_detail(self, quest_id)
        if getattr(self.quest_detail_view, "current_quest_id", None) == quest_id:
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
        if self._navigation_suspended:
            return
        try:
            quest_id, error = self._detail_results.get_nowait()
        except Empty:
            return
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

    def rebuild_hierarchy(self) -> None:
        self._quest_state_cache.clear()
        super().rebuild_hierarchy()

    def refresh_hierarchy_quest_state(self, quest_id: int) -> None:
        self._quest_state_cache.clear()
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

    def matching_quests(self):
        if self._navigation_suspended:
            self._resume_search = len(self.search.text().strip()) >= MIN_QUEST_SEARCH_CHARS
            return []
        if (
            getattr(self.catalog, "deferred_details", False)
            and len(self.search.text().strip()) >= MIN_QUEST_SEARCH_CHARS
            and not isinstance(getattr(self.catalog, "_prebuilt_quest_search_text", None), dict)
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
        if self._navigation_suspended:
            return
        try:
            documents, error = self._search_results.get_nowait()
        except Empty:
            return
        self._search_worker = None
        self._search_index_timer.stop()
        active_query = len(self.search.text().strip()) >= MIN_QUEST_SEARCH_CHARS
        if error is not None:
            if active_query:
                self.status_callback(f"Recherche indisponible : {error}")
            return
        self.catalog._prebuilt_quest_search_text = documents
        self._quest_search_text_cache.clear()
        if active_query:
            self.refresh_quests()


__all__ = ["LazyQuestsPage"]
