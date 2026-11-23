from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Callable, Literal

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QMenu,
    QScrollArea,
    QLabel,
    QPushButton,
    QStyledItemDelegate,
    QSizePolicy,
    QSpinBox,
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
from app.ui.unity_skin import sprite_icon_path, unity_guide_chevron_path


# Compatibility names from #363 keep using one indexed widget and one
# character-icon geometry owner when the two UI branches are integrated.
GUIDE_CHARACTER_BUTTON_PX = UNITY_CONTROL_SIZES_PX["guide_character_button"]
GUIDE_CHARACTER_ICON_PX = UNITY_CONTROL_SIZES_PX["guide_character_icon"]

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
    # Existing Zaap favorite QSS role, now selected through AtlasButton.
    "zaap_favorite": "favoriteChipName",
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


def fit_unity_number_spinbox(spinbox: QSpinBox) -> int:
    """Fit an indexed Unity x/x selector to its actual displayed range."""
    # Either endpoint may be wider (e.g. -1000 vs 99). The prefix,
    # suffix and special-value label are real Qt text, not a second width
    # policy owned by individual Guide or module screens.
    labels = (
        *(f"{spinbox.prefix()}{spinbox.textFromValue(value)}{spinbox.suffix()}"
          for value in (spinbox.minimum(), spinbox.maximum())),
        spinbox.text(),
        spinbox.specialValueText(),
    )
    content_width = max(spinbox.fontMetrics().horizontalAdvance(label) for label in labels)
    # Guide sheet page numbers have an extra shared inner left inset in QSS.
    # Reserve that exact Unity spacing token without widening ordinary
    # preparation quantities or other number selectors.
    page_inset = (
        UNITY_SPACING_PX["sm"]
        if spinbox.objectName() == "GuideCompactPageJump" else 0
    )
    width = max(
        UNITY_CONTROL_SIZES_PX["guide_quantity_width"],
        content_width + UNITY_CONTROL_SIZES_PX["guide_quantity_chrome_width"] + page_inset,
    )
    spinbox.setFixedWidth(width)
    return width


def refresh_unity_widget_style(widget: QWidget) -> None:
    """Repolish shared Qt property/object-name styles without local QSS."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_unity_widget_property(widget: QWidget, name: str, value: object) -> bool:
    """Update a dynamic Qt style property only when its value changed."""
    if widget.property(name) == value:
        return False
    widget.setProperty(name, value)
    refresh_unity_widget_style(widget)
    return True


def set_unity_widget_object_name(widget: QWidget, object_name: str) -> bool:
    """Repolish only when a widget's indexed QSS object-name role changes."""
    if widget.objectName() == object_name:
        return False
    widget.setObjectName(object_name)
    refresh_unity_widget_style(widget)
    return True


