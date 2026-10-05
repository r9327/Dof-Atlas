from __future__ import annotations

import os
from typing import Any

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtWidgets import QLabel, QWidget

from app.constants import (
    KEY_CLICK_HOTKEY,
    KEY_DOUBLE_CLICK_HOTKEY,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_SWITCH_CHARACTER,
    KEY_SWITCH_CLICK,
    KEY_SWITCH_DOUBLE_CLICK,
    KEY_SWITCH_MOVEMENT,
    PROFILE_FILE,
)
from app.services.character_order_service import CharacterOrderService
from app.windows_embed import UnityWindowEventWatcher
from app.pages.organizer.character_sessions import CharacterSessionsMixin
from app.pages.organizer.common import (
    BUTTON_HEIGHT,
    CARD_PADDING,
    CARD_SPACING,
    CHARACTER_SLOT_HEIGHT,
    SESSION_SLOT_COUNT,
    WINDOW_EVENT_DEBOUNCE_MS,
    client_slot_hotkey_key,
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
    "SESSION_SLOT_COUNT",
    "BUTTON_HEIGHT",
    "CARD_PADDING",
    "CARD_SPACING",
    "CHARACTER_SLOT_HEIGHT",
    "client_slot_hotkey_key",
    "empty_session_slot",
    "session_name",
    "session_hwnd",
    "session_pid",
    "session_is_empty",
    "session_is_detected",
]
