"""Interactive developer-only visual inventory of the real shared Unity widgets.

No local stylesheet and no parallel component implementations: this page
always inherits the active application theme and shows real Qt interactions.
It is constructed lazily only after the user explicitly opens it in Settings.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
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
from app.ui.theme import PALETTE
from app.ui.unity_skin import sprite_icon_path


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
            "Vrais composants partagés : modifier le thème commun doit changer "
            "tous ces exemples, sans styles locaux ni données de jeu."
        )
        subtitle.setObjectName("MutedLabel")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)
        self.feedback = QLabel("Test des interactions : prêt")
        self.feedback.setObjectName("MutedLabel")
        self.feedback.setAccessibleName("Résultat des interactions du laboratoire UI")
        outer.addWidget(self.feedback)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setProperty("atlasUnityPage", True)
        content = QVBoxLayout(body)
        content.setContentsMargins(7, 7, 7, 16)
        content.setSpacing(12)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self._build_buttons(content)
        self._build_tabs_and_menus(content)
        self._build_fields(content)
        self._build_panels(content)
        self._build_dialogs_and_colors(content)
        content.addStretch(1)

    @staticmethod
    def _section(parent_layout: QVBoxLayout, title: str) -> QVBoxLayout:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 22, 14, 12)
        layout.setSpacing(9)
        parent_layout.addWidget(group)
        return layout

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
            AtlasButton("Onglet normal"),
            AtlasButton("Onglet actif"),
        )
        self.preview_nav[0].set_style_name("TopNavButton")
        self.preview_nav[1].set_style_name("TopNavButtonActive")
        for index, button in enumerate(self.preview_nav):
            button.clicked.connect(
                lambda _checked=False, selected=index: self._select_nav(selected)
            )
            nav_row.addWidget(button)
        nav_row.addStretch(1)
        section.addLayout(nav_row)

    def _select_nav(self, active: int) -> None:
        for index, button in enumerate(self.preview_nav):
            button.set_style_name(
                "TopNavButtonActive" if index == active else "TopNavButton"
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

    def _build_fields(self, parent: QVBoxLayout) -> None:
        section = self._section(parent, "Saisie · sélection · progression")
        row = QHBoxLayout()
        self.preview_input = QLineEdit()
        self.preview_input.setPlaceholderText("Champ texte Unity")
        self.preview_input.setToolTip("Focus, bordure et curseur hérités du thème")
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
        row.addWidget(self.preview_spin)
        section.addLayout(row)

        self.preview_text = QPlainTextEdit()
        self.preview_text.setPlaceholderText("Zone de texte multiligne")
        self.preview_text.setMaximumHeight(68)
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
            path = sprite_icon_path(name)
            if path is not None:
                from PySide6.QtGui import QIcon
                icon_label = QLabel()
                icon_label.setPixmap(QIcon(str(path)).pixmap(24, 24))
                row.addWidget(icon_label)
        row.addStretch(1)
        section.addLayout(row)

        colors = self._section(parent, "Palette Unity · source de vérité")
        grid = QGridLayout()
        for index, role in enumerate((
            "BG", "PANEL", "PANEL_2", "PANEL_ACTIVE", "BORDER",
            "BORDER_CARD", "TEXT", "TEXT_MUTED", "GREEN", "RED",
            "LIST_SURFACE", "NAV_SURFACE", "TOOLTIP_SURFACE",
        )):
            value = PALETTE[role]
            cell = QWidget()
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            swatch = QPixmap(32, 18)
            swatch.fill(QColor(value))
            chip = QLabel()
            chip.setPixmap(swatch)
            chip.setAccessibleName(f"Couleur {role}")
            cell_layout.addWidget(chip)
            cell_layout.addWidget(QLabel(f"{role}  {value}"), 1)
            grid.addWidget(cell, index // 2, index % 2)
        colors.addLayout(grid)

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
