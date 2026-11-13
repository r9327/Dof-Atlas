"""Interactive developer-only visual inventory of the real shared Unity widgets.

No local stylesheet and no parallel component implementations: this page
always inherits the active application theme and shows real Qt interactions.
It is constructed lazily only after the user explicitly opens it in Settings.
"""
from __future__ import annotations

import re
from collections.abc import Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
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
    QSlider,
    QSpinBox,
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

from app.ui.components import (
    AtlasButton,
    AtlasDialog,
    AtlasDialogHeader,
    AtlasPageTitle,
    AtlasPanelToggle,
    atlas_application_icon,
)
from app.ui.theme import PALETTE, SIZES, SPACING, TYPOGRAPHY
from app.ui.unity_palette import (
    UNITY_ICON_NAMES, UNITY_MAIN_ROLES, UNITY_SIZES_PX, UNITY_UI_USAGE,
)
from app.ui.unity_skin import apply_unity_panel_shadow, unity_ui_icon


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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(10)
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
        navigator.addWidget(QLabel("Aller à une famille"))
        self.gallery_navigation = QComboBox()
        self.gallery_navigation.setAccessibleName("Accès direct aux familles UI")
        navigator.addWidget(self.gallery_navigation, 1)
        self.gallery_count = QLabel()
        self.gallery_count.setObjectName("MutedLabel")
        navigator.addWidget(self.gallery_count)
        outer.addLayout(navigator)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.gallery_scroll = scroll
        body = QWidget()
        body.setProperty("atlasUnityPage", True)
        content = QVBoxLayout(body)
        content.setContentsMargins(7, 7, 7, 16)
        content.setSpacing(10)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._build_buttons(content)
        self._build_tabs_and_menus(content)
        self._build_data_views(content)
        self._build_scroll_and_resize(content)
        self._build_fields(content)
        self._build_advanced_fields(content)
        self._build_states_and_badges(content)
        self._build_surfaces_and_typography(content)
        self._build_sizes(content)
        self._build_panels(content)
        self._build_startup_preview(content)
        self._build_guide_samples(content)
        self._build_ui_assets(content)
        self._build_scope_matrix(content)
        self._build_dialogs_and_colors(content)
        content.addStretch(1)

        self.gallery_navigation.addItems(
            [section.title() for section in self.gallery_sections]
        )
        self.gallery_count.setText(f"{len(self.gallery_sections)} familles UI")
        self.gallery_navigation.currentIndexChanged.connect(self._jump_to_section)

    def _section(self, parent_layout: QVBoxLayout, title: str) -> QVBoxLayout:
        group = QGroupBox(title)
        # Real shared Unity relief on two static catalog panels. Avoid the
        # 16-fold scrolling cost of applying shadows to every section.
        if title.startswith(("Formulaires avancés", "Surfaces · cartes")):
            apply_unity_panel_shadow(group, blur=18, vertical=5, alpha=145)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 22, 14, 12)
        layout.setSpacing(9)
        parent_layout.addWidget(group)
        self.gallery_sections.append(group)
        return layout

    def _jump_to_section(self, index: int) -> None:
        """Scroll to the real section; no duplicate or floating UI catalog."""
        if 0 <= index < len(self.gallery_sections):
            self.gallery_scroll.ensureWidgetVisible(
                self.gallery_sections[index], 0, 12
            )

    def _report(self, action: str) -> None:
        self._click_count += 1
        self.feedback.setText(f"Interaction {self._click_count} : {action}")

    def _build_buttons(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "Boutons · variantes et états")
        row = QHBoxLayout()
        self.preview_buttons: dict[str, AtlasButton] = {}
        for name, caption in (
            ("primary", "Principal"),
            ("secondary", "Secondaire"),
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

    def _select_nav(self, active: int) -> None:
        for index, button in enumerate(self.preview_nav):
            button.set_variant(
                "navigation_active" if index == active else "navigation"
            )
        self._report(f"Onglet {active + 1} sélectionné")

    def _build_tabs_and_menus(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "Onglets · menus et navigation")
        self.preview_tabs = QTabWidget()
        for title in ("Quêtes", "Succès", "Guides"):
            tab = QWidget()
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
        self.menu_button.setMenu(menu)
        menu_row.addWidget(self.menu_button)
        menu_row.addStretch(1)
        section.addLayout(menu_row)

    def _build_data_views(self, parent: QVBoxLayout) -> None:
        """Exercise the actual shared tree/table family and their Qt signals."""
        section = self._section(parent, "Listes · arborescences · tableaux")
        row = QHBoxLayout()

        self.preview_tree = QTreeWidget()
        self.preview_tree.setHeaderLabels(("Famille UI", "État"))
        self.preview_tree.setMaximumHeight(154)
        self.preview_tree.setAlternatingRowColors(True)
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
        self.preview_table.setMaximumHeight(154)
        self.preview_table.setAlternatingRowColors(True)
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

    def _build_fields(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "Saisie · sélection · progression")
        row = QHBoxLayout()
        self.preview_input = QLineEdit()
        self.preview_input.setPlaceholderText("Champ texte Unity")
        self.preview_input.setToolTip("Focus, bordure et curseur hérités du thème")
        self.preview_input.textChanged.connect(
            lambda text: self._report(f"Saisie : {text}")
        )
        row.addWidget(self.preview_input, 2)
        self.preview_combo = QComboBox()
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
        self.preview_slider.setRange(0, 100)
        self.preview_slider.setValue(40)
        self.preview_slider.valueChanged.connect(self.preview_progress.setValue)
        section.addWidget(self.preview_progress)
        section.addWidget(self.preview_slider)

    def _build_advanced_fields(self, parent: QVBoxLayout) -> None:
        """Show native Qt controls which inherit the same application QSS."""
        section = self._section(parent, "Formulaires avancés · états et formats")

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

    def _build_states_and_badges(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "États · badges · retours visuels")

        badges = QHBoxLayout()
        self.preview_badges: dict[str, QLabel] = {}
        for state, caption in (
            ("done", "Terminé"),
            ("active", "En cours"),
            ("blocked", "Indisponible"),
        ):
            badge = QLabel(caption)
            badge.setObjectName("StatusBadge")
            badge.setProperty("state", state)
            badge.setAlignment(Qt.AlignCenter)
            badge.setAccessibleName(f"Statut {caption}")
            self.preview_badges[state] = badge
            badges.addWidget(badge)
        badges.addStretch(1)
        section.addLayout(badges)

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

    def _build_surfaces_and_typography(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "Surfaces · cartes · typographie")

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
            apply_unity_panel_shadow(card, blur=17, vertical=5, alpha=135)
            self.preview_cards[role] = card
            cards.addWidget(card, 1)
        section.addLayout(cards)

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
        section = self._section(parent, "Défilement · listes · redimensionnement")
        hint = QLabel(
            "Déplace la séparation, sélectionne une ligne et fais défiler la liste."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        section.addWidget(hint)

        self.preview_splitter = QSplitter(Qt.Horizontal)
        self.preview_splitter.setChildrenCollapsible(False)
        self.preview_scroll_list = QListWidget()
        for item in (
            "Accueil", "Personnage", "Encyclopédie", "Outils",
            "Stuffs", "Organizer", "Almanax", "Launcher",
        ):
            self.preview_scroll_list.addItem(item)
        self.preview_scroll_list.setMinimumWidth(130)
        self.preview_scroll_list.setMaximumHeight(134)
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
        """Inspect the shared size scale without changing existing UI geometry."""
        section = self._section(parent, "Tailles · typographie · espacements")
        sizing_hint = QLabel(
            "Trois hauteurs de contrôles et quatre tailles d'icônes, "
            "pilotées par les mêmes métriques que le code commun."
        )
        sizing_hint.setObjectName("MutedLabel")
        sizing_hint.setWordWrap(True)
        section.addWidget(sizing_hint)
        self.preview_metric_buttons: dict[str, AtlasButton] = {}
        row = QHBoxLayout()
        for label, role in (
            ("Compact", "control_compact"),
            ("Normal", "control_normal"),
            ("Large", "control_large"),
        ):
            button = AtlasButton(
                f"{label} · {UNITY_SIZES_PX[role]} px", variant="secondary"
            )
            button.setFixedHeight(UNITY_SIZES_PX[role])
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
            icon.setPixmap(unity_ui_icon("guide", size).pixmap(size, size))
            icon.setToolTip(f"{role} : {size} px")
            icons.addWidget(icon)
            text = QLabel(f"{size} px")
            text.setObjectName("MutedLabel")
            icons.addWidget(text)
            self.preview_metric_icons[role] = icon
        icons.addStretch(1)
        section.addLayout(icons)

        self.preview_metrics = QTableWidget(
            len(SIZES) + len(SPACING) + len(TYPOGRAPHY), 2
        )
        self.preview_metrics.setHorizontalHeaderLabels(("Token commun", "Valeur"))
        self.preview_metrics.setMaximumHeight(178)
        self.preview_metrics.setAlternatingRowColors(True)
        self.preview_metrics.setShowGrid(False)
        self.preview_metrics.verticalHeader().hide()
        self.preview_metrics.horizontalHeader().setStretchLastSection(False)
        self.preview_metrics.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.preview_metrics.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for index, (name, value) in enumerate((
            *SIZES.items(), *SPACING.items(), *TYPOGRAPHY.items(),
        )):
            self.preview_metrics.setItem(index, 0, QTableWidgetItem(name))
            self.preview_metrics.setItem(index, 1, QTableWidgetItem(value))
        section.addWidget(self.preview_metrics)

    def _build_panels(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "Panneaux · transparence · réduction")
        control_row = QHBoxLayout()
        self.panel_toggle = AtlasPanelToggle()
        self.panel_toggle.clicked.connect(self._toggle_panel)
        control_row.addWidget(self.panel_toggle)
        control_row.addWidget(QLabel("Masquer / réafficher la carte"))
        control_row.addStretch(1)
        section.addLayout(control_row)

        self.preview_panel = QFrame()
        self.preview_panel.setObjectName("card")
        panel_layout = QVBoxLayout(self.preview_panel)
        panel_layout.addWidget(QLabel("Carte commune Unity · bordure et fond partagés"))
        section.addWidget(self.preview_panel)

    def _toggle_panel(self) -> None:
        collapsed = not bool(self.panel_toggle.property("collapsed"))
        self.panel_toggle.set_collapsed(collapsed)
        self.preview_panel.setHidden(collapsed)
        self._report("Panneau masqué" if collapsed else "Panneau affiché")

    def _build_startup_preview(self, parent: QVBoxLayout) -> None:
        """Show startup's actual global QSS selectors without running preload."""
        section = self._section(parent, "Préchargement · même thème Unity")
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
        section = self._section(parent, "Guides · panneaux Unity partagés")
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

        # Use the real Guide Ultime parent selector and the same native
        # QComboBox as Successes. Never apply a per-widget QSS override.
        self.guide_ultime_sample = QFrame()
        self.guide_ultime_sample.setObjectName("GuideUltimeGeneratedView")
        guide_layout = QHBoxLayout(self.guide_ultime_sample)
        guide_layout.addWidget(QLabel("Menu Guide Ultime · style Succès"), 1)
        self.guide_ultime_combo = QComboBox()
        self.guide_ultime_combo.addItems(("Normal", "Rapide", "Instantané"))
        self.guide_ultime_combo.currentTextChanged.connect(
            lambda value: self._report(f"Guide Ultime : {value}")
        )
        guide_layout.addWidget(self.guide_ultime_combo, 1)
        section.addWidget(self.guide_ultime_sample)

    def _build_ui_assets(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "Icônes · raccourcis · tooltips")

        source_hint = QLabel(
            "Sprites Unity transparents si disponibles · sinon icônes Atlas monochromes"
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
        }
        for index, name in enumerate(UNITY_ICON_NAMES):
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
            symbol.setPixmap(unity_ui_icon(name, size).pixmap(size, size))
            symbol.setToolTip(
                f"{icon_captions[name]} · Unity local si transparent, repli Atlas sinon"
            )
            caption = QLabel(icon_captions[name])
            caption.setObjectName("MutedLabel")
            cell_layout.addWidget(symbol)
            cell_layout.addWidget(caption, 1)
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
        section = self._section(parent, "Couverture · modules consommateurs")
        note = QLabel(
            "Périmètre de propagation à contrôler : la présence ici ne signifie "
            "pas que le module est déjà intégralement globalisé."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        section.addWidget(note)

        modules = (
            "Accueil", "Personnage", "Quêtes", "Succès",
            "Guides", "Bestiaire", "Outils", "Stuffs",
            "Organizer", "Almanax", "Réseau", "Launcher",
        )
        self.preview_scope = QTableWidget(len(modules), 2)
        self.preview_scope.setHorizontalHeaderLabels(("Module", "Source de style cible"))
        self.preview_scope.setMaximumHeight(192)
        self.preview_scope.setAlternatingRowColors(True)
        self.preview_scope.setShowGrid(False)
        self.preview_scope.verticalHeader().hide()
        self.preview_scope.horizontalHeader().setStretchLastSection(False)
        self.preview_scope.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.preview_scope.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for index, module in enumerate(modules):
            self.preview_scope.setItem(index, 0, QTableWidgetItem(module))
            source = "Palette Unity / Tk" if module == "Launcher" else "Thème Qt commun"
            self.preview_scope.setItem(index, 1, QTableWidgetItem(source))
        self.preview_scope.setToolTip(
            "Inventaire du périmètre, pas une certification de migration"
        )
        section.addWidget(self.preview_scope)

    def _build_dialogs_and_colors(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "Dialogues · icônes · typographie")
        section.addWidget(AtlasPageTitle("Titre Atlas partagé"))
        muted = QLabel("Texte secondaire · même typographie sur chaque écran")
        muted.setObjectName("MutedLabel")
        section.addWidget(muted)
        row = QHBoxLayout()
        self.dialog_button = AtlasButton("Ouvrir une popup", variant="primary")
        self.dialog_button.clicked.connect(self._open_preview_dialog)
        row.addWidget(self.dialog_button)
        for name in ("guide", "quest", "success", "character"):
            icon_label = QLabel()
            icon_label.setPixmap(unity_ui_icon(name).pixmap(24, 24))
            icon_label.setToolTip(name)
            row.addWidget(icon_label)
        row.addStretch(1)
        section.addLayout(row)

        colors = self._section(parent, "Palette Unity · source de vérité")
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
        dialog = AtlasDialog(self)
        dialog.setWindowTitle("Prévisualisation du dialogue Unity")
        dialog.content_layout.addWidget(
            AtlasDialogHeader(
                "Dialogue commun",
                "Même palette, même police, mêmes contrôles.",
                icon=atlas_application_icon(),
            )
        )
        message = QLabel("Ce dialogue n'enregistre aucune modification.")
        message.setWordWrap(True)
        dialog.content_layout.addWidget(message)
        close_button = AtlasButton("Fermer", variant="primary")
        close_button.clicked.connect(dialog.accept)
        dialog.content_layout.addWidget(close_button)
        dialog.finished.connect(
            lambda _result: self._report("Dialogue refermé")
        )
        self._preview_dialog = dialog
        dialog.open()
        self._report("Dialogue ouvert")
