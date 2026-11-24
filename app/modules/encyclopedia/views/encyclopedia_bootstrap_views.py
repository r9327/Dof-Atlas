from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from app.ui.components import configure_unity_progress_bar
from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX


class EncyclopediaWarmupView(QWidget):
    """Neutral responsive shell while a requested heavy provider loads."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EncyclopediaWarmupView")
        root = QVBoxLayout(self)
        geometry = UNITY_MODULE_GEOMETRY_PX["encyclopedia_warmup"]
        root.setContentsMargins(*geometry["margins"])
        root.setSpacing(geometry["spacing"])
        heading = QLabel(str(title or "Encyclopédie"))
        heading.setObjectName("GuideSectionTitle")
        heading.setAlignment(Qt.AlignCenter)
        root.addStretch(1)
        root.addWidget(heading)
        progress = configure_unity_progress_bar(QProgressBar(), maximum=0, text_visible=False)
        progress.setMaximumWidth(geometry["progress_max_width"])
        root.addWidget(progress, 0, Qt.AlignHCenter)
        root.addStretch(1)


__all__ = ["EncyclopediaWarmupView"]
