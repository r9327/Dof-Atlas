from __future__ import annotations

import re
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtCore import QModelIndex, Qt, QUrl
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QSizePolicy,
    QSpinBox,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.constants import CLIENT_INDEX_JSON, CRAFT_SELECTION_FILE, PROFILE_FILE, QUEST_PROGRESS_FILE
from app.core.character_identity import is_character_key
from app.core.map_coordinates import (
    DOCUMENTARY_POSITION_RE, normalize_coordinate_pair, quest_launch_instruction, travel_command_from_link,
)
from app.core.numbers import format_grouped_int
from app.core.json_store import InvalidPersistentJsonError
from app.core.file_stamp import mtime_ctime_size_stamp
from app.pages.quest_character_cache import cached_load_quest_characters as load_quest_characters
from app.core.craft_selection import (
    selection_item_id as owned_item_identifier, selection_quantities,
    persist_selection_quantity,
)
from app.modules.encyclopedia.providers import AchievementProvider, QuestProvider
from app.modules.encyclopedia.services import (
    QuestGraphService,
    QuestHierarchyPath,
    QuestHierarchyService,
    QuestProgressService,
)
from app.modules.encyclopedia.services.quest_search_text import quest_repeatability_text, quest_context_search_text
from app.modules.encyclopedia.services.lazy_progress_service import (
    ACHIEVEMENT_PROGRESS_FILE,
    lazy_achievement_progress_service,
)
from app.modules.encyclopedia.widgets.dashboard import (
    CollapsedColumnRail,
    EncyclopediaPanel,
    FixedColumnSplitter,
    HideCompletedButton,
)
from app.modules.encyclopedia.widgets.detail_panel import DetailPanel
from app.modules.encyclopedia.widgets.quest_widgets import QUEST_ID_ROLE, QuestListModel
from app.quest_catalog import (
    QuestCatalog,
    QuestCharacter,
    QuestRecord,
    normalize_text,
)
from app.storage import IconCache, read_json
from app.ui.components import (
    AtlasBreadcrumb, AtlasButton, AtlasComboBox, clear_unity_widget_layout,
    configure_unity_number_spinbox, restore_unity_number_value, configure_unity_tool_button,
    populate_character_combo, select_character_combo_key,
)
from app.ui.theme import PALETTE, render_theme_template
from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX, UNITY_SPACING_PX


QUEST_GEOMETRY = UNITY_MODULE_GEOMETRY_PX["quests"]

if TYPE_CHECKING:
    from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView


_QUEST_VM = None


def _quest_vm():
    global _QUEST_VM
    if _QUEST_VM is None:
        from app.modules.encyclopedia.services import guide_quest_view_model

        _QUEST_VM = guide_quest_view_model
    return _QUEST_VM


def clean_requirement_line(*args, **kwargs):
    return _quest_vm().clean_requirement_line(*args, **kwargs)


def _display_item(*args, **kwargs):
    return _quest_vm().DisplayItem(*args, **kwargs)


def _quest_item_row(*args, **kwargs):
    from app.modules.encyclopedia.widgets.quest_item_row import item_row

    return item_row(*args, **kwargs)


QUEST_PANEL_ITEM_OBJECTIVE_TYPES = {2, 3, 17}
KEY_LAST_SELECTED_QUEST_ID = "encyclopedia_last_quest_id"
MIN_QUEST_SEARCH_CHARS = 5
QUEST_HIERARCHY_OPEN_WIDTH = QUEST_GEOMETRY["hierarchy_open_width"]
QUEST_HIERARCHY_COLLAPSED_WIDTH = QUEST_GEOMETRY["hierarchy_collapsed_width"]
HIERARCHY_KIND_ROLE = Qt.UserRole + 101
HIERARCHY_ID_ROLE = Qt.UserRole + 102


