from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app.network.application_coordinator import NetworkApplicationStatus


class LazyNetworkUiBridge(QObject):
    """Qt-compatible proxy that constructs the real network bridge on demand."""

    statusChanged = Signal(object)
    progressChanged = Signal(str)
    characterActivated = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._bridge: Any = None
        self._initial_status = NetworkApplicationStatus(
            running=False,
            calibrating=False,
            reason="waiting_context",
        )

    @property
    def is_hydrated(self) -> bool:
        return self._bridge is not None

    @property
    def last_status(self) -> NetworkApplicationStatus:
        bridge = self._bridge
        return bridge.last_status if bridge is not None else self._initial_status

    def _ensure_bridge(self):
        bridge = self._bridge
        if bridge is not None:
            return bridge

        from app.ui.network_bridge import network_ui_bridge

        bridge = network_ui_bridge()
        bridge.statusChanged.connect(self.statusChanged.emit)
        bridge.progressChanged.connect(self.progressChanged.emit)
        activated = getattr(bridge, "characterActivated", None)
        if activated is not None:
            activated.connect(self.characterActivated.emit)
        self._bridge = bridge
        return bridge

    def configure_context(
        self,
        *,
        quest_catalog,
        achievement_provider: Any,
        guide_provider: Any = None,
    ) -> bool:
        return bool(
            self._ensure_bridge().configure_context(
                quest_catalog=quest_catalog,
                achievement_provider=achievement_provider,
                guide_provider=guide_provider,
            )
        )

    def request_calibration(self) -> bool:
        return bool(self._ensure_bridge().request_calibration())

    def prepare_capture(self) -> bool:
        return bool(self._ensure_bridge().prepare_capture())

    def request_verified_runtime(self) -> bool:
        return bool(self._ensure_bridge().request_verified_runtime())

    def stop(self) -> bool:
        bridge = self._bridge
        return True if bridge is None else bool(bridge.stop())


_PROXY: LazyNetworkUiBridge | None = None


def lazy_network_ui_bridge() -> LazyNetworkUiBridge:
    global _PROXY
    if _PROXY is None:
        _PROXY = LazyNetworkUiBridge(QApplication.instance())
    return _PROXY


__all__ = ["LazyNetworkUiBridge", "lazy_network_ui_bridge"]
