from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QWidget

from app.constants import (
    CLIENT_INDEX_INI,
    CLIENT_INDEX_JSON,
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
from app.services.character_order_service import CharacterOrderService
from app.services.profile_settings_service import ProfileSettingsService
from app.storage import clean_auto_group_name, default_profiles, normalize_key, read_json
from app.windows_embed import UnityWindowEventWatcher, scan_unity_sessions
from app.pages.organizer.character_sessions import CharacterSessionsMixin
from app.pages.organizer.common import (
    BUTTON_HEIGHT,
    CARD_PADDING,
    CARD_SPACING,
    CHARACTER_SLOT_HEIGHT,
    CLASS_ICON_DIRS,
    CLASS_ICON_EXTENSIONS,
    DOFUS_CLASS_DEFINITIONS,
    RELEASE_RETRY_DELAYS_MS,
    SESSION_SLOT_COUNT,
    WINDOW_EVENT_DEBOUNCE_MS,
    client_slot_hotkey_key,
    dofus_class_key_from_window_name,
    empty_session_slot,
    session_hwnd,
    session_is_detected,
    session_is_empty,
    session_name,
    session_pid,
)
from app.pages.organizer.organizer_drag_drop import OrganizerDragDropMixin
from app.pages.organizer.organizer_hotkeys import OrganizerHotkeysMixin
from app.pages.organizer.organizer_ui import OrganizerUiMixin


def dofus_class_key_for_character_name(value: Any) -> str | None:
    """Resolve a character class through the compatibility index path."""

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
        if normalize_key(client.get("character_name")) != character_key:
            continue
        explicit_class = normalize_key(client.get("class_key"))
        if explicit_class in DOFUS_CLASS_DEFINITIONS:
            matches.add(explicit_class)
            continue
        inferred_class = dofus_class_key_from_window_name(client.get("name"))
        if inferred_class:
            matches.add(inferred_class)
    return next(iter(matches)) if len(matches) == 1 else None


def class_icon_candidates(class_key: str) -> list[Path]:
    """Build class icon candidates from the public compatibility directories."""

    definition = DOFUS_CLASS_DEFINITIONS.get(class_key)
    if not definition:
        return []
    class_id = definition["id"]
    stems: list[str] = []
    for value in (class_key, definition["label"], *definition["aliases"]):
        key = normalize_key(value)
        if key and key not in stems:
            stems.append(key)
    stems.extend([f"symbol_{class_id}", f"logo_transparent_{class_id}", f"class_{class_key}"])
    return [
        directory / f"{stem}{extension}"
        for directory in CLASS_ICON_DIRS
        for stem in stems
        for extension in CLASS_ICON_EXTENSIONS
    ]


def class_icon_path_for_window_name(value: Any) -> Path | None:
    class_key = dofus_class_key_from_window_name(value) or dofus_class_key_for_character_name(value)
    if not class_key:
        return None
    return next((path for path in class_icon_candidates(class_key) if path.exists()), None)


class OrganizerPage(
    OrganizerUiMixin,
    CharacterSessionsMixin,
    OrganizerDragDropMixin,
    OrganizerHotkeysMixin,
    QWidget,
):
    """Organizer entry point: state/orchestration only; UI and behaviours live in focused modules."""

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
    ) -> None:
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

        # Keep runtime dependencies explicit while resolving the historical
        # module-level scan hook at call time. Existing shell tests and tools
        # patch organizer_page.scan_unity_sessions dynamically.
        self.profile_file = PROFILE_FILE
        self.client_index_json = CLIENT_INDEX_JSON
        self.client_index_ini = CLIENT_INDEX_INI
        self.scan_unity_sessions_callback = lambda: scan_unity_sessions()

        self.character_order_service = CharacterOrderService(self.profile_file)
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
        self.sessions_grid = None
        self.sessions_placeholder: QWidget | None = None
        self.setFocusPolicy(Qt.StrongFocus)

        self.build_organizer_ui(status_callback, launch_zaap_callback)
        self._connect_actions()
        self.update_switch_buttons()
        self.update_global_buttons()
        self.update_script_speed_buttons()
        self.update_debug_button()
        self.export_client_index()
        self.request_sessions_render()
        self._start_session_runtime()

    def load_profiles(self) -> dict[str, Any]:
        """Compatibility facade kept on OrganizerPage for callers and AST contracts."""

        payload = read_json(PROFILE_FILE, default_profiles())
        if not isinstance(payload, dict):
            payload = default_profiles()
        merged = default_profiles()
        merged.update(payload)
        cleaned = self.sanitize_profiles(merged)
        cleaned[KEY_SESSION_ORDER] = list(self.character_order_service.load_order())
        self._profiles_baseline = dict(cleaned)
        return cleaned

    def save_profiles(self, payload: dict[str, Any]) -> None:
        """Persist only the Organizer delta while preserving newer shared state."""

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

    def _connect_actions(self) -> None:
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

    def _start_session_runtime(self) -> None:
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


__all__ = [
    "OrganizerPage",
    "PROFILE_FILE",
    "CLIENT_INDEX_JSON",
    "CLIENT_INDEX_INI",
    "KEY_DEBUG_MODE",
    "KEY_PRIMARY_WINDOW",
    "KEY_SCRIPT_SPEED",
    "KEY_SESSION_ORDER",
    "KEY_TRAVEL_TEXT",
    "RELEASE_RETRY_DELAYS_MS",
    "SESSION_SLOT_COUNT",
    "BUTTON_HEIGHT",
    "CARD_PADDING",
    "CARD_SPACING",
    "CHARACTER_SLOT_HEIGHT",
    "CLASS_ICON_DIRS",
    "CLASS_ICON_EXTENSIONS",
    "DOFUS_CLASS_DEFINITIONS",
    "client_slot_hotkey_key",
    "clean_auto_group_name",
    "default_profiles",
    "dofus_class_key_from_window_name",
    "dofus_class_key_for_character_name",
    "class_icon_candidates",
    "class_icon_path_for_window_name",
    "empty_session_slot",
    "scan_unity_sessions",
    "session_name",
    "session_hwnd",
    "session_pid",
    "session_is_empty",
    "session_is_detected",
]
