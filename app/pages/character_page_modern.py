from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.pages.character_page import (
    CHARACTER_STAT_ROWS,
    EQUIPMENT_SLOTS,
    CharacterPage as _CharacterPage,
)


_SUCCESS_GOLD = "#E4B84A"
_EQUIPMENT_SLOT_SIZE = 64
_EQUIPMENT_ICON_SIZE = 54


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
            root.setContentsMargins(10, 8, 10, 10)
            root.setSpacing(6)

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
            columns.setSpacing(8)
            columns.setStretch(0, 70)
            columns.setStretch(1, 30)

        equipment_layout = self.equipment_panel.layout()
        if equipment_layout is not None:
            equipment_layout.setContentsMargins(8, 6, 8, 8)
            equipment_layout.setSpacing(4)

        stats_layout = self.stats_panel.layout()
        if stats_layout is not None:
            stats_layout.setContentsMargins(10, 8, 10, 10)
            stats_layout.setSpacing(6)

        self.equipment_panel.setMinimumWidth(650)
        self.stats_panel.setMinimumWidth(250)
        self.stats_panel.setMaximumWidth(340)

    @staticmethod
    def _apply_success_style(label: QLabel, *, compact: bool = False) -> None:
        size = 18 if compact else 23
        label.setStyleSheet(
            f"color: {_SUCCESS_GOLD}; font-size: {size}px; font-weight: 700;"
        )

    def _build_identity_panel(self, layout: QVBoxLayout) -> None:
        # Created here because the base class expects them during refresh. The
        # equipment builder reparents the two visible controls into its centre.
        self.achievement_points = QLabel("—")
        self.achievement_points.setObjectName("CharacterAchievementPoints")
        self.achievement_points.setAlignment(Qt.AlignCenter)
        self._apply_success_style(self.achievement_points, compact=True)
        layout.addWidget(self.achievement_points)

        self.character_selector = QComboBox()
        self.character_selector.setObjectName("CharacterPageCharacterCombo")
        self.character_selector.setIconSize(QSize(38, 38))
        self.character_selector.setMinimumWidth(260)
        self.character_selector.setMaximumWidth(360)
        self.character_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
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

        self.stats_scroll = QScrollArea()
        self.stats_scroll.setWidgetResizable(True)
        self.stats_scroll.setFrameShape(QFrame.NoFrame)
        self.stats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.stats_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(7)
        self.stat_rows: dict[str, QWidget] = {}
        self.stat_value_labels: dict[str, QLabel] = {}

        for stat_key, label_text in CHARACTER_STAT_ROWS:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            label = QLabel(label_text)
            label.setObjectName("MutedLabel")
            row_layout.addWidget(label, 1)

            value = QLabel("")
            value.setObjectName("CharacterStatValue")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(value)

            row.hide()
            content_layout.addWidget(row)
            self.stat_rows[stat_key] = row
            self.stat_value_labels[stat_key] = value

        content_layout.addStretch(1)
        self.stats_scroll.setWidget(content)
        self.stats_scroll.hide()
        layout.addWidget(self.stats_scroll, 1)

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
        self.portrait.setMinimumSize(230, 300)
        self.portrait.setMaximumSize(300, 360)
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

    def _rebuild_character_selector(self) -> None:
        self.character_selector.blockSignals(True)
        try:
            self.character_selector.clear()
            self.character_selector.setEnabled(bool(self.characters))
            for character in self.characters:
                icon_path = self._icon_path(character.label)
                icon = QIcon(icon_path) if icon_path else QIcon()
                self.character_selector.addItem(
                    icon,
                    self._character_selector_text(character),
                    character.key,
                )
            self._sync_character_selector_selection()
        finally:
            self.character_selector.blockSignals(False)

    def _refresh_character_selector_runtime_labels(self) -> None:
        by_key = {character.key: character for character in self.characters}
        self.character_selector.blockSignals(True)
        try:
            for index in range(self.character_selector.count()):
                key = str(self.character_selector.itemData(index) or "")
                character = by_key.get(key)
                if character is not None:
                    self.character_selector.setItemText(index, character.label)
        finally:
            self.character_selector.blockSignals(False)

    @staticmethod
    def _success_text(points) -> str:
        if points is None:
            return "—"
        try:
            return f"{int(points):,}".replace(",", " ")
        except (TypeError, ValueError, OverflowError):
            return str(points)

    def _render_identity(self, character) -> None:
        snapshot = self.runtime_state_store.snapshot(self.active_character_key)
        points = snapshot.achievement_points if snapshot is not None else None
        level = snapshot.level if snapshot is not None else None
        points_text = self._success_text(points)

        self.achievement_points.setText(points_text)
        self.character_level.setText(f"Niveau {level}" if level is not None else "")
        self._render_stats(snapshot)

        if character is None:
            self.character_name.setText("Aucun personnage sélectionné")
            self._set_portrait("")
            return

        self.character_name.setText(character.label)
        self._set_portrait(self._visual_path(character.label))

    def _render_stats(self, snapshot) -> None:
        values = dict(snapshot.stats) if snapshot is not None else {}
        visible = 0
        for stat_key, _label_text in CHARACTER_STAT_ROWS:
            row = self.stat_rows[stat_key]
            value_label = self.stat_value_labels[stat_key]
            if stat_key not in values:
                value_label.setText("")
                row.hide()
                continue
            value_label.setText(str(values[stat_key]))
            row.show()
            visible += 1

        self.stats_empty_label.setVisible(visible == 0)
        self.stats_scroll.setVisible(visible > 0)

    def _visual_path(self, label: str) -> str:
        # The equipment centre is reserved for the real character skin. A class
        # icon belongs in the selector and must not masquerade as the skin.
        return self._skin_path(label)

    def _set_portrait(self, icon_path: str) -> None:
        path = Path(icon_path) if icon_path else None
        if path is None or not path.exists():
            self.portrait.setPixmap(QPixmap())
            self.portrait.setText("Skin du personnage\n(à venir)")
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.portrait.setPixmap(QPixmap())
            self.portrait.setText("Skin du personnage\n(à venir)")
            return
        self.portrait.setText("")
        self.portrait.setPixmap(
            pixmap.scaled(
                self.portrait.maximumWidth() - 12,
                self.portrait.maximumHeight() - 12,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )


__all__ = ["CharacterPage"]
