from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, QUrlQuery, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QListView, QListWidget, QPushButton,
    QListWidgetItem, QScrollArea, QSpinBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from app.core.character_identity import is_character_key
from app.ui.theme import PALETTE
from app.ui.unity_skin import unity_enabled
from app.modules.encyclopedia.views.guide_featured_home import (
    FEATURED, FeaturedGuideCard, FeaturedPair,
)
from app.modules.encyclopedia.views.guide_library_sources import (
    ATLAS_EQUIVALENTS, CATEGORIES, displayable_listings, load_ganymede_listings,
)

from app.modules.encyclopedia.services.guide_catalog_hints import (
    catalog_route_map_count_hint,
)
from app.modules.encyclopedia.services.quest_progress_service import QuestProgressService
from app.modules.encyclopedia.services.guide_progress_service import (
    GUIDE_PROGRESS_FILE, GuideProgressService,
)
from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    active_manual_catalog_sources, manual_source_completed_count,
)
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
        self._ganymede_source_dialog = None
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
        content.setObjectName("GuidesHomeContent")
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

        # Exactly two highlighted guides; alignments remain in the browsable library.
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

        # Tree nodes are stable across refreshes: expansion is user-controlled.
        self.library_categories = QTreeWidget(self)
        self.library_categories.setObjectName("GuideLibraryCategories")
        self.library_categories.setHeaderHidden(True)
        self.library_categories.setIndentation(16)
        self.library_categories.setMaximumWidth(235)
        self._category_nodes = {}
        for category_key, text in CATEGORIES:
            node = QTreeWidgetItem((text,))
            node.setData(0, Qt.UserRole, category_key)
            self.library_categories.addTopLevelItem(node)
            self._category_nodes[category_key] = node
        self.library_categories.setCurrentItem(self._category_nodes["dofus"])
        self.library_categories.currentItemChanged.connect(self._on_category_changed)

        self.library_right = QWidget(self)
        self.library_right.setObjectName("GuideLibraryResults")
        result_layout = QVBoxLayout(self.library_right)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.setSpacing(6)
        self.library_results_title = heading("DOFUS")
        result_layout.addWidget(self.library_results_title)

        result_layout.addWidget(self.home_dofus_list, 1)
        self.metadata_title = QLabel("Parcours Ganymède en ligne")
        self.metadata_title.setStyleSheet(f"color: {PALETTE['TEXT_MUTED']}; font-weight: 600;")
        result_layout.addWidget(self.metadata_title)
        self.home_metadata_list = QListWidget(self)
        self.home_metadata_list.setObjectName("GuideLibraryUnavailableList")
        # Public source guides are readable on Ganymède, but their manual
        # steps are not imported and must never affect Atlas progress.
        # Avoid Qt's white alternating rows / faint disabled foreground on dark UI.
        self.home_metadata_list.setAlternatingRowColors(False)
        self.home_metadata_list.itemClicked.connect(self._open_ganymede_source_item)
        self.home_metadata_list.setMaximumHeight(148)
        # Keep the disabled metadata legible; unlike the default opaque Atlas
        # panel, the optional Unity skin leaves some of the sky visible.
        metadata_background = (
            "rgba(27, 39, 70, 0.88)"
            if unity_enabled() else PALETTE["PANEL"]
        )
        self.home_metadata_list.setStyleSheet(
            f"QListWidget#GuideLibraryUnavailableList {{ background: {metadata_background};"
            f" color: {PALETTE['TEXT_MUTED']}; border: 1px solid {PALETTE['BORDER']}; }}"
            f"QListWidget#GuideLibraryUnavailableList::item {{ padding: 4px 8px;"
            f" background: {metadata_background}; color: {PALETTE['TEXT_MUTED']}; }}"
            f"QListWidget#GuideLibraryUnavailableList::item:disabled {{"
            f" color: {PALETTE['TEXT_MUTED']}; }}"
        )
        result_layout.addWidget(self.home_metadata_list, 0)

        self.home_empty = QLabel("Aucun parcours disponible dans cette catégorie.")
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
        self._populate_library_tree()
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
        # Bonta/Brâkmar must open their actual Ganymède route instead of
        # displaying the old Atlas quest checklist. Keep the historic JSON
        # untouched until those routes have a verified offline replacement.
        if guide_id in {"alignement_bonta", "alignement_brakmar"}:
            source = next(
                (entry for entry in self.ganymede_listings
                 if ATLAS_EQUIVALENTS.get(entry.source_id) == guide_id),
                None,
            )
            if source is not None:
                target = QListWidgetItem(source.title)
                target.setData(Qt.UserRole, source.source_id)
                self._open_ganymede_source_item(target)
                return True
        self.current_guide_id = guide_id
        self.guideRequested.emit(guide_id)
        return True

    def set_search_text(self, text: str) -> None:
        """Retain the programmatic navigation contract without a search widget."""
        text = str(text or "")
        if text == self.search_text:
            return
        self.search_text = text
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
        manual_routes = active_manual_catalog_sources(self.provider, self.visible_guides)
        manual_progress = GuideProgressService(GUIDE_PROGRESS_FILE) if manual_routes else None
        compact_ids = getattr(self.provider, "progress_quest_ids_for", None)
        result: dict[str, tuple[int, int, str]] = {}
        for guide in self.visible_guides:
            guide_id = str(getattr(guide, "id", ""))
            if guide_id == GUIDE_SUCCESS_CATALOG_ID:
                result[guide_id] = (0, 0, "")
                continue
            if guide_id in manual_routes and manual_progress is not None:
                source_id, total = manual_routes[guide_id]
                done = manual_source_completed_count(
                    manual_progress, self.current_character_key,
                    guide_id, source_id, total,
                )
                state = (
                    "Choisir un personnage"
                    if not self.current_character_key
                    else "Terminé" if done == total
                    else "En cours" if done else "Non commencé"
                )
                result[guide_id] = (done, total, state)
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

    def _populate_library_tree(self) -> None:
        """Attach only real playable guides; metadata-only sources never launch."""
        for category in ("optimized", "alignements"):
            parent = self._category_nodes[category]
            parent.takeChildren()
            for guide in self.guides:
                is_optimized = guide.category == "aventure"
                if not (is_optimized if category == "optimized"
                        else guide.category == "alignements"):
                    continue
                title = dict(FEATURED).get(guide.id, guide.title)
                child = QTreeWidgetItem((title,))
                child.setData(0, Qt.UserRole + 1, str(guide.id))
                child.setToolTip(0, str(guide.title))
                parent.addChild(child)
            parent.setExpanded(True)

    def _on_category_changed(self, item: QTreeWidgetItem | None, _previous=None) -> None:
        if item is None:
            return
        guide_id = item.data(0, Qt.UserRole + 1)
        if guide_id:
            self.select_guide(str(guide_id))
            return
        category = item.data(0, Qt.UserRole)
        if not category:
            return
        self.library_category = str(category)
        if self._runtime_ready:
            self.refresh_home()

    def refresh_home(self) -> None:
        if not self._runtime_ready:
            return
        matched = list(self.provider.search(self.search_text))
        featured_ids = {guide_id for guide_id, _title in FEATURED}
        catalog_by_id = {str(guide.id): guide for guide in self.guides}
        self.result_model.set_home_column(matched, "left")
        self._apply_catalog_overrides()

        category = self.library_category
        if category == "optimized":
            shown_guides = [
                guide for guide in matched
                if guide.category == "aventure" and guide.id not in featured_ids
            ]
        else:
            shown_guides = [
                guide for guide in matched
                if guide.category == category and guide.id not in featured_ids
            ]

        # Read progress only for rendered cards; no eager per-guide widget creation.
        self.visible_guides = list({
            str(guide.id): guide for guide in
            [*(catalog_by_id[id_] for id_ in featured_ids if id_ in catalog_by_id),
             *shown_guides]
        }.values())
        progress = self._progress_snapshot()
        self.result_model.set_progress(progress)
        for guide_id, _title in FEATURED:
            self.featured_cards[guide_id].set_guide(
                catalog_by_id.get(guide_id), progress.get(guide_id, (0, 0, ""))
            )

        self.home_dofus_model.set_home_column(shown_guides, "catalog")
        self.home_dofus_model.set_progress(progress)
        self.library_results_title.setText(dict(CATEGORIES).get(category, "Guides").upper())
        self.home_dofus_list.setVisible(bool(shown_guides))

        # Hide only routes that already have a source-backed native reader,
        # plus Sylvestre Opti, which must remain unchanged. Legacy quest-only
        # guides do not hide their actual source route from the library.
        native = set(active_manual_catalog_sources(self.provider, self.guides))
        linked_alignment_ids = {
            guide_id for guide_id in ("alignement_bonta", "alignement_brakmar")
            if guide_id in catalog_by_id
        }
        entries = displayable_listings(
            self.ganymede_listings,
            native | {"dofus_sylvestre"} | linked_alignment_ids,
            category, self.search_text,
        )
        self.home_metadata_list.clear()
        for entry in entries:
            count = f" · {entry.step_count} étapes" if entry.step_count is not None else ""
            item = QListWidgetItem(f"{entry.title}{count} · lire")
            item.setToolTip(
                "Ouvrir les étapes originales sur Ganymède dans Atlas. "
                "La progression n'est pas synchronisée avec Atlas."
            )
            item.setData(Qt.UserRole, entry.source_id)
            self.home_metadata_list.addItem(item)

        has_metadata = bool(entries)
        self.metadata_title.setVisible(has_metadata)
        self.home_metadata_list.setVisible(has_metadata)
        if category == "optimized" and not shown_guides:
            # The two optimized routes are already shown as featured cards.
            self.home_empty.setVisible(False)
        else:
            self.home_empty.setText("Aucun parcours disponible dans cette catégorie.")
            self.home_empty.setVisible(not shown_guides and not has_metadata)
        self._sync_grid_columns()

    def _open_ganymede_source_item(self, item: QListWidgetItem) -> None:
        """Open public source steps in Atlas; store only user-approved step IDs."""
        source_id = item.data(Qt.UserRole)
        entry = next(
            (row for row in self.ganymede_listings if row.source_id == source_id),
            None,
        )
        if entry is None:
            return
        # The source inventory rejects forged paths and URL hosts up front.
        source_url = QUrl(entry.source_url)
        if (source_url.scheme() != "https"
                or source_url.host() != "ganymede-app.com"
                or source_url.path() != f"/guides/{entry.source_id}"):
            return
        if self._ganymede_source_dialog is not None:
            self._ganymede_source_dialog.close()
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.setObjectName("GanymedeSourceReader")
        dialog.setWindowTitle(f"Ganymède — {entry.title}")
        dialog.resize(950, 700)
        dialog.setMinimumSize(560, 400)
        layout = QVBoxLayout(dialog)
        notice = QLabel(
            "Étapes officielles en ligne : contenu fourni par Ganymède. "
            "Le suivi manuel des étapes est enregistré uniquement dans Atlas "
            "pour le personnage actuellement sélectionné.",
            dialog,
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        browser = None
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
        except ImportError:
            fallback = QLabel(
                "Lecteur web intégré indisponible. "
                "Le bouton « Navigateur » ouvre l'étape courante.",
                dialog,
            )
            fallback.setWordWrap(True)
        else:
            browser = QWebEngineView(dialog)
            browser.setObjectName("GanymedeSourceWebView")

        count = entry.step_count if type(entry.step_count) is int and entry.step_count > 0 else 0
        selected = str(self.current_character_key or "")
        can_record = is_character_key(selected)
        progress_id = f"ganymede_source_{entry.source_id}"
        progress_service = GuideProgressService(GUIDE_PROGRESS_FILE) if can_record and count else None
        checked = (
            progress_service.manual_steps(selected, progress_id)
            if progress_service is not None else set()
        )
        source_step_id = lambda n: f"ganymede_{entry.source_id}_step_{n:04d}"
        current_page = [1]

        def step_url(n: int) -> QUrl:
            url = QUrl(source_url)
            query = QUrlQuery()
            query.addQueryItem("page", str(n))
            query.addQueryItem("stepsPerPage", "1")
            url.setQuery(query)
            return url

        def open_external() -> None:
            QDesktopServices.openUrl(step_url(current_page[0]))

        if count:
            controls = QHBoxLayout()
            previous_button = QPushButton("Précédent", dialog)
            current_button = QPushButton("Actuelle", dialog)
            number = QSpinBox(dialog)
            number.setObjectName("GanymedeSourceStepNumber")
            number.setRange(1, count)
            number.setSuffix(f" / {count}")
            next_button = QPushButton("Suivant", dialog)
            validate_button = QPushButton("Valider l'étape", dialog)
            validate_button.setObjectName("GanymedeSourceValidateStep")
            validate_button.setEnabled(can_record)
            for widget in (previous_button, current_button, number, next_button, validate_button):
                controls.addWidget(widget)
            layout.addLayout(controls)
            progress_label = QLabel(dialog)
            progress_label.setObjectName("GanymedeSourceProgress")
            layout.addWidget(progress_label)

            def first_unchecked() -> int:
                return next(
                    (n for n in range(1, count + 1) if source_step_id(n) not in checked),
                    count,
                )

            def select_page(page: int) -> None:
                page = max(1, min(count, page))
                current_page[0] = page
                previous_button.setEnabled(page > 1)
                next_button.setEnabled(page < count)
                if browser is not None:
                    browser.setUrl(step_url(page))
                done = sum(
                    1 for n in range(1, count + 1)
                    if source_step_id(n) in checked
                )
                is_done = source_step_id(page) in checked
                validate_button.setText(
                    "Annuler la validation" if is_done else "Valider l'étape"
                )
                progress_label.setText(
                    f"{done} / {count} étapes validées"
                    if can_record else
                    "Choisir un personnage Atlas pour enregistrer la progression."
                )

            def toggle_step() -> None:
                if progress_service is None:
                    return
                step_id = source_step_id(current_page[0])
                completed = step_id not in checked
                try:
                    progress_service.set_manual_step_completed(
                        selected, progress_id, step_id, completed,
                    )
                except (OSError, ValueError, RuntimeError) as exc:
                    self.status_callback(f"Progression Ganymède non enregistrée : {exc}")
                    return
                if completed:
                    checked.add(step_id)
                else:
                    checked.discard(step_id)
                select_page(current_page[0])

            number.valueChanged.connect(select_page)
            previous_button.clicked.connect(
                lambda: number.setValue(max(1, number.value() - 1))
            )
            next_button.clicked.connect(
                lambda: number.setValue(min(count, number.value() + 1))
            )
            current_button.clicked.connect(lambda: number.setValue(first_unchecked()))
            validate_button.clicked.connect(toggle_step)
            start = first_unchecked()
            number.setValue(start)
            select_page(start)
        elif browser is not None:
            browser.setUrl(source_url)

        open_browser = QPushButton("Navigateur", dialog)
        open_browser.setObjectName("GanymedeSourceExternalButton")
        open_browser.clicked.connect(open_external)
        layout.addWidget(open_browser)
        if browser is None:
            layout.addWidget(fallback, 1)
        else:
            layout.addWidget(browser, 1)
        self._ganymede_source_dialog = dialog
        dialog.finished.connect(
            lambda _result, source_dialog=dialog: self._clear_ganymede_source_dialog(source_dialog)
        )
        dialog.show()

    def _clear_ganymede_source_dialog(self, dialog: QDialog) -> None:
        if self._ganymede_source_dialog is dialog:
            self._ganymede_source_dialog = None

    def _sync_grid_columns(self) -> None:
        """Fit whole cells to the real viewport, with no empty heading cell."""
        width = self.home_dofus_list.viewport().width()
        if width <= 0:
            return
        cell_width = self._grid_cell_width(width)
        wanted = QSize(cell_width, 96)
        if self.home_dofus_list.gridSize() != wanted:
            self.home_dofus_list.setGridSize(wanted)

    @staticmethod
    def _grid_cell_width(viewport_width: int) -> int:
        """Never create a grid cell wider than its actual viewport.

        A 215px minimum clipped the last card when the panel was narrower
        (notably in the stacked layout or at high Windows DPI).
        """
        if viewport_width <= 0:
            return 0
        columns = max(1, viewport_width // 230)
        return min(320, max(1, viewport_width // columns))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_grid_columns)


__all__ = ["GuideCatalogView"]
