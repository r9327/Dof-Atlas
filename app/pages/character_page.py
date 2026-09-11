from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.constants import (
    CLIENT_INDEX_JSON,
    KEY_SELECTED_CHARACTER,
    NETWORK_CHARACTER_BINDINGS_FILE,
    PROFILE_FILE,
)
from app.network.character_runtime_state import (
    CharacterRuntimeSnapshot,
    CharacterRuntimeStateStore,
    character_runtime_state,
)
from app.pages.organizer_icon_cache import cached_class_icon_path_for_window_name
from app.quest_catalog import QuestCharacter, load_quest_characters
from app.services.character_order_service import CharacterOrderService
from app.storage import default_profiles, read_json


IconResolver = Callable[[str], str | Path | None]


# DOFUS Unity equipment dressing layout: clothing / weaponry on the left,
# jewellery on the right, character preview in the centre and six Dofus /
# trophy slots in one horizontal row underneath.
EQUIPMENT_SLOTS: tuple[tuple[str, str, int, int], ...] = (
    ("hat", "Coiffe", 0, 0),
    ("cape", "Cape", 1, 0),
    ("weapon", "Arme", 3, 0),
    ("shield", "Bouclier", 4, 0),
    ("pet", "Familier / montilier / monture", 5, 0),
    ("amulet", "Amulette", 0, 5),
    ("ring_left", "Anneau 1", 1, 5),
    ("ring_right", "Anneau 2", 2, 5),
    ("belt", "Ceinture", 3, 5),
    ("boots", "Bottes", 4, 5),
    ("dofus_1", "Dofus / trophée 1", 6, 0),
    ("dofus_2", "Dofus / trophée 2", 6, 1),
    ("dofus_3", "Dofus / trophée 3", 6, 2),
    ("dofus_4", "Dofus / trophée 4", 6, 3),
    ("dofus_5", "Dofus / trophée 5", 6, 4),
    ("dofus_6", "Dofus / trophée 6", 6, 5),
)

# The labels are presentation only. Values come exclusively from the verified
# runtime snapshot and rows stay hidden until Npcap has supplied that exact stat.
CHARACTER_STAT_ROWS: tuple[tuple[str, str], ...] = (
    ("life_points", "Points de vie"),
    ("action_points", "PA"),
    ("movement_points", "PM"),
    ("vitality", "Vitalité"),
    ("wisdom", "Sagesse"),
    ("strength", "Force"),
    ("intelligence", "Intelligence"),
    ("chance", "Chance"),
    ("agility", "Agilité"),
    ("power", "Puissance"),
    ("critical", "Critique"),
    ("range", "Portée"),
    ("summons", "Invocations"),
    ("prospecting", "Prospection"),
    ("initiative", "Initiative"),
    ("heals", "Soins"),
    ("dodge_action_points", "Esquive PA"),
    ("dodge_movement_points", "Esquive PM"),
    ("withdraw_action_points", "Retrait PA"),
    ("withdraw_movement_points", "Retrait PM"),
    ("escape", "Fuite"),
    ("lock", "Tacle"),
    ("shield", "Bouclier"),
    ("energy", "Énergie"),
    ("pods", "Pods"),
)


