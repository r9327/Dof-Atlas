from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
    QListWidgetItem, QScrollArea, QVBoxLayout, QWidget,
)
from app.ui.theme import PALETTE
from app.modules.encyclopedia.views.guide_featured_home import (
    FEATURED, FeaturedGuideCard, FeaturedPair,
)
from app.modules.encyclopedia.views.guide_library_sources import (
    CATEGORIES, displayable_listings, load_ganymede_listings,
)

from app.modules.encyclopedia.services.guide_catalog_hints import (
    catalog_route_map_count_hint,
)
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.widgets.guide_card import (
    GUIDE_ID_ROLE,
    GuideCardDelegate,
    GuideHomeColumns,
    GuideListModel,
)

GUIDE_SUCCESS_CATALOG_ID = "guide_complet"
GUIDE_ULTIME_TITLE = "Guide Ultime"
CATALOG_MANUAL_GUIDE_IDS = frozenset({"dofus_sylvestre"})


class GuideCatalogView(QWidget):
    """Small Guide catalogue surface; rich Guide UI is imported on selection only."""

    guideRequested = Signal(str)
    achievementRuntimeRequested = Signal()

    CATALOG = "catalog"
    QUEST_DETAIL = "quest_detail"

    def __init__(
        self,
        status_callback,
        *,
        provider,
        quest_progress_path,
        character_key: str = "",
        initial_progress_by_guide: dict[str, tuple[int, int, str]] | None = None,
        initial_progress_character_key: str = "",
        graph=None,
        achievement_provider=None,
        quest_provider=None,
        defer_runtime: bool = False,
        **_kwargs,
    ) -> None:
        super().__init__()
        self.setObjectName("GuidesView")
        self.status_callback = status_callback
        self.provider = provider
        self.quest_progress_path = quest_progress_path
        self.current_character_key = str(character_key or "")
        self.current_guide_id: str | None = None
        self.current_quest_id: int | None = None
        self.state = self.CATALOG
        self.graph = graph
        self.achievement_provider = achievement_provider
        self.quest_provider = quest_provider
        self._runtime_ready = False
        self.search_text = ""
        self.guides = []
        self.visible_guides = []
        self.ganymede_listings = ()
        self.library_category = "dofus"
        self._initial_progress_by_guide = dict(initial_progress_by_guide or {})
        self._initial_progress_character_key = str(initial_progress_character_key or "")

        # Outer scrolling is only for genuinely small windows; each catalogue
        # view keeps its own scrolling for large inventories.
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.home_scroll = QScrollArea(self)
        self.home_scroll.setWidgetResizable(True)
        self.home_scroll.setFrameShape(QFrame.NoFrame)
        self.home_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget(self.home_scroll)
        root = QVBoxLayout(content)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        self.home_scroll.setWidget(content)
        shell.addWidget(self.home_scroll, 1)

        def heading(text: str) -> QLabel:
            label = QLabel(text)
            label.setStyleSheet(
                f"color: {PALETTE['TEXT']}; font-size: 13px; font-weight: 800;"
            )
            return label

        # Main focus: two genuinely large optimized cards and two alignments.
        # These four cards remain visible even while the library is searched.
        self.featured_cards = {
            guide_id: FeaturedGuideCard(guide_id, title, self.select_guide, self)
            for guide_id, title in FEATURED
        }
        root.addWidget(heading("GUIDES OPTIMISÉS"))
        self.optimized_pair = FeaturedPair(
            (self.featured_cards["guide_complet"],
             self.featured_cards["dofus_sylvestre"]), self
        )
        root.addWidget(self.optimized_pair)
        root.addWidget(heading("ALIGNEMENTS"))
        self.alignments_pair = FeaturedPair(
            (self.featured_cards["alignement_bonta"],
             self.featured_cards["alignement_brakmar"]), self
        )
        root.addWidget(self.alignments_pair)

        search_row = QHBoxLayout()
        search_row.addWidget(heading("EXPLORER LES GUIDES"))
        search_row.addStretch(1)
        self.library_search = QLineEdit(self)
        self.library_search.setObjectName("GuideLibrarySearch")
        self.library_search.setPlaceholderText("Rechercher un guide…")
        self.library_search.setClearButtonEnabled(True)
        self.library_search.setMaximumWidth(270)
        self.library_search.textChanged.connect(self.set_search_text)
        search_row.addWidget(self.library_search)
        root.addLayout(search_row)

        # Preserve the legacy model roles for integrations and external progress.
        self.result_model = GuideListModel(self)
        self.home_dofus_model = GuideListModel(self)
        self.home_list = QListView(self)
        self.home_list.setModel(self.result_model)
        self.home_list.setVisible(False)

        self.home_dofus_list = QListView(self)
        self.home_dofus_list.setObjectName("GuidesHomeDofusGrid")
        self.home_dofus_list.setModel(self.home_dofus_model)
        self.home_dofus_list.setItemDelegate(GuideCardDelegate(self.home_dofus_list))
        self.home_dofus_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.home_dofus_list.setMouseTracking(True)
        self.home_dofus_list.setViewMode(QListView.IconMode)
        self.home_dofus_list.setFlow(QListView.LeftToRight)
        self.home_dofus_list.setWrapping(True)
        self.home_dofus_list.setResizeMode(QListView.Adjust)
        self.home_dofus_list.setGridSize(QSize(280, 96))
        self.home_dofus_list.clicked.connect(self._on_clicked)
        self.home_dofus_list.activated.connect(self._on_clicked)

        self.library_categories = QListWidget(self)
        self.library_categories.setObjectName("GuideLibraryCategories")
        self.library_categories.setMaximumWidth(235)
        for category_key, text in CATEGORIES:
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, category_key)
            self.library_categories.addItem(item)
        self.library_categories.setCurrentRow(0)
        self.library_categories.currentRowChanged.connect(self._on_category_changed)

        self.library_right = QWidget(self)
        result_layout = QVBoxLayout(self.library_right)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(6)
        self.library_results_title = heading("DOFUS")
        result_layout.addWidget(self.library_results_title)

        self.library_filter = QComboBox(self)
        self.library_filter.setObjectName("GuideLibraryProgressFilter")
        self.library_filter.addItems(("Tous", "En cours", "Terminés"))
        self.library_filter.currentIndexChanged.connect(lambda _idx: self.refresh_home())
        result_layout.addWidget(self.library_filter)

        result_layout.addWidget(self.home_dofus_list, 1)
        self.metadata_title = QLabel("Parcours Ganymède référencés · non jouables")
        self.metadata_title.setStyleSheet(f"color: {PALETTE['TEXT_MUTED']}; font-weight: 600;")
        result_layout.addWidget(self.metadata_title)
        self.home_metadata_list = QListWidget(self)
        self.home_metadata_list.setObjectName("GuideLibraryUnavailableList")
        self.home_metadata_list.setAlternatingRowColors(True)
        result_layout.addWidget(self.home_metadata_list, 1)

        self.home_empty = QLabel("Aucun guide ne correspond à la recherche.")
        self.home_empty.setObjectName("GuidesHomeEmptyText")
        self.home_empty.setAlignment(Qt.AlignCenter)
        self.home_empty.setVisible(False)
        result_layout.addWidget(self.home_empty, 1)

        self.home_columns = GuideHomeColumns(
            self.library_categories, self.library_right, self
        )
        root.addWidget(self.home_columns, 1)

        if defer_runtime:
            self._show_runtime_loading()
        else:
            self.hydrate_runtime(
                graph=graph,
                initial_progress_by_guide=initial_progress_by_guide,
                initial_progress_character_key=initial_progress_character_key,
            )

    def _show_runtime_loading(self) -> None:
        self.home_dofus_list.setVisible(False)
        self.home_metadata_list.setVisible(False)
        self.metadata_title.setVisible(False)
        self.home_empty.setText("Chargement des guides…")
        self.home_empty.setWordWrap(False)
        self.home_empty.setVisible(True)

    def show_runtime_error(self, message: str) -> None:
        self.home_dofus_list.setVisible(False)
        self.home_metadata_list.setVisible(False)
        self.metadata_title.setVisible(False)
        self.home_empty.setText(str(message or "Chargement des guides impossible."))
        self.home_empty.setWordWrap(True)
        self.home_empty.setVisible(True)

    def hydrate_runtime(
        self,
        *,
        graph=None,
        initial_progress_by_guide: dict[str, tuple[int, int, str]] | None = None,
        initial_progress_character_key: str = "",
    ) -> bool:
        if self._runtime_ready:
            return True
        guides = self.provider.load_all()
        if not guides:
            raise RuntimeError("Aucun guide chargé depuis catalog.json")
        self.graph = graph
        self.guides = list(guides)
        # Metadata are deliberately not playable Atlas guides.
        try:
            self.ganymede_listings = load_ganymede_listings()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.ganymede_listings = ()
            self.status_callback(f"Inventaire Ganymède indisponible : {exc}")
        if initial_progress_by_guide is not None:
            self._initial_progress_by_guide = dict(initial_progress_by_guide)
        if initial_progress_character_key:
            self._initial_progress_character_key = str(initial_progress_character_key)
        self._runtime_ready = True
        self.refresh_home()
        self.status_callback(f"{len(self.guides)} guide(s) chargés.")
        return True

    def _on_clicked(self, index) -> None:
        guide_id = index.data(GUIDE_ID_ROLE)
        if guide_id:
            self.select_guide(str(guide_id))

    def select_guide(self, guide_id: str) -> bool:
        guide_id = str(guide_id or "")
        if not guide_id:
            return False
        if not any(str(getattr(guide, "id", "")) == guide_id for guide in self.guides):
            return False
        self.current_guide_id = guide_id
        self.guideRequested.emit(guide_id)
        return True

    def set_search_text(self, text: str) -> None:
        text = str(text or "")
        if text == self.search_text:
            return
        self.search_text = text
        if self.library_search.text() != text:
            self.library_search.blockSignals(True)
            self.library_search.setText(text)
            self.library_search.blockSignals(False)
        if self._runtime_ready:
            self.refresh_home()

    def set_character_key(self, character_key: str) -> None:
        character_key = str(character_key or "")
        if character_key == self.current_character_key:
            return
        self.current_character_key = character_key
        self._initial_progress_by_guide = {}
        self._initial_progress_character_key = ""
        if self._runtime_ready:
            self.refresh_home()

    def refresh_external_progress(self) -> None:
        if not self._runtime_ready:
            return
        self._initial_progress_by_guide = {}
        self._initial_progress_character_key = ""
        self.refresh_home()

    def _progress_snapshot(self) -> dict[str, tuple[int, int, str]]:
        visible_ids = {str(getattr(guide, "id", "")) for guide in self.visible_guides}
        if (
            self._initial_progress_by_guide
            and self._initial_progress_character_key == self.current_character_key
            and visible_ids.issubset(self._initial_progress_by_guide)
        ):
            result = {
                guide_id: self._initial_progress_by_guide[guide_id]
                for guide_id in visible_ids
            }
            self._initial_progress_by_guide = {}
            return result

        completed_ids = QuestProgressService(
            self.quest_progress_path
        ).completed_quest_ids(self.current_character_key)
        compact_ids = getattr(self.provider, "progress_quest_ids_for", None)
        result: dict[str, tuple[int, int, str]] = {}
        for guide in self.visible_guides:
            guide_id = str(getattr(guide, "id", ""))
            if guide_id == GUIDE_SUCCESS_CATALOG_ID:
                result[guide_id] = (0, 0, "")
                continue
            raw_ids = (
                compact_ids(guide_id)
                if callable(compact_ids)
                else getattr(guide, "quest_ids", ())
            )
            ids: list[int] = []
            seen: set[int] = set()
            for raw_id in raw_ids or ():
                try:
                    quest_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                if quest_id in seen:
                    continue
                seen.add(quest_id)
                ids.append(quest_id)
            completed = sum(1 for quest_id in ids if quest_id in completed_ids)
            total = len(ids)
            state = (
                "Terminé"
                if total and completed >= total
                else "En cours"
                if completed
                else "Non commencé"
            )
            result[guide_id] = (completed, total, state)
        return result

    def _apply_catalog_overrides(self) -> None:
        self.result_model.set_title_override(
            GUIDE_SUCCESS_CATALOG_ID,
            GUIDE_ULTIME_TITLE,
        )
        for guide_id in CATALOG_MANUAL_GUIDE_IDS:
            count = int(catalog_route_map_count_hint(guide_id) or 0)
            if count <= 0:
                continue
            suffix = "map" if count == 1 else "maps"
            self.result_model.set_subtitle_override(
                guide_id,
                f"Parcours optimisé · {count} {suffix}",
            )

    def _on_category_changed(self, row: int) -> None:
        if row < 0:
            return
        item = self.library_categories.item(row)
        if item is None:
            return
        self.library_category = str(item.data(Qt.UserRole))
        if self._runtime_ready:
            self.refresh_home()

    def refresh_home(self) -> None:
        if not self._runtime_ready:
            return
        # Searching the library never hides the four prioritized guides.
        matched = list(self.provider.search(self.search_text))
        featured_ids = {id_ for id_, _name in FEATURED}
        catalog_by_id = {str(guide.id): guide for guide in self.guides}
        self.result_model.set_home_column(matched, "left")
        self._apply_catalog_overrides()

        shown_dofus = (
            [guide for guide in matched
             if guide.category == "dofus" and guide.id not in featured_ids]
            if self.library_category == "dofus" else []
        )
        # Limit progress IO to the four highlighted cards and the active grid.
        self.visible_guides = list({
            str(guide.id): guide for guide in
            [*(catalog_by_id[id_] for id_ in featured_ids if id_ in catalog_by_id),
             *shown_dofus]
        }.values())
        progress = self._progress_snapshot()
        self.result_model.set_progress(progress)
        for guide_id, _name in FEATURED:
            self.featured_cards[guide_id].set_guide(
                catalog_by_id.get(guide_id),
                progress.get(guide_id, (0, 0, "")),
            )

        chosen = self.library_filter.currentText()
        if chosen == "En cours":
            shown_dofus = [
                guide for guide in shown_dofus
                if 0 < progress.get(guide.id, (0, 0, ""))[0]
                < progress.get(guide.id, (0, 0, ""))[1]
            ]
        elif chosen == "Terminés":
            shown_dofus = [
                guide for guide in shown_dofus
                if progress.get(guide.id, (0, 0, ""))[1] > 0
                and progress.get(guide.id, (0, 0, ""))[0]
                >= progress.get(guide.id, (0, 0, ""))[1]
            ]
        self.home_dofus_model.set_home_column(shown_dofus, "right")
        self.home_dofus_model.set_progress(progress)

        category_label = dict(CATEGORIES).get(self.library_category, "Guides")
        self.library_results_title.setText(category_label.upper())
        self.library_filter.setVisible(self.library_category == "dofus")
        self.home_dofus_list.setVisible(bool(self.home_dofus_model.guides))

        # Metadata-only items must be disabled, never passed to select_guide().
        entries = displayable_listings(
            self.ganymede_listings, set(catalog_by_id),
            self.library_category, self.search_text,
        )
        if chosen != "Tous" and self.library_category == "dofus":
            # Unknown progress is never advertised as "in progress" or "done".
            entries = []
        self.home_metadata_list.clear()
        for entry in entries:
            level = f" · niveau {entry.level}" if entry.level is not None else ""
            steps = f" · {entry.step_count} étapes référencées" if entry.step_count is not None else ""
            item = QListWidgetItem(
                f"{entry.title}{level}{steps} · en préparation"
            )
            item.setFlags(Qt.NoItemFlags)
            item.setToolTip(
                f"Source : {entry.source_url}\n"
                "Métadonnées uniquement : aucune route jouable certifiée."
            )
            item.setData(Qt.UserRole, entry.source_id)
            self.home_metadata_list.addItem(item)

        has_metadata = bool(entries)
        self.metadata_title.setVisible(has_metadata)
        self.home_metadata_list.setVisible(has_metadata)
        empty = not shown_dofus and not has_metadata
        self.home_empty.setText("Aucun guide disponible pour cette recherche.")
        self.home_empty.setVisible(empty)


__all__ = ["GuideCatalogView"]