class NativeQuestDetailPanel(DetailPanel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._html = ""
        self._lazy_payload = None

    def set_lazy_payload(self, payload) -> None:
        self._html = ""
        self._lazy_payload = payload

    def set_compat_html(self, html: str) -> None:
        self._lazy_payload = None
        self._html = html

    def toHtml(self) -> str:
        """Legacy HTML is computed only by a caller that explicitly needs it."""
        if self._lazy_payload is not None:
            quest, done, owned, guides, achievements, state = self._lazy_payload
            self._html = quest_detail_html(
                quest, done, owned, related_guides=guides,
                related_achievements=achievements, achievement_state=state,
            )
            self._lazy_payload = None
        return self._html

    def openLinks(self) -> bool:
        return False


class QuestListFacade(QListView):
    def __init__(self, page: "QuestsPage", parent=None) -> None:
        super().__init__(parent)
        self.page = page
        self.setObjectName("QuestResultList")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setUniformItemSizes(False)
        self.clicked.connect(self._on_clicked)

    def count(self) -> int:
        return self.model().rowCount() if self.model() is not None else 0

    def item(self, row: int):
        if self.model() is None:
            return None
        index = self.model().index(row, 0)
        if not index.isValid():
            return None
        return QuestFacadeItem(self.page, index.data(QUEST_ID_ROLE), index.data())

    def setCurrentItem(self, item) -> None:
        if item is None:
            return
        self.page.select_quest_from_search(int(item.quest_id))

    def _on_clicked(self, index: QModelIndex) -> None:
        quest_id = index.data(QUEST_ID_ROLE)
        if quest_id is not None:
            self.page.select_quest_from_search(int(quest_id))


class QuestFacadeItem:
    def __init__(self, page: "QuestsPage", quest_id: int, text: str) -> None:
        self.page = page
        self.quest_id = int(quest_id)
        self._text = text

    def text(self) -> str:
        return self._text

    def data(self, role: int):
        if role == Qt.UserRole:
            return self.quest_id
        return None

    def setCheckState(self, state: Qt.CheckState) -> None:
        self.page.set_quest_checked(self.quest_id, state == Qt.Checked)

    def checkState(self) -> Qt.CheckState:
        return Qt.Checked if self.page.is_quest_done(self.quest_id) else Qt.Unchecked


class QuestsPage(QWidget):
    MODES = ("PARCOURS", "DOFUS", "SUCCÈS LIÉS", "ZONES", "TOUTES")

    def __init__(
        self,
        status_callback,
        parent: QWidget | None = None,
        catalog: QuestCatalog | None = None,
        quest_provider: QuestProvider | None = None,
        progress_path: Path = QUEST_PROGRESS_FILE,
        profile_path: Path = PROFILE_FILE,
        client_index_path: Path = CLIENT_INDEX_JSON,
        owned_items: dict[int, int] | None = None,
        owned_items_path: Path = CRAFT_SELECTION_FILE,
        guide_provider: Any = None,
        achievement_provider: AchievementProvider | None = None,
        achievement_progress_service: Any = None,
        achievement_progress_path: Path = ACHIEVEMENT_PROGRESS_FILE,
        graph: QuestGraphService | None = None,
        navigate_callback: Callable[[str, int | str], bool] | None = None,
        defer_detail_view: bool = False,
    ):
        super().__init__(parent)
        self.setObjectName("QuestsPage")
        self.status_callback = status_callback
        self.progress_path = progress_path
        self.profile_path = profile_path
        self.client_index_path = client_index_path
        self.owned_items_path = owned_items_path
        self.guide_provider = guide_provider
        self.achievement_provider = achievement_provider
        self.achievement_progress_service = (
            achievement_progress_service
            or lazy_achievement_progress_service(achievement_progress_path)
        )
        self.navigate_callback = navigate_callback
        self._defer_detail_view = bool(defer_detail_view)
        self.quest_detail_view: QuestDetailView | None = None
        self._quest_detail_placeholder: QWidget | None = None
        if quest_provider is not None:
            self.quest_provider = quest_provider
            self.catalog = quest_provider.get_catalog()
        else:
            self.catalog = catalog if catalog is not None else QuestCatalog.load()
            self.quest_provider = QuestProvider(catalog=self.catalog)
        self.graph = graph or QuestGraphService(self.quest_provider, guide_provider, achievement_provider)
        self.quest_progress_service = QuestProgressService(progress_path)
        self.progress = self.quest_progress_service.progress
        self.owned_items = normalize_owned_items(owned_items)
        self._owned_items_file_signature: tuple[int, int, int] | None = None
        self.characters: list[QuestCharacter] = []
        self.current_character_key = ""
        self.selected_quest_id: int | None = None
        self.active_series_id = ""
        self.hierarchy_collapsed = False
        self.hierarchy = QuestHierarchyService(self.catalog, self.graph).build()
        self.category_items: dict[str, QTreeWidgetItem] = {}
        self.series_items: dict[str, QTreeWidgetItem] = {}
        self.quest_tree_items: dict[int, list[QTreeWidgetItem]] = {}
        self._loaded_category_names: set[str] = set()
        self._loaded_series_ids: set[str] = set()
        self._hierarchy_completed_quest_ids: frozenset[int] = frozenset()
        self._rendered_hierarchy = None
        self.current_mode = "TOUTES"
        self.refreshing = False
        self.object_rows_refreshing = False
        self.icon_cache = IconCache(24)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UNITY_SPACING_PX["sm"])

        self._init_hidden_controls()
        self._build_search_ui(root)
        if not self._defer_detail_view:
            self._build_detail_view()
        self._build_hierarchy_ui(root)

        self.refresh_characters()
        self._sync_achievement_progress()
        if self.quest_detail_view is not None:
            self.quest_detail_view.set_character_key(self.current_character_key)
        self.rebuild_hierarchy()
        self.refresh_quests()
        self.restore_last_quest()
        self.status_callback(f"{len(self.catalog.quests)} quêtes chargées.")

    def _init_hidden_controls(self) -> None:
        self.character_combo = AtlasComboBox()
        self.character_combo.setVisible(False)
        self.character_combo.currentIndexChanged.connect(self.on_character_changed)

        self.mode_list = QListWidget()
        self.mode_list.setVisible(False)
        for mode in self.MODES:
            self.mode_list.addItem(mode)
        self.mode_list.setCurrentRow(len(self.MODES) - 1)

        self.state_combo = AtlasComboBox()
        self.state_combo.setVisible(False)
        self.state_combo.addItems(["Toutes", "Disponibles", "Bloquées", "Terminées"])
        self.type_combo = AtlasComboBox()
        self.type_combo.setVisible(False)
        self.type_combo.addItems(["Toutes", "Normales", "Répétables", "Journalières", "Hebdomadaires"])
        self.hide_done_button = HideCompletedButton()
        self.hide_done_button.setVisible(False)
        self.count_label = QLabel("")
        self.count_label.setVisible(False)
        self.copy_feedback = QLabel("")
        self.copy_feedback.setObjectName("MutedLabel")
        self.copy_feedback.setVisible(False)
        self.quest_items_panel = QFrame(self)
        self.quest_items_panel.setVisible(False)

    def _build_search_ui(self, root: QVBoxLayout) -> None:
        self.search = QLineEdit()
        self.search.setObjectName("EncyclopediaSearch")
        self.search.setPlaceholderText("Rechercher une quête...")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(QUEST_GEOMETRY["search_min_height"])
        self.search.textChanged.connect(lambda _text: self.refresh_quests())
        root.addWidget(self.search)

        self.breadcrumb = AtlasBreadcrumb()
        self.breadcrumb_layout = self.breadcrumb.row
        root.addWidget(self.breadcrumb)

        self.quest_model = QuestListModel(self)
        self.quest_list = QuestListFacade(self)
        self.quest_list.setModel(self.quest_model)
        self.quest_list.setMaximumHeight(QUEST_GEOMETRY["quest_list_max_height"])
        self.quest_list.setVisible(False)
        root.addWidget(self.quest_list)

        self.detail = NativeQuestDetailPanel(self)
        self.detail.setVisible(False)

    def _build_detail_view(self) -> None:
        if self.quest_detail_view is not None:
            return
        from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView

        self.quest_detail_view = QuestDetailView(
            self.quest_provider,
            self.graph,
            self.quest_progress_service,
            achievement_provider=self.achievement_provider,
            guide_provider=self.guide_provider,
            character_key=self.current_character_key,
            open_quest=self.open_related_quest,
            open_prerequisite=self.open_related_quest,
            navigate_entity=self.navigate_callback,
        )
        self.quest_detail_view.questProgressChanged.connect(self.on_shared_quest_progress_changed)

    def _bind_detail_view_aliases(self) -> None:
        view = self.quest_detail_view
        if view is None:
            self.splitter = None
            self.center_panel = None
            self.center_scroll = None
            self.center_layout = None
            self.right_panel = None
            self.right_scroll = None
            self.right_layout = None
            return
        self.splitter = view.splitter
        self.center_panel = view.center_panel
        self.center_scroll = view.center_scroll
        self.center_layout = view.center_layout
        self.right_panel = None
        self.right_scroll = None
        self.right_layout = None

    def _ensure_quest_detail_view(self):
        if self.quest_detail_view is not None:
            return self.quest_detail_view
        self._build_detail_view()
        view = self.quest_detail_view
        if view is None:
            raise RuntimeError("QuestDetailView indisponible")
        placeholder = self._quest_detail_placeholder
        if placeholder is not None and hasattr(self, "body_splitter"):
            index = self.body_splitter.indexOf(placeholder)
            if index >= 0:
                replaced = self.body_splitter.replaceWidget(index, view)
                if replaced is not None:
                    replaced.deleteLater()
            else:
                self.body_splitter.addWidget(view)
            self._quest_detail_placeholder = None
            self.body_splitter.setStretchFactor(1, 1)
            self.body_splitter.setSizes([QUEST_HIERARCHY_OPEN_WIDTH, QUEST_GEOMETRY["detail_initial_width"]])
            # QSplitter.replaceWidget() does not inherit the replaced
            # placeholder's visible state. Without this, the first selected
            # quest owns a hydrated detail widget that remains explicitly
            # hidden behind an empty splitter column.
            view.show()
        self._bind_detail_view_aliases()
        view.set_character_key(self.current_character_key)
        return view

    def _build_hierarchy_ui(self, root: QVBoxLayout) -> None:
        self.body_splitter = FixedColumnSplitter(Qt.Horizontal)
        self.body_splitter.setObjectName("QuestHierarchySplitter")
        self.hierarchy_panel = EncyclopediaPanel()
        self.hierarchy_panel.setObjectName("GuideLeftPanel")
        self.hierarchy_panel.setMinimumWidth(QUEST_HIERARCHY_OPEN_WIDTH)
        self.hierarchy_panel.setMaximumWidth(QUEST_HIERARCHY_OPEN_WIDTH)

        self.hierarchy_content = QWidget()
        self.hierarchy_content.setObjectName("GuideLeftPanelContent")
        hierarchy_content_layout = QVBoxLayout(self.hierarchy_content)
        hierarchy_content_layout.setContentsMargins(0, 0, 0, 0)
        hierarchy_content_layout.setSpacing(UNITY_SPACING_PX["sm"])
        hierarchy_header = QFrame()
        hierarchy_header.setObjectName("GuideStepsHeader")
        hierarchy_header_layout = QHBoxLayout(hierarchy_header)
        hierarchy_header_layout.setContentsMargins(0, 0, 0, UNITY_SPACING_PX["xxs"])
        hierarchy_header_layout.setSpacing(UNITY_SPACING_PX["sm"])
        hierarchy_title = QLabel("CATÉGORIES ET SUITES")
        hierarchy_title.setObjectName("GuideSectionTitle")
        hierarchy_header_layout.addWidget(hierarchy_title, 1)
        collapse_box = QUEST_GEOMETRY["collapse_button_box"]
        self.hierarchy_collapse_button = configure_unity_tool_button(
            QToolButton(), object_name="GuideStepsCollapseButton",
            text="\u2039", box=(collapse_box, collapse_box), focus_policy=Qt.NoFocus,
        )
        self.hierarchy_collapse_button.setToolTip("Réduire la colonne")
        self.hierarchy_collapse_button.clicked.connect(lambda: self.set_hierarchy_collapsed(True))
        hierarchy_header_layout.addWidget(self.hierarchy_collapse_button)
        hierarchy_content_layout.addWidget(hierarchy_header)

        self.hierarchy_tree = QTreeWidget()
        self.hierarchy_tree.setObjectName("QuestHierarchyTree")
        self.hierarchy_tree.setHeaderHidden(True)
        self.hierarchy_tree.setUniformRowHeights(True)
        self.hierarchy_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.hierarchy_tree.itemClicked.connect(self.on_hierarchy_item_clicked)
        self.hierarchy_tree.itemExpanded.connect(self.on_hierarchy_item_expanded)
        hierarchy_content_layout.addWidget(self.hierarchy_tree, 1)
        self.hierarchy_panel.root.addWidget(self.hierarchy_content, 1)
        self.hierarchy_collapsed_rail = CollapsedColumnRail("Afficher les catégories et suites")
        self.hierarchy_collapsed_rail.expandedRequested.connect(lambda: self.set_hierarchy_collapsed(False))
        self.hierarchy_collapsed_rail.setVisible(False)
        self.hierarchy_panel.root.addWidget(self.hierarchy_collapsed_rail, 1)
        self.body_splitter.addWidget(self.hierarchy_panel)
        if self.quest_detail_view is not None:
            self.body_splitter.addWidget(self.quest_detail_view)
        else:
            placeholder = QFrame()
            placeholder.setObjectName("QuestDetailDeferred")
            placeholder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            placeholder_layout = QVBoxLayout(placeholder)
            inset = QUEST_GEOMETRY["deferred_detail_padding"]
            placeholder_layout.setContentsMargins(inset, inset, inset, inset)
            hint = QLabel("Sélectionnez une quête pour afficher sa fiche.")
            hint.setObjectName("MutedLabel")
            hint.setAlignment(Qt.AlignCenter)
            placeholder_layout.addStretch(1)
            placeholder_layout.addWidget(hint)
            placeholder_layout.addStretch(1)
            self._quest_detail_placeholder = placeholder
            self.body_splitter.addWidget(placeholder)
        self.body_splitter.setStretchFactor(0, 0)
        self.body_splitter.setStretchFactor(1, 1)
        self.body_splitter.setSizes([QUEST_HIERARCHY_OPEN_WIDTH, QUEST_GEOMETRY["detail_initial_width"]])
        root.addWidget(self.body_splitter, 1)
        self._bind_detail_view_aliases()

    def set_hierarchy_collapsed(self, collapsed: bool) -> None:
        collapsed = bool(collapsed)
        if self.hierarchy_collapsed == collapsed:
            return
        self.hierarchy_collapsed = collapsed
        self.hierarchy_content.setVisible(not collapsed)
        self.hierarchy_collapsed_rail.setVisible(collapsed)
        width = QUEST_HIERARCHY_COLLAPSED_WIDTH if collapsed else QUEST_HIERARCHY_OPEN_WIDTH
        self.hierarchy_panel.setMinimumWidth(width)
        self.hierarchy_panel.setMaximumWidth(width)
        available = max(1, sum(self.body_splitter.sizes()) - width)
        self.body_splitter.setSizes([width, available])

    def _sync_achievement_progress(self) -> bool:
        if self.achievement_provider is None or not is_character_key(self.current_character_key):
            return False
        return self.achievement_progress_service.sync_from_quest_progress(
            self.current_character_key,
            self.achievement_provider,
            self.quest_progress_service,
            self.guide_provider,
        )

    def update_related_context(
        self,
        guide_provider: Any = None,
        achievement_provider: AchievementProvider | None = None,
        graph: QuestGraphService | None = None,
    ) -> None:
        if guide_provider is not None:
            self.guide_provider = guide_provider
        if achievement_provider is not None:
            self.achievement_provider = achievement_provider
        if graph is not None:
            self.graph = graph
        elif guide_provider is not None or achievement_provider is not None:
            self.graph = QuestGraphService(self.quest_provider, self.guide_provider, self.achievement_provider)
        if self.quest_detail_view is not None:
            self.quest_detail_view.update_related_context(
                guide_provider=guide_provider,
                achievement_provider=achievement_provider,
                graph=self.graph,
            )
        self._sync_achievement_progress()
        self.hierarchy = QuestHierarchyService(self.catalog, self.graph).build()
        self.rebuild_hierarchy()

    @staticmethod
    def _hierarchy_placeholder() -> QTreeWidgetItem:
        item = QTreeWidgetItem([""])
        item.setData(0, HIERARCHY_KIND_ROLE, "placeholder")
        item.setFlags(Qt.NoItemFlags)
        return item

    def _hierarchy_category(self, name: str):
        return next(
            (category for category in self.hierarchy.categories if category.name == name),
            None,
        )

    def ensure_category_series_loaded(self, category_name: str) -> QTreeWidgetItem | None:
        item = self.category_items.get(str(category_name))
        if item is not None:
            self._materialize_hierarchy_category(item)
        return item

    def ensure_series_quests_loaded(self, series_id: str) -> QTreeWidgetItem | None:
        series_id = str(series_id)
        item = self.series_items.get(series_id)
        if item is None:
            category = next((category for category in self.hierarchy.categories
                             if any(series.id == series_id for series in category.series)), None)
            if category is not None:
                self.ensure_category_series_loaded(category.name)
                item = self.series_items.get(series_id)
        if item is not None:
            self._materialize_hierarchy_series(item)
        return item

    def _materialize_hierarchy_category(self, item: QTreeWidgetItem) -> None:
        name = str(item.data(0, HIERARCHY_ID_ROLE) or "")
        if not name or name in self._loaded_category_names:
            return
        category = self._hierarchy_category(name)
        if category is None:
            return

        item.takeChildren()
        for series in category.series:
            series_item = QTreeWidgetItem([series.name])
            series_item.setData(0, HIERARCHY_KIND_ROLE, "series")
            series_item.setData(0, HIERARCHY_ID_ROLE, series.id)
            series_item.setToolTip(0, f"{len(series.quest_ids)} quêtes")
            if series.quest_ids:
                series_item.addChild(self._hierarchy_placeholder())
            item.addChild(series_item)
            self.series_items[series.id] = series_item
        self._loaded_category_names.add(name)

    def _materialize_hierarchy_series(self, item: QTreeWidgetItem) -> None:
        series_id = str(item.data(0, HIERARCHY_ID_ROLE) or "")
        if not series_id or series_id in self._loaded_series_ids:
            return
        series = self.hierarchy.series_by_id.get(series_id)
        if series is None:
            return

        item.takeChildren()
        completed_quest_ids = self._hierarchy_completed_quest_ids
        for quest_id in series.quest_ids:
            quest = self.catalog.by_id.get(int(quest_id))
            if quest is None:
                continue
            quest_item = QTreeWidgetItem(
                [self.hierarchy_quest_label(quest, completed_quest_ids)]
            )
            quest_item.setData(0, HIERARCHY_KIND_ROLE, "quest")
            quest_item.setData(0, HIERARCHY_ID_ROLE, int(quest.id))
            quest_item.setToolTip(0, quest.name)
            item.addChild(quest_item)
            self.quest_tree_items.setdefault(int(quest.id), []).append(quest_item)
        self._loaded_series_ids.add(series_id)

    def on_hierarchy_item_expanded(self, item: QTreeWidgetItem) -> None:
        kind = str(item.data(0, HIERARCHY_KIND_ROLE) or "")
        if kind == "category":
            self._materialize_hierarchy_category(item)
        elif kind == "series":
            self._materialize_hierarchy_series(item)

    def rebuild_hierarchy(self) -> None:
        selected_id = self.selected_quest_id
        preferred_series = self.active_series_id
        completed_quest_ids = (
            self.quest_progress_service.completed_quest_ids(self.current_character_key)
            if self.current_character_key
            else set()
        )
        self._hierarchy_completed_quest_ids = frozenset(
            int(value) for value in completed_quest_ids
        )
        if self._rendered_hierarchy is self.hierarchy and self.hierarchy_tree.topLevelItemCount():
            for quest_id, items in self.quest_tree_items.items():
                quest = self.catalog.by_id.get(quest_id)
                if quest is not None:
                    label = self.hierarchy_quest_label(quest, self._hierarchy_completed_quest_ids)
                    for item in items:
                        if item.text(0) != label:
                            item.setText(0, label)
            if selected_id is not None:
                self.sync_hierarchy_selection(selected_id, preferred_series)
            self.render_breadcrumb()
            return
        previous_blocked = self.hierarchy_tree.blockSignals(True)
        previous_updates = self.hierarchy_tree.updatesEnabled()
        self.hierarchy_tree.setUpdatesEnabled(False)
        try:
            self.hierarchy_tree.clear()
            self.category_items.clear()
            self.series_items.clear()
            self.quest_tree_items.clear()
            self._loaded_category_names.clear()
            self._loaded_series_ids.clear()
            for category in self.hierarchy.categories:
                category_item = QTreeWidgetItem([category.name])
                category_item.setData(0, HIERARCHY_KIND_ROLE, "category")
                category_item.setData(0, HIERARCHY_ID_ROLE, category.name)
                category_item.setToolTip(0, f"{len(category.series)} suites")
                if category.series:
                    category_item.addChild(self._hierarchy_placeholder())
                self.hierarchy_tree.addTopLevelItem(category_item)
                self.category_items[category.name] = category_item
            self._rendered_hierarchy = self.hierarchy
        finally:
            self.hierarchy_tree.blockSignals(previous_blocked)
            self.hierarchy_tree.setUpdatesEnabled(previous_updates)
        if selected_id is not None:
            self.sync_hierarchy_selection(selected_id, preferred_series)
        self.render_breadcrumb()

    def hierarchy_quest_label(
        self,
        quest: QuestRecord,
        completed_quest_ids: set[int] | frozenset[int] | None = None,
    ) -> str:
        if completed_quest_ids is None:
            completed = bool(self.current_character_key and self.is_quest_done(int(quest.id)))
        else:
            completed = int(quest.id) in completed_quest_ids
        marker = "✓ " if completed else ""
        return f"{marker}{quest.name}"

    def on_hierarchy_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(0, HIERARCHY_KIND_ROLE) != "quest":
            return
        quest_id = item.data(0, HIERARCHY_ID_ROLE)
        parent = item.parent()
        series_id = str(parent.data(0, HIERARCHY_ID_ROLE) or "") if parent is not None else ""
        self.select_quest(int(quest_id), series_id=series_id)

    def sync_hierarchy_selection(self, quest_id: int, preferred_series_id: str = "") -> QuestHierarchyPath | None:
        path = self.hierarchy.path_for(int(quest_id), preferred_series_id)
        if path is None:
            self.active_series_id = ""
            return None

        self.active_series_id = path.series.id
        category_item = self.category_items.get(path.category.name)
        if category_item is None:
            return path
        self._materialize_hierarchy_category(category_item)

        series_item = self.series_items.get(path.series.id)
        if series_item is None:
            return path
        self._materialize_hierarchy_series(series_item)

        category_item.setExpanded(True)
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

    def render_breadcrumb(self) -> None:
        clear_unity_widget_layout(self.breadcrumb_layout)
        home = AtlasButton("Quêtes", variant="guide_breadcrumb")
        home.clicked.connect(lambda _checked=False: self.hierarchy_tree.setFocus())
        self.breadcrumb_layout.addWidget(home)
        if self.selected_quest_id is None:
            self.breadcrumb_layout.addStretch(1)
            return
        path = self.hierarchy.path_for(self.selected_quest_id, self.active_series_id)
        quest = self.catalog.by_id.get(int(self.selected_quest_id))
        if path is None or quest is None:
            self.breadcrumb_layout.addStretch(1)
            return
        self.breadcrumb.add_separator()
        category_button = AtlasButton(path.category.name, variant="guide_breadcrumb")
        category_button.setMaximumWidth(QUEST_GEOMETRY["category_button_max_width"])
        category_button.setToolTip(path.category.name)
        category_button.clicked.connect(
            lambda _checked=False, name=path.category.name: self.focus_hierarchy_category(name)
        )
        self.breadcrumb_layout.addWidget(category_button)
        self.breadcrumb.add_separator()
        series_button = AtlasButton(path.series.name, variant="guide_breadcrumb")
        series_button.setMaximumWidth(QUEST_GEOMETRY["series_button_max_width"])
        series_button.setToolTip(path.series.name)
        series_button.clicked.connect(
            lambda _checked=False, series_id=path.series.id: self.focus_hierarchy_series(series_id)
        )
        self.breadcrumb_layout.addWidget(series_button)
        self.breadcrumb.add_separator()
        current = self.breadcrumb.add_current(quest.name)
        current.setToolTip(quest.name)
        current.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def focus_hierarchy_category(self, category_name: str) -> None:
        item = self.category_items.get(str(category_name))
        if item is not None:
            item.setExpanded(True)
            self.hierarchy_tree.setCurrentItem(item)
            self.hierarchy_tree.scrollToItem(item)
            self.hierarchy_tree.setFocus()

    def focus_hierarchy_series(self, series_id: str) -> None:
        item = self.ensure_series_quests_loaded(series_id)
        if item is not None:
            item.parent().setExpanded(True)
            item.setExpanded(True)
            self.hierarchy_tree.setCurrentItem(item)
            self.hierarchy_tree.scrollToItem(item)
            self.hierarchy_tree.setFocus()

    def refresh_characters(self) -> None:
        previous = self.current_character_key
        self.characters = load_quest_characters(
            self.profile_path,
            self.client_index_path,
            connected_only=True,
        )
        self.current_character_key = populate_character_combo(
            self.character_combo, self.characters, previous,
        )

    def on_character_changed(self) -> None:
        character = self.character_combo.currentData()
        self.set_character_key(character.key if isinstance(character, QuestCharacter) else "")

    def set_character_key(self, character_key: str) -> None:
        """One character-switch pipeline for standalone and embedded Quests."""
        character_key = str(character_key or "")
        select_character_combo_key(self.character_combo, character_key)
        if character_key == self.current_character_key:
            return
        self.current_character_key = character_key
        self.progress = self.quest_progress_service.reload()
        self._sync_achievement_progress()
        self.rebuild_hierarchy()
        self.refresh_quests()
        if self.selected_quest_id is not None:
            self.show_quest_detail(self.selected_quest_id)
        elif self.quest_detail_view is not None:
            self.quest_detail_view.set_character_key(character_key, refresh=False)

    def on_mode_changed(self, text: str) -> None:
        self.current_mode = text or "TOUTES"
        self.refresh_quests()

    def on_hide_done_toggled(self, _checked: bool) -> None:
        self.refresh_quests()

    def refresh_external_progress(self) -> None:
        quest_changed = self.quest_progress_service.refresh_if_changed()
        achievement_changed = self.achievement_progress_service.refresh_if_changed()
        if not quest_changed and not achievement_changed:
            return

        if quest_changed:
            self.progress = self.quest_progress_service.progress
            self._sync_achievement_progress()
            self.rebuild_hierarchy()
            self.refresh_quests()
        if self.selected_quest_id is not None:
            self.show_quest_detail(self.selected_quest_id)
        elif quest_changed:
            self.restore_last_quest()

    def is_quest_done(self, quest_id: int) -> bool:
        return self.quest_progress_service.is_quest_completed(
            self.current_character_key,
            int(quest_id),
        )

    def quest_state(self, quest: QuestRecord) -> str:
        if self.is_quest_done(quest.id):
            return "Terminée"
        if any(not self.is_quest_done(quest_id) for quest_id in self.graph.previous_ids(quest.id)):
            return "Bloquée"
        if self.graph.is_repeatable(quest):
            return "Répétable"
        return "Disponible"

    def repeatability_kind(self, quest: QuestRecord) -> str:
        text = normalize_text(quest_repeatability_text(quest))
        if any(token in text for token in ("hebdomadaire", "weekly", "chaque semaine")):
            return "Hebdomadaire"
        if any(token in text for token in ("journaliere", "journalier", "daily", "chaque jour")):
            return "Journalière"
        if self.graph.is_repeatable(quest):
            return "Répétable"
        return "Normale"

    def matching_quests(self) -> list[QuestRecord]:
        if len(self.search.text().strip()) < MIN_QUEST_SEARCH_CHARS:
            return []
        query = normalize_text(self.search.text())
        tokens = [token for token in query.split("_") if token]
        # Inactive filters must not hydrate details or read progress.
        matches: list[QuestRecord] = []
        for quest in self.catalog.quests:
            if not self._matches_search_tokens(quest, tokens):
                continue
            if not self._matches_current_mode(quest):
                continue
            matches.append(quest)
        return matches

    def _matches_search_tokens(self, quest: QuestRecord, tokens: list[str]) -> bool:
        haystack = self.quest_search_text(quest)
        return not tokens or all(token in haystack for token in tokens)

    def _matches_state_filter(self, quest: QuestRecord, hide_done: bool, state_filter: str) -> bool:
        if not hide_done and state_filter == "Toutes":
            return True
        state = self.quest_state(quest)
        if hide_done and state == "Terminée":
            return False
        if state_filter == "Disponibles":
            return state == "Disponible"
        if state_filter == "Bloquées":
            return state == "Bloquée"
        if state_filter == "Terminées":
            return state == "Terminée"
        return True

    def _matches_type_filter(self, quest: QuestRecord, type_filter: str) -> bool:
        if type_filter == "Toutes":
            return True
        repeatability = self.repeatability_kind(quest)
        if type_filter == "Normales":
            return repeatability == "Normale"
        if type_filter == "Répétables":
            return repeatability != "Normale"
        if type_filter == "Journalières":
            return repeatability == "Journalière"
        if type_filter == "Hebdomadaires":
            return repeatability == "Hebdomadaire"
        return True

    def _matches_current_mode(self, quest: QuestRecord) -> bool:
        if self.current_mode == "DOFUS":
            guides = (
                self.guide_provider.get_guides_for_entity("quest", quest.id)
                if self.guide_provider is not None
                else []
            )
            return any(guide.category == "dofus" for guide in guides)
        if self.current_mode == "PARCOURS":
            return bool(self.graph.guide_ids(quest.id))
        if self.current_mode == "SUCCÈS LIÉS":
            return bool(quest.achievements)
        return True

    def quest_search_text(self, quest: QuestRecord) -> str:
        guides = self.guide_provider.get_guides_for_entity("quest", quest.id) if self.guide_provider is not None else []
        prebuilt = getattr(self.catalog, "_prebuilt_quest_search_text", None)
        document = prebuilt.get(int(quest.id)) if isinstance(prebuilt, dict) else None
        return quest_context_search_text(
            quest, self.graph.achievement_names(quest.id),
            (guide.title for guide in guides), document=document,
        )

    def _clear_search_projection(self) -> None:
        self.quest_model.set_quests([], {})
        self.quest_list.clearSelection()
        self.quest_list.setVisible(False)

    def refresh_quests(self) -> None:
        if not self.current_character_key or len(self.search.text().strip()) < MIN_QUEST_SEARCH_CHARS:
            # The search list is independent of the selected hierarchy sheet.
            # A closed or incomplete search must not erase that sheet.
            self._clear_search_projection()
            return
        current_id = self.selected_quest_id
        matches = self.matching_quests()
        states = {quest.id: self.quest_state(quest) for quest in matches}
        self.quest_model.set_quests(matches, states)
        self.quest_list.setVisible(len(self.search.text().strip()) >= MIN_QUEST_SEARCH_CHARS and bool(matches))
        if self.count_label.isVisible():
            done_count = len(self.quest_progress_service.completed_quest_ids(self.current_character_key))
            self.count_label.setText(f"{format_grouped_int(len(matches))} / {format_grouped_int(len(self.catalog.quests))} quêtes • {format_grouped_int(done_count)} terminées")
        if current_id is not None:
            row = self.quest_model.row_for_quest(current_id)
            if row >= 0:
                index = self.quest_model.index(row, 0)
                self.quest_list.setCurrentIndex(index)
            elif getattr(self, "_search_worker", None) is None:
                self.render_empty_detail("Quête masquée par le filtre.")

    def close_search_results(self) -> None:
        blocked = self.search.blockSignals(True)
        try:
            self.search.clear()
        finally:
            self.search.blockSignals(blocked)
        self._clear_search_projection()

    def select_quest_from_search(self, quest_id: int) -> None:
        self.close_search_results()
        self.select_quest(quest_id)

    def select_quest(self, quest_id: int, persist: bool = True, series_id: str = "") -> None:
        quest_id = int(quest_id)
        if quest_id not in self.catalog.by_id:
            self.selected_quest_id = None
            self.active_series_id = ""
            self.clear_detail_columns()
            self.render_breadcrumb()
            return
        self.selected_quest_id = quest_id
        self.sync_hierarchy_selection(quest_id, series_id or self.active_series_id)
        self.render_breadcrumb()
        row = self.quest_model.row_for_quest(quest_id)
        if row >= 0:
            index = self.quest_model.index(row, 0)
            self.quest_list.setCurrentIndex(index)
            self.quest_list.scrollTo(index)
        self.show_quest_detail(quest_id)
        if persist:
            self.save_last_quest_id(quest_id)

    def open_related_quest(self, quest_id: int) -> bool:
        quest_id = int(quest_id)
        if quest_id not in self.catalog.by_id:
            return False
        self.select_quest(quest_id, persist=False)
        return True

    def restore_last_quest(self) -> None:
        quest_id = self.load_last_quest_id()
        if quest_id is None or quest_id not in self.catalog.by_id:
            self.selected_quest_id = None
            self.clear_detail_columns()
            return
        self.select_quest(quest_id, persist=False)

    def load_last_quest_id(self) -> int | None:
        payload = read_json(self.profile_path, {})
        if not isinstance(payload, dict):
            return None
        try:
            quest_id = int(payload.get(KEY_LAST_SELECTED_QUEST_ID))
        except (TypeError, ValueError):
            return None
        return quest_id if quest_id > 0 else None

    def save_last_quest_id(self, quest_id: int) -> None:
        from app.services.profile_settings_service import ProfileSettingsService
        ProfileSettingsService(self.profile_path).set_value(KEY_LAST_SELECTED_QUEST_ID, int(quest_id))

    def clear_detail_columns(self) -> None:
        self.detail.set_compat_html("")
        if self.quest_detail_view is not None:
            self.quest_detail_view.clear()

    def _refresh_after_quest_progress_change(
        self, quest_id: int, *, reload_progress: bool,
        refresh_list: bool, refresh_detail: bool,
    ) -> None:
        self.progress = (self.quest_progress_service.reload() if reload_progress
                         else self.quest_progress_service.progress)
        self._sync_achievement_progress()
        self.refresh_hierarchy_quest_state(quest_id)
        if refresh_list:
            self.refresh_quests()
        if refresh_detail:
            self.show_quest_detail(quest_id)

    def on_shared_quest_progress_changed(self, quest_id: int) -> None:
        quest_id = int(quest_id)
        self._refresh_after_quest_progress_change(
            quest_id, reload_progress=True,
            refresh_list=len(self.search.text().strip()) >= MIN_QUEST_SEARCH_CHARS,
            refresh_detail=False,
        )
        self.selected_quest_id = quest_id

    def refresh_hierarchy_quest_state(self, quest_id: int) -> None:
        quest = self.catalog.by_id.get(int(quest_id))
        if quest is None:
            return
        completed = bool(self.current_character_key and self.is_quest_done(int(quest_id)))
        if completed:
            self._hierarchy_completed_quest_ids = self._hierarchy_completed_quest_ids | {int(quest_id)}
        else:
            self._hierarchy_completed_quest_ids = self._hierarchy_completed_quest_ids - {int(quest_id)}
        text = self.hierarchy_quest_label(quest, self._hierarchy_completed_quest_ids)
        for item in self.quest_tree_items.get(int(quest_id), ()):
            if item.text(0) != text:
                item.setText(0, text)

    def set_quest_checked(self, quest_id: int, done: bool) -> None:
        self.quest_progress_service.set_quest_completed(
            self.current_character_key,
            int(quest_id),
            bool(done),
        )
        self._refresh_after_quest_progress_change(
            int(quest_id), reload_progress=False, refresh_list=True, refresh_detail=True,
        )

    def show_quest_detail(self, quest_id: int) -> None:
        quest = self.catalog.by_id.get(int(quest_id))
        if not quest:
            self.quest_items_panel.setVisible(False)
            self.clear_detail_columns()
            return
        done = self.is_quest_done(quest.id)
        self.refresh_owned_items()
        related_guides = self.guide_provider.get_guides_for_entity("quest", quest.id) if self.guide_provider is not None else []
        related_achievements = self.achievement_provider.get_by_quest(quest.id) if self.achievement_provider is not None else []
        achievement_state = self.achievement_progress_service.state_for(self.current_character_key)
        self.detail.set_lazy_payload((
            quest, done, dict(self.owned_items),
            tuple(related_guides), tuple(related_achievements), achievement_state,
        ))
        view = self._ensure_quest_detail_view()
        from app.modules.encyclopedia.widgets.quest_detail_view import QuestViewContext

        view.set_character_key(self.current_character_key, refresh=False)
        active_series = self.hierarchy.series_by_id.get(self.active_series_id)
        view.show_quest(
            int(quest.id),
            QuestViewContext(
                host="quests",
                ordered_quest_ids=active_series.quest_ids if active_series is not None else (),
            ),
        )

    def render_empty_detail(self, message: str) -> None:
        self.detail.set_compat_html(empty_detail_html(message))
        if self.quest_detail_view is not None:
            self.quest_detail_view.clear(message)

    def on_detail_link_clicked(self, url: QUrl) -> None:
        if url.scheme() == "atlas-guide":
            guide_id = url.toString().split(":", 1)[1] if ":" in url.toString() else ""
            if guide_id and self.navigate_callback is not None and self.navigate_callback("guide", guide_id):
                self.status_callback(f"Ouverture guide {guide_id}")
            else:
                self.status_callback("Guide associé introuvable.")
            return
        command = travel_command_from_url(url)
        if command:
            QApplication.clipboard().setText(command)
            self.set_copy_feedback(f"Copie: {command}")
            self.status_callback(f"Copie: {command}")
            return
        self.status_callback("Lien externe désactivé dans Quêtes.")

    def refresh_owned_items(self) -> None:
        signature = mtime_ctime_size_stamp(self.owned_items_path)
        if signature == self._owned_items_file_signature:
            return
        # A disappeared file means an empty persisted selection, not stale
        # quantities. Initial caller-supplied quantities remain a valid fallback.
        self.owned_items = load_owned_items(self.owned_items_path) if signature is not None else {}
        self._owned_items_file_signature = signature

    def set_copy_feedback(self, text: str) -> None:
        self.copy_feedback.setText(text)
        self.copy_feedback.setVisible(True)

    def refresh_quest_items_panel(self, quest: QuestRecord) -> None:
        clear_layout(self.quest_items_layout)
        items = quest_required_items(quest)
        self.quest_items_panel.setVisible(bool(items))
        self.object_rows_refreshing = True
        for item in items:
            self.quest_items_layout.addWidget(self.create_quest_item_row(quest, item))
        self.quest_items_layout.addStretch(1)
        self.object_rows_refreshing = False

    def create_quest_item_row(self, quest: QuestRecord, item: dict[str, Any]) -> QWidget:
        item_id_value = int(item["item_id"])
        required = max(1, int(item["quantity"]))
        owned = min(required, int(self.owned_items.get(item_id_value, 0)))
        display_item = _display_item(
            item_id=item_id_value,
            name=str(item["name"]),
            image_path=str(item.get("image_path") or ""),
        )
        row = _quest_item_row(
            display_item,
            checked=self.quest_progress_service.is_item_completed(
                self.current_character_key,
                quest.id,
                item_id_value,
            ),
            on_toggle=lambda checked, qid=quest.id, iid=item_id_value: self.set_quest_item_checked(qid, iid, checked),
            on_copy=self.copy_quest_item_name,
        )
        row.setObjectName("QuestItemRow")
        layout = row.layout()
        required_label = QLabel(f"/ {format_grouped_int(required)}")
        required_label.setObjectName("MutedLabel")
        quantity = configure_unity_number_spinbox(
            QSpinBox(), minimum=0, maximum=required,
            value=owned, object_name="QuestItemQuantity",
            centered=True,
        )
        quantity.valueChanged.connect(lambda value, data=dict(item), maximum=required: self.set_owned_item_quantity(data, value, maximum))
        layout.addWidget(quantity)
        layout.addWidget(required_label)
        return row

    def set_quest_item_checked(self, quest_id: int, item_id_value: int, checked: bool) -> None:
        if self.object_rows_refreshing:
            return
        self.quest_progress_service.set_item_completed(
            self.current_character_key,
            int(quest_id),
            int(item_id_value),
            bool(checked),
        )
        self.progress = self.quest_progress_service.progress
        if self.selected_quest_id == int(quest_id):
            self.show_quest_detail(int(quest_id))

    def copy_quest_item_name(self, name: str) -> None:
        QApplication.clipboard().setText(name)
        self.set_copy_feedback(f"Copie objet: {name}")
        self.status_callback(f"Copie objet: {name}")

    def set_owned_item_quantity(self, item: dict[str, Any], value: int, maximum: int) -> None:
        if self.object_rows_refreshing:
            return
        quantity = max(0, min(int(value or 0), int(maximum)))
        ident = int(item["item_id"])
        try:
            save_owned_item_quantity(item, quantity, self.owned_items_path)
        except (InvalidPersistentJsonError, OSError, TimeoutError) as exc:
            counter = self.sender()
            if isinstance(counter, QSpinBox):
                restore_unity_number_value(counter, min(counter.maximum(), self.owned_items.get(ident, 0)))
            self.status_callback(f"Quantité non enregistrée : {exc}")
            return
        if quantity > 0:
            self.owned_items[ident] = quantity
        else:
            self.owned_items.pop(ident, None)


