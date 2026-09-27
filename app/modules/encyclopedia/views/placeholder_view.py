from __future__ import annotations

from PySide6.QtWidgets import QWidget


class EncyclopediaPlaceholderView(QWidget):
    """Zero-cost tab slot used only until the canonical deferred view is built."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EncyclopediaDeferredSlot")
