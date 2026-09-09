from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.character_identity import is_character_key
from app.modules.encyclopedia.models.achievement import Achievement
from app.modules.encyclopedia.models.entity_ref import EntityRef
from app.modules.encyclopedia.providers import AchievementProvider, QuestProvider
from app.modules.encyclopedia.services import AchievementProgressService, QuestGraphService, QuestProgressService
from app.modules.encyclopedia.achievement_catalog_policy import (
    ALIGNMENT_GUIDE_IDS,
    ALIGNMENT_ORDER_ACHIEVEMENT_RANKS,
)
from app.modules.encyclopedia.services.guide_path_profiles import ORDER_QUEST_IDS
from app.modules.encyclopedia.widgets.achievement_detail_widget import AchievementDetailWidget
from app.modules.encyclopedia.widgets.achievement_entity_section import AchievementEntityRow
from app.modules.encyclopedia.widgets.dashboard import FixedColumnSplitter
from app.modules.encyclopedia.widgets.quest_detail_view import QuestDetailView, QuestViewContext
from app.quest_catalog import normalize_text
from app.ui.components import AtlasButton
from app.ui.theme import PALETTE
from app.ui.theme import render_theme_template


CATEGORY_ROLE = Qt.UserRole
TOP_CATEGORY_ROLE = Qt.UserRole + 1
COMPLETED_ROLE = Qt.UserRole + 2
_SEARCH_DEBOUNCE_MS = 90
_RESULT_BATCH_SIZE = 60


class AchievementListDelegate(QStyledItemDelegate):
    """Keep completed achievements visibly grey, even while selected."""

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        style = opt.widget.style() if opt.widget is not None else None
        if style is None:
            super().paint(painter, option, index)
            return
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)

        completed = bool(index.data(COMPLETED_ROLE))
        if completed:
            shade = QColor(PALETTE["BG"])
            shade.setAlpha(105)
            painter.fillRect(opt.rect.adjusted(1, 1, -1, -1), shade)
        painter.save()
        painter.setFont(opt.font)
        painter.setPen(QColor(PALETTE["TEXT_DISABLED"] if completed else PALETTE["TEXT_SOFT"]))
        painter.setOpacity(0.68 if completed else 1.0)
        painter.drawText(
            opt.rect.adjusted(10, 4, -10, -4),
            int(Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap),
            text,
        )
        painter.restore()