def empty_detail_html(message: str) -> str:
    return render_theme_template(f"""
<html><body style="font-family: @FONT_FAMILY; color: @TEXT; background: @PANEL;">
<p style="color:@TEXT_MUTED;">{escape(message)}</p>
</body></html>
""")


def quest_detail_html(
    quest: QuestRecord,
    done: bool,
    owned_items: dict[int, int] | None = None,
    related_guides: list[Any] | None = None,
    related_achievements: list[Any] | None = None,
    achievement_state: Any = None,
) -> str:
    status = "Effectuée" if done else "À faire"
    status_color = PALETTE["GREEN"] if done else PALETTE["YELLOW"]
    zones = ", ".join(quest.zones[:4]) or "Zone non détectée"
    level = f"Niveau {quest.level_min}" if quest.level_min else "Niveau non indiqué"
    if quest.level_max and quest.level_max != quest.level_min:
        level = f"{level} - {quest.level_max}"
    launch_instruction = quest_launch_instruction(quest.source_info)
    launch_section = (
        f"<h2>Lancement</h2><p>{linkify_travel_coordinates(launch_instruction)}</p>"
        if launch_instruction else ""
    )
    sections = [
        achievement_context_section(related_achievements or [], achievement_state, quest.achievements),
        launch_section,
        list_section("Prérequis", quest.prerequisites, "Aucun prérequis détecté."),
        list_section("Info", quest.info, "Aucune information particulière."),
        rewards_section(quest),
        steps_section(quest),
        guides_section(related_guides or []),
    ]
    return render_theme_template(f"""
<html>
<head>
<style>
body {{
  font-family: @FONT_FAMILY;
  background: @PANEL;
  color: @TEXT;
  font-size: @FONT_BODY;
  margin: 0;
}}
h1 {{ font-size: @FONT_CONTENT_H1; margin: 0 0 6px 0; }}
h2 {{ font-size: @FONT_CONTENT_H2; margin: 18px 0 6px 0; color: @TEXT; }}
h3 {{ font-size: @FONT_CONTENT_H3; margin: 12px 0 4px 0; color: @TEXT_SOFT; }}
p {{ line-height: 1.35; margin: 0; padding: 0; }}
ul {{ margin: 0 0 0 14px; padding: 0; }}
li {{ line-height: 1.35; margin: 0; padding: 0; }}
a {{ color: @GREEN; }}
a.coord {{
  color: @GREEN;
  font-weight: 700;
  text-decoration: none;
}}
.muted {{ color: @TEXT_MUTED; }}
.badge {{
  display: inline-block;
  color: @BG;
  background: {status_color};
  border-radius: 4px;
  padding: 2px 6px;
  font-weight: 700;
}}
.meta {{
  color: @TEXT_SOFT;
  margin: 2px 0 10px 0;
}}
.reward img, .step-image {{
  vertical-align: middle;
  max-width: 42px;
  max-height: 42px;
  margin: 4px 6px 4px 0;
}}
.quest-item img {{
  vertical-align: middle;
  margin-right: 6px;
}}
.achievement-card {{
  background: @PANEL_2;
  border: 1px solid @BORDER;
  border-radius: 6px;
  margin: 6px 0;
  padding: 7px 8px;
}}
</style>
</head>
<body>
<h1>{escape(quest.name)}</h1>
<p><span class="badge">{status}</span></p>
<p class="meta">{escape(level)} | {escape(quest.category or "Catégorie inconnue")} | {escape(zones)}</p>
{''.join(sections)}
</body>
</html>
""")


