from __future__ import annotations

from typing import Any, Iterable, TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

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

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # Home imports this module before its first paint, but the real bridge is
        # created only after Encyclopedia context or an explicit calibration
        # request. Keep coordinator/settings/catalog imports on that real-use path.
        from app.network.application_coordinator import NetworkApplicationCoordinator

        self.coordinator = NetworkApplicationCoordinator(self._window_handles)
        self._context_signature: tuple[int, int, int] | None = None
        self._last_status = self.coordinator.latest_status()
        self._stopped = False
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
        return True

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
        return self.coordinator.request_start_verified_runtime()

    def stop(self) -> bool:
        if self._stopped:
            return True
        self._stopped = True
        self._timer.stop()
        return bool(self.coordinator.stop())

    def _poll(self) -> None:
        if self._stopped:
            return
        statuses = self.coordinator.drain_statuses(50)
        if statuses:
            self._last_status = statuses[-1]
            self.statusChanged.emit(self._last_status)
        changed_characters: set[str] = set()
        active_character = ""
        for result in self.coordinator.drain_results(100):
            reason = str(getattr(result, "reason", "") or "")
            if (
                bool(getattr(result, "accepted", False))
                and result.character_key
                and (reason.startswith("character_") or reason.startswith("quest_journal_"))
            ):
                active_character = str(result.character_key)
            if result.changed and result.character_key:
                changed_characters.add(str(result.character_key))
        if active_character:
            self.characterActivated.emit(active_character)
        for character_key in sorted(changed_characters):
            self.progressChanged.emit(character_key)

    @staticmethod
    def _window_handles() -> tuple[int, ...]:
        try:
            from app.core.settings import load_settings

            settings = load_settings()
            handles: list[int] = []
            for client in settings.clients:
                try:
                    handle = int(getattr(client, "handle", 0) or 0)
                except (TypeError, ValueError, OverflowError):
                    continue
                if handle > 0:
                    handles.append(handle)
            return tuple(dict.fromkeys(handles))
        except Exception:
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
    if _BRIDGE is None or bool(getattr(_BRIDGE, "_stopped", False)):
        _BRIDGE = NetworkUiBridge(app)
        if app is not None:
            app.aboutToQuit.connect(_BRIDGE.stop)
    return _BRIDGE


__all__ = [
    "NetworkUiBridge",
    "network_ui_bridge",
    "refresh_visible_encyclopedia_widgets",
]