class AchievementsView(QWidget):
    """Lot 7 catalogue: category or zone -> achievement -> detail."""

    def _initialize_achievements_view(
        self,
        status_callback,
        provider: AchievementProvider,
        progress_service: AchievementProgressService,
        character_key: str = "",
        navigate_callback: Callable[..., bool] | None = None,
        quest_provider: QuestProvider | None = None,
        guide_provider: Any = None,
        quest_graph: QuestGraphService | None = None,
        quest_progress_service: QuestProgressService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AchievementsView")
        self.status_callback = status_callback
        self.provider = provider
        self.progress_service = progress_service
        self.character_key = character_key or ""
        self.navigate_callback = navigate_callback
        self.quest_provider = quest_provider or provider.quest_provider
        self.guide_provider = guide_provider
        self.quest_graph = quest_graph or QuestGraphService(self.quest_provider, guide_provider, provider)
        self.quest_progress_service = quest_progress_service or QuestProgressService()
        self.achievements = provider.load_retained()
        self.sync_automatic_progress()
        self.filtered: list[Achievement] = []
        self.current_achievement_id: int | None = None
        self.selected_category_id: int | None = None
        self._tree_items: dict[int, QTreeWidgetItem] = {}
        self._detail_open = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.search = QLineEdit()
        self.search.setObjectName("EncyclopediaSearch")
        self.search.setPlaceholderText("Rechercher dans les succès conservés...")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        root.addWidget(self.search)

        self.splitter = FixedColumnSplitter(Qt.Horizontal)
        self.splitter.setObjectName("AchievementCatalogSplitter")
        root.addWidget(self.splitter, 1)

        self.category_panel = self._panel("GuideLeftPanel", "CATÉGORIES ET ZONES")
        self.category_tree = QTreeWidget()
        self.category_tree.setObjectName("AchievementCategoryTree")
        self.category_tree.setHeaderHidden(True)
        self.category_tree.setUniformRowHeights(True)
        self.category_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.category_tree.currentItemChanged.connect(self.on_category_changed)
        self.category_panel.layout().addWidget(self.category_tree, 1)
        self.category_panel.setMinimumWidth(235)
        self.category_panel.setMaximumWidth(300)
        self.splitter.addWidget(self.category_panel)

        self.success_panel = self._panel("GuideCenterPanel", "SUCCÈS")
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("QuestResultList")
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setItemDelegate(AchievementListDelegate(self.list_widget))
        self.list_widget.itemClicked.connect(self.on_achievement_clicked)
        self.success_panel.layout().addWidget(self.list_widget, 1)
        self.success_panel.setMinimumWidth(285)
        self.splitter.addWidget(self.success_panel)

        self.detail_stack = QStackedWidget()
        self.detail_stack.setObjectName("AchievementDetailStack")
        self.detail_stack.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.splitter.addWidget(self.detail_stack)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setObjectName("GuideRightPanelScroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.detail_stack.addWidget(self.detail_scroll)

        self.detail_content = QWidget()
        self.detail_content.setObjectName("AchievementDetailContent")
        self.detail_content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.detail_layout = QVBoxLayout(self.detail_content)
        self.detail_layout.setContentsMargins(12, 12, 12, 12)
        self.detail_layout.setSpacing(10)
        self.detail_scroll.setWidget(self.detail_content)

        self.quest_detail_page = QWidget()
        self.quest_detail_page.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        quest_page_layout = QVBoxLayout(self.quest_detail_page)
        quest_page_layout.setContentsMargins(0, 0, 0, 0)
        quest_page_layout.setSpacing(6)
        self.back_to_achievement = AtlasButton("← Retour au succès")
        self.back_to_achievement.setObjectName("GuideBreadcrumbButton")
        self.back_to_achievement.clicked.connect(self.show_current_achievement)
        quest_page_layout.addWidget(self.back_to_achievement, 0, Qt.AlignLeft)
        self.quest_detail_view = QuestDetailView(
            self.quest_provider,
            self.quest_graph,
            self.quest_progress_service,
            achievement_provider=self.provider,
            guide_provider=self.guide_provider,
            character_key=self.character_key,
            open_quest=self.show_quest,
            open_prerequisite=self.open_prerequisite_in_quests,
            navigate_entity=self.open_shared_entity,
        )
        self.quest_detail_view.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        quest_page_layout.addWidget(self.quest_detail_view, 1)
        self.detail_stack.addWidget(self.quest_detail_page)
        self.quest_detail_view.questProgressChanged.connect(
            self.on_embedded_quest_progress_changed
        )

        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setStretchFactor(2, 1)
        self.splitter.setSizes([245, 315, 640])

        self.apply_local_style()
        self.populate_categories()
        self.refresh()

    @staticmethod
    def _panel(object_name: str, title: str) -> QFrame:
        panel = QFrame()
        panel.setObjectName(object_name)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        label = QLabel(title)
        label.setObjectName("GuideSectionTitle")
        layout.addWidget(label)
        return panel

    def apply_local_style(self) -> None:
        self.setStyleSheet(
            render_theme_template(
                """
                QWidget#AchievementsView {
                    background: @BG;
                }

                QWidget#AchievementsView QLineEdit#EncyclopediaSearch {
                    background: @PANEL;
                    border: 1px solid @BORDER;
                    border-radius: @RADIUS_MD;
                    color: @TEXT;
                    min-height: 32px;
                    max-height: 32px;
                    padding: 0px 10px;
                    selection-background-color: @GREEN_DARK;
                }

                QWidget#AchievementsView QLineEdit#EncyclopediaSearch:focus {
                    border-color: @GREEN;
                }

                QWidget#AchievementsView QFrame#GuideLeftPanel,
                QWidget#AchievementsView QFrame#GuideCenterPanel,
                QWidget#AchievementsView QStackedWidget#AchievementDetailStack {
                    background: @PANEL;
                    border: 1px solid @BORDER;
                    border-radius: @RADIUS_MD;
                }

                QWidget#AchievementsView QLabel#GuideSectionTitle {
                    color: @YELLOW;
                    font-size: 12px;
                    font-weight: 800;
                    padding: 1px 2px 6px 2px;
                }

                QWidget#AchievementsView QTreeWidget#AchievementCategoryTree,
                QWidget#AchievementsView QListWidget#QuestResultList {
                    background: transparent;
                    border: none;
                    color: @TEXT_SOFT;
                    outline: none;
                    show-decoration-selected: 0;
                }

                QWidget#AchievementsView QTreeWidget#AchievementCategoryTree::item {
                    min-height: 30px;
                    margin: 1px 0px;
                    padding: 3px 7px;
                    border: 1px solid transparent;
                    border-radius: @RADIUS_SM;
                }

                QWidget#AchievementsView QTreeWidget#AchievementCategoryTree::item:hover {
                    background: @PANEL_HOVER;
                    border-color: @BORDER_SOFT;
                }

                QWidget#AchievementsView QTreeWidget#AchievementCategoryTree::item:selected {
                    background: @PANEL_ACTIVE;
                    border: 1px solid @GREEN_BORDER;
                    border-left: 3px solid @GREEN;
                    color: @TEXT;
                }

                QWidget#AchievementsView QListWidget#QuestResultList::item {
                    background: @PANEL_2;
                    border: 1px solid @BORDER_SOFT;
                    border-radius: @RADIUS_SM;
                    color: @TEXT_SOFT;
                    min-height: 48px;
                    margin: 2px 0px;
                    padding: 6px 10px;
                }

                QWidget#AchievementsView QListWidget#QuestResultList::item:hover {
                    background: @PANEL_HOVER;
                    border-color: @BORDER_STRONG;
                }

                QWidget#AchievementsView QListWidget#QuestResultList::item:selected {
                    background: @PANEL_ACTIVE;
                    border: 1px solid @GREEN_BORDER;
                    border-left: 3px solid @GREEN;
                }

                QWidget#AchievementsView QStackedWidget#AchievementDetailStack,
                QWidget#AchievementsView QScrollArea#GuideRightPanelScroll,
                QWidget#AchievementsView QWidget#AchievementDetailContent {
                    background: @PANEL;
                }

                QWidget#AchievementsView QScrollArea#GuideRightPanelScroll {
                    border: none;
                    border-radius: @RADIUS_MD;
                }

                QWidget#AchievementsView QFrame#AchievementDetailBody {
                    background: transparent;
                    border: none;
                }

                QWidget#AchievementsView QFrame#AchievementAlignmentPanel {
                    background: @PANEL_2;
                    border: 1px solid @BORDER_SOFT;
                    border-radius: @RADIUS_SM;
                }

                QWidget#AchievementsView QLabel#AchievementDetailTitle {
                    color: @TEXT;
                    font-size: 18px;
                    font-weight: 800;
                    padding: 0px 0px 2px 0px;
                }

                QWidget#AchievementsView QLabel#AchievementDescription {
                    color: @TEXT_SOFT;
                    font-size: 12px;
                    padding: 0px 0px 2px 0px;
                }

                QWidget#AchievementsView QLabel#AchievementProgressText {
                    color: @TEXT_MUTED;
                    font-size: 11px;
                    font-weight: 700;
                }

                QWidget#AchievementsView QLabel#AchievementSectionTitle {
                    color: @YELLOW;
                    font-size: 11px;
                    font-weight: 800;
                    padding: 5px 1px 1px 1px;
                }

                QWidget#AchievementsView QCheckBox#AchievementDoneCheck {
                    color: @TEXT_SOFT;
                    font-weight: 700;
                    spacing: 7px;
                }

                QWidget#AchievementsView QCheckBox#AchievementDoneCheck:checked {
                    color: @GREEN;
                }

                QWidget#AchievementsView QFrame#EntityLinksPanel {
                    background: transparent;
                    border: none;
                    border-radius: 0px;
                }

                QWidget#AchievementsView QFrame#AchievementEntityRow,
                QWidget#AchievementsView QFrame#ObjectiveRow {
                    background: @PANEL_2;
                    border: 1px solid @BORDER_SOFT;
                    border-radius: @RADIUS_SM;
                }

                QWidget#AchievementsView QFrame#AchievementEntityRow:hover,
                QWidget#AchievementsView QFrame#ObjectiveRow:hover {
                    background: @PANEL_HOVER;
                    border-color: @GREEN_BORDER;
                }

                QWidget#AchievementsView QLabel#AchievementEntityRowText {
                    color: @TEXT_SOFT;
                }

                QWidget#AchievementsView QLabel#AchievementEntityChevron {
                    color: @TEXT_MUTED;
                    font-size: 18px;
                    font-weight: 700;
                }

                QWidget#AchievementsView QFrame#AchievementEntityRow:hover QLabel#AchievementEntityChevron {
                    color: @GREEN;
                }

                QWidget#AchievementsView QProgressBar#EncyclopediaProgressBar {
                    background: @BG;
                    border: 1px solid @BORDER_SOFT;
                    border-radius: 4px;
                    min-height: 8px;
                    max-height: 8px;
                }

                QWidget#AchievementsView QProgressBar#EncyclopediaProgressBar::chunk {
                    background: @GREEN;
                    border-radius: 3px;
                }

                QWidget#AchievementsView QSplitter#AchievementCatalogSplitter::handle {
                    background: transparent;
                    width: 6px;
                }
                """
            )
        )

    def populate_categories(self) -> None:
        self.category_tree.blockSignals(True)
        self.category_tree.clear()
        self._tree_items.clear()
        first_item: QTreeWidgetItem | None = None
        for category in self.provider.get_retained_categories():
            top_item = QTreeWidgetItem([f"{category.name}  ({len(self.provider.get_by_category(category.id))})"])
            top_font = top_item.font(0)
            top_font.setBold(True)
            top_item.setFont(0, top_font)
            top_item.setToolTip(0, category.name)
            top_item.setData(0, CATEGORY_ROLE, category.id)
            top_item.setData(0, TOP_CATEGORY_ROLE, category.id)
            self.category_tree.addTopLevelItem(top_item)
            self._tree_items[category.id] = top_item
            if first_item is None:
                first_item = top_item
            for subcategory in self.provider.get_subcategories(category.id):
                child = QTreeWidgetItem([f"{subcategory.name}  ({len(self.provider.get_by_category(subcategory.id))})"])
                child.setToolTip(0, subcategory.name)
                child.setData(0, CATEGORY_ROLE, subcategory.id)
                child.setData(0, TOP_CATEGORY_ROLE, category.id)
                top_item.addChild(child)
                self._tree_items[subcategory.id] = child
            top_item.setExpanded(top_item is first_item)
        if first_item is not None:
            self.selected_category_id = int(first_item.data(0, CATEGORY_ROLE))
            self.category_tree.setCurrentItem(first_item)
        self.category_tree.blockSignals(False)

    def sync_automatic_progress(self) -> bool:
        if not is_character_key(self.character_key):
            return False
        return self.progress_service.sync_from_quest_progress(
            self.character_key,
            self.provider,
            self.quest_progress_service,
            self.guide_provider,
        )

    def set_character_key(self, character_key: str) -> None:
        self.character_key = character_key or ""
        self.quest_progress_service.reload()
        self.sync_automatic_progress()
        self.quest_detail_view.set_character_key(self.character_key)
        self.refresh_completion_styles()
        if self.detail_stack.currentWidget() is self.quest_detail_page:
            self.quest_detail_view.refresh()
        elif self._detail_open and self.current_achievement_id is not None:
            self.show_achievement(self.current_achievement_id)


    def on_embedded_quest_progress_changed(self, _quest_id: int) -> None:
        """Refresh only achievement state derived from the shared quest mutation."""

        self.quest_progress_service.reload()
        self.sync_automatic_progress()
        self.refresh_completion_styles()



    def on_achievement_completion_changed(self, achievement_id: int, completed: bool) -> None:
        _ = completed
        self.refresh_completion_styles()

    def category_label(self, category_id: int | None) -> str:
        if category_id is None:
            return "catalogue"
        item = self._tree_items.get(int(category_id))
        if item is None:
            return "catalogue"
        return item.text(0).rsplit("  (", 1)[0]

    def on_category_changed(self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        value = current.data(0, CATEGORY_ROLE)
        if value is None:
            return
        self.selected_category_id = int(value)
        if self.search.text():
            self.search.clear()
        else:
            self.refresh()

    def select_achievement(self, achievement_id: int) -> bool:
        achievement = self.provider.get_by_id(int(achievement_id))
        if achievement is None or not self.provider.is_retained(achievement.id):
            return False
        target_category_id = achievement.subcategory_id or achievement.category_id
        tree_item = self._tree_items.get(target_category_id)
        if tree_item is not None:
            if tree_item.parent() is not None:
                tree_item.parent().setExpanded(True)
            self.category_tree.setCurrentItem(tree_item)
        if self.search.text():
            self.search.clear()
        for row, candidate in enumerate(self.filtered):
            if candidate.id == achievement.id:
                self.list_widget.setCurrentRow(row)
                self.show_achievement(achievement.id)
                return True
        return False

    def on_achievement_clicked(self, item: QListWidgetItem) -> None:
        achievement_id = item.data(Qt.UserRole)
        if achievement_id is None:
            return
        achievement_id = int(achievement_id)
        if self._detail_open and self.current_achievement_id == achievement_id:
            self.close_detail_panel()
            return
        self.show_achievement(achievement_id)

    def show_achievement(self, achievement_id: int) -> None:
        achievement = self.provider.get_by_id(int(achievement_id))
        if achievement is None or not self.provider.is_retained(achievement.id):
            self.show_empty()
            return
        self.current_achievement_id = achievement.id
        self._detail_open = True
        self.detail_stack.setCurrentWidget(self.detail_scroll)
        self.clear_detail()
        (
            objective_completion_overrides,
            readonly_objective_ids,
            objective_entity_overrides,
            objective_text_overrides,
        ) = self.alignment_tracking_overrides(achievement)
        if achievement.id in ALIGNMENT_ORDER_ACHIEVEMENT_RANKS:
            self.detail_layout.addWidget(self.build_alignment_order_panel())
        self.detail_layout.addWidget(
            AchievementDetailWidget(
                achievement,
                self.progress_service,
                self.character_key,
                navigate_callback=self.open_linked_entity,
                linked_quests=self.effective_quest_refs(achievement),
                linked_monsters=achievement.resolved_linked_monsters,
                linked_dungeons=achievement.resolved_linked_dungeons,
                objective_completion_overrides=objective_completion_overrides,
                readonly_objective_ids=readonly_objective_ids,
                objective_entity_overrides=objective_entity_overrides,
                objective_text_overrides=objective_text_overrides,
                completion_changed_callback=lambda completed, achievement_id=achievement.id: self.on_achievement_completion_changed(
                    achievement_id, completed
                ),
            )
        )
        self.detail_layout.addStretch(1)
        self.status_callback(f"Succès : {achievement.name}")

    def build_alignment_order_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("AchievementAlignmentPanel")
        panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(9, 8, 9, 8)
        layout.setSpacing(6)

        title = QLabel("ORDRE D'ALIGNEMENT")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)
        help_label = QLabel(
            "Choisissez une seule branche. Le suivi affiche uniquement les cinq quêtes de cet Ordre, dans leur ordre réel."
        )
        help_label.setObjectName("MutedLabel")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        combo = QComboBox()
        combo.setObjectName("AchievementAlignmentOrderCombo")
        combo.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        combo.setMinimumContentsLength(16)
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.addItem("Choisir un Ordre...", None)
        for side, orders in ORDER_QUEST_IDS.items():
            city = "Bonta" if side == "bonta" else "Brâkmar"
            for order_name in orders:
                combo.addItem(f"{city} · {order_name}", (side, order_name))
        choice = self.valid_alignment_choice()
        if choice is not None:
            for index in range(1, combo.count()):
                if combo.itemData(index) == choice:
                    combo.setCurrentIndex(index)
                    break
        combo.currentIndexChanged.connect(lambda _index: self.on_alignment_choice_changed(combo.currentData()))
        layout.addWidget(combo)

        if choice is None:
            missing = QLabel("Aucune branche n'est comptée tant qu'un Ordre n'est pas sélectionné.")
            missing.setObjectName("MutedLabel")
            missing.setWordWrap(True)
            layout.addWidget(missing)
            self.add_alignment_guide_button(layout, "bonta")
            self.add_alignment_guide_button(layout, "brakmar")
            return panel

        side, order_name = choice
        self.add_alignment_guide_button(layout, side)

        quest_ids = ORDER_QUEST_IDS[side][order_name]
        done = 0
        for rank, quest_id in enumerate(quest_ids, 1):
            quest = self.quest_provider.get_quest(int(quest_id))
            if quest is None:
                continue
            completed = self.quest_progress_service.is_quest_completed(self.character_key, int(quest_id))
            done += int(completed)
            marker = "✓" if completed else "○"
            link = AchievementEntityRow(EntityRef("quest", int(quest_id), f"{marker} Rang {rank} · {quest.name}"))
            link.entityActivated.connect(self.on_alignment_quest_activated)
            layout.addWidget(link)
        progress = QLabel(f"Progression de l'Ordre · {done} / 5 quêtes")
        progress.setObjectName("MutedLabel")
        layout.addWidget(progress)
        return panel

    def add_alignment_guide_button(self, layout: QVBoxLayout, side: str) -> None:
        city = "Bonta" if side == "bonta" else "Brâkmar"
        guide_button = AtlasButton(f"Ouvrir le Guide Alignement {city}")
        guide_button.setObjectName("GuideBreadcrumbButton")
        guide_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        guide_button.clicked.connect(
            lambda _checked=False, guide_id=ALIGNMENT_GUIDE_IDS[side]: self.open_guide(guide_id)
        )
        layout.addWidget(guide_button, 0, Qt.AlignLeft)

    def valid_alignment_choice(self) -> tuple[str, str] | None:
        choice = self.progress_service.alignment_order_choice(self.character_key)
        if choice is None:
            return None
        side, order_name = choice
        if order_name not in ORDER_QUEST_IDS.get(side, {}):
            return None
        return side, order_name

    def alignment_tracking_overrides(
        self,
        achievement: Achievement,
    ) -> tuple[dict[int, bool], set[int], dict[int, EntityRef], dict[int, str]]:
        rank = ALIGNMENT_ORDER_ACHIEVEMENT_RANKS.get(achievement.id)
        if rank is None:
            return {}, set(), {}, {}
        rank_objective = next(
            (
                objective
                for objective in achievement.objectives
                if str(objective.objective_type).casefold() == "critère pr"
            ),
            None,
        )
        if rank_objective is None:
            return {}, set(), {}, {}

        objective_id = int(rank_objective.id)
        readonly = {objective_id}
        choice = self.valid_alignment_choice()
        if choice is None:
            return (
                {objective_id: False},
                readonly,
                {},
                {objective_id: f"{rank_objective.text} · choisissez un Ordre"},
            )

        side, order_name = choice
        quest_id = int(ORDER_QUEST_IDS[side][order_name][rank - 1])
        quest = self.quest_provider.get_quest(quest_id)
        if quest is None:
            return {objective_id: False}, readonly, {}, {}
        completed = self.quest_progress_service.is_quest_completed(self.character_key, quest_id)
        return (
            {objective_id: completed},
            readonly,
            {objective_id: EntityRef("quest", quest_id, quest.name)},
            {objective_id: f"{rank_objective.text} · {quest.name}"},
        )

    def on_alignment_choice_changed(self, choice: object) -> None:
        if choice is None:
            self.progress_service.clear_alignment_order_choice(self.character_key)
            self.sync_automatic_progress()
            self.refresh_completion_styles()
            self.show_current_achievement()
            return
        if not isinstance(choice, tuple) or len(choice) != 2:
            return
        side, order_name = str(choice[0]), str(choice[1])
        if order_name not in ORDER_QUEST_IDS.get(side, {}):
            return
        self.progress_service.set_alignment_order_choice(self.character_key, side, order_name)
        self.sync_automatic_progress()
        self.refresh_completion_styles()
        self.show_current_achievement()

    def effective_quest_refs(self, achievement: Achievement) -> tuple[EntityRef, ...]:
        rank = ALIGNMENT_ORDER_ACHIEVEMENT_RANKS.get(achievement.id)
        if rank is None:
            return achievement.resolved_linked_quests
        choice = self.valid_alignment_choice()
        if choice is None:
            return ()
        side, order_name = choice
        quest_ids = ORDER_QUEST_IDS[side][order_name]
        quest_id = int(quest_ids[rank - 1])
        quest = self.quest_provider.get_quest(quest_id)
        if quest is None:
            return ()
        return (EntityRef("quest", quest_id, quest.name),)

    def _achievement_ordered_quest_ids(self) -> tuple[int, ...]:
        achievement_id = self.current_achievement_id
        if achievement_id is None:
            return ()
        achievement = self.provider.get_by_id(int(achievement_id))
        if achievement is None:
            return ()

        ordered: list[int] = []
        seen: set[int] = set()
        for ref in self.effective_quest_refs(achievement):
            try:
                quest_id = int(getattr(ref, "entity_id"))
            except (TypeError, ValueError):
                continue
            if quest_id <= 0 or quest_id in seen:
                continue
            if self.quest_provider.get_quest(quest_id) is None:
                continue
            seen.add(quest_id)
            ordered.append(quest_id)
        return tuple(ordered)

    def show_empty(self) -> None:
        self.current_achievement_id = None
        self.close_detail_panel()

    def show_quest(self, quest_id: int) -> bool:
        return self.open_quest_in_quests(int(quest_id))


    def show_current_achievement(self) -> None:
        if self.current_achievement_id is not None:
            self.show_achievement(self.current_achievement_id)

    def on_alignment_quest_activated(self, entity_type: str, entity_id: object) -> None:
        if str(entity_type) == "quest":
            self.open_quest_in_quests(int(entity_id))

    def open_guide(self, guide_id: str) -> bool:
        if self.navigate_callback is None:
            return False
        return bool(self.navigate_callback("guide", guide_id, source="achievement"))

    def open_linked_entity(self, entity_type: str, entity_id: int) -> bool:
        if str(entity_type) == "quest":
            return self.open_quest_in_quests(int(entity_id))
        if str(entity_type) == "achievement":
            return self.select_achievement(int(entity_id))
        if self.navigate_callback is None:
            return False
        return bool(self.navigate_callback(str(entity_type), int(entity_id), source="achievement"))

    def open_prerequisite_in_quests(self, quest_id: int) -> bool:
        if self.navigate_callback is None:
            return False
        return bool(
            self.navigate_callback(
                "quest",
                int(quest_id),
                source="achievement_prerequisite",
                achievement_id=self.current_achievement_id,
            )
        )

    def open_shared_entity(self, entity_type: str, entity_id: int | str, **_context: object) -> bool:
        if str(entity_type) == "achievement":
            return self.select_achievement(int(entity_id))
        if str(entity_type) == "quest":
            return self.open_quest_in_quests(int(entity_id))
        if self.navigate_callback is None:
            return False
        return bool(self.navigate_callback(str(entity_type), entity_id, source="achievement"))

    def close_detail_panel(self) -> None:
        self._detail_open = False
        self.detail_stack.setCurrentWidget(self.detail_scroll)
        self.clear_detail()

    def clear_detail(self) -> None:
        while self.detail_layout.count():
            item = self.detail_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def __init__(self, *args, **kwargs) -> None:
        self._catalog_refresh_signature: tuple[object, ...] | None = None
        self._achievement_render_generation = 0
        self._achievement_pending_rows: list[tuple[int, str, str]] = []
        self._achievement_pending_selected_id: int | None = None
        self._achievement_rows_dirty = False
        self._achievement_completed_ids: frozenset[int] = frozenset()
        self._achievement_batch_timer: QTimer | None = None
        self._achievement_initializing = True
        self._initialize_achievements_view(*args, **kwargs)
        self._achievement_initializing = False

        # The Success search belongs to the tab content, not to the tab bar.
        # Keep a stable visual gutter so lazy tab swaps never make both rows
        # appear to overlap or touch.
        root = self.layout()
        if root is not None:
            margins = root.contentsMargins()
            root.setContentsMargins(
                margins.left(),
                max(8, margins.top()),
                margins.right(),
                margins.bottom(),
            )

        self._catalog_refresh_signature = self._current_catalog_signature()
        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(_SEARCH_DEBOUNCE_MS)
        self._search_debounce_timer.timeout.connect(self.refresh)
        try:
            self.search.textChanged.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.search.textChanged.connect(lambda _text: self._search_debounce_timer.start())

        batch_timer = QTimer(self)
        batch_timer.setSingleShot(True)
        batch_timer.setInterval(0)
        batch_timer.timeout.connect(self._render_next_achievement_batch)
        self._achievement_batch_timer = batch_timer
        if self.isVisible() and self._achievement_rows_dirty:
            batch_timer.start()

    def _current_catalog_signature(self) -> tuple[object, ...]:
        search = getattr(self, "search", None)
        query = normalize_text(search.text()) if search is not None else ""
        return (int(self.selected_category_id) if self.selected_category_id is not None else None, query)

    def _filtered_achievements(self):
        query = normalize_text(self.search.text())
        tokens = [token for token in query.split("_") if token]
        if tokens:
            candidates = self.achievements
        elif self.selected_category_id is not None:
            candidates = self.provider.get_by_category(self.selected_category_id)
        else:
            candidates = self.achievements
        filtered = [
            achievement
            for achievement in candidates
            if self.provider.is_retained(achievement.id)
            and (not tokens or all(token in achievement.search_text for token in tokens))
        ]
        return filtered, tokens

    @staticmethod
    def _achievement_row_text(achievement) -> str:
        meta: list[str] = []
        if achievement.level is not None:
            meta.append(f"Niveau {achievement.level}")
        if achievement.points:
            meta.append(f"{achievement.points} pt{'s' if achievement.points > 1 else ''}")
        text = achievement.name
        if meta:
            text = f"{text}\n{'  ·  '.join(meta)}"
        return text

    def refresh(self) -> None:
        signature = self._current_catalog_signature()
        if (
            not self._achievement_initializing
            and self._catalog_refresh_signature == signature
            and not self._achievement_rows_dirty
            and not self._achievement_pending_rows
            and hasattr(self, "list_widget")
            and self.list_widget.count() > 0
        ):
            return

        self.close_detail_panel()
        filtered, tokens = self._filtered_achievements()
        self.filtered = filtered
        previous_id = self.current_achievement_id
        selected_id = previous_id if any(row.id == previous_id for row in filtered) else (filtered[0].id if filtered else None)

        self._achievement_render_generation += 1
        self._achievement_pending_selected_id = int(selected_id) if selected_id is not None else None
        self._achievement_completed_ids = frozenset(
            int(value) for value in self.progress_service.state_for(self.character_key).completed_achievements
        )
        self._achievement_pending_rows = [
            (int(achievement.id), self._achievement_row_text(achievement), achievement.name)
            for achievement in filtered
        ]
        self._achievement_rows_dirty = bool(self._achievement_pending_rows)

        timer = self._achievement_batch_timer
        if timer is not None:
            timer.stop()
        if hasattr(self, "list_widget"):
            self.list_widget.clear()

        if not filtered:
            self.show_empty()
        else:
            self.current_achievement_id = self._achievement_pending_selected_id

        scope = "recherche globale" if tokens else self.category_label(self.selected_category_id)
        self.status_callback(f"Succès · {scope} : {len(self.filtered)}")
        self._catalog_refresh_signature = signature

        # During the base constructor and while the tab is hidden, keep only the
        # lightweight filtered snapshot. The first visible paint can happen
        # before hundreds of QListWidgetItem objects are materialized.
        if not self._achievement_rows_dirty or self._achievement_initializing or not self.isVisible():
            return
        if timer is not None:
            timer.start()

    def _render_next_achievement_batch(self) -> None:
        if not self.isVisible() or not self._achievement_pending_rows:
            self._achievement_rows_dirty = bool(self._achievement_pending_rows)
            return

        generation = self._achievement_render_generation
        batch = self._achievement_pending_rows[:_RESULT_BATCH_SIZE]
        del self._achievement_pending_rows[:_RESULT_BATCH_SIZE]
        done_color = self.palette().color(QPalette.Disabled, QPalette.Text)
        todo_color = self.palette().color(QPalette.Active, QPalette.Text)

        self.list_widget.blockSignals(True)
        try:
            for achievement_id, text, tooltip in batch:
                if generation != self._achievement_render_generation:
                    return
                completed = achievement_id in self._achievement_completed_ids
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, achievement_id)
                item.setToolTip(tooltip)
                item.setForeground(done_color if completed else todo_color)
                item.setData(COMPLETED_ROLE, completed)
                self.list_widget.addItem(item)
        finally:
            self.list_widget.blockSignals(False)

        if generation != self._achievement_render_generation:
            return
        if self._achievement_pending_rows:
            timer = self._achievement_batch_timer
            if timer is not None:
                timer.start()
            return

        self._achievement_rows_dirty = False
        selected_id = self._achievement_pending_selected_id
        if selected_id is not None:
            for row in range(self.list_widget.count()):
                item = self.list_widget.item(row)
                if int(item.data(Qt.UserRole) or 0) == int(selected_id):
                    self.list_widget.setCurrentRow(row)
                    break

    def showEvent(self, event) -> None:
        super().showEvent(event)
        timer = self._achievement_batch_timer
        if self._achievement_rows_dirty and timer is not None and not timer.isActive():
            timer.start()

    def refresh_completion_styles(self) -> None:
        """Project one immutable completion snapshot across visible and pending rows."""

        state = self.progress_service.state_for(self.character_key)
        completed_ids = frozenset(int(value) for value in state.completed_achievements)
        self._achievement_completed_ids = completed_ids
        done_color = self.palette().color(QPalette.Disabled, QPalette.Text)
        todo_color = self.palette().color(QPalette.Active, QPalette.Text)
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            achievement_id = item.data(Qt.UserRole)
            if achievement_id is None:
                continue
            completed = int(achievement_id) in completed_ids
            item.setForeground(done_color if completed else todo_color)
            item.setData(COMPLETED_ROLE, completed)

    def open_quest_in_quests(self, quest_id: int) -> bool:
        """Leave Succès and open the shared Quêtes page for linked quests."""

        try:
            quest_id = int(quest_id)
        except (TypeError, ValueError):
            return False
        if self.quest_provider.get_quest(quest_id) is None or self.navigate_callback is None:
            return False
        return bool(
            self.navigate_callback(
                "quest",
                quest_id,
                source="achievement_link",
                achievement_id=self.current_achievement_id,
            )
        )

    def refresh_external_progress(self) -> None:
        if not self.quest_progress_service.refresh_if_changed():
            return
        self.sync_automatic_progress()
        self.refresh_completion_styles()
        if self.detail_stack.currentWidget() is self.quest_detail_page:
            self.quest_detail_view.refresh()
        elif self._detail_open and self.current_achievement_id is not None:
            self.show_achievement(self.current_achievement_id)
