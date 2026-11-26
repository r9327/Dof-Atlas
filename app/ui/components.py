from __future__ import annotations

from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Callable, Literal

from PySide6.QtCore import QSignalBlocker, QObject, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLayout,
    QListWidget,
    QListWidgetItem,
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
from app.core.file_stamp import mtime_ctime_size_stamp
from app.core.numbers import clamp_int32, clamped_percent, INT32_MAX
from app.ui.unity_palette import (
    UNITY_CONTROL_LIMITS, UNITY_CONTROL_SIZES_PX, UNITY_LAYOUT_SIZES_PX,
    UNITY_PALETTE, UNITY_PANEL_SHADOW,
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
_APPLICATION_ICON_STAMP: tuple[str, tuple[int, int, int] | None] | None = None


def atlas_application_icon() -> QIcon:
    """Return a cheap copy of the product icon from the canonical source asset."""

    global _APPLICATION_ICON, _APPLICATION_ICON_STAMP
    stamp = (str(APP_ICON_PATH), mtime_ctime_size_stamp(APP_ICON_PATH))
    if _APPLICATION_ICON is None or stamp != _APPLICATION_ICON_STAMP:
        if APP_ICON_PATH.is_file():
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
        _APPLICATION_ICON_STAMP = stamp
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


def configure_unity_number_spinbox(
    spinbox: QSpinBox, *, minimum: int, maximum: int, value: int,
    object_name: str | None = None, suffix: str | None = None,
    tooltip: str | None = None, centered: bool = False, compact: bool = False,
) -> QSpinBox:
    """One numeric editor projection; callers own the meaning of the value."""
    with QSignalBlocker(spinbox):
        if object_name is not None:
            spinbox.setObjectName(object_name)
        if compact:
            spinbox.setFixedHeight(UNITY_SIZES_PX["control_compact"])
        if centered:
            spinbox.setAlignment(Qt.AlignCenter)
        spinbox.setRange(clamp_int32(minimum), clamp_int32(maximum))
        if suffix is not None:
            spinbox.setSuffix(suffix)
        if tooltip is not None:
            spinbox.setToolTip(tooltip)
        spinbox.setValue(clamp_int32(value))
        fit_unity_number_spinbox(spinbox)
    return spinbox


def restore_unity_number_value(spinbox: QSpinBox, value: int) -> None:
    """Restore a persisted value without generating a second user edit."""
    with QSignalBlocker(spinbox):
        spinbox.setValue(clamp_int32(value))


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


def atlas_guide_state_marker(state: str) -> QLabel:
    """One indexed marker owner for Guide section and prerequisite states."""
    symbols = {"done": "✓", "partial": "●", "todo": "○", "neutral": ""}
    if state not in symbols:
        raise ValueError(f"Unknown Guide marker state: {state}")
    marker = QLabel(symbols[state])
    marker.setObjectName("GuideTreeState")
    marker.setProperty("state", state)
    marker.setFixedWidth(UNITY_CONTROL_SIZES_PX["guide_tree_state_width"])
    marker.setAlignment(Qt.AlignCenter)
    return marker


def atlas_prerequisite_row(content: QWidget, completed: bool | None = None) -> QFrame:
    """Canonical marker/layout for plain, Quest and Achievement prerequisites."""
    row = QFrame()
    row.setObjectName("GuidePrerequisiteRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    geometry = UNITY_MODULE_GEOMETRY_PX["quest_detail"]
    layout.setSpacing(geometry["prerequisite_row_spacing"])
    marker = atlas_guide_state_marker(
        "done" if completed is True else "todo" if completed is False else "neutral"
    )
    layout.addWidget(marker, 0, Qt.AlignTop)
    layout.addWidget(content, 1)
    return row


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
    area.viewport().setAutoFillBackground(False)
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


def set_unity_progress_counts(
    bar: QProgressBar, completed: int, total: int, *, busy_when_empty: bool = False,
) -> int | None:
    """One bounded count projection; the caller owns wording and empty state."""
    if total <= 0:
        bar.setRange(0, 0 if busy_when_empty else 1)
        if not busy_when_empty:
            bar.setValue(0)
        return None
    completed = max(0, min(completed, total))
    if total > INT32_MAX:
        # Very large source totals cannot cross Qt's signed-native boundary.
        bar.setRange(0, 100)
        bar.setValue(clamped_percent(completed, total))
    else:
        bar.setRange(0, total)
        bar.setValue(completed)
    return clamped_percent(completed, total)


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
        if size == "compact":
            self.setProperty("atlasCompactButton", True)
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
        view = self.view()
        popup = view.window()
        shadow_margin = 0
        layout = popup.layout()
        if popup is not self and popup.windowType() == Qt.Popup and layout is not None:
            shadow_margin = UNITY_PANEL_SHADOW["blur"] + UNITY_PANEL_SHADOW["vertical"]
            if view.graphicsEffect() is None:
                popup.setWindowFlag(Qt.FramelessWindowHint)
                popup.setWindowFlag(Qt.NoDropShadowWindowHint)
                popup.setAttribute(Qt.WA_TranslucentBackground)
                popup.setAutoFillBackground(False)
                layout.setContentsMargins(shadow_margin, shadow_margin, shadow_margin, shadow_margin)
                apply_unity_panel_shadow(view)
        super().showPopup()
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
        width = min(desired + 2 * shadow_margin, available.width())
        geometry = popup.geometry()
        geometry.setWidth(width)
        geometry.moveLeft(max(
            available.left(),
            min(geometry.left() - shadow_margin, available.right() - width + 1),
        ))
        # Qt may open a tall list below a selector near the bottom of a
        # monitor. Bound both axes to the same usable screen geometry:
        # the popup stays scrollable rather than escaping off-screen.
        height = min(geometry.height() + 2 * shadow_margin, available.height())
        geometry.setHeight(height)
        geometry.moveTop(max(
            available.top(),
            min(geometry.top() - shadow_margin, available.bottom() - height + 1),
        ))
        popup.setGeometry(geometry)
        if view.currentIndex().isValid():
            view.scrollTo(view.currentIndex())


def character_combo_index(combo: QComboBox, character_key: str) -> int:
    """Find a character by canonical identity, never its display name."""
    for index in range(combo.count()):
        if getattr(combo.itemData(index), "key", None) == character_key:
            return index
    return -1


def select_character_combo_key(combo: QComboBox, character_key: str) -> bool:
    index = character_combo_index(combo, character_key)
    if index < 0:
        return False
    with QSignalBlocker(combo):
        combo.setCurrentIndex(index)
        combo.setToolTip(str(getattr(combo.currentData(), "label", "")))
    return True


def populate_character_combo(combo: QComboBox, characters, previous_key: str) -> str:
    """Shared selector projection, retaining selection and caller signal state."""
    rows = tuple(characters)
    with QSignalBlocker(combo):
        combo.clear()
        selected = 0
        for index, row in enumerate(rows):
            combo.addItem(row.label, row)
            combo.setItemData(index, row.label, Qt.ToolTipRole)
            if row.key == previous_key or (not previous_key and row.connected):
                selected = index
        combo.setCurrentIndex(selected)
        current = combo.currentData()
        combo.setToolTip(str(getattr(current, "label", "")))
        return str(getattr(current, "key", previous_key))


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
        else:
            # The same bounded decoder is used by the catalogue and real sheets.
            from app.modules.encyclopedia.services.image_service import ENCYCLOPEDIA_IMAGE_SERVICE
            pixmap = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(cover, self.size())
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


def _paint_disabled_tool_icon(button: QToolButton, *, smooth: bool = False) -> None:
    """Preserve indexed icon artwork when Qt suppresses disabled tool icons."""
    if button.isEnabled() or button.icon().isNull():
        return
    pixmap = button.icon().pixmap(button.iconSize(), QIcon.Normal)
    if pixmap.isNull():
        return
    painter = QPainter(button)
    if smooth:
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
    pixel_ratio = max(1.0, pixmap.devicePixelRatio())
    painter.drawPixmap(
        int((button.width() - pixmap.width() / pixel_ratio) / 2),
        int((button.height() - pixmap.height() / pixel_ratio) / 2),
        pixmap,
    )
    painter.end()


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
        _paint_disabled_tool_icon(self, smooth=True)


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
        _paint_disabled_tool_icon(self)


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


def _guide_metric_drawer_layout(frame: QFrame) -> QVBoxLayout:
    frame.setProperty("guideMetricDrawer", True)
    frame.setFixedHeight(UNITY_GUIDE_READING_METRICS_PX["normal_drawer_max_height"])
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(
        UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["xs"],
        UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["xs"],
    )
    layout.setSpacing(UNITY_SPACING_PX["xs"])
    apply_unity_panel_shadow(frame)
    return layout


class AtlasGuideReadingHeader(QFrame):
    """Shared UI shell for real Guide readers and the Dev UI, without game data."""

    summaryRequested = Signal(int)

    def __init__(self, title: str, *, image_path: str | Path | None = None,
                 category: str = "guide", overview: bool = False,
                 show_cover: bool = True,
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
        if show_cover and not overview:
            guide_icon.set_artwork(image_path, category=category)
        if not show_cover:
            guide_icon.hide()
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
            if show_cover:
                guide_icon.set_artwork(image_path, category=category)
            self.guide_title_label.setObjectName("GuideHeaderTitle")
            self.guide_title_label.setWordWrap(True)
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
        self._optional_sections = QWidget(self)
        self._optional_sections.setObjectName("GuideHeaderSectionHost")
        self._optional_sections_layout = QVBoxLayout(self._optional_sections)
        self._optional_sections_layout.setContentsMargins(0, 0, 0, 0)
        self._optional_sections_layout.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
        self._optional_sections.hide()
        right.addWidget(self._optional_sections)
        self.optional_section_buttons: dict[str, AtlasButton] = {}

        # Global progress spans the two independently expandable lower metrics.
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
        self.global_details_button.setToolTip("Afficher Préparation et Sommaire")
        self.global_details_button.setAccessibleName("Déplier la progression globale")
        overall_caption.addWidget(self.global_details_button, 0, Qt.AlignVCenter)
        overall_caption.addStretch(1)
        overall_caption.addWidget(self.global_progress_label)
        # Global progression is the parent disclosure. Its bar remains
        # visible; both independent child drawers live inside its body.
        self.progress_group = QFrame()
        self.progress_group.setObjectName("GuideHeaderProgressGroup")
        progress_layout = QVBoxLayout(self.progress_group)
        inset = UNITY_SPACING_PX["xs"]
        progress_layout.setContentsMargins(inset, inset, inset, inset)
        progress_layout.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
        progress_layout.addLayout(overall_caption)
        progress_layout.addWidget(self.global_progress_bar)
        right.addWidget(self.progress_group)

        self.global_details_panel = QFrame()
        self.global_details_panel.setObjectName("GuideGlobalDetailsPanel")
        details = QVBoxLayout(self.global_details_panel)
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
        self.global_details_rows = QWidget()
        self.global_details_rows.setObjectName("GuideGlobalCharacterProgress")
        self.global_details_layout = QVBoxLayout(self.global_details_rows)
        self.global_details_layout.setContentsMargins(0, 0, 0, 0)
        self.global_details_layout.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
        details.addWidget(self.global_details_rows)

        metrics = QHBoxLayout()
        metrics.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_column_spacing"])
        icon_size = UNITY_SIZES_PX["icon_small"]
        for is_preparation, title, symbol, bar_role, tooltip in (
            (True, "Préparation", "cube", "GuideCompactPreparationProgress", "Afficher Préparation"),
            (False, "Sommaire", "summary", "GuideCompactSummaryProgress", "Ouvrir Sommaire"),
        ):
            column = QWidget()
            column.setObjectName("GuideHeaderSectionHost")
            metric = QVBoxLayout(column)
            metric.setContentsMargins(0, 0, 0, 0)
            metric.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
            caption = QHBoxLayout()
            caption.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_caption_spacing"])
            icon = QLabel()
            icon.setPixmap(atlas_guide_symbol_icon(
                icon, symbol, size=icon_size, color=PALETTE["GREEN"],
            ).pixmap(icon_size, icon_size))
            icon.setFixedSize(icon_size, icon_size)
            caption.addWidget(icon)
            label = QLabel(title)
            caption.addWidget(label)
            button = AtlasGuideDisclosure()
            button.configure_compact()
            button.setToolTip(tooltip)
            button.setAccessibleName(f"Afficher {title}")
            caption.addWidget(button, 0, Qt.AlignVCenter)
            caption.addStretch(1)
            value = QLabel("—")
            value.setObjectName("GuideCompactMetricValue")
            caption.addWidget(value)
            metric.addLayout(caption)
            bar = configure_unity_progress_bar(
                QProgressBar(), object_name=bar_role,
                height_role="progress_secondary", expanding=True,
            )
            metric.addWidget(bar)
            if is_preparation:
                icon.setObjectName("GuideCompactMetricIconCube")
                label.setToolTip(title)
                self.preparation_column = column
                self.preparation_caption, self.preparation_icon = label, icon
                self.preparation_button, self.preparation_progress_label = button, value
                self.preparation_bar = bar
                self._preparation_description = ""
                self.preparation_drawer = QVBoxLayout()
                self.preparation_drawer.setContentsMargins(0, 0, 0, 0)
                metric.addLayout(self.preparation_drawer)
                metrics.addWidget(column, 1)
            else:
                self.summary_column = column
                self.summary_icon = icon
                self.summary_button, self.summary_progress_label = button, value
                self.summary_bar = bar
                summary_metric = metric

        self.summary_panel = QListWidget()
        self.summary_panel.setObjectName("GuideSummaryList")
        self.summary_panel.setAccessibleName("Sommaire du guide")
        self.summary_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.summary_panel.setTextElideMode(Qt.ElideRight)
        self.summary_panel.hide()
        self.summary_panel.currentRowChanged.connect(self._request_summary_row)
        self._summary_titles = ()
        self._summary_index = -1
        self._summary_provider = None
        self.summary_button.toggled.connect(self._set_summary_open)
        self.summary_drawer = QFrame()
        _guide_metric_drawer_layout(self.summary_drawer).addWidget(self.summary_panel, 1)
        self.summary_drawer.hide()
        summary_metric.addWidget(self.summary_drawer)
        metrics.addWidget(self.summary_column, 1)
        # Keep both progress bars at the same height regardless of open panels.
        metrics.setAlignment(self.preparation_column, Qt.AlignTop)
        metrics.setAlignment(self.summary_column, Qt.AlignTop)
        details.insertLayout(0, metrics)
        self.global_details_panel.setVisible(False)
        self.global_details_button.toggled.connect(self._set_global_details_open)
        progress_layout.addWidget(self.global_details_panel)
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
        if opened and self.summary_button.isChecked():
            self._refresh_summary_rows()
        self.global_details_panel.setVisible(opened)
        self.global_details_button.setAccessibleName(
            "Replier la progression globale" if opened else "Déplier la progression globale"
        )
        self.global_details_button.setToolTip(
            "Masquer Préparation et Sommaire" if opened
            else "Afficher Préparation et Sommaire"
        )

    def set_guide_title(self, title: str) -> None:
        """Keep the visible title and its full accessible hover text in sync."""
        self.guide_title_label.setText(title)
        self.guide_title_label.setToolTip(title)

    def set_overview_progress(self, completed: int, total: int, *, visible: bool = True) -> None:
        """Present real catalogue counts only; unavailable totals stay unknown."""
        self.global_progress_title.setVisible(visible)
        self.global_progress_label.setVisible(visible)
        self.global_progress_bar.setVisible(visible)
        set_unity_progress_counts(self.global_progress_bar, completed, total)
        self.global_progress_label.setText(f"{completed}/{total}" if total > 0 else "—")

    def set_global_detail_lines(self, lines: tuple[str, ...]) -> None:
        """Reuse the same indexed character lines across progress updates."""
        role = "GuidePreparationParticipantNeed" if lines else "GuidePreparationEmpty"
        texts = lines or ("Sélectionne un personnage pour afficher sa progression.",)
        layout = self.global_details_layout
        for index, text in enumerate(texts):
            item = layout.itemAt(index)
            label = item.widget() if item is not None else None
            if label is None:
                label = QLabel()
                label.setWordWrap(True)
                layout.addWidget(label)
            if label.objectName() != role:
                label.setObjectName(role)
                refresh_unity_widget_style(label)
            if label.text() != text:
                label.setText(text)
        while layout.count() > len(texts):
            item = layout.takeAt(layout.count() - 1)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def set_optional_section_count(self, name: str, count: str) -> bool:
        """Update only the caption; preserve drawer, scroll, focus and rows."""
        button = self.optional_section_buttons.get(name)
        if button is None:
            return False
        text = f"{name}  {count}" if count else name
        if button.text() != text:
            button.setText(text)
        return True

    def set_optional_sections(
        self, sections: list[tuple[str, str, list[QWidget]]], *, preserve_open: bool = False,
    ) -> None:
        """Shared independent header drawers. Empty content owns no command."""
        opened = {
            name for name, button in self.optional_section_buttons.items()
            if preserve_open and button.isChecked()
        }
        clear_unity_widget_layout(self._optional_sections_layout, recursive=True, hide_widgets=True)
        self.optional_section_buttons.clear()
        available = [(name, count, rows) for name, count, rows in sections if rows]
        self._optional_sections.setVisible(bool(available))
        if not available:
            return
        commands = QHBoxLayout()
        commands.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_caption_spacing"])
        self._optional_sections_layout.addLayout(commands)
        # Keep simultaneously opened drawers on a single bounded row.
        # Three long lists must not stack to fill the entire reader.
        drawers = QHBoxLayout()
        drawers.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_column_spacing"])
        self._optional_sections_layout.addLayout(drawers)
        for name, count, rows in available:
            button = AtlasButton(f"{name}  {count}" if count else name)
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            button.setAccessibleName(name)
            commands.addWidget(button)
            self.optional_section_buttons[name] = button
            panel = configure_unity_scroll_area(QScrollArea(), borderless=True)
            panel.setObjectName("GuideHeaderSectionScroll")
            content = QWidget()
            content.setObjectName("GuideHeaderSectionHost")
            body = QVBoxLayout(content)
            body.setContentsMargins(0, 0, 0, 0)
            body.setSpacing(UNITY_LAYOUT_SIZES_PX["guide_metric_row_spacing"])
            for row in rows:
                body.addWidget(row)
            panel.setWidget(content)
            panel.setFixedHeight(min(
                UNITY_GUIDE_READING_METRICS_PX["normal_drawer_max_height"],
                max(UNITY_SIZES_PX["control_compact"], body.sizeHint().height()),
            ))
            drawers.addWidget(panel, 1, Qt.AlignTop)

            def sync(checked: bool, control=button, drawer=panel, label=name) -> None:
                control.setIcon(atlas_guide_arrow_icon("up" if checked else "down"))
                control.setToolTip(("Masquer " if checked else "Afficher ") + label)
                drawer.setVisible(checked)

            button.toggled.connect(sync)
            button.setChecked(name in opened)
            sync(button.isChecked())
        commands.addStretch(1)

    def set_metric_available(self, metric: str, available: bool) -> None:
        """Hide empty compact metrics and close their drawer before reusing it."""
        column = getattr(self, f"{metric}_column")
        button = getattr(self, f"{metric}_button")
        if not available:
            button.setChecked(False)
        column.setVisible(available)

    def set_summary_provider(self, provider: Callable[[], tuple[str, ...]]) -> None:
        self._summary_provider = provider
        if self.global_details_button.isChecked() and self.summary_button.isChecked():
            self._refresh_summary_rows()

    def _refresh_summary_rows(self) -> None:
        if self._summary_provider is None:
            return
        titles = tuple(self._summary_provider())
        with QSignalBlocker(self.summary_panel):
            if titles != self._summary_titles:
                self._summary_titles = titles
                self.summary_panel.clear()
                for index, title in enumerate(titles, 1):
                    text = f"{index}. {title}"
                    item = QListWidgetItem(text)
                    # Long authored titles remain readable in the narrow drawer;
                    # escape source text before passing it to Qt's rich tooltip.
                    item.setToolTip(f"<qt>{escape(text)}</qt>")
                    self.summary_panel.addItem(item)
            self.summary_panel.setCurrentRow(self._summary_index)

    def _request_summary_row(self, index: int) -> None:
        if 0 <= index < len(self._summary_titles):
            self.summaryRequested.emit(index)

    def _set_summary_open(self, opened: bool) -> None:
        if opened and self.global_details_button.isChecked():
            self._refresh_summary_rows()
        self.summary_panel.setVisible(opened)
        self.summary_drawer.setVisible(opened)
        action = "Masquer Sommaire" if opened else "Afficher Sommaire"
        self.summary_button.setAccessibleName(action)
        self.summary_button.setToolTip(action)

    def set_summary_position(self, index: int) -> None:
        self._summary_index = index
        self.summary_bar.setRange(self.global_progress_bar.minimum(), self.global_progress_bar.maximum())
        self.summary_bar.setValue(self.global_progress_bar.value())
        self.summary_progress_label.setText(self.global_progress_label.text())
        if self.global_details_button.isChecked() and self.summary_button.isChecked():
            self._refresh_summary_rows()

    def attach_preparation(self, panel: QWidget) -> None:
        self.preparation_drawer.addWidget(panel)
        panel.setVisible(self.preparation_button.isChecked())
        self.preparation_button.toggled.connect(panel.setVisible)
        self.preparation_button.toggled.connect(self._set_preparation_open)

    def set_preparation_description(self, description: str) -> None:
        """Keep a reader's source/availability notice across drawer toggles."""
        self._preparation_description = description
        self._set_preparation_open(self.preparation_button.isChecked())

    def _set_preparation_open(self, opened: bool) -> None:
        action = "Masquer Préparation" if opened else "Afficher Préparation"
        self.preparation_button.setAccessibleName(action)
        description = self._preparation_description
        self.preparation_button.setToolTip(
            f"{action} — {description}" if description else action
        )


def atlas_preparation_copy_button(name: str, display: str | None = None) -> AtlasButton:
    """Copy the real item name, independently of its visible presentation."""
    button = AtlasButton(name if display is None else display, size="compact")
    button.set_style_name("GuidePreparationItemCopy")
    button.setFlat(False)
    button.setToolTip(f"Cliquer pour copier : {name}")
    button.setAccessibleName(f"Copier {name}")
    button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    button.clicked.connect(lambda _checked=False: QApplication.clipboard().setText(name))
    return button


class AtlasGuidePreparationPanel(QFrame):
    """The real bounded preparation drawer, independent of the item model."""

    def __init__(self, categories: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuidePreparationPanel")
        panel_layout = _guide_metric_drawer_layout(self)
        self.category_filter = AtlasComboBox()
        self.category_filter.setObjectName("GuidePreparationCategoryFilter")
        self.category_filter.addItems(("Tout", *categories))
        self.category_filter.setFixedHeight(UNITY_SIZES_PX["control_compact"])
        self.category_filter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.category_filter.setToolTip("Filtrer les besoins de préparation")
        self.category_filter.setAccessibleName("Catégorie de préparation")
        panel_layout.addWidget(self.category_filter)

        self.scroll = configure_unity_scroll_area(QScrollArea(), borderless=True)
        self.scroll.setObjectName("GuidePreparationScroll")
        self.content = QWidget()
        self.content.setObjectName("GuidePreparationContent")
        self.rows_layout = QVBoxLayout(self.content)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(UNITY_SPACING_PX["xxs"])
        self.scroll.setWidget(self.content)
        panel_layout.addWidget(self.scroll, 1)

    def fit_content_height(self, *, scroll_position: int = 0) -> None:
        self.rows_layout.activate()
        self.content.adjustSize()
        self.scroll.verticalScrollBar().setValue(scroll_position)


class AtlasGuidePreparationSummary(QFrame):
    """One category title/count bar for real preparation and the gallery."""

    def __init__(self, category: str, *, ready: int, total: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuidePreparationSummary")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["xxs"],
            UNITY_SPACING_PX["sm"], UNITY_SPACING_PX["xxs"],
        )
        title = QLabel(category)
        title.setObjectName("GuidePreparationSummaryTitle")
        layout.addWidget(title)
        layout.addStretch(1)
        self.count_label = QLabel()
        self.count_label.setObjectName("GuidePreparationSummaryCount")
        layout.addWidget(self.count_label)
        self.set_counts(ready, total)

    def set_counts(self, ready: int, total: int) -> None:
        self.count_label.setText(f"{ready} / {total} prêts")


class AtlasGuidePreparationRow(QFrame):
    """One preparation row for Dev UI and live Guides; the host owns persistence."""

    def __init__(
        self, name: str, *, quantity: int | None, owned: int = 0,
        confirmed: int = 0, participants: int = 1,
        stock_formatter: Callable[..., tuple[str, str]],
        name_button: AtlasButton | None = None, parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("GuidePreparationRow")
        self._stock_formatter = stock_formatter
        self._confirmed = confirmed
        self._participants = participants
        self._ready = bool(participants and confirmed == participants)
        self.body_layout = QVBoxLayout(self)
        self.body_layout.setContentsMargins(UNITY_SPACING_PX["xs"], 0, UNITY_SPACING_PX["xs"], 0)
        self.body_layout.setSpacing(UNITY_SPACING_PX["xxs"])
        self.row_layout = QHBoxLayout()
        self.row_layout.setSpacing(UNITY_SPACING_PX["xs"])
        self.body_layout.addLayout(self.row_layout)

        self.ready_button = QCheckBox()
        self.ready_button.setObjectName("GuidePreparationReady")
        self.ready_button.setAccessibleName(f"Valider {name}")
        self.ready_button.setToolTip("Confirmer Prêt")
        self.ready_button.setCursor(Qt.PointingHandCursor)
        self.ready_button.setFixedWidth(UNITY_CONTROL_SIZES_PX["guide_validation_width"])
        self.ready_button.setChecked(self._ready)
        self.row_layout.addWidget(self.ready_button, 0, Qt.AlignVCenter)

        self.quantity_editor: QSpinBox | None = None
        if quantity is not None and quantity > 0:
            counter = configure_unity_number_spinbox(
                QSpinBox(), minimum=0, maximum=int(quantity),
                value=max(0, int(owned)),
                object_name="GuidePreparationQuantity", suffix=f"/{quantity}",
                tooltip="Quantité déjà possédée (brouillon de cette session)", compact=True,
            )
            self.quantity_editor = counter
            self.row_layout.addWidget(counter, 0, Qt.AlignVCenter)
        else:
            placeholder = QLabel("—")
            placeholder.setObjectName("GuidePreparationQuantityPlaceholder")
            placeholder.setFixedWidth(UNITY_CONTROL_SIZES_PX["guide_quantity_width"])
            placeholder.setAlignment(Qt.AlignCenter)
            self.row_layout.addWidget(placeholder, 0, Qt.AlignVCenter)

        self.name_button = name_button if name_button is not None else atlas_preparation_copy_button(name)
        self.row_layout.addWidget(self.name_button, 1, Qt.AlignVCenter)
        self.status_label = QLabel()
        self.status_label.setObjectName("GuidePreparationRowStatus")
        self.row_layout.addWidget(self.status_label, 0, Qt.AlignVCenter)
        if self.quantity_editor is not None:
            self.quantity_editor.valueChanged.connect(self._refresh_status)
        self._refresh_status()

    def _refresh_status(self, _changed: int | None = None) -> None:
        counter = self.quantity_editor
        if counter is not None:
            text, tooltip = self._stock_formatter(
                counter.maximum(), counter.value(), ready=self._ready,
                confirmed=self._confirmed, participants=self._participants,
            )
        else:
            text = "Prêt" if self._ready else f"{self._confirmed}/{self._participants} prêts"
            tooltip = text
        if self.status_label.text() != text:
            self.status_label.setText(text)
        if self.status_label.toolTip() != tooltip:
            self.status_label.setToolTip(tooltip)
        ready_state = "true" if self._ready else "false"
        set_unity_widget_property(self.status_label, "ready", ready_state)
        set_unity_widget_property(self, "ready", ready_state)

    def attach_details(self, provider: Callable[[], tuple[str, ...]]) -> QToolButton:
        """Build participant details only on first expansion; preserve them on checks."""
        button = configure_unity_tool_button(
            QToolButton(), object_name="GuidePreparationDetailsButton",
            pointing=True, focus_policy=Qt.StrongFocus,
        )
        button.setArrowType(Qt.RightArrow)
        button.setCheckable(True)
        button.setAccessibleName("Détails de préparation")
        button.setToolTip("Afficher les détails de préparation")
        self.row_layout.addWidget(button)
        details = QFrame()
        details.setObjectName("GuidePreparationDetails")
        layout = QVBoxLayout(details)
        geometry = UNITY_MODULE_GEOMETRY_PX["guide_reading_header"]
        layout.setContentsMargins(*geometry["preparation_detail_margins"])
        layout.setSpacing(UNITY_SPACING_PX["xxs"])
        details.hide()
        self.body_layout.addWidget(details)

        def toggle(opened: bool) -> None:
            if opened and not layout.count():
                for text in provider():
                    label = QLabel(text)
                    label.setObjectName("GuidePreparationParticipantNeed")
                    label.setWordWrap(True)
                    layout.addWidget(label)
            details.setVisible(opened)
            button.setArrowType(Qt.DownArrow if opened else Qt.RightArrow)
            button.setToolTip(("Masquer" if opened else "Afficher") + " les détails de préparation")

        button.toggled.connect(toggle)
        return button

    def set_saved_state(self, *, confirmed: int, participants: int, owned: int | None = None) -> None:
        """Refresh widgets in place without emitting a second save request."""
        self._confirmed = confirmed
        self._participants = participants
        self._ready = bool(participants and confirmed == participants)
        with QSignalBlocker(self.ready_button):
            self.ready_button.setChecked(self._ready)
        counter = self.quantity_editor
        if counter is not None and owned is not None:
            restore_unity_number_value(counter, max(0, min(counter.maximum(), int(owned))))
        self._refresh_status()


class AtlasGuideValidationButton(AtlasButton):
    """Shared checkable page action; no progression writes in the widget."""

    def __init__(self, text: str = "Valider", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.set_style_name("GuideManualPageCheck")
        self.setCheckable(True)


class AtlasGuideReadingNav(QFrame):
    """Actual three-action reading footer shared with the Dev UI gallery."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideManualNav")
        geometry = UNITY_MODULE_GEOMETRY_PX["guide_reading_header"]
        nav_layout = QHBoxLayout(self)
        nav_layout.setContentsMargins(*geometry["footer_margins"])
        nav_layout.setSpacing(geometry["footer_gap"])
        icon_size = geometry["back_icon"]
        self.previous_button = AtlasButton("Précédent")
        self.previous_button.set_style_name("GuideManualPrev")
        self.previous_button.setIcon(atlas_guide_arrow_icon("left"))
        self.previous_button.setIconSize(QSize(icon_size, icon_size))
        nav_layout.addWidget(self.previous_button)
        nav_layout.addStretch(1)
        self.validation_host = QFrame()
        self.validation_host.setObjectName("GuideManualValidationHost")
        self.validation_layout = QHBoxLayout(self.validation_host)
        self.validation_layout.setContentsMargins(0, 0, 0, 0)
        self.validation_layout.setSpacing(0)
        nav_layout.addWidget(self.validation_host)
        nav_layout.addStretch(1)
        self.next_button = AtlasButton("Suivant")
        self.next_button.set_style_name("GuideManualNextButton")
        self.next_button.setIcon(atlas_guide_arrow_icon("right"))
        self.next_button.setIconSize(QSize(icon_size, icon_size))
        nav_layout.addWidget(self.next_button)
        apply_unity_panel_shadow(self)


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
        total = max(0, int(total))
        configure_unity_number_spinbox(
            self.page_jump, minimum=1 if total else 0, maximum=total,
            value=max(1, min(page, total)) if total else 0, suffix=f"/{total}",
        )
        self.page_jump.setEnabled(total > 0)


class AtlasPageTitle(QLabel):
    """Shared page heading using the canonical PageTitle theme token."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("PageTitle")


class AtlasUnavailablePage(QWidget):
    """Shared honest unavailable-module surface; no business runtime loaded."""

    def __init__(
        self, title: str, message: str, *, badge: str = "",
        object_name: str = "PlaceholderPage", message_role: str = "CompactLabel",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        geometry = UNITY_MODULE_GEOMETRY_PX["unavailable_page"]
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*geometry["margins"])
        layout.setSpacing(geometry["spacing"])
        self.heading = AtlasPageTitle(title)
        layout.addWidget(self.heading)
        self.badge = AtlasStatusBadge(badge, state="blocked") if badge else None
        if self.badge is not None:
            layout.addWidget(self.badge, 0, Qt.AlignLeft)
        self.message_label = QLabel(message)
        self.message_label.setObjectName(message_role)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)
        layout.addStretch(1)


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
) -> bool:
    """Present at most one dialog per slot, respecting a refused close."""
    if mode not in ("show", "open"):
        raise ValueError(f"Unknown dialog presentation mode: {mode}")
    current = getattr(owner, attribute, None)
    if current is dialog:
        return True
    if current is not None and not current.close():
        # In particular Craft can refuse to close while resources are in
        # progress. Do not orphan it or report the new dialog as presented.
        dialog.deleteLater()
        return False
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
    return True


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
