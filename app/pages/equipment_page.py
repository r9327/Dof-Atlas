from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.constants import HUZOUNET_URL
from app.ui.components import AtlasButton


class EquipmentPage(QWidget):
    """Lightweight equipment entry point.

    Huzounet used to be embedded through a Chromium runtime. That embedded
    browser retained more than one hundred megabytes after leaving the page,
    which is incompatible with Atlas' multi-account memory budget. Keep the
    useful shortcut, but open it in the user's browser until Atlas' native
    equipment rooms are implemented.
    """

    def __init__(self, status_callback, parent: QWidget | None = None):
        super().__init__(parent)
        self.status_callback = status_callback
        self.ready_callbacks: list[Callable[[], None]] = []
        self.section = "PvM"

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 18)
        root.setSpacing(12)

        title = QLabel("Équipement")
        title.setObjectName("PageTitle")
        root.addWidget(title)

        self.section_label = QLabel()
        self.section_label.setObjectName("GuideSectionTitle")
        root.addWidget(self.section_label)

        explanation = QLabel(
            "Le builder intégré est temporairement désactivé pour préserver la mémoire. "
            "Huzounet reste disponible dans le navigateur externe en attendant les salles "
            "d'équipement natives de Dofus Atlas."
        )
        explanation.setObjectName("CompactLabel")
        explanation.setWordWrap(True)
        root.addWidget(explanation)

        open_button = AtlasButton("Ouvrir Huzounet dans le navigateur", variant="primary")
        open_button.clicked.connect(self.open_huzounet)
        root.addWidget(open_button, 0, Qt.AlignLeft)
        root.addStretch(1)

        self.set_section(self.section)

    def is_navigation_ready(self) -> bool:
        return True

    def prepare_for_navigation(self, ready_callback: Callable[[], None] | None = None) -> bool:
        if ready_callback is not None:
            QTimer.singleShot(0, ready_callback)
        return True

    def set_section(self, label: str) -> None:
        value = str(label or "PvM").strip() or "PvM"
        self.section = value
        self.section_label.setText(value)

    def open_huzounet(self) -> None:
        QDesktopServices.openUrl(QUrl(HUZOUNET_URL))
        self.status_callback("Huzounet ouvert dans le navigateur.")


__all__ = ["EquipmentPage"]
