from __future__ import annotations

from typing import Literal

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyledItemDelegate,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.constants import APP_ICON_PATH
from app.ui.unity_palette import (
    UNITY_CONTROL_LIMITS, UNITY_CONTROL_SIZES_PX, UNITY_LAYOUT_SIZES_PX,
    UNITY_PALETTE,
    UNITY_SIZES_PX, UNITY_SPACING_PX,
)
from app.ui.splash_image import clear_connected_dark_background


BUTTON_OBJECT_NAMES = {
    "primary": "PrimaryActionButton",
    "secondary": "SecondaryButton",
    "selected": "ActiveButton",
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
        size: Literal["compact", "normal", "large"] | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(UNITY_SIZES_PX["control_compact"])
        if size is not None:
            self.setFixedHeight(UNITY_SIZES_PX[f"control_{size}"])
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


class UnityPopupSeparatorDelegate(QStyledItemDelegate):
    """Draw Unity dividers while preserving the native menu interactions."""

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        hint.setHeight(max(hint.height(), UNITY_CONTROL_SIZES_PX["dropdown_row"]))
        return hint

    def paint(self, painter: QPainter, option, index) -> None:
        super().paint(painter, option, index)
        if index.row() + 1 >= index.model().rowCount(index.parent()):
            return
        inset = UNITY_SPACING_PX["md"]
        painter.save()
        painter.setPen(QColor(UNITY_PALETTE["BORDER_SOFT"]))
        painter.drawLine(
            option.rect.left() + inset, option.rect.bottom(),
            option.rect.right() - inset, option.rect.bottom(),
        )
        painter.restore()


def apply_unity_calendar_weekdays(calendar: QCalendarWidget) -> None:
    """Keep the built-in calendar's weekend text in the canonical Unity palette.

    QCalendarWidget formats Saturday/Sunday with native red on some Qt
    platforms; QSS cannot reliably override Qt's per-day text formats.
    """
    for day in (Qt.Saturday, Qt.Sunday):
        format = calendar.weekdayTextFormat(day)
        format.setForeground(QColor(UNITY_PALETTE["TEXT_SOFT"]))
        calendar.setWeekdayTextFormat(day, format)


class AtlasComboBox(QComboBox):
    """Native combo box with the shared Unity row separators."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # A single row-limit contract for every Unity dropdown, including
        # selectors created by future modules. Keep native keyboard/scroll.
        self.setMaxVisibleItems(UNITY_CONTROL_LIMITS["dropdown_visible_rows"])
        popup = self.view()
        popup.setItemDelegate(UnityPopupSeparatorDelegate(popup))


class AtlasBreadcrumb(QFrame):
    """Shared frame and labels for a host-owned navigation path."""

    def __init__(self, parent: QWidget | None = None, *, compact: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("GuideBreadcrumb")
        self.row = QHBoxLayout(self)
        inset = UNITY_LAYOUT_SIZES_PX[
            "breadcrumb_compact_inset" if compact else "breadcrumb_normal_inset"
        ]
        horizontal = UNITY_SPACING_PX["md"]
        self.row.setContentsMargins(horizontal, inset, horizontal, inset)
        self.row.setSpacing(UNITY_LAYOUT_SIZES_PX["breadcrumb_item_gap"])

    def add_separator(self) -> None:
        label = QLabel("›")
        label.setObjectName("GuideBreadcrumbSeparator")
        self.row.addWidget(label)

    def add_current(self, text: str, *, emphasized: bool = False) -> QLabel:
        label = QLabel(text)
        label.setObjectName("GuideBreadcrumbCurrentStrong" if emphasized else "GuideBreadcrumbCurrent")
        label.setWordWrap(False)
        self.row.addWidget(label, 1)
        return label


class AtlasStatusBadge(QLabel):
    """Read-only Unity status: corner hairline + text, never a clickable button.

    The global #StatusBadge QSS owns all colors, typography and geometry.
    Call set_state() when a status changes so Qt repolishes the shared role.
    """

    def __init__(
        self, text: str, state: str = "neutral",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("StatusBadge")
        self.setCursor(Qt.ArrowCursor)
        self.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self.setMinimumHeight(UNITY_SIZES_PX["control_compact"])
        self.setAccessibleName(f"Statut {text}")
        self.set_state(state)

    def set_state(self, state: str) -> None:
        if self.property("state") == state:
            return
        self.setProperty("state", state)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.update()


class AtlasGuideDisclosure(QToolButton):
    """Shared Guide dropdown: down opens, up closes, with indexed Unity QSS."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideMetricDropdown")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setArrowType(Qt.DownArrow)
        self.toggled.connect(self._sync_direction)

    def _sync_direction(self, opened: bool) -> None:
        self.setArrowType(Qt.UpArrow if opened else Qt.DownArrow)


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
        # Shared dialogs must leave enough room for a title and action footer
        # instead of compressing both into the native 290 px minimum.
        self.setMinimumWidth(UNITY_CONTROL_SIZES_PX["dialog_min_width"])
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(
            UNITY_LAYOUT_SIZES_PX["dialog_padding_x"],
            UNITY_LAYOUT_SIZES_PX["dialog_padding_y"],
            UNITY_LAYOUT_SIZES_PX["dialog_padding_x"],
            UNITY_LAYOUT_SIZES_PX["dialog_padding_y"],
        )
        self.content_layout.setSpacing(UNITY_LAYOUT_SIZES_PX["dialog_gap"])


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
        layout.setSpacing(UNITY_LAYOUT_SIZES_PX["dialog_header_gap"])

        self.icon_label = QLabel()
        self.icon_label.setObjectName("DialogLogo")
        icon_box = UNITY_CONTROL_SIZES_PX["dialog_header_icon_box"]
        self.icon_label.setFixedSize(QSize(icon_box, icon_box))
        self.icon_label.setAlignment(Qt.AlignCenter)
        if icon is not None and not icon.isNull():
            artwork_size = UNITY_CONTROL_SIZES_PX["dialog_header_icon_artwork"]
            self.icon_label.setPixmap(icon.pixmap(QSize(artwork_size, artwork_size)))
        pixmap = self.icon_label.pixmap()
        # Qt may return a *null QPixmap*, not None. Do not leave an empty
        # bordered 52 px tile when the official Atlas icon is unavailable.
        self.icon_label.setVisible(pixmap is not None and not pixmap.isNull())
        layout.addWidget(self.icon_label, 0, Qt.AlignTop)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 1, 0, 0)
        text_layout.setSpacing(UNITY_LAYOUT_SIZES_PX["dialog_header_text_gap"])
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
