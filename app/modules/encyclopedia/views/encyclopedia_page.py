from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Callable

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QTabWidget, QVBoxLayout, QWidget

from app.background_work import background_io_priority
from app.constants import CLIENT_INDEX_JSON, CRAFT_SELECTION_FILE, PROFILE_FILE, QUEST_PROGRESS_FILE
from app.modules.encyclopedia.constants import ACHIEVEMENTS_TAB, DEFAULT_TAB, ENCYCLOPEDIA_TABS, GUIDES_TAB, QUESTS_TAB
from app.modules.encyclopedia.providers import AchievementProvider, GuideProvider, QuestProvider
from app.modules.encyclopedia.services import (
    ACHIEVEMENT_PROGRESS_FILE,
    GUIDE_PROGRESS_FILE,
    AchievementProgressService,
    EncyclopediaService,
    GuideProgressCalculator,
    GuideProgressService,
    QuestGraphService,
    QuestProgressService,
    build_related_encyclopedia_data,
)
from app.modules.encyclopedia.views.guides_view import GuidesView
from app.modules.encyclopedia.views.achievements_view import AchievementsView
from app.modules.encyclopedia.views.encyclopedia_bootstrap_views import (
    AchievementIndexView,
    EncyclopediaWarmupView,
    GuideIndexView,
)
from app.modules.encyclopedia.views.deferred_achievement_guides_view import (
    DeferredAchievementGuidesView,
)
from app.modules.encyclopedia.views.placeholder_view import EncyclopediaPlaceholderView
from app.modules.encyclopedia.views.related_preload_state import (
    RelatedPreloadGate,
    RelatedPreloadState,
)
from app.pages.progressive_quests_page import ProgressiveQuestsPage
from app.pages.quest_character_cache import quest_character_source_signature
from app.pages.quests_page import QuestsPage
from app.quest_catalog import QuestCatalog, QuestCharacter, load_quest_characters


@dataclass(slots=True)
class _QuestRuntimePayload:
    graph: QuestGraphService


@dataclass(slots=True)
class _GuideStagePayload:
    guide_provider: object
    graph: QuestGraphService
    progress_by_guide: dict[str, tuple[int, int, str]]
    character_key: str


@dataclass(slots=True)
class _AchievementStagePayload:
    achievement_provider: object
    graph: QuestGraphService


