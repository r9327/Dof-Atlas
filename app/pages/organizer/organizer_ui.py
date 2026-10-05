from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from app.constants import (
    ICON_PATH,
    KEY_CLICK_HOTKEY,
    KEY_DEBUG_MODE,
    KEY_DOUBLE_CLICK_HOTKEY,
    KEY_PRIMARY_WINDOW,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_SWITCH_CHARACTER,
    KEY_SWITCH_CLICK,
    KEY_SWITCH_DOUBLE_CLICK,
    KEY_SWITCH_MOVEMENT,
)
from app.storage import ZaapWidget, clean_auto_group_name, profile_bool, short_label
from app.ui.components import AtlasButton
from .common import (
    BUTTON_HEIGHT,
    CARD_PADDING,
    CARD_SPACING,
    CHARACTER_SLOT_HEIGHT,
    DOFUS_CLASS_DEFINITIONS,
    KEY_BADGE_HEIGHT,
    SESSION_SLOT_COUNT,
    STOP_BUTTON_HEIGHT,
    class_icon_path_for_window_name,
    dofus_class_key_for_character_name,
    dofus_class_key_from_window_name,
    empty_session_slot,
    session_hwnd,
    session_is_detected,
    session_is_empty,
    session_name,
)


class CharacterSlotsPanel(QFrame):
    """Organizer character card sized from the slot grid instead of a magic cap."""

    def __init__(
        self,
        refresh_button: QWidget,
        *,
        slot_count: int = SESSION_SLOT_COUNT,
        row_height: int = CHARACTER_SLOT_HEIGHT,
        columns: int = 2,
        horizontal_spacing: int = 8,
        vertical_spacing: int = 6,
        card_padding: int = CARD_PADDING,
        card_spacing: int = CARD_SPACING,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if columns <= 0:
            raise ValueError("columns must be greater than zero")
        self.slot_count = max(0, int(slot_count))
        self.row_height = max(0, int(row_height))
        self.columns = int(columns)
        self.vertical_spacing = max(0, int(vertical_spacing))

        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.panel_layout = QVBoxLayout(self)
        self.panel_layout.setContentsMargins(card_padding, card_padding, card_padding, card_padding)
        self.panel_layout.setSpacing(card_spacing)

        self.title = QLabel("Personnage")
        self.title.setObjectName("cardTitle")
        self.title.setFixedHeight(20)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        accent = QFrame()
        accent.setObjectName("CardTitleAccent")
        accent.setFixedSize(3, 16)
        header.addWidget(accent, alignment=Qt.AlignVCenter)
        header.addWidget(self.title, alignment=Qt.AlignVCenter)
        header.addStretch(1)
        header.addWidget(refresh_button, alignment=Qt.AlignVCenter)
        self.panel_layout.addLayout(header)

        self.content = QWidget()
        self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(horizontal_spacing)
        self.grid.setVerticalSpacing(self.vertical_spacing)
        for column in range(self.columns):
            self.grid.setColumnStretch(column, 1)
        self.panel_layout.addWidget(self.content)
        self.content.setFixedHeight(self.slot_grid_height())
        self.setFixedHeight(self.calculated_height())

    def row_count(self) -> int:
        if not self.slot_count:
            return 0
        return (self.slot_count + self.columns - 1) // self.columns

    def slot_grid_height(self) -> int:
        rows = self.row_count()
        if not rows:
            return 0
        return rows * self.row_height + max(0, rows - 1) * self.vertical_spacing

    def header_height(self) -> int:
        item = self.panel_layout.itemAt(0)
        return max(self.title.height(), item.sizeHint().height() if item is not None else 0)

    def calculated_height(self) -> int:
        margins = self.panel_layout.contentsMargins()
        return (
            margins.top()
            + self.header_height()
            + self.panel_layout.spacing()
            + self.slot_grid_height()
            + margins.bottom()
        )

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(hint.width(), self.calculated_height())

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(hint.width(), self.calculated_height())

    def grid_position(self, slot_index: int) -> tuple[int, int]:
        return divmod(int(slot_index), self.columns)

    def add_slot(self, widget: QWidget, slot_index: int) -> None:
        row, column = self.grid_position(slot_index)
        self.grid.addWidget(widget, row, column)

    def clear_slots(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class OrganizerUiMixin:
    def build_organizer_ui(self, status_callback, launch_zaap_callback) -> None:
        self.zaap = ZaapWidget(status_callback, launch_zaap_callback, self.refresh_sessions_and_export)
        self.zaap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)
        root.setAlignment(Qt.AlignTop)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        accent = QFrame()
        accent.setObjectName("TitleAccent")
        accent.setFixedSize(4, 24)
        title = QLabel("Organizer")
        title.setObjectName("PageTitle")
        title.setFixedHeight(28)
        header.addWidget(accent, alignment=Qt.AlignVCenter)
        header.addWidget(title, 1)
        root.addLayout(header)

        controls_title = QLabel("Macro")
        controls_title.setObjectName("cardTitle")
        controls_title.setFixedHeight(20)
        self.quick_actions_title = QLabel("Action rapide")
        self.quick_actions_title.setObjectName("cardTitle")
        self.quick_actions_title.setFixedHeight(20)
        self.runtime_status_dot = QLabel("●")
        self.runtime_status_dot.setObjectName("RuntimeStatusDot")
        self.runtime_status_dot.setFixedSize(14, 18)
        self.runtime_status_dot.setAlignment(Qt.AlignCenter)
        self.set_runtime_active(False)

        self.switch_character = AtlasButton("")
        self.switch_click = AtlasButton("")
        self.switch_double_click = AtlasButton("")
        self.switch_movement = AtlasButton("")
        self.switch_fake = AtlasButton("Auto-groupe")
        self.fake_button_2 = AtlasButton("Slot libre")
        self.click_button = AtlasButton("")
        self.double_click_button = AtlasButton("")
        self.double_click_clear = AtlasButton("x")
        self.fake_shortcut_2 = AtlasButton("F2")
        self.reload_runtime_button = AtlasButton("Relancer scripts")
        self.debug_button = AtlasButton("Debug")
        self.script_speed_title = QLabel("Vitesse script")
        self.script_speed_normal = AtlasButton("Normal")
        self.script_speed_fast = AtlasButton("Rapide")
        self.stop_script_button = AtlasButton("Stop urgence")
        self.stop_script_hotkey_button = AtlasButton("")
        self.stop_script_clear = AtlasButton("x")
        self.click_clear = AtlasButton("x")

        control_size = QSize(154, BUTTON_HEIGHT)
        controls_panel_height = 164
        panel_inner_width = control_size.width() * 2 + 8
        panel_width = panel_inner_width + CARD_PADDING * 2
        stop_hotkey_size = QSize(52, STOP_BUTTON_HEIGHT)
        stop_size = QSize(panel_inner_width - stop_hotkey_size.width() - 8, STOP_BUTTON_HEIGHT)
        shortcut_size = QSize(42, KEY_BADGE_HEIGHT)

        for button in (
            self.switch_character,
            self.switch_click,
            self.switch_double_click,
            self.switch_movement,
            self.switch_fake,
            self.fake_button_2,
            self.reload_runtime_button,
            self.debug_button,
        ):
            button.setFixedSize(control_size)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            button.setObjectName("secondaryButton")
        self.stop_script_button.setObjectName("dangerButton")
        self.stop_script_button.setFixedSize(stop_size)
        self.stop_script_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        for button in (self.click_button, self.double_click_button, self.fake_shortcut_2):
            button.setObjectName("keyBadge")
            button.setFixedSize(shortcut_size)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.stop_script_hotkey_button.setObjectName("iconButton")
        self.stop_script_hotkey_button.setFixedSize(stop_hotkey_size)
        self.stop_script_hotkey_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        for button in (self.fake_button_2, self.fake_shortcut_2):
            button.setFocusPolicy(Qt.NoFocus)
            button.setToolTip("Bouton reserve")
        self.script_speed_title.setObjectName("MutedLabel")
        self.script_speed_title.setFixedSize(stop_size.width(), 0)
        self.script_speed_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.script_speed_title.hide()
        for button in (self.script_speed_normal, self.script_speed_fast):
            button.setFixedSize(control_size)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            button.setObjectName("segmentedButton")
        self.click_button.setToolTip("Raccourci Switch Clique")
        self.double_click_button.setToolTip("Raccourci Switch clic x2")
        self.stop_script_hotkey_button.setToolTip("Raccourci Stop script")
        self.reload_runtime_button.setToolTip("Relancer les raccourcis et le runtime Python")
        self.debug_button.setToolTip("Activer les logs runtime detailles")
        self.script_speed_normal.setToolTip("Vitesse script normale")
        self.script_speed_fast.setToolTip("Vitesse script rapide")
        self.stop_script_button.setToolTip("Arreter immediatement les macros Python")
        for button in (self.click_clear, self.double_click_clear, self.stop_script_clear):
            button.setObjectName("iconButtonDanger")
            button.setFixedSize(14, 14)
            button.setToolTip("Supprimer le raccourci")

        def macro_cell(
            action: QPushButton,
            shortcut: QPushButton | None = None,
            clear: QPushButton | None = None,
            size: QSize = control_size,
        ) -> QWidget:
            wrapper = QWidget()
            wrapper.setFixedSize(size)
            wrapper.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            cell = QGridLayout(wrapper)
            cell.setContentsMargins(0, 0, 0, 0)
            cell.setHorizontalSpacing(0)
            cell.setVerticalSpacing(0)
            cell.addWidget(action, 0, 0)
            if shortcut is not None:
                cell.addWidget(shortcut, 0, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
                shortcut.raise_()
            if clear is not None:
                cell.addWidget(clear, 0, 0, alignment=Qt.AlignTop | Qt.AlignRight)
                clear.raise_()
            return wrapper

        def make_card_header(
            title_label: QLabel,
            trailing: QWidget | None = None,
            after_title: QWidget | None = None,
        ) -> QHBoxLayout:
            layout = QHBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            title_accent = QFrame()
            title_accent.setObjectName("CardTitleAccent")
            title_accent.setFixedSize(3, 16)
            layout.addWidget(title_accent, alignment=Qt.AlignVCenter)
            layout.addWidget(title_label, alignment=Qt.AlignVCenter)
            if after_title is not None:
                layout.addWidget(after_title, alignment=Qt.AlignVCenter)
            layout.addStretch(1)
            if trailing is not None:
                layout.addWidget(trailing, alignment=Qt.AlignVCenter)
            return layout

        controls_grid_host = QWidget()
        controls_grid_host.setFixedWidth(panel_inner_width)
        controls_grid_host.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        controls_grid = QGridLayout(controls_grid_host)
        controls_grid.setContentsMargins(0, 0, 0, 0)
        controls_grid.setHorizontalSpacing(8)
        controls_grid.setVerticalSpacing(8)
        controls_grid.addWidget(macro_cell(self.switch_character), 0, 0)
        controls_grid.addWidget(macro_cell(self.switch_click, self.click_button, self.click_clear), 0, 1)
        controls_grid.addWidget(macro_cell(self.switch_movement), 1, 0)
        controls_grid.addWidget(macro_cell(self.switch_double_click, self.double_click_button, self.double_click_clear), 1, 1)
        controls_grid.addWidget(macro_cell(self.switch_fake), 2, 0)
        controls_grid.addWidget(macro_cell(self.fake_button_2, self.fake_shortcut_2), 2, 1)
        for column in range(2):
            controls_grid.setColumnMinimumWidth(column, control_size.width())
            controls_grid.setColumnStretch(column, 0)
        for row in range(3):
            controls_grid.setRowMinimumHeight(row, BUTTON_HEIGHT)

        self.macro_panel = QFrame()
        self.macro_panel.setObjectName("card")
        self.macro_panel.setFixedSize(panel_width, controls_panel_height)
        self.macro_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.apply_card_shadow(self.macro_panel)
        macro_layout = QVBoxLayout(self.macro_panel)
        macro_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        macro_layout.setSpacing(CARD_SPACING)
        macro_layout.addLayout(make_card_header(controls_title, after_title=self.runtime_status_dot))
        macro_layout.addWidget(controls_grid_host, alignment=Qt.AlignLeft)

        self.quick_actions_panel = QFrame()
        self.quick_actions_panel.setObjectName("card")
        self.quick_actions_panel.setFixedSize(panel_width, controls_panel_height)
        self.quick_actions_panel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.apply_card_shadow(self.quick_actions_panel)
        quick_layout = QVBoxLayout(self.quick_actions_panel)
        quick_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        quick_layout.setSpacing(CARD_SPACING)
        quick_layout.addLayout(make_card_header(self.quick_actions_title))
        quick_grid_host = QWidget()
        quick_grid_host.setFixedWidth(panel_inner_width)
        quick_grid_host.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        quick_grid = QGridLayout(quick_grid_host)
        quick_grid.setContentsMargins(0, 0, 0, 0)
        quick_grid.setHorizontalSpacing(8)
        quick_grid.setVerticalSpacing(8)
        quick_grid.addWidget(self.reload_runtime_button, 0, 0)
        quick_grid.addWidget(self.debug_button, 0, 1)
        quick_grid.addWidget(self.script_speed_normal, 1, 0)
        quick_grid.addWidget(self.script_speed_fast, 1, 1)
        stop_row = QWidget()
        stop_row.setFixedSize(panel_inner_width, STOP_BUTTON_HEIGHT)
        stop_row.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        stop_row_layout = QHBoxLayout(stop_row)
        stop_row_layout.setContentsMargins(0, 0, 0, 0)
        stop_row_layout.setSpacing(8)
        stop_row_layout.addWidget(self.stop_script_button)
        stop_row_layout.addWidget(macro_cell(self.stop_script_hotkey_button, None, self.stop_script_clear, stop_hotkey_size))
        quick_grid.addWidget(stop_row, 2, 0, 1, 2)
        for column in range(2):
            quick_grid.setColumnMinimumWidth(column, control_size.width())
            quick_grid.setColumnStretch(column, 0)
        quick_grid.setRowMinimumHeight(0, BUTTON_HEIGHT)
        quick_grid.setRowMinimumHeight(1, BUTTON_HEIGHT)
        quick_grid.setRowMinimumHeight(2, STOP_BUTTON_HEIGHT)
        quick_layout.addWidget(quick_grid_host, alignment=Qt.AlignLeft)

        controls_panels_row = QHBoxLayout()
        controls_panels_row.setContentsMargins(0, 0, 0, 0)
        controls_panels_row.setSpacing(8)
        controls_panels_row.addWidget(self.macro_panel)
        controls_panels_row.addWidget(self.quick_actions_panel)
        controls_panels_row.addStretch(1)
        root.addLayout(controls_panels_row)

        self.zaap_panel = QFrame()
        self.zaap_panel.setObjectName("card")
        self.zaap_panel.setMaximumHeight(124)
        self.zaap_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.apply_card_shadow(self.zaap_panel)
        zaap_layout = QVBoxLayout(self.zaap_panel)
        zaap_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        zaap_layout.setSpacing(CARD_SPACING)
        zaap_title = QLabel("Zaap")
        zaap_title.setObjectName("cardTitle")
        zaap_title.setFixedHeight(20)
        zaap_layout.addLayout(make_card_header(zaap_title))
        zaap_layout.addWidget(self.zaap, 1)
        root.addWidget(self.zaap_panel)

        self.sessions_refresh_button = AtlasButton("⟳")
        self.sessions_refresh_button.setObjectName("iconButton")
        self.sessions_refresh_button.setFixedSize(32, BUTTON_HEIGHT)
        self.sessions_refresh_button.setToolTip("Scanner les fenêtres Dofus")
        self.sessions_panel = CharacterSlotsPanel(self.sessions_refresh_button)
        self.sessions_content = self.sessions_panel.content
        self.sessions_grid = self.sessions_panel.grid
        self.apply_card_shadow(self.sessions_panel)
        root.addWidget(self.sessions_panel)
        root.addStretch(1)

    def apply_card_shadow(self, frame: QFrame) -> None:
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 70))
        frame.setGraphicsEffect(shadow)

    def set_runtime_active(self, connected: bool) -> None:
        if not isValid(self):
            return
        status_dot = getattr(self, "runtime_status_dot", None)
        if status_dot is None or not isValid(status_dot):
            return
        status_dot.setObjectName("runtimeStatusActive" if connected else "runtimeStatusInactive")
        self.restyle_button(status_dot)

    def restyle_button(self, button: QPushButton) -> None:
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def set_toggle_button(self, button: QPushButton, label: str, enabled: bool) -> None:
        button.setText(label)
        button.setToolTip(f"{label} actif" if enabled else f"{label} inactif")
        button.setObjectName("primaryButton" if enabled else "secondaryButton")
        self.restyle_button(button)

    def update_switch_buttons(self) -> None:
        self.set_toggle_button(self.switch_character, "Switch Personnage", profile_bool(self.profiles, KEY_SWITCH_CHARACTER, True))
        self.set_toggle_button(self.switch_click, "Switch Clique", profile_bool(self.profiles, KEY_SWITCH_CLICK, False))
        self.set_toggle_button(self.switch_double_click, "Switch clic x2", profile_bool(self.profiles, KEY_SWITCH_DOUBLE_CLICK, False))
        self.set_toggle_button(self.switch_movement, "Switch Deplacement", profile_bool(self.profiles, KEY_SWITCH_MOVEMENT, False))

    def update_global_buttons(self) -> None:
        click = self.hotkey_label(KEY_CLICK_HOTKEY)
        double_click = self.hotkey_label(KEY_DOUBLE_CLICK_HOTKEY)
        stop_script = self.hotkey_label(KEY_STOP_SCRIPT_HOTKEY)
        self.click_button.setText(short_label(click, 9) if click else "...")
        self.click_button.setToolTip(f"Switch Clique: {click}" if click else "Raccourci Switch Clique")
        self.click_clear.setVisible(bool(click))
        self.double_click_button.setText(short_label(double_click, 9) if double_click else "...")
        self.double_click_button.setToolTip(f"Switch clic x2: {double_click}" if double_click else "Raccourci Switch clic x2")
        self.double_click_clear.setVisible(bool(double_click))
        self.stop_script_hotkey_button.setText(short_label(stop_script, 9) if stop_script else "...")
        self.stop_script_hotkey_button.setToolTip(f"Stop script: {stop_script}" if stop_script else "Raccourci Stop script")
        self.stop_script_clear.setVisible(bool(stop_script))

    def update_script_speed_buttons(self) -> None:
        speed = self.script_speed()
        for button, value in ((self.script_speed_normal, "normal"), (self.script_speed_fast, "rapide")):
            button.setObjectName("segmentedButtonActive" if speed == value else "segmentedButton")
            self.restyle_button(button)

    def update_debug_button(self) -> None:
        enabled = profile_bool(self.profiles, KEY_DEBUG_MODE, False)
        self.debug_button.setObjectName("primaryButton" if enabled else "secondaryButton")
        self.debug_button.setToolTip(
            "Debug actif: logs runtime detailles" if enabled else "Debug inactif: logs runtime allegees"
        )
        self.restyle_button(self.debug_button)

    def request_sessions_render(self) -> None:
        if self.isVisible():
            self.render_sessions()
            return
        self._sessions_render_dirty = True

    def flush_sessions_render_if_dirty(self) -> None:
        if self._sessions_render_dirty:
            self.render_sessions()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.flush_sessions_render_if_dirty()

    def render_sessions(self) -> None:
        self.sessions_panel.clear_slots()
        self.session_row_widgets = []
        self.session_slot_widgets = []
        self.sessions_grid = self.sessions_panel.grid
        self.sessions_placeholder = None
        primary = str(self.profiles.get(KEY_PRIMARY_WINDOW, ""))
        primary_matched = False
        slot_count = self.session_slot_count()
        while len(self.sessions) < slot_count:
            self.sessions.append(empty_session_slot())

        def slot_index_badge(slot_index: int) -> QLabel:
            badge = QLabel(str(slot_index + 1))
            badge.setObjectName("slotIndexBadge")
            badge.setFixedSize(24, KEY_BADGE_HEIGHT)
            badge.setAlignment(Qt.AlignCenter)
            return badge

        for index in range(slot_count):
            session = self.sessions[index]
            name = session_name(session)
            hwnd = session_hwnd(session)
            is_empty = session_is_empty(session)
            is_detected = session_is_detected(session)
            is_primary = is_detected and self.session_is_primary(name, hwnd, primary)
            if is_primary and not primary.startswith("hwnd:"):
                if primary_matched:
                    is_primary = False
                else:
                    primary_matched = True

            if is_empty:
                slot = QFrame()
                slot.setAttribute(Qt.WA_Hover, True)
                slot.setObjectName("characterSlotDropTarget" if index == self.drag_hover_index else "characterSlotEmpty")
                slot.setFixedHeight(CHARACTER_SLOT_HEIGHT)
                slot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                slot_layout = QHBoxLayout(slot)
                slot_layout.setContentsMargins(8, 0, 8, 0)
                slot_layout.setSpacing(7)
                add_marker = QLabel("+")
                add_marker.setObjectName("EmptySlotAdd")
                add_marker.setFixedWidth(18)
                add_marker.setAlignment(Qt.AlignCenter)
                slot_layout.addWidget(add_marker)
                empty_label = QLabel("Slot vide")
                empty_label.setObjectName("MutedLabel")
                empty_label.setAlignment(Qt.AlignVCenter)
                slot_layout.addWidget(empty_label, 1)
                slot_layout.addWidget(slot_index_badge(index))
                self.sessions_panel.add_slot(slot, index)
                self.session_slot_widgets.append((slot, index))
                continue

            row = QFrame()
            row.setAttribute(Qt.WA_Hover, True)
            if index == self.drag_session_index:
                row.setObjectName("characterSlotDragging")
            elif index == self.drag_hover_index:
                row.setObjectName("characterSlotDropTarget")
            elif is_detected:
                row.setObjectName("characterSlot")
            else:
                row.setObjectName("characterSlotMissing")
            row.setFixedHeight(CHARACTER_SLOT_HEIGHT)
            row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 0, 8, 0)
            layout.setSpacing(7)
            grip = AtlasButton("⠿")
            grip.setObjectName("DragHandle")
            grip.setFixedSize(14, 24)
            grip.setCursor(Qt.OpenHandCursor)
            grip.setToolTip("Déplacer ce personnage")
            self.bind_session_drag_events(grip, index, row)
            layout.addWidget(grip)
            star = AtlasButton("★" if is_primary else "☆")
            star.setObjectName("FavoriteButtonActive" if is_primary else "FavoriteButton")
            star.setFixedSize(22, 24)
            star.setToolTip("Fenêtre principale")
            star.setEnabled(is_detected)
            if is_detected:
                star.clicked.connect(lambda _checked=False, target=session: self.set_primary_window(target))
                self.bind_session_drag_events(star, index, row)
            layout.addWidget(star)
            icon = QLabel()
            icon.setFixedSize(24, 24)
            icon.setAlignment(Qt.AlignCenter)
            class_key = dofus_class_key_from_window_name(name) or dofus_class_key_for_character_name(name)
            icon_path = class_icon_path_for_window_name(name)
            pixmap = QPixmap(str(icon_path)) if icon_path is not None else QPixmap()
            if pixmap.isNull() and ICON_PATH.exists():
                pixmap = QPixmap(str(ICON_PATH))
            if not pixmap.isNull():
                pixmap = pixmap.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                icon.setPixmap(pixmap)
            if class_key:
                icon.setToolTip(DOFUS_CLASS_DEFINITIONS[class_key]["label"])
            icon.setCursor(Qt.OpenHandCursor)
            self.bind_session_drag_events(icon, index, row)
            layout.addWidget(icon)
            display_name = clean_auto_group_name(name) or name
            label = QLabel(display_name)
            label.setObjectName("CompactLabel" if is_detected else "MutedLabel")
            label.setWordWrap(False)
            label.setFixedHeight(24)
            label.setAlignment(Qt.AlignVCenter)
            label.setCursor(Qt.OpenHandCursor)
            label.setToolTip(display_name)
            self.bind_session_drag_events(label, index, row)
            layout.addWidget(label, 1)
            binding = self.slot_hotkey_label(index)
            shortcut = AtlasButton(binding or "...")
            shortcut.setObjectName("keyBadge")
            shortcut.setFixedSize(52, KEY_BADGE_HEIGHT)
            shortcut.setToolTip("Raccourci client")
            shortcut.clicked.connect(lambda _checked=False, slot=index, button=shortcut: self.begin_capture("client", slot=slot, button=button))
            remove = AtlasButton("x")
            remove.setObjectName("iconButtonDanger")
            remove.setFixedSize(14, 14)
            remove.setVisible(bool(binding))
            remove.setToolTip("Supprimer le raccourci client")
            remove.clicked.connect(lambda _checked=False, slot=index: self.remove_client_hotkey(slot))
            self.bind_session_drag_events(shortcut, index, row)
            self.bind_session_drag_events(remove, index, row)
            shortcut_wrap = QWidget()
            shortcut_wrap.setFixedSize(58, 24)
            shortcut_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.bind_session_drag_events(shortcut_wrap, index, row)
            shortcut_grid = QGridLayout(shortcut_wrap)
            shortcut_grid.setContentsMargins(0, 0, 0, 0)
            shortcut_grid.setHorizontalSpacing(0)
            shortcut_grid.setVerticalSpacing(0)
            shortcut_grid.addWidget(shortcut, 0, 0)
            shortcut_grid.addWidget(remove, 0, 0, alignment=Qt.AlignTop | Qt.AlignRight)
            remove.raise_()
            layout.addWidget(shortcut_wrap)
            index_badge = slot_index_badge(index)
            self.bind_session_drag_events(index_badge, index, row)
            layout.addWidget(index_badge)
            self.sessions_panel.add_slot(row, index)
            row.setCursor(Qt.OpenHandCursor)
            self.bind_session_drag_events(row, index, row)
            self.session_row_widgets.append((row, index))
            self.session_slot_widgets.append((row, index))
        self._sessions_render_dirty = False
