from __future__ import annotations

import os
from pathlib import Path
from threading import Thread
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame

from app.constants import (
    CLIENT_INDEX_INI,
    CLIENT_INDEX_JSON,
    KEY_SESSION_ORDER,
    LOGGER,
    PROFILE_FILE,
    ZAAP_SHORTCUTS_FILE,
)
from app.pages import organizer_page as _organizer_module
from app.pages.organizer_icon_cache import preserve_verified_character_classes
from app.pages.organizer_page import OrganizerPage as _EagerOrganizerPage
from app.services.profile_settings_service import ProfileSettingsService
from app.startup_timing import startup_mark
from app.storage import default_profiles


class OrganizerPage(_EagerOrganizerPage):
    """Keep Organizer tracking eager while deferring hidden/redundant work.

    Session tracking, exports and the WinEvent watcher stay active from startup so
    the shell and runtime always receive current Unity sessions. Expensive Qt
    paint work is deferred while Organizer is hidden, repeated client-index
    exports are skipped when their inputs are unchanged, and automatic Win32
    scans run outside the Qt UI thread.
    """

    sessionScanFinished = Signal(object)

    _SCAN_PRIORITY = {
        "release_retry": 1,
        "window_event": 2,
        "startup": 3,
        "manual": 4,
    }

    def __init__(self, *args, **kwargs) -> None:
        startup_mark("organizer_construct_start")
        self._sessions_render_dirty = True
        self._controls_render_dirty = True
        self._runtime_status_dirty = True
        self._runtime_status_value = False
        self._pending_shadow_frames: list[QFrame] = []
        self._last_client_export_signature: tuple[object, ...] | None = None
        self._scan_in_flight = False
        self._pending_scan_mode = ""
        self._reuse_scanned_sessions_once = False
        self.profile_settings_service = ProfileSettingsService(PROFILE_FILE)
        self._profile_persisted_snapshot: dict[str, Any] = {}
        super().__init__(*args, **kwargs)
        self.sessionScanFinished.connect(self._apply_async_scan_result)
        startup_mark("organizer_construct_ready")

    def load_profiles(self) -> dict[str, Any]:
        payload = self.profile_settings_service.load(default_profiles())
        merged = default_profiles()
        merged.update(payload)
        cleaned = self.sanitize_profiles(merged)
        cleaned[KEY_SESSION_ORDER] = list(self.character_order_service.load_order())
        self._profile_persisted_snapshot = dict(cleaned)
        return cleaned

    def save_profiles(self, payload: dict[str, Any]) -> None:
        """Persist only Organizer-owned changes from its local snapshot.

        The page keeps ``self.profiles`` for UI/runtime reads. It can live for a
        long time, so writing that complete dictionary would be a stale-snapshot
        lost-update hazard. Compare it with the last Organizer snapshot, then
        replay only the keys actually changed by Organizer on the latest disk
        profile through the coordinated profile store. Character order is
        excluded because CharacterOrderService owns that key canonically.
        """

        snapshot = dict(payload)
        baseline = dict(getattr(self, "_profile_persisted_snapshot", {}) or {})
        excluded = {KEY_SESSION_ORDER}
        sentinel = object()
        updates: dict[str, Any] = {}
        removals: list[str] = []

        for key in set(baseline) | set(snapshot):
            if key in excluded:
                continue
            before = baseline.get(key, sentinel)
            after = snapshot.get(key, sentinel)
            if before == after:
                continue
            if after is sentinel:
                removals.append(str(key))
            else:
                updates[str(key)] = after

        saved, _changed = self.profile_settings_service.update_values(
            updates,
            remove_keys=removals,
            default=default_profiles(),
        )
        merged = default_profiles()
        merged.update(saved)
        cleaned = self.sanitize_profiles(merged)
        cleaned[KEY_SESSION_ORDER] = list(self.character_order_service.load_order())
        self.profiles = cleaned
        self._profile_persisted_snapshot = dict(cleaned)

    @staticmethod
    def _freeze_signature(value: Any) -> object:
        if isinstance(value, dict):
            return tuple(
                sorted(
                    (str(key), OrganizerPage._freeze_signature(nested))
                    for key, nested in value.items()
                )
            )
        if isinstance(value, (list, tuple)):
            return tuple(OrganizerPage._freeze_signature(item) for item in value)
        if isinstance(value, set):
            return tuple(sorted(OrganizerPage._freeze_signature(item) for item in value))
        return value

    @staticmethod
    def _file_stamp(path: Path) -> tuple[int, int]:
        try:
            stat = path.stat()
        except OSError:
            return (0, 0)
        return (int(stat.st_mtime_ns), int(stat.st_size))

    def _client_export_signature(self) -> tuple[object, ...]:
        return (
            self._freeze_signature(getattr(self, "profiles", {})),
            self._freeze_signature(getattr(self, "sessions", [])),
            self._file_stamp(Path(ZAAP_SHORTCUTS_FILE)),
            bool(Path(CLIENT_INDEX_JSON).exists()),
            bool(Path(CLIENT_INDEX_INI).exists()),
        )

    def export_client_index(self) -> None:
        # The eager constructor intentionally clears stale active HWND/PID rows
        # before the async Unity scan. Preserve only already-known class metadata
        # on verified character identities before that safe runtime reset.
        preserve_verified_character_classes(getattr(self, "sessions", []))
        signature = self._client_export_signature()
        if signature == self._last_client_export_signature:
            return
        _EagerOrganizerPage.export_client_index(self)
        # Base export can normalize/save session order, so capture the final
        # state rather than the pre-write signature.
        self._last_client_export_signature = self._client_export_signature()

    def apply_card_shadow(self, frame: QFrame) -> None:
        if not self.isVisible():
            pending = getattr(self, "_pending_shadow_frames", None)
            if not isinstance(pending, list):
                pending = []
                self._pending_shadow_frames = pending
            if frame not in pending:
                pending.append(frame)
            return
        _EagerOrganizerPage.apply_card_shadow(self, frame)

    def render_sessions(self) -> None:
        if not self.isVisible():
            self._sessions_render_dirty = True
            return
        self._sessions_render_dirty = False
        _EagerOrganizerPage.render_sessions(self)

    def _defer_control_refresh_if_hidden(self) -> bool:
        if self.isVisible():
            return False
        self._controls_render_dirty = True
        return True

    def update_switch_buttons(self) -> None:
        if self._defer_control_refresh_if_hidden():
            return
        self._controls_render_dirty = False
        _EagerOrganizerPage.update_switch_buttons(self)

    def update_global_buttons(self) -> None:
        if self._defer_control_refresh_if_hidden():
            return
        self._controls_render_dirty = False
        _EagerOrganizerPage.update_global_buttons(self)

    def update_script_speed_buttons(self) -> None:
        if self._defer_control_refresh_if_hidden():
            return
        self._controls_render_dirty = False
        _EagerOrganizerPage.update_script_speed_buttons(self)

    def update_debug_button(self) -> None:
        if self._defer_control_refresh_if_hidden():
            return
        self._controls_render_dirty = False
        _EagerOrganizerPage.update_debug_button(self)

    def set_runtime_active(self, connected: bool) -> None:
        self._runtime_status_value = bool(connected)
        if not self.isVisible():
            self._runtime_status_dirty = True
            return
        self._runtime_status_dirty = False
        _EagerOrganizerPage.set_runtime_active(self, self._runtime_status_value)

    def _hydrate_hidden_visuals(self) -> None:
        pending = list(getattr(self, "_pending_shadow_frames", ()) or ())
        if hasattr(self, "_pending_shadow_frames"):
            self._pending_shadow_frames.clear()
        for frame in pending:
            if frame.graphicsEffect() is None:
                _EagerOrganizerPage.apply_card_shadow(self, frame)
        if bool(getattr(self, "_controls_render_dirty", False)):
            # The base constructor invokes these independently. One first-show
            # hydration after the global stylesheet exists avoids four groups of
            # hidden unpolish/polish passes during startup.
            _EagerOrganizerPage.update_switch_buttons(self)
            _EagerOrganizerPage.update_global_buttons(self)
            _EagerOrganizerPage.update_script_speed_buttons(self)
            _EagerOrganizerPage.update_debug_button(self)
            self._controls_render_dirty = False
        if bool(getattr(self, "_runtime_status_dirty", False)):
            _EagerOrganizerPage.set_runtime_active(
                self,
                bool(getattr(self, "_runtime_status_value", False)),
            )
            self._runtime_status_dirty = False
        if bool(getattr(self, "_sessions_render_dirty", False)):
            self._sessions_render_dirty = False
            _EagerOrganizerPage.render_sessions(self)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._hydrate_hidden_visuals()

    def _merge_pending_scan_mode(self, mode: str) -> None:
        current = self._pending_scan_mode
        if self._SCAN_PRIORITY.get(mode, 0) >= self._SCAN_PRIORITY.get(current, 0):
            self._pending_scan_mode = mode

    def _shell_is_shutting_down(self) -> bool:
        try:
            window = self.window()
        except RuntimeError:
            return True
        return bool(getattr(window, "quit_requested", False))

    def _request_session_scan(self, mode: str) -> bool:
        if self._shell_is_shutting_down():
            return False
        if os.name != "nt":
            return False
        if self._scan_in_flight:
            self._merge_pending_scan_mode(mode)
            return True

        self._scan_in_flight = True

        def worker() -> None:
            payload: dict[str, object]
            try:
                payload = {
                    "mode": mode,
                    "sessions": _organizer_module.scan_unity_sessions(),
                    "error": "",
                }
            except Exception as exc:
                LOGGER.exception("Scan Unity asynchrone impossible.")
                payload = {
                    "mode": mode,
                    "sessions": [],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            try:
                self.sessionScanFinished.emit(payload)
            except RuntimeError:
                # The page can be destroyed while the app is shutting down.
                pass

        Thread(target=worker, name="DofusAtlasUnityScan", daemon=True).start()
        return True

    def _request_pending_scan_if_needed(self) -> None:
        mode = self._pending_scan_mode
        self._pending_scan_mode = ""
        if mode:
            self._request_session_scan(mode)

    def _apply_async_scan_result(self, payload: object) -> None:
        self._scan_in_flight = False
        if self._shell_is_shutting_down():
            self._pending_scan_mode = ""
            return
        data = payload if isinstance(payload, dict) else {}
        mode = str(data.get("mode") or "window_event")
        error = str(data.get("error") or "")
        sessions = data.get("sessions")
        if error:
            self.status_callback(f"Scan sessions Unity impossible: {error}")
            self._request_pending_scan_if_needed()
            return
        if not isinstance(sessions, list):
            sessions = []

        previous_count = self.detected_session_count()
        previous_signature = self.session_identity_signature()
        self.profiles = self.load_profiles()
        self.sessions = self.build_session_slots(sessions)
        changed = self.session_identity_signature() != previous_signature

        if mode in {"manual", "startup"} or changed:
            self.export_client_index()
            self.render_sessions()
            self.notify_sessions_changed()
        self.sync_event_watcher_sessions()

        if mode == "release_retry":
            if self.sessions_have_generic_names():
                self.schedule_next_release_identity_retry()
        else:
            self.begin_release_identity_retries()

        detected_count = self.detected_session_count()
        if mode == "manual":
            if detected_count:
                self.status_callback(f"{detected_count} session(s) Unity détectée(s).")
                self._reuse_scanned_sessions_once = True
                self.reload_runtime_callback()
            else:
                self.status_callback("Aucune session Unity détectée.")
        elif mode == "startup":
            if detected_count:
                self.status_callback(f"{detected_count} session(s) Unity détectée(s) au lancement.")
                self._reuse_scanned_sessions_once = True
                self.reload_runtime_callback()
            elif previous_count:
                self.status_callback(f"{previous_count} session(s) conservee(s) depuis le dernier scan.")

        self._request_pending_scan_if_needed()

    def refresh_sessions_and_export(self, render: bool = False) -> bool:
        if self._reuse_scanned_sessions_once:
            self._reuse_scanned_sessions_once = False
            self.profiles = self.load_profiles()
            self.export_client_index()
            if render:
                self.render_sessions()
            self.sync_event_watcher_sessions()
            self.notify_sessions_changed()
            return self.detected_session_count() > 0
        return _EagerOrganizerPage.refresh_sessions_and_export(self, render=render)

    def scan_sessions(self) -> None:
        if os.name != "nt":
            self.status_callback("Scan sessions disponible seulement sous Windows.")
            return
        self.capture_target = None
        self.status_callback("Scan des fenêtres Dofus...")
        self._request_session_scan("manual")

    def auto_scan_sessions_on_startup(self) -> None:
        self._request_session_scan("startup")

    def refresh_sessions_from_window_event(self) -> None:
        self._request_session_scan("window_event")

    def retry_release_identity(self) -> None:
        if os.name != "nt" or not self.sessions_have_generic_names():
            return
        self._request_session_scan("release_retry")


__all__ = ["OrganizerPage"]
