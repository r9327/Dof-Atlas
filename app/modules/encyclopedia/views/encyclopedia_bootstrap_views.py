from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class EncyclopediaWarmupView(QWidget):
    """Neutral responsive shell while a requested heavy provider loads."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EncyclopediaWarmupView")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        heading = QLabel(str(title or "Encyclopédie"))
        heading.setObjectName("GuideSectionTitle")
        heading.setAlignment(Qt.AlignCenter)
        root.addStretch(1)
        root.addWidget(heading)
        progress = QProgressBar()
        progress.setRange(0, 0)
        progress.setTextVisible(False)
        progress.setMaximumWidth(360)
        root.addWidget(progress, 0, Qt.AlignHCenter)
        root.addStretch(1)


__all__ = ["EncyclopediaWarmupView"]