def list_section(title: str, items: list[str], empty: str) -> str:
    clean_items = [clean_requirement_line(str(item)) for item in items]
    clean_items = [item for item in clean_items if item]
    if not clean_items:
        return f"<h2>{escape(title)}</h2><p class=\"muted\">{escape(empty)}</p>"
    rows = "".join(f"<li>{linkify_travel_coordinates(str(item))}</li>" for item in clean_items[:20])
    return f"<h2>{escape(title)}</h2><ul>{rows}</ul>"


def achievement_context_section(achievements: list[Any], achievement_state: Any, fallback_names: list[str]) -> str:
    if not achievements:
        return list_section("Succès associés", fallback_names, "Aucun succès détecté dans les données locales.")
    cards = []
    for achievement in achievements[:8]:
        aid = int(getattr(achievement, "id", 0) or 0)
        objectives = list(getattr(achievement, "objectives", ()) or ())
        from app.modules.encyclopedia.services.achievement_progress_logic import achievement_progress_snapshot
        done_objectives, total_objectives, _completed, percent = achievement_progress_snapshot(
            achievement, achievement_state,
        )
        objective_rows = []
        for objective in objectives[:12]:
            oid = int(getattr(objective, "id", 0) or 0)
            checked = bool(achievement_state.is_objective_completed(aid, oid)) if achievement_state is not None and aid else False
            status = "✓" if checked else "○"
            objective_type = str(getattr(objective, "objective_type", "") or "")
            meta = f" <span class=\"muted\">{escape(objective_type)}</span>" if objective_type else ""
            objective_rows.append(f"<li>{status} {escape(str(getattr(objective, 'text', '')))}{meta}</li>")
        reward_rows = []
        visible_rewards = [
            reward
            for reward in list(getattr(achievement, "rewards", ()) or ())
            if str(getattr(reward, "kind", "") or "") not in {"xp", "xp_ratio"}
        ]
        for reward in visible_rewards[:8]:
            reward_rows.append(f"<li>{escape(achievement_reward_label(reward))}</li>")
        cards.append(
            "<div class=\"achievement-card\">"
            f"<h3>{escape(str(getattr(achievement, 'name', 'Succès')))}</h3>"
            f"<p class=\"muted\">{escape(str(getattr(achievement, 'description', '') or ''))}</p>"
            f"<p class=\"meta\">{done_objectives} / {total_objectives} objectif(s) • {percent} %</p>"
            + ("<ul>" + "".join(objective_rows) + "</ul>" if objective_rows else "<p class=\"muted\">Objectifs non détaillés.</p>")
            + ("<p class=\"muted\">Récompenses utiles</p><ul>" + "".join(reward_rows) + "</ul>" if reward_rows else "")
            + "</div>"
        )
    return f"<h2>Succès associés</h2>{''.join(cards)}"