class CharacterPage(QWidget):
    """Projection UI des personnages Atlas connus autour d'une sélection centrale.

    Les statistiques en jeu et l'équipement restent volontairement vides tant
    qu'une source réseau Npcap fiable ne les expose pas au modèle central.
    """

    characterSelected = Signal(str)
    characterDeleteRequested = Signal(str)
    characterOrderChanged = Signal()

    def __init__(
        self,
        *,
        profile_path: Path = PROFILE_FILE,
        client_index_path: Path = CLIENT_INDEX_JSON,
        binding_path: Path = NETWORK_CHARACTER_BINDINGS_FILE,
        runtime_state_store: CharacterRuntimeStateStore | None = None,
        skin_resolver: IconResolver | None = None,
        icon_resolver: IconResolver | None = None,
        character_order_service: CharacterOrderService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CharacterPage")
        self.profile_path = Path(profile_path)
        self.client_index_path = Path(client_index_path)
        self.binding_path = Path(binding_path)
        self.runtime_state_store = runtime_state_store or character_runtime_state()
        self.skin_resolver = skin_resolver
        self.icon_resolver = icon_resolver
        self.character_order_service = (
            character_order_service
            if character_order_service is not None
            else CharacterOrderService(self.profile_path)
        )
        self.active_character_key = ""
        self.characters: tuple[QuestCharacter, ...] = ()
        self._character_list_signature: tuple[object, ...] | None = None
        self._runtime_generation = self.runtime_state_store.generation
        self._rebuilding_character_order = False

        # Network facts arrive on the worker after the page may already be
        # visible. Poll only the cheap generation counter while this page is
        # shown, and redraw only the current runtime projection when it changes.
        self._runtime_refresh_timer = QTimer(self)
        self._runtime_refresh_timer.setInterval(350)
        self._runtime_refresh_timer.timeout.connect(self._refresh_runtime_projection)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 20)
        root.setSpacing(12)

        title = QLabel("Mon personnage")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        subtitle = QLabel("Identité, statistiques et équipement du personnage actif")
        subtitle.setObjectName("MutedLabel")
        root.addWidget(subtitle)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 4, 0, 0)
        columns.setSpacing(14)
        root.addLayout(columns, 1)

        self.identity_panel = self._panel(None, "HomeCharacterCard")
        self.identity_panel.setMinimumWidth(270)
        self.identity_panel.setMaximumWidth(340)
        columns.addWidget(self.identity_panel, 25)
        self._build_identity_panel(self.identity_panel.layout())

        self.stats_panel = self._panel("Statistiques", "HomeTrackingCard")
        self.stats_panel.setMinimumWidth(250)
        columns.addWidget(self.stats_panel, 25)
        self._build_stats_panel(self.stats_panel.layout())

        self.equipment_panel = self._panel("Équipement", "HomeTrackingCard")
        self.equipment_panel.setMinimumWidth(460)
        columns.addWidget(self.equipment_panel, 50)
        self._build_equipment_panel(self.equipment_panel.layout())

        self.refresh_from_sources()

    @staticmethod
    def _panel(title: str | None, object_name: str) -> QFrame:
        panel = QFrame()
        panel.setObjectName(object_name)
        panel.setFrameShape(QFrame.StyledPanel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        if title:
            label = QLabel(title)
            label.setObjectName("PanelTitle")
            layout.addWidget(label)
        return panel

    def _build_identity_panel(self, layout: QVBoxLayout) -> None:
        self.character_selector = QComboBox()
        self.character_selector.setObjectName("CharacterPageCharacterCombo")
        self.character_selector.setIconSize(QSize(36, 36))
        self.character_selector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.character_selector.setToolTip("Changer de personnage")
        self.character_selector.currentIndexChanged.connect(
            self._on_character_selector_changed
        )
        layout.addWidget(self.character_selector)

        self.achievement_points = QLabel("— points de succès")
        self.achievement_points.setObjectName("PanelTitle")
        self.achievement_points.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.achievement_points)

        # Kept as a compatibility projection for existing callers/tests. The
        # visible pseudo is now the selector itself, as requested by the UI.
        self.character_name = QLabel("Aucun personnage sélectionné")
        self.character_name.setObjectName("HomeCharacterName")
        self.character_name.setAlignment(Qt.AlignCenter)
        self.character_name.setWordWrap(True)
        self.character_name.hide()
        layout.addWidget(self.character_name)

        self.character_level = QLabel("")
        self.character_level.setObjectName("MutedLabel")
        self.character_level.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.character_level)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setObjectName("DialogDivider")
        layout.addWidget(separator)

        order_title = QLabel("Ordre des personnages")
        order_title.setObjectName("PanelTitle")
        layout.addWidget(order_title)

        order_hint = QLabel("Glisser-déposer, ou utiliser les flèches.")
        order_hint.setObjectName("MutedLabel")
        order_hint.setWordWrap(True)
        layout.addWidget(order_hint)

        self.character_order_list = QListWidget()
        self.character_order_list.setObjectName("CharacterOrderList")
        self.character_order_list.setIconSize(QSize(30, 30))
        self.character_order_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.character_order_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.character_order_list.setDefaultDropAction(Qt.MoveAction)
        self.character_order_list.setDropIndicatorShown(True)
        self.character_order_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.character_order_list.setMinimumHeight(132)
        self.character_order_list.setMaximumHeight(190)
        self.character_order_list.itemDoubleClicked.connect(
            self._on_character_order_item_activated
        )
        self.character_order_list.currentRowChanged.connect(
            lambda _row: self._update_character_order_controls()
        )
        self.character_order_list.model().rowsMoved.connect(
            self._on_character_order_rows_moved
        )
        layout.addWidget(self.character_order_list, 1)

        order_controls = QHBoxLayout()
        order_controls.setContentsMargins(0, 0, 0, 0)
        order_controls.setSpacing(6)

        self.character_move_up = QToolButton()
        self.character_move_up.setObjectName("SecondaryButton")
        self.character_move_up.setText("↑")
        self.character_move_up.setToolTip("Monter ce personnage")
        self.character_move_up.setCursor(Qt.PointingHandCursor)
        self.character_move_up.clicked.connect(lambda: self._move_selected_character(-1))
        order_controls.addWidget(self.character_move_up)

        self.character_move_down = QToolButton()
        self.character_move_down.setObjectName("SecondaryButton")
        self.character_move_down.setText("↓")
        self.character_move_down.setToolTip("Descendre ce personnage")
        self.character_move_down.setCursor(Qt.PointingHandCursor)
        self.character_move_down.clicked.connect(lambda: self._move_selected_character(1))
        order_controls.addWidget(self.character_move_down)

        order_controls.addStretch(1)

        self.character_delete_button = QToolButton()
        self.character_delete_button.setObjectName("SecondaryButton")
        self.character_delete_button.setText("Supprimer")
        self.character_delete_button.setToolTip("Supprimer le personnage sélectionné d'Atlas")
        self.character_delete_button.setCursor(Qt.PointingHandCursor)
        self.character_delete_button.clicked.connect(self._delete_selected_character)
        order_controls.addWidget(self.character_delete_button)
        layout.addLayout(order_controls)
        layout.addStretch(1)

    def _build_stats_panel(self, layout: QVBoxLayout) -> None:
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
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_layout.addWidget(value, 0)

            row.hide()
            content_layout.addWidget(row)
            self.stat_rows[stat_key] = row
            self.stat_value_labels[stat_key] = value

        content_layout.addStretch(1)
        self.stats_scroll.setWidget(content)
        layout.addWidget(self.stats_scroll, 1)

    def _build_equipment_panel(self, layout: QVBoxLayout) -> None:
        equipment_widget = QWidget()
        equipment_widget.setObjectName("CharacterEquipmentGrid")
        equipment_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        grid = QGridLayout(equipment_widget)
        grid.setContentsMargins(6, 8, 6, 6)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.equipment_slots: dict[str, QToolButton] = {}

        for column in range(6):
            grid.setColumnMinimumWidth(column, 62)
        for row in range(7):
            grid.setRowMinimumHeight(row, 62)

        self.portrait = QLabel("◈")
        self.portrait.setObjectName("HomeCharacterPortrait")
        self.portrait.setAlignment(Qt.AlignCenter)
        self.portrait.setMinimumSize(214, 292)
        self.portrait.setMaximumSize(274, 332)
        self.portrait.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        grid.addWidget(self.portrait, 0, 1, 6, 4, Qt.AlignCenter)

        for slot_key, slot_label, row, column in EQUIPMENT_SLOTS:
            button = QToolButton()
            button.setObjectName("SecondaryButton")
            button.setProperty("equipmentSlot", slot_key)
            button.setFixedSize(62, 62)
            button.setIconSize(QSize(52, 52))
            button.setEnabled(False)
            button.setToolTip(slot_label)
            button.setText("")
            grid.addWidget(button, row, column, Qt.AlignCenter)
            self.equipment_slots[slot_key] = button

        layout.addWidget(equipment_widget, 1, Qt.AlignHCenter)

    @staticmethod
    def _file_stamp(path: Path) -> tuple[str, int, int]:
        resolved = str(path.resolve())
        try:
            stat = path.stat()
        except OSError:
            return (resolved, 0, 0)
        return (resolved, int(stat.st_mtime_ns), int(stat.st_size))

    def _selected_key_from_profile(self) -> str:
        payload = read_json(self.profile_path, default_profiles())
        if not isinstance(payload, dict):
            return ""
        return str(payload.get(KEY_SELECTED_CHARACTER, "") or "")

    def refresh_from_sources(self, active_key: str | None = None) -> None:
        if active_key is None:
            active_key = self.active_character_key or self._selected_key_from_profile()
        self.active_character_key = str(active_key or "")

        loaded_characters = tuple(
            load_quest_characters(
                self.profile_path,
                self.client_index_path,
                binding_path=self.binding_path,
                connected_only=False,
            )
        )
        self.characters = self.character_order_service.sort_rows(
            loaded_characters,
            label_getter=lambda row: row.label,
        )

        signature = (
            self.active_character_key,
            tuple((row.key, row.label, row.connected) for row in self.characters),
            self.character_order_service.load_order(),
            self._file_stamp(self.profile_path),
            self._file_stamp(self.client_index_path),
            self._file_stamp(self.binding_path),
        )
        if signature != self._character_list_signature:
            self._character_list_signature = signature
            self._rebuild_character_selector()
            self._rebuild_character_order_list()
        else:
            self._sync_character_selector_selection()
            self._sync_character_order_selection()

        selected = next(
            (row for row in self.characters if row.key == self.active_character_key),
            None,
        )
        self._render_identity(selected)
        self._runtime_generation = self.runtime_state_store.generation

    def _refresh_runtime_projection(self) -> None:
        generation = self.runtime_state_store.generation
        if generation == self._runtime_generation:
            return
        self._runtime_generation = generation
        self._refresh_character_selector_runtime_labels()
        self._refresh_character_order_runtime_labels()
        selected = next(
            (row for row in self.characters if row.key == self.active_character_key),
            None,
        )
        self._render_identity(selected)

    def _character_selector_text(self, character: QuestCharacter) -> str:
        snapshot = self.runtime_state_store.snapshot(character.key)
        points = snapshot.achievement_points if snapshot is not None else None
        points_text = str(points) if points is not None else "—"
        return f"{character.label}  ·  {points_text} succès"

    def _rebuild_character_selector(self) -> None:
        self.character_selector.blockSignals(True)
        try:
            self.character_selector.clear()
            self.character_selector.setEnabled(bool(self.characters))
            for character in self.characters:
                visual_path = self._visual_path(character.label)
                icon = QIcon(visual_path) if visual_path else QIcon()
                self.character_selector.addItem(
                    icon,
                    self._character_selector_text(character),
                    character.key,
                )
            self._sync_character_selector_selection()
        finally:
            self.character_selector.blockSignals(False)

    def _sync_character_selector_selection(self) -> None:
        target = -1
        for index in range(self.character_selector.count()):
            if str(self.character_selector.itemData(index) or "") == self.active_character_key:
                target = index
                break
        if self.character_selector.currentIndex() == target:
            return
        self.character_selector.blockSignals(True)
        try:
            self.character_selector.setCurrentIndex(target)
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
                    self.character_selector.setItemText(
                        index,
                        self._character_selector_text(character),
                    )
        finally:
            self.character_selector.blockSignals(False)

    def _on_character_selector_changed(self, index: int) -> None:
        if index < 0:
            return
        key = str(self.character_selector.itemData(index) or "").strip()
        if not key or key == self.active_character_key:
            return
        self.characterSelected.emit(key)

    def _rebuild_character_order_list(self) -> None:
        self._rebuilding_character_order = True
        try:
            self.character_order_list.clear()
            for character in self.characters:
                visual_path = self._visual_path(character.label)
                icon = QIcon(visual_path) if visual_path else QIcon()
                item = QListWidgetItem(icon, self._character_selector_text(character))
                item.setData(Qt.UserRole, character.key)
                item.setFlags(
                    item.flags()
                    | Qt.ItemIsDragEnabled
                    | Qt.ItemIsDropEnabled
                    | Qt.ItemIsSelectable
                    | Qt.ItemIsEnabled
                )
                self.character_order_list.addItem(item)
            self.character_order_list.setEnabled(bool(self.characters))
            self._sync_character_order_selection()
            self._update_character_order_controls()
        finally:
            self._rebuilding_character_order = False

    def _sync_character_order_selection(self) -> None:
        target = -1
        for row in range(self.character_order_list.count()):
            item = self.character_order_list.item(row)
            if item is not None and str(item.data(Qt.UserRole) or "") == self.active_character_key:
                target = row
                break
        if target >= 0:
            self.character_order_list.setCurrentRow(target)
        elif self.character_order_list.count() and self.character_order_list.currentRow() < 0:
            self.character_order_list.setCurrentRow(0)
        self._update_character_order_controls()

    def _refresh_character_order_runtime_labels(self) -> None:
        by_key = {character.key: character for character in self.characters}
        for row in range(self.character_order_list.count()):
            item = self.character_order_list.item(row)
            if item is None:
                continue
            character = by_key.get(str(item.data(Qt.UserRole) or ""))
            if character is not None:
                item.setText(self._character_selector_text(character))

    def _on_character_order_item_activated(self, item: QListWidgetItem) -> None:
        key = str(item.data(Qt.UserRole) or "").strip()
        if key and key != self.active_character_key:
            self.characterSelected.emit(key)

    def _on_character_order_rows_moved(self, *_args) -> None:
        if self._rebuilding_character_order:
            return
        self._persist_character_order()

    def _ordered_character_labels(self) -> list[str]:
        by_key = {character.key: character.label for character in self.characters}
        labels: list[str] = []
        for row in range(self.character_order_list.count()):
            item = self.character_order_list.item(row)
            if item is None:
                continue
            label = by_key.get(str(item.data(Qt.UserRole) or ""), "")
            if label:
                labels.append(label)
        return labels

    def _persist_character_order(self) -> None:
        if not self.character_order_service.save_labels(self._ordered_character_labels()):
            self._update_character_order_controls()
            return
        self.characters = self.character_order_service.sort_rows(
            self.characters,
            label_getter=lambda row: row.label,
        )
        self._character_list_signature = None
        self._rebuild_character_selector()
        self._sync_character_order_selection()
        self._update_character_order_controls()
        self.characterOrderChanged.emit()

    def _move_selected_character(self, delta: int) -> None:
        row = self.character_order_list.currentRow()
        target = row + int(delta)
        if row < 0 or target < 0 or target >= self.character_order_list.count():
            self._update_character_order_controls()
            return
        item = self.character_order_list.takeItem(row)
        if item is None:
            return
        self.character_order_list.insertItem(target, item)
        self.character_order_list.setCurrentRow(target)
        self._persist_character_order()

    def _update_character_order_controls(self) -> None:
        row = self.character_order_list.currentRow()
        count = self.character_order_list.count()
        self.character_move_up.setEnabled(row > 0)
        self.character_move_down.setEnabled(0 <= row < count - 1)
        self.character_delete_button.setEnabled(0 <= row < count)

    def _delete_selected_character(self) -> None:
        item = self.character_order_list.currentItem()
        if item is None:
            return
        key = str(item.data(Qt.UserRole) or "").strip()
        character = next((row for row in self.characters if row.key == key), None)
        if character is not None:
            self._confirm_delete_character(character.key, character.label)

    def _confirm_delete_character(self, character_key: str, label: str) -> None:
        answer = QMessageBox.question(
            self,
            "Supprimer le personnage",
            f"Êtes-vous sûr de vouloir supprimer {label} ?\n\n"
            "Toutes les données Atlas liées à ce personnage seront supprimées.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if answer == QMessageBox.Yes:
            self.characterDeleteRequested.emit(str(character_key))

    def _render_identity(self, character: QuestCharacter | None) -> None:
        snapshot = self.runtime_state_store.snapshot(self.active_character_key)
        points = snapshot.achievement_points if snapshot is not None else None
        level = snapshot.level if snapshot is not None else None
        self.achievement_points.setText(
            f"{points} points de succès" if points is not None else "— points de succès"
        )
        self.character_level.setText(f"Niveau {level}" if level is not None else "")
        self._render_stats(snapshot)
        if character is None:
            self.character_name.setText("Aucun personnage sélectionné")
            self._set_portrait("")
            return
        self.character_name.setText(character.label)
        self._set_portrait(self._visual_path(character.label))

    def _render_stats(self, snapshot: CharacterRuntimeSnapshot | None) -> None:
        values = dict(snapshot.stats) if snapshot is not None else {}
        for stat_key, _label_text in CHARACTER_STAT_ROWS:
            row = self.stat_rows[stat_key]
            value_label = self.stat_value_labels[stat_key]
            if stat_key not in values:
                value_label.setText("")
                row.hide()
                continue
            value_label.setText(str(values[stat_key]))
            row.show()

    def _skin_path(self, label: str) -> str:
        if self.skin_resolver is None:
            return ""
        try:
            candidate = self.skin_resolver(label)
        except Exception:
            candidate = None
        path = Path(candidate) if candidate else None
        return str(path) if path is not None and path.exists() else ""

    def _icon_path(self, label: str) -> str:
        candidate: str | Path | None = None
        if self.icon_resolver is not None:
            try:
                candidate = self.icon_resolver(label)
            except Exception:
                candidate = None
        if not candidate:
            try:
                candidate = cached_class_icon_path_for_window_name(label)
            except Exception:
                candidate = None
        path = Path(candidate) if candidate else None
        return str(path) if path is not None and path.exists() else ""

    def _visual_path(self, label: str) -> str:
        return self._skin_path(label) or self._icon_path(label)

    def _set_portrait(self, icon_path: str) -> None:
        path = Path(icon_path) if icon_path else None
        if path is None or not path.exists():
            self.portrait.setPixmap(QPixmap())
            self.portrait.setText("◈")
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self.portrait.setPixmap(QPixmap())
            self.portrait.setText("◈")
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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh_from_sources(self.active_character_key or None)
        if not self._runtime_refresh_timer.isActive():
            self._runtime_refresh_timer.start()

    def hideEvent(self, event) -> None:
        self._runtime_refresh_timer.stop()
        super().hideEvent(event)


__all__ = ["CharacterPage", "CHARACTER_STAT_ROWS", "EQUIPMENT_SLOTS"]