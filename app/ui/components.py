from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Callable, Literal

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QCalendarWidget,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLayout,
    QMenu,
    QProgressBar,
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
    UNITY_SIZES_PX, UNITY_SPACING_PX, UNITY_GUIDE_READING_METRICS_PX,
    UNITY_WINDOW_PRESETS_PX, UNITY_MODULE_GEOMETRY_PX,
)
from app.ui.splash_image import clear_connected_dark_background
from app.ui.unity_skin import sprite_icon_path, unity_guide_chevron_path, apply_unity_panel_shadow


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
    spinbox.ensurePolished()
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


def configure_unity_tool_button(
    button: QToolButton, *, object_name: str | None = None,
    box: tuple[int, int] | None = None, icon_size: int | None = None,
    text: str | None = None, pointing: bool = False,
    focus_policy: Qt.FocusPolicy | None = None,
) -> QToolButton:
    """Configure shared icon/action chrome without changing callbacks or button state."""
    if object_name is not None:
        button.setObjectName(object_name)
    if box is not None:
        button.setFixedSize(*box)
    if icon_size is not None:
        button.setIconSize(QSize(icon_size, icon_size))
    if text is not None:
        button.setText(text)
    if pointing:
        button.setCursor(Qt.PointingHandCursor)
    if focus_policy is not None:
        button.setFocusPolicy(focus_policy)
    return button


def configure_unity_scroll_area(
    area: QScrollArea, *, borderless: bool = False,
    vertical_policy: Qt.ScrollBarPolicy | None = None,
    horizontal_policy: Qt.ScrollBarPolicy = Qt.ScrollBarAlwaysOff,
) -> QScrollArea:
    """One native scroll policy for Craft, Guides, Organizer and Dev UI.

    Layouts, contents, object names and scroll ownership remain with callers.
    """
    area.setWidgetResizable(True)
    area.setHorizontalScrollBarPolicy(horizontal_policy)
    if borderless:
        area.setFrameShape(QFrame.NoFrame)
    if vertical_policy is not None:
        area.setVerticalScrollBarPolicy(vertical_policy)
    return area


def configure_unity_progress_bar(
    bar: QProgressBar, *, object_name: str | None = None,
    maximum: int = 100, text_visible: bool = False,
    height_role: str | None = None, expanding: bool = False,
    display_format: str | None = None,
) -> QProgressBar:
    """Configure shared progress presentation; callers retain data and ownership."""
    if object_name is not None:
        bar.setObjectName(object_name)
    bar.setRange(0, maximum)
    bar.setTextVisible(text_visible)
    if height_role is not None:
        bar.setFixedHeight(UNITY_CONTROL_SIZES_PX[height_role])
    if expanding:
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    if display_format is not None:
        bar.setFormat(display_format)
    return bar


def clear_unity_widget_layout(
    layout: QLayout, *, hide_widgets: bool = False,
    recursive: bool = False, detach_widgets: bool = True,
) -> None:
    """Clear Qt layouts without replacing their ownership or rendering policy.

    Default detaching matches Quêtes/Succès/Guides. Craft retains the parent
    until DeferredDelete; nested item layouts are walked only when requested.
    """
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            if hide_widgets:
                widget.hide()
            if detach_widgets:
                widget.setParent(None)
            widget.deleteLater()
        elif recursive:
            child_layout = item.layout()
            if child_layout is not None:
                clear_unity_widget_layout(
                    child_layout, hide_widgets=hide_widgets,
                    recursive=True, detach_widgets=detach_widgets,
                )


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


def atlas_guide_symbol_icon(
    widget: QWidget, symbol: str, *, size: int | None = None, color: str | None = None
) -> QIcon:
    """Share tiny semantic Qt icons instead of repainting one per row."""
    # Retain the historical widget-taking API; this artwork is independent of
    # widget identity and must not pin deleted QObjects in a global cache.
    from app.ui.theme import PALETTE

    extent = max(1, int(size if size is not None else UNITY_CONTROL_SIZES_PX["guide_symbol_icon"]))
    return _cached_atlas_guide_symbol_icon(symbol, extent, color or PALETTE["TEXT_SOFT"])


