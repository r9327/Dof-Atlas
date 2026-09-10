from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.constants import (
    CLIENT_INDEX_INI,
    CLIENT_INDEX_JSON,
    DATA_DIR,
    ICON_PATH,
    KEY_CLICK_HOTKEY,
    KEY_DEBUG_MODE,
    KEY_DOUBLE_CLICK_HOTKEY,
    KEY_PRIMARY_WINDOW,
    KEY_SCRIPT_SPEED,
    KEY_SESSION_ORDER,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_SWITCH_CHARACTER,
    KEY_SWITCH_CLICK,
    KEY_SWITCH_DOUBLE_CLICK,
    KEY_SWITCH_MOVEMENT,
    KEY_TRAVEL_TEXT,
    PROFILE_FILE,
)
from app.storage import (
    ZaapWidget,
    clean_auto_group_name,
    default_profiles,
    format_zaap_ratio,
    invoke_compatible_callback,
    key_sequence_to_hotkey,
    normalize_key,
    profile_bool,
    read_json,
    read_zaap_button_ratios,
    read_zaap_click_position,
    short_label,
    write_json,
    write_text_atomic,
)
from app.quest_catalog import is_generic_dofus_client_name
from app.services.character_order_service import CharacterOrderService
from app.services.profile_settings_service import ProfileSettingsService
from app.ui.components import AtlasButton
from app.windows_embed import EVENT_SYSTEM_FOREGROUND, UnityWindowEventWatcher, scan_unity_sessions

CLASS_ICON_DIRS = (
    DATA_DIR / "images" / "classes",
    DATA_DIR / "images" / "breeds",
    DATA_DIR / "images" / "misc" / "classes",
)
CLASS_ICON_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg", ".ico")
SESSION_SLOT_COUNT = 8
WINDOW_EVENT_DEBOUNCE_MS = 80
RELEASE_RETRY_DELAYS_MS = (200, 500, 1000, 2000)
CARD_PADDING = 12
CARD_SPACING = 10
BUTTON_HEIGHT = 30
INPUT_HEIGHT = 32
KEY_BADGE_HEIGHT = 22
KEY_BADGE_MIN_WIDTH = 34
FAVORITE_CHIP_HEIGHT = 28
CHARACTER_SLOT_HEIGHT = 36
STOP_BUTTON_HEIGHT = 34
DOFUS_CLASS_DEFINITIONS = {
    "feca": {"id": 1, "label": "Feca", "aliases": ("feca", "féca")},
    "osamodas": {"id": 2, "label": "Osamodas", "aliases": ("osamodas",)},
    "enutrof": {"id": 3, "label": "Enutrof", "aliases": ("enutrof",)},
    "sram": {"id": 4, "label": "Sram", "aliases": ("sram",)},
    "xelor": {"id": 5, "label": "Xelor", "aliases": ("xelor", "xélor")},
    "ecaflip": {"id": 6, "label": "Ecaflip", "aliases": ("ecaflip",)},
    "eniripsa": {"id": 7, "label": "Eniripsa", "aliases": ("eniripsa",)},
    "iop": {"id": 8, "label": "Iop", "aliases": ("iop",)},
    "cra": {"id": 9, "label": "Cra", "aliases": ("cra", "crâ")},
    "sadida": {"id": 10, "label": "Sadida", "aliases": ("sadida",)},
    "sacrieur": {"id": 11, "label": "Sacrieur", "aliases": ("sacrieur",)},
    "pandawa": {"id": 12, "label": "Pandawa", "aliases": ("pandawa",)},
    "roublard": {"id": 13, "label": "Roublard", "aliases": ("roublard",)},
    "zobal": {"id": 14, "label": "Zobal", "aliases": ("zobal",)},
    "steamer": {"id": 15, "label": "Steamer", "aliases": ("steamer",)},
    "eliotrope": {"id": 16, "label": "Eliotrope", "aliases": ("eliotrope", "éliotrope")},
    "huppermage": {"id": 17, "label": "Huppermage", "aliases": ("huppermage",)},
    "ouginak": {"id": 18, "label": "Ouginak", "aliases": ("ouginak",)},
    "forgelance": {"id": 20, "label": "Forgelance", "aliases": ("forgelance",)},
}


def empty_session_slot() -> dict[str, Any]:
    return {"nom": "", "hwnd": 0, "_empty_slot": True}


def client_slot_hotkey_key(slot_index: int) -> str:
    return f"__raccourci_personnage_{max(1, int(slot_index) + 1)}__"


def session_name(session: dict[str, Any] | None) -> str:
    return str((session or {}).get("nom", "")).strip()


def session_hwnd(session: dict[str, Any] | None) -> int:
    try:
        return int((session or {}).get("hwnd", 0))
    except (TypeError, ValueError):
        return 0


def session_pid(session: dict[str, Any] | None) -> int:
    try:
        return int((session or {}).get("pid", 0))
    except (TypeError, ValueError):
        return 0


def session_is_empty(session: dict[str, Any] | None) -> bool:
    return bool((session or {}).get("_empty_slot")) or not session_name(session) or session_hwnd(session) <= 0


def session_is_detected(session: dict[str, Any] | None) -> bool:
    return bool(session_name(session) and session_hwnd(session) > 0 and not (session or {}).get("_empty_slot"))


def dofus_class_key_from_window_name(value: Any) -> str | None:
    tokens = set(normalize_key(value).split("_"))
    if not tokens:
        return None
    for class_key, definition in DOFUS_CLASS_DEFINITIONS.items():
        for alias in definition["aliases"]:
            if normalize_key(alias) in tokens:
                return class_key
    return None


def dofus_class_key_for_character_name(value: Any) -> str | None:
    """Resolve a class from the exported slot metadata without changing display text."""

    character_key = normalize_key(value)
    if not character_key:
        return None
    payload = read_json(CLIENT_INDEX_JSON, {"clients": []})
    clients = payload.get("clients", []) if isinstance(payload, dict) else []
    if not isinstance(clients, list):
        return None

    matches: set[str] = set()
    for client in clients:
        if not isinstance(client, dict):
            continue
        display_name = str(client.get("character_name") or "").strip()
        if normalize_key(display_name) != character_key:
            continue
        explicit_class = normalize_key(client.get("class_key"))
        if explicit_class in DOFUS_CLASS_DEFINITIONS:
            matches.add(explicit_class)
            continue
        inferred_class = dofus_class_key_from_window_name(client.get("name"))
        if inferred_class:
            matches.add(inferred_class)
    if len(matches) != 1:
        return None
    return next(iter(matches))