def achievement_reward_label(reward: Any) -> str:
    quantity = getattr(reward, "quantity", None)
    name = str(getattr(reward, "name", "") or "")
    kind = str(getattr(reward, "kind", "") or "")
    if kind == "achievement_points":
        return f"{quantity or 0} point(s) de succès"
    if kind == "xp_ratio":
        return f"Expérience • ratio {quantity}"
    if kind == "kamas_ratio":
        return f"Kamas • ratio {quantity}"
    if quantity and int(quantity) > 1:
        return f"x{quantity} {name}"
    return name


def guides_section(guides: list[Any]) -> str:
    if not guides:
        return ""
    rows = []
    for guide in guides[:12]:
        guide_id = escape(str(getattr(guide, "id", "")), quote=True)
        title = escape(str(getattr(guide, "title", guide_id)))
        if guide_id:
            rows.append(f'<li><a href="atlas-guide:{guide_id}">{title}</a></li>')
    return f"<h2>Guides associés</h2><ul>{''.join(rows)}</ul>" if rows else ""


def local_image_url(path: str) -> str:
    return escape(QUrl.fromLocalFile(str(path)).toString())


def normalize_owned_items(payload: Any) -> dict[int, int]:
    return selection_quantities(payload, allow_legacy=True)


def load_owned_items(path: Path = CRAFT_SELECTION_FILE) -> dict[int, int]:
    return normalize_owned_items(read_json(path, {"items": []}))


