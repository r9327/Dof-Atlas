from __future__ import annotations

from functools import lru_cache
from time import monotonic
from typing import Any, Iterable, TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from app.validation_log import record_validation

_PROGRESS_REFRESH_DEBOUNCE_MS = 120
_WINDOW_SCAN_INTERVAL_SECONDS = 2.0


@lru_cache(maxsize=1)
def _live_dofus_sessions(_scan_interval: int) -> tuple[tuple[int, str], ...]:
    from app.macros.mirror_plan import is_dofus_unity_process
    from app.quest_catalog import is_generic_dofus_client_name
    from app.windows_embed import scan_unity_sessions

    sessions = {}
    for row in scan_unity_sessions():
        hwnd = row["hwnd"]
        if is_dofus_unity_process(hwnd):
            title = str(row.get("detected_title") or "")
            sessions[hwnd] = (
                "" if is_generic_dofus_client_name(title) else title
            )
    return tuple(sorted(sessions.items()))


if TYPE_CHECKING:
    from app.network.application_coordinator import NetworkApplicationStatus
    from app.quest_catalog import QuestCatalog


class NetworkUiBridge(QObject):
    """Qt-side adapter around the thread-owned network coordinator.

    Heavy fingerprint/capture bootstrap stays inside NetworkApplicationCoordinator.
    This object only drains queues on the UI thread and emits Qt signals. It owns
    no progression state and keeps the verified network runtime alive while the
    main application is hidden to the tray.
    """

    statusChanged = Signal(object)
    progressChanged = Signal(str)
    characterActivated = Signal(str)
    charactersIdentified = Signal(object)
    connectionsChanged = Signal(object)
    localSessionsChanged = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # Home imports this module before its first paint, but the real bridge is
        # created only after Encyclopedia context or an explicit calibration
        # request. Keep coordinator/settings/catalog imports on that real-use path.
        from app.network.application_coordinator import NetworkApplicationCoordinator
        from app.network.character_runtime_state import character_runtime_state

        self._local_sessions: tuple[str, ...] = ()
        self._published_local_sessions: tuple[str, ...] = ()
        self.coordinator = NetworkApplicationCoordinator(self._window_handles)
        # The decoded transport read model also changes on an entire capture
        # reset or verified recovery, without an individual progress event.
        self._character_runtime_state = character_runtime_state()
        self._observed_network_keys = self._character_runtime_state.connected_character_keys()
        self._context_signature: tuple[int, int, int] | None = None
        self._compact_context_ready = False
        self._last_status = self.coordinator.latest_status()
        self._stopped = False
        self._stop_result: bool | None = None
        self._pending_progress_characters: set[str] = set()
        self._progress_timer = QTimer(self)
        self._progress_timer.setSingleShot(True)
        self._progress_timer.setInterval(_PROGRESS_REFRESH_DEBOUNCE_MS)
        self._progress_timer.timeout.connect(self._emit_pending_progress)
        self._timer = QTimer(self)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    @property
    def last_status(self) -> NetworkApplicationStatus:
        return self._last_status

    def configure_context(
        self,
        *,
        quest_catalog: QuestCatalog,
        achievement_provider: Any,
        guide_provider: Any = None,
    ) -> bool:
        from app.quest_catalog import QuestCatalog

        if self._stopped:
            return False
        if not isinstance(quest_catalog, QuestCatalog) or achievement_provider is None:
            return False
        signature = (id(quest_catalog), id(achievement_provider), id(guide_provider))
        if signature == self._context_signature:
            return True
        self.coordinator.configure_context(
            quest_catalog=quest_catalog,
            achievement_provider=achievement_provider,
            guide_provider=guide_provider,
        )
        self._context_signature = signature
        # The injected provider may be a rich Encyclopedia object. If later
        # released on Home, a compact provider must replace it, not keep it.
        self._compact_context_ready = False
        return True

    def configure_compact_context(self) -> bool:
        """Configure network validation without retaining Encyclopedia catalogues."""

        if self._stopped:
            return False
        if self._compact_context_ready:
            return True
        if getattr(self.coordinator, "worker_compact_context_ready", False) is True:
            # Home already built exactly this compact network context in the
            # existing coordinator worker: no second provider or disk scan.
            self._compact_context_ready = True
            return True
        # The coordinator owns the only cold catalogue constructor. A return
        # to Home must not run its SQLite/index I/O on the GUI thread.
        accepted = self.coordinator.request_configure_compact_context()
        if accepted:
            self._context_signature = None
        return accepted

    def request_calibration(self) -> bool:
        if self._stopped:
            return False
        return self.coordinator.request_start_calibration()

    def prepare_capture(self) -> bool:
        if self._stopped:
            return False
        return self.coordinator.request_prepare_capture()

    def request_verified_runtime(self) -> bool:
        if self._stopped:
            return False
        from app.core.network_presentation import capture_retry_allowed

        if not capture_retry_allowed(self.coordinator.latest_status().reason):
            return False
        # Explicit retry from Home is allowed before visiting Encyclopedia.
        # The coordinator resolves only its compact Quest context off-thread;
        # keep all Qt widgets out of catalogue loading.
        return self.coordinator.request_start_compact_runtime()

    def stop(self) -> bool:
        if self._stopped:
            # A failed cleanup must never become a reported success on the
            # second call (for example via aboutToQuit after window closing).
            return self._stop_result is True
        self._stopped = True
        self._timer.stop()
        self._progress_timer.stop()
        self._pending_progress_characters.clear()
        had_local_sessions = bool(self._published_local_sessions)
        self._local_sessions = self._published_local_sessions = ()
        try:
            stopped = bool(self.coordinator.stop())
        except Exception:
            # An unexpected coordinator cleanup error must leave the UI in a
            # truthful failed state, not abort close before statusChanged.
            from app.core.logger import get_runtime_logger

            get_runtime_logger().exception("Network coordinator shutdown failed.")
            stopped = False
        self._stop_result = stopped
        # The poll timer is stopped too: publish one final truthful state or
        # a previously active Home badge could remain green indefinitely.
        from app.network.application_coordinator import NetworkApplicationStatus

        self._last_status = NetworkApplicationStatus(
            False, False, "stopped" if stopped else "stop_failed",
        )
        if had_local_sessions:
            self.localSessionsChanged.emit(())
        self.statusChanged.emit(self._last_status)
        return stopped

    def _poll(self) -> None:
        if self._stopped:
            return
        local_sessions = self._local_sessions
        if local_sessions != self._published_local_sessions:
            self._published_local_sessions = local_sessions
            self.localSessionsChanged.emit(local_sessions)
            if self._stopped:
                return
        current_network_keys = self._character_runtime_state.connected_character_keys()
        membership_changes = current_network_keys ^ self._observed_network_keys
        self._observed_network_keys = current_network_keys
        pending = self.coordinator.has_pending_ui_events()
        if not pending and not membership_changes:
            return
        statuses = self.coordinator.drain_statuses(50) if pending else ()
        if statuses:
            # The queue is bounded per poll and concurrent publishers may
            # enqueue old notifications after a newer state was committed.
            # Render the authoritative snapshot, not an older queued badge.
            latest = self.coordinator.latest_status()
            # A fast explicit retry can return to the same status in one
            # poll. Refresh Home so it can exit its retry-in-progress state.
            if latest != self._last_status or any(
                status.reason == "network_retry_starting" for status in statuses
            ):
                self._last_status = latest
                self.statusChanged.emit(latest)
            # A direct Qt slot can stop the bridge during this emission.
            # Never consume or publish an older worker event afterwards.
            if self._stopped:
                return
        changed_characters: set[str] = set()
        active_characters: set[str] = set()
        disconnected_characters: set[str] = set()
        for result in (self.coordinator.drain_results(100) if pending else ()):
            reason = str(getattr(result, "reason", "") or "")
            if (
                bool(getattr(result, "accepted", False))
                and result.character_key
                and reason in {
                    "character_identified",
                    "character_identified_with_quest_journal",
                }
            ):
                # Journal completions change quest progress, not the selected
                # character. Avoid reloading all client profiles each poll.
                active_characters.add(str(result.character_key))
            if (
                bool(getattr(result, "accepted", False))
                and bool(getattr(result, "changed", False))
                and getattr(result, "character_key", "")
                and reason == "session_closed"
            ):
                disconnected_characters.add(str(result.character_key))
            if (
                bool(getattr(result, "accepted", False))
                and result.changed
                and result.character_key
                and reason not in {"character_identified", "session_closed"}
            ):
                # Identity routing/session closure is not a persisted quest
                # mutation. Only progress changes need a costly tab refresh.
                changed_characters.add(str(result.character_key))
        if active_characters or changed_characters:
            record_validation("network_progress", changed=len(changed_characters),
                              activated=bool(active_characters))
        if active_characters:
            # Coalesce multiple concurrent logins into one profile refresh.
            # Never silently discard all but the last identity in a poll.
            identities = tuple(sorted(active_characters))
            self.charactersIdentified.emit(identities)
            if self._stopped:
                return
            if len(identities) == 1:
                # Preserve the existing single-account signal for consumers
                # outside the shell; a multi-login batch is not a focused
                # character and must not activate an arbitrary account.
                self.characterActivated.emit(identities[0])
                if self._stopped:
                    return
        connection_changes = disconnected_characters | membership_changes
        if connection_changes and not active_characters:
            # A decoder reset can remove all transports without individual
            # closure events. Recovery can also attach an existing identity
            # without a login. Both are roster refreshes, never activations.
            self.connectionsChanged.emit(tuple(sorted(connection_changes)))
            if self._stopped:
                return
        # When an identification happened in this same poll, its batch
        # refresh already sees the final runtime state; no second scan needed.
        if changed_characters:
            self._pending_progress_characters.update(changed_characters)
            if not self._progress_timer.isActive():
                self._progress_timer.start()

    def _emit_pending_progress(self) -> None:
        if self._stopped:
            self._pending_progress_characters.clear()
            return
        pending = tuple(sorted(self._pending_progress_characters))
        self._pending_progress_characters.clear()
        for character_key in pending:
            # A recipient can stop the bridge synchronously on the first signal.
            if self._stopped:
                return
            self.progressChanged.emit(character_key)

    def _window_handles(self) -> tuple[int, ...]:
        try:
            sessions = _live_dofus_sessions(int(monotonic() // _WINDOW_SCAN_INTERVAL_SECONDS))
            self._local_sessions = tuple(label for _hwnd, label in sessions)
            return tuple(hwnd for hwnd, _label in sessions)
        except Exception:
            self._local_sessions = ()
            from app.core.logger import get_runtime_logger
            get_runtime_logger().exception("Network window handle lookup failed.")
            return ()


def refresh_visible_encyclopedia_widgets(
    widgets: Iterable[object],
    character_key: str,
) -> int:
    """Refresh only the visible Encyclopedia tab for the changed character.

    EncyclopediaPage already refreshes hidden tabs when they are opened. Network
    ingestion therefore refreshes only the currently displayed child, avoiding
    three expensive UI rebuilds for every completed quest while keeping the
    screen the player is looking at immediately synchronized.
    """

    target = str(character_key or "").strip()
    if not target:
        return 0
    refreshed = 0
    for widget in widgets:
        try:
            object_name = str(widget.objectName() or "")
        except Exception:
            continue
        if object_name != "EncyclopediaPage":
            continue
        # Only the displayed page needs an immediate refresh; the shell
        # synchronizes a hidden Encyclopedia when it is opened again.
        is_visible = getattr(widget, "isVisible", None)
        if callable(is_visible):
            try:
                if not is_visible():
                    continue
            except RuntimeError:
                # Qt can delete an old page while navigation is replacing it.
                continue
        if str(getattr(widget, "current_character_key", "") or "") != target:
            continue
        tabs = getattr(widget, "tabs", None)
        current_widget = getattr(tabs, "currentWidget", None)
        if not callable(current_widget):
            continue
        try:
            current = current_widget()
        except Exception:
            continue
        refresh = getattr(current, "refresh_external_progress", None)
        if not callable(refresh):
            continue
        try:
            refresh()
        except RuntimeError:
            # Qt may delete a page between allWidgets() and this queued refresh.
            continue
        refreshed += 1
    return refreshed


_BRIDGE: NetworkUiBridge | None = None


def network_ui_bridge() -> NetworkUiBridge:
    global _BRIDGE
    app = QApplication.instance()
    if _BRIDGE is None or (
        bool(getattr(_BRIDGE, "_stopped", False))
        and getattr(_BRIDGE, "_stop_result", None) is True
    ):
        # A failed stop may leave a capture helper or worker alive: fail closed
        # rather than starting a second coordinator against the same client.
        _BRIDGE = NetworkUiBridge(app)
        if app is not None:
            app.aboutToQuit.connect(_BRIDGE.stop)
    return _BRIDGE


__all__ = [
    "NetworkUiBridge",
    "network_ui_bridge",
    "refresh_visible_encyclopedia_widgets",
]