def fill_unity_navigation_menu(
    menu: QMenu, choices: tuple[tuple[str, str], ...], activate: Callable[[str], None],
) -> QMenu:
    """Populate shared QMenu actions without a second navigation widget."""
    for label, target in choices:
        action = menu.addAction(label)
        action.triggered.connect(
            lambda _checked=False, selected=target: activate(selected)
        )
    return menu


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
        set_unity_widget_object_name(self, object_name)


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
    """Unity dropdown sized to its entries, constrained by its parent/screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Recalculate the natural width when entries change. The Maximum policy
        # accepts narrower layouts without forcing every selector to fill a row.
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        # A single row-limit contract for every Unity dropdown, including
        # selectors created by future modules. Keep native keyboard/scroll.
        self.setMaxVisibleItems(UNITY_CONTROL_LIMITS["dropdown_visible_rows"])
        popup = self.view()
        popup.setItemDelegate(UnityPopupSeparatorDelegate(popup))

    def showPopup(self) -> None:
        """Expand the popup for long entries without escaping the screen."""
        super().showPopup()
        view = self.view()
        popup = view.window()
        screen = self.screen()
        if screen is None or popup is self:
            return
        available = screen.availableGeometry()
        content_width = view.sizeHintForColumn(0)
        if (
            content_width <= 0
            or available.width() <= 0
            or available.height() <= 0
        ):
            return
        scrollbar_width = (
            view.verticalScrollBar().sizeHint().width()
            if self.count() > self.maxVisibleItems() else 0
        )
        desired = max(
            self.width(),
            content_width + 2 * view.frameWidth()
            + scrollbar_width + 2 * UNITY_SPACING_PX["lg"],
        )
        width = min(desired, available.width())
        geometry = popup.geometry()
        geometry.setWidth(width)
        geometry.moveLeft(max(
            available.left(),
            min(geometry.left(), available.right() - width + 1),
        ))
        # Qt may open a tall list below a selector near the bottom of a
        # monitor. Bound both axes to the same usable screen geometry:
        # the popup stays scrollable rather than escaping off-screen.
        height = min(geometry.height(), available.height())
        geometry.setHeight(height)
        geometry.moveTop(max(
            available.top(),
            min(geometry.top(), available.bottom() - height + 1),
        ))
        popup.setGeometry(geometry)


class AtlasPageNavigator(QWidget):
    """Reusable compact ‹ current/total › control; the caller owns the page."""

    pageRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None, *, total: int = 1) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(UNITY_SPACING_PX["xs"])

        self.previous_button = AtlasButton("‹", variant="secondary", size="compact")
        self.previous_button.setAccessibleName("Page précédente")
        self.previous_button.setToolTip("Page précédente")
        self.previous_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.page_label = QLabel()
        self.page_label.setObjectName("AtlasPageCounter")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.page_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.next_button = AtlasButton("›", variant="secondary", size="compact")
        self.next_button.setAccessibleName("Page suivante")
        self.next_button.setToolTip("Page suivante")
        self.next_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        row.addWidget(self.previous_button)
        row.addWidget(self.page_label)
        row.addWidget(self.next_button)
        self.previous_button.clicked.connect(
            lambda: self.pageRequested.emit(self._page - 1)
        )
        self.next_button.clicked.connect(
            lambda: self.pageRequested.emit(self._page + 1)
        )
        self.set_page(1, total)

    def set_page(self, page: int, total: int) -> None:
        self._total = max(0, int(total))
        self._page = max(1, min(int(page), self._total)) if self._total else 0
        self.page_label.setText(f"{self._page}/{self._total}")
        self.page_label.updateGeometry()
        self.previous_button.setEnabled(self._page > 1)
        self.next_button.setEnabled(self._page < self._total)
        self.updateGeometry()


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
        set_unity_widget_property(self, "state", state)


class AtlasGuideCover(QLabel):
    """Single indexed Guide artwork slot, retaining original local Unity colors."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideCompactTitleIcon")
        self.setFixedSize(QSize(UNITY_SIZES_PX["icon_xlarge"], UNITY_SIZES_PX["icon_xlarge"]))
        self.setAlignment(Qt.AlignCenter)

    def set_artwork(self, image_path: str | Path | None = None, *, category: str = "guide") -> bool:
        """Show a verified local cover or an explicitly generic Unity pictogram."""
        cover = Path(image_path) if isinstance(image_path, (str, Path)) and image_path else None
        if cover is None or not cover.is_file():
            cover = sprite_icon_path("dofus" if category == "dofus" else "guide")
        pixmap = QIcon(str(cover)).pixmap(self.size()) if cover else QPixmap()
        self.setPixmap(pixmap)
        self.setVisible(not pixmap.isNull())
        return not pixmap.isNull()



@lru_cache(maxsize=8)
def atlas_guide_character_icon(size: int) -> QIcon:
    """Render the *existing* Unity Character sprite without empty PNG margins.

    The original sprite has substantial transparent space: QIcon scaling the
    entire source shrinks the pictogram to a nearly invisible dot. Keep its
    original pixels/colors; only crop transparent margins and scale once.
    """
    path = sprite_icon_path("character")
    if path is None:
        return QIcon()
    source = QPixmap(str(path))
    if source.isNull():
        return QIcon()
    # Reuse Atlas's existing edge-connected dark-background removal,
    # then crop only the transparent padding of the original Unity sprite.
    image = clear_connected_dark_background(source.toImage())
    source = QPixmap.fromImage(image)
    if image.hasAlphaChannel():
        left, top = image.width(), image.height()
        right, bottom = -1, -1
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() > 32:
                    left, top = min(left, x), min(top, y)
                    right, bottom = max(right, x), max(bottom, y)
        if right >= left and bottom >= top:
            source = source.copy(QRect(
                left, top, right - left + 1, bottom - top + 1
            ))
    pixmap = source.scaled(
        QSize(size, size), Qt.KeepAspectRatio, Qt.SmoothTransformation
    )
    icon = QIcon()
    icon.addPixmap(pixmap, QIcon.Normal)
    icon.addPixmap(pixmap, QIcon.Disabled)
    return icon