class EncyclopediaPage(QWidget):
    def _initialize_encyclopedia_shell(
        self,
        status_callback,
        parent: QWidget | None = None,
        quest_provider: QuestProvider | None = None,
        achievement_provider: AchievementProvider | None = None,
        guide_provider: GuideProvider | None = None,
        progress_path: Path = QUEST_PROGRESS_FILE,
        achievement_progress_path: Path = ACHIEVEMENT_PROGRESS_FILE,
        guide_progress_path: Path = GUIDE_PROGRESS_FILE,
        profile_path: Path = PROFILE_FILE,
        client_index_path: Path = CLIENT_INDEX_JSON,
        owned_items: dict[int, int] | None = None,
        owned_items_path: Path = CRAFT_SELECTION_FILE,
        quest_graph: QuestGraphService | None = None,
        guide_progress_by_guide: dict[str, tuple[int, int, str]] | None = None,
        guide_progress_character_key: str = "",
        launch_travel_callback: Callable[[str], None] | None = None,
        related_data_ready_callback: Callable[[AchievementProvider, GuideProvider], None] | None = None,
        initial_tab: str = DEFAULT_TAB,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EncyclopediaPage")
        self.status_callback = status_callback
        self.quest_provider = quest_provider or QuestProvider()
        self.service = EncyclopediaService(
            quest_provider=self.quest_provider,
            achievement_provider=achievement_provider,
            guide_provider=guide_provider,
        )
        self.achievement_progress_service = AchievementProgressService(achievement_progress_path)
        self.guide_progress_service = GuideProgressService(guide_progress_path)
        self.quest_progress_path = progress_path
        self.profile_path = profile_path
        self.client_index_path = client_index_path
        self.characters: list[QuestCharacter] = []
        self.current_character_key = ""
        self._syncing_character = False
        self._initializing = True
        self._initial_tab = initial_tab if initial_tab in ENCYCLOPEDIA_TABS else DEFAULT_TAB
        self.quest_page: QuestsPage | None = None
        self.guides_view: GuidesView | None = None
        self._achievement_provider_supplied = achievement_provider is not None
        self._guide_provider_supplied = guide_provider is not None
        self._owned_items = owned_items
        self._owned_items_path = owned_items_path
        self._quest_graph = quest_graph
        if self._quest_graph is None and achievement_provider is not None and guide_provider is not None:
            self._quest_graph = QuestGraphService(
                self.quest_provider,
                guide_provider=guide_provider,
                achievement_provider=achievement_provider,
            )
        self._guide_progress_by_guide = guide_progress_by_guide or {}
        self._guide_progress_character_key = guide_progress_character_key or ""
        self._launch_travel_callback = launch_travel_callback
        self._related_data_ready_callback = related_data_ready_callback
        self._lazy_placeholders: dict[str, QWidget] = {}
        self._related_ready = all(
            value is not None
            for value in (achievement_provider, guide_provider, self._quest_graph)
        )
        self._related_preload_started = False
        self._related_preload_queue: Queue[object] = Queue(maxsize=1)
        self._related_preload_timer = QTimer(self)
        self._related_preload_timer.setInterval(60)
        self._related_preload_timer.timeout.connect(self.collect_related_preload)
        self._pending_lazy_tab = ""
        self._last_ready_tab_index = ENCYCLOPEDIA_TABS.index(DEFAULT_TAB)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self.character_label = QLabel("Personnage :")
        self.character_label.setObjectName("MutedLabel")
        self.character_label.setVisible(False)
        header.addWidget(self.character_label)
        self.character_combo = QComboBox()
        self.character_combo.setObjectName("EncyclopediaCharacterCombo")
        self.character_combo.setMinimumWidth(0)
        self.character_combo.setMaximumWidth(0)
        self.character_combo.setVisible(False)
        self.character_combo.currentIndexChanged.connect(self.on_global_character_changed)
        header.addWidget(self.character_combo)

        header.addStretch(1)
        self.search = QLineEdit()
        self.search.setObjectName("EncyclopediaSearch")
        self.search.setPlaceholderText("Recherche...")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(220)
        self.search.textChanged.connect(self.on_search_changed)
        header.addWidget(self.search, 1)
        root.addLayout(header)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("EncyclopediaTabs")
        self.tabs.tabBar().setProperty("guideActive", False)
        root.addWidget(self.tabs, 1)

        for tab_name in ENCYCLOPEDIA_TABS:
            if tab_name == QUESTS_TAB and self._initial_tab == QUESTS_TAB:
                self.tabs.addTab(self.build_quests_page(), tab_name)
            else:
                placeholder = EncyclopediaPlaceholderView()
                self._lazy_placeholders[tab_name] = placeholder
                self.tabs.addTab(placeholder, tab_name)

        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.refresh_characters()
        self.tabs.setCurrentIndex(ENCYCLOPEDIA_TABS.index(self._initial_tab))
        self.sync_tab_accent()
        self.sync_search_visibility()
        self.sync_character_to_children()
        self._initializing = False
        if self.quest_page is None:
            QTimer.singleShot(0, lambda index=self.tabs.currentIndex(): self.on_tab_changed(index))


    def _ensure_guides_view_base(self) -> GuidesView:
        if self.guides_view is None:
            self.guides_view = GuidesView(
                self.status_callback,
                provider=self.service.guide_provider,
                quest_provider=self.service.quest_provider,
                achievement_provider=self.service.achievement_provider,
                achievement_progress_service=self.achievement_progress_service,
                guide_progress_service=self.guide_progress_service,
                quest_progress_path=self.quest_progress_path,
                navigate_callback=self.navigate_to_entity,
                launch_travel_callback=self._launch_travel_callback,
                character_key=self.current_character_key,
                graph=self._quest_graph,
                initial_progress_by_guide=self._guide_progress_by_guide,
                initial_progress_character_key=self._guide_progress_character_key,
            )
            self.replace_tab_widget(GUIDES_TAB, self.guides_view)
        return self.guides_view





    def ensure_tab_loaded(self, label: str) -> QWidget:
        if label == GUIDES_TAB:
            return self.ensure_guides_view()
        if label == ACHIEVEMENTS_TAB:
            return self.ensure_achievements_view()
        if label == QUESTS_TAB and self.quest_page is None:
            page = self.build_quests_page()
            self.replace_tab_widget(QUESTS_TAB, page)
            return page
        index = self.tab_labels().index(label)
        return self.tabs.widget(index)

    def replace_tab_widget(self, label: str, widget: QWidget) -> None:
        index = self.tab_labels().index(label)
        current_label = self.current_tab_label()
        old_widget = self.tabs.widget(index)
        self.tabs.blockSignals(True)
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, widget, label)
        target_label = label if current_label == label else current_label
        if target_label in self.tab_labels():
            self.tabs.setCurrentIndex(self.tab_labels().index(target_label))
        self.tabs.blockSignals(False)
        self._lazy_placeholders.pop(label, None)
        if old_widget is not widget:
            old_widget.deleteLater()

    def apply_preloaded_related_data(
        self,
        achievement_provider: AchievementProvider | None = None,
        guide_provider: GuideProvider | None = None,
        quest_graph: QuestGraphService | None = None,
        guide_progress_by_guide: dict[str, tuple[int, int, str]] | None = None,
        guide_progress_character_key: str = "",
    ) -> None:
        if achievement_provider is not None:
            self.service.achievement_provider = achievement_provider
            self._achievement_provider_supplied = True
        if guide_provider is not None:
            self.service.guide_provider = guide_provider
            self._guide_provider_supplied = True
        if quest_graph is not None:
            self._quest_graph = quest_graph
        if guide_progress_by_guide is not None:
            self._guide_progress_by_guide = dict(guide_progress_by_guide)
            self._guide_progress_character_key = guide_progress_character_key or ""
        if self.quest_page is not None:
            self.quest_page.update_related_context(
                guide_provider=guide_provider,
                achievement_provider=achievement_provider,
                graph=quest_graph,
            )
        if achievement_provider is not None and guide_provider is not None and quest_graph is not None:
            self._related_ready = True
            self._guide_runtime_ready = True
            self._achievement_ready = bool(getattr(achievement_provider, "_loaded", False))
            if callable(self._related_data_ready_callback):
                self._related_data_ready_callback(achievement_provider, guide_provider)
            self.open_pending_lazy_tab()

    def _refresh_characters_base(self) -> None:
        previous_key = self.current_character_key
        self.characters = load_quest_characters(
            self.profile_path,
            self.client_index_path,
            connected_only=True,
        )
        self.character_combo.blockSignals(True)
        self.character_combo.clear()
        selected_index = 0
        for index, character in enumerate(self.characters):
            self.character_combo.addItem(character.label, character)
            self.character_combo.setItemData(index, character.label, Qt.ToolTipRole)
            if character.key == previous_key:
                selected_index = index
            elif not previous_key and character.connected:
                selected_index = index
        self.character_combo.setCurrentIndex(selected_index)
        self.character_combo.blockSignals(False)
        character = self.character_combo.currentData()
        self.current_character_key = (
            character.key if isinstance(character, QuestCharacter) else previous_key
        )
        self.character_combo.setToolTip(character.label if isinstance(character, QuestCharacter) else "")

    def set_character_key(self, character_key: str) -> None:
        """Synchronise le personnage global piloté par AtlasWindow."""
        target = str(character_key or "")
        target_index = -1
        for index in range(self.character_combo.count()):
            character = self.character_combo.itemData(index)
            if isinstance(character, QuestCharacter) and character.key == target:
                target_index = index
                break
        if target_index < 0:
            self.refresh_characters()
            for index in range(self.character_combo.count()):
                character = self.character_combo.itemData(index)
                if isinstance(character, QuestCharacter) and character.key == target:
                    target_index = index
                    break
        if target_index >= 0:
            self.character_combo.blockSignals(True)
            self.character_combo.setCurrentIndex(target_index)
            self.character_combo.blockSignals(False)
            character = self.character_combo.currentData()
            self.current_character_key = character.key if isinstance(character, QuestCharacter) else target
            self.character_combo.setToolTip(character.label if isinstance(character, QuestCharacter) else "")
        else:
            self.current_character_key = target
        self.sync_character_to_children()

    def on_global_character_changed(self) -> None:
        if self._syncing_character:
            return
        character = self.character_combo.currentData()
        self.current_character_key = character.key if isinstance(character, QuestCharacter) else ""
        self.character_combo.setToolTip(character.label if isinstance(character, QuestCharacter) else "")
        self.sync_character_to_children()

    def sync_character_to_children(self) -> None:
        if self._syncing_character:
            return
        self._syncing_character = True
        try:
            if self.guides_view is not None and getattr(self.guides_view, "current_character_key", None) != self.current_character_key:
                self.guides_view.set_character_key(self.current_character_key)
            if self.quest_page is not None:
                self.sync_quest_page_character()
            achievements_view = self.get_achievements_view()
            if achievements_view is not None and getattr(achievements_view, "character_key", None) != self.current_character_key:
                achievements_view.set_character_key(self.current_character_key)
        finally:
            self._syncing_character = False

    def sync_quest_page_character(self) -> None:
        if self.quest_page is None:
            return
        combo = self.quest_page.character_combo
        target_index = -1
        for index in range(combo.count()):
            character = combo.itemData(index)
            if isinstance(character, QuestCharacter) and character.key == self.current_character_key:
                target_index = index
                break
        if target_index >= 0:
            combo.blockSignals(True)
            combo.setCurrentIndex(target_index)
            combo.blockSignals(False)
        if self.quest_page.current_character_key == self.current_character_key:
            return
        self.quest_page.current_character_key = self.current_character_key
        self.quest_page.progress = self.quest_page.quest_progress_service.reload()
        self.quest_page.rebuild_hierarchy()
        self.quest_page.refresh_quests()
        self.quest_page.quest_detail_view.set_character_key(self.current_character_key)
        if self.quest_page.selected_quest_id is not None:
            self.quest_page.show_quest_detail(self.quest_page.selected_quest_id)

    def on_search_changed(self, text: str) -> None:
        widget = self.tabs.currentWidget()
        if isinstance(widget, GuidesView):
            widget.set_search_text(text)

    def _on_tab_changed_base(self, index: int) -> None:
        if index < 0:
            return
        label = self.tabs.tabText(index)
        if self._initializing:
            self._last_ready_tab_index = index
            self.sync_tab_accent(label)
            self.sync_search_visibility()
            return
        was_lazy_placeholder = isinstance(self.tabs.widget(index), EncyclopediaPlaceholderView)
        if was_lazy_placeholder and label in {GUIDES_TAB, ACHIEVEMENTS_TAB} and not self._related_ready:
            fallback = self._last_ready_tab_index
            self.tabs.blockSignals(True)
            self.tabs.setCurrentIndex(fallback)
            self.tabs.blockSignals(False)
            self.request_related_preload(label)
            self.status_callback(f"Préparation de {label} en arrière-plan...")
            return
        widget = self.ensure_tab_loaded(label)
        self._last_ready_tab_index = index
        self.sync_tab_accent(label)
        self.sync_search_visibility()
        if not was_lazy_placeholder:
            refresh = getattr(widget, "refresh_external_progress", None)
            if callable(refresh):
                refresh()
            self.sync_character_to_children()
        self.on_search_changed(self.search.text())
        self.status_callback(f"Encyclopédie : {label}")

    def sync_tab_accent(self, label: str | None = None) -> None:
        active = (label if label is not None else self.current_tab_label()) == GUIDES_TAB
        tab_bar = self.tabs.tabBar()
        if tab_bar.property("guideActive") == active:
            return
        tab_bar.setProperty("guideActive", active)
        tab_bar.style().unpolish(tab_bar)
        tab_bar.style().polish(tab_bar)
        tab_bar.update()

    def _sync_search_visibility_base(self) -> None:
        widget = self.tabs.currentWidget()
        embedded_search_active = isinstance(widget, (GuidesView, QuestsPage, AchievementsView))
        self.search.setVisible(not embedded_search_active)
        self.search.setEnabled(not embedded_search_active)
        if embedded_search_active and self.search.text():
            self.search.clear()

    def navigate_to_entity(self, entity_type: str, entity_id: int | str, **context: object) -> bool:
        entity_type = str(entity_type)
        source = str(context.get("source") or "")
        if entity_type == "guide":
            return self.navigate_to_guide(str(entity_id))
        if entity_type == "achievement":
            if source in {"relation", "quests", "achievement"}:
                return self.navigate_to_achievement_tab(int(entity_id))
            return self.navigate_to_achievement_context(int(entity_id))
        if entity_type != "quest":
            return False
        quest_id = int(entity_id)
        if self.quest_provider.get_quest(quest_id) is None:
            return False
        if source == "guide":
            guides_view = self.ensure_guides_view()
            guide_id = str(context.get("guide_id") or "")
            if guide_id and guides_view.current_guide_id != guide_id and not guides_view.select_guide(guide_id):
                return False
            return guides_view.show_quest_detail(quest_id)
        if source == "achievement":
            achievements_view = self.ensure_achievements_view()
            return achievements_view.show_quest(quest_id)
        if self.quest_page is None:
            self.ensure_tab_loaded(QUESTS_TAB)
        if self.quest_page is None:
            return False
        if self.search.text():
            self.search.clear()
        if self.quest_page.search.text():
            self.quest_page.search.clear()
        self.tabs.setCurrentIndex(ENCYCLOPEDIA_TABS.index(QUESTS_TAB))
        self.quest_page.select_quest(quest_id)
        return self.quest_page.selected_quest_id == quest_id




    def get_achievements_view(self) -> AchievementsView | None:
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, AchievementsView):
                return widget
        return None

    def tab_labels(self) -> list[str]:
        return [self.tabs.tabText(index) for index in range(self.tabs.count())]

    def current_tab_label(self) -> str:
        return self.tabs.tabText(self.tabs.currentIndex())

    def __init__(self, *args, **kwargs) -> None:
        self._guide_runtime_ready = False
        self._success_runtime_requested = False
        self._full_guide_tab_requested = False
        self._achievement_index_view: AchievementIndexView | None = None
        self._guide_index_view: GuideIndexView | None = None
        self._pending_guide_id = ""
        self._pending_achievement_id: int | None = None
        self._pending_achievement_context_id: int | None = None
        self._warmup_views: dict[str, EncyclopediaWarmupView] = {}

        self._quest_load_queue: Queue[object] = Queue(maxsize=1)
        self._quest_load_started = False
        self._achievement_load_queue: Queue[object] = Queue(maxsize=1)
        self._achievement_load_started = False
        self._achievement_ready = False
        self._catalog_context_published = False
        self._character_sources_signature: tuple[object, ...] | None = None
        self._initialize_encyclopedia_shell(*args, **kwargs)
        self._related_preload_gate = RelatedPreloadGate(ready=self._related_ready)

        self._quest_load_timer = QTimer(self)
        self._quest_load_timer.setInterval(30)
        self._quest_load_timer.timeout.connect(self._collect_quest_runtime)
        self._achievement_load_timer = QTimer(self)
        self._achievement_load_timer.setInterval(30)
        self._achievement_load_timer.timeout.connect(self._collect_achievement_runtime)

        self._achievement_ready = bool(
            self._achievement_provider_supplied
            and getattr(self.service.achievement_provider, "_loaded", False)
            and self._quest_graph is not None
        )

        if self.current_tab_label() == GUIDES_TAB and self.guides_view is None:
            self._show_warmup(GUIDES_TAB)
        self._guide_runtime_ready = bool(self._related_ready or self.guides_view is not None)
        self._stabilize_header_geometry()

    @property
    def related_preload_state(self) -> RelatedPreloadState:
        return self._related_preload_gate.state

    def _current_character_sources_signature(self) -> tuple[object, ...]:
        return quest_character_source_signature(
            self.profile_path,
            self.client_index_path,
        )

    def refresh_characters(self) -> None:
        signature = self._current_character_sources_signature()
        if signature == self._character_sources_signature and getattr(self, "characters", None):
            return
        EncyclopediaPage._refresh_characters_base(self)
        self._character_sources_signature = self._current_character_sources_signature()

    @staticmethod
    def _guide_progress_state(completed: int, total: int) -> str:
        if total and completed >= total:
            return "Terminé"
        if completed > 0:
            return "En cours"
        return "Non commencé"

    @classmethod
    def _build_guide_progress_snapshot(
        cls,
        catalog: QuestCatalog,
        guide_provider,
        character_key: str,
        quest_progress_path,
        guide_progress_path,
        achievement_progress_path,
    ) -> dict[str, tuple[int, int, str]]:
        calculator = GuideProgressCalculator(
            QuestProgressService(quest_progress_path),
            GuideProgressService(guide_progress_path),
            AchievementProgressService(achievement_progress_path),
            catalog.by_id,
        )
        result: dict[str, tuple[int, int, str]] = {}
        for guide in guide_provider.load_all():
            progress = calculator.guide_progress(guide, character_key)
            result[guide.id] = (
                progress.completed,
                progress.total,
                cls._guide_progress_state(progress.completed, progress.total),
            )
        return result

    def _build_quests_page_progressive(self) -> ProgressiveQuestsPage:
        lightweight_graph = self._quest_graph or QuestGraphService(self.quest_provider)
        page = ProgressiveQuestsPage(
            self.status_callback,
            catalog=self.quest_provider.get_catalog(),
            quest_provider=self.quest_provider,
            progress_path=self.quest_progress_path,
            profile_path=self.profile_path,
            client_index_path=self.client_index_path,
            owned_items=self._owned_items,
            owned_items_path=self._owned_items_path,
            guide_provider=self.service.guide_provider if self._guide_provider_supplied else None,
            achievement_provider=self.service.achievement_provider if self._achievement_provider_supplied else None,
            achievement_progress_service=self.achievement_progress_service,
            graph=lightweight_graph,
            navigate_callback=self.navigate_to_entity,
        )
        page.character_combo.setVisible(False)
        page.character_combo.setFixedWidth(0)
        self.quest_page = page
        return page

    def _promote_guides_runtime_context(self, view) -> None:
        graph = getattr(view, "graph", None)
        if graph is None:
            return
        self._quest_graph = graph
        self._guide_provider_supplied = True
        self._achievement_provider_supplied = True
        self._related_ready = True
        self._related_preload_started = False
        gate = getattr(self, "_related_preload_gate", None)
        if gate is not None:
            gate.mark_ready()

    def _ensure_guides_view_progressive(self):
        view = self._ensure_guides_view_base()
        self._promote_guides_runtime_context(view)
        return view

    def _on_tab_changed_progressive(self, index: int) -> None:
        if index < 0:
            return
        label = self.tabs.tabText(index)
        if self._initializing or label != GUIDES_TAB:
            self._on_tab_changed_base(index)
            return

        widget = self.ensure_guides_view()
        guide_index = self.tab_labels().index(GUIDES_TAB)
        self._last_ready_tab_index = guide_index
        self.sync_tab_accent(GUIDES_TAB)
        self.sync_search_visibility()
        refresh = getattr(widget, "refresh_external_progress", None)
        if callable(refresh):
            refresh()
        self.sync_character_to_children()
        self.on_search_changed(self.search.text())
        self.status_callback(f"Encyclopédie : {GUIDES_TAB}")

    def build_quests_page(self):
        # The public Encyclopedia shell may be created before any Doduda catalogue
        # exists. Never make the Qt constructor parse it synchronously.
        if getattr(self.quest_provider, "_catalog", None) is None:
            return EncyclopediaWarmupView(QUESTS_TAB)
        return self._build_quests_page_progressive()

    def _show_guide_index(self) -> GuideIndexView:
        current = self.tabs.widget(self.tab_labels().index(GUIDES_TAB))
        if isinstance(current, GuideIndexView):
            self._guide_index_view = current
            return current
        view = GuideIndexView()
        view.guideRequested.connect(self._on_guide_requested)
        self._guide_index_view = view
        self.replace_tab_widget(GUIDES_TAB, view)
        return view

    def _show_achievement_index(self) -> AchievementIndexView:
        index = self.tab_labels().index(ACHIEVEMENTS_TAB)
        current = self.tabs.widget(index)
        if isinstance(current, AchievementIndexView):
            self._achievement_index_view = current
            return current
        view = AchievementIndexView(data_dir=self.service.achievement_provider.data_dir)
        view.achievementRequested.connect(self._on_achievement_requested)
        self._achievement_index_view = view
        self.replace_tab_widget(ACHIEVEMENTS_TAB, view)
        return view

    def _on_achievement_requested(self, achievement_id: int) -> None:
        self._pending_achievement_id = int(achievement_id)
        self._pending_lazy_tab = ACHIEVEMENTS_TAB
        if self._achievement_index_view is not None:
            self._achievement_index_view.set_loading(int(achievement_id))
        if self._achievement_ready or self._related_ready:
            self.open_pending_lazy_tab()
            return
        self.request_achievement_runtime()

    def _show_warmup(self, label: str) -> EncyclopediaWarmupView:
        index = self.tab_labels().index(label)
        current = self.tabs.widget(index)
        if isinstance(current, EncyclopediaWarmupView):
            self._warmup_views[label] = current
            return current
        view = EncyclopediaWarmupView(label)
        self._warmup_views[label] = view
        self.replace_tab_widget(label, view)
        return view

    def _publish_catalog_context(self, achievement_provider=None, guide_provider=None) -> None:
        callback = self._related_data_ready_callback
        if not callable(callback):
            return
        if achievement_provider is None:
            achievement_provider = self.service.achievement_provider
        # The callback accepts an optional Guide provider at runtime; None is
        # deliberate until Guide has genuinely been requested.
        callback(achievement_provider, guide_provider)
        self._catalog_context_published = True

    def request_quest_runtime(self) -> None:
        if self.quest_page is not None:
            return
        if self._quest_load_started:
            return
        self._quest_load_started = True
        provider = self.quest_provider
        results = self._quest_load_queue

        def worker() -> None:
            with background_io_priority():
                try:
                    provider.get_catalog()
                    graph = QuestGraphService(provider)
                    result: object = _QuestRuntimePayload(graph)
                except Exception as exc:
                    result = exc
                results.put(result)

        Thread(target=worker, name="DofusAtlasQuestIndex", daemon=True).start()
        self._quest_load_timer.start()

    def _collect_quest_runtime(self) -> None:
        try:
            result = self._quest_load_queue.get_nowait()
        except Empty:
            return
        self._quest_load_timer.stop()
        self._quest_load_started = False
        if isinstance(result, Exception):
            self.status_callback(f"Chargement Quêtes impossible : {result}")
            return
        if not isinstance(result, _QuestRuntimePayload):
            return

        self._quest_graph = result.graph
        if self.quest_page is None:
            page = self._build_quests_page_progressive()
            self.replace_tab_widget(QUESTS_TAB, page)
        if not self._catalog_context_published:
            self._publish_catalog_context(self.service.achievement_provider, None)
        if self.current_tab_label() == QUESTS_TAB:
            self._activate_loaded_tab(QUESTS_TAB)

    def ensure_achievements_view(self) -> AchievementsView:
        view = self.get_achievements_view()
        if isinstance(view, AchievementsView):
            return view
        guide_provider = self.service.guide_provider if self._guide_provider_supplied else None
        view = AchievementsView(
            self.status_callback,
            provider=self.service.achievement_provider,
            progress_service=self.achievement_progress_service,
            character_key=self.current_character_key,
            navigate_callback=self.navigate_to_entity,
            quest_provider=self.quest_provider,
            guide_provider=guide_provider,
            quest_graph=self._quest_graph,
            quest_progress_service=QuestProgressService(self.quest_progress_path),
        )
        self.replace_tab_widget(ACHIEVEMENTS_TAB, view)
        return view

    def _on_guide_requested(self, guide_id: str) -> None:
        guide_id = str(guide_id or "").strip()
        if not guide_id:
            return
        self._pending_guide_id = guide_id
        if self._guide_index_view is not None:
            self._guide_index_view.set_loading(guide_id)
        if self._related_ready:
            self._finish_pending_guide_request()
            return
        self.request_related_preload(GUIDES_TAB)

    def _finish_pending_guide_request(self) -> bool:
        guide_id = str(self._pending_guide_id or "")
        if not guide_id or not self._related_ready:
            return False
        view = self._ensure_guides_view_progressive()
        self._guide_index_view = None
        self._pending_guide_id = ""
        if GUIDES_TAB in self.tab_labels():
            self.tabs.setCurrentIndex(self.tab_labels().index(GUIDES_TAB))
        return bool(view.select_guide(guide_id))


    def _activate_loaded_tab(self, label: str) -> None:
        widget = self.tabs.widget(self.tab_labels().index(label))
        if label == QUESTS_TAB and self.quest_page is not None:
            widget = self.quest_page
        elif label == GUIDES_TAB and self.guides_view is not None:
            widget = self.guides_view
        elif label == ACHIEVEMENTS_TAB and self._achievement_ready:
            widget = self.ensure_achievements_view()
        self._last_ready_tab_index = self.tab_labels().index(label)
        self.sync_tab_accent(label)
        self.sync_search_visibility()
        refresh = getattr(widget, "refresh_external_progress", None)
        if callable(refresh):
            refresh()
        self.sync_character_to_children()
        self.on_search_changed(self.search.text())
        self.status_callback(f"Encyclopédie : {label}")

    def _on_tab_changed_indexed(self, index: int) -> None:
        if index < 0:
            return
        label = self.tabs.tabText(index)
        if self._initializing:
            self._last_ready_tab_index = index
            self.sync_tab_accent(label)
            self.sync_search_visibility()
            return

        if (
            label == ACHIEVEMENTS_TAB
            and not self._achievement_ready
            and not self._related_ready
        ):
            self._show_achievement_index()
            self._last_ready_tab_index = self.tab_labels().index(ACHIEVEMENTS_TAB)
            self.sync_tab_accent(ACHIEVEMENTS_TAB)
            self.sync_search_visibility()
            self.status_callback(f"Encyclopédie : {ACHIEVEMENTS_TAB}")
            return

        if label == GUIDES_TAB:
            if self.guides_view is not None:
                self._activate_loaded_tab(GUIDES_TAB)
                return
            if self._related_ready:
                self._activate_loaded_tab(GUIDES_TAB)
                return
            self._show_guide_index()
            self._last_ready_tab_index = self.tab_labels().index(GUIDES_TAB)
            self.sync_tab_accent(GUIDES_TAB)
            self.sync_search_visibility()
            self.status_callback(f"Encyclopédie : {GUIDES_TAB}")
            return

        if label == ACHIEVEMENTS_TAB:
            if isinstance(self.tabs.widget(index), AchievementsView):
                self._activate_loaded_tab(ACHIEVEMENTS_TAB)
                return
            if self._achievement_ready or self._related_ready:
                self.open_pending_lazy_tab()
                self._activate_loaded_tab(ACHIEVEMENTS_TAB)
                return
            self._show_warmup(ACHIEVEMENTS_TAB)
            self._last_ready_tab_index = self.tab_labels().index(ACHIEVEMENTS_TAB)
            self.sync_tab_accent(ACHIEVEMENTS_TAB)
            self.sync_search_visibility()
            self.status_callback(f"Encyclopédie : {ACHIEVEMENTS_TAB}")
            self.request_achievement_runtime()
            return

        if label == QUESTS_TAB:
            if self.quest_page is not None:
                self._activate_loaded_tab(QUESTS_TAB)
                return
            self._show_warmup(QUESTS_TAB)
            self._last_ready_tab_index = self.tab_labels().index(QUESTS_TAB)
            self.sync_tab_accent(QUESTS_TAB)
            self.sync_search_visibility()
            self.status_callback(f"Encyclopédie : {QUESTS_TAB}")
            self.request_quest_runtime()
            return

        self._on_tab_changed_progressive(index)

    def _sync_search_visibility_indexed(self) -> None:
        widget = self.tabs.currentWidget()
        if isinstance(widget, (AchievementIndexView, GuideIndexView, EncyclopediaWarmupView)):
            self.search.setVisible(False)
            self.search.setEnabled(False)
            return
        self._sync_search_visibility_base()




    def _on_tab_changed_indexed_runtime(self, index: int) -> None:
        if index < 0:
            return
        label = self.tabs.tabText(index)
        if self._initializing:
            self._on_tab_changed_indexed(index)
            return
        if label == GUIDES_TAB:
            if self.guides_view is not None:
                self._activate_loaded_tab(GUIDES_TAB)
                return
            if self._related_ready:
                self._pending_lazy_tab = GUIDES_TAB
                self.open_pending_lazy_tab()
                return
            self._start_full_guide_runtime()
            return
        if label == ACHIEVEMENTS_TAB:
            if self._achievement_ready or self._related_ready:
                self._pending_lazy_tab = ACHIEVEMENTS_TAB
                self.open_pending_lazy_tab()
                return
            self._start_full_achievement_runtime()
            return
        self._on_tab_changed_indexed(index)

    def _stabilize_header_geometry(self) -> None:
        root = self.layout()
        if root is None:
            return
        root.setSpacing(max(9, root.spacing()))
        first = root.itemAt(0)
        header = first.layout() if first is not None else None
        if header is not None:
            header.setContentsMargins(0, 0, 0, 3)

    def sync_search_visibility(self) -> None:
        widget = self.tabs.currentWidget() if hasattr(self, "tabs") else None
        if isinstance(widget, EncyclopediaWarmupView):
            # Keeping the row alive avoids the tab/search geometry jump that made
            # the search field appear to sit on the tab bar during lazy swaps.
            self.search.setVisible(True)
            self.search.setEnabled(False)
            self.search.setPlaceholderText("Chargement en cours…")
            return
        if hasattr(self, "search"):
            self.search.setPlaceholderText("Recherche...")
        self._sync_search_visibility_indexed()

    def _start_full_guide_runtime(self) -> None:
        """Keep Guide interactive while its rich provider finishes in background."""

        self._full_guide_tab_requested = True
        self._pending_lazy_tab = GUIDES_TAB
        self._show_guide_index()
        index = self.tab_labels().index(GUIDES_TAB)
        self._last_ready_tab_index = index
        self.sync_tab_accent(GUIDES_TAB)
        self.sync_search_visibility()
        self.status_callback("Guide disponible · enrichissement en arrière-plan...")
        self.request_related_preload(GUIDES_TAB)

    def _start_full_achievement_runtime(self) -> None:
        """Show the lightweight Success index instead of a blocking-looking spinner."""

        self._pending_lazy_tab = ACHIEVEMENTS_TAB
        self._show_achievement_index()
        index = self.tab_labels().index(ACHIEVEMENTS_TAB)
        self._last_ready_tab_index = index
        self.sync_tab_accent(ACHIEVEMENTS_TAB)
        self.sync_search_visibility()
        self.status_callback("Succès disponibles · détails en arrière-plan...")
        self.request_achievement_runtime()

    def request_related_preload(self, target_tab: str = "") -> None:
        if target_tab:
            self._pending_lazy_tab = str(target_tab)
        if self._guide_runtime_ready:
            self.open_pending_lazy_tab()
            return
        if self._related_preload_started:
            return
        # If Successes are already reading the shared achievement source, let
        # that single reader finish first rather than competing on the same JSONs.
        if self._achievement_load_started and not self._achievement_ready:
            return
        if not self._related_preload_gate.begin():
            return

        self._related_preload_started = True
        quest_provider = self.quest_provider
        guide_provider = self.service.guide_provider
        achievement_provider = self.service.achievement_provider
        results = self._related_preload_queue
        character_key = str(self.current_character_key or "")
        quest_progress_path = self.quest_progress_path
        guide_progress_path = self.guide_progress_service.path
        achievement_progress_path = self.achievement_progress_service.path

        def worker() -> None:
            with background_io_priority():
                try:
                    catalog = quest_provider.get_catalog()
                    # IndexedGuideProvider resolves achievement link labels without
                    # forcing the rich AchievementProvider to materialize here.
                    guide_provider.load_all()
                    graph = QuestGraphService(
                        quest_provider,
                        guide_provider=guide_provider,
                        achievement_provider=achievement_provider,
                    )
                    try:
                        progress = self._build_guide_progress_snapshot(
                            catalog,
                            guide_provider,
                            character_key,
                            quest_progress_path,
                            guide_progress_path,
                            achievement_progress_path,
                        )
                    except Exception:
                        progress = {}
                    result: object = _GuideStagePayload(
                        guide_provider,
                        graph,
                        progress,
                        character_key,
                    )
                except Exception as exc:
                    result = exc
                results.put(result)

        try:
            Thread(target=worker, name="DofusAtlasGuideStage", daemon=True).start()
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            self._related_preload_started = False
            self._related_preload_gate.mark_failed()
            self.status_callback(f"Chargement Guide impossible : {exc}")
            return
        self._related_preload_timer.start()

    def collect_related_preload(self) -> None:
        try:
            result = self._related_preload_queue.get_nowait()
        except Empty:
            return
        self._related_preload_timer.stop()
        self._related_preload_started = False

        if isinstance(result, Exception):
            self._related_preload_gate.mark_failed()
            self.status_callback(f"Chargement Guide impossible : {result}")
            # Keep a useful lightweight catalogue instead of a permanent spinner.
            self._show_guide_index()
            self.sync_search_visibility()
            return
        if not isinstance(result, _GuideStagePayload):
            return

        self.service.guide_provider = result.guide_provider
        self._guide_provider_supplied = True
        self._quest_graph = result.graph
        self._guide_progress_by_guide = dict(result.progress_by_guide)
        self._guide_progress_character_key = result.character_key
        self._guide_runtime_ready = True

        # AtlasWindow historically uses _related_ready as the Guide navigation
        # readiness flag. Keep that compatibility contract while _achievement_ready
        # remains the authoritative signal for the richer Success runtime.
        self._related_ready = True
        self._related_preload_gate.mark_ready()

        if self.quest_page is not None:
            self.quest_page.update_related_context(
                guide_provider=result.guide_provider,
                graph=result.graph,
            )

        achievements_view = self.get_achievements_view()
        if achievements_view is not None:
            achievements_view.guide_provider = result.guide_provider
            achievements_view.quest_graph = result.graph

        if self._achievement_ready:
            self._complete_related_context()

        # Guide catalogue is now fully usable. Rich Success data remains cold
        # until the user opens Successes, a guide detail, or an achievement link.
        self.open_pending_lazy_tab()

    def request_achievement_runtime(self) -> None:
        self._start_achievement_stage(open_success=True)

    def request_achievement_warmup(self) -> None:
        self._start_achievement_stage(open_success=False)

    def _start_achievement_stage(self, *, open_success: bool) -> None:
        if open_success:
            self._success_runtime_requested = True
            self._pending_lazy_tab = ACHIEVEMENTS_TAB
        if self._achievement_ready:
            self._complete_related_context()
            if open_success:
                self.open_pending_lazy_tab()
            return
        if self._achievement_load_started:
            return

        self._achievement_load_started = True
        quest_provider = self.quest_provider
        achievement_provider = self.service.achievement_provider
        results = self._achievement_load_queue
        existing_graph = self._quest_graph

        def worker() -> None:
            with background_io_priority():
                try:
                    quest_provider.get_catalog()
                    achievement_provider.load_all()
                    graph = existing_graph or QuestGraphService(
                        quest_provider,
                        achievement_provider=achievement_provider,
                    )
                    result: object = _AchievementStagePayload(
                        achievement_provider,
                        graph,
                    )
                except Exception as exc:
                    result = exc
                results.put(result)

        try:
            Thread(target=worker, name="DofusAtlasAchievementStage", daemon=True).start()
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            self._achievement_load_started = False
            self.status_callback(f"Chargement Succès impossible : {exc}")
            return
        self._achievement_load_timer.start()

    def _collect_achievement_runtime(self) -> None:
        try:
            result = self._achievement_load_queue.get_nowait()
        except Empty:
            return
        self._achievement_load_timer.stop()
        self._achievement_load_started = False

        if isinstance(result, Exception):
            requested = self._success_runtime_requested
            self._success_runtime_requested = False
            if requested:
                self.status_callback(f"Chargement Succès impossible : {result}")
                self._show_achievement_index()
                self.sync_search_visibility()
            if self._full_guide_tab_requested and not self._guide_runtime_ready:
                self.request_related_preload("")
            return
        if not isinstance(result, _AchievementStagePayload):
            return

        self.service.achievement_provider = result.achievement_provider
        self._achievement_provider_supplied = True
        self._achievement_ready = True
        self._quest_graph = result.graph
        # A quest-only graph may have been reused; promote the now-hot provider.
        self._quest_graph.achievement_provider = result.achievement_provider

        if self.quest_page is not None:
            self.quest_page.update_related_context(
                achievement_provider=result.achievement_provider,
                graph=result.graph,
            )

        if self._guide_runtime_ready:
            self._complete_related_context()
            view = self.guides_view
            apply_runtime = getattr(view, "apply_achievement_runtime", None)
            if callable(apply_runtime):
                apply_runtime()
        else:
            self._publish_catalog_context(result.achievement_provider, None)

        if self._full_guide_tab_requested and not self._guide_runtime_ready:
            # Build Guides after the already-running Success reader, but do not
            # overwrite whichever tab the user most recently requested.
            self.request_related_preload("")

        if self._pending_achievement_context_id is not None and self._guide_runtime_ready:
            self._pending_lazy_tab = GUIDES_TAB
            self.open_pending_lazy_tab()

        if self._success_runtime_requested:
            self._success_runtime_requested = False
            self._pending_lazy_tab = ACHIEVEMENTS_TAB
            self.open_pending_lazy_tab()

    def _complete_related_context(self) -> None:
        if not (self._guide_runtime_ready and self._achievement_ready):
            return
        self._related_ready = True
        self._related_preload_gate.mark_ready()
        graph = self._quest_graph
        if graph is None:
            return
        graph.guide_provider = self.service.guide_provider
        graph.achievement_provider = self.service.achievement_provider

        if self.quest_page is not None:
            self.quest_page.update_related_context(
                guide_provider=self.service.guide_provider,
                achievement_provider=self.service.achievement_provider,
                graph=graph,
            )
        achievements_view = self.get_achievements_view()
        if achievements_view is not None:
            achievements_view.guide_provider = self.service.guide_provider
            achievements_view.quest_graph = graph
            detail = getattr(achievements_view, "quest_detail_view", None)
            update = getattr(detail, "update_related_context", None)
            if callable(update):
                update(
                    guide_provider=self.service.guide_provider,
                    achievement_provider=self.service.achievement_provider,
                    graph=graph,
                )
        self._publish_catalog_context(
            self.service.achievement_provider,
            self.service.guide_provider,
        )

    def ensure_guides_view(self) -> DeferredAchievementGuidesView:
        if self.guides_view is None:
            self.guides_view = DeferredAchievementGuidesView(
                self.status_callback,
                provider=self.service.guide_provider,
                quest_provider=self.service.quest_provider,
                achievement_provider=self.service.achievement_provider,
                achievement_progress_service=self.achievement_progress_service,
                guide_progress_service=self.guide_progress_service,
                quest_progress_path=self.quest_progress_path,
                navigate_callback=self.navigate_to_entity,
                launch_travel_callback=self._launch_travel_callback,
                character_key=self.current_character_key,
                graph=self._quest_graph,
                initial_progress_by_guide=self._guide_progress_by_guide,
                initial_progress_character_key=self._guide_progress_character_key,
            )
            self.guides_view.achievementRuntimeRequested.connect(
                self.request_achievement_warmup
            )
            self.replace_tab_widget(GUIDES_TAB, self.guides_view)
        return self.guides_view

    def open_pending_lazy_tab(self) -> None:
        label = str(self._pending_lazy_tab or "")
        if not label or label not in self.tab_labels():
            return
        if label == GUIDES_TAB and not self._guide_runtime_ready:
            return
        if label == ACHIEVEMENTS_TAB and not self._achievement_ready:
            return
        if label == QUESTS_TAB and self.quest_page is None:
            return

        self._pending_lazy_tab = ""
        if label == GUIDES_TAB:
            view = self.ensure_guides_view()
            self._guide_index_view = None
            if self._pending_guide_id:
                guide_id = self._pending_guide_id
                self._pending_guide_id = ""
                view.select_guide(guide_id)
            if (
                self._pending_achievement_context_id is not None
                and self._achievement_ready
            ):
                achievement_id = self._pending_achievement_context_id
                self._pending_achievement_context_id = None
                view.open_achievement_context(achievement_id)
        elif label == ACHIEVEMENTS_TAB:
            view = self.ensure_achievements_view()
            if self._pending_achievement_id is not None:
                achievement_id = self._pending_achievement_id
                self._pending_achievement_id = None
                view.show_achievement(achievement_id)
        elif label != QUESTS_TAB:
            self.ensure_tab_loaded(label)

        self.tabs.setCurrentIndex(self.tab_labels().index(label))
        self._last_ready_tab_index = self.tabs.currentIndex()
        self.sync_tab_accent(label)
        self.sync_search_visibility()
        self.sync_character_to_children()
        self.status_callback(f"Encyclopédie : {label}")

    def on_tab_changed(self, index: int) -> None:
        if index < 0:
            return
        label = self.tabs.tabText(index)
        if self._initializing:
            self._on_tab_changed_indexed_runtime(index)
            return
        if label == GUIDES_TAB:
            if self.guides_view is not None:
                self._activate_loaded_tab(GUIDES_TAB)
                return
            if self._guide_runtime_ready:
                self._pending_lazy_tab = GUIDES_TAB
                self.open_pending_lazy_tab()
                return
            self._start_full_guide_runtime()
            return
        if label == ACHIEVEMENTS_TAB:
            if self._achievement_ready:
                self._pending_lazy_tab = ACHIEVEMENTS_TAB
                self.open_pending_lazy_tab()
                return
            self._start_full_achievement_runtime()
            return
        self._on_tab_changed_indexed_runtime(index)

    def navigate_to_guide(self, guide_id: str) -> bool:
        guide_id = str(guide_id or "").strip()
        if not guide_id:
            return False
        self._pending_guide_id = guide_id
        self._pending_lazy_tab = GUIDES_TAB
        self.tabs.setCurrentIndex(self.tab_labels().index(GUIDES_TAB))
        if self._guide_runtime_ready:
            self.open_pending_lazy_tab()
        else:
            self._start_full_guide_runtime()
        return True

    def navigate_to_achievement_tab(self, achievement_id: int) -> bool:
        self._pending_achievement_id = int(achievement_id)
        self._pending_lazy_tab = ACHIEVEMENTS_TAB
        self.tabs.setCurrentIndex(self.tab_labels().index(ACHIEVEMENTS_TAB))
        if self._achievement_ready:
            self.open_pending_lazy_tab()
        else:
            self._start_full_achievement_runtime()
        return True

    def navigate_to_achievement_context(self, achievement_id: int) -> bool:
        self._pending_achievement_context_id = int(achievement_id)
        self._pending_lazy_tab = GUIDES_TAB
        self.tabs.setCurrentIndex(self.tab_labels().index(GUIDES_TAB))
        if not self._guide_runtime_ready:
            self._start_full_guide_runtime()
        else:
            self.open_pending_lazy_tab()
        if not self._achievement_ready:
            self.request_achievement_warmup()
        return True
