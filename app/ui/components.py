from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap, QTransform, QPainter
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.constants import APP_ICON_PATH
from app.ui.splash_image import clear_connected_dark_background
from app.ui.unity_skin import unity_guide_chevron_path


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
        if APP_ICON_PATH.exists():
            source = QImage(str(APP_ICON_PATH))
            if source.isNull():
                _APPLICATION_ICON = QIcon(str(APP_ICON_PATH))
            else:
                # The splash already removes the edge-connected dark square
                # from this exact artwork. Do the same for the brand, tray,
                # dialogs and taskbar instead of showing a black tile.
                image = clear_connected_dark_background(source)
                _APPLICATION_ICON = QIcon(QPixmap.fromImage(image))
        else:
            _APPLICATION_ICON = QIcon()
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


def atlas_guide_arrow_icon(direction: str) -> QIcon:
    """Reuse the indexed Unity chevron for Guide drawers and navigation."""
    if direction not in {"up", "down", "left", "right"}:
        raise ValueError("Unknown Guide arrow direction")
    path = unity_guide_chevron_path("down" if direction in {"left", "right"} else direction)
    if path is None:
        return QIcon()
    pixmap = QIcon(str(path)).pixmap(QSize(14, 14))
    if direction in {"left", "right"}:
        pixmap = pixmap.transformed(
            QTransform().rotate(90 if direction == "left" else -90),
            Qt.SmoothTransformation,
        )
    icon = QIcon()
    icon.addPixmap(pixmap, QIcon.Normal)
    icon.addPixmap(pixmap, QIcon.Disabled)
    return icon


class AtlasGuideDisclosure(QToolButton):
    """Shared Guide dropdown: down opens, up closes, with indexed Unity QSS."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideMetricDropdown")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setIconSize(QSize(14, 14))
        self.toggled.connect(self._sync_direction)
        self._sync_direction(False)

    def _sync_direction(self, opened: bool) -> None:
        icon = atlas_guide_arrow_icon("up" if opened else "down")
        self.setArrowType(Qt.NoArrow if not icon.isNull() else
                          Qt.UpArrow if opened else Qt.DownArrow)
        self.setIcon(icon)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt
        super().paintEvent(event)
        # Qt/Windows suppresses QToolButton SVG icons in disabled state
        # even though the same QIcon works on the navigation QPushButtons.
        # Draw the unchanged indexed artwork on top of the shared chrome.
        if self.isEnabled() or self.icon().isNull():
            return
        pixmap = self.icon().pixmap(self.iconSize(), QIcon.Normal)
        if pixmap.isNull():
            return
        painter = QPainter(self)
        painter.drawPixmap(
            (self.width() - pixmap.width()) // 2,
            (self.height() - pixmap.height()) // 2,
            pixmap,
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        if self.isEnabled() or self.icon().isNull():
            return
        # Windows may omit disabled QToolButton icons even though the vector
        # QIcon has a Disabled pixmap. Keep the UI-only Guide arrows visible.
        glyph = self.icon().pixmap(self.iconSize(), QIcon.Disabled)
        if glyph.isNull():
            return
        painter = QPainter(self)
        painter.drawPixmap(
            (self.width() - glyph.width()) // 2,
            (self.height() - glyph.height()) // 2,
            glyph,
        )
        painter.end()


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
