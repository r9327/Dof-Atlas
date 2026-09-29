from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class EncyclopediaFutureModuleView(QWidget):
    """Explicit state for Encyclopedia features that do not exist yet.

    This view is never a loading shell and must not be used for Guides,
    Successes or any other implemented feature with a canonical runtime view.
    """

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("EncyclopediaFutureModuleView")
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(8)
        root.addStretch(1)

        heading = QLabel(str(title or "Encyclopédie"))
        heading.setObjectName("GuideSectionTitle")
        heading.setAlignment(Qt.AlignCenter)
        root.addWidget(heading)

        detail = QLabel("Ce module n’est pas encore disponible.")
        detail.setObjectName("MutedLabel")
        detail.setAlignment(Qt.AlignCenter)
        detail.setWordWrap(True)
        root.addWidget(detail)
        root.addStretch(1)


__all__ = ["EncyclopediaFutureModuleView"]
