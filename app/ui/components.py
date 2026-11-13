from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
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
from app.ui.unity_palette import UNITY_SIZES_PX
from app.ui.splash_image import clear_connected_dark_background


BUTTON_OBJECT_NAMES = {
    "primary": "PrimaryActionButton",
    "secondary": "SecondaryButton",
    "danger": "DangerButton",
    "navigation": "TopNavButton",
    "navigation_active": "TopNavButtonActive",
    # Shared link roles across Guides, Quêtes and Succès.
    "guide_breadcrumb": "GuideBreadcrumbButton",
    "guide_quest_link": "GuideInlineQuestButton",
    "guide_achievement_link": "GuideInlineAchievementButton",
    # Reusable, unbordered links for secondary actions and popup triggers.
    "inline_action": "InlineActionButton",
    "popup_link": "PopupLinkButton",
    # Unlike read-only badges, status chips are interactive and checkable.
    "status_chip": "StatusChip",
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
        self.setMinimumHeight(UNITY_SIZES_PX["control_compact"])
        if variant:
            self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        try:
            object_name = BUTTON_OBJECT_NAMES[variant]
        except KeyError as exc:
            raise ValueError(f"Unknown AtlasButton variant: {variant}") from exc
        self.set_style_name(object_name)

    def set_style_name(self, object_name: str) -> None:
        """Refresh a changed shared Qt style role without recreating the button."""
        if self.objectName() == object_name:
            return
        self.setObjectName(object_name)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()


class AtlasPanelToggle(QToolButton):
    """Shared Unity control for collapsing a host-owned information panel.

    Only presentation and accessibility are shared. The host retains the
    visibility, splitter sizing, scroll restoration and click callback.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideRightPanelToggle")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setProperty("collapsed", False)
        self.setText("›")
        self.setToolTip("Masquer la colonne d'informations")
        self.setAccessibleName(self.toolTip())

    def set_collapsed(self, collapsed: bool) -> None:
        """Update the shared state without extra repolish on identical values."""
        collapsed = bool(collapsed)
        self.setText("‹" if collapsed else "›")
        label = (
            "Réafficher la colonne d'informations"
            if collapsed else "Masquer la colonne d'informations"
        )
        self.setToolTip(label)
        self.setAccessibleName(label)
        if self.property("collapsed") == collapsed:
            return
        self.setProperty("collapsed", collapsed)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()


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