def save_owned_item_quantity(item: dict[str, Any], quantity: int, path: Path = CRAFT_SELECTION_FILE) -> None:
    persist_selection_quantity(
        path, int(item["item_id"]), str(item.get("name") or ""), int(quantity),
    )


def clear_layout(layout: QVBoxLayout) -> None:
    clear_unity_widget_layout(layout, detach_widgets=False)


def quest_required_items(quest: QuestRecord) -> list[dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for step in quest.steps:
        for objective in step.objectives:
            if objective.item_id is None:
                continue
            if int(getattr(objective, "type_id", 0) or 0) not in QUEST_PANEL_ITEM_OBJECTIVE_TYPES:
                continue
            if is_alteration_objective(objective):
                continue
            quantity = max(1, int(objective.item_quantity or 1))
            entry = merged.setdefault(
                int(objective.item_id),
                {
                    "item_id": int(objective.item_id),
                    "name": objective.image_label or objective.text,
                    "quantity": 0,
                    "image_path": objective.image_path,
                },
            )
            entry["quantity"] = int(entry["quantity"]) + quantity
            if objective.image_path and not entry.get("image_path"):
                entry["image_path"] = objective.image_path
            if objective.image_label:
                entry["name"] = objective.image_label
    return sorted(merged.values(), key=lambda item: normalize_text(item.get("name")))


def is_alteration_objective(objective: Any) -> bool:
    text = normalize_text(f"{getattr(objective, 'image_label', '')} {getattr(objective, 'text', '')}")
    return "alteration" in text or "alterations" in text


def rewards_section(quest: QuestRecord) -> str:
    rewards = [
        reward
        for reward in quest.rewards
        if str(getattr(reward, "kind", "item") or "item") not in {"xp", "xp_ratio"}
        and not (getattr(reward, "kind", "item") == "kamas" and int(getattr(reward, "quantity", 0) or 0) <= 0)
    ]
    if not rewards:
        return "<h2>Récompenses</h2><p class=\"muted\">Aucune récompense détaillée détectée.</p>"
    rows = []
    for reward in rewards[:24]:
        icon = ""
        if reward.image_path:
            icon = f'<img width="24" height="24" src="{local_image_url(reward.image_path)}"> '
        rows.append(f'<li class="reward">{icon}{escape(reward_label(reward))}</li>')
    return f"<h2>Récompenses</h2><ul>{''.join(rows)}</ul>"


def reward_label(reward: Any) -> str:
    if getattr(reward, "kind", "item") == "kamas":
        return f"{format_grouped_int(int(reward.quantity or 0))} Kamas"
    if getattr(reward, "kind", "item") == "job":
        return f"Métier : {reward.name}"
    if getattr(reward, "kind", "item") == "spell":
        return f"Sort : {reward.name}"
    if getattr(reward, "kind", "item") == "title":
        return f"Titre : {reward.name}"
    if getattr(reward, "kind", "item") == "emote":
        return f"Émote : {reward.name}"
    quantity = f"x{format_grouped_int(int(reward.quantity))} " if int(reward.quantity or 1) > 1 else ""
    return quantity + str(reward.name)


def steps_section(quest: QuestRecord) -> str:
    if not quest.steps:
        return "<h2>Étapes</h2><p class=\"muted\">Aucune étape locale détectée.</p>"
    blocks = []
    for step in quest.steps[:30]:
        objective_rows = [objective_html(objective) for objective in step.objectives[:20]]
        objectives = "".join(f"<li>{row}</li>" for row in objective_rows if row)
        clean_description = clean_requirement_line(step.description)
        description = f"<p>{linkify_travel_coordinates(clean_description)}</p>" if clean_description else ""
        blocks.append(
            f"<h3>{escape(step.name)}</h3>"
            + description
            + (f"<ul>{objectives}</ul>" if objectives else "")
        )
    return "<h2>Étapes</h2>" + "".join(blocks)


def objective_html(objective: Any) -> str:
    image = ""
    if getattr(objective, "image_path", ""):
        image = f'<img class="step-image" width="42" height="42" src="{local_image_url(objective.image_path)}"> '
    clean = clean_requirement_line(objective.text)
    if not clean:
        return ""
    text = linkify_travel_coordinates(clean)
    return image + text


def linkify_travel_coordinates(value: str) -> str:
    text = escape(str(value or ""))

    def replace(match: re.Match[str]) -> str:
        x, y, dimension = match.groups()
        if dimension:
            return f"<b>{match.group(0)}</b>"
        coordinates = normalize_coordinate_pair(x, y)
        if coordinates is None:
            return match.group(0)
        return f'<b><a class="coord" href="atlas-travel:{coordinates}">[{coordinates}]</a></b>'

    return DOCUMENTARY_POSITION_RE.sub(replace, text)


def travel_command_from_url(url: QUrl) -> str:
    text = url.toString()
    if url.scheme() != "atlas-travel":
        return ""
    return travel_command_from_link(text) or ""
