from __future__ import annotations


from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QLabel,
    QListWidget,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.numbers import format_grouped_int
from app.pages._character_page_impl import (
    EQUIPMENT_SLOTS,
    CharacterPage as _CharacterPage,
)
from app.ui.components import AtlasComboBox
from app.ui.unity_palette import UNITY_CONTENT_TYPOGRAPHY_PX, UNITY_MODULE_GEOMETRY_PX, UNITY_SPACING_PX

CHARACTER_GEOMETRY = UNITY_MODULE_GEOMETRY_PX["character"]


_EQUIPMENT_SLOT_SIZE = CHARACTER_GEOMETRY["equipment_slot_box"]
_EQUIPMENT_ICON_SIZE = CHARACTER_GEOMETRY["equipment_icon"]


class CharacterPage(_CharacterPage):
    """Compact Atlas character surface: equipment/identity plus live stats."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        root = self.layout()
        columns = root.itemAt(2).layout() if root is not None and root.count() > 2 else None
        if root is not None:
            # The page shell already identifies the destination. Remove the old
            # page title/subtitle without replacing them by another heading.
            for index in (0, 1):
                item = root.itemAt(index)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.hide()
            root.setContentsMargins(*CHARACTER_GEOMETRY["page_margins"])
            root.setSpacing(UNITY_SPACING_PX["sm"])

        if columns is not None:
            # The old identity card must not consume a column anymore. Its
            # compatibility-only widgets stay alive, while the visible selector
            # and success score live in the centre of the equipment dressing.
            columns.removeWidget(self.identity_panel)
            self.identity_panel.hide()

            columns.removeWidget(self.stats_panel)
            columns.removeWidget(self.equipment_panel)
            columns.insertWidget(0, self.equipment_panel, 70)
            columns.insertWidget(1, self.stats_panel, 30)
            columns.setSpacing(UNITY_SPACING_PX["md"])
            columns.setStretch(0, 70)
            columns.setStretch(1, 30)

        equipment_layout = self.equipment_panel.layout()
        if equipment_layout is not None:
            equipment_layout.setContentsMargins(*CHARACTER_GEOMETRY["equipment_panel_margins"])
            equipment_layout.setSpacing(UNITY_SPACING_PX["xs"])

        stats_layout = self.stats_panel.layout()
        if stats_layout is not None:
            stats_layout.setContentsMargins(*CHARACTER_GEOMETRY["stats_panel_margins"])
            stats_layout.setSpacing(UNITY_SPACING_PX["sm"])

        # A 900px shell must fit both cards plus its 20px horizontal
        # margins and the 8px gutter. The equipment grid already needs
        # far less than its old 650px minimum; do not force window growth
        # just because the Personnage page was opened.
        self.equipment_panel.setMinimumWidth(CHARACTER_GEOMETRY["equipment_min_width"])
        self.stats_panel.setMinimumWidth(CHARACTER_GEOMETRY["stats_min_width"])
        self.stats_panel.setMaximumWidth(CHARACTER_GEOMETRY["stats_max_width"])

    @staticmethod
    def _apply_success_style(label: QLabel, *, compact: bool = False) -> None:
        """Apply score typography while leaving colors to the shared theme."""

        font = label.font()
        role = "character_score_compact" if compact else "character_score_regular"
        font.setPixelSize(UNITY_CONTENT_TYPOGRAPHY_PX[role])
        font.setBold(True)
        label.setFont(font)

    def _build_identity_panel(self, layout: QVBoxLayout) -> None:
        # Created here because the base class expects them during refresh. The
        # equipment builder reparents the two visible controls into its centre.
        self.achievement_points = QLabel("—")
        self.achievement_points.setObjectName("CharacterAchievementPoints")
        self.achievement_points.setAlignment(Qt.AlignCenter)
        self._apply_success_style(self.achievement_points, compact=True)
        layout.addWidget(self.achievement_points)

        self.character_selector = AtlasComboBox()
        self.character_selector.setObjectName("CharacterPageCharacterCombo")
        selector_icon = CHARACTER_GEOMETRY["selector_icon"]
        self.character_selector.setIconSize(QSize(selector_icon, selector_icon))
        # Let the shared Unity combo fit the longest character label, while
        # retaining this panel's design cap on narrow equipment layouts.
        self.character_selector.setMaximumWidth(CHARACTER_GEOMETRY["selector_max_width"])
        self.character_selector.setToolTip("Sélectionner un personnage")
        self.character_selector.currentIndexChanged.connect(
            self._on_character_selector_changed
        )
        layout.addWidget(self.character_selector)

        # Compatibility projection for existing callers/tests. The character
        # name no longer has a visible duplicate in the Equipment block.
        self.character_name = QLabel("Aucun personnage sélectionné")
        self.character_name.setObjectName("HomeCharacterName")
        self.character_name.hide()
        layout.addWidget(self.character_name)

        self.character_level = QLabel("")
        self.character_level.setObjectName("MutedLabel")
        self.character_level.hide()
        layout.addWidget(self.character_level)

        # Preserve ordering/deletion APIs without showing the obsolete left card.
        self.character_order_list = QListWidget(self)
        self.character_order_list.setObjectName("CharacterOrderList")
        self.character_order_list.setIconSize(QSize(30, 30))
        self.character_order_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.character_order_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.character_order_list.setDefaultDropAction(Qt.MoveAction)
        self.character_order_list.setDropIndicatorShown(True)
        self.character_order_list.itemDoubleClicked.connect(
            self._on_character_order_item_activated
        )
        self.character_order_list.currentRowChanged.connect(
            lambda _row: self._update_character_order_controls()
        )
        self.character_order_list.model().rowsMoved.connect(
            self._on_character_order_rows_moved
        )
        self.character_order_list.hide()

        self.character_move_up = QToolButton(self)
        self.character_move_up.setText("↑")
        self.character_move_up.clicked.connect(lambda: self._move_selected_character(-1))
        self.character_move_up.hide()

        self.character_move_down = QToolButton(self)
        self.character_move_down.setText("↓")
        self.character_move_down.clicked.connect(lambda: self._move_selected_character(1))
        self.character_move_down.hide()

        self.character_delete_button = QToolButton(self)
        self.character_delete_button.setText("Supprimer")
        self.character_delete_button.clicked.connect(self._delete_selected_character)
        self.character_delete_button.hide()

    def _build_stats_panel(self, layout: QVBoxLayout) -> None:
        self.stats_empty_label = QLabel("Statistiques en jeu\nen attente de détection")
        self.stats_empty_label.setObjectName("MutedLabel")
        self.stats_empty_label.setAlignment(Qt.AlignCenter)
        self.stats_empty_label.setWordWrap(True)
        layout.addWidget(self.stats_empty_label, 1)

        super()._build_stats_panel(layout)
        for value in self.stat_value_labels.values():
            value.setObjectName("CharacterStatValue")
        self.stats_scroll.hide()

    def _build_equipment_panel(self, layout: QVBoxLayout) -> None:
        equipment_widget = QWidget()
        equipment_widget.setObjectName("CharacterEquipmentGrid")
        equipment_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        grid = QGridLayout(equipment_widget)
        grid.setContentsMargins(2, 2, 2, 2)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        self.equipment_slots: dict[str, QToolButton] = {}
        for column in range(6):
            grid.setColumnMinimumWidth(column, _EQUIPMENT_SLOT_SIZE)
            grid.setColumnStretch(column, 0)
        for row in range(7):
            grid.setRowMinimumHeight(row, _EQUIPMENT_SLOT_SIZE)
            grid.setRowStretch(row, 0)
        for column in range(1, 5):
            grid.setColumnStretch(column, 1)

        skin_block = QWidget()
        skin_block.setObjectName("CharacterEquipmentCenter")
        skin_block.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        skin_layout = QVBoxLayout(skin_block)
        skin_layout.setContentsMargins(4, 0, 4, 0)
        skin_layout.setSpacing(4)

        # Success score and selector are now genuinely inside Equipment and sit
        # in the central lane between the two top equipment squares.
        identity_layout = self.identity_panel.layout()
        if identity_layout is not None:
            identity_layout.removeWidget(self.achievement_points)
            identity_layout.removeWidget(self.character_selector)
        skin_layout.addWidget(self.achievement_points, 0, Qt.AlignHCenter)
        skin_layout.addWidget(self.character_selector, 0, Qt.AlignHCenter)

        # Keep compatibility attributes without creating duplicate visible labels.
        self.skin_success_points = self.achievement_points
        self.skin_character_name = self.character_name

        self.portrait = QLabel("Skin du personnage\n(à venir)")
        self.portrait.setObjectName("HomeCharacterPortrait")
        self.portrait.setAlignment(Qt.AlignCenter)
        self.portrait.setWordWrap(True)
        self.portrait.setMinimumSize(*CHARACTER_GEOMETRY["portrait_min_size"])
        self.portrait.setMaximumSize(*CHARACTER_GEOMETRY["portrait_max_size"])
        self.portrait.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        skin_layout.addWidget(self.portrait, 1, Qt.AlignCenter)

        grid.addWidget(skin_block, 0, 1, 6, 4)

        for slot_key, slot_label, row, column in EQUIPMENT_SLOTS:
            button = QToolButton()
            button.setObjectName("SecondaryButton")
            button.setProperty("equipmentSlot", slot_key)
            button.setFixedSize(_EQUIPMENT_SLOT_SIZE, _EQUIPMENT_SLOT_SIZE)
            button.setIconSize(QSize(_EQUIPMENT_ICON_SIZE, _EQUIPMENT_ICON_SIZE))
            button.setEnabled(False)
            button.setToolTip(slot_label)
            button.setText("")
            grid.addWidget(button, row, column, Qt.AlignCenter)
            self.equipment_slots[slot_key] = button

        layout.addWidget(equipment_widget, 1)

    def _character_selector_text(self, character) -> str:
        return str(character.label or "Personnage")

    def _selector_icon_path(self, label: str) -> str:
        return self._icon_path(label)

    @staticmethod
    def _success_text(points) -> str:
        if points is None:
            return "—"
        try:
            return format_grouped_int(points)
        except (TypeError, ValueError, OverflowError):
            return str(points)

    def _achievement_text(self, points: int | None) -> str:
        return self._success_text(points)

    def _stat_text(self, value: int) -> str:
        return str(value)

    def _render_stats(self, snapshot) -> int:
        visible = super()._render_stats(snapshot)
        self.stats_empty_label.setVisible(visible == 0)
        self.stats_scroll.setVisible(visible > 0)
        return visible

    def _visual_path(self, label: str) -> str:
        # The equipment centre is reserved for the real character skin. A class
        # icon belongs in the selector and must not masquerade as the skin.
        return self._skin_path(label)

    def _portrait_placeholder(self) -> str:
        return "Skin du personnage\n(à venir)"


__all__ = ["CharacterPage"]