def class_icon_candidates(class_key: str) -> list[Path]:
    definition = DOFUS_CLASS_DEFINITIONS.get(class_key)
    if not definition:
        return []
    class_id = definition["id"]
    stems = []
    for value in (class_key, definition["label"], *definition["aliases"]):
        key = normalize_key(value)
        if key and key not in stems:
            stems.append(key)
    stems.extend([f"symbol_{class_id}", f"logo_transparent_{class_id}", f"class_{class_key}"])
    candidates = []
    for directory in CLASS_ICON_DIRS:
        for stem in stems:
            for extension in CLASS_ICON_EXTENSIONS:
                candidates.append(directory / f"{stem}{extension}")
    return candidates


def class_icon_path_for_window_name(value: Any) -> Path | None:
    class_key = dofus_class_key_from_window_name(value) or dofus_class_key_for_character_name(value)
    if not class_key:
        return None
    for path in class_icon_candidates(class_key):
        if path.exists():
            return path
    return None


class OrganizerPage(QWidget):
    unityWindowEvent = Signal(int, int)

    def __init__(
        self,
        status_callback,
        reload_runtime_callback,
        stop_runtime_callback=None,
        launch_auto_group_callback=None,
        launch_travel_callback=None,
        launch_zaap_callback=None,
        parent: QWidget | None = None,
        sessions_changed_callback=None,
        active_session_callback=None,
    ):
        super().__init__(parent)
        self.setObjectName("organizerPage")
        self.status_callback = status_callback
        self.reload_runtime_callback = reload_runtime_callback
        self.stop_runtime_callback = stop_runtime_callback
        self.launch_auto_group_callback = launch_auto_group_callback
        self.launch_travel_callback = launch_travel_callback
        self.launch_zaap_callback = launch_zaap_callback
        self.sessions_changed_callback = sessions_changed_callback
        self.active_session_callback = active_session_callback
        self._last_notified_session_signature: tuple[tuple[int, str, int, int], ...] | None = None
        self._sessions_render_dirty = False
        self.release_retry_index = 0
        self.character_order_service = CharacterOrderService(PROFILE_FILE)
        self.profiles = self.load_profiles()
        self.sessions: list[dict[str, Any]] = self.build_session_slots(self.load_last_sessions())
        self.capture_target: dict[str, Any] | None = None
        self.drag_session_index: int | None = None
        self.drag_session_row: QWidget | None = None
        self.drag_session_key: str | None = None
        self.drag_session_moved = False
        self.drag_drop_index: int | None = None
        self.drag_hover_index: int | None = None
        self.drag_pending_index: int | None = None
        self.drag_pending_row: QWidget | None = None
        self.drag_start_global: QPoint | None = None
        self.drag_last_global: QPoint | None = None
        self.drag_ghost: QLabel | None = None
        self.drag_ghost_offset = QPoint(0, 0)
        self.session_row_widgets: list[tuple[QWidget, int]] = []
        self.session_slot_widgets: list[tuple[QWidget, int]] = []
        self.sessions_grid: QGridLayout | None = None
        self.sessions_placeholder: QWidget | None = None
        self.setFocusPolicy(Qt.StrongFocus)

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
        panel_inner_width = (control_size.width() * 2) + 8
        panel_width = panel_inner_width + (CARD_PADDING * 2)
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

        def make_card_header(
            title_label: QLabel,
            trailing: QWidget | None = None,
            after_title: QWidget | None = None,
        ) -> QHBoxLayout:
            header_layout = QHBoxLayout()
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(8)
            title_accent = QFrame()
            title_accent.setObjectName("CardTitleAccent")
            title_accent.setFixedSize(3, 16)
            header_layout.addWidget(title_accent, alignment=Qt.AlignVCenter)
            header_layout.addWidget(title_label, alignment=Qt.AlignVCenter)
            if after_title is not None:
                header_layout.addWidget(after_title, alignment=Qt.AlignVCenter)
            header_layout.addStretch(1)
            if trailing is not None:
                header_layout.addWidget(trailing, alignment=Qt.AlignVCenter)
            return header_layout

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

        zaap_panel = QFrame()
        zaap_panel.setObjectName("card")
        zaap_panel.setMaximumHeight(124)
        zaap_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.apply_card_shadow(zaap_panel)
        zaap_layout = QVBoxLayout(zaap_panel)
        zaap_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        zaap_layout.setSpacing(CARD_SPACING)
        zaap_title = QLabel("Zaap")
        zaap_title.setObjectName("cardTitle")
        zaap_title.setFixedHeight(20)
        zaap_layout.addLayout(make_card_header(zaap_title))
        zaap_layout.addWidget(self.zaap, 1)
        root.addWidget(zaap_panel)

        self.sessions_area = QScrollArea()
        self.sessions_area.setObjectName("SessionsArea")
        self.sessions_area.setWidgetResizable(True)
        self.sessions_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sessions_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sessions_area.setFrameShape(QFrame.NoFrame)
        self.sessions_content = QWidget()
        self.sessions_layout = QVBoxLayout(self.sessions_content)
        self.sessions_layout.setContentsMargins(0, 0, 0, 0)
        self.sessions_layout.setSpacing(5)
        self.sessions_area.setWidget(self.sessions_content)
        sessions_panel = QFrame()
        sessions_panel.setObjectName("card")
        sessions_panel.setMaximumHeight(226)
        sessions_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.apply_card_shadow(sessions_panel)
        sessions_panel_layout = QVBoxLayout(sessions_panel)
        sessions_panel_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        sessions_panel_layout.setSpacing(CARD_SPACING)
        sessions_title = QLabel("Personnage")
        sessions_title.setObjectName("cardTitle")
        sessions_title.setFixedHeight(20)
        self.sessions_refresh_button = AtlasButton("⟳")
        self.sessions_refresh_button.setObjectName("iconButton")
        self.sessions_refresh_button.setFixedSize(32, BUTTON_HEIGHT)
        self.sessions_refresh_button.setToolTip("Scanner les fenêtres Dofus")
        sessions_panel_layout.addLayout(make_card_header(sessions_title, trailing=self.sessions_refresh_button))
        sessions_panel_layout.addWidget(self.sessions_area, 1)
        root.addWidget(sessions_panel)
        root.addStretch(1)

        self.click_button.clicked.connect(lambda: self.begin_capture("click"))
        self.click_clear.clicked.connect(lambda: self.clear_global_hotkey(KEY_CLICK_HOTKEY))
        self.double_click_button.clicked.connect(lambda: self.begin_capture("double_click"))
        self.double_click_clear.clicked.connect(lambda: self.clear_global_hotkey(KEY_DOUBLE_CLICK_HOTKEY))
        self.stop_script_button.clicked.connect(self.stop_script)
        self.stop_script_hotkey_button.clicked.connect(lambda: self.begin_capture("stop_script"))
        self.stop_script_clear.clicked.connect(lambda: self.clear_global_hotkey(KEY_STOP_SCRIPT_HOTKEY))
        self.reload_runtime_button.clicked.connect(self.reload_runtime)
        self.debug_button.clicked.connect(self.toggle_debug_mode)
        self.sessions_refresh_button.clicked.connect(self.scan_sessions)
        self.switch_character.clicked.connect(lambda: self.toggle_profile_bool(KEY_SWITCH_CHARACTER))
        self.switch_click.clicked.connect(lambda: self.toggle_profile_bool(KEY_SWITCH_CLICK))
        self.switch_double_click.clicked.connect(lambda: self.toggle_profile_bool(KEY_SWITCH_DOUBLE_CLICK))
        self.switch_movement.clicked.connect(lambda: self.toggle_profile_bool(KEY_SWITCH_MOVEMENT))
        self.switch_fake.clicked.connect(self.launch_auto_group)
        self.script_speed_normal.clicked.connect(lambda: self.set_script_speed("normal"))
        self.script_speed_fast.clicked.connect(lambda: self.set_script_speed("rapide"))
        self.update_switch_buttons()
        self.update_global_buttons()
        self.update_script_speed_buttons()
        self.update_debug_button()
        self.export_client_index()
        self.request_sessions_render()
        self.window_event_refresh_timer = QTimer(self)
        self.window_event_refresh_timer.setSingleShot(True)
        self.window_event_refresh_timer.setInterval(WINDOW_EVENT_DEBOUNCE_MS)
        self.window_event_refresh_timer.timeout.connect(self.refresh_sessions_from_window_event)
        self.release_retry_timer = QTimer(self)
        self.release_retry_timer.setSingleShot(True)
        self.release_retry_timer.timeout.connect(self.retry_release_identity)
        self.unityWindowEvent.connect(self.on_unity_window_event)
        self.session_event_watcher = UnityWindowEventWatcher(self.unityWindowEvent.emit)
        if os.environ.get("QT_QPA_PLATFORM", "").strip().casefold() != "offscreen":
            self.session_event_watcher.start()
        self.destroyed.connect(self.stop_session_event_watcher)
        self.startup_scan_timer = QTimer(self)
        self.startup_scan_timer.setSingleShot(True)
        self.startup_scan_timer.timeout.connect(self.auto_scan_sessions_on_startup)
        self.startup_scan_timer.start(0)

    def apply_card_shadow(self, frame: QFrame) -> None:
        shadow = QGraphicsDropShadowEffect(frame)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 70))
        frame.setGraphicsEffect(shadow)

    def load_profiles(self) -> dict[str, Any]:
        payload = read_json(PROFILE_FILE, default_profiles())
        if not isinstance(payload, dict):
            payload = default_profiles()
        merged = default_profiles()
        merged.update(payload)
        cleaned = self.sanitize_profiles(merged)
        cleaned[KEY_SESSION_ORDER] = list(self.character_order_service.load_order())
        self._profiles_baseline = dict(cleaned)
        return cleaned

    def sanitize_profiles(self, payload: dict[str, Any]) -> dict[str, Any]:
        cleaned = dict(payload)
        legacy_debug_key = "".join(["__mode_debug_", "a", "h", "k__"])
        if legacy_debug_key in cleaned and KEY_DEBUG_MODE not in cleaned:
            cleaned[KEY_DEBUG_MODE] = cleaned.get(legacy_debug_key)
        cleaned.pop(legacy_debug_key, None)
        legacy_order = cleaned.get(KEY_SESSION_ORDER, [])
        if not isinstance(legacy_order, list):
            legacy_order = []

        for index, raw_name in enumerate(legacy_order[:SESSION_SLOT_COUNT]):
            name = str(raw_name or "").strip()
            if not name:
                continue
            legacy_binding = str(cleaned.get(name, "")).strip().upper()
            slot_key = client_slot_hotkey_key(index)
            if legacy_binding and not str(cleaned.get(slot_key, "")).strip():
                cleaned[slot_key] = legacy_binding

        for key in list(cleaned.keys()):
            if not str(key).startswith("__"):
                cleaned.pop(key, None)
        cleaned.pop(KEY_TRAVEL_TEXT, None)
        cleaned[KEY_SESSION_ORDER] = [str(value or "").strip() for value in legacy_order]
        primary = str(cleaned.get(KEY_PRIMARY_WINDOW, "")).strip()
        if primary and not primary.startswith("hwnd:"):
            cleaned[KEY_PRIMARY_WINDOW] = ""
        return cleaned

    def save_profiles(self, payload: dict[str, Any]) -> None:
        snapshot = dict(payload)
        snapshot[KEY_SESSION_ORDER] = list(self.character_order_service.load_order())
        baseline = dict(getattr(self, "_profiles_baseline", {}))
        updates = {
            key: value
            for key, value in snapshot.items()
            if key not in baseline or baseline.get(key) != value
        }
        removals = tuple(key for key in baseline if key not in snapshot)
        persisted, _changed = ProfileSettingsService(PROFILE_FILE).update_values(
            updates,
            remove_keys=removals,
            default=default_profiles(),
        )
        current = self.sanitize_profiles(persisted)
        current[KEY_SESSION_ORDER] = list(self.character_order_service.load_order())
        self.profiles = current
        self._profiles_baseline = dict(current)

    def set_runtime_active(self, connected: bool) -> None:
        if not hasattr(self, "runtime_status_dot"):
            return
        self.runtime_status_dot.setObjectName("runtimeStatusActive" if connected else "runtimeStatusInactive")
        self.restyle_button(self.runtime_status_dot)

    def reload_profiles_and_export(self) -> None:
        self.profiles = self.load_profiles()
        self.export_client_index()
        self.request_sessions_render()

    def refresh_sessions_and_export(self, render: bool = False) -> bool:
        self.profiles = self.load_profiles()
        refreshed = False
        if os.name == "nt":
            sessions = scan_unity_sessions()
            self.sessions = self.build_session_slots(sessions)
            refreshed = bool(sessions)
        self.export_client_index()
        if render:
            self.request_sessions_render()
        self.sync_event_watcher_sessions()
        self.notify_sessions_changed()
        return refreshed

    def sync_event_watcher_sessions(self) -> None:
        watcher = getattr(self, "session_event_watcher", None)
        if watcher is None:
            return
        watcher.replace_tracked_hwnds(
            session_hwnd(session)
            for session in self.sessions
            if session_is_detected(session)
        )

    def stop_session_event_watcher(self, *_args) -> None:
        self.window_event_refresh_timer.stop()
        self.release_retry_timer.stop()
        watcher = getattr(self, "session_event_watcher", None)
        if watcher is not None:
            watcher.stop()

    def on_unity_window_event(self, event_id: int, hwnd: int) -> None:
        if int(event_id) == EVENT_SYSTEM_FOREGROUND and callable(self.active_session_callback):
            self.active_session_callback(int(hwnd))
        self.window_event_refresh_timer.start()

    def session_identity_signature(self) -> tuple[tuple[int, str, int, int], ...]:
        return tuple(
            (
                slot_index + 1,
                clean_auto_group_name(session_name(session)),
                session_hwnd(session),
                session_pid(session),
            )
            for slot_index, session in enumerate(self.sessions)
            if session_is_detected(session)
        )

    def notify_sessions_changed(self) -> None:
        signature = self.session_identity_signature()
        if signature == self._last_notified_session_signature:
            return
        self._last_notified_session_signature = signature
        if callable(self.sessions_changed_callback):
            self.sessions_changed_callback()

    def load_last_sessions(self) -> list[dict[str, Any]]:
        return []

    def session_slot_count(self) -> int:
        return SESSION_SLOT_COUNT

    def detected_session_count(self) -> int:
        return sum(1 for session in self.sessions if session_is_detected(session))

    def build_session_slots(self, detected_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        detected = [
            dict(session)
            for session in detected_sessions
            if session_is_detected(session)
        ]
        ordered = list(
            self.character_order_service.sort_rows(
                detected,
                label_getter=lambda session: (
                    clean_auto_group_name(session_name(session)) or session_name(session)
                ),
            )
        )
        slots = ordered[:SESSION_SLOT_COUNT]
        while len(slots) < SESSION_SLOT_COUNT:
            slots.append(empty_session_slot())
        return slots

    def session_order_keys(self, session: dict[str, Any]) -> list[str]:
        try:
            hwnd = int(session.get("hwnd", 0))
        except (AttributeError, TypeError, ValueError):
            hwnd = 0
        label = str(session.get("nom", "")).strip() if isinstance(session, dict) else ""
        short_name = clean_auto_group_name(label)
        keys = [normalize_key(label), normalize_key(short_name)]
        if hwnd > 0:
            keys.append(f"hwnd:{hwnd}")
        seen = set()
        return [key for key in keys if key and not (key in seen or seen.add(key))]

    def saved_session_order_map(self) -> dict[str, int]:
        return {
            key: index
            for index, key in enumerate(
                self.character_order_service.load_order()[:SESSION_SLOT_COUNT]
            )
        }

    def apply_saved_session_order(self, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.build_session_slots(sessions)

    def persisted_session_order_key(self, session: dict[str, Any]) -> str:
        if session_is_empty(session):
            return ""
        short_name = normalize_key(clean_auto_group_name(session_name(session)))
        if short_name:
            return short_name
        for key in self.session_order_keys(session):
            if key and not key.startswith("hwnd:"):
                return key
        return ""

    def save_session_order(self) -> None:
        order = [
            self.persisted_session_order_key(session)
            for session in self.sessions
            if session_is_detected(session)
        ]
        if not order:
            return
        self.character_order_service.save_labels(order)
        self.profiles[KEY_SESSION_ORDER] = list(self.character_order_service.load_order())

    def restyle_button(self, button: QPushButton) -> None:
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def toggle_profile_bool(self, key: str) -> None:
        self.set_profile_bool(key, not profile_bool(self.profiles, key, False))

    def set_profile_bool(self, key: str, value: bool) -> None:
        self.profiles[key] = bool(value)
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_switch_buttons()
        self.update_debug_button()
        self.reload_runtime_callback()

    def toggle_debug_mode(self) -> None:
        enabled = not profile_bool(self.profiles, KEY_DEBUG_MODE, False)
        self.profiles[KEY_DEBUG_MODE] = enabled
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_debug_button()
        invoke_compatible_callback(self.reload_runtime_callback, True)
        self.status_callback(
            "Debug actif: logs runtime detailles."
            if enabled
            else "Debug inactif: logs runtime alleges."
        )

    def hotkey_label(self, key: str) -> str:
        return str(self.profiles.get(key) or "").strip().upper()

    def slot_hotkey_label(self, slot_index: int) -> str:
        return self.hotkey_label(client_slot_hotkey_key(slot_index))

    def client_hotkey_owner(self, hotkey: str, exclude_slot: int | None = None) -> str:
        value = str(hotkey or "").strip().upper()
        if not value:
            return ""
        for slot_index in range(SESSION_SLOT_COUNT):
            if exclude_slot is not None and slot_index == exclude_slot:
                continue
            if self.slot_hotkey_label(slot_index) == value:
                return f"Personnage {slot_index + 1}"
        return ""

    def global_hotkey_owner(self, hotkey: str) -> str:
        value = str(hotkey or "").strip().upper()
        if not value:
            return ""
        for key, label in (
            (KEY_CLICK_HOTKEY, "Switch Clique"),
            (KEY_DOUBLE_CLICK_HOTKEY, "Switch clic x2"),
            (KEY_STOP_SCRIPT_HOTKEY, "Stop script"),
        ):
            if value == self.hotkey_label(key):
                return label
        return ""

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

    def script_speed(self) -> str:
        speed = str(self.profiles.get(KEY_SCRIPT_SPEED, "normal")).strip().casefold()
        return "rapide" if speed in ("rapide", "fast") else "normal"

    def set_script_speed(self, speed: str) -> None:
        resolved = "rapide" if str(speed).strip().casefold() in ("rapide", "fast") else "normal"
        self.profiles[KEY_SCRIPT_SPEED] = resolved
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_script_speed_buttons()
        self.reload_runtime_callback()
        label = "Rapide" if resolved == "rapide" else "Normal"
        self.status_callback(f"Vitesse script : {label}.")

    def update_script_speed_buttons(self) -> None:
        speed = self.script_speed()
        for button, value in (
            (self.script_speed_normal, "normal"),
            (self.script_speed_fast, "rapide"),
        ):
            button.setObjectName("segmentedButtonActive" if speed == value else "segmentedButton")
            self.restyle_button(button)

    def update_debug_button(self) -> None:
        enabled = profile_bool(self.profiles, KEY_DEBUG_MODE, False)
        self.debug_button.setObjectName("primaryButton" if enabled else "secondaryButton")
        self.debug_button.setToolTip(
            "Debug actif: logs runtime detailles"
            if enabled
            else "Debug inactif: logs runtime allegees"
        )
        self.restyle_button(self.debug_button)

    def stop_script(self) -> None:
        if callable(self.stop_runtime_callback):
            self.stop_runtime_callback()
        else:
            self.status_callback("Stop urgence indisponible.")

    def primary_session(self) -> dict[str, Any] | None:
        primary = str(self.profiles.get(KEY_PRIMARY_WINDOW, ""))
        if not primary:
            return None
        primary_matched = False
        for slot_index, session in enumerate(self.sessions):
            name = session_name(session)
            hwnd = session_hwnd(session)
            if not name or hwnd <= 0:
                continue
            if self.session_is_primary(name, hwnd, primary):
                if primary.startswith("hwnd:") or not primary_matched:
                    return session
                primary_matched = True
        return None

    def launch_auto_group(self) -> None:
        self.capture_target = None
        invite_names = []
        seen = set()
        for slot_index, session in enumerate(self.sessions):
            if not session_is_detected(session):
                continue
            name = clean_auto_group_name(session.get("nom", ""))
            key = normalize_key(name)
            if not name or key in seen:
                continue
            seen.add(key)
            invite_names.append({"name": name, "handle": session_hwnd(session)})
        if not invite_names:
            self.status_callback("Auto-groupe ignoré: aucun personnage détecté.")
            return
        self.export_client_index()
        if callable(self.launch_auto_group_callback):
            self.launch_auto_group_callback(invite_names)
        else:
            self.status_callback("Runtime Python indisponible.")
            return
        self.status_callback(f"Auto-groupe lancé: {len(invite_names)} invitation(s).")

    def clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self.clear_layout(child_layout)

    def scan_sessions(self) -> None:
        if os.name != "nt":
            self.status_callback("Scan sessions disponible seulement sous Windows.")
            return
        self.capture_target = None
        self.sessions = self.build_session_slots(scan_unity_sessions())
        self.export_client_index()
        self.request_sessions_render()
        self.sync_event_watcher_sessions()
        self.notify_sessions_changed()
        self.begin_release_identity_retries()
        detected_count = self.detected_session_count()
        if detected_count:
            self.status_callback(f"{detected_count} session(s) Unity détectée(s).")
            self.reload_runtime_callback()
        else:
            self.status_callback("Aucune session Unity détectée.")

    def auto_scan_sessions_on_startup(self) -> None:
        if os.name != "nt":
            return

        previous_count = self.detected_session_count()
        scanned = self.refresh_sessions_and_export(render=True)
        if scanned:
            self.status_callback(f"{self.detected_session_count()} session(s) Unity détectée(s) au lancement.")
            self.reload_runtime_callback()

        self.begin_release_identity_retries()
        if not scanned and previous_count:
            self.status_callback(f"{previous_count} session(s) conservee(s) depuis le dernier scan.")

    def refresh_sessions_from_window_event(self) -> None:
        if os.name != "nt":
            return
        previous_signature = self.session_identity_signature()
        self.profiles = self.load_profiles()
        self.sessions = self.build_session_slots(scan_unity_sessions())
        changed = self.session_identity_signature() != previous_signature
        if changed:
            self.export_client_index()
            self.request_sessions_render()
            self.notify_sessions_changed()
        self.sync_event_watcher_sessions()
        self.begin_release_identity_retries()

    def begin_release_identity_retries(self) -> None:
        self.release_retry_timer.stop()
        self.release_retry_index = 0
        if self.sessions_have_generic_names():
            self.schedule_next_release_identity_retry()

    def schedule_next_release_identity_retry(self) -> None:
        if self.release_retry_index >= len(RELEASE_RETRY_DELAYS_MS):
            return
        delay_ms = RELEASE_RETRY_DELAYS_MS[self.release_retry_index]
        self.release_retry_index += 1
        self.release_retry_timer.start(delay_ms)

    def retry_release_identity(self) -> None:
        if os.name != "nt" or not self.sessions_have_generic_names():
            return
        previous_signature = self.session_identity_signature()
        self.sessions = self.build_session_slots(scan_unity_sessions())
        changed = self.session_identity_signature() != previous_signature
        if changed:
            self.export_client_index()
            self.request_sessions_render()
            self.notify_sessions_changed()
        self.sync_event_watcher_sessions()
        if self.sessions_have_generic_names():
            self.schedule_next_release_identity_retry()

    def sessions_have_generic_names(self) -> bool:
        detected = [session for session in self.sessions if session_is_detected(session)]
        if not detected:
            return False
        return any(is_generic_dofus_client_name(session_name(session)) for session in detected)

    def reload_runtime(self) -> None:
        self.capture_target = None
        self.refresh_sessions_and_export(render=True)
        invoke_compatible_callback(self.reload_runtime_callback, True)
        detected_count = self.detected_session_count()
        if detected_count:
            self.status_callback(f"Raccourcis Python recharges: {detected_count} session(s) Unity.")
        else:
            self.status_callback("Raccourcis Python recharges: aucune session Unity detectee.")

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
        self.clear_layout(self.sessions_layout)
        self.session_row_widgets = []
        self.session_slot_widgets = []
        self.sessions_grid = None
        self.sessions_placeholder = None
        primary = str(self.profiles.get(KEY_PRIMARY_WINDOW, ""))
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        self.sessions_grid = grid
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
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
                grid.addWidget(slot, index // 2, index % 2)
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
            grid.addWidget(row, index // 2, index % 2)
            row.setCursor(Qt.OpenHandCursor)
            self.bind_session_drag_events(row, index, row)
            self.session_row_widgets.append((row, index))
            self.session_slot_widgets.append((row, index))
        self.sessions_layout.addWidget(grid_host)
        self.sessions_layout.addStretch(1)
        self._sessions_render_dirty = False

    def base_session_slot_object_name(self, index: int) -> str:
        if index < 0 or index >= len(self.sessions):
            return "characterSlotEmpty"
        session = self.sessions[index]
        if session_is_empty(session):
            return "characterSlotEmpty"
        return "characterSlot" if session_is_detected(session) else "characterSlotMissing"

    def set_session_row_state(self, row: QWidget, object_name: str) -> None:
        row.setObjectName(object_name)
        row.style().unpolish(row)
        row.style().polish(row)
        row.update()

    def bind_session_drag_events(self, widget: QWidget, index: int, row: QWidget) -> None:
        widget._atlas_drag_index = index
        widget._atlas_drag_row = row
        widget.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        index = getattr(watched, "_atlas_drag_index", None)
        row = getattr(watched, "_atlas_drag_row", None)
        if index is None or row is None:
            return super().eventFilter(watched, event)

        event_type = event.type()
        if event_type == QEvent.MouseButtonPress:
            if hasattr(event, "button") and event.button() == Qt.LeftButton:
                self.prepare_session_drag(index, row, event)
            return False

        if event_type == QEvent.MouseMove:
            if not hasattr(event, "buttons") or not (event.buttons() & Qt.LeftButton):
                return False
            if self.drag_session_index is None:
                if self.drag_pending_index != index or self.drag_start_global is None:
                    return False
                global_point = self.event_global_point(event)
                self.drag_last_global = global_point
                if (global_point - self.drag_start_global).manhattanLength() < 3:
                    return False
                self.begin_session_drag(index, row, None)
            self.update_session_drag_hover(event)
            return True

        if event_type == QEvent.MouseButtonRelease:
            if hasattr(event, "button") and event.button() == Qt.LeftButton:
                if self.drag_session_index is not None:
                    self.finish_session_drag(event)
                    return True
                self.clear_session_drag_pending()
            return False

        return super().eventFilter(watched, event)

    def event_global_point(self, event) -> QPoint:
        try:
            return event.globalPosition().toPoint()
        except AttributeError:
            return event.globalPos()

    def prepare_session_drag(self, index: int, row: QWidget, event) -> None:
        if index < 0 or index >= len(self.sessions) or session_is_empty(self.sessions[index]):
            return
        self.drag_pending_index = index
        self.drag_pending_row = row
        self.drag_start_global = self.event_global_point(event)
        self.drag_last_global = self.drag_start_global
        self.set_session_row_state(row, "characterSlotDragging")

    def clear_session_drag_pending(self) -> None:
        if self.drag_session_index is None and self.drag_pending_row is not None:
            try:
                index = self.drag_pending_index if self.drag_pending_index is not None else 0
                self.set_session_row_state(self.drag_pending_row, self.base_session_slot_object_name(index))
            except RuntimeError:
                pass
        self.drag_pending_index = None
        self.drag_pending_row = None
        self.drag_start_global = None

    def session_drag_key(self, session: dict[str, Any]) -> str:
        try:
            hwnd = int(session.get("hwnd", 0))
        except (AttributeError, TypeError, ValueError):
            hwnd = 0
        name = str(session.get("nom", "")).strip() if isinstance(session, dict) else ""
        return f"hwnd:{hwnd}" if hwnd > 0 else f"name:{name}"

    def current_drag_session_index(self) -> int | None:
        if self.drag_session_key:
            for index, session in enumerate(self.sessions):
                if self.session_drag_key(session) == self.drag_session_key:
                    return index
        if self.drag_session_index is not None and 0 <= self.drag_session_index < len(self.sessions):
            return self.drag_session_index
        return None

    def begin_session_drag(self, index: int, row: QWidget, event) -> None:
        if event is not None and hasattr(event, "button") and event.button() != Qt.LeftButton:
            event.ignore()
            return
        if index < 0 or index >= len(self.sessions) or session_is_empty(self.sessions[index]):
            return
        if event is not None:
            self.drag_last_global = self.event_global_point(event)
        if self.drag_last_global is None:
            self.drag_last_global = row.mapToGlobal(QPoint(row.width() // 2, row.height() // 2))
        self.drag_session_index = index
        self.drag_session_row = row
        self.drag_session_key = self.session_drag_key(self.sessions[index])
        self.drag_session_moved = False
        self.drag_drop_index = None
        self.drag_hover_index = None
        self.set_session_row_state(row, "characterSlotDragging")
        self.show_session_drag_ghost(row, self.drag_last_global)
        row.raise_()
        row.setCursor(Qt.ClosedHandCursor)
        row.grabMouse()
        if event is not None:
            event.accept()

    def update_session_drag_hover(self, event) -> None:
        if self.drag_session_index is None:
            return
        global_point = self.event_global_point(event)
        self.drag_last_global = global_point
        self.move_session_drag_ghost(global_point)
        target_index = self.session_drop_index(global_point)
        self.drag_drop_index = target_index
        self.drag_hover_index = target_index
        if self.drag_hover_index == self.current_drag_session_index():
            self.drag_hover_index = None
        self.restyle_drag_rows()
        if event is not None:
            event.accept()

    def session_hover_index(self, global_point: QPoint) -> int | None:
        for slot, index in self.session_slot_widgets:
            local = slot.mapFromGlobal(global_point)
            if slot.rect().contains(local):
                return index
        return None

    def show_session_drag_ghost(self, row: QWidget, global_point: QPoint) -> None:
        self.clear_session_drag_ghost()
        pixmap = row.grab()
        ghost = QLabel()
        ghost.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        ghost.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        ghost.setAttribute(Qt.WA_ShowWithoutActivating, True)
        ghost.setPixmap(pixmap)
        ghost.resize(pixmap.size())
        ghost.setWindowOpacity(0.72)
        self.drag_ghost = ghost
        self.drag_ghost_offset = global_point - row.mapToGlobal(QPoint(0, 0))
        self.move_session_drag_ghost(global_point)
        ghost.show()
        ghost.raise_()

    def move_session_drag_ghost(self, global_point: QPoint) -> None:
        if self.drag_ghost is None:
            return
        self.drag_ghost.move(global_point - self.drag_ghost_offset)

    def clear_session_drag_ghost(self) -> None:
        if self.drag_ghost is None:
            return
        try:
            self.drag_ghost.close()
            self.drag_ghost.deleteLater()
        except RuntimeError:
            pass
        self.drag_ghost = None
        self.drag_ghost_offset = QPoint(0, 0)

    def move_dragged_session_to_drop_index(self, target_index: int | None) -> bool:
        if target_index is None:
            return False
        source_index = self.current_drag_session_index()
        if source_index is None:
            return False
        target_index = max(0, min(target_index, self.session_slot_count() - 1))
        if not self.move_session_to_slot(source_index, target_index):
            self.drag_session_index = source_index
            return False
        self.drag_session_index = target_index
        self.drag_session_moved = True
        self.render_sessions()
        return True

    def reflow_session_rows(self) -> None:
        if self.sessions_grid is None:
            return
        for widget, index in self.session_slot_widgets:
            self.sessions_grid.removeWidget(widget)
            self.sessions_grid.addWidget(widget, index // 2, index % 2)
        self.sessions_content.updateGeometry()
        self.sessions_content.update()

    def restyle_drag_rows(self) -> None:
        for widget, index in self.session_slot_widgets:
            if index == self.drag_session_index and not session_is_empty(self.sessions[index]):
                object_name = "characterSlotDragging"
            elif index == self.drag_hover_index:
                object_name = "characterSlotDropTarget"
            else:
                object_name = self.base_session_slot_object_name(index)
            self.set_session_row_state(widget, object_name)

    def clear_session_drag_visuals(self) -> None:
        self.clear_session_drag_ghost()
        if self.drag_session_row is not None:
            try:
                self.drag_session_row.releaseMouse()
            except RuntimeError:
                pass
            try:
                self.drag_session_row.setCursor(Qt.OpenHandCursor)
            except RuntimeError:
                pass
        for widget, index in self.session_slot_widgets:
            self.set_session_row_state(widget, self.base_session_slot_object_name(index))
        self.drag_session_index = None
        self.drag_session_row = None
        self.drag_session_key = None
        self.drag_session_moved = False
        self.drag_drop_index = None
        self.drag_hover_index = None
        self.drag_pending_index = None
        self.drag_pending_row = None
        self.drag_start_global = None
        self.drag_last_global = None

    def finish_session_drag(self, event) -> None:
        if self.drag_session_index is None:
            return
        if event is not None:
            self.update_session_drag_hover(event)
        source_index = self.current_drag_session_index()
        target_index = self.drag_drop_index
        moved_live = self.drag_session_moved
        self.clear_session_drag_visuals()
        if moved_live:
            self.export_client_index()
            self.render_sessions()
            self.notify_sessions_changed()
            self.status_callback("Ordre des personnages mis à jour.")
        elif source_index is not None and target_index is not None:
            self.reorder_session(source_index, target_index)
        if event is not None:
            event.accept()

    def session_drop_index(self, global_point: QPoint) -> int | None:
        if not self.session_slot_widgets:
            return None
        ordered_slots = sorted(self.session_slot_widgets, key=lambda entry: entry[1])
        for slot, index in ordered_slots:
            local = slot.mapFromGlobal(global_point)
            if slot.rect().contains(local):
                return index
        return self.nearest_session_drop_index(global_point, ordered_slots)

    def nearest_session_drop_index(self, global_point: QPoint, slots: list[tuple[QWidget, int]] | None = None) -> int | None:
        ordered_slots = slots if slots is not None else sorted(self.session_slot_widgets, key=lambda entry: entry[1])
        if not ordered_slots:
            return None
        return min(
            ordered_slots,
            key=lambda entry: (
                global_point - entry[0].mapToGlobal(entry[0].rect().center())
            ).manhattanLength(),
        )[1]

    def move_session_to_slot(self, source_index: int, target_index: int) -> bool:
        while len(self.sessions) < SESSION_SLOT_COUNT:
            self.sessions.append(empty_session_slot())
        if source_index < 0 or source_index >= len(self.sessions):
            return False
        target_index = max(0, min(target_index, len(self.sessions) - 1))
        if target_index == source_index or session_is_empty(self.sessions[source_index]):
            return False
        session = self.sessions[source_index]
        if session_is_empty(self.sessions[target_index]):
            self.sessions[target_index] = session
            self.sessions[source_index] = empty_session_slot()
            return True
        self.sessions[source_index], self.sessions[target_index] = self.sessions[target_index], session
        return True

    def reorder_session(self, source_index: int, target_index: int) -> None:
        if not self.move_session_to_slot(source_index, target_index):
            return
        self.save_session_order()
        self.export_client_index()
        self.render_sessions()
        self.notify_sessions_changed()
        self.status_callback("Ordre des personnages mis à jour.")

    def primary_token_for_session(self, name: str, hwnd: int) -> str:
        return f"hwnd:{hwnd}" if hwnd > 0 else name

    def session_is_primary(self, name: str, hwnd: int, primary: str) -> bool:
        if not primary:
            return False
        if hwnd > 0 and primary == self.primary_token_for_session(name, hwnd):
            return True
        return primary == name

    def set_primary_window(self, session: dict[str, Any] | str) -> None:
        current = str(self.profiles.get(KEY_PRIMARY_WINDOW, ""))
        if isinstance(session, dict):
            name = str(session.get("nom", "Session"))
            try:
                hwnd = int(session.get("hwnd", 0))
            except (TypeError, ValueError):
                hwnd = 0
            token = self.primary_token_for_session(name, hwnd)
        else:
            name = str(session)
            token = name
        self.profiles[KEY_PRIMARY_WINDOW] = "" if current == token else token
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.render_sessions()
        self.status_callback(f"Fenêtre principale : {name}")

    def remove_client_hotkey(self, slot_index: int) -> None:
        self.profiles.pop(client_slot_hotkey_key(slot_index), None)
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.render_sessions()
        self.status_callback(f"Raccourci supprimé pour personnage {slot_index + 1}.")

    def clear_global_hotkey(self, key: str) -> None:
        self.profiles.pop(key, None)
        if key == KEY_CLICK_HOTKEY:
            self.profiles[KEY_SWITCH_CLICK] = False
        elif key == KEY_DOUBLE_CLICK_HOTKEY:
            self.profiles[KEY_SWITCH_DOUBLE_CLICK] = False
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_switch_buttons()
        self.update_global_buttons()
        self.reload_runtime_callback()
        self.status_callback("Raccourci supprimé.")

    def begin_capture(self, kind: str, name: str | None = None, slot: int | None = None, button: QPushButton | None = None) -> None:
        self.capture_target = {"kind": kind, "name": name, "slot": slot, "button": button}
        if button is not None:
            button.setText("...")
        elif kind == "click":
            self.click_button.setText("...")
        elif kind == "double_click":
            self.double_click_button.setText("...")
        elif kind == "stop_script":
            self.stop_script_hotkey_button.setText("...")
        self.setFocus(Qt.ShortcutFocusReason)
        self.status_callback("En attente d'une touche...")

    def keyPressEvent(self, event) -> None:
        if not self.capture_target:
            super().keyPressEvent(event)
            return
        hotkey = key_sequence_to_hotkey(event.key(), event.modifiers())
        target = self.capture_target
        self.capture_target = None
        if not hotkey:
            self.status_callback("Touche ignorée.")
            self.update_global_buttons()
            self.render_sessions()
            return
        kind = target.get("kind")
        if kind == "client" and target.get("slot") is not None:
            slot_index = int(target["slot"])
            owner = self.global_hotkey_owner(hotkey) or self.client_hotkey_owner(hotkey, exclude_slot=slot_index)
            if owner:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci deja utilise par {owner}.")
                return
            self.profiles[client_slot_hotkey_key(slot_index)] = hotkey
        elif kind == "click":
            if hotkey == self.hotkey_label(KEY_DOUBLE_CLICK_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Switch clic x2.")
                return
            if hotkey == self.hotkey_label(KEY_STOP_SCRIPT_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Stop script.")
                return
            owner = self.client_hotkey_owner(hotkey)
            if owner:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci deja utilise par {owner}.")
                return
            self.profiles[KEY_CLICK_HOTKEY] = hotkey
        elif kind == "double_click":
            if hotkey == self.hotkey_label(KEY_CLICK_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Switch Clique.")
                return
            if hotkey == self.hotkey_label(KEY_STOP_SCRIPT_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Stop script.")
                return
            owner = self.client_hotkey_owner(hotkey)
            if owner:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci deja utilise par {owner}.")
                return
            self.profiles[KEY_DOUBLE_CLICK_HOTKEY] = hotkey
        elif kind == "stop_script":
            if hotkey == self.hotkey_label(KEY_CLICK_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Switch Clique.")
                return
            if hotkey == self.hotkey_label(KEY_DOUBLE_CLICK_HOTKEY):
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback("Raccourci déjà utilisé par Switch clic x2.")
                return
            owner = self.client_hotkey_owner(hotkey)
            if owner:
                self.update_global_buttons()
                self.render_sessions()
                self.status_callback(f"Raccourci deja utilise par {owner}.")
                return
            self.profiles[KEY_STOP_SCRIPT_HOTKEY] = hotkey
        self.save_profiles(self.profiles)
        self.export_client_index()
        self.update_global_buttons()
        self.render_sessions()
        self.reload_runtime_callback()
        self.status_callback(f"Raccourci {hotkey} enregistré.")

    def export_client_index(self) -> None:
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        self.save_session_order()
        primary_token = str(self.profiles.get(KEY_PRIMARY_WINDOW, ""))
        primary_label = ""
        primary_handle = 0
        used_client_bindings: set[str] = set()
        zaap_ratios = read_zaap_button_ratios()
        zaap_ratio_x = format_zaap_ratio(zaap_ratios[0]) if zaap_ratios else ""
        zaap_ratio_y = format_zaap_ratio(zaap_ratios[1]) if zaap_ratios else ""
        click_enabled = profile_bool(self.profiles, KEY_SWITCH_CLICK, False)
        double_click_enabled = profile_bool(self.profiles, KEY_SWITCH_DOUBLE_CLICK, False)
        click_hotkey = str(self.profiles.get(KEY_CLICK_HOTKEY, "")).strip() if click_enabled else ""
        double_click_hotkey = str(self.profiles.get(KEY_DOUBLE_CLICK_HOTKEY, "")).strip() if double_click_enabled else ""
        stop_script_hotkey = str(self.profiles.get(KEY_STOP_SCRIPT_HOTKEY, "")).strip()
        script_speed = self.script_speed()
        debug_enabled = profile_bool(self.profiles, KEY_DEBUG_MODE, False)
        if double_click_enabled and click_hotkey and double_click_hotkey and click_hotkey == double_click_hotkey:
            double_click_enabled = False
            double_click_hotkey = ""
        clients = []
        primary_matched = False
        for slot_index, session in enumerate(self.sessions):
            name = session_name(session)
            hwnd = session_hwnd(session)
            if not name or hwnd <= 0 or session_is_empty(session):
                continue
            client_index = len(clients) + 1
            is_primary = self.session_is_primary(name, hwnd, primary_token)
            if is_primary and not primary_token.startswith("hwnd:"):
                if primary_matched:
                    is_primary = False
                else:
                    primary_matched = True
            if is_primary:
                primary_label = f"Personnage {client_index}"
                primary_handle = hwnd
            binding = self.resolve_client_binding(
                slot_index,
                used_client_bindings,
                {click_hotkey, double_click_hotkey, stop_script_hotkey},
            )
            clients.append(
                {
                    "index": client_index,
                    "label": f"Personnage {client_index}",
                    "name": name,
                    "character_name": clean_auto_group_name(name),
                    "class_key": dofus_class_key_from_window_name(name) or "",
                    "slot": slot_index + 1,
                    "handle": hwnd,
                    "handle_hex": hex(hwnd),
                    "pid": session_pid(session),
                    "binding": binding,
                    "binding_explicit": bool(binding),
                    "primary": is_primary,
                }
            )

        payload = {
            "version": 1,
            "generated_at": timestamp,
            "scan_policy": "startup_and_user_interaction",
            "note": "Index de sessions Unity rafraichi au lancement et par interaction utilisateur.",
            "global_hotkeys": {
                "enabled": profile_bool(self.profiles, KEY_SWITCH_CHARACTER, True),
                "click_enabled": click_enabled,
                "click_hotkey": click_hotkey,
                "double_click_enabled": double_click_enabled,
                "double_click_hotkey": double_click_hotkey,
                "movement_enabled": profile_bool(self.profiles, KEY_SWITCH_MOVEMENT, False),
                "stop_script_hotkey": stop_script_hotkey,
                "script_speed": script_speed,
                "debug_enabled": debug_enabled,
                "zaap_click_x": read_zaap_click_position(self.profiles)[0],
                "zaap_click_y": read_zaap_click_position(self.profiles)[1],
                "zaap_click_x_ratio": zaap_ratio_x,
                "zaap_click_y_ratio": zaap_ratio_y,
                "primary_label": primary_label,
                "primary_handle": primary_handle,
            },
            "count": len(clients),
            "clients": clients,
        }

        lines = [
            "; Genere par session_manager_pyside.py pendant un scan au lancement ou une interaction utilisateur.",
            "; Le Python scanne les fenetres Unity pour alimenter le runtime de macros Python.",
            "[meta]",
            "version=1",
            f"generated_at={timestamp}",
            "scan_policy=startup_and_user_interaction",
            f"count={len(clients)}",
            "",
            "[global_hotkeys]",
            f"enabled={1 if profile_bool(self.profiles, KEY_SWITCH_CHARACTER, True) else 0}",
            f"click_enabled={1 if click_enabled else 0}",
            f"click_hotkey={click_hotkey}",
            f"double_click_enabled={1 if double_click_enabled else 0}",
            f"double_click_hotkey={double_click_hotkey}",
            f"movement_enabled={1 if profile_bool(self.profiles, KEY_SWITCH_MOVEMENT, False) else 0}",
            f"stop_script_hotkey={stop_script_hotkey}",
            f"script_speed={script_speed}",
            f"debug_enabled={1 if debug_enabled else 0}",
            f"zaap_click_x={read_zaap_click_position(self.profiles)[0]}",
            f"zaap_click_y={read_zaap_click_position(self.profiles)[1]}",
            f"zaap_click_x_ratio={zaap_ratio_x}",
            f"zaap_click_y_ratio={zaap_ratio_y}",
            f"primary_label={primary_label}",
            f"primary_handle={primary_handle}",
            "",
        ]
        for client in clients:
            lines.extend(
                [
                    f"[client_{client['index']}]",
                    f"label={client['label']}",
                    f"handle={client['handle']}",
                    f"handle_hex={client['handle_hex']}",
                    f"binding={client['binding']}",
                    f"binding_explicit={1 if client['binding_explicit'] else 0}",
                    f"primary={1 if client['primary'] else 0}",
                    "",
                ]
            )
        write_json(CLIENT_INDEX_JSON, payload)
        write_text_atomic(CLIENT_INDEX_INI, "\n".join(lines) + "\n")

    def resolve_client_binding(
        self,
        slot_index: int,
        used_bindings: set[str],
        reserved_bindings: set[str],
    ) -> str:
        reserved = {str(binding or "").strip().upper() for binding in reserved_bindings if str(binding or "").strip()}
        binding = self.slot_hotkey_label(slot_index)
        if not binding or binding in reserved or binding in used_bindings:
            return ""
        used_bindings.add(binding)
        return binding
