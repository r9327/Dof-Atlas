"""Interactive developer-only visual inventory of the real shared Unity widgets.

No local stylesheet and no parallel component implementations: this page
always inherits the active application theme and shows real Qt interactions.
It is constructed lazily only after the user explicitly opens it in Settings.
"""
from __future__ import annotations

import re
from collections.abc import Callable

from PySide6.QtCore import QDate, QEasingCurve, QEvent, QPropertyAnimation, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QCalendarWidget,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QGraphicsOpacityEffect,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTimeEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.modules.encyclopedia.services.guide_preparation_model import (
    PREPARATION_CATEGORIES, matches_preparation_category,
    preparation_stock_presentation,
)
from app.ui.components import (
    AtlasBreadcrumb,
    AtlasButton,
    BUTTON_OBJECT_NAMES,
    AtlasComboBox,
    AtlasPageNavigator,
    AtlasDialog, AtlasImagePopup,
    AtlasDialogHeader,
    AtlasPageTitle, AtlasUnavailablePage,
    AtlasPanelToggle,
    configure_unity_number_spinbox,
    AtlasGuideReadingHeader, AtlasGuideSheetHeader,
    AtlasGuidePreparationRow, AtlasGuidePreparationPanel, AtlasGuidePreparationSummary,
    AtlasGuideReadingNav, AtlasGuideValidationButton,
    AtlasStatusBadge,
    atlas_application_icon,
    apply_unity_calendar_weekdays,
    fill_unity_navigation_menu,
    present_transient_dialog,
    configure_unity_progress_bar, configure_unity_scroll_area, configure_unity_tool_button,
    atlas_guide_symbol_icon, atlas_guide_global_progress_bar,
)
from app.ui.theme import PALETTE, SIZES, SPACING, TYPOGRAPHY
from app.ui.entity_link_roles import entity_link_markup
from app.ui.unity_palette import (
    UNITY_CHIP_TONES, UNITY_ICON_NAMES, UNITY_ICON_PENDING,
    UNITY_PANEL_SHADOW,
    UNITY_INTERACTION_STATES, UNITY_MAIN_ROLES, UNITY_ORGANIZER_METRICS_PX,
    UNITY_SIZES_PX, UNITY_SPACING_PX, UNITY_UI_USAGE,
    UNITY_CONTROL_LIMITS, UNITY_CONTROL_SIZES_PX,
    UNITY_LAYOUT_SIZES_PX, UNITY_LAYOUT_BREAKPOINTS_PX,
    UNITY_WINDOW_PRESETS_PX, UNITY_LAYOUT_PROFILE_PX, unity_layout_metrics,
    UNITY_MODULE_GEOMETRY_PX, UNITY_MODULE_GEOMETRY_OWNERS,
    UNITY_GUIDE_READING_METRICS_PX,
    UNITY_UI_CONSUMERS, UNITY_UI_FAMILY_INDEX, UNITY_UI_UNIFICATION_CONTRACT,
)
from app.ui.unity_skin import (
    UnityBackdrop, apply_unity_panel_shadow, sprite_icon_path, unity_original_preview_icon,
)
from app.ui.ui_registry import (
    UI_CONSUMER_INDEX, UI_FAMILY_QSS_SELECTORS,
    UI_FAMILY_PAINTED_ROLES, validate_ui_index,
)


_DIALOG_PREVIEW_VARIANTS = (
    ("info", "Information"),
    ("warning", "Attention"),
    ("danger", "Erreur"),
    ("confirmation", "Confirmation"),
    ("form", "Contenu personnalisé"),
)


