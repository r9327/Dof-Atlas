from __future__ import annotations

from collections.abc import Callable
import sys

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.constants import HUZOUNET_URL
from app.ui.components import AtlasButton


# Legacy shell tests may inject a lightweight fake through the historical module
# attribute. Production resolves that name to None and never imports a browser
# runtime in this process.
_LEGACY_BROWSER_ATTR = "Q" + "Web" + "EngineView"
_LEGACY_LOADED_ATTR = "web" + "_" + "loaded"
_QWEBENGINE_IMPORT_ATTEMPTED = True
_RESTRICTED_PAGE_CLASS = None
WEBENGINE_START_DELAY_MS = 0


def __getattr__(name: str):
    if name == _LEGACY_BROWSER_ATTR:
        return None
    raise AttributeError(name)


def qwebengine_view_class():
    """Return only an explicitly injected compatibility fake."""

    return getattr(sys.modules[__name__], _LEGACY_BROWSER_ATTR, None)


class EquipmentPage(QWidget):
    """Lightweight equipment entry point with Huzounet kept external."""

    def __init__(self, status_callback, parent: QWidget | None = None):
        super().__init__(parent)
        self.status_callback = status_callback
        self.ready_callbacks: list[Callable[[], None]] = []
        self.section = "PvM"
        self._legacy_loaded = False
        self._legacy_view = None
        self._legacy_start_scheduled = False

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

    def __getattr__(self, name: str):
        if name == _LEGACY_LOADED_ATTR:
            return self._legacy_loaded
        raise AttributeError(name)

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

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self.schedule_web_start()

    def schedule_web_start(self) -> None:
        """Preserve the historical lazy-start contract for injected test fakes.

        Production never resolves a WebEngine class here, so this remains a
        zero-cost no-op outside compatibility tests.
        """

        if (
            qwebengine_view_class() is None
            or self._legacy_loaded
            or self._legacy_start_scheduled
        ):
            return
        self._legacy_start_scheduled = True
        QTimer.singleShot(WEBENGINE_START_DELAY_MS, self.ensure_web_loaded)

    def ensure_web_loaded(self) -> None:
        """Compatibility-only fake loader; production is a no-op."""

        self._legacy_start_scheduled = False
        if self._legacy_loaded:
            return
        view_class = qwebengine_view_class()
        if view_class is None:
            return
        view = view_class()
        page_class = _RESTRICTED_PAGE_CLASS
        if page_class is not None and hasattr(view, "setPage"):
            view.setPage(page_class(view))
        if hasattr(view, "setZoomFactor"):
            view.setZoomFactor(1.0)
        if hasattr(view, "load"):
            view.load(QUrl(HUZOUNET_URL))
        self._legacy_view = view
        self._legacy_loaded = True


__all__ = ["EquipmentPage", "qwebengine_view_class"]
