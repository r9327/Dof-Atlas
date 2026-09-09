from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.constants import APP_ICON_PATH


BUTTON_OBJECT_NAMES = {
    "primary": "PrimaryActionButton",
    "secondary": "SecondaryButton",
    "danger": "DangerButton",
}

_APPLICATION_ICON: QIcon | None = None


def atlas_application_icon() -> QIcon:
    """Return a cheap copy of the product icon from the canonical source asset."""

    global _APPLICATION_ICON
    if _APPLICATION_ICON is None:
        _APPLICATION_ICON = QIcon(str(APP_ICON_PATH)) if APP_ICON_PATH.exists() else QIcon()
    # QIcon is implicitly shared; copying preserves caller value semantics while
    # avoiding repeated file-backed icon construction during shell/dialog setup.
    return QIcon(_APPLICATION_ICON)


class AtlasButton(QPushButton):
    """Shared push button whose visual variants are owned by the global theme."""

    def __init__(
        self,
        text: str,
        parent: QWidget | None = None,
        *,
        variant: str | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(24)
        if variant:
            self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        try:
            object_name = BUTTON_OBJECT_NAMES[variant]
        except KeyError as exc:
            raise ValueError(f"Unknown AtlasButton variant: {variant}") from exc
        self.setObjectName(object_name)


class AtlasPageTitle(QLabel):
    """Shared page heading using the canonical PageTitle theme token."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("PageTitle")


class AtlasDialog(QDialog):
    """Common themed dialog surface with consistent spacing."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AtlasDialog")
        self.setModal(True)
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(24, 22, 24, 22)
        self.content_layout.setSpacing(16)


class AtlasDialogHeader(QWidget):
    """Reusable application-dialog header with optional product icon."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        *,
        icon: QIcon | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DialogHeader")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.icon_label = QLabel()
        self.icon_label.setObjectName("DialogLogo")
        self.icon_label.setFixedSize(QSize(52, 52))
        self.icon_label.setAlignment(Qt.AlignCenter)
        if icon is not None and not icon.isNull():
            self.icon_label.setPixmap(icon.pixmap(QSize(44, 44)))
        self.icon_label.setVisible(self.icon_label.pixmap() is not None)
        layout.addWidget(self.icon_label, 0, Qt.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 1, 0, 0)
        text_layout.setSpacing(5)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("DialogTitle")
        self.title_label.setWordWrap(True)
        text_layout.addWidget(self.title_label)
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("DialogSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        text_layout.addWidget(self.subtitle_label)
        layout.addLayout(text_layout, 1)
