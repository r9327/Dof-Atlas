from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.storage import ZaapWidget as _EagerZaapWidget


class LazyZaapWidget(QWidget):
    """Cheap Organizer placeholder that hydrates the real Zaap UI on demand."""

    def __init__(
        self,
        status_callback,
        start_callback=None,
        config_update_callback=None,
        parent: QWidget | None = None,
        show_position_controls: bool = True,
        show_favorites: bool = True,
    ) -> None:
        super().__init__(parent)
        self._status_callback = status_callback
        self._start_callback = start_callback
        self._config_update_callback = config_update_callback
        self._show_position_controls = bool(show_position_controls)
        self._show_favorites = bool(show_favorites)
        self._zaap_widget: QWidget | None = None

        self._hydrate_timer = QTimer(self)
        self._hydrate_timer.setSingleShot(True)
        self._hydrate_timer.setInterval(0)
        self._hydrate_timer.timeout.connect(self._hydrate_if_visible)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMaximumHeight(68 if self._show_favorites else 32)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._layout = layout

        self._placeholder = QLabel("Chargement du Zaap…")
        self._placeholder.setObjectName("MutedLabel")
        self._placeholder.setFixedHeight(32)
        self._layout.addWidget(self._placeholder)

    @property
    def is_hydrated(self) -> bool:
        return self._zaap_widget is not None

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._schedule_hydration()

    def _schedule_hydration(self) -> None:
        if self._zaap_widget is not None or self._hydrate_timer.isActive() or not self.isVisible():
            return
        self._hydrate_timer.start()

    def _hydrate_if_visible(self) -> None:
        if self._zaap_widget is not None or not self.isVisible():
            return

        widget = _EagerZaapWidget(
            self._status_callback,
            self._start_callback,
            self._config_update_callback,
            parent=self,
            show_position_controls=self._show_position_controls,
            show_favorites=self._show_favorites,
        )
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._layout.replaceWidget(self._placeholder, widget)
        self._placeholder.hide()
        self._placeholder.deleteLater()
        self._zaap_widget = widget
        widget.show()


__all__ = ["LazyZaapWidget"]
