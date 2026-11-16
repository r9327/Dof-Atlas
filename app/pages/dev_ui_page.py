"""Interactive developer-only visual inventory of the real shared Unity widgets.

No local stylesheet and no parallel component implementations: this page
always inherits the active application theme and shows real Qt interactions.
It is constructed lazily only after the user explicitly opens it in Settings.
"""
from __future__ import annotations

import re
from collections.abc import Callable

from PySide6.QtCore import QDate, QEasingCurve, QEvent, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
    QStyle,
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

from app.ui.components import (
    AtlasBreadcrumb,
    AtlasButton,
    AtlasComboBox,
    AtlasDialog,
    AtlasDialogHeader,
    AtlasPageTitle,
    AtlasPanelToggle,
    AtlasGuideDisclosure,
    atlas_guide_arrow_icon,
    atlas_guide_character_icon,
    AtlasGuideParticipantButton,
    AtlasGuideCover,
    AtlasStatusBadge,
    atlas_application_icon,
    apply_unity_calendar_weekdays,
)
from app.ui.theme import PALETTE, SIZES, SPACING, TYPOGRAPHY
from app.ui.unity_palette import (
    UNITY_CHIP_TONES, UNITY_ICON_NAMES, UNITY_ICON_PENDING,
    UNITY_PANEL_SHADOW,
    UNITY_INTERACTION_STATES, UNITY_MAIN_ROLES, UNITY_ORGANIZER_METRICS_PX,
    UNITY_SIZES_PX, UNITY_SPACING_PX, UNITY_UI_USAGE,
    UNITY_CONTROL_LIMITS, UNITY_CONTROL_SIZES_PX,
    UNITY_LAYOUT_SIZES_PX, UNITY_LAYOUT_BREAKPOINTS_PX,
    UNITY_WINDOW_PRESETS_PX, UNITY_LAYOUT_PROFILE_PX, unity_layout_metrics,
    UNITY_MODULE_GEOMETRY_PX, UNITY_MODULE_GEOMETRY_OWNERS,
    UNITY_UI_CONSUMERS, UNITY_UI_FAMILY_INDEX, UNITY_UI_UNIFICATION_CONTRACT,
)
from app.ui.unity_skin import (
    UnityBackdrop, apply_unity_panel_shadow, sprite_icon_path, unity_original_preview_icon,
)
from app.ui.ui_registry import (
    UI_CONSUMER_INDEX, UI_FAMILY_QSS_SELECTORS,
    UI_FAMILY_PAINTED_ROLES, validate_ui_index,
)