@lru_cache(maxsize=32)
def _cached_atlas_guide_symbol_icon(symbol: str, size: int, color: str) -> QIcon:
    """Build at most 32 lightweight icon rasters, on the Qt GUI thread."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / 18.0, size / 18.0)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    if symbol == "target":
        painter.drawEllipse(QPointF(9, 9), 5.3, 5.3)
        painter.drawEllipse(QPointF(9, 9), 2.2, 2.2)
        painter.drawLine(QPointF(9, 1), QPointF(9, 5))
        painter.drawLine(QPointF(9, 13), QPointF(9, 17))
        painter.drawLine(QPointF(1, 9), QPointF(5, 9))
        painter.drawLine(QPointF(13, 9), QPointF(17, 9))
    elif symbol == "cube":
        painter.drawPolyline([QPointF(9, 2), QPointF(16, 5.5), QPointF(9, 9), QPointF(2, 5.5), QPointF(9, 2)])
        painter.drawPolyline([QPointF(2, 5.5), QPointF(2, 13), QPointF(9, 17), QPointF(16, 13), QPointF(16, 5.5)])
        painter.drawLine(QPointF(9, 9), QPointF(9, 17))
    elif symbol == "trophy":
        painter.drawRoundedRect(QRectF(5, 2, 8, 9), 2, 2)
        painter.drawArc(QRectF(1.5, 2.5, 6.5, 8), 125 * 16, 205 * 16)
        painter.drawArc(QRectF(10, 2.5, 6.5, 8), 210 * 16, 205 * 16)
        painter.drawLine(QPointF(9, 11), QPointF(9, 15))
        painter.drawLine(QPointF(5, 16), QPointF(13, 16))
    elif symbol == "guide":
        painter.drawPolyline([QPointF(9, 4), QPointF(6, 2.5), QPointF(2, 3.5), QPointF(2, 14), QPointF(6, 13), QPointF(9, 15)])
        painter.drawPolyline([QPointF(9, 4), QPointF(12, 2.5), QPointF(16, 3.5), QPointF(16, 14), QPointF(12, 13), QPointF(9, 15)])
        painter.drawLine(QPointF(9, 4), QPointF(9, 15))
    elif symbol == "settings":
        center = QPointF(9, 9)
        painter.drawEllipse(center, 3.0, 3.0)
        painter.drawEllipse(center, 5.6, 5.6)
        for dx, dy in ((0, -7), (0, 7), (-7, 0), (7, 0), (-5, -5), (5, 5), (-5, 5), (5, -5)):
            start = QPointF(center.x() + dx * 0.72, center.y() + dy * 0.72)
            end = QPointF(center.x() + dx, center.y() + dy)
            painter.drawLine(start, end)
    elif symbol == "map":
        painter.drawPolyline(
            [QPointF(2, 4), QPointF(6.5, 2), QPointF(11.5, 4), QPointF(16, 2)]
        )
        painter.drawPolyline(
            [QPointF(2, 4), QPointF(2, 15), QPointF(6.5, 13), QPointF(11.5, 15), QPointF(16, 13), QPointF(16, 2)]
        )
        painter.drawLine(QPointF(6.5, 2), QPointF(6.5, 13))
        painter.drawLine(QPointF(11.5, 4), QPointF(11.5, 15))
    elif symbol == "location":
        painter.drawEllipse(QPointF(9, 6.5), 4.2, 4.2)
        painter.drawEllipse(QPointF(9, 6.5), 1.2, 1.2)
        painter.drawLine(QPointF(6.2, 9.7), QPointF(9, 16))
        painter.drawLine(QPointF(11.8, 9.7), QPointF(9, 16))
    elif symbol == "clipboard":
        painter.drawRoundedRect(QRectF(3, 3, 12, 13), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(6, 1.5, 6, 4), 1.2, 1.2)
        painter.drawLine(QPointF(6, 9), QPointF(12, 9))
        painter.drawLine(QPointF(6, 12), QPointF(12, 12))
    elif symbol == "people":
        painter.drawEllipse(QPointF(6.2, 6), 2.6, 2.6)
        painter.drawEllipse(QPointF(12.2, 7), 2.2, 2.2)
        painter.drawArc(QRectF(1.5, 8.5, 9.5, 7), 20 * 16, 140 * 16)
        painter.drawArc(QRectF(8, 10, 8, 5), 20 * 16, 140 * 16)
    elif symbol == "summary":
        for y in (4, 9, 14):
            painter.drawEllipse(QPointF(3, y), 0.8, 0.8)
            painter.drawLine(QPointF(6, y), QPointF(16, y))
    elif symbol == "current":
        painter.drawArc(QRectF(3, 3, 11, 11), 35 * 16, 285 * 16)
        painter.drawLine(QPointF(3, 4), QPointF(3, 9))
        painter.drawLine(QPointF(3, 4), QPointF(8, 4))
    elif symbol == "lock":
        painter.drawRoundedRect(QRectF(4, 8, 10, 8), 1.5, 1.5)
        painter.drawArc(QRectF(6, 2, 6, 9), 0, 180 * 16)
    elif symbol == "unlock":
        painter.drawRoundedRect(QRectF(4, 8, 10, 8), 1.5, 1.5)
        painter.drawArc(QRectF(8, 2, 6, 9), 0, 180 * 16)
    elif symbol == "back":
        painter.drawLine(QPointF(13, 9), QPointF(3, 9))
        painter.drawLine(QPointF(8, 4), QPointF(3, 9))
        painter.drawLine(QPointF(3, 9), QPointF(8, 14))
    elif symbol == "check":
        painter.drawLine(QPointF(3, 9), QPointF(7, 13))
        painter.drawLine(QPointF(7, 13), QPointF(15, 4))
    painter.end()
    return QIcon(pixmap)


def atlas_quest_shortcut_icon() -> QIcon:
    from app.ui.theme import PALETTE

    size = max(1, int(UNITY_CONTROL_SIZES_PX["guide_quest_shortcut_icon"]))
    return _cached_atlas_quest_shortcut_icon(PALETTE["TEXT_SOFT"], size)


@lru_cache(maxsize=8)
def _cached_atlas_quest_shortcut_icon(color: str, size: int) -> QIcon:
    """Draw a theme-coloured quest page instead of a platform file icon."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / 18.0, size / 18.0)
    pen = QPen(QColor(color), 1.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(3, 1, 12, 16, 2, 2)
    painter.drawLine(6, 6, 12, 6)
    painter.drawLine(6, 9, 12, 9)
    painter.drawLine(6, 12, 10, 12)
    painter.end()
    return QIcon(pixmap)


class AtlasGuideProgressDonut(QWidget):
    """Small palette-aware route progress indicator used in the fixed header."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._percent: int | None = None
        self.setObjectName("GuideCompactDonut")
        self.setFixedSize(UNITY_CONTROL_SIZES_PX["guide_donut_box"], UNITY_CONTROL_SIZES_PX["guide_donut_box"])

    def set_percent(self, value: int | None) -> None:
        value = None if value is None else max(0, min(100, int(value)))
        if value == self._percent:
            return
        self._percent = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        inset = UNITY_CONTROL_SIZES_PX["guide_donut_inset"]
        ring = self.rect().adjusted(inset, inset, -inset, -inset)
        pen = QPen(self.palette().mid().color(), UNITY_CONTROL_SIZES_PX["guide_donut_stroke"])
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(ring, 0, 360 * 16)
        pen.setColor(self.palette().highlight().color())
        painter.setPen(pen)
        if self._percent is not None:
            painter.drawArc(ring, 90 * 16, -round(360 * 16 * self._percent / 100))
        painter.setPen(self.palette().text().color())
        painter.drawText(self.rect(), Qt.AlignCenter,
                         f"{self._percent} %" if self._percent is not None else "—")


class AtlasGuideParticipantPortrait(QToolButton):
    """Real class portrait button with a compact individual progress ring."""

    def __init__(
        self,
        character_key: str,
        *,
        progress: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.character_key = str(character_key)
        self.progress = None if progress is None else max(0, min(100, int(progress)))
        self.progress_checked = 0
        self.progress_total = 0
        box = UNITY_CONTROL_SIZES_PX["guide_portrait_button"]
        configure_unity_tool_button(
            self, object_name="GuideParticipantPortrait", box=(box, box),
            icon_size=UNITY_CONTROL_SIZES_PX["guide_portrait_icon"], pointing=True,
        )
        self.setCheckable(True)

    def set_percent(self, progress: int | None) -> None:
        normalized = None if progress is None else max(0, min(100, int(progress)))
        if normalized != self.progress:
            self.progress = normalized
            self.update()

    def set_progress(self, completed: int, total: int) -> None:
        """Retain exact source counts and use the same ring for every Guide."""
        if not (type(completed) is int and type(total) is int
                and total >= 0 and 0 <= completed <= total):
            raise ValueError("Invalid manual portrait progress")
        self.progress_checked, self.progress_total = completed, total
        self.set_percent(round(completed * 100 / total) if total else None)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # Keep the ring in Unity accents; gray looks like a disabled portrait.
        from app.ui.theme import PALETTE

        color = QColor(
            PALETTE["GREEN"] if self.isChecked() else PALETTE["BORDER_STRONG"]
        )
        pen = QPen(color, UNITY_CONTROL_SIZES_PX["guide_portrait_stroke"])
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        if self.progress is not None:
            inset = UNITY_CONTROL_SIZES_PX["guide_portrait_inset"]
            painter.drawArc(
                self.rect().adjusted(inset, inset, -inset, -inset),
                90 * 16,
                -round(360 * 16 * self.progress / 100),
            )


class AtlasGuideParticipantButton(QToolButton):
    """Keep the indexed Unity Character artwork legible in disabled shells.

    QStyle may wash out only the central pixels of disabled PNG icons on
    Windows. Repaint the existing normal sprite above the disabled chrome,
    without enabling a control that has no certified route.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideParticipantsButton")

    def configure_compact(self) -> None:
        """Apply the shared title-row geometry, leaving menu/check behavior to the caller."""
        size = UNITY_CONTROL_SIZES_PX["guide_character_button"]
        icon_size = UNITY_CONTROL_SIZES_PX["guide_character_icon"]
        configure_unity_tool_button(self, box=(size, size), icon_size=icon_size)
        self.setToolButtonStyle(Qt.ToolButtonIconOnly)

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
        configure_unity_tool_button(
            self, object_name="GuideMetricDropdown", pointing=True,
            focus_policy=Qt.StrongFocus,
            icon_size=UNITY_CONTROL_SIZES_PX["progress_toggle_icon"],
        )
        self.setCheckable(True)
        self.toggled.connect(self._sync_direction)
        self._sync_direction(False)

    def configure_compact(self) -> None:
        """Apply the one indexed metric disclosure geometry."""
        self.setFixedSize(
            UNITY_CONTROL_SIZES_PX["progress_toggle_width"],
            UNITY_CONTROL_SIZES_PX["progress_toggle_height"],
        )

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
        pixel_ratio = max(1.0, pixmap.devicePixelRatio())
        painter.drawPixmap(
            int((self.width() - pixmap.width() / pixel_ratio) / 2),
            int((self.height() - pixmap.height() / pixel_ratio) / 2),
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
        configure_unity_tool_button(
            self, object_name="GuideRightPanelToggle", pointing=True,
            focus_policy=Qt.StrongFocus,
        )
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


def atlas_guide_global_progress_bar() -> QProgressBar:
    """Single indexed progress control, shared by headers and standalone previews."""
    return configure_unity_progress_bar(
        QProgressBar(), object_name="GuideGlobalProgress",
        height_role="progress_primary", expanding=True,
    )


class AtlasGuideReadingHeader(QFrame):
    """Shared UI shell for real Guide readers and the Dev UI, without game data."""

    def __init__(self, title: str, *, image_path: str | Path | None = None,
                 category: str = "guide", overview: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from app.ui.theme import PALETTE

        self.setObjectName("GuideHeader" if overview else "GuideCompactHeader")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(
            UNITY_LAYOUT_SIZES_PX["guide_header_margin_x"],
            UNITY_LAYOUT_SIZES_PX["guide_header_margin_top"],
            UNITY_LAYOUT_SIZES_PX["guide_header_margin_x"],
            UNITY_LAYOUT_SIZES_PX["guide_header_margin_bottom"],
        )
        outer.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_header_outer_spacing"])

        right = QVBoxLayout()
        right.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_header_content_spacing"])
        outer.addLayout(right, 1)
        self.global_progress_bar = atlas_guide_global_progress_bar()
        self.global_progress_label = QLabel("—")
        self.global_progress_label.setObjectName("GuideCompactMetricValue")

        # Row 1: active guide, instant sheet selector and compact commands.
        title_row = QHBoxLayout()
        title_row.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_header_content_spacing"])
        guide_icon = AtlasGuideCover()
        self.guide_icon_label = guide_icon
        guide_icon.set_artwork(image_path, category=category)
        title_row.addWidget(guide_icon)
        self.guide_title_label = QLabel(title)
        self.guide_title_label.setObjectName("GuideCompactTitle")
        self.guide_title_label.setMinimumWidth(0)
        self.guide_title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.guide_title_label.setToolTip(title)
        if overview:
            # Catalog and quest detail have no certified preparation model.
            # Reuse the same title/progress shell, with only genuine actions.
            geometry = UNITY_MODULE_GEOMETRY_PX["guide_reading_header"]
            guide_icon.setObjectName("GuideHeaderImage")
            guide_icon.setFixedSize(geometry["overview_cover_box"], geometry["overview_cover_box"])
            guide_icon.set_artwork(image_path, category=category)
            self.guide_title_label.setObjectName("GuideHeaderTitle")
            titles = QVBoxLayout()
            titles.setContentsMargins(0, 0, 0, 0)
            titles.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
            titles.addWidget(self.guide_title_label)
            self.meta_label = QLabel()
            self.meta_label.setObjectName("GuideHeaderMeta")
            self.meta_label.hide()
            titles.addWidget(self.meta_label)
            title_row.addLayout(titles, 1)
        else:
            title_row.addWidget(self.guide_title_label, 1)

        right.addLayout(title_row)
        self.title_row = title_row
        self.content_layout = right

        # Shared #363 layout: progress is global; preparation is inside details.
        overall_caption = QHBoxLayout()
        title = QLabel("Progression globale")
        title.setObjectName("GuideGlobalProgressTitle")
        overall_caption.addWidget(title)
        self.global_progress_title = title
        if overview:
            overall_caption.addStretch(1)
            overall_caption.addWidget(self.global_progress_label)
            self.global_progress_label.setObjectName("GuideHeaderProgress")
            right.addLayout(overall_caption)
            right.addWidget(self.global_progress_bar)
            apply_unity_panel_shadow(self)
            return
        self.global_details_button = AtlasGuideDisclosure()
        self.global_details_button.configure_compact()
        self.global_details_button.setToolTip("Afficher la progression et les préparatifs")
        self.global_details_button.setAccessibleName("Déplier la progression globale")
        overall_caption.addWidget(self.global_details_button, 0, Qt.AlignVCenter)
        overall_caption.addStretch(1)
        overall_caption.addWidget(self.global_progress_label)
        right.addLayout(overall_caption)
        right.addWidget(self.global_progress_bar)

        self.global_details_panel = QFrame()
        self.global_details_panel.setObjectName("GuideGlobalDetailsPanel")
        details = QVBoxLayout(self.global_details_panel)
        details.setContentsMargins(
            UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["xs"],
            UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["sm"],
        )
        details.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
        self.global_details_rows = QWidget()
        self.global_details_rows.setObjectName("GuideGlobalCharacterProgress")
        self.global_details_layout = QVBoxLayout(self.global_details_rows)
        self.global_details_layout.setContentsMargins(0, 0, 0, 0)
        self.global_details_layout.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
        details.addWidget(self.global_details_rows)

        preparation_metric = QVBoxLayout()
        preparation_metric.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
        caption = QHBoxLayout()
        caption.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_caption_spacing"])
        icon = QLabel()
        icon.setObjectName("GuideCompactMetricIconCube")
        icon_size = UNITY_SIZES_PX["icon_small"]
        icon.setPixmap(
            atlas_guide_symbol_icon(icon, "cube", size=icon_size, color=PALETTE["GREEN"]).pixmap(icon_size, icon_size)
        )
        icon.setFixedSize(UNITY_SIZES_PX["icon_small"], UNITY_SIZES_PX["icon_small"])
        caption.addWidget(icon)
        caption_label = QLabel("À préparer")
        caption_label.setToolTip("Préparation")
        caption.addWidget(caption_label)
        self.preparation_caption = caption_label
        self.preparation_icon = icon
        caption.addStretch(1)
        self.preparation_progress_label = QLabel("—")
        self.preparation_progress_label.setObjectName("GuideCompactMetricValue")
        caption.addWidget(self.preparation_progress_label)
        self.preparation_button = AtlasGuideDisclosure()
        self.preparation_button.configure_compact()
        self.preparation_button.setToolTip("Ouvrir Préparation")
        self.preparation_button.setAccessibleName("Afficher Préparation")
        caption.insertWidget(2, self.preparation_button, 0, Qt.AlignVCenter)
        preparation_metric.addLayout(caption)
        self.preparation_bar = configure_unity_progress_bar(
            QProgressBar(), object_name="GuideCompactPreparationProgress",
            height_role="progress_secondary", expanding=True,
        )
        preparation_metric.addWidget(self.preparation_bar)
        drawer = QVBoxLayout()
        drawer.setContentsMargins(0, 0, 0, 0)
        self.preparation_drawer = drawer
        preparation_metric.addLayout(drawer)
        details.addLayout(preparation_metric)
        self.global_details_panel.setVisible(False)
        self.global_details_button.toggled.connect(self._set_global_details_open)
        right.addWidget(self.global_details_panel)
        self.content_layout = right

        self.participants_button = AtlasGuideParticipantButton()
        self.participants_button.configure_compact()
        self.participants_button.setIcon(atlas_guide_character_icon(UNITY_CONTROL_SIZES_PX["guide_character_icon"]))
        if self.participants_button.icon().isNull():
            self.participants_button.setIcon(atlas_guide_symbol_icon(self.participants_button, "people"))
        self.participants_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.participants_button.setCheckable(True)
        self.participants_button.setCursor(Qt.PointingHandCursor)
        self.participants_button.setToolTip("Personnages")
        self.participants_button.setAccessibleName("Personnages")
        title_row.addWidget(self.participants_button, 0, Qt.AlignVCenter)
        self.participants_panel = QFrame()
        self.participants_panel.setObjectName("GuideParticipantsPanel")
        self.participants_layout = QHBoxLayout(self.participants_panel)
        self.participants_layout.setContentsMargins(*UNITY_MODULE_GEOMETRY_PX["guide_reading_header"]["participant_margins"])
        self.participants_layout.setSpacing(UNITY_MODULE_GEOMETRY_PX["guide_reading_header"]["participant_gap"])
        self.participants_panel.hide()
        self.participants_button.toggled.connect(self.participants_panel.setVisible)
        right.insertWidget(1, self.participants_panel)
        apply_unity_panel_shadow(self)

    def _set_global_details_open(self, opened: bool) -> None:
        self.global_details_panel.setVisible(opened)
        self.global_details_button.setAccessibleName(
            "Replier la progression globale" if opened else "Déplier la progression globale"
        )
        self.global_details_button.setToolTip(
            "Masquer la progression et les préparatifs" if opened
            else "Afficher la progression et les préparatifs"
        )

    def set_overview_progress(self, completed: int, total: int, *, visible: bool = True) -> None:
        """Present real catalogue counts only; unavailable totals stay unknown."""
        self.global_progress_title.setVisible(visible)
        self.global_progress_label.setVisible(visible)
        self.global_progress_bar.setVisible(visible)
        self.global_progress_bar.setRange(0, max(1, total))
        self.global_progress_bar.setValue(max(0, min(completed, total)))
        self.global_progress_label.setText(f"{completed}/{total}" if total > 0 else "—")

    def attach_preparation(self, panel: QWidget) -> None:
        self.preparation_drawer.addWidget(panel)
        panel.setVisible(self.preparation_button.isChecked())
        self.preparation_button.toggled.connect(panel.setVisible)
        self.preparation_button.toggled.connect(self._set_preparation_open)

    def _set_preparation_open(self, opened: bool) -> None:
        self.preparation_button.setAccessibleName(
            "Masquer Préparation" if opened else "Afficher Préparation"
        )


class AtlasGuideSheetHeader(QFrame):
    """One authored sheet title, back action and content-sized page selector."""

    def __init__(self, title: str = "", *, total: int, page: int = 1, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideSheetHeader")
        geometry = UNITY_MODULE_GEOMETRY_PX["guide_reading_header"]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*geometry["sheet_margins"])
        layout.setSpacing(geometry["sheet_gap"])
        top = QHBoxLayout()
        top.setSpacing(geometry["sheet_row_gap"])
        self.back_button = AtlasButton("")
        self.back_button.setIcon(atlas_guide_arrow_icon("left"))
        self.back_button.setIconSize(QSize(geometry["back_icon"], geometry["back_icon"]))
        self.back_button.setObjectName("GuideManualGuideButton")
        self.back_button.setToolTip("Revenir à la fiche actuelle, puis au catalogue des guides")
        self.back_button.setAccessibleName("Fiche actuelle ou catalogue des guides")
        self.back_button.setMaximumWidth(geometry["back_max_width"])
        top.addWidget(self.back_button, 0, Qt.AlignVCenter)
        labels = QVBoxLayout()
        labels.setSpacing(geometry["sheet_title_gap"])
        self.title_label = QLabel(title)
        self.title_label.setObjectName("GuideSheetTitle")
        self.title_label.setWordWrap(True)
        labels.addWidget(self.title_label)
        top.addLayout(labels, 1)
        self.page_jump = QSpinBox()
        self.page_jump.setObjectName("GuideCompactPageJump")
        self.page_jump.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.page_jump.setToolTip("Ouvrir directement la fiche sélectionnée")
        self.page_jump.setAccessibleName("Sélectionner la fiche du guide")
        self.set_page(page, total)
        top.addWidget(self.page_jump, 0, Qt.AlignTop)
        layout.addLayout(top)
        apply_unity_panel_shadow(self)

    def set_page(self, page: int, total: int) -> None:
        previous = self.page_jump.blockSignals(True)
        try:
            total = max(0, int(total))
            self.page_jump.setRange(1 if total else 0, total)
            self.page_jump.setSuffix(f"/{total}")
            self.page_jump.setValue(max(1, min(page, total)) if total else 0)
            self.page_jump.setEnabled(total > 0)
            fit_unity_number_spinbox(self.page_jump)
        finally:
            self.page_jump.blockSignals(previous)


class AtlasPageTitle(QLabel):
    """Shared page heading using the canonical PageTitle theme token."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("PageTitle")


def clear_current_dialog_reference(owner: object, attribute: str, dialog: QDialog) -> bool:
    """Never let a closed older popup clear its newer replacement."""
    if getattr(owner, attribute, None) is not dialog:
        return False
    setattr(owner, attribute, None)
    return True


def release_transient_dialog(dialog: QDialog) -> None:
    """Dispose temporary Qt dialogs after they finish, never on show()."""
    dialog.finished.connect(dialog.deleteLater)


def present_transient_dialog(
    owner: object, attribute: str, dialog: QDialog, *,
    mode: Literal["show", "open"] = "show",
    on_finished: Callable[[int], None] | None = None,
) -> None:
    """One temporary window per owner slot; release safely on completion."""
    if mode not in ("show", "open"):
        raise ValueError(f"Unknown dialog presentation mode: {mode}")
    current = getattr(owner, attribute, None)
    if current is dialog:
        return
    if current is not None:
        current.close()
    setattr(owner, attribute, dialog)

    def finished(result: int) -> None:
        clear_current_dialog_reference(owner, attribute, dialog)
        if on_finished is not None:
            on_finished(result)

    dialog.finished.connect(finished)
    # Parentless windows (notably the always-on-top Craft resources) must
    # retain their independent window flags but not outlive the owning page.
    if isinstance(owner, QObject) and dialog.parent() is None:
        owner.destroyed.connect(dialog.deleteLater)
    dialog.destroyed.connect(
        lambda *_args: clear_current_dialog_reference(owner, attribute, dialog)
    )
    release_transient_dialog(dialog)
    if mode == "open":
        dialog.open()
    else:
        dialog.show()
        dialog.raise_()


def exec_transient_dialog(dialog: QDialog) -> int:
    """Release one-shot modal dialogs after their nested event loop returns."""
    try:
        return dialog.exec()
    finally:
        dialog.deleteLater()


class AtlasImagePopup(QDialog):
    """Shared nonmodal image zoom for all document/Guide previews."""

    def __init__(self, source: QPixmap, parent: QWidget, *, title: str = "") -> None:
        super().__init__(parent, Qt.Popup)
        self.setObjectName("AtlasDialog")
        self.setWindowTitle(title or "Image de solution")
        metrics = UNITY_GUIDE_READING_METRICS_PX
        margin = metrics["zoom_margin"]
        root = QVBoxLayout(self)
        root.setContentsMargins(margin, margin, margin, margin)
        root.setSpacing(0)
        image = QLabel()
        image.setObjectName("QuestSolutionImage")
        image.setAlignment(Qt.AlignCenter)
        screen = parent.screen()
        bounds = screen.availableGeometry() if screen is not None else None
        available = bounds.size() if bounds is not None else QSize(*UNITY_WINDOW_PRESETS_PX["standard"])
        max_width = min(available.width(), max(
            metrics["zoom_min_width"],
            min(metrics["zoom_dialog_width"], available.width() * metrics["zoom_screen_percent"] // 100),
        ))
        max_height = min(available.height(), max(
            metrics["zoom_min_height"],
            min(metrics["zoom_dialog_height"], available.height() * metrics["zoom_screen_percent"] // 100),
        ))
        inset = max(metrics["zoom_content_inset"], margin * 2)
        target = source.size()
        target.scale(
            max(1, max_width - inset),
            max(1, max_height - inset),
            Qt.KeepAspectRatio,
        )
        image.setPixmap(source.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        root.addWidget(image)
        self.resize(target.width() + margin * 2, target.height() + margin * 2)
        center = parent.mapToGlobal(parent.rect().center())
        x = center.x() - self.width() // 2
        y = center.y() - self.height() // 2
        if bounds is not None:
            x = max(bounds.left(), min(x, bounds.right() - self.width() + 1))
            y = max(bounds.top(), min(y, bounds.bottom() - self.height() + 1))
        self.move(x, y)


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
        area = configure_unity_scroll_area(QScrollArea(self))
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