def _muted_label(text: str = "", *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName("MutedLabel")
    if wrap:
        label.setWordWrap(True)
    return label


class DevUiPage(QWidget):
    """One interactive visual checkpoint for all currently shared UI families."""

    def __init__(
        self,
        *,
        on_back: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        validate_ui_index()
        self.setObjectName("DevUiPage")
        self.setProperty("atlasUnityPage", True)
        self._preview_dialog: AtlasDialog | AtlasImagePopup | None = None
        self._click_count = 0
        self.gallery_sections: list[QGroupBox] = []
        self._gallery_section_layouts: list[QVBoxLayout] = []
        # The gallery is generated from the same index that documents every
        # common family; consumers use the existing shared QSS/components.
        self.gallery_family_widgets: dict[str, QGroupBox] = {}

        outer = QVBoxLayout(self)
        self._gallery_outer_layout = outer
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(UNITY_LAYOUT_SIZES_PX["module_gap"])

        # Real page breadcrumb, immediately under the shell's navigation tabs.
        # The same GuideBreadcrumb owner is reused by the gallery below.
        self.page_breadcrumb = AtlasBreadcrumb(compact=True)
        breadcrumb_line = self.page_breadcrumb.row
        self.page_breadcrumb_back = AtlasButton(
            "Paramètres", variant="guide_breadcrumb"
        )
        self.page_breadcrumb_back.setEnabled(on_back is not None)
        if on_back is not None:
            self.page_breadcrumb_back.clicked.connect(on_back)
        breadcrumb_line.addWidget(self.page_breadcrumb_back)
        self.page_breadcrumb.add_separator()
        development = QLabel("Développement")
        development.setObjectName("GuideBreadcrumbSeparator")
        breadcrumb_line.addWidget(development)
        self.page_breadcrumb.add_separator()
        self.page_breadcrumb.add_current("UI Dev")
        apply_unity_panel_shadow(self.page_breadcrumb, **UNITY_PANEL_SHADOW)
        outer.addWidget(self.page_breadcrumb)

        heading = QHBoxLayout()
        heading.addWidget(AtlasPageTitle("Dev · Bibliothèque UI Unity"), 1)
        self.back_button = AtlasButton("Retour aux paramètres", variant="secondary")
        self.back_button.setEnabled(on_back is not None)
        if on_back is not None:
            self.back_button.clicked.connect(on_back)
        heading.addWidget(self.back_button)
        outer.addLayout(heading)

        subtitle = _muted_label(
            "Composants Unity existants et contrôles candidats à mutualiser. "
            "Cette galerie permet la comparaison visuelle ; l'adoption dans "
            "chaque module se vérifie séparément.",
            wrap=True,
        )
        outer.addWidget(subtitle)
        self.feedback = _muted_label("Test des interactions : prêt")
        self.feedback.setAccessibleName("Résultat des interactions du laboratoire UI")
        outer.addWidget(self.feedback)

        # The index stays visible while the long catalog scrolls underneath.
        navigator = QHBoxLayout()
        navigation_label = QLabel("Aller à une famille")
        navigator.addWidget(navigation_label)
        self.gallery_navigation = AtlasComboBox()
        self.gallery_navigation.setObjectName("DevUiFamilyCombo")
        self.gallery_navigation.setAccessibleName("Accès direct aux familles UI")
        navigation_label.setBuddy(self.gallery_navigation)
        self.gallery_navigation.view().setAlternatingRowColors(False)
        # The shared combo sizes to the longest family label, but can shrink
        # when the page uses a compact layout.
        navigator.addWidget(self.gallery_navigation)
        self.gallery_count = _muted_label()
        navigator.addWidget(self.gallery_count)
        navigator.addStretch(1)
        outer.addLayout(navigator)

        scroll = configure_unity_scroll_area(QScrollArea(self), borderless=True)
        scroll.setObjectName("DevUiGalleryScroll")
        self.gallery_scroll = scroll
        body = QWidget()
        body.setProperty("atlasUnityPage", True)
        content = QVBoxLayout(body)
        self._gallery_content_layout = content
        content.setContentsMargins(7, 7, 7, 16)
        content.setSpacing(UNITY_LAYOUT_SIZES_PX["module_gap"])
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._build_buttons(content)
        self._build_tabs_and_menus(content)
        self._build_breadcrumbs(content)
        self._build_headers(content)
        self._build_sidebar(content)
        self._build_data_views(content)
        self._build_scroll_and_resize(content)
        self._build_layouts(content)
        self._build_fields(content)
        self._build_advanced_fields(content)
        self._build_states_and_badges(content)
        self._build_notifications(content)
        self._build_surfaces_and_typography(content)
        self._build_sizes(content)
        self._build_panels(content)
        self._build_backdrop(content)
        self._build_startup_preview(content)
        self._build_guide_samples(content)
        self._build_ui_assets(content)
        self._build_motion_gallery(content)
        self._build_scope_matrix(content)
        self._build_dialogs_and_colors(content)
        content.addStretch(1)

        if tuple(self.gallery_family_widgets) != tuple(UNITY_UI_FAMILY_INDEX):
            raise RuntimeError("Dev UI family index does not match gallery sections")
        self.gallery_navigation.addItems(
            [details["title"] for details in UNITY_UI_FAMILY_INDEX.values()]
        )
        self.gallery_count.setText(f"{len(self.gallery_sections)} familles UI")
        self.gallery_navigation.activated.connect(self._jump_to_section)
        self._apply_gallery_geometry(self.width())

    def _apply_gallery_geometry(self, viewport_width: int) -> None:
        """Apply one shared spacing profile to all 23 real UI families.

        This never reparents or changes the order of any module. The gallery
        stays vertically scrollable, and only margins/padding/gaps change.
        """
        metrics = unity_layout_metrics(viewport_width)
        page_margin = metrics["page_margin"]
        module_padding = metrics["module_padding"]
        module_gap = metrics["module_gap"]
        top_bottom = max(8, page_margin - 4)
        self._gallery_outer_layout.setContentsMargins(
            page_margin, top_bottom, page_margin, top_bottom
        )
        self._gallery_outer_layout.setSpacing(module_gap)
        gallery_inset = max(6, module_padding - 4)
        self._gallery_content_layout.setContentsMargins(
            gallery_inset, gallery_inset, gallery_inset, page_margin
        )
        self._gallery_content_layout.setSpacing(module_gap)
        for layout in self._gallery_section_layouts:
            layout.setContentsMargins(
                module_padding,
                UNITY_LAYOUT_SIZES_PX["gallery_section_header_inset"],
                module_padding,
                module_padding,
            )
            layout.setSpacing(UNITY_SPACING_PX["md"])

    def resizeEvent(self, event: QEvent) -> None:
        super().resizeEvent(event)
        self._apply_gallery_geometry(event.size().width())

    def _section(self, parent_layout: QVBoxLayout, family_key: str) -> QVBoxLayout:
        details = UNITY_UI_FAMILY_INDEX[family_key]
        group = QGroupBox(details["title"])
        group.setProperty("atlasUiFamily", family_key)
        group.setAccessibleName(details["title"])
        qss_selectors = UI_FAMILY_QSS_SELECTORS[family_key]
        painted_roles = UI_FAMILY_PAINTED_ROLES.get(family_key, ())
        group.setToolTip(
            f"Source : {details['style_owner']}\n"
            f"Composants indexés : {', '.join(details['components'])}\n"
            f"Règles globales : {', '.join(qss_selectors) or 'tokens / démo'}\n"
            f"Couleurs peintes : {', '.join(painted_roles) or 'via QSS'}\n"
            f"Portée : {details['scope']}"
        )
        # The same subtle Unity relief on every static gallery module.
        # Never apply graphics effects to scrolling rows or input controls.
        apply_unity_panel_shadow(group, **UNITY_PANEL_SHADOW)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(
            UNITY_LAYOUT_SIZES_PX["module_padding"],
            UNITY_LAYOUT_SIZES_PX["gallery_section_header_inset"],
            UNITY_LAYOUT_SIZES_PX["module_padding"],
            UNITY_LAYOUT_SIZES_PX["module_padding"],
        )
        layout.setSpacing(UNITY_SPACING_PX["md"])
        self._gallery_section_layouts.append(layout)
        parent_layout.addWidget(group)
        self.gallery_sections.append(group)
        self.gallery_family_widgets[family_key] = group
        return layout

    @staticmethod
    def _catalog_table(
        row_count: int, columns: tuple[str, ...], *resize_modes: QHeaderView.ResizeMode,
    ) -> QTableWidget:
        table = QTableWidget(row_count, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.verticalHeader().hide()
        header = table.horizontalHeader()
        for index, mode in enumerate(resize_modes):
            header.setSectionResizeMode(index, mode)
        return table

    @staticmethod
    def _expand_catalog_table(table: QTableWidget) -> None:
        """Expose every inventory row using only the main gallery scroll."""
        table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        table.resizeRowsToContents()
        row_height = sum(max(24, table.rowHeight(i)) for i in range(table.rowCount()))
        header_height = table.horizontalHeader().sizeHint().height()
        table.setFixedHeight(header_height + row_height + 2 * table.frameWidth() + 6)

    def _add_catalog_table(
        self, layout: QVBoxLayout, table: QTableWidget, label: str
    ) -> AtlasButton:
        table.setAlternatingRowColors(False)
        table.setShowGrid(False)
        self._expand_catalog_table(table)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.hide()
        toggle = AtlasButton(f"Afficher {label}", variant="secondary")
        toggle.setCheckable(True)
        toggle.toggled.connect(table.setVisible)
        toggle.toggled.connect(
            lambda expanded: toggle.setText(
                f"{'Masquer' if expanded else 'Afficher'} {label}"
            )
        )
        layout.addWidget(toggle, alignment=Qt.AlignLeft)
        layout.addWidget(table)
        return toggle

    def _jump_to_section(self, index: int) -> None:
        """Scroll to the real section; no duplicate or floating UI catalog."""
        if 0 <= index < len(self.gallery_sections):
            self.gallery_navigation.setCurrentIndex(index)
            self.gallery_scroll.ensureWidgetVisible(
                self.gallery_sections[index], 0, 12
            )

    def _report(self, action: str) -> None:
        self._click_count += 1
        self.feedback.setText(f"Interaction {self._click_count} : {action}")

    def _build_buttons(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "buttons")
        row = QHBoxLayout()
        self.preview_buttons: dict[str, AtlasButton] = {}
        for name, caption in (
            ("primary", "Principal"),
            ("secondary", "Secondaire"),
            ("selected", "Sélectionné"),
            ("danger", "Danger"),
        ):
            button = AtlasButton(caption, variant=name)
            button.setToolTip(f"Bouton Unity {name} · clic actif")
            button.clicked.connect(
                lambda _checked=False, selected=name: self._report(
                    f"Bouton {selected} cliqué"
                )
            )
            self.preview_buttons[name] = button
            row.addWidget(button)
        disabled = AtlasButton("Désactivé", variant="secondary")
        disabled.setEnabled(False)
        self.preview_buttons["disabled"] = disabled
        row.addWidget(disabled)
        row.addStretch(1)
        section.addLayout(row)

        nav_row = QHBoxLayout()
        self.preview_nav = (
            AtlasButton("Onglet normal", variant="navigation"),
            AtlasButton("Onglet actif", variant="navigation_active"),
        )
        for index, button in enumerate(self.preview_nav):
            button.clicked.connect(
                lambda _checked=False, selected=index: self._select_nav(selected)
            )
            nav_row.addWidget(button)
        nav_row.addStretch(1)
        section.addLayout(nav_row)

        # Actual shared link variants used in Guides, Quêtes and Succès.
        link_row = QHBoxLayout()
        for name, caption in (
            ("guide_breadcrumb", "Fil d'Ariane"),
            ("guide_quest_link", "Lien de quête"),
            ("guide_achievement_link", "Lien de succès"),
        ):
            button = AtlasButton(caption, variant=name)
            button.clicked.connect(
                lambda _checked=False, selected=name: self._report(
                    f"Lien {selected} cliqué"
                )
            )
            self.preview_buttons[name] = button
            link_row.addWidget(button)
        link_row.addStretch(1)
        section.addLayout(link_row)

        # Borderless but unmistakably clickable secondary/popup actions.
        # Both are real AtlasButton controls and inherit the same QSS tokens.
        action_row = QHBoxLayout()
        self.preview_text_actions: dict[str, AtlasButton] = {}
        for name, caption in (
            ("inline_action", "Voir les détails"),
            ("popup_link", "Ouvrir la popup"),
        ):
            button = AtlasButton(caption, variant=name)
            button.setAccessibleName(caption)
            button.setToolTip("Texte d'action cliquable · survol vert · clavier actif")
            if name == "popup_link":
                button.clicked.connect(self._open_preview_dialog)
            else:
                button.clicked.connect(
                    lambda _checked=False: self._report("Détails ouverts")
                )
            self.preview_text_actions[name] = button
            action_row.addWidget(button)
        action_row.addStretch(1)
        section.addLayout(action_row)

        # Same existing favoriteChipName / favoriteChip QSS as ZaapWidget.
        # This is a shared style sample, not another Zaap interaction model.
        favorite_row = QHBoxLayout()
        favorite_chip = QFrame()
        favorite_chip.setObjectName("favoriteChip")
        favorite_layout = QHBoxLayout(favorite_chip)
        favorite_layout.setContentsMargins(8, 0, 10, 0)
        favorite_layout.setSpacing(4)
        self.preview_zaap_favorite_button = AtlasButton(
            "Favori Zaap", variant="zaap_favorite"
        )
        self.preview_zaap_favorite_button.setToolTip(
            "Bouton de favori Zaap partagé, sans commande de déplacement"
        )
        self.preview_zaap_favorite_button.clicked.connect(
            lambda: self._report("Bouton favori Zaap partagé cliqué")
        )
        favorite_layout.addWidget(self.preview_zaap_favorite_button)
        favorite_row.addWidget(favorite_chip)
        favorite_row.addStretch(1)
        section.addLayout(favorite_row)

    def _select_nav(self, active: int) -> None:
        for index, button in enumerate(self.preview_nav):
            button.set_variant(
                "navigation_active" if index == active else "navigation"
            )
        self._report(f"Onglet {active + 1} sélectionné")

    def _build_tabs_and_menus(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "navigation")
        self.preview_tabs = QTabWidget()
        self.preview_tabs.setObjectName("EncyclopediaTabs")
        for title in ("Quêtes", "Succès", "Guides"):
            tab = QWidget()
            tab.setObjectName("DevUiTabPage")
            tab_layout = QVBoxLayout(tab)
            text = _muted_label(f"Contenu de démonstration : {title}")
            tab_layout.addWidget(text)
            self.preview_tabs.addTab(tab, title)
        self.preview_tabs.currentChanged.connect(
            lambda index: self._report(
                f"Onglet {self.preview_tabs.tabText(index)}"
            )
        )
        section.addWidget(self.preview_tabs)

        menu_row = QHBoxLayout()
        self.menu_button = AtlasButton("Ouvrir un menu", variant="secondary")
        menu = QMenu(self.menu_button)
        fill_unity_navigation_menu(
            menu,
            tuple((label, label) for label in (
                "Première action", "Deuxième action", "Troisième action",
            )),
            lambda label: self._report(f"Menu : {label}"),
        )
        menu.addSeparator()
        checked_action = menu.addAction("Action cochable")
        checked_action.setCheckable(True)
        checked_action.toggled.connect(
            lambda checked: self._report(
                "Menu : cochée" if checked else "Menu : décochée"
            )
        )
        submenu = menu.addMenu("Sous-menu")
        submenu.addAction("Sous-action").triggered.connect(
            lambda: self._report("Sous-menu : action cliquée")
        )
        self.menu_button.setMenu(menu)
        menu_row.addWidget(self.menu_button)
        menu_row.addStretch(1)
        section.addLayout(menu_row)

        pagination = QHBoxLayout()
        self.preview_page_index = 1
        self.preview_pagination = AtlasPageNavigator(total=3)
        self.preview_page_prev = self.preview_pagination.previous_button
        self.preview_page_next = self.preview_pagination.next_button
        self.preview_page_label = self.preview_pagination.page_label
        self.preview_pagination.pageRequested.connect(
            lambda page: self._change_preview_page(page - self.preview_page_index)
        )
        pagination.addWidget(self.preview_pagination)
        back = AtlasButton("Retour", variant="secondary")
        back.clicked.connect(lambda: self._report("Navigation : retour"))
        pagination.addWidget(back)
        pagination.addStretch(1)
        section.addLayout(pagination)

    def _change_preview_page(self, step: int) -> None:
        self.preview_page_index = max(1, min(3, self.preview_page_index + step))
        self.preview_pagination.set_page(self.preview_page_index, 3)
        self._report(f"Navigation : page {self.preview_page_index}")

    def _build_headers(self, parent: QVBoxLayout) -> None:
        """Show real shared Guide header parts without a second UI skin or runtime."""
        from app.ui.components import (
            AtlasGuideParticipantPortrait as _ParticipantPortraitButton,
            atlas_guide_symbol_icon as _guide_symbol_icon,
        )

        section = self._section(parent, "headers")
        note = _muted_label(
            "En-têtes de référence · composants et thème Unity existants. "
            "Progression et personnages fictifs : aucune donnée Ganymède chargée.",
            wrap=True,
        )
        section.addWidget(note)

        self.preview_page_header = QFrame()
        self.preview_page_header.setObjectName("card")
        page_row = QHBoxLayout(self.preview_page_header)
        page_row.setContentsMargins(12, 9, 12, 9)
        page_row.addWidget(AtlasPageTitle("Encyclopédie"), 1)
        back = AtlasButton("Retour", variant="secondary")
        back.clicked.connect(lambda: self._report("En-tête page · retour"))
        page_row.addWidget(back)
        apply_unity_panel_shadow(self.preview_page_header, **UNITY_PANEL_SHADOW)
        section.addWidget(self.preview_page_header)

        self.preview_module_header = AtlasGuideReadingHeader("Guides Dofus", overview=True)
        self.preview_module_header.meta_label.setText("En-tête de module · sous-titre Unity")
        self.preview_module_header.meta_label.show()
        self.preview_module_header.set_overview_progress(7, 20)
        module_action = AtlasButton("Parcourir", variant="secondary")
        module_action.clicked.connect(lambda: self._report("En-tête module · parcourir"))
        self.preview_module_header.title_row.addWidget(module_action)
        section.addWidget(self.preview_module_header)

        header = AtlasGuideReadingHeader("Guide · aperçu fictif")
        self.preview_compact_header = header
        self.preview_header_title_row = header.title_row
        self.preview_header_content_layout = header.content_layout
        self.preview_header_guide_icon = header.guide_icon_label
        self.preview_header_global_progress = header.global_progress_bar
        header.global_progress_bar.setValue(35)
        header.global_progress_label.setText("35 %")
        header.preparation_bar.setValue(60)
        header.preparation_progress_label.setText("60 %")
        header.set_summary_provider(lambda: ("Parler au PNJ", "Récupérer les objets", "Retour au village"))
        header.set_summary_position(0)
        header.summaryRequested.connect(lambda index: self._report(f"Sommaire · fiche {index + 1} (aperçu)"))
        global_toggle = header.global_details_button
        prep_toggle = header.preparation_button
        character_toggle = header.participants_button
        global_panel = header.global_details_panel
        characters = header.participants_panel
        portraits = header.participants_layout
        self.preview_header_global_panel = global_panel
        self.preview_header_controls = {
            "Progression globale": global_toggle,
            "Préparation": prep_toggle,
            "Sommaire": header.summary_button,
            "Personnages": character_toggle,
        }
        self.preview_header_panels = {
            "Progression globale": global_panel,
            "Sommaire": header.summary_panel,
            "Personnages": characters,
        }
        self.preview_header_metrics = {"Préparation": header.preparation_bar, "Sommaire": header.summary_bar}
        self.preview_header_metric_icons = {"Préparation": header.preparation_icon, "Sommaire": header.summary_icon}
        header.set_global_detail_lines(tuple(
            f"Personnage fictif {index} · {percent} %"
            for index, percent in enumerate((35, 60, 10), start=1)
        ))

        prep_panel = AtlasGuidePreparationPanel(PREPARATION_CATEGORIES)
        materials = prep_panel.content
        materials_layout = prep_panel.rows_layout
        self.preview_header_filter = prep_panel.category_filter
        self.preview_header_preparation_examples = []
        def filter_preparation_example(category: str) -> None:
            for widget, item_category, item_name in self.preview_header_preparation_examples:
                widget.setVisible(matches_preparation_category(
                    item_category, item_name, category,
                ))
            prep_panel.fit_content_height()
            self._report(f"Préparation · filtre {category} (aperçu)")
        self.preview_header_filter.currentTextChanged.connect(
            filter_preparation_example
        )
        self.preview_header_preparation_rows = []
        self.preview_header_preparation_names = []
        for category, name, quantity, done in (
            ("Prérequis", "Accès au village", 1, True),
            ("Métiers", "Métier Paysan requis", 1, False),
            ("Potions", "Potion de rappel", 2, True),
            ("Pierres d'âme", "Pierre d'âme", 1, False),
            ("Clefs", "Clef du donjon", 1, False),
            ("Objets", "Ressources à récupérer", 8, False),
        ):
            # The gallery uses the same live row, but no persistence or
            # invented quantity for non-material requirements.
            required = quantity if category not in {"Prérequis", "Métiers"} else None
            item = AtlasGuidePreparationRow(
                name, quantity=required, owned=quantity if done else 0,
                confirmed=int(done), participants=1,
                stock_formatter=preparation_stock_presentation,
            )
            amount = item.quantity_editor
            checkbox = item.ready_button
            copy_button = item.name_button
            checkbox.setToolTip("Marquer comme prêt · aperçu fictif")
            checkbox.toggled.connect(
                lambda checked, row=item, total=quantity: row.set_saved_state(
                    confirmed=int(checked), participants=1, owned=total if checked else 0,
                )
            )
            materials_layout.addWidget(item)
            self.preview_header_preparation_examples.append((item, category, name))
            self.preview_header_preparation_rows.append((amount, checkbox))
            self.preview_header_preparation_names.append(copy_button)
        prep_panel.fit_content_height()
        self.preview_header_materials_host = materials

        header.attach_preparation(prep_panel)
        self.preview_header_panels["Préparation"] = prep_panel
        for name, toggle in self.preview_header_controls.items():
            toggle.clicked.connect(
                lambda opened, label=name: self._report(
                    f"Guide · {label} : {'ouvert' if opened else 'fermé'} (aperçu)"
                )
            )

        self.preview_header_portraits = []
        portrait_icon = sprite_icon_path("character")
        for index, percent in enumerate((35, 60, 10), start=1):
            portrait = _ParticipantPortraitButton(
                f"character:demo_{index}", progress=percent
            )
            portrait.setToolTip(
                f"Personnage fictif {index} · progression {percent} %"
            )
            portrait.setAccessibleName(f"Personnage fictif {index}")
            portrait.setChecked(index == 1)
            if portrait_icon:
                portrait.setIcon(QIcon(str(portrait_icon)))
            else:
                portrait.setIcon(_guide_symbol_icon(
                    portrait, "people", color=PALETTE["TEXT_SOFT"]
                ))
            portrait.toggled.connect(
                lambda checked, number=index: self._report(
                    f"Guide · personnage {number} "
                    f"{'choisi' if checked else 'retiré'} (aperçu)"
                )
            )
            portraits.addWidget(portrait)
            self.preview_header_portraits.append(portrait)
        portraits.addStretch(1)
        section.addWidget(header)

        self.preview_sheet_header = AtlasGuideSheetHeader(
            "Exemple · parler au PNJ du village", total=20, page=4,
        )
        self.preview_sheet_header.back_button.clicked.connect(
            lambda: self._report("En-tête fiche · retour")
        )
        self.preview_header_page_jump = self.preview_sheet_header.page_jump
        self.preview_header_page_jump.valueChanged.connect(
            lambda value: self._report(f"Guide · fiche {value} / 20")
        )
        section.addWidget(self.preview_sheet_header)

        self.preview_dialog_header = AtlasDialogHeader(
            "Confirmation", "En-tête commun aux fenêtres et popups"
        )
        section.addWidget(self.preview_dialog_header)

    def _build_sidebar(self, parent: QVBoxLayout) -> None:
        """Real sidebar selectors, with live selection and collapse."""
        section = self._section(parent, "sidebar")
        row = QHBoxLayout()
        self.preview_sidebar = QFrame()
        self.preview_sidebar.setObjectName("sidebar")
        apply_unity_panel_shadow(self.preview_sidebar, **UNITY_PANEL_SHADOW)
        self.preview_sidebar.setMinimumWidth(
            UNITY_CONTROL_SIZES_PX["gallery_sidebar_min_width"]
        )
        self.preview_sidebar.setMaximumWidth(
            UNITY_CONTROL_SIZES_PX["gallery_sidebar_max_width"]
        )
        layout = QVBoxLayout(self.preview_sidebar)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.preview_burger = configure_unity_tool_button(
            QToolButton(), object_name="MenuButton", text="Menu",
        )
        self.preview_burger.setToolTip("Replier / déplier le menu")
        self.preview_burger.clicked.connect(self._toggle_preview_sidebar)
        layout.addWidget(self.preview_burger)
        self.preview_sidebar_content = QWidget()
        self.preview_sidebar_content.setObjectName("DevUiSidebarContent")
        self.preview_sidebar_content.setProperty("atlasUnityPage", True)
        content = QVBoxLayout(self.preview_sidebar_content)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(4)
        self.preview_sidebar_buttons: dict[str, AtlasButton] = {}
        for label in ("Accueil", "Encyclopédie", "Outils", "Organizer"):
            button = AtlasButton(label)
            button.set_style_name(
                "navItemActive" if label == "Encyclopédie" else "navItem"
            )
            button.clicked.connect(
                lambda _checked=False, target=label: self._select_preview_sidebar(target)
            )
            self.preview_sidebar_buttons[label] = button
            content.addWidget(button)
        divider = QFrame()
        divider.setObjectName("NavSeparator")
        divider.setFixedHeight(1)
        content.addWidget(divider)
        layout.addWidget(self.preview_sidebar_content)
        row.addWidget(self.preview_sidebar)
        note = _muted_label(
            "Navigation Unity : actif, survol, replié et séparateur. "
            "Démonstration sans changement de page.",
            wrap=True,
        )
        row.addWidget(note, 1)
        section.addLayout(row)

        # Real World Scan menu identities, not a second navigation skin.
        self.preview_world_menu = QFrame()
        self.preview_world_menu.setObjectName("WorldMenu")
        apply_unity_panel_shadow(self.preview_world_menu, **UNITY_PANEL_SHADOW)
        world_layout = QHBoxLayout(self.preview_world_menu)
        world_layout.setContentsMargins(8, 8, 8, 8)
        world_layout.setSpacing(6)
        self.preview_world_buttons: dict[str, AtlasButton] = {}
        for name in ("Monde des Douze", "Incarnam", "Frigost"):
            button = AtlasButton(name)
            button.set_style_name(
                "WorldMenuItemActive" if name == "Monde des Douze"
                else "WorldMenuItem"
            )
            button.setFixedHeight(UNITY_SIZES_PX["control_normal"])
            button.clicked.connect(
                lambda _checked=False, choice=name: self._select_preview_world(choice)
            )
            self.preview_world_buttons[name] = button
            world_layout.addWidget(button)
        # Navigation labels are compact tabs, not three giant equal-width bars.
        world_layout.addStretch(1)
        section.addWidget(self.preview_world_menu)

    def _toggle_preview_sidebar(self) -> None:
        collapsed = not self.preview_sidebar_content.isHidden()
        self.preview_sidebar_content.setHidden(collapsed)
        self._report("Menu latéral replié" if collapsed else "Menu latéral déployé")

    def _select_preview_sidebar(self, selected: str) -> None:
        for label, button in self.preview_sidebar_buttons.items():
            button.set_style_name(
                "navItemActive" if label == selected else "navItem"
            )
        self._report(f"Navigation latérale : {selected}")

    def _select_preview_world(self, selected: str) -> None:
        for name, button in self.preview_world_buttons.items():
            button.set_style_name(
                "WorldMenuItemActive" if name == selected else "WorldMenuItem"
            )
        self._report(f"Navigation Monde : {selected}")

    def _build_breadcrumbs(self, parent: QVBoxLayout) -> None:
        """Real shared Guide breadcrumb states, not one isolated button."""
        section = self._section(parent, "breadcrumbs")
        caption = _muted_label("Parcours complet : survoler et cliquer chaque niveau.")
        section.addWidget(caption)

        self.preview_breadcrumb = AtlasBreadcrumb()
        apply_unity_panel_shadow(self.preview_breadcrumb, **UNITY_PANEL_SHADOW)
        row = self.preview_breadcrumb.row
        self.preview_breadcrumb_links: dict[str, AtlasButton] = {}
        for level in ("Encyclopédie", "Guides", "Dofus"):
            button = AtlasButton(level, variant="guide_breadcrumb")
            button.setToolTip(f"Naviguer vers : {level}")
            button.clicked.connect(
                lambda _checked=False, target=level: self._report(
                    f"Fil d'Ariane : {target}"
                )
            )
            self.preview_breadcrumb_links[level] = button
            row.addWidget(button)
            self.preview_breadcrumb.add_separator()
        self.preview_breadcrumb_current = self.preview_breadcrumb.add_current("Ocre")
        section.addWidget(self.preview_breadcrumb)
        variants = QHBoxLayout()
        self.preview_breadcrumb_compact = QLabel("Encyclopédie › Quêtes")
        self.preview_breadcrumb_compact.setObjectName("BreadcrumbLabel")
        variants.addWidget(self.preview_breadcrumb_compact)
        self.preview_breadcrumb_strong = QLabel("Étape en cours")
        self.preview_breadcrumb_strong.setObjectName("GuideBreadcrumbCurrentStrong")
        variants.addWidget(self.preview_breadcrumb_strong)
        variants.addStretch(1)
        section.addLayout(variants)

    def _build_data_views(self, parent: QVBoxLayout) -> None:
        """Exercise the actual shared tree/table family and their Qt signals."""
        section = self._section(parent, "data_views")
        row = QHBoxLayout()

        self.preview_tree = QTreeWidget()
        # Exercise the actual Quest hierarchy canvas, not an unstyled sample.
        self.preview_tree.setObjectName("QuestHierarchyTree")
        self.preview_tree.setHeaderLabels(("Famille UI", "État"))
        self.preview_tree.setMaximumHeight(5 * UNITY_SIZES_PX["control_normal"])
        self.preview_tree.setAlternatingRowColors(False)
        self.preview_tree.setUniformRowHeights(True)
        self.preview_tree.setIndentation(14)
        self.preview_tree.header().setStretchLastSection(False)
        self.preview_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.preview_tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.preview_tree.setColumnWidth(1, 150)
        parent_item = QTreeWidgetItem(("Encyclopédie", "Disponible"))
        for label in ("Quêtes", "Succès", "Guides"):
            QTreeWidgetItem(parent_item, (label, "Sélectionnable"))
        self.preview_tree.addTopLevelItem(parent_item)
        parent_item.setExpanded(True)
        self.preview_tree.currentItemChanged.connect(
            lambda item, _previous: self._report(
                f"Arborescence : {item.text(0)}"
            ) if item is not None else None
        )
        row.addWidget(self.preview_tree, 1)

        self.preview_table = QTableWidget(3, 2)
        self.preview_table.setHorizontalHeaderLabels(("Contrôle", "État"))
        self.preview_table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.preview_table.setMaximumHeight(5 * UNITY_SIZES_PX["control_normal"])
        self.preview_table.setAlternatingRowColors(False)
        self.preview_table.setShowGrid(False)
        self.preview_table.verticalHeader().hide()
        self.preview_table.horizontalHeader().setStretchLastSection(False)
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for index, title in enumerate(("Survol", "Sélection", "Clavier")):
            self.preview_table.setItem(index, 0, QTableWidgetItem(title))
            self.preview_table.setItem(index, 1, QTableWidgetItem("Unity"))
        self.preview_table.currentCellChanged.connect(
            lambda current_row, _column, _old_row, _old_column: self._report(
                f"Tableau : {self.preview_table.item(current_row, 0).text()}"
            ) if current_row >= 0 and self.preview_table.item(current_row, 0)
            else None
        )
        row.addWidget(self.preview_table, 1)
        section.addLayout(row)

        # Map catalog's production selector, with real Qt selection.
        self.preview_map_tree = QTreeWidget()
        self.preview_map_tree.setObjectName("MapViewTree")
        self.preview_map_tree.setHeaderHidden(True)
        self.preview_map_tree.setMaximumHeight(3 * UNITY_SIZES_PX["control_normal"])
        self.preview_map_tree.setAlternatingRowColors(False)
        for name in ("Monde des Douze", "Incarnam", "Frigost"):
            self.preview_map_tree.addTopLevelItem(QTreeWidgetItem((name,)))
        self.preview_map_tree.currentItemChanged.connect(
            lambda item, _previous: self._report(
                f"Arbre Carte : {item.text(0)}"
            ) if item is not None else None
        )
        section.addWidget(self.preview_map_tree)

        # Success catalogue: same real root/column selectors as the live
        # three-column view, without loading any achievements or providers.
        self.preview_success_catalogue = QWidget()
        self.preview_success_catalogue.setObjectName("AchievementsView")
        self.preview_success_catalogue.setProperty("atlasUnityPage", True)
        catalogue_layout = QHBoxLayout(self.preview_success_catalogue)
        catalogue_layout.setContentsMargins(4, 4, 4, 4)
        catalogue_layout.setSpacing(8)
        self.preview_success_columns: dict[str, QWidget] = {}
        for object_name, caption in (
            ("GuideLeftPanel", "Catégories"),
            ("GuideCenterPanel", "Succès"),
            ("AchievementDetailStack", "Détails"),
        ):
            if object_name == "AchievementDetailStack":
                column = QStackedWidget()
                detail = QWidget()
                # Reuse the already-shared transparent content host: do not
                # paint an opaque QWidget on top of the stacked glass shell.
                detail.setObjectName("AtlasTransparentHost")
                detail_layout = QVBoxLayout(detail)
                detail_layout.addWidget(QLabel(caption))
                column.addWidget(detail)
            else:
                column = QFrame()
                column_layout = QVBoxLayout(column)
                column_layout.addWidget(QLabel(caption))
            column.setObjectName(object_name)
            column.setMinimumHeight(3 * UNITY_SIZES_PX["control_normal"])
            apply_unity_panel_shadow(column, **UNITY_PANEL_SHADOW)
            catalogue_layout.addWidget(column, 1)
            self.preview_success_columns[object_name] = column
        section.addWidget(self.preview_success_catalogue)

    def _build_layouts(self, parent: QVBoxLayout) -> None:
        """Existing card QSS inside an elastic two-column grid."""
        section = self._section(parent, "layouts")
        intro = _muted_label("Grille 2 × 2 : colonnes égales, marges et alignements communs.")
        section.addWidget(intro)
        grid = QGridLayout()
        grid.setSpacing(10)
        self.preview_layout_cards: list[QFrame] = []
        for index, name in enumerate(("Quêtes", "Succès", "Métiers", "Bestiaire")):
            card = QFrame()
            card.setObjectName("card")
            apply_unity_panel_shadow(card, **UNITY_PANEL_SHADOW)
            line = QHBoxLayout(card)
            line.setContentsMargins(10, 8, 10, 8)
            line.addWidget(QLabel(name), 1)
            line.addWidget(AtlasStatusBadge(
                "Actif" if index == 0 else "Disponible",
                state="active" if index == 0 else "neutral",
            ))
            grid.addWidget(card, index // 2, index % 2)
            self.preview_layout_cards.append(card)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        section.addLayout(grid)

    def _build_fields(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "fields")
        row = QHBoxLayout()
        self.preview_input = QLineEdit()
        self.preview_input.setPlaceholderText("Champ texte Unity")
        self.preview_input.setToolTip("Focus, bordure et curseur hérités du thème")
        self.preview_input.textChanged.connect(
            lambda text: self._report(f"Saisie : {text}")
        )
        row.addWidget(self.preview_input, 2)
        self.preview_combo = AtlasComboBox()
        self.preview_combo.view().setAlternatingRowColors(False)
        self.preview_combo.addItems(("Normal", "Rapide", "Instantané"))
        self.preview_combo.currentTextChanged.connect(
            lambda value: self._report(f"Menu déroulant : {value}")
        )
        row.addWidget(self.preview_combo, 0, Qt.AlignVCenter)
        self.preview_spin = configure_unity_number_spinbox(
            QSpinBox(), minimum=1, maximum=8, value=4,
        )
        self.preview_spin.valueChanged.connect(
            lambda value: self._report(f"Compteur : {value}")
        )
        row.addWidget(self.preview_spin)
        section.addLayout(row)

        self.preview_text = QPlainTextEdit()
        self.preview_text.setPlaceholderText("Zone de texte multiligne")
        self.preview_text.setMaximumHeight(68)
        self.preview_text.textChanged.connect(
            lambda: self._report("Saisie multiligne modifiée")
        )
        section.addWidget(self.preview_text)

        states = QHBoxLayout()
        self.preview_check = QCheckBox("Case cochée")
        self.preview_check.setChecked(True)
        self.preview_check.toggled.connect(
            lambda checked: self._report(
                "Case cochée" if checked else "Case décochée"
            )
        )
        states.addWidget(self.preview_check)
        first_radio = QRadioButton("Option A")
        second_radio = QRadioButton("Option B")
        first_radio.setChecked(True)
        states.addWidget(first_radio)
        states.addWidget(second_radio)
        states.addStretch(1)
        section.addLayout(states)

        self.preview_progress = configure_unity_progress_bar(
            QProgressBar(), text_visible=True,
        )
        self.preview_progress.setValue(40)
        self.preview_slider = QSlider(Qt.Horizontal)
        self.preview_slider.setObjectName("DevUiProgressSlider")
        self.preview_slider.setRange(0, 100)
        self.preview_slider.setValue(40)
        self.preview_slider.valueChanged.connect(self.preview_progress.setValue)
        section.addWidget(self.preview_progress)
        section.addWidget(self.preview_slider)

    def _build_advanced_fields(self, parent: QVBoxLayout) -> None:
        """Show native Qt controls which inherit the same application QSS."""
        section = self._section(parent, "advanced_fields")

        form_grid = QGridLayout()
        form_grid.setHorizontalSpacing(12)
        form_grid.setVerticalSpacing(7)
        self.preview_advanced_grid = form_grid
        self.preview_password = QLineEdit()
        self.preview_password.setPlaceholderText("Mot de passe")
        self.preview_password.setEchoMode(QLineEdit.Password)
        self.preview_password.setAccessibleName("Champ de mot de passe")

        self.preview_readonly = QLineEdit("Lecture seule")
        self.preview_readonly.setReadOnly(True)

        self.preview_disabled_input = QLineEdit("Indisponible")
        self.preview_disabled_input.setEnabled(False)

        self.preview_double_spin = QDoubleSpinBox()
        self.preview_double_spin.setDecimals(2)
        self.preview_double_spin.setRange(0.0, 999.99)
        self.preview_double_spin.setValue(12.50)
        self.preview_double_spin.valueChanged.connect(
            lambda value: self._report(f"Nombre décimal : {value:.2f}")
        )
        self.preview_date = QDateEdit()
        self.preview_date.setCalendarPopup(True)
        self.preview_date.setDisplayFormat("dd/MM/yyyy")
        self.preview_date.setDate(QDate.currentDate())
        self.preview_date.dateChanged.connect(
            lambda value: self._report(f"Date : {value.toString('dd/MM/yyyy')}")
        )
        self.preview_time = QTimeEdit()
        self.preview_time.setDisplayFormat("HH:mm")
        self.preview_time.timeChanged.connect(
            lambda value: self._report(f"Heure : {value.toString('HH:mm')}")
        )
        for index, (caption, control) in enumerate((
            ("Mot de passe", self.preview_password),
            ("Lecture seule", self.preview_readonly),
            ("Désactivé", self.preview_disabled_input),
            ("Nombre décimal", self.preview_double_spin),
            ("Date", self.preview_date),
            ("Heure", self.preview_time),
        )):
            heading = _muted_label(caption)
            form_grid.addWidget(heading, index // 3 * 2, index % 3)
            control.setMinimumHeight(UNITY_SIZES_PX["control_normal"])
            form_grid.addWidget(control, index // 3 * 2 + 1, index % 3)
            form_grid.setColumnStretch(index % 3, 1)
        section.addLayout(form_grid)

        checks = QHBoxLayout()
        checks.setSpacing(16)
        self.preview_tristate = QCheckBox("Tri-état")
        self.preview_tristate.setTristate(True)
        self.preview_tristate.setCheckState(Qt.PartiallyChecked)
        checks.addWidget(self.preview_tristate)
        self.preview_disabled_check = QCheckBox("Case désactivée")
        self.preview_disabled_check.setEnabled(False)
        checks.addWidget(self.preview_disabled_check)
        checks.addStretch(1)
        section.addLayout(checks)

        # Same object name and global QSS as the real Almanax page.
        self.preview_almanax_calendar = QCalendarWidget()
        self.preview_almanax_calendar.setObjectName("AlmanaxCalendar")
        self.preview_almanax_calendar.setFirstDayOfWeek(Qt.Monday)
        apply_unity_calendar_weekdays(self.preview_almanax_calendar)
        self.preview_almanax_calendar.setVerticalHeaderFormat(
            QCalendarWidget.NoVerticalHeader
        )
        self.preview_almanax_calendar.setMaximumHeight(7 * UNITY_SIZES_PX["control_normal"])
        apply_unity_panel_shadow(
            self.preview_almanax_calendar, **UNITY_PANEL_SHADOW
        )
        self.preview_almanax_calendar.selectionChanged.connect(
            lambda: self._report(
                "Almanax : "
                + self.preview_almanax_calendar.selectedDate().toString("dd/MM/yyyy")
            )
        )
        section.addWidget(self.preview_almanax_calendar)

    def _build_states_and_badges(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "statuses")

        badges = QHBoxLayout()
        self.preview_badges: dict[str, QLabel] = {}
        for state, caption in (
            ("done", "Terminé"),
            ("active", "En cours"),
            ("blocked", "Indisponible"),
            ("danger", "Danger"),
            ("warning", "Attention"),
            ("info", "Information"),
            ("neutral", "Neutre"),
        ):
            badge = AtlasStatusBadge(caption, state=state)
            self.preview_badges[state] = badge
            badges.addWidget(badge)
        badges.addStretch(1)
        section.addLayout(badges)

        # Passive corner badges do not respond to hover. Clickable chips below
        # are separate, underlined actions with full hover/focus states.
        chip_hint = _muted_label("Actions de statut cliquables · survol et sélection")
        section.addWidget(chip_hint)
        chip_row = QHBoxLayout()
        self.preview_chips: dict[str, AtlasButton] = {}
        chip_captions = {
            "success": "Validé", "danger": "Danger", "warning": "Attention",
            "info": "Information", "neutral": "Neutre",
        }
        for tone in UNITY_CHIP_TONES:
            chip = AtlasButton(chip_captions[tone], variant="status_chip")
            chip.setMinimumHeight(20)
            chip.setMaximumHeight(24)
            chip.setProperty("tone", tone)
            chip.setCheckable(True)
            chip.setChecked(tone == "success")
            chip.setAccessibleName(f"Action de statut {chip_captions[tone]}")
            chip.setToolTip(f"Action {tone} · clic, survol, sélection et focus")
            chip.toggled.connect(
                lambda checked, selected=tone: self._report(
                    f"Badge {selected} {'activé' if checked else 'désactivé'}"
                )
            )
            self.preview_chips[tone] = chip
            chip_row.addWidget(chip)
        chip_row.addStretch(1)
        section.addLayout(chip_row)
        self.preview_interaction_states = UNITY_INTERACTION_STATES
        hint = _muted_label("États indexés : " + " · ".join(UNITY_INTERACTION_STATES))
        section.addWidget(hint)

        state_row = QHBoxLayout()
        self.preview_toggle = configure_unity_tool_button(
            QToolButton(), object_name="GuideSummaryButton", text="Commutateur",
        )
        self.preview_toggle.setCheckable(True)
        self.preview_toggle.setChecked(True)
        self.preview_toggle.setAccessibleName("Commutateur de démonstration")
        self.preview_toggle.toggled.connect(
            lambda checked: self._report("Commutateur actif" if checked
                                         else "Commutateur inactif")
        )
        state_row.addWidget(self.preview_toggle)
        self.preview_checked_action = AtlasButton("Sélectionné", variant="secondary")
        self.preview_checked_action.setCheckable(True)
        self.preview_checked_action.setChecked(True)
        self.preview_checked_action.toggled.connect(
            lambda checked: self._report(
                "Bouton sélectionné" if checked else "Bouton désélectionné"
            )
        )
        state_row.addWidget(self.preview_checked_action)
        info = _muted_label("Survol · pressé · focus · désactivé")
        state_row.addWidget(info, 1)
        section.addLayout(state_row)

        # Native hover, pressed and focus states are interactive Qt controls.
        state_row = QHBoxLayout()
        self.preview_state_buttons: dict[str, AtlasButton] = {}
        for state, title, variant in (
            ("normal", "Normal", "secondary"),
            ("hover", "Survoler", "secondary"),
            ("pressed", "Cliquer", "secondary"),
            ("selected", "Sélectionné", "selected"),
            ("focus", "Focus clavier", "secondary"),
            ("disabled", "Désactivé", "secondary"),
        ):
            button = AtlasButton(title, variant=variant)
            button.setEnabled(state != "disabled")
            button.setToolTip(f"État Qt réel : {state}")
            button.clicked.connect(
                lambda _checked=False, key=state:
                    self._report(f"État : {key}")
            )
            self.preview_state_buttons[state] = button
            state_row.addWidget(button)
        state_row.addStretch(1)
        section.addLayout(state_row)

        progress_row = QHBoxLayout()
        self.preview_busy = configure_unity_progress_bar(
            QProgressBar(), maximum=0, text_visible=True,
        )
        self.preview_busy.setAccessibleName("Progression indéterminée")
        progress_row.addWidget(self.preview_busy, 1)
        self.preview_complete = configure_unity_progress_bar(
            QProgressBar(), text_visible=True,
        )
        self.preview_complete.setValue(100)
        self.preview_complete.setAccessibleName("Progression terminée")
        progress_row.addWidget(self.preview_complete, 1)
        section.addLayout(progress_row)

    def _build_notifications(self, parent: QVBoxLayout) -> None:
        """Read-only notification preview; no pretend toast or duplicate QSS."""
        section = self._section(parent, "notifications")
        note = _muted_label(
            "Exemples intégrés utilisant les badges et surfaces Unity existants. "
            "Le comportement des notifications flottantes reste à mutualiser.",
            wrap=True,
        )
        section.addWidget(note)
        self.preview_notifications: dict[str, QFrame] = {}
        for state, title, message in (
            ("done", "Terminé", "Opération terminée avec succès"),
            ("info", "Information", "Nouvelle information disponible"),
            ("warning", "Attention", "Vérifier les paramètres avant de continuer"),
            ("danger", "Erreur", "Une opération nécessite une intervention"),
        ):
            frame = QFrame()
            frame.setObjectName("card")
            # Static preview card, unlike long scrolling rows: safe to give
            # it the same subtle Unity relief as other shared cards.
            apply_unity_panel_shadow(frame, **UNITY_PANEL_SHADOW)
            line = QHBoxLayout(frame)
            line.setContentsMargins(10, 6, 10, 6)
            line.setSpacing(12)
            line.addWidget(AtlasStatusBadge(title, state=state))
            body = _muted_label(message, wrap=True)
            line.addWidget(body, 1)
            self.preview_notifications[state] = frame
            section.addWidget(frame)

    def _build_surfaces_and_typography(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "surfaces")

        # Real theme-owned roles: this is not a second typography system.
        # Designers can compare title, section, body and caption at a glance.
        scale = QGridLayout()
        scale.setHorizontalSpacing(18)
        scale.setVerticalSpacing(6)
        self.preview_type_samples: dict[str, QLabel] = {
            "page": AtlasPageTitle("Titre de page"),
            "section": QLabel("Titre de section"),
            "body": QLabel("Texte courant de l'application"),
            "muted": QLabel("Texte secondaire et indications"),
        }
        self.preview_type_samples["section"].setObjectName("PanelTitle")
        self.preview_type_samples["muted"].setObjectName("MutedLabel")
        for index, (role, caption) in enumerate((
            ("page", "Page"),
            ("section", "Section"),
            ("body", "Courant"),
            ("muted", "Secondaire"),
        )):
            key = _muted_label(caption)
            scale.addWidget(key, index, 0)
            scale.addWidget(self.preview_type_samples[role], index, 1)
        scale.setColumnStretch(1, 1)
        section.addLayout(scale)

        accents = QHBoxLayout()
        self.preview_title_accent = QFrame()
        self.preview_title_accent.setObjectName("TitleAccent")
        self.preview_title_accent.setFixedSize(4, 28)
        accents.addWidget(self.preview_title_accent)
        accents.addWidget(QLabel("Accent du titre"))
        self.preview_card_accent = QFrame()
        self.preview_card_accent.setObjectName("CardTitleAccent")
        self.preview_card_accent.setFixedSize(3, 22)
        accents.addWidget(self.preview_card_accent)
        accents.addWidget(QLabel("Accent de section"))
        accents.addStretch(1)
        section.addLayout(accents)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        cards.setContentsMargins(12, 8, 12, 14)
        self.preview_cards: dict[str, QFrame] = {}
        for role, caption in (
            ("card", "Carte globale"),
            ("Panel", "Panneau"),
            ("QuestPanel", "Panneau de quête"),
        ):
            card = QFrame()
            card.setObjectName(role)
            card.setMinimumHeight(82)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(5)
            heading = QLabel(caption)
            heading.setObjectName("PanelTitle")
            card_layout.addWidget(heading)
            small = _muted_label("Couleurs, bordures et espacements communs", wrap=True)
            card_layout.addWidget(small)
            # Fixed visual samples only. No effect on scrolling rows,
            # focusable controls or the actual game panels.
            apply_unity_panel_shadow(card, **UNITY_PANEL_SHADOW)
            self.preview_cards[role] = card
            cards.addWidget(card, 1)
        section.addLayout(cards)
        self.preview_unavailable_page = AtlasUnavailablePage(
            "Module indisponible", "Exemple de module non encore implémenté.",
            badge="En travaux",
        )
        section.addWidget(self.preview_unavailable_page)

        # Real World Scan shells + read-only value chips. The canvas isn't
        # copied: its own painter is deliberately left untouched.
        world_chrome = QHBoxLayout()
        self.preview_map_chrome: dict[str, QFrame] = {}
        for role, title in (
            ("MapToolbar", "Barre Carte"), ("WorldDetailPanel", "Détails Monde"),
        ):
            panel = QFrame()
            panel.setObjectName(role)
            panel_layout = QVBoxLayout(panel)
            panel_layout.addWidget(QLabel(title))
            apply_unity_panel_shadow(panel, **UNITY_PANEL_SHADOW)
            world_chrome.addWidget(panel, 1)
            self.preview_map_chrome[role] = panel
        section.addLayout(world_chrome)

        value_row = QHBoxLayout()
        self.preview_map_values: dict[str, QLabel] = {}
        for role, title in (
            ("WorldDetailValue", "Position : [0,0]"),
            ("MapDetailValue", "Carte : démonstration"),
        ):
            value = QLabel(title)
            value.setObjectName(role)
            value_row.addWidget(value, 1)
            self.preview_map_values[role] = value
        section.addLayout(value_row)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Plain)
        section.addWidget(separator)
        hint = _muted_label(
            "Les surfaces de démonstration gardent les styles QSS réels. "
            "Les dispositions et données spécifiques restent propres aux modules.",
            wrap=True,
        )
        section.addWidget(hint)

    def _build_scroll_and_resize(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "scroll_resize")
        hint = _muted_label(
            "Déplace la séparation, sélectionne une ligne et fais défiler la liste.",
            wrap=True,
        )
        section.addWidget(hint)

        self.preview_splitter = QSplitter(Qt.Horizontal)
        self.preview_splitter.setObjectName("DevUiResizeSplitter")
        self.preview_splitter.setHandleWidth(6)
        self.preview_splitter.setChildrenCollapsible(False)
        self.preview_scroll_list = QListWidget()
        for item in (
            "Accueil", "Personnage", "Encyclopédie", "Outils",
            "Stuffs", "Organizer", "Almanax", "Launcher",
        ):
            self.preview_scroll_list.addItem(item)
        self.preview_scroll_list.setMinimumWidth(130)
        self.preview_scroll_list.setMaximumHeight(4 * UNITY_SIZES_PX["control_normal"])
        self.preview_scroll_list.currentTextChanged.connect(
            lambda text: self._report(f"Liste : {text}")
        )
        self.preview_splitter.addWidget(self.preview_scroll_list)

        self.preview_scroll_panel = QFrame()
        self.preview_scroll_panel.setObjectName("Panel")
        split_layout = QVBoxLayout(self.preview_scroll_panel)
        title = QLabel("Panneau adaptable")
        title.setObjectName("PanelTitle")
        split_layout.addWidget(title)
        detail = _muted_label(
            "Redimensionnement du panneau · bordure Unity · "
            "barre de défilement partagée",
            wrap=True,
        )
        split_layout.addWidget(detail, 1)
        self.preview_splitter.addWidget(self.preview_scroll_panel)
        self.preview_splitter.setSizes((220, 460))
        section.addWidget(self.preview_splitter)

    def _build_sizes(self, parent: QVBoxLayout) -> None:
        """Show shared sizing rules and live layouts before module migration."""
        section = self._section(parent, "metrics")
        sizing_hint = _muted_label(
            "Trois hauteurs de contrôles et quatre tailles d'icônes, "
            "pilotées par les mêmes métriques que le code commun.",
            wrap=True,
        )
        section.addWidget(sizing_hint)
        self._build_responsive_reference(section)
        self.preview_metric_buttons: dict[str, AtlasButton] = {}
        row = QHBoxLayout()
        for label, size in (
            ("Compact", "compact"),
            ("Normal", "normal"),
            ("Large", "large"),
        ):
            role = f"control_{size}"
            button = AtlasButton(
                f"{label} · {UNITY_SIZES_PX[role]} px", variant="secondary", size=size
            )
            button.setToolTip(f"{label} : {UNITY_SIZES_PX[role]} px")
            self.preview_metric_buttons[role] = button
            row.addWidget(button)
        row.addStretch(1)
        section.addLayout(row)

        icons = QHBoxLayout()
        self.preview_metric_icons: dict[str, QLabel] = {}
        for role in ("icon_small", "icon_normal", "icon_large", "icon_xlarge"):
            size = UNITY_SIZES_PX[role]
            icon = QLabel()
            icon.setPixmap(unity_original_preview_icon("guide", size).pixmap(size, size))
            icon.setToolTip(f"{role} : {size} px")
            icons.addWidget(icon)
            text = _muted_label(f"{size} px")
            icons.addWidget(text)
            self.preview_metric_icons[role] = icon
        icons.addStretch(1)
        section.addLayout(icons)

        metric_rows = (
            *SIZES.items(), *SPACING.items(), *TYPOGRAPHY.items(),
            *((f"LIMIT_{key.upper()}", f"{value} lignes")
              for key, value in UNITY_CONTROL_LIMITS.items()),
            *((f"WINDOW_{key.upper()}", f"{width} × {height} px")
              for key, (width, height) in UNITY_WINDOW_PRESETS_PX.items()),
            *((f"PROFILE_{key.upper()}_{metric.upper()}", f"{value}px")
              for key, profile in UNITY_LAYOUT_PROFILE_PX.items()
              for metric, value in profile.items()),
            *((f"LAYOUT_{key.upper()}", f"{value}px")
              for key, value in UNITY_LAYOUT_SIZES_PX.items()),
            *((f"CONTROL_{key.upper()}", f"{value}px")
              for key, value in UNITY_CONTROL_SIZES_PX.items()),
            *((f"BREAKPOINT_{key.upper()}", f"{value}px")
              for key, value in UNITY_LAYOUT_BREAKPOINTS_PX.items()),
            *((f"ORGANIZER_{key.upper()}", f"{value}px")
              for key, value in UNITY_ORGANIZER_METRICS_PX.items()),
            *((f"GUIDE_READING_{key.upper()}", f"{value}px")
              for key, value in UNITY_GUIDE_READING_METRICS_PX.items()),
        )
        self.preview_metrics = self._catalog_table(
            len(metric_rows), ("Token commun", "Valeur"),
            QHeaderView.ResizeToContents, QHeaderView.Stretch,
        )
        for index, (name, value) in enumerate(metric_rows):
            self.preview_metrics.setItem(index, 0, QTableWidgetItem(name))
            self.preview_metrics.setItem(index, 1, QTableWidgetItem(value))
        self.preview_metrics_toggle = self._add_catalog_table(
            section, self.preview_metrics, "les dimensions et espacements"
        )
        module_intro = _muted_label(
            "Dimensions relevées dans les modules réels. Indexé ne veut pas "
            "dire raccordé : les pages doivent consommer ces valeurs pour "
            "hériter d'une modification future.",
            wrap=True,
        )
        section.addWidget(module_intro)
        module_rows = tuple(
            (module, role, size)
            for module, values in UNITY_MODULE_GEOMETRY_PX.items()
            for role, size in values.items()
        )
        self.preview_module_geometry = QTableWidget(len(module_rows), 3)
        self.preview_module_geometry.setObjectName("DevUiModuleGeometryTable")
        self.preview_module_geometry.setHorizontalHeaderLabels(
            ("Module", "Contrainte indexée", "Valeur existante")
        )
        for i, (module, role, value) in enumerate(module_rows):
            item = QTableWidgetItem(module)
            item.setToolTip(UNITY_MODULE_GEOMETRY_OWNERS[module])
            self.preview_module_geometry.setItem(i, 0, item)
            self.preview_module_geometry.setItem(i, 1, QTableWidgetItem(role))
            label = (
                " × ".join(str(v) for v in value) + " px"
                if isinstance(value, tuple)
                else f"{value} px"
            )
            if role == "dofus_grid_max_columns":
                label = f"{value} colonnes"
            self.preview_module_geometry.setItem(i, 2, QTableWidgetItem(label))
        self.preview_module_geometry_toggle = self._add_catalog_table(
            section, self.preview_module_geometry,
            "les dimensions indexées des modules"
        )


    def _build_responsive_reference(self, section: QVBoxLayout) -> None:
        """Show a stable panel hierarchy at every reference and intermediate size.

        Presets cap the reference width; no virtual screenshot or reordering.
        """
        title = QLabel("Dimensions & responsive · aperçu des modules")
        title.setObjectName("PanelTitle")
        section.addWidget(title)

        selector_row = QHBoxLayout()
        selector_row.setSpacing(UNITY_SPACING_PX["md"])
        selector_row.addWidget(QLabel("Format de fenêtre"))
        self.preview_window_selector = AtlasComboBox()
        self.preview_window_selector.setObjectName("DevUiWindowPreset")
        self.preview_window_selector.setAccessibleName("Format de fenêtre de référence")
        for key, (width, height) in UNITY_WINDOW_PRESETS_PX.items():
            caption = {
                "compact": "Compact",
                "standard": "Standard",
                "large": "Grand",
                "full_hd": "Full HD",
            }[key]
            self.preview_window_selector.addItem(
                f"{caption} · {width} × {height}", key
            )
        self.preview_window_selector.setCurrentIndex(1)
        selector_row.addWidget(self.preview_window_selector)
        selector_row.addStretch(1)
        section.addLayout(selector_row)

        self.preview_window_description = _muted_label(wrap=True)
        section.addWidget(self.preview_window_description)

        self.preview_responsive_mode = _muted_label()
        section.addWidget(self.preview_responsive_mode)

        self.preview_responsive_host = QFrame()
        self.preview_responsive_host.setObjectName("Panel")
        self.preview_responsive_host.setMinimumWidth(0)
        self.preview_responsive_host.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred
        )
        self.preview_responsive_grid = QGridLayout(self.preview_responsive_host)
        self.preview_responsive_grid.setContentsMargins(
            *([UNITY_LAYOUT_SIZES_PX["module_padding"]] * 4)
        )
        self.preview_responsive_grid.setSpacing(
            UNITY_LAYOUT_SIZES_PX["module_gap"]
        )
        self.preview_responsive_cards: list[QFrame] = []
        for index, (name, summary) in enumerate((
            ("Contenu principal", "Liste, détails et progression sans largeur fixe"),
            ("Informations", "Sélection et état compact"),
            ("Actions", "Commandes alignées et largeur disponible"),
        )):
            card = QFrame()
            card.setObjectName("card")
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            apply_unity_panel_shadow(card, **UNITY_PANEL_SHADOW)
            content = QVBoxLayout(card)
            inset = UNITY_LAYOUT_SIZES_PX["module_padding"]
            content.setContentsMargins(inset, inset, inset, inset)
            content.setSpacing(UNITY_SPACING_PX["md"])
            heading = QLabel(name)
            heading.setObjectName("PanelTitle")
            content.addWidget(heading)
            description = _muted_label(summary, wrap=True)
            content.addWidget(description)
            if index == 0:
                progress = atlas_guide_global_progress_bar()
                progress.setValue(45)
                content.addWidget(progress)
            elif index == 1:
                selector = AtlasComboBox()
                selector.addItems(("Personnage 1", "Personnage 2"))
                content.addWidget(selector)
            else:
                action = AtlasButton(
                    "Tester l'action", variant="secondary", size="compact"
                )
                action.clicked.connect(
                    lambda _checked=False: self._report("Responsive : clic reçu")
                )
                content.addWidget(action, 0, Qt.AlignLeft)
            self.preview_responsive_cards.append(card)

        section.addWidget(self.preview_responsive_host)
        self.preview_responsive_columns = 0
        self.preview_responsive_host.installEventFilter(self)
        self.preview_window_selector.currentIndexChanged.connect(
            self._update_responsive_reference
        )
        self._update_responsive_reference()

    def _update_responsive_reference(self, _index: int = -1) -> None:
        key = self.preview_window_selector.currentData()
        width, height = UNITY_WINDOW_PRESETS_PX[key]
        margin = UNITY_LAYOUT_SIZES_PX["page_margin"]
        self.preview_responsive_host.setMaximumWidth(width - 2 * margin)
        self.preview_window_description.setText(
            f"Référence : {width} × {height} px. La fenêtre reste librement "
            "redimensionnable entre les quatre repères. Panneaux, sous-menus "
            "et sélections conservent leur emplacement ; seules les dimensions "
            "flexibles et les espacements s'adaptent."
        )
        self._relayout_responsive_cards()

    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:
        if (watched is getattr(self, "preview_responsive_host", None)
                and event.type() == QEvent.Resize):
            self._relayout_responsive_cards()
        return super().eventFilter(watched, event)

    def _relayout_responsive_cards(self, width: int | None = None) -> None:
        """Keep all structural panels in their original positions on resize.

        Only shared margins, padding and gaps evolve between four references.
        Existing Qt widgets and their signal connections are never recreated.
        """
        grid = self.preview_responsive_grid
        requested_width = (
            self.preview_responsive_host.width() if width is None else width
        )
        preset_width = UNITY_WINDOW_PRESETS_PX[
            self.preview_window_selector.currentData()
        ][0]
        metrics = unity_layout_metrics(min(max(0, requested_width), preset_width))
        inset = metrics["module_padding"]
        margins = grid.contentsMargins()
        if (
            margins.left() != inset or margins.top() != inset
            or margins.right() != inset or margins.bottom() != inset
        ):
            grid.setContentsMargins(inset, inset, inset, inset)
        if grid.spacing() != metrics["module_gap"]:
            grid.setSpacing(metrics["module_gap"])

        # Fixed semantic order: main content | information | actions.
        # Four stretch units give a stable 50 / 25 / 25 grid, even at 900 px.
        # No QLayout.takeAt or breakpoint-driven panel movement.
        if self.preview_responsive_columns != 3:
            positions = ((0, 0, 1, 2), (0, 2, 1, 1), (0, 3, 1, 1))
            for column in range(4):
                grid.setColumnStretch(column, 1)
            for card, (row, column, row_span, column_span) in zip(
                self.preview_responsive_cards, positions
            ):
                grid.addWidget(card, row, column, row_span, column_span)
            self.preview_responsive_columns = 3
        self.preview_responsive_mode.setText(
            "Disposition fixe 50 / 25 / 25 · 3 modules dans le même ordre · "
            f"marge {metrics['page_margin']} px · "
            f"espacement {metrics['module_gap']} px"
        )

    def _build_panels(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "panels")
        control_row = QHBoxLayout()
        self.panel_toggle = AtlasPanelToggle()
        self.panel_toggle.clicked.connect(self._toggle_panel)
        control_row.addWidget(self.panel_toggle)
        control_row.addWidget(QLabel("Masquer / réafficher la carte"))
        control_row.addStretch(1)
        section.addLayout(control_row)

        self.preview_panel = QFrame()
        self.preview_panel.setObjectName("card")
        apply_unity_panel_shadow(self.preview_panel, **UNITY_PANEL_SHADOW)
        panel_layout = QVBoxLayout(self.preview_panel)
        panel_layout.addWidget(QLabel("Carte commune Unity · bordure et fond partagés"))
        section.addWidget(self.preview_panel)

        self.preview_glass_panel = QFrame()
        self.preview_glass_panel.setObjectName("OrganizerPanel")
        apply_unity_panel_shadow(self.preview_glass_panel, **UNITY_PANEL_SHADOW)
        line = QHBoxLayout(self.preview_glass_panel)
        glass_title = _muted_label("Organizer · glass Unity et dégradé communs")
        line.addWidget(glass_title)
        section.addWidget(self.preview_glass_panel)

    def _toggle_panel(self) -> None:
        collapsed = not bool(self.panel_toggle.property("collapsed"))
        self.panel_toggle.set_collapsed(collapsed)
        self.preview_panel.setHidden(collapsed)
        self._report("Panneau masqué" if collapsed else "Panneau affiché")

    def _build_backdrop(self, parent: QVBoxLayout) -> None:
        """Display the actual cached wallpaper/gradient widget used by the shell."""
        section = self._section(parent, "backdrop")
        self.preview_backdrop = UnityBackdrop()
        self.preview_wallpaper_status = _muted_label(
            "Fond actif : image étoilée Unity locale nettoyée."
            if self.preview_backdrop.has_wallpaper else
            "Fond actif : dégradé Unity de secours (image étoilée indisponible)."
        )
        section.addWidget(self.preview_wallpaper_status)
        note = _muted_label(
            "Aucun faux motif étoilé : la démonstration utilise exactement "
            "le même UnityBackdrop que l'application.",
            wrap=True,
        )
        section.addWidget(note)
        self.preview_backdrop.setFixedHeight(5 * UNITY_SIZES_PX["control_normal"])
        wrapper = QVBoxLayout(self.preview_backdrop)
        wrapper.setContentsMargins(16, 14, 16, 14)
        card = QFrame()
        card.setObjectName("card")
        apply_unity_panel_shadow(card, **UNITY_PANEL_SHADOW)
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(AtlasPageTitle("Carte sur fond Unity"))
        muted = _muted_label("Dégradé, transparence et bordures hérités du thème")
        card_layout.addWidget(muted)
        wrapper.addWidget(card)
        section.addWidget(self.preview_backdrop)

    def _build_startup_preview(self, parent: QVBoxLayout) -> None:
        """Show startup's actual global QSS selectors without running preload."""
        section = self._section(parent, "startup")
        self.startup_title = QLabel("Dofus Atlas")
        self.startup_title.setObjectName("PreloadPopupTitle")
        self.startup_title.setAlignment(Qt.AlignCenter)
        section.addWidget(self.startup_title)

        self.startup_status = QLabel("Préparation de Guides & Succès…")
        self.startup_status.setObjectName("PreloadPopupCurrent")
        self.startup_status.setAlignment(Qt.AlignCenter)
        section.addWidget(self.startup_status)

        self.startup_progress = configure_unity_progress_bar(
            QProgressBar(), object_name="PreloadPopupProgress", maximum=3,
            text_visible=True, display_format="%p %",
        )
        self.startup_progress.setValue(2)
        section.addWidget(self.startup_progress)

    def _build_guide_samples(self, parent: QVBoxLayout) -> None:
        """Render Guide's real shared selectors; never duplicate their colors."""
        section = self._section(parent, "guides")
        # Production Guide selectors, rendered side by side with the same
        # shared QSS as the rest of Dev UI (no fake quests or local palette).
        guide_surfaces = QHBoxLayout()
        self.guide_sample_header = QFrame()
        self.guide_sample_header.setObjectName("GuideHeader")
        header_layout = QVBoxLayout(self.guide_sample_header)
        header_layout.addWidget(QLabel("En-tête · panneau glass Unity"))
        apply_unity_panel_shadow(self.guide_sample_header, **UNITY_PANEL_SHADOW)
        guide_surfaces.addWidget(self.guide_sample_header, 1)

        self.guide_sample_category = QFrame()
        self.guide_sample_category.setObjectName("GuidesHomeCategory")
        category_layout = QVBoxLayout(self.guide_sample_category)
        category_layout.addWidget(QLabel("Catégorie · même matériau"))
        apply_unity_panel_shadow(self.guide_sample_category, **UNITY_PANEL_SHADOW)
        guide_surfaces.addWidget(self.guide_sample_category, 1)
        section.addLayout(guide_surfaces)

        guide_cards = QHBoxLayout()
        self.guide_sample_dofus_card = QFrame()
        self.guide_sample_dofus_card.setObjectName("GuideDofusCard")
        card_layout = QVBoxLayout(self.guide_sample_dofus_card)
        card_layout.addWidget(QLabel("Dofus · état normal"))
        apply_unity_panel_shadow(self.guide_sample_dofus_card, **UNITY_PANEL_SHADOW)
        guide_cards.addWidget(self.guide_sample_dofus_card, 1)

        self.guide_sample_active_route = QFrame()
        self.guide_sample_active_route.setObjectName("GuideQuestLineActive")
        route_layout = QVBoxLayout(self.guide_sample_active_route)
        route_layout.addWidget(QLabel("Étape active · trait vert fin"))
        guide_cards.addWidget(self.guide_sample_active_route, 1)
        section.addLayout(guide_cards)

        # Real source identities, one reusable empty reader. Metadata is
        # never promoted to a playable route, page count or player progress.
        from app.modules.encyclopedia.views.guide_library_sources import load_ganymede_listings

        try:
            self._guide_preview_listings = load_ganymede_listings()
        except (OSError, ValueError, KeyError, TypeError):
            self._guide_preview_listings = ()
        self.guide_source_preview_combo = AtlasComboBox()
        self.guide_source_preview_combo.setSizeAdjustPolicy(
            self.guide_source_preview_combo.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.guide_source_preview_combo.setMinimumContentsLength(20)
        self.guide_source_preview_combo.setAccessibleName("Sélectionner un conteneur Guide (aperçu)")
        for listing in self._guide_preview_listings:
            self.guide_source_preview_combo.addItem(listing.title, listing.source_id)
        self.guide_source_preview_combo.setEnabled(bool(self._guide_preview_listings))
        self.guide_source_preview_status = _muted_label(wrap=True)
        section.addWidget(self.guide_source_preview_status)
        section.addWidget(self.guide_source_preview_combo)

        self.guide_sample_compact_header = AtlasGuideReadingHeader(
            "Guide indisponible", show_cover=False,
        )
        self.guide_sample_compact_header.set_metric_available("preparation", False)
        self.guide_sample_compact_header.set_metric_available("summary", False)
        self.guide_sample_compact_header.global_details_button.setEnabled(False)
        self.guide_sample_compact_header.participants_button.setEnabled(False)
        section.addWidget(self.guide_sample_compact_header)
        self.guide_source_preview_sheet = AtlasGuideSheetHeader(total=0)
        self.guide_source_preview_sheet.back_button.setEnabled(False)
        self.guide_source_preview_sheet.title_label.hide()
        section.addWidget(self.guide_source_preview_sheet)
        self.guide_source_preview_combo.currentIndexChanged.connect(self._select_guide_source_preview)
        self._select_guide_source_preview(self.guide_source_preview_combo.currentIndex())

        self.preview_quest_start_position = QLabel(
            "Position de lancement : [4,-18]"
        )
        self.preview_quest_start_position.setObjectName("QuestLaunchPosition")
        self.preview_quest_start_position.setAccessibleName(
            "Aperçu typographique d'une position de lancement"
        )
        section.addWidget(self.preview_quest_start_position)

        self.guide_sample_summary = AtlasGuidePreparationSummary("Objets", ready=0, total=1)
        section.addWidget(self.guide_sample_summary)

        self.guide_sample_row = AtlasGuidePreparationRow(
            "Ressource de démonstration", quantity=3,
            stock_formatter=preparation_stock_presentation,
        )
        self.guide_sample_row.attach_details(lambda: ("Personnage fictif 1 : besoin 3",))
        self.guide_copy_button = self.guide_sample_row.name_button
        self.guide_sample_row.ready_button.toggled.connect(
            lambda checked: self.guide_sample_summary.set_counts(int(checked), 1)
        )
        self.guide_sample_row.ready_button.toggled.connect(
            lambda checked: self.guide_sample_row.set_saved_state(
                confirmed=int(checked), participants=1, owned=3 if checked else 0,
            )
        )
        self.guide_copy_button.clicked.connect(
            lambda: self._report("Guide · bouton Copier cliqué")
        )
        section.addWidget(self.guide_sample_row)

        self.guide_manual_nav = AtlasGuideReadingNav()
        validation = AtlasGuideValidationButton()
        self.guide_manual_nav.validation_layout.addWidget(validation)
        self.guide_manual_nav.previous_button.clicked.connect(
            lambda: self._report("Guide · Précédent (aperçu)")
        )
        self.guide_manual_nav.next_button.clicked.connect(
            lambda: self._report("Guide · Suivant (aperçu)")
        )
        validation.toggled.connect(
            lambda checked: self._report(f"Guide · fiche {'validée' if checked else 'non validée'} (aperçu)")
        )
        section.addWidget(self.guide_manual_nav)

        # Preview the real guide reading surface, without a local stylesheet.
        self.guide_manual_scroll_sample = configure_unity_scroll_area(QScrollArea())
        self.guide_manual_scroll_sample.setObjectName("GuideManualScroll")
        self.guide_manual_scroll_sample.setFixedHeight(88)
        content = QWidget()
        content.setObjectName("GuideManualContent")
        content_row = QVBoxLayout(content)
        content_row.addWidget(QLabel("Zone du texte du guide · bordure complète"))
        self.guide_manual_scroll_sample.setWidget(content)
        section.addWidget(self.guide_manual_scroll_sample)

        # Semantic links consume exactly the same indexed Unity color roles
        # as the shared Guide renderer; no additional stylesheet or colors.
        link_caption = _muted_label("Liens des étapes · couleurs Unity communes")
        section.addWidget(link_caption)
        link_grid = QGridLayout()
        link_grid.setHorizontalSpacing(10)
        link_grid.setVerticalSpacing(4)
        self.preview_guide_link_labels: dict[str, QLabel] = {}
        for index, (category, name) in enumerate((
            ("monster", "Monstre"), ("boss", "Boss"),
            ("item", "Objet"), ("equipment", "Équipement"),
            ("npc", "PNJ"), ("position", "Position"),
            ("quest", "Quête"),
        )):
            # Real rich-text anchors use the same formatter as the Guides.
            # Preview destinations never leave Dev UI or impersonate gameplay.
            label = QLabel(entity_link_markup(
                name, category, f"dev-preview:{category}", PALETTE,
            ))
            label.setTextFormat(Qt.RichText)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
            label.setOpenExternalLinks(False)
            label.linkActivated.connect(
                lambda _href, kind=category: self._report(
                    f"Aperçu lien sémantique : {kind}"
                )
            )
            label.setAccessibleName(f"Couleur de lien Guide : {name}")
            label.setToolTip(f"{name} · rôle Unity : {category}")
            link_grid.addWidget(label, index // 4, index % 4)
            self.preview_guide_link_labels[category] = label
        section.addLayout(link_grid)

        # Use the real Guide Ultime parent selector and the same native
        # QComboBox as Successes. Never apply a per-widget QSS override.
        self.guide_ultime_sample = QFrame()
        self.guide_ultime_sample.setObjectName("GuideUltimeGeneratedView")
        guide_layout = QHBoxLayout(self.guide_ultime_sample)
        guide_layout.addWidget(QLabel("Menu Guide Ultime · style Succès"), 1)
        self.guide_ultime_combo = AtlasComboBox()
        self.guide_ultime_combo.view().setAlternatingRowColors(False)
        self.guide_ultime_combo.addItems(("Normal", "Rapide", "Instantané"))
        self.guide_ultime_combo.currentTextChanged.connect(
            lambda value: self._report(f"Guide Ultime : {value}")
        )
        guide_layout.addWidget(self.guide_ultime_combo, 0, Qt.AlignVCenter)
        section.addWidget(self.guide_ultime_sample)

    def _select_guide_source_preview(self, index: int) -> None:
        listings = self._guide_preview_listings
        if not 0 <= index < len(listings):
            self.guide_source_preview_status.setText("Index Ganymède indisponible · aucun contenu chargé")
            self.guide_sample_compact_header.set_guide_title("Guide indisponible")
            return
        listing = listings[index]
        self.guide_sample_compact_header.set_guide_title(listing.title)
        self.guide_source_preview_status.setText(
            f"Conteneur {index + 1}/{len(listings)} · ID source {listing.source_id} · aperçu sans contenu"
        )

    def _build_ui_assets(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "assets")

        all_icon_names = (*UNITY_ICON_NAMES, *UNITY_ICON_PENDING)
        local_icon_count = sum(
            sprite_icon_path(name) is not None for name in all_icon_names
        )
        source_hint = _muted_label(
            f"Sources Unity communes : {local_icon_count}/{len(all_icon_names)} "
            "pictogrammes repérés dans ce lancement · couleurs originales conservées"
        )
        section.addWidget(source_hint)
        icons = QGridLayout()
        self.preview_icon_grid = icons
        icons.setHorizontalSpacing(12)
        icons.setVerticalSpacing(6)
        self.preview_icon_labels: dict[str, QLabel] = {}
        icon_captions = {
            "guide": "Guides", "quest": "Quêtes", "success": "Succès",
            "encyclopedia": "Encyclopédie", "character": "Personnage",
            "dofus": "Dofus", "map": "Carte", "inventory": "Inventaire",
            "jobs": "Métiers", "bestiary": "Bestiaire", "craft": "Crafts",
            "equipment": "Stuffs", "organizer": "Organizer",
            "almanax": "Almanax",
        }
        self.preview_icon_missing: dict[str, QLabel] = {}
        for index, name in enumerate(all_icon_names):
            cell = QWidget()
            cell.setObjectName("DevUiIconCell")
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(4, 4, 4, 4)
            cell_layout.setSpacing(9)
            symbol = QLabel()
            symbol.setAlignment(Qt.AlignCenter)
            symbol.setFixedSize(32, 32)
            symbol.setAccessibleName(f"Icône {icon_captions[name]}")
            size = UNITY_SIZES_PX["icon_large"]
            icon = unity_original_preview_icon(name, size)
            if icon.isNull():
                # Not present at this path in *this environment*. Do not
                # claim the user's original assets are unavailable elsewhere.
                symbol.setObjectName("DevUiMissingIcon")
                symbol.setText("—")
                symbol.setToolTip(
                    f"{icon_captions[name]} · non détecté dans le dossier "
                    "Unity de cet environnement"
                )
                self.preview_icon_missing[name] = symbol
            else:
                symbol.setPixmap(icon.pixmap(size, size))
                symbol.setToolTip(
                    f"{icon_captions[name]} · sprite Unity local ou repli Atlas"
                )
            caption = _muted_label(icon_captions[name])
            cell_layout.addWidget(symbol)
            cell_layout.addWidget(caption, 1)
            if name in self.preview_icon_missing:
                flag = QLabel("Non détecté ici")
                flag.setObjectName("DevUiMissingIconText")
                cell_layout.addWidget(flag)
            icons.addWidget(cell, index // 4, index % 4)
            self.preview_icon_labels[name] = symbol
        section.addLayout(icons)

        tools = QHBoxLayout()
        for label in ("Ctrl + K", "Shift + F2"):
            shortcut = QToolButton()
            shortcut.setObjectName("InlineShortcutButton")
            shortcut.setText(label)
            shortcut.setToolTip("Exemple visuel de raccourci (aucune action globale)")
            shortcut.clicked.connect(
                lambda _checked=False, value=label: self._report(
                    f"Raccourci affiché : {value}"
                )
            )
            tools.addWidget(shortcut)
        tooltip = AtlasButton("Survole-moi", variant="secondary")
        tooltip.setToolTip("Tooltip du thème Unity partagé")
        tooltip.clicked.connect(lambda: self._report("Info-bulle contrôlée"))
        tools.addWidget(tooltip)
        tools.addStretch(1)
        section.addLayout(tools)

    def _build_scope_matrix(self, parent: QVBoxLayout) -> None:
        """Show migration scope without incorrectly claiming all screens migrated."""
        section = self._section(parent, "coverage")
        note = _muted_label(
            "Exemples de réutilisation dans les modules. La couverture complète "
            "reste à vérifier écran par écran.",
            wrap=True,
        )
        section.addWidget(note)

        modules = UNITY_UI_CONSUMERS
        shared_examples = {
            "Accueil": "Boutons et badge Almanax",
            "Personnage": "Menu de sélection du personnage",
            "Quêtes": "Menus de filtre et liens",
            "Succès": "Menus et lien d’alignement",
            "Guides": "Menus, fil d’Ariane et liens",
            "Outils": "Catégories et actions Crafts",
            "Organizer": "Variantes dans la feuille Qt globale",
            "Almanax": "Calendrier et badge depuis le shell",
            "Launcher": "Couleurs et typographie Unity via Tk",
            "Craft": "Recettes, quantités et fenêtres Métiers",
            "Carte du monde": "Outils et panneaux cartographiques",
            "Paramètres": "Shell, sections et préférences",
            "Dev UI": "Galerie et démonstrations partagées",
            "Popups et dialogues": "12 cas de capture, pas 12 composants",
            "Overlays et démarrage": "Radial, splash et préchargement",
        }
        self.preview_scope = self._catalog_table(
            len(modules), ("Module", "Source de style cible", "Exemple partagé"),
            QHeaderView.ResizeToContents, QHeaderView.ResizeToContents, QHeaderView.Stretch,
        )
        for index, module in enumerate(modules):
            self.preview_scope.setItem(index, 0, QTableWidgetItem(module))
            consumer = UI_CONSUMER_INDEX[module]
            source = {
                "qt": "Thème Qt commun",
                "qt_scoped": "Thème Qt + variantes Organizer",
                "tk": "Palette Unity / Tk",
            }[consumer["adapter"]]
            cell = QTableWidgetItem(source)
            cell.setToolTip("Fichiers indexés :\n" + "\n".join(consumer["paths"]))
            self.preview_scope.setItem(index, 1, cell)
            self.preview_scope.setItem(
                index, 2, QTableWidgetItem(shared_examples.get(module, "À vérifier"))
            )
        self.preview_scope.setToolTip(
            "Inventaire du périmètre, pas une certification de migration"
        )
        self.preview_scope_toggle = self._add_catalog_table(
            section, self.preview_scope, "les modules consommateurs"
        )

        # Actual secondary surfaces from the same consumer registry. Keeping
        # their owners visible prevents a gallery preview from masquerading
        # as proof that a popup/overlay was migrated or captured.
        secondary = []
        seen_surfaces = set()
        for module in ("Popups et dialogues", "Overlays et démarrage"):
            for label, path in UI_CONSUMER_INDEX[module]["surfaces"]:
                key = (label, path)
                if key in seen_surfaces:
                    continue  # Preload is both a dialog and a startup surface.
                seen_surfaces.add(key)
                secondary.append((module, label, path))
        secondary_title = QLabel(
            "Usages existants (pas des composants différents) : fenêtres, "
            "menus, zoom et overlays"
        )
        secondary_title.setObjectName("PanelTitle")
        section.addWidget(secondary_title)
        self.preview_secondary_surfaces = self._catalog_table(
            len(secondary), ("Zone", "UI existante", "Fichier propriétaire"),
            QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
        )
        self.preview_secondary_surfaces.horizontalHeader().setStretchLastSection(True)
        for index, (module, label, path) in enumerate(secondary):
            for column, value in enumerate(
                (module, label, path.rsplit("/", 1)[-1])
            ):
                item = QTableWidgetItem(value)
                if column == 2:
                    item.setToolTip(path)
                self.preview_secondary_surfaces.setItem(index, column, item)
        self.preview_secondary_surfaces.setToolTip(
            "Références au code réel ; la galerie ne certifie pas les interactions Windows"
        )
        self.preview_secondary_toggle = self._add_catalog_table(
            section, self.preview_secondary_surfaces, "les fenêtres secondaires"
        )

        counts_title = QLabel("Compteurs de mutualisation — types ≠ variantes ≠ usages")
        counts_title.setObjectName("PanelTitle")
        section.addWidget(counts_title)
        craft_dialog_count = sum(
            path == "app/pages/craft_page.py" and label.endswith("Dialog")
            for label, path in UI_CONSUMER_INDEX["Popups et dialogues"]["surfaces"]
        )
        self.preview_shared_ui_counts = _muted_label(
            f"Boutons classiques : 1 AtlasButton / {len(BUTTON_OBJECT_NAMES)} "
            "rôles visuels. "
            "Sélections : 1 AtlasComboBox partagé et 1 règle de largeur "
            "pour les compteurs QSpinBox. "
            f"Dialogues standard : 1 AtlasDialog / "
            f"{len(_DIALOG_PREVIEW_VARIANTS)} variantes de démonstration. "
            f"Craft : {craft_dialog_count} usages sur AtlasDialog commun. "
            f"Popups et overlays : {len(secondary)} usages existants distincts "
            "(pas autant de composants).",
            wrap=True,
        )
        section.addWidget(self.preview_shared_ui_counts)

        family_keys = tuple(UNITY_UI_FAMILY_INDEX)
        contract_label = QLabel(
            "Tous les éléments prévus en uniformisation (cliquer une ligne "
            "pour ouvrir son exemple dans UI Dev)"
        )
        contract_label.setObjectName("PanelTitle")
        section.addWidget(contract_label)
        self.preview_contract = self._catalog_table(
            len(UNITY_UI_UNIFICATION_CONTRACT), ("Élément prévu", "Famille UI"),
            QHeaderView.Stretch, QHeaderView.ResizeToContents,
        )
        for index, (label, family) in enumerate(UNITY_UI_UNIFICATION_CONTRACT):
            self.preview_contract.setItem(index, 0, QTableWidgetItem(label))
            family_item = QTableWidgetItem(UNITY_UI_FAMILY_INDEX[family]["title"])
            scope = UNITY_UI_FAMILY_INDEX[family]["scope"]
            family_item.setToolTip(
                "Démo de référence ; adoption à vérifier écran par écran"
                if scope != "prototype" else
                "Prototype seulement : non généralisé dans l'application"
            )
            self.preview_contract.setItem(index, 1, family_item)
        self.preview_contract.cellClicked.connect(
            lambda row, _col: self._jump_to_section(
                family_keys.index(UNITY_UI_UNIFICATION_CONTRACT[row][1])
            )
        )
        self.preview_contract_toggle = self._add_catalog_table(
            section, self.preview_contract, "le détail par famille"
        )

    def _build_motion_gallery(self, parent: QVBoxLayout) -> None:
        """Replay bounded Qt motions using real Unity-themed controls.

        Timings are adjustable prototypes, not measured DOFUS client timings.
        Keep these isolated from production widgets until visual acceptance.
        """
        section = self._section(parent, "motion")
        note = _muted_label(
            "Transitions de prévisualisation Qt. Les durées ne sont pas "
            "encore mesurées sur DOFUS Unity : comparer puis valider avant "
            "toute généralisation.",
            wrap=True,
        )
        section.addWidget(note)

        timing = QHBoxLayout()
        timing.addWidget(QLabel("Durée de référence"))
        self.motion_duration = configure_unity_number_spinbox(
            QSpinBox(), minimum=80, maximum=600, value=180,
            object_name="DevUiMotionDuration", suffix=" ms",
        )
        self.motion_duration.setSingleStep(20)
        timing.addWidget(self.motion_duration)
        timing.addStretch(1)
        section.addLayout(timing)

        controls = QHBoxLayout()
        self.motion_buttons: dict[str, AtlasButton] = {}
        for key, caption in (
            ("apparition", "Rejouer apparition"),
            ("panneau", "Rejouer panneau"),
            ("progression", "Rejouer progression"),
        ):
            button = AtlasButton(caption, variant="secondary")
            button.clicked.connect(
                lambda _checked=False, name=key: self._play_motion(name)
            )
            self.motion_buttons[key] = button
            controls.addWidget(button)
        controls.addStretch(1)
        section.addLayout(controls)

        self.motion_fade_card = QFrame()
        self.motion_fade_card.setObjectName("card")
        fade_layout = QHBoxLayout(self.motion_fade_card)
        fade_layout.addWidget(QLabel("Apparition · carte Unity"))
        section.addWidget(self.motion_fade_card)
        self.motion_opacity = QGraphicsOpacityEffect(self.motion_fade_card)
        self.motion_opacity.setOpacity(1.0)
        self.motion_fade_card.setGraphicsEffect(self.motion_opacity)

        self.motion_panel = QFrame()
        self.motion_panel.setObjectName("card")
        panel_layout = QHBoxLayout(self.motion_panel)
        panel_layout.addWidget(QLabel("Panneau · ouverture verticale"))
        self._motion_panel_height = 3 * UNITY_SIZES_PX["control_compact"]
        self.motion_panel.setMaximumHeight(self._motion_panel_height)
        section.addWidget(self.motion_panel)

        self.motion_progress = configure_unity_progress_bar(
            QProgressBar(), object_name="DevUiMotionProgress", text_visible=True,
        )
        self.motion_progress.setValue(100)
        section.addWidget(self.motion_progress)

        # Animations have Qt parents and are stopped automatically when the
        # lazily constructed Dev UI page is released on returning Home.
        self.motion_animations: dict[str, QPropertyAnimation] = {
            "apparition": QPropertyAnimation(
                self.motion_opacity, b"opacity", self
            ),
            "panneau": QPropertyAnimation(
                self.motion_panel, b"maximumHeight", self
            ),
            "progression": QPropertyAnimation(
                self.motion_progress, b"value", self
            ),
        }
        for animation in self.motion_animations.values():
            animation.setDuration(self.motion_duration.value())
            animation.setEasingCurve(QEasingCurve.OutCubic)

    def _play_motion(self, name: str) -> None:
        """Restart the selected preview without overlapping animations."""
        animation = self.motion_animations[name]
        animation.stop()
        animation.setDuration(self.motion_duration.value())
        if name == "apparition":
            self.motion_opacity.setOpacity(0.35)
            animation.setStartValue(0.35)
            animation.setEndValue(1.0)
        elif name == "panneau":
            self.motion_panel.setMaximumHeight(0)
            animation.setStartValue(0)
            animation.setEndValue(self._motion_panel_height)
        else:
            self.motion_progress.setValue(0)
            animation.setStartValue(0)
            animation.setEndValue(100)
        animation.start()
        self._report(
            f"Motion Gallery : {name} · {self.motion_duration.value()} ms"
        )

    def _build_dialogs_and_colors(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "dialogs")
        section.addWidget(AtlasPageTitle("Titre Atlas partagé"))
        muted = _muted_label("Texte secondaire · même typographie sur chaque écran")
        section.addWidget(muted)
        family_note = _muted_label(
            "Un seul conteneur AtlasDialog pour les fenêtres classiques : "
            "en-tête, contenu et actions changent selon l'utilisation. "
            "Le zoom Quêtes/Guides réutilise AtlasImagePopup ; les menus, "
            "suggestions et overlays conservent leur comportement spécialisé. "
            "La largeur du dialogue suit son contenu et les limites partagées.",
            wrap=True,
        )
        section.addWidget(family_note)
        row = QHBoxLayout()
        self.dialog_button = AtlasButton("Ouvrir une fenêtre", variant="primary")
        self.dialog_button.clicked.connect(self._open_preview_dialog)
        row.addWidget(self.dialog_button)
        self.preview_image_zoom = AtlasButton("Aperçu du zoom image", variant="secondary")
        self.preview_image_zoom.clicked.connect(self._open_image_zoom_preview)
        row.addWidget(self.preview_image_zoom)
        row.addStretch(1)
        section.addLayout(row)
        variants_row = QHBoxLayout()
        self.preview_dialog_variants: dict[str, AtlasButton] = {}
        for state, caption in _DIALOG_PREVIEW_VARIANTS:
            variant_button = AtlasButton(
                caption, variant="danger" if state == "danger" else "secondary"
            )
            variant_button.clicked.connect(
                lambda _checked=False, mode=state:
                    self._open_preview_dialog_variant(mode)
            )
            self.preview_dialog_variants[state] = variant_button
            variants_row.addWidget(variant_button)
        variants_row.addStretch(1)
        section.addLayout(variants_row)
        icons_row = QHBoxLayout()
        for name in ("guide", "quest", "success", "character"):
            icon_label = QLabel()
            icon_label.setPixmap(unity_original_preview_icon(name).pixmap(24, 24))
            icon_label.setToolTip(name)
            icons_row.addWidget(icon_label)
        icons_row.addStretch(1)
        section.addLayout(icons_row)

        craft_note = _muted_label(
            "Fenêtres Craft réelles (sans mutation des données) : "
            "quatre contenus métier sur le conteneur AtlasDialog commun "
            "et l'en-tête AtlasDialogHeader partagé.",
            wrap=True,
        )
        section.addWidget(craft_note)
        craft_row = QHBoxLayout()
        self.preview_craft_dialog_choice = AtlasComboBox()
        self.preview_craft_dialog_choice.setObjectName("DevUiCraftDialogChoice")
        self.preview_craft_dialog_choice.addItems(
            ("Ressources Craft", "Panoplie", "Leveling métier", "Route métier")
        )
        self.preview_craft_dialog_choice.setAccessibleName(
            "Choisir une fenêtre Craft réelle à prévisualiser"
        )
        craft_row.addWidget(self.preview_craft_dialog_choice)
        self.preview_craft_dialog_open = AtlasButton(
            "Voir la fenêtre Craft", variant="secondary"
        )
        self.preview_craft_dialog_open.clicked.connect(
            self._open_craft_dialog_preview
        )
        craft_row.addWidget(self.preview_craft_dialog_open)
        craft_row.addStretch(1)
        section.addLayout(craft_row)

        colors = self._section(parent, "palette")
        intro = _muted_label(
            "Couleurs principales et emplacement dans l'UI darkStone : "
            "les mêmes rôles sont utilisés dans les modules. "
            "Les boutons partagés suivent strictement les couleurs Unity.",
            wrap=True,
        )
        colors.addWidget(intro)

        main_grid = QGridLayout()
        self.preview_main_color_roles = UNITY_MAIN_ROLES
        for index, role in enumerate(UNITY_MAIN_ROLES):
            main_grid.addWidget(
                self._palette_swatch(role), index // 5, index % 5
            )
        colors.addLayout(main_grid)

        placement_title = QLabel("À quel endroit chaque couleur s'applique")
        placement_title.setObjectName("PanelTitle")
        colors.addWidget(placement_title)
        placement = QGridLayout()
        self.preview_ui_usage = UNITY_UI_USAGE
        for index, (caption, surface_role, accent_role) in enumerate(UNITY_UI_USAGE):
            card = QFrame()
            card.setObjectName("card")
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(8, 6, 8, 6)
            title = QLabel(caption)
            title.setMinimumWidth(112)
            card_layout.addWidget(title)
            for role in (surface_role, accent_role):
                chip = QLabel()
                chip.setPixmap(self._color_pixmap(PALETTE[role], 25, 18))
                chip.setToolTip(f"{role} : {PALETTE[role]}")
                card_layout.addWidget(chip)
            placement.addWidget(card, index // 2, index % 2)
        colors.addLayout(placement)

        self.preview_palette_toggle = AtlasButton(
            "Afficher la palette technique complète", variant="secondary"
        )
        self.preview_palette_toggle.clicked.connect(self._toggle_palette_details)
        colors.addWidget(self.preview_palette_toggle)
        self.preview_palette_details = QWidget()
        detail_layout = QGridLayout(self.preview_palette_details)
        # Technical roles remain available for audit, but do not drown the UI.
        for index, role in enumerate(PALETTE):
            detail_layout.addWidget(
                self._palette_swatch(role), index // 3, index % 3
            )
        self.preview_palette_details.hide()
        colors.addWidget(self.preview_palette_details)

    @staticmethod
    def _color_pixmap(value: str, width: int = 32, height: int = 18) -> QPixmap:
        """Render both flat colors and actual QSS gradients in the gallery."""
        pix = QPixmap(width, height)
        color = QColor(value)
        if color.isValid():
            pix.fill(color)
            return pix
        pix.fill(Qt.transparent)
        # The canonical gradient tokens contain explicit QSS stop positions.
        stops = re.findall(
            r"stop:\s*([01](?:\.\d+)?)\s+(#[0-9a-fA-F]{6})",
            value,
        )
        if stops:
            coords = re.search(
                r"x1:\s*([01]),\s*y1:\s*([01]),\s*x2:\s*([01]),\s*y2:\s*([01])",
                value,
            )
            x1, y1, x2, y2 = (
                [int(part) for part in coords.groups()] if coords else [0, 0, 1, 0]
            )
            gradient = QLinearGradient(
                x1 * width, y1 * height, x2 * width, y2 * height
            )
            for offset, hex_color in stops:
                gradient.setColorAt(float(offset), QColor(hex_color))
            painter = QPainter(pix)
            painter.fillRect(pix.rect(), QBrush(gradient))
            painter.end()
        return pix

    def _palette_swatch(self, role: str) -> QWidget:
        value = PALETTE[role]
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        chip = QLabel()
        chip.setPixmap(self._color_pixmap(value))
        chip.setAccessibleName(f"Couleur {role}")
        layout.addWidget(chip)
        label = _muted_label(role)
        label.setToolTip(f"{role} : {value}")
        layout.addWidget(label, 1)
        return cell

    def _toggle_palette_details(self) -> None:
        visible = self.preview_palette_details.isHidden()
        self.preview_palette_details.setVisible(visible)
        self.preview_palette_toggle.setText(
            "Masquer les nuances techniques" if visible
            else "Afficher la palette technique complète"
        )
        self._report("Palette technique affichée" if visible
                     else "Palette technique masquée")

    def _present_preview_dialog(self, dialog: AtlasDialog, *, opened: str, closed: str) -> None:
        """Own one Dev UI preview at a time; release the old Qt window."""
        if present_transient_dialog(
            self, "_preview_dialog", dialog, mode="open",
            on_finished=lambda _result: self._report(closed),
        ):
            self._report(opened)

    def _open_craft_dialog_preview(self) -> None:
        """Open an existing Craft dialog with harmless, local demonstration data."""
        # Lazy import: the developer gallery must not preload Craft or game
        # data merely because Settings/Dev UI was opened.
        from app.pages.craft_page import (
            CraftResourceDialog, ItemSetDialog, LevelingDialog, RouteDialog,
        )

        choice = self.preview_craft_dialog_choice.currentIndex()
        if choice == 0:
            dialog = CraftResourceDialog(
                {"Fer": {"quantity": 8}, "Ortie": {"quantity": 12}},
                ["Ressource de démonstration sans recette"],
                self,
            )
        elif choice == 1:
            dialog = ItemSetDialog(
                {"name_fr": "Panoplie de démonstration",
                 "items": [{"name": "Coiffe", "level": 40},
                           {"name": "Cape", "level": 42}]},
                lambda *_args: None, self,
            )
        elif choice == 2:
            dialog = LevelingDialog(
                "Alchimiste",
                {"source": "atlas-local", "kind": "harvest",
                 "entries": [{"level_range": "1-20",
                              "craft": {"name": "Ortie"}}]},
                lambda _name: None, lambda _craft: None, self,
            )
        elif choice == 3:
            dialog = RouteDialog(
                "Métier de démonstration",
                {"name": "Ressource sans capture"}, self,
            )
        else:
            raise ValueError(f"Unknown Craft dialog preview index: {choice}")

        self._present_preview_dialog(
            dialog,
            opened=f"Fenêtre Craft réelle : {self.preview_craft_dialog_choice.currentText()}",
            closed="Fenêtre Craft refermée",
        )

    def _open_image_zoom_preview(self) -> None:
        icon = unity_original_preview_icon("guide")
        if icon.isNull():
            icon = atlas_guide_symbol_icon(self.preview_image_zoom, "guide")
        source = icon.pixmap(160, 160)
        dialog = AtlasImagePopup(source, self.preview_image_zoom, title="Zoom image · aperçu Dev UI")
        if present_transient_dialog(
            self, "_preview_dialog", dialog,
            on_finished=lambda _result: self._report("Zoom image refermé"),
        ):
            self._report("Zoom image partagé Quêtes / Guides")

    def _open_preview_dialog(self) -> None:
        self._open_preview_dialog_variant("info")

    def _open_preview_dialog_variant(self, mode: str) -> None:
        titles = dict(_DIALOG_PREVIEW_VARIANTS)
        if mode not in titles:
            raise ValueError(mode)
        dialog = AtlasDialog(self)
        dialog.setWindowTitle("Prévisualisation du dialogue Unity")
        dialog.add_header(
            f"Dialogue commun · {titles[mode]}",
            "Même palette, même police, mêmes contrôles.",
            icon=atlas_application_icon(),
        )
        if mode in {"info", "warning", "danger"}:
            dialog.content_layout.addWidget(
                AtlasStatusBadge(titles[mode], state=mode)
            )
        message = QLabel(
            "Ce dialogue n'enregistre aucune modification."
            if mode != "confirmation" else
            "Confirmer cette action de démonstration ?"
        )
        message.setWordWrap(True)
        dialog.content_layout.addWidget(message)
        if mode == "form":
            fields = QHBoxLayout()
            option = QCheckBox("Option de préparation")
            option.setObjectName("DevUiDialogOption")
            fields.addWidget(option, 1)
            count = configure_unity_number_spinbox(
                QSpinBox(), minimum=0, maximum=9999, value=3, object_name="DevUiDialogQuantity",
            )
            fields.addWidget(count)
            dialog.content_layout.addLayout(fields)
        footer_actions: list[AtlasButton] = []
        if mode in {"confirmation", "form"}:
            cancel = AtlasButton("Annuler", variant="secondary")
            cancel.clicked.connect(dialog.reject)
            footer_actions.append(cancel)
            confirm = AtlasButton("Valider", variant="primary")
            confirm.clicked.connect(dialog.accept)
            footer_actions.append(confirm)
        else:
            close_button = AtlasButton("Fermer", variant="primary")
            close_button.clicked.connect(dialog.accept)
            footer_actions.append(close_button)
        dialog.add_action_row(*footer_actions)
        self._present_preview_dialog(
            dialog, opened="Dialogue ouvert", closed="Dialogue refermé",
        )