def atlas_guide_arrow_icon(direction: Literal["up", "down", "left", "right"]) -> QIcon:
    """One original Unity chevron source for all Guide arrows."""
    path = unity_guide_chevron_path("down" if direction in ("left", "right") else direction)
    if path is None:
        return QIcon()
    icon_size = UNITY_CONTROL_SIZES_PX["progress_toggle_icon"]
    pixmap = QIcon(str(path)).pixmap(QSize(icon_size, icon_size))
    if direction in ("left", "right"):
        pixmap = pixmap.transformed(QTransform().rotate(
            90 if direction == "left" else -90), Qt.SmoothTransformation)
    icon = QIcon()
    icon.addPixmap(pixmap, QIcon.Normal)
    icon.addPixmap(pixmap, QIcon.Disabled)
    return icon


class AtlasGuideParticipantButton(QToolButton):
    """Keep the indexed Unity Character artwork legible in disabled shells.

    QStyle may wash out only the central pixels of disabled PNG icons on
    Windows. Repaint the existing normal sprite above the disabled chrome,
    without enabling a control that has no certified route.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideParticipantsButton")

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.isEnabled() or self.icon().isNull():
            return
        pixmap = self.icon().pixmap(self.iconSize(), QIcon.Normal)
        if pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        pixel_ratio = max(1.0, pixmap.devicePixelRatio())
        painter.drawPixmap(
            int((self.width() - pixmap.width() / pixel_ratio) / 2),
            int((self.height() - pixmap.height() / pixel_ratio) / 2),
            pixmap,
        )
        painter.end()


# #363's public name is an alias, never a second owner/implementation.
AtlasGuideCharacterButton = AtlasGuideParticipantButton


class AtlasGuideDisclosure(QToolButton):
    """Shared Guide dropdown: down opens, up closes, with indexed Unity QSS."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideMetricDropdown")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        icon_size = UNITY_CONTROL_SIZES_PX["progress_toggle_icon"]
        self.setIconSize(QSize(icon_size, icon_size))
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
        painter.end()


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
        set_unity_widget_property(self, "collapsed", collapsed)


class AtlasPageTitle(QLabel):
    """Shared page heading using the canonical PageTitle theme token."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("PageTitle")


def release_transient_dialog(dialog: QDialog) -> None:
    """Dispose temporary Qt dialogs after they finish, never on show()."""
    dialog.finished.connect(dialog.deleteLater)


class AtlasDialog(QDialog):
    """Single themed dialog with indexed standard or compact spacing."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        density: Literal["normal", "compact"] = "normal",
    ) -> None:
        if density not in ("normal", "compact"):
            raise ValueError(f"Unknown AtlasDialog density: {density}")
        super().__init__(parent)
        self.setObjectName("AtlasDialog")
        self.layout_density = density
        self.setModal(True)
        # Shared dialogs must leave enough room for a title and action footer
        # instead of compressing both into the native 290 px minimum.
        self.setMinimumWidth(UNITY_CONTROL_SIZES_PX["dialog_min_width"])
        prefix = "dialog_compact_" if density == "compact" else "dialog_"
        x = UNITY_LAYOUT_SIZES_PX[f"{prefix}padding_x"]
        y = UNITY_LAYOUT_SIZES_PX[f"{prefix}padding_y"]
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(x, y, x, y)
        self.content_layout.setSpacing(UNITY_LAYOUT_SIZES_PX[f"{prefix}gap"])

    def add_header(
        self, title: str, subtitle: str = "", *, icon: QIcon | None = None,
    ) -> AtlasDialogHeader:
        """Attach one canonical indexed header to the dialog's content."""
        header = AtlasDialogHeader(title, subtitle, icon=icon, parent=self)
        self.content_layout.addWidget(header)
        return header

    def add_scroll_rows(self) -> QVBoxLayout:
        """Create the shared scrollable content slot for item-heavy dialogs."""
        area = QScrollArea(self)
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget(area)
        rows = QVBoxLayout(container)
        area.setWidget(container)
        self.content_layout.addWidget(area, 1)
        return rows

    def add_action_row(self, *actions: QWidget) -> QHBoxLayout:
        """Place themed dialog actions in one right-aligned shared footer."""
        footer = QHBoxLayout()
        footer.addStretch(1)
        for action in actions:
            footer.addWidget(action)
        self.content_layout.addLayout(footer)
        return footer


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