class DevUiPage(QWidget):
    """One interactive visual checkpoint for all currently shared UI families."""

    def __init__(
        self,
        *,
        on_back: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DevUiPage")
        self.setProperty("atlasUnityPage", True)
        self._preview_dialog: AtlasDialog | None = None
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

        subtitle = QLabel(
            "Composants Unity existants et contrôles candidats à mutualiser. "
            "Cette galerie permet la comparaison visuelle ; l'adoption dans "
            "chaque module se vérifie séparément."
        )
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        self.feedback = QLabel("Test des interactions : prêt")
        self.feedback.setObjectName("MutedLabel")
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
        # This is a navigation chooser, not a full-width form field.
        # The common combo itself caps popup rows for keyboard/scroll access.
        self.gallery_navigation.setMinimumWidth(
            UNITY_CONTROL_SIZES_PX["gallery_selector_min_width"]
        )
        self.gallery_navigation.setMaximumWidth(
            UNITY_CONTROL_SIZES_PX["gallery_selector_max_width"]
        )
        navigator.addWidget(self.gallery_navigation)
        self.gallery_count = QLabel()
        self.gallery_count.setObjectName("MutedLabel")
        navigator.addWidget(self.gallery_count)
        navigator.addStretch(1)
        outer.addLayout(navigator)

        scroll = QScrollArea(self)
        scroll.setObjectName("DevUiGalleryScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
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
        validate_ui_index()
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
            text = QLabel(f"Contenu de démonstration : {title}")
            text.setObjectName("MutedLabel")
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
        for text in ("Première action", "Deuxième action", "Troisième action"):
            action = menu.addAction(text)
            action.triggered.connect(
                lambda _checked=False, label=text: self._report(
                    f"Menu : {label}"
                )
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
        self.preview_page_prev = AtlasButton("‹ Précédent", variant="secondary")
        self.preview_page_prev.setEnabled(False)
        self.preview_page_next = AtlasButton("Suivant ›", variant="secondary")
        self.preview_page_label = QLabel("Page 1 / 3")
        self.preview_page_label.setObjectName("MutedLabel")
        self.preview_page_prev.clicked.connect(lambda: self._change_preview_page(-1))
        self.preview_page_next.clicked.connect(lambda: self._change_preview_page(1))
        pagination.addWidget(self.preview_page_prev)
        pagination.addWidget(self.preview_page_label)
        pagination.addWidget(self.preview_page_next)
        back = AtlasButton("Retour", variant="secondary")
        back.clicked.connect(lambda: self._report("Navigation : retour"))
        pagination.addWidget(back)
        pagination.addStretch(1)
        section.addLayout(pagination)

    def _change_preview_page(self, step: int) -> None:
        self.preview_page_index = max(1, min(3, self.preview_page_index + step))
        self.preview_page_label.setText(f"Page {self.preview_page_index} / 3")
        self.preview_page_prev.setEnabled(self.preview_page_index > 1)
        self.preview_page_next.setEnabled(self.preview_page_index < 3)
        self._report(f"Navigation : page {self.preview_page_index}")

    def _build_headers(self, parent: QVBoxLayout) -> None:
        """Show real shared Guide header parts without a second UI skin or runtime."""
        # Import only when the developer-only page is explicitly opened.
        from app.modules.encyclopedia.views.shared_manual_guide_view import (
            _ParticipantPortraitButton, _guide_symbol_icon,
        )
        from app.modules.encyclopedia.views.guide_ultime_manual_view import (
            GuideManualProgressBar,
        )

        section = self._section(parent, "headers")
        note = QLabel(
            "En-têtes de référence · composants et thème Unity existants. "
            "Progression et personnages fictifs : aucune donnée Ganymède chargée."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
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

        self.preview_module_header = QFrame()
        self.preview_module_header.setObjectName("GuideHeader")
        module_row = QHBoxLayout(self.preview_module_header)
        module_row.setContentsMargins(12, 9, 12, 9)
        module_titles = QVBoxLayout()
        module_title = QLabel("Guides Dofus")
        module_title.setObjectName("GuideHeaderTitle")
        module_titles.addWidget(module_title)
        module_meta = QLabel("En-tête de module · sous-titre Unity")
        module_meta.setObjectName("GuideHeaderMeta")
        module_titles.addWidget(module_meta)
        module_row.addLayout(module_titles, 1)
        module_action = AtlasButton("Parcourir", variant="secondary")
        module_action.clicked.connect(
            lambda: self._report("En-tête module · parcourir")
        )
        module_row.addWidget(module_action)
        apply_unity_panel_shadow(self.preview_module_header, **UNITY_PANEL_SHADOW)
        section.addWidget(self.preview_module_header)

        self.preview_compact_header = QFrame()
        self.preview_compact_header.setObjectName("GuideCompactHeader")
        outer = QHBoxLayout(self.preview_compact_header)
        outer.setContentsMargins(10, 6, 10, 7)
        outer.setSpacing(10)

        right = QVBoxLayout()
        right.setSpacing(6)
        outer.addLayout(right, 1)
        heading = QHBoxLayout()
        heading.setSpacing(6)
        self.preview_header_guide_icon = AtlasGuideCover()
        self.preview_header_guide_icon.set_artwork(category="guide")
        heading.addWidget(self.preview_header_guide_icon)

        title = QLabel("Guide · aperçu fictif")
        title.setObjectName("GuideCompactTitle")
        title.setMinimumWidth(0)
        title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        heading.addWidget(title, 1)
        self.preview_header_overlay = QToolButton()
        self.preview_header_overlay.setObjectName("GuideCompactOverlayButton")
        self.preview_header_overlay.setIcon(
            _guide_symbol_icon(self.preview_header_overlay, "map")
        )
        self.preview_header_overlay.setToolTip("Overlay indisponible dans ce runtime")
        self.preview_header_overlay.setAccessibleName("Overlay")
        self.preview_header_overlay.setEnabled(False)
        heading.addWidget(self.preview_header_overlay)

        self.preview_header_settings = QToolButton()
        self.preview_header_settings.setObjectName("GuideCompactSettingsButton")
        self.preview_header_settings.setIcon(
            _guide_symbol_icon(self.preview_header_settings, "settings")
        )
        self.preview_header_settings.setToolTip("Paramètres du Guide")
        self.preview_header_settings.setAccessibleName("Paramètres du Guide")
        self.preview_header_settings.setCheckable(True)
        heading.addWidget(self.preview_header_settings)
        right.addLayout(heading)
        self.preview_header_title_row = heading
        self.preview_header_content_layout = right
        overall_caption = QHBoxLayout()
        overall_title = QLabel("Progression globale")
        overall_title.setObjectName("GuideGlobalProgressTitle")
        overall_caption.addWidget(overall_title)
        overall_caption.addStretch(1)
        overall_value = QLabel("35 %")
        overall_value.setObjectName("GuideCompactMetricValue")
        overall_caption.addWidget(overall_value)
        right.addLayout(overall_caption)
        self.preview_header_global_progress = QProgressBar()
        self.preview_header_global_progress.setObjectName("GuideGlobalProgress")
        self.preview_header_global_progress.setRange(0, 100)
        self.preview_header_global_progress.setValue(35)
        self.preview_header_global_progress.setTextVisible(False)
        self.preview_header_global_progress.setFixedHeight(
            UNITY_CONTROL_SIZES_PX["progress_primary"]
        )
        self.preview_header_global_progress.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        right.addWidget(self.preview_header_global_progress)

        self.preview_header_metrics: dict[str, QProgressBar] = {}
        self.preview_header_metric_icons: dict[str, QLabel] = {}
        self.preview_header_controls: dict[str, QToolButton] = {}
        metrics = QGridLayout()
        metrics.setContentsMargins(0, 0, 0, 0)
        metrics.setHorizontalSpacing(12)
        metrics.setVerticalSpacing(2)
        self.preview_header_metric_columns: dict[str, QVBoxLayout] = {}
        for name, role, amount, icon_symbol, color_role in (
            ("Route", "GuideManualProgress", 35, "target", "RED"),
            ("Préparation", "GuideCompactPreparationProgress", 60, "cube", "GREEN"),
        ):
            column = len(self.preview_header_metric_columns)
            caption = QHBoxLayout()
            caption.setSpacing(4)
            metric_icon = QLabel()
            metric_icon.setObjectName(
                f"GuideCompactMetricIcon{icon_symbol.title()}"
            )
            metric_icon.setPixmap(
                _guide_symbol_icon(
                    metric_icon, icon_symbol, size=16,
                    color=PALETTE[color_role],
                ).pixmap(16, 16)
            )
            metric_icon.setFixedSize(
                UNITY_SIZES_PX["icon_small"], UNITY_SIZES_PX["icon_small"]
            )
            caption.addWidget(metric_icon)
            self.preview_header_metric_icons[name] = metric_icon
            caption.addWidget(QLabel(name))
            caption.addStretch(1)
            value = QLabel(f"{amount} %")
            value.setObjectName("GuideCompactMetricValue")
            caption.addWidget(value)
            metrics.addLayout(caption, 0, column)
            bar = GuideManualProgressBar() if name == "Route" else QProgressBar()
            bar.setObjectName(role)
            bar.setRange(0, 100)
            bar.setValue(amount)
            bar.setTextVisible(False)
            bar.setFixedHeight(UNITY_CONTROL_SIZES_PX["progress_secondary"])
            bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if name == "Route":
                bar.setCursor(Qt.PointingHandCursor)
                bar.navigationRequested.connect(
                    lambda fraction: self._report(
                        f"Guide · navigation route {round(fraction * 100)} % (aperçu)"
                    )
                )
            arrow = AtlasGuideDisclosure()
            arrow.setFixedSize(
                UNITY_CONTROL_SIZES_PX["progress_toggle_width"],
                UNITY_CONTROL_SIZES_PX["progress_toggle_height"],
            )
            arrow.setCursor(Qt.PointingHandCursor)
            target = "Sommaire" if name == "Route" else "Préparation"
            arrow.setToolTip(f"Ouvrir {target}")
            arrow.setAccessibleName(f"Afficher {target}")
            caption.insertWidget(2, arrow, 0, Qt.AlignVCenter)
            metrics.addWidget(bar, 1, column)
            drawer_column = QVBoxLayout()
            drawer_column.setContentsMargins(0, 0, 0, 0)
            metrics.addLayout(drawer_column, 2, column, Qt.AlignTop)
            metrics.setColumnStretch(column, 1)
            self.preview_header_metric_columns[target] = drawer_column
            self.preview_header_controls[target] = arrow
            self.preview_header_metrics[name] = bar
        right.addLayout(metrics)

        # The progress arrows own both dropdowns; no duplicate text buttons.
        character_toggle = AtlasGuideParticipantButton()
        character_toggle.setObjectName("GuideParticipantsButton")
        character_icon = atlas_guide_character_icon(UNITY_CONTROL_SIZES_PX["guide_character_icon"])
        if character_icon.isNull():
            character_icon = _guide_symbol_icon(character_toggle, "people")
        character_toggle.setIcon(character_icon)
        character_toggle.setIconSize(QSize(
            UNITY_CONTROL_SIZES_PX["guide_character_icon"],
            UNITY_CONTROL_SIZES_PX["guide_character_icon"],
        ))
        character_toggle.setToolButtonStyle(Qt.ToolButtonIconOnly)
        character_toggle.setFixedSize(
            UNITY_CONTROL_SIZES_PX["guide_character_button"],
            UNITY_CONTROL_SIZES_PX["guide_character_button"],
        )
        character_toggle.setToolTip("Personnages")
        character_toggle.setAccessibleName("Personnages")
        character_toggle.setCheckable(True)
        self.preview_header_title_row.insertWidget(
            self.preview_header_title_row.count() - 1,
            character_toggle, 0, Qt.AlignVCenter,
        )
        self.preview_header_controls["Personnages"] = character_toggle

        self.preview_header_panels: dict[str, QFrame] = {}
        for label, role in (
            ("Préparation", "GuidePreparationPanel"),
            ("Sommaire", "GuideSummaryPanel"),
            ("Personnages", "GuideParticipantsPanel"),
        ):
            panel = QFrame()
            panel.setObjectName(role)
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(8, 5, 8, 5)
            panel_layout.setSpacing(4)
            if label == "Préparation":
                heading = QLabel("Préparer avant de partir · exemple fictif")
                heading.setObjectName("GuidePreparationSummary")
                panel_layout.addWidget(heading)
                self.preview_header_filter = AtlasComboBox()
                self.preview_header_filter.setObjectName("GuidePreparationCategoryFilter")
                self.preview_header_filter.addItems((
                    "Tout", "Prérequis", "Métiers", "Potions", "Pierres d'âme", "Clefs", "Objets",
                ))
                self.preview_header_filter.setAccessibleName("Catégorie de préparation")
                self.preview_header_filter.currentTextChanged.connect(
                    lambda value: self._report(f"Préparation · filtre {value} (aperçu)")
                )
                panel_layout.addWidget(self.preview_header_filter, 0, Qt.AlignLeft)
                self.preview_header_preparation_rows: list[tuple[QSpinBox, QCheckBox]] = []
                self.preview_header_preparation_names: list[AtlasButton] = []
                for name, quantity, done in (
                    ("Potion de rappel", 2, True),
                    ("Clef du donjon", 1, False),
                    ("Ressources à récupérer", 8, False),
                ):
                    row_frame = QFrame()
                    row_frame.setObjectName("GuidePreparationRow")
                    row = QHBoxLayout(row_frame)
                    row.setContentsMargins(8, 3, 8, 3)
                    name_button = AtlasButton(name, variant="secondary")
                    name_button.setObjectName("GuidePreparationItemCopy")
                    name_button.setFlat(True)
                    name_button.setCursor(Qt.PointingHandCursor)
                    name_button.setToolTip(f"Cliquer pour copier : {name}")
                    name_button.setAccessibleName(f"Copier {name}")
                    name_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                    name_button.clicked.connect(
                        lambda _checked=False, value=name:
                        QApplication.clipboard().setText(value)
                    )
                    amount = QSpinBox()
                    amount.setObjectName("GuidePreparationQuantity")
                    amount.setRange(0, quantity)
                    amount.setValue(quantity if done else 0)
                    amount.setSuffix(f" / {quantity}")
                    amount.setFixedWidth(UNITY_CONTROL_SIZES_PX["guide_quantity_width"])
                    amount.setToolTip("Quantité possédée · aperçu fictif")
                    validate = QCheckBox()
                    validate.setObjectName("GuidePreparationReady")
                    validate.setChecked(done)
                    validate.setToolTip("Marquer comme prêt · aperçu fictif")
                    validate.setAccessibleName(f"Valider {name}")
                    validate.toggled.connect(
                        lambda checked, spin=amount: spin.setValue(
                            spin.maximum() if checked else 0
                        )
                    )
                    validate.setFixedWidth(UNITY_CONTROL_SIZES_PX["guide_validation_width"])
                    row.addWidget(validate, 0, Qt.AlignVCenter)
                    row.addWidget(amount, 0, Qt.AlignVCenter)
                    row.addWidget(name_button, 1, Qt.AlignVCenter)
                    self.preview_header_preparation_rows.append((amount, validate))
                    self.preview_header_preparation_names.append(name_button)
                    panel_layout.addWidget(row_frame)
            elif label == "Sommaire":
                self.preview_header_summary_search = QLineEdit()
                self.preview_header_summary_search.setObjectName("GuideSummarySearch")
                self.preview_header_summary_search.setPlaceholderText(
                    "Rechercher une fiche…"
                )
                panel_layout.addWidget(self.preview_header_summary_search)
                summary = QListWidget()
                summary.setObjectName("GuideSummaryList")
                summary.addItems((
                    "1 · Introduction au village",
                    "2 · Préparer le départ",
                    "3 · Traverser la forêt",
                    "4 · Parler au PNJ du village",
                    "5 · Première quête",
                    "6 · Prochaine étape",
                ))
                summary.setCurrentRow(3)
                summary.setMaximumHeight(150)
                self.preview_header_summary_search.textChanged.connect(
                    lambda value, list_widget=summary: [
                        list_widget.item(i).setHidden(
                            value.casefold() not in
                            list_widget.item(i).text().casefold()
                        )
                        for i in range(list_widget.count())
                    ]
                )
                summary.itemClicked.connect(
                    lambda item: self._report(
                        f"Guide · sommaire : {item.text()} (aperçu)"
                    )
                )
                panel_layout.addWidget(summary)
            else:
                portraits_row = QHBoxLayout()
                portraits_row.setSpacing(5)
                self.preview_header_portraits: list[_ParticipantPortraitButton] = []
                # The same visible local Unity character artwork as the
                # original Dev UI sample (no empty/gray class placeholders).
                portrait_icon = sprite_icon_path("character")
                for index, percent in enumerate((35, 60, 10), start=1):
                    portrait = _ParticipantPortraitButton(
                        f"character:demo_{index}", progress=percent,
                    )
                    portrait.setToolTip(
                        f"Personnage fictif {index} · progression {percent} %"
                    )
                    portrait.setAccessibleName(f"Personnage fictif {index}")
                    portrait.setChecked(index == 1)
                    if portrait_icon:
                        portrait.setIcon(QIcon(str(portrait_icon)))
                    else:
                        portrait.setIcon(
                            _guide_symbol_icon(
                                portrait, "people", color=PALETTE["TEXT_SOFT"]
                            )
                        )
                    portrait.toggled.connect(
                        lambda checked, number=index: self._report(
                            f"Guide · personnage {number} {'choisi' if checked else 'retiré'} (aperçu)"
                        )
                    )
                    portraits_row.addWidget(portrait)
                    self.preview_header_portraits.append(portrait)
                portraits_row.addStretch(1)
                panel_layout.addLayout(portraits_row)
            panel.setVisible(False)
            if label == "Personnages":
                right.insertWidget(1, panel)
            else:
                self.preview_header_metric_columns[label].addWidget(panel)
            toggle = self.preview_header_controls[label]
            toggle.toggled.connect(panel.setVisible)
            toggle.clicked.connect(
                lambda checked, name=label: self._report(
                    f"Guide · {name} : {'ouvert' if checked else 'fermé'} (aperçu)"
                )
            )
            self.preview_header_panels[label] = panel
        # Capture each real state independently; start with every menu closed.

        self.preview_header_settings_panel = QFrame()
        self.preview_header_settings_panel.setObjectName("GuideCompactSettingsPanel")
        settings_row = QHBoxLayout(self.preview_header_settings_panel)
        settings_row.setContentsMargins(8, 5, 8, 5)
        self.preview_header_route_lock = QToolButton()
        self.preview_header_route_lock.setObjectName("GuideManualProgressLock")
        self.preview_header_route_lock.setCheckable(True)
        self.preview_header_route_lock.setText("Verrouiller la progression")
        self.preview_header_route_lock.toggled.connect(
            lambda checked: self._report(
                f"Guide · progression {'verrouillée' if checked else 'déverrouillée'} (aperçu)"
            )
        )
        settings_row.addWidget(self.preview_header_route_lock)
        settings_row.addStretch(1)
        self.preview_header_settings_panel.setVisible(False)
        self.preview_header_settings.toggled.connect(
            self.preview_header_settings_panel.setVisible
        )
        right.addWidget(self.preview_header_settings_panel)
        apply_unity_panel_shadow(self.preview_compact_header, **UNITY_PANEL_SHADOW)
        section.addWidget(self.preview_compact_header)

        self.preview_sheet_header = QFrame()
        self.preview_sheet_header.setObjectName("GuideSheetHeader")
        sheet_row = QHBoxLayout(self.preview_sheet_header)
        sheet_row.setContentsMargins(10, 7, 10, 7)
        sheet_row.setSpacing(7)
        sheet_back = AtlasButton("Retour", variant="guide_breadcrumb")
        sheet_back.setObjectName("GuideManualGuideButton")
        sheet_back.setIcon(
            _guide_symbol_icon(sheet_back, "back", size=16, color=PALETTE["TEXT_SOFT"])
        )
        sheet_back.setToolTip("Retour à la fiche ou au catalogue des guides")
        sheet_back.clicked.connect(
            lambda: self._report("En-tête fiche · retour")
        )
        sheet_row.addWidget(sheet_back)
        labels = QVBoxLayout()
        labels.setSpacing(1)
        meta = QLabel("ÉTAPE · VILLAGE")
        meta.setObjectName("GuideSheetMeta")
        labels.addWidget(meta)
        sheet_title = QLabel("Exemple · parler au PNJ du village")
        sheet_title.setObjectName("GuideSheetTitle")
        sheet_title.setWordWrap(True)
        labels.addWidget(sheet_title)
        sheet_row.addLayout(labels, 1)
        self.preview_header_page_jump = QSpinBox()
        self.preview_header_page_jump.setObjectName("GuideCompactPageJump")
        self.preview_header_page_jump.setRange(1, 20)
        self.preview_header_page_jump.setSuffix(" / 20")
        self.preview_header_page_jump.setValue(4)
        self.preview_header_page_jump.setMaximumWidth(110)
        self.preview_header_page_jump.setToolTip("Ouvrir directement la fiche sélectionnée")
        self.preview_header_page_jump.setAccessibleName("Sélectionner la fiche du guide")
        self.preview_header_page_jump.valueChanged.connect(
            lambda value: self._report(f"Guide · fiche {value} / 20")
        )
        sheet_row.addWidget(self.preview_header_page_jump, 0, Qt.AlignTop)
        apply_unity_panel_shadow(self.preview_sheet_header, **UNITY_PANEL_SHADOW)
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
        self.preview_burger = QToolButton()
        self.preview_burger.setObjectName("MenuButton")
        self.preview_burger.setText("Menu")
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
        note = QLabel(
            "Navigation Unity : actif, survol, replié et séparateur. "
            "Démonstration sans changement de page."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
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
        caption = QLabel("Parcours complet : survoler et cliquer chaque niveau.")
        caption.setObjectName("MutedLabel")
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
        intro = QLabel("Grille 2 × 2 : colonnes égales, marges et alignements communs.")
        intro.setObjectName("MutedLabel")
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
        row.addWidget(self.preview_combo, 1)
        self.preview_spin = QSpinBox()
        self.preview_spin.setRange(1, 8)
        self.preview_spin.setValue(4)
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

        self.preview_progress = QProgressBar()
        self.preview_progress.setRange(0, 100)
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
            heading = QLabel(caption)
            heading.setObjectName("MutedLabel")
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
        chip_hint = QLabel("Actions de statut cliquables · survol et sélection")
        chip_hint.setObjectName("MutedLabel")
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
        hint = QLabel("États indexés : " + " · ".join(UNITY_INTERACTION_STATES))
        hint.setObjectName("MutedLabel")
        section.addWidget(hint)

        state_row = QHBoxLayout()
        self.preview_toggle = QToolButton()
        self.preview_toggle.setObjectName("GuideSummaryButton")
        self.preview_toggle.setText("Commutateur")
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
        info = QLabel("Survol · pressé · focus · désactivé")
        info.setObjectName("MutedLabel")
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
        self.preview_busy = QProgressBar()
        self.preview_busy.setRange(0, 0)
        self.preview_busy.setAccessibleName("Progression indéterminée")
        progress_row.addWidget(self.preview_busy, 1)
        self.preview_complete = QProgressBar()
        self.preview_complete.setRange(0, 100)
        self.preview_complete.setValue(100)
        self.preview_complete.setAccessibleName("Progression terminée")
        progress_row.addWidget(self.preview_complete, 1)
        section.addLayout(progress_row)

    def _build_notifications(self, parent: QVBoxLayout) -> None:
        """Read-only notification preview; no pretend toast or duplicate QSS."""
        section = self._section(parent, "notifications")
        note = QLabel(
            "Exemples intégrés utilisant les badges et surfaces Unity existants. "
            "Le comportement des notifications flottantes reste à mutualiser."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
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
            body = QLabel(message)
            body.setObjectName("MutedLabel")
            body.setWordWrap(True)
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
            key = QLabel(caption)
            key.setObjectName("MutedLabel")
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
            small = QLabel("Couleurs, bordures et espacements communs")
            small.setObjectName("MutedLabel")
            small.setWordWrap(True)
            card_layout.addWidget(small)
            # Fixed visual samples only. No effect on scrolling rows,
            # focusable controls or the actual game panels.
            apply_unity_panel_shadow(card, **UNITY_PANEL_SHADOW)
            self.preview_cards[role] = card
            cards.addWidget(card, 1)
        section.addLayout(cards)

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
        hint = QLabel(
            "Les surfaces de démonstration gardent les styles QSS réels. "
            "Les dispositions et données spécifiques restent propres aux modules."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        section.addWidget(hint)

    def _build_scroll_and_resize(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "scroll_resize")
        hint = QLabel(
            "Déplace la séparation, sélectionne une ligne et fais défiler la liste."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
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
        detail = QLabel(
            "Redimensionnement du panneau · bordure Unity · "
            "barre de défilement partagée"
        )
        detail.setObjectName("MutedLabel")
        detail.setWordWrap(True)
        split_layout.addWidget(detail, 1)
        self.preview_splitter.addWidget(self.preview_scroll_panel)
        self.preview_splitter.setSizes((220, 460))
        section.addWidget(self.preview_splitter)

    def _build_sizes(self, parent: QVBoxLayout) -> None:
        """Show shared sizing rules and live layouts before module migration."""
        section = self._section(parent, "metrics")
        sizing_hint = QLabel(
            "Trois hauteurs de contrôles et quatre tailles d'icônes, "
            "pilotées par les mêmes métriques que le code commun."
        )
        sizing_hint.setObjectName("MutedLabel")
        sizing_hint.setWordWrap(True)
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
            text = QLabel(f"{size} px")
            text.setObjectName("MutedLabel")
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
        )
        self.preview_metrics = QTableWidget(len(metric_rows), 2)
        self.preview_metrics.setHorizontalHeaderLabels(("Token commun", "Valeur"))
        self.preview_metrics.setAlternatingRowColors(False)
        self.preview_metrics.setShowGrid(False)
        self.preview_metrics.verticalHeader().hide()
        self.preview_metrics.horizontalHeader().setStretchLastSection(False)
        self.preview_metrics.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.preview_metrics.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for index, (name, value) in enumerate(metric_rows):
            self.preview_metrics.setItem(index, 0, QTableWidgetItem(name))
            self.preview_metrics.setItem(index, 1, QTableWidgetItem(value))
        self.preview_metrics_toggle = self._add_catalog_table(
            section, self.preview_metrics, "les dimensions et espacements"
        )
        module_intro = QLabel(
            "Dimensions relevées dans les modules réels. Indexé ne veut pas "
            "dire raccordé : les pages doivent consommer ces valeurs pour "
            "hériter d'une modification future."
        )
        module_intro.setObjectName("MutedLabel")
        module_intro.setWordWrap(True)
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
        self.preview_module_geometry.setAlternatingRowColors(False)
        self.preview_module_geometry.setShowGrid(False)
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

        self.preview_window_description = QLabel()
        self.preview_window_description.setObjectName("MutedLabel")
        self.preview_window_description.setWordWrap(True)
        section.addWidget(self.preview_window_description)

        self.preview_responsive_mode = QLabel()
        self.preview_responsive_mode.setObjectName("MutedLabel")
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
            description = QLabel(summary)
            description.setObjectName("MutedLabel")
            description.setWordWrap(True)
            content.addWidget(description)
            if index == 0:
                progress = QProgressBar()
                progress.setObjectName("GuideGlobalProgress")
                progress.setRange(0, 100)
                progress.setValue(45)
                progress.setTextVisible(False)
                progress.setFixedHeight(UNITY_CONTROL_SIZES_PX["progress_primary"])
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
        glass_title = QLabel("Organizer · glass Unity et dégradé communs")
        glass_title.setObjectName("MutedLabel")
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
        self.preview_wallpaper_status = QLabel(
            "Fond actif : image étoilée Unity locale nettoyée."
            if self.preview_backdrop.has_wallpaper else
            "Fond actif : dégradé Unity de secours (image étoilée indisponible)."
        )
        self.preview_wallpaper_status.setObjectName("MutedLabel")
        section.addWidget(self.preview_wallpaper_status)
        note = QLabel(
            "Aucun faux motif étoilé : la démonstration utilise exactement "
            "le même UnityBackdrop que l'application."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        section.addWidget(note)
        self.preview_backdrop.setFixedHeight(5 * UNITY_SIZES_PX["control_normal"])
        wrapper = QVBoxLayout(self.preview_backdrop)
        wrapper.setContentsMargins(16, 14, 16, 14)
        card = QFrame()
        card.setObjectName("card")
        apply_unity_panel_shadow(card, **UNITY_PANEL_SHADOW)
        card_layout = QVBoxLayout(card)
        card_layout.addWidget(AtlasPageTitle("Carte sur fond Unity"))
        muted = QLabel("Dégradé, transparence et bordures hérités du thème")
        muted.setObjectName("MutedLabel")
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

        self.startup_progress = QProgressBar()
        self.startup_progress.setObjectName("PreloadPopupProgress")
        self.startup_progress.setRange(0, 3)
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

        self.guide_sample_compact_header = QFrame()
        self.guide_sample_compact_header.setObjectName("GuideCompactHeader")
        compact_layout = QVBoxLayout(self.guide_sample_compact_header)
        compact_layout.addWidget(QLabel("Guide compact · mêmes bordures"))
        apply_unity_panel_shadow(
            self.guide_sample_compact_header, **UNITY_PANEL_SHADOW
        )
        section.addWidget(self.guide_sample_compact_header)

        self.preview_quest_start_position = QLabel(
            "Position de lancement : [4,-18]"
        )
        self.preview_quest_start_position.setObjectName("QuestLaunchPosition")
        self.preview_quest_start_position.setAccessibleName(
            "Aperçu typographique d'une position de lancement"
        )
        section.addWidget(self.preview_quest_start_position)

        self.guide_sample_summary = QFrame()
        self.guide_sample_summary.setObjectName("GuidePreparationSummary")
        summary_layout = QVBoxLayout(self.guide_sample_summary)
        summary_layout.addWidget(QLabel("Préparation · fond et bordures Unity"))
        section.addWidget(self.guide_sample_summary)

        self.guide_sample_row = QFrame()
        self.guide_sample_row.setObjectName("GuidePreparationRow")
        row_layout = QHBoxLayout(self.guide_sample_row)
        row_layout.addWidget(QLabel("Ressource de démonstration"), 1)
        self.guide_copy_button = AtlasButton("Copier", variant="secondary")
        self.guide_copy_button.set_style_name("GuidePreparationItemCopy")
        self.guide_copy_button.clicked.connect(
            lambda: self._report("Guide · bouton Copier cliqué")
        )
        row_layout.addWidget(self.guide_copy_button)
        section.addWidget(self.guide_sample_row)

        self.guide_manual_nav = QFrame()
        self.guide_manual_nav.setObjectName("GuideManualNav")
        nav_layout = QHBoxLayout(self.guide_manual_nav)
        nav_layout.addWidget(QLabel("Navigation du guide · fond partagé"))
        section.addWidget(self.guide_manual_nav)

        # Preview the real guide reading surface, without a local stylesheet.
        self.guide_manual_scroll_sample = QScrollArea()
        self.guide_manual_scroll_sample.setObjectName("GuideManualScroll")
        self.guide_manual_scroll_sample.setWidgetResizable(True)
        self.guide_manual_scroll_sample.setFixedHeight(88)
        content = QWidget()
        content.setObjectName("GuideManualContent")
        content_row = QVBoxLayout(content)
        content_row.addWidget(QLabel("Zone du texte du guide · bordure complète"))
        self.guide_manual_scroll_sample.setWidget(content)
        section.addWidget(self.guide_manual_scroll_sample)

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
        guide_layout.addWidget(self.guide_ultime_combo, 1)
        section.addWidget(self.guide_ultime_sample)

    def _build_ui_assets(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "assets")

        all_icon_names = (*UNITY_ICON_NAMES, *UNITY_ICON_PENDING)
        local_icon_count = sum(
            sprite_icon_path(name) is not None for name in all_icon_names
        )
        source_hint = QLabel(
            f"Sources Unity communes : {local_icon_count}/{len(all_icon_names)} "
            "pictogrammes repérés dans ce lancement · couleurs originales conservées"
        )
        source_hint.setObjectName("MutedLabel")
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
            caption = QLabel(icon_captions[name])
            caption.setObjectName("MutedLabel")
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
        note = QLabel(
            "Exemples de réutilisation dans les modules. La couverture complète "
            "reste à vérifier écran par écran."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
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
            "Almanax": "Bouton et badge sur l’Accueil",
            "Launcher": "Couleurs et typographie Unity",
        }
        self.preview_scope = QTableWidget(len(modules), 3)
        self.preview_scope.setHorizontalHeaderLabels(
            ("Module", "Source de style cible", "Exemple partagé")
        )
        self.preview_scope.setAlternatingRowColors(False)
        self.preview_scope.setShowGrid(False)
        self.preview_scope.verticalHeader().hide()
        self.preview_scope.horizontalHeader().setStretchLastSection(False)
        self.preview_scope.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.preview_scope.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.preview_scope.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
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

        contract_label = QLabel(
            "Tous les éléments prévus en uniformisation (cliquer une ligne "
            "pour ouvrir son exemple dans UI Dev)"
        )
        contract_label.setObjectName("PanelTitle")
        section.addWidget(contract_label)
        self.preview_contract = QTableWidget(len(UNITY_UI_UNIFICATION_CONTRACT), 2)
        self.preview_contract.setHorizontalHeaderLabels(("Élément prévu", "Famille UI"))
        self.preview_contract.setAlternatingRowColors(False)
        self.preview_contract.setShowGrid(False)
        self.preview_contract.verticalHeader().hide()
        self.preview_contract.horizontalHeader().setStretchLastSection(False)
        self.preview_contract.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.preview_contract.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        family_keys = tuple(UNITY_UI_FAMILY_INDEX)
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
        note = QLabel(
            "Transitions de prévisualisation Qt. Les durées ne sont pas "
            "encore mesurées sur DOFUS Unity : comparer puis valider avant "
            "toute généralisation."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        section.addWidget(note)

        timing = QHBoxLayout()
        timing.addWidget(QLabel("Durée de référence"))
        self.motion_duration = QSpinBox()
        self.motion_duration.setObjectName("DevUiMotionDuration")
        self.motion_duration.setRange(80, 600)
        self.motion_duration.setSingleStep(20)
        self.motion_duration.setSuffix(" ms")
        self.motion_duration.setValue(180)
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

        self.motion_progress = QProgressBar()
        self.motion_progress.setObjectName("DevUiMotionProgress")
        self.motion_progress.setRange(0, 100)
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
        muted = QLabel("Texte secondaire · même typographie sur chaque écran")
        muted.setObjectName("MutedLabel")
        section.addWidget(muted)
        row = QHBoxLayout()
        self.dialog_button = AtlasButton("Ouvrir une popup", variant="primary")
        self.dialog_button.clicked.connect(self._open_preview_dialog)
        row.addWidget(self.dialog_button)
        self.preview_dialog_variants: dict[str, AtlasButton] = {}
        for state, caption in (
            ("info", "Information"),
            ("warning", "Attention"),
            ("danger", "Erreur"),
        ):
            variant_button = AtlasButton(
                caption, variant="danger" if state == "danger" else "secondary"
            )
            variant_button.clicked.connect(
                lambda _checked=False, mode=state:
                    self._open_preview_dialog_variant(mode)
            )
            self.preview_dialog_variants[state] = variant_button
            row.addWidget(variant_button)
        for name in ("guide", "quest", "success", "character"):
            icon_label = QLabel()
            icon_label.setPixmap(unity_original_preview_icon(name).pixmap(24, 24))
            icon_label.setToolTip(name)
            row.addWidget(icon_label)
        row.addStretch(1)
        section.addLayout(row)

        colors = self._section(parent, "palette")
        intro = QLabel(
            "Couleurs principales et emplacement dans l'UI darkStone : "
            "les mêmes rôles sont utilisés dans les modules. "
            "Les boutons partagés suivent strictement les couleurs Unity."
        )
        intro.setObjectName("MutedLabel")
        intro.setWordWrap(True)
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
        label = QLabel(role)
        label.setObjectName("MutedLabel")
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

    def _open_preview_dialog(self) -> None:
        self._open_preview_dialog_variant("info")

    def _open_preview_dialog_variant(self, mode: str) -> None:
        if mode not in {"info", "warning", "danger"}:
            raise ValueError(mode)
        dialog = AtlasDialog(self)
        dialog.setWindowTitle("Prévisualisation du dialogue Unity")
        titles = {
            "info": "Information", "warning": "Attention", "danger": "Erreur",
        }
        dialog.content_layout.addWidget(
            AtlasDialogHeader(
                f"Dialogue commun · {titles[mode]}",
                "Même palette, même police, mêmes contrôles.",
                icon=atlas_application_icon(),
            )
        )
        dialog.content_layout.addWidget(
            AtlasStatusBadge(titles[mode], state=mode)
        )
        message = QLabel("Ce dialogue n'enregistre aucune modification.")
        message.setWordWrap(True)
        dialog.content_layout.addWidget(message)
        close_button = AtlasButton("Fermer", variant="primary")
        close_button.clicked.connect(dialog.accept)
        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close_button)
        dialog.content_layout.addLayout(footer)
        dialog.finished.connect(
            lambda _result: self._report("Dialogue refermé")
        )
        self._preview_dialog = dialog
        dialog.open()
        self._report("Dialogue ouvert")
