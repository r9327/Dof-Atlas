from __future__ import annotations

from math import cos, pi, sin
from functools import lru_cache

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from app.constants import (
    ICON_PATH,
    KEY_CLICK_HOTKEY,
    KEY_DEBUG_MODE,
    KEY_ORGANIZER_MACRO_MODE,
    KEY_DOUBLE_CLICK_HOTKEY,
    KEY_PRIMARY_WINDOW,
    KEY_RADIAL_HOTKEY,
    KEY_RADIAL_ENABLED,
    KEY_NEXT_CHARACTER_HOTKEY,
    KEY_PREVIOUS_CHARACTER_HOTKEY,
    KEY_MIRROR_TOGGLE_HOTKEY,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_SWITCH_CHARACTER,
    KEY_SWITCH_CLICK,
    KEY_SWITCH_DOUBLE_CLICK,
    KEY_SWITCH_MOVEMENT,
)
from app.storage import ZaapWidget, clean_auto_group_name, profile_bool, short_label
from app.ui.splash_image import clear_connected_dark_background
from app.ui.theme import render_theme_template
from app.ui.components import AtlasButton
from .glass_material import (
    OrganizerGlassButton, OrganizerGlassCard, unity_glass_gradient,
)
from .common import (
    BUTTON_HEIGHT,
    CARD_PADDING,
    CARD_SPACING,
    CHARACTER_SLOT_HEIGHT,
    DOFUS_CLASS_DEFINITIONS,
    KEY_BADGE_HEIGHT,
    SESSION_SLOT_COUNT,
    class_icon_candidates,
    dofus_class_key_from_window_name,
    empty_session_slot,
    session_hwnd,
    session_is_detected,
    session_is_empty,
    session_name,
)


@lru_cache(maxsize=48)
def _organizer_class_pixmap(path: str) -> QPixmap:
    """Remove only edge-connected near-black icon backgrounds, once per file."""
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return pixmap
    cleaned = clear_connected_dark_background(pixmap.toImage())
    return QPixmap.fromImage(cleaned).scaled(
        22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation,
    )


def _organizer_grip_icon() -> QIcon:
    pixmap = QPixmap(20, 24)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#B5C6DA"))
    for row in (5, 12, 19):
        for col in (6, 14):
            painter.drawEllipse(QPointF(col, row), 1.5, 1.5)
    painter.end()
    return QIcon(pixmap)


def _organizer_favorite_icon(selected: bool) -> QIcon:
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.transparent)
    vertices = [
        QPointF(
            12 + (9.0 if i % 2 == 0 else 4.1) * cos(-pi / 2 + i * pi / 5),
            12 + (9.0 if i % 2 == 0 else 4.1) * sin(-pi / 2 + i * pi / 5),
        )
        for i in range(10)
    ]
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#E7B850" if selected else "#AABACD"), 1.5))
    painter.setBrush(QColor("#E7B850") if selected else Qt.NoBrush)
    painter.drawPolygon(QPolygonF(vertices))
    painter.end()
    return QIcon(pixmap)


def _organizer_warning_icon() -> QIcon:
    """Draw the warning mark rather than relying on missing Unicode glyphs."""
    pixmap = QPixmap(26, 26)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#FFF0B2"), 1.4))
    painter.setBrush(QColor("#E7AB32"))
    painter.drawPolygon(QPolygonF([
        QPointF(13, 3), QPointF(24, 22), QPointF(2, 22),
    ]))
    painter.setPen(QPen(QColor("#39240C"), 2.3, Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(13, 9), QPointF(13, 15))
    painter.drawPoint(QPointF(13, 19))
    painter.end()
    return QIcon(pixmap)


def _organizer_refresh_icon() -> QIcon:
    """Antialiased refresh arrow visible with all fonts and DPI settings."""
    pixmap = QPixmap(28, 28)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#D7E6F1"), 2.3, Qt.SolidLine, Qt.RoundCap))
    painter.drawArc(QRectF(5.0, 5.0, 18.0, 18.0), 45 * 16, 290 * 16)
    painter.drawLine(QPointF(20.5, 4.8), QPointF(23.0, 11.2))
    painter.drawLine(QPointF(23.0, 11.2), QPointF(16.2, 10.3))
    painter.end()
    return QIcon(pixmap)


def _organizer_action_icon(kind: str) -> QIcon:
    """Compact antialiased icons; no platform-font glyph dependencies."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#E3EEF9"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    if kind == "radial":
        # Monochrome pie, aligned with the other white action pictograms.
        painter.setBrush(Qt.NoBrush)
        for index in range(8):
            painter.setPen(QPen(QColor("#E3EEF9"), 1.7, Qt.SolidLine, Qt.RoundCap))
            painter.drawPie(QRectF(4, 4, 24, 24), index * 45 * 16, 45 * 16)
        painter.setBrush(QColor("#E3EEF9"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRectF(13, 13, 6, 6))
    elif kind == "macro":
        # Three stacked plates: mode Macro, not the radial selector.
        painter.setBrush(Qt.NoBrush)
        for y in (6, 11, 16):
            painter.drawPolyline(QPolygonF([
                QPointF(4, y), QPointF(16, y + 7),
                QPointF(28, y), QPointF(16, y - 7), QPointF(4, y),
            ]))
    elif kind == "mirror":
        # Overlapping window outlines signal actions mirrored to another client.
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(4, 4, 18, 18), 2, 2)
        painter.drawRoundedRect(QRectF(10, 10, 18, 18), 2, 2)
        painter.drawLine(QPointF(15, 16), QPointF(23, 16))
    elif kind == "group":
        painter.drawEllipse(QRectF(5, 7, 8, 8))
        painter.drawEllipse(QRectF(19, 7, 8, 8))
        painter.drawArc(QRectF(3, 16, 13, 11), 0, 180 * 16)
        painter.drawArc(QRectF(16, 16, 13, 11), 0, 180 * 16)
    elif kind == "switch":
        painter.drawLine(QPointF(5, 11), QPointF(26, 11))
        painter.drawLine(QPointF(22, 7), QPointF(26, 11))
        painter.drawLine(QPointF(26, 11), QPointF(22, 15))
        painter.drawLine(QPointF(27, 21), QPointF(6, 21))
        painter.drawLine(QPointF(10, 17), QPointF(6, 21))
        painter.drawLine(QPointF(6, 21), QPointF(10, 25))
    elif kind == "move":
        painter.drawLine(QPointF(16, 4), QPointF(16, 28))
        painter.drawLine(QPointF(4, 16), QPointF(28, 16))
        for end, a, b in (
            (QPointF(16, 4), QPointF(12, 9), QPointF(20, 9)),
            (QPointF(16, 28), QPointF(12, 23), QPointF(20, 23)),
            (QPointF(4, 16), QPointF(9, 12), QPointF(9, 20)),
            (QPointF(28, 16), QPointF(23, 12), QPointF(23, 20)),
        ):
            painter.drawLine(end, a)
            painter.drawLine(end, b)
    elif kind == "click":
        painter.setBrush(QColor("#B9D3ED"))
        painter.drawPolygon(QPolygonF([
            QPointF(6, 4), QPointF(8, 25), QPointF(13, 19),
            QPointF(19, 27), QPointF(23, 24),
            QPointF(17, 16), QPointF(25, 14),
        ]))
    elif kind == "double":
        painter.drawEllipse(QRectF(4, 4, 17, 17))
        painter.drawEllipse(QRectF(11, 11, 17, 17))
        painter.drawLine(QPointF(16, 8), QPointF(16, 13))
        painter.drawLine(QPointF(8, 16), QPointF(13, 16))
    elif kind == "debug":
        painter.drawEllipse(QRectF(10, 10, 12, 15))
        painter.drawLine(QPointF(12, 11), QPointF(9, 6))
        painter.drawLine(QPointF(20, 11), QPointF(23, 6))
        for y in (13, 19, 25):
            painter.drawLine(QPointF(10, y), QPointF(5, y - 2))
            painter.drawLine(QPointF(22, y), QPointF(27, y - 2))
    painter.end()
    return QIcon(pixmap)


def _organizer_card_shadow(panel: QFrame) -> None:
    """Subtle Unity-style separation, never a black-filled backing rectangle."""
    shadow = QGraphicsDropShadowEffect(panel)
    shadow.setBlurRadius(18)
    shadow.setOffset(0, 3)
    shadow.setColor(QColor(5, 16, 34, 75))
    panel.setGraphicsEffect(shadow)


class OrganizerZaapWidget(ZaapWidget):
    """Use painted, DPI-safe favorite stars only in Organizer."""

    def refresh_favorite_chips(self) -> None:
        super().refresh_favorite_chips()
        for star in self.favorite_star_buttons:
            star.setText("")
            star.setIcon(_organizer_favorite_icon(True))
            star.setIconSize(QSize(15, 15))
            star.setAccessibleName(star.toolTip())


class CharacterSlotsPanel(OrganizerGlassCard):
    """Organizer character card sized from the slot grid instead of a magic cap."""

    def __init__(
        self,
        refresh_button: QWidget,
        *,
        slot_count: int = SESSION_SLOT_COUNT,
        row_height: int = CHARACTER_SLOT_HEIGHT,
        columns: int = 2,
        horizontal_spacing: int = 8,
        vertical_spacing: int = 6,
        card_padding: int = CARD_PADDING,
        card_spacing: int = CARD_SPACING,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if columns <= 0:
            raise ValueError("columns must be greater than zero")
        self.slot_count = max(0, int(slot_count))
        self.row_height = max(0, int(row_height))
        self.columns = int(columns)
        self.vertical_spacing = max(0, int(vertical_spacing))

        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.panel_layout = QVBoxLayout(self)
        self.panel_layout.setContentsMargins(card_padding, card_padding, card_padding, card_padding)
        self.panel_layout.setSpacing(card_spacing)

        self.title = QLabel("Personnage")
        self.title.setObjectName("cardTitle")
        self.title.setFixedHeight(20)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        accent = QFrame()
        accent.setObjectName("CardTitleAccent")
        accent.setFixedSize(3, 16)
        header.addWidget(accent, alignment=Qt.AlignVCenter)
        header.addWidget(self.title, alignment=Qt.AlignVCenter)
        header.addStretch(1)
        header.addWidget(refresh_button, alignment=Qt.AlignVCenter)
        self.panel_layout.addLayout(header)

        self.content = QWidget()
        self.content.setObjectName("OrganizerTransparentHost")
        self.content.setStyleSheet("QWidget#OrganizerTransparentHost { background: transparent; border: none; }")
        self.content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(horizontal_spacing)
        self.grid.setVerticalSpacing(self.vertical_spacing)
        for column in range(self.columns):
            self.grid.setColumnStretch(column, 1)
        self.panel_layout.addWidget(self.content)
        self.content.setFixedHeight(self.slot_grid_height())
        self.setFixedHeight(self.calculated_height())

    def row_count(self) -> int:
        if not self.slot_count:
            return 0
        return (self.slot_count + self.columns - 1) // self.columns

    def slot_grid_height(self) -> int:
        rows = self.row_count()
        if not rows:
            return 0
        return rows * self.row_height + max(0, rows - 1) * self.vertical_spacing

    def header_height(self) -> int:
        item = self.panel_layout.itemAt(0)
        return max(self.title.height(), item.sizeHint().height() if item is not None else 0)

    def calculated_height(self) -> int:
        margins = self.panel_layout.contentsMargins()
        return (
            margins.top()
            + self.header_height()
            + self.panel_layout.spacing()
            + self.slot_grid_height()
            + margins.bottom()
        )

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(hint.width(), self.calculated_height())

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(hint.width(), self.calculated_height())

    def grid_position(self, slot_index: int) -> tuple[int, int]:
        return divmod(int(slot_index), self.columns)

    def add_slot(self, widget: QWidget, slot_index: int) -> None:
        row, column = self.grid_position(slot_index)
        self.grid.addWidget(widget, row, column)

    def clear_slots(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class OrganizerSpeedSelector(QFrame):
    """One flat 3-stop track with a sliding highlight, not three separate cards.

    Reuses the existing speed actions and profile keys. The highlight is purely
    visual, so it never changes speed before the corresponding click callback.
    """

    PRESETS = ("normal", "rapide", "instantane")

    def __init__(self, normal: QPushButton, rapid: QPushButton,
                 instant: QPushButton, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("OrganizerSpeedSelector")
        self.setFixedHeight(BUTTON_HEIGHT)
        self._choices = (normal, rapid, instant)
        self._selected: int | None = None
        self.highlight = QFrame(self)
        self.highlight.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.highlight.setObjectName("OrganizerSpeedHighlight")
        self.highlight.hide()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        for button in self._choices:
            button.setObjectName("OrganizerSpeedChoice")
            button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            button.setMinimumWidth(0)
            layout.addWidget(button, 1)
        self.highlight.lower()
        self._motion = QPropertyAnimation(self.highlight, b"pos", self)
        self._motion.setDuration(145)
        self._motion.setEasingCurve(QEasingCurve.OutCubic)

    def set_selected(self, preset: str) -> None:
        previous = self._selected
        self._selected = self.PRESETS.index(preset) if preset in self.PRESETS else None
        for index, button in enumerate(self._choices):
            button.setObjectName(
                "OrganizerSpeedChoiceSelected" if self._selected == index
                else "OrganizerSpeedChoice"
            )
            button.style().unpolish(button)
            button.style().polish(button)
        self._position_highlight(animated=previous is not None and previous != self._selected)

    def _position_highlight(self, *, animated: bool = False) -> None:
        self._motion.stop()
        if self._selected is None:
            self.highlight.hide()
            return
        self.layout().activate()
        target = self._choices[self._selected].geometry()
        if target.width() <= 0:
            return
        self.highlight.setFixedSize(target.size())
        if animated and self.isVisible() and self.highlight.isVisible():
            self._motion.setStartValue(self.highlight.pos())
            self._motion.setEndValue(target.topLeft())
            self._motion.start()
        else:
            self.highlight.move(target.topLeft())
        self.highlight.lower()
        self.highlight.show()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._selected is not None:
            self._position_highlight()


class OrganizerModeSwitch(QFrame):
    """Two mode actions presented as a single sliding switch surface.

    The Miroir half keeps its existing embedded hotkey and arm callback.
    Highlight position represents the selected mode, not permission to
    inject mirrored input; the runtime still handles explicit arming.
    """

    def __init__(self, macro: QPushButton, mirror_cell: QWidget) -> None:
        super().__init__()
        self.setObjectName("OrganizerModeSwitch")
        # Match the 194 + 8 + 194 grid exactly, including both column starts.
        self.setFixedSize(396, BUTTON_HEIGHT)
        self._choices = (macro, mirror_cell)
        self._selected = -1
        self.highlight = QFrame(self)
        self.highlight.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.highlight.setObjectName("OrganizerModeHighlight")
        layout = QHBoxLayout(self)
        # The borderless track and zero margins prevent a 1-2px offset
        # against the two 194px Macro/Quick-action columns.
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(macro)
        layout.addWidget(mirror_cell)
        self.highlight.lower()
        self._animation = QPropertyAnimation(self.highlight, b"pos", self)
        self._animation.setDuration(155)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

    def set_selected(self, mirror: bool, *, armed: bool = False) -> None:
        new = 1 if mirror else 0
        changed = self._selected >= 0 and self._selected != new
        self._selected = new
        self.highlight.setObjectName(
            "OrganizerModeHighlightArmed" if mirror and armed
            else "OrganizerModeHighlight"
        )
        self.highlight.style().unpolish(self.highlight)
        self.highlight.style().polish(self.highlight)
        self._sync_highlight(animate=changed)

    def _sync_highlight(self, *, animate: bool = False) -> None:
        self._animation.stop()
        if self._selected < 0:
            return
        self.layout().activate()
        target = self._choices[self._selected].geometry()
        if target.width() <= 0:
            return
        self.highlight.setFixedSize(target.size())
        if animate and self.isVisible() and self.highlight.isVisible():
            self._animation.setStartValue(self.highlight.pos())
            self._animation.setEndValue(target.topLeft())
            self._animation.start()
        else:
            self.highlight.move(target.topLeft())
        self.highlight.lower()
        self.highlight.show()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._selected >= 0:
            self._sync_highlight()


class OrganizerUiMixin:
    def build_organizer_ui(self, status_callback, launch_zaap_callback) -> None:
        # The active /zaap sender uses the destination command directly.
        # Keep legacy calibration data readable but hide its obsolete
        # position/lock/calibrate widgets on the Organizer page.
        self.zaap = OrganizerZaapWidget(
            status_callback, launch_zaap_callback, self.refresh_sessions_and_export,
            show_position_controls=False,
            compact_favorites=True,
            compact_favorite_columns=2,
        )
        self.zaap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.zaap.setObjectName("OrganizerZaapContent")

        # Organizer scrolls its own content; Atlas navigation stays fixed.
        self.organizer_scroll = QScrollArea(self)
        self.organizer_scroll.setObjectName("OrganizerContentScroll")
        self.organizer_scroll.setFrameShape(QFrame.NoFrame)
        self.organizer_scroll.setWidgetResizable(True)
        self.organizer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.organizer_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.organizer_scroll)
        self.organizer_scroll.viewport().setObjectName("OrganizerContentViewport")
        content = QWidget()
        content.setObjectName("OrganizerScrollContent")
        self.organizer_scroll.setWidget(content)
        # Unity's shared yellow/green button border sprites have deep
        # baked-in shadows. Organizer uses flat themed button surfaces only;
        # do not remove these sprites from the other application modules.
        # The colors come from Unity's single palette; the material adds
        # cached background diffusion + edge glints, not a blue repaint.
        glass_qss = """
            #organizerPage QFrame#card {
                /* GlassCard paints a cached diffused backdrop and specular
                   rim; QSS cannot render a frosted material on its own. */
                background: transparent;
                border: none;
                border-radius: 10px;
                border-image: none;
            }
            #organizerPage QPushButton#primaryButton,
            #organizerPage QPushButton#secondaryButton,
            #organizerPage QPushButton#PrimaryActionButton,
            #organizerPage QPushButton#SecondaryButton,
            #organizerPage QPushButton#segmentedButton,
            #organizerPage QPushButton#segmentedButtonActive,
            #organizerPage QPushButton#dangerButton {
                background: @GLASS_BUTTON;
                border: 1px solid @BORDER;
                border-radius: 8px;
                border-image: none;
                color: @TEXT_SOFT;
                text-align: center;
                padding: 0px 5px;
            }
            #organizerPage QPushButton#primaryButton,
            #organizerPage QPushButton#PrimaryActionButton,
            #organizerPage QPushButton#segmentedButtonActive {
                background: @GLASS_GREEN;
                border-color: @GREEN_BORDER;
                color: @TEXT;
            }
            #organizerPage QPushButton#dangerButton {
                background: @RED_DARK;
                border-color: @RED;
                color: @TEXT;
                font-weight: 700;
            }
            #organizerPage QPushButton#primaryButton:hover,
            #organizerPage QPushButton#secondaryButton:hover,
            #organizerPage QPushButton#PrimaryActionButton:hover,
            #organizerPage QPushButton#SecondaryButton:hover,
            #organizerPage QPushButton#segmentedButton:hover,
            #organizerPage QPushButton#segmentedButtonActive:hover {
                background: @GLASS_HOVER;
                border-color: @BORDER_STRONG;
                color: @TEXT;
            }
            #organizerPage QPushButton#primaryButton:pressed,
            #organizerPage QPushButton#secondaryButton:pressed,
            #organizerPage QPushButton#PrimaryActionButton:pressed,
            #organizerPage QPushButton#SecondaryButton:pressed,
            #organizerPage QPushButton#segmentedButton:pressed,
            #organizerPage QPushButton#segmentedButtonActive:pressed {
                background: @PANEL_ACTIVE;
                border-color: @GREEN_BORDER;
            }
            #organizerPage QPushButton#dangerButton:hover {
                background: @RED_HOVER;
                border-color: @RED;
            }
            #organizerPage QPushButton#dangerButton:pressed {
                background: @RED_DARK;
                border-color: @RED;
            }
            #organizerPage QPushButton#primaryButton:disabled,
            #organizerPage QPushButton#secondaryButton:disabled,
            #organizerPage QPushButton#PrimaryActionButton:disabled,
            #organizerPage QPushButton#SecondaryButton:disabled,
            #organizerPage QPushButton#segmentedButton:disabled,
            #organizerPage QPushButton#segmentedButtonActive:disabled,
            #organizerPage QPushButton#dangerButton:disabled {
                background: @PANEL;
                border-color: @BORDER_SOFT;
                color: @TEXT_DISABLED;
            }
            /* All seven embedded shortcuts, STOP and character slots are
               the SAME keyBadge family and 52x22 dimensions. */
            #organizerPage QPushButton#keyBadge {
                background: @GLASS_BUTTON;
                border: 1px solid @BORDER_STRONG;
                border-radius: 6px;
                border-image: none;
                color: @TEXT;
                font-size: 10px;
                font-weight: 700;
                min-width: 0px;
                /* 20px content + 2px borders = exact 22px Qt badge.
                   A zero min-height allowed Qt to shrink them to 12px. */
                min-height: 20px;
                max-height: 20px;
                padding: 0px 2px;
                text-align: center;
            }
            #organizerPage QPushButton#keyBadge:hover {
                background: @GLASS_HOVER;
                border-color: @GREEN_BORDER;
            }
            #organizerPage QPushButton#keyBadge:pressed {
                background: @GREEN_DARK;
                border-color: @GREEN;
            }
            #organizerPage QPushButton#keyBadge:disabled {
                background: @PANEL;
                border-color: @BORDER_SOFT;
                color: @TEXT_DISABLED;
            }
            #organizerPage QPushButton#iconButton,
            #organizerPage QPushButton#iconButtonDanger {
                background: @GLASS_BUTTON;
                border: 1px solid @BORDER;
                border-radius: 6px;
                border-image: none;
                color: @TEXT_SOFT;
                padding: 0px;
            }
            #organizerPage QPushButton#iconButton:hover,
            #organizerPage QPushButton#iconButtonDanger:hover {
                background: @GLASS_HOVER;
                border-color: @BORDER_STRONG;
            }
            #organizerPage QPushButton#iconButton:disabled,
            #organizerPage QPushButton#iconButtonDanger:disabled {
                background: @PANEL;
                color: @TEXT_DISABLED;
                border-color: @BORDER_SOFT;
            }
            #organizerPage QWidget#OrganizerTransparentHost {
                background: transparent;
                border: none;
                border-image: none;
            }
            #organizerPage QLineEdit#comboField {
                background: @PANEL_2;
                border: 1px solid @BORDER;
                border-radius: 8px;
                border-image: none;
                color: @TEXT;
                padding: 0px 8px;
            }
            #organizerPage QLineEdit#comboField:focus {
                background: @PANEL_HOVER;
                border-color: @GREEN;
            }
            #organizerPage QFrame#OrganizerSpeedSelector,
            #organizerPage QFrame#OrganizerModeSwitch {
                background: @PANEL;
                border: none;
                border-radius: 8px;
                border-image: none;
            }
            #organizerPage QFrame#OrganizerSpeedHighlight,
            #organizerPage QFrame#OrganizerModeHighlight {
                background: @GREEN_DARK;
                border: 1px solid @GREEN_BORDER;
                border-radius: 7px;
                border-image: none;
            }
            #organizerPage QFrame#OrganizerModeHighlightArmed {
                background: @ACTIVE_GRADIENT;
                border: 1px solid @GREEN;
                border-radius: 7px;
                border-image: none;
            }
            #organizerPage QPushButton#OrganizerSpeedChoice,
            #organizerPage QPushButton#OrganizerSpeedChoiceSelected,
            #organizerPage QPushButton#OrganizerModeChoice {
                background: transparent;
                border: none;
                border-image: none;
                border-radius: 6px;
                padding: 0px 2px;
                color: @TEXT_SOFT;
                font-size: 11px;
                font-weight: 600;
                min-height: 0px;
            }
            #organizerPage QPushButton#OrganizerSpeedChoiceSelected {
                color: @TEXT;
                font-weight: 700;
            }
            #organizerPage QScrollArea#OrganizerContentScroll,
            #organizerPage QScrollArea#OrganizerZaapScroll,
            #organizerPage QWidget#OrganizerContentViewport,
            #organizerPage QWidget#OrganizerZaapViewport,
            #organizerPage QWidget#OrganizerScrollContent,
            #organizerPage QWidget#OrganizerZaapContent,
            #organizerPage QWidget#ZaapFavoritesRow {
                background: transparent;
                border: none;
                border-image: none;
            }
            #organizerPage QWidget#favoriteChip {
                background: @GLASS_BUTTON;
                border: 1px solid @BORDER_CARD;
                border-radius: 8px;
                border-image: none;
            }
            #organizerPage QWidget#favoriteChip:hover {
                background: @GLASS_HOVER;
                border-color: @BORDER_STRONG;
            }
            #organizerPage QFrame#characterSlotEmpty,
            #organizerPage QFrame#characterSlotMissing {
                background: @PANEL;
                border: 1px solid @BORDER_SOFT;
                border-radius: 8px;
                border-image: none;
            }
            #organizerPage QFrame#characterSlot {
                background: @PANEL_2;
                border: 1px solid @BORDER;
                border-radius: 8px;
                border-image: none;
            }
            #organizerPage QFrame#characterSlotDragging,
            #organizerPage QFrame#characterSlotDropTarget {
                background: @PANEL_ACTIVE;
                border: 1px solid @GREEN_BORDER;
                border-radius: 8px;
                border-image: none;
            }
            #organizerPage QFrame#characterSlot QPushButton#FavoriteButton,
            #organizerPage QFrame#characterSlot QPushButton#FavoriteButtonActive {
                background: @PANEL_HOVER;
                border: 1px solid @BORDER;
                border-radius: 6px;
                border-image: none;
            }
            #organizerPage QFrame#characterSlot QPushButton#FavoriteButton:hover,
            #organizerPage QFrame#characterSlot QPushButton#FavoriteButtonActive:hover {
                background: @PANEL_ACTIVE;
                border-color: @GREEN_BORDER;
            }
        """
        glass_qss = (
            glass_qss
            .replace("@GLASS_BUTTON", unity_glass_gradient())
            .replace("@GLASS_HOVER", unity_glass_gradient(
                "PANEL_HOVER", "PANEL_ACTIVE", top_alpha=199, bottom_alpha=206,
            ))
            .replace("@GLASS_GREEN", unity_glass_gradient(
                "GREEN_DARK", "GREEN_DARK", top_alpha=196, bottom_alpha=218,
            ))
        )
        self.setStyleSheet(render_theme_template(glass_qss))
        root = QVBoxLayout(content)
        # Space for the lower rounded corners and drop shadows at all DPI.
        root.setContentsMargins(14, 12, 14, 20)
        root.setSpacing(12)
        root.setAlignment(Qt.AlignTop)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(10)
        accent = QFrame()
        accent.setObjectName("TitleAccent")
        accent.setFixedSize(4, 24)
        title = QLabel("Organizer")
        title.setObjectName("PageTitle")
        title.setFixedHeight(28)
        header.addWidget(accent, alignment=Qt.AlignVCenter)
        header.addWidget(title, alignment=Qt.AlignVCenter)
        self.runtime_status_dot = QLabel("●")
        self.runtime_status_dot.setObjectName("RuntimeStatusDot")
        self.runtime_status_dot.setFixedSize(14, 18)
        self.runtime_status_dot.setAlignment(Qt.AlignCenter)
        header.addWidget(self.runtime_status_dot, alignment=Qt.AlignVCenter)
        header.addStretch(1)
        root.addLayout(header)

        self.macro_mode_button = OrganizerGlassButton("Macro")
        self.mirror_mode_button = OrganizerGlassButton("Miroir")
        self.macro_mode_button.setFixedSize(194, BUTTON_HEIGHT)
        self.mirror_mode_button.setFixedSize(194, BUTTON_HEIGHT)
        self.macro_mode_button.setToolTip("Revenir aux macros classiques")
        self.mirror_mode_button.setToolTip("Activer ou arrêter Miroir")
        self.quick_actions_title = QLabel("Action rapide")
        self.quick_actions_title.setObjectName("cardTitle")
        self.quick_actions_title.setFixedHeight(BUTTON_HEIGHT)
        self.set_runtime_active(False)

        self.switch_character = OrganizerGlassButton("")
        self.switch_click = OrganizerGlassButton("")
        self.switch_double_click = OrganizerGlassButton("")
        self.switch_movement = OrganizerGlassButton("")
        self.next_character = OrganizerGlassButton("Suivant")
        self.previous_character = OrganizerGlassButton("Précédent")
        self.mirror_arm_button = OrganizerGlassButton("Activer Miroir")
        self.mirror_toggle_hotkey_button = OrganizerGlassButton("")
        self.mirror_toggle_clear = OrganizerGlassButton("x")
        self.switch_fake = OrganizerGlassButton("Auto-groupe")
        self.radial_select_button = OrganizerGlassButton("Sélection perso")
        self.radial_select_button.setAccessibleName("Sélection personnage")
        self.click_button = OrganizerGlassButton("")
        self.double_click_button = OrganizerGlassButton("")
        self.double_click_clear = OrganizerGlassButton("x")
        self.radial_hotkey_button = OrganizerGlassButton("")
        self.radial_clear = OrganizerGlassButton("x")
        self.next_character_hotkey_button = OrganizerGlassButton("")
        self.next_character_clear = OrganizerGlassButton("x")
        self.previous_character_hotkey_button = OrganizerGlassButton("")
        self.previous_character_clear = OrganizerGlassButton("x")
        self.reload_runtime_button = OrganizerGlassButton("Relancer scripts")
        self.debug_button = OrganizerGlassButton("Debug")
        self.script_speed_title = QLabel("Vitesse")
        self.script_speed_legacy = OrganizerGlassButton("Classique")
        self.script_speed_normal = OrganizerGlassButton("Normal")
        self.script_speed_fast = OrganizerGlassButton("Rapide")
        self.script_speed_instant = OrganizerGlassButton("Instantané")
        self.stop_script_button = OrganizerGlassButton("STOP URGENCE")
        self.stop_script_hotkey_button = OrganizerGlassButton("")
        self.stop_script_clear = OrganizerGlassButton("x")
        self.click_clear = OrganizerGlassButton("x")

        control_size = QSize(194, BUTTON_HEIGHT)
        # Use the same one-line control height as neighboring modules.
        radial_control_size = control_size
        # Extra bottom breathing room keeps Qt rounded borders/shadows visible.
        controls_panel_height = 146
        panel_inner_width = control_size.width() * 2 + 8
        panel_width = panel_inner_width + CARD_PADDING * 2
        stop_hotkey_size = QSize(52, KEY_BADGE_HEIGHT)
        stop_size = QSize(panel_inner_width, BUTTON_HEIGHT)
        shortcut_size = QSize(52, KEY_BADGE_HEIGHT)

        for button in (
            self.switch_character,
            self.switch_click,
            self.switch_double_click,
            self.switch_movement,
            self.switch_fake,
            self.radial_select_button,
            self.next_character,
            self.previous_character,
            self.mirror_arm_button,
            self.reload_runtime_button,
            self.debug_button,
        ):
            button.setFixedSize(control_size)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            button.setObjectName("secondaryButton")
        self.radial_select_button.setFixedSize(radial_control_size)
        # Small functional icons, without changing callbacks or shortcuts.
        # Previous/Next intentionally stay text-only.
        for button, kind in (
            (self.switch_character, "switch"),
            (self.switch_click, "click"),
            (self.switch_double_click, "double"),
            (self.switch_movement, "move"),
            (self.switch_fake, "group"),
            (self.radial_select_button, "radial"),
            (self.debug_button, "debug"),
        ):
            button.setIcon(_organizer_action_icon(kind))
            button.setIconSize(QSize(17, 17))
        self.reload_runtime_button.setIcon(_organizer_refresh_icon())
        self.reload_runtime_button.setIconSize(QSize(17, 17))
        for button, kind in (
            (self.macro_mode_button, "macro"),
            (self.mirror_mode_button, "mirror"),
        ):
            button.setIcon(_organizer_action_icon(kind))
            button.setIconSize(QSize(17, 17))
        # Retain the original arm control for compatible runtime hooks, but
        # the only visible mirror action is the mode button with its own badge.
        self.mirror_arm_button.setParent(self)
        self.mirror_arm_button.hide()
        self.stop_script_button.setObjectName("dangerButton")
        self.stop_script_button.setIcon(_organizer_warning_icon())
        self.stop_script_button.setIconSize(QSize(20, 20))
        self.stop_script_button.setFixedSize(stop_size)
        self.stop_script_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        for button in (self.click_button, self.double_click_button, self.radial_hotkey_button,
                       self.next_character_hotkey_button, self.previous_character_hotkey_button,
                       self.mirror_toggle_hotkey_button):
            button.setObjectName("keyBadge")
            button.setFixedSize(shortcut_size)
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.stop_script_hotkey_button.setObjectName("keyBadge")
        self.stop_script_hotkey_button.setFixedSize(stop_hotkey_size)
        self.stop_script_hotkey_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.radial_select_button.setToolTip(
            "Activer ou désactiver la roue ; régler la touche avec le badge."
        )
        self.radial_hotkey_button.setToolTip("Configurer la touche maintenue pour sélectionner un personnage")
        self.radial_hotkey_button.setAccessibleName("Raccourci du camembert")
        self.radial_clear.setAccessibleName("Supprimer le raccourci du camembert")
        self.next_character_hotkey_button.setAccessibleName("Raccourci personnage suivant")
        self.previous_character_hotkey_button.setAccessibleName("Raccourci personnage précédent")
        self.mirror_toggle_hotkey_button.setAccessibleName("Raccourci activation Miroir")
        self.script_speed_title.setObjectName("MutedLabel")
        self.script_speed_title.setFixedSize(52, BUTTON_HEIGHT)
        self.script_speed_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.script_speed_legacy.setFixedSize(78, BUTTON_HEIGHT)
        self.script_speed_legacy.setObjectName("segmentedButton")
        self.click_button.setToolTip("Raccourci Switch Clique")
        self.double_click_button.setToolTip("Raccourci Switch clic x2")
        self.stop_script_hotkey_button.setToolTip("Raccourci Stop script")
        self.reload_runtime_button.setToolTip("Relancer les raccourcis et le runtime Python")
        self.debug_button.setToolTip("Activer les logs runtime detailles")
        self.script_speed_legacy.setToolTip("Classique : anciens délais Normal conservés")
        self.script_speed_normal.setToolTip("Normal : anciens délais Rapide conservés")
        self.script_speed_fast.setToolTip("Rapide : délais réduits, à confirmer sur DOFUS Unity")
        self.script_speed_instant.setToolTip("Instantané : délais minimaux, fiabilité à tester en jeu")
        self.next_character.setToolTip("Activer le personnage suivant")
        self.previous_character.setToolTip("Activer le personnage précédent")
        self.mirror_arm_button.setToolTip("Le mode Miroir est désarmé tant que vous ne l'activez pas ici.")
        self.next_character_hotkey_button.setToolTip("Raccourci personnage suivant")
        self.stop_script_button.setToolTip("Arreter immediatement les macros Python")
        for button in (self.click_clear, self.double_click_clear, self.stop_script_clear,
                       self.radial_clear, self.next_character_clear, self.previous_character_clear,
                       self.mirror_toggle_clear):
            button.setObjectName("iconButtonDanger")
            button.setFixedSize(14, 14)
            button.setToolTip("Supprimer le raccourci")

        def macro_cell(
            action: QPushButton,
            shortcut: QPushButton | None = None,
            clear: QPushButton | None = None,
            size: QSize = control_size,
        ) -> QWidget:
            wrapper = QWidget()
            wrapper.setObjectName("OrganizerTransparentHost")
            wrapper.setStyleSheet("QWidget#OrganizerTransparentHost { background: transparent; border: none; }")
            wrapper.setFixedSize(size)
            wrapper.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            cell = QGridLayout(wrapper)
            cell.setContentsMargins(0, 0, 0, 0)
            cell.setHorizontalSpacing(0)
            cell.setVerticalSpacing(0)
            cell.addWidget(action, 0, 0)
            if shortcut is not None:
                # The badge is embedded, but inset from the right border.
                action.setStyleSheet(
                    "text-align: center; padding-left: 4px; padding-right: 64px; font-size: 10px;"
                )
                badge_host = QWidget(wrapper)
                badge_host.setObjectName("OrganizerTransparentHost")
                badge_host.setStyleSheet("QWidget#OrganizerTransparentHost { background: transparent; border: none; }")
                badge_host.setFixedSize(shortcut.width() + 8, BUTTON_HEIGHT)
                badge_layout = QHBoxLayout(badge_host)
                badge_layout.setContentsMargins(0, 0, 8, 0)
                badge_layout.setSpacing(0)
                badge_layout.addWidget(shortcut, alignment=Qt.AlignVCenter)
                cell.addWidget(badge_host, 0, 0, alignment=Qt.AlignRight | Qt.AlignVCenter)
                badge_host.raise_()
            if clear is not None:
                clear_host = QWidget(wrapper)
                clear_host.setObjectName("OrganizerTransparentHost")
                clear_host.setStyleSheet("QWidget#OrganizerTransparentHost { background: transparent; border: none; }")
                clear_host.setFixedSize(clear.width() + 6, clear.height() + 2)
                clear_layout = QHBoxLayout(clear_host)
                clear_layout.setContentsMargins(0, 2, 6, 0)
                clear_layout.addWidget(clear)
                cell.addWidget(clear_host, 0, 0, alignment=Qt.AlignTop | Qt.AlignRight)
                clear_host.raise_()
            return wrapper

        def make_card_header(
            title_label: QLabel,
            trailing: QWidget | None = None,
            after_title: QWidget | None = None,
        ) -> QHBoxLayout:
            layout = QHBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            title_accent = QFrame()
            title_accent.setObjectName("CardTitleAccent")
            title_accent.setFixedSize(3, 16)
            layout.addWidget(title_accent, alignment=Qt.AlignVCenter)
            layout.addWidget(title_label, alignment=Qt.AlignVCenter)
            if after_title is not None:
                layout.addWidget(after_title, alignment=Qt.AlignVCenter)
            layout.addStretch(1)
            if trailing is not None:
                layout.addWidget(trailing, alignment=Qt.AlignVCenter)
            return layout

        controls_grid_host = QWidget()
        controls_grid_host.setObjectName("OrganizerTransparentHost")
        controls_grid_host.setFixedWidth(panel_inner_width)
        controls_grid_host.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        controls_grid = QGridLayout(controls_grid_host)
        controls_grid.setContentsMargins(0, 0, 0, 0)
        controls_grid.setHorizontalSpacing(8)
        controls_grid.setVerticalSpacing(8)
        self.macro_grid_host = controls_grid_host
        controls_grid.addWidget(macro_cell(self.switch_character), 0, 0)
        controls_grid.addWidget(macro_cell(self.switch_click, self.click_button, self.click_clear), 0, 1)
        controls_grid.addWidget(macro_cell(self.switch_movement), 1, 0)
        controls_grid.addWidget(macro_cell(self.switch_double_click, self.double_click_button, self.double_click_clear), 1, 1)
        # Précédent / Suivant sont des actions rapides, jamais des switches Macro.
        for column in range(2):
            controls_grid.setColumnMinimumWidth(column, control_size.width())
            controls_grid.setColumnStretch(column, 0)
        for row in range(2):
            controls_grid.setRowMinimumHeight(row, BUTTON_HEIGHT)

        self.macro_panel = OrganizerGlassCard()
        self.macro_panel.setObjectName("card")
        self.macro_panel.setMinimumWidth(panel_width)
        self.macro_panel.setFixedHeight(controls_panel_height)
        self.macro_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        macro_layout = QVBoxLayout(self.macro_panel)
        macro_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        # Same 8px row rhythm as Quick actions and Controls.
        macro_layout.setSpacing(8)
        macro_layout.setAlignment(Qt.AlignTop)
        self.macro_mode_button.setObjectName("OrganizerModeChoice")
        self.mirror_mode_button.setObjectName("OrganizerModeChoice")
        self.mode_switch = OrganizerModeSwitch(
            # Both halves need the same fixed 194x30 host. Without this,
            # Qt compresses the bare Macro button to 24px while Miroir
            # (inside a macro_cell) remains at 30px in the full Windows CI.
            macro_cell(self.macro_mode_button),
            macro_cell(
                self.mirror_mode_button, self.mirror_toggle_hotkey_button,
                self.mirror_toggle_clear, size=control_size,
            ),
        )
        macro_layout.addWidget(self.mode_switch, alignment=Qt.AlignLeft)
        macro_layout.addWidget(controls_grid_host, alignment=Qt.AlignLeft)

        self.quick_actions_panel = OrganizerGlassCard()
        self.quick_actions_panel.setObjectName("card")
        self.quick_actions_panel.setMinimumWidth(panel_width)
        self.quick_actions_panel.setFixedHeight(controls_panel_height)
        self.quick_actions_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        quick_layout = QVBoxLayout(self.quick_actions_panel)
        quick_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        quick_layout.setSpacing(CARD_SPACING)
        quick_layout.setAlignment(Qt.AlignTop)
        quick_grid_host = QWidget()
        quick_grid_host.setObjectName("OrganizerTransparentHost")
        quick_grid_host.setFixedWidth(panel_inner_width)
        quick_grid_host.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        quick_grid = QGridLayout(quick_grid_host)
        quick_grid.setContentsMargins(0, 0, 0, 0)
        quick_grid.setHorizontalSpacing(8)
        quick_grid.setVerticalSpacing(8)
        quick_grid.addWidget(self.switch_fake, 0, 0)
        quick_grid.addWidget(macro_cell(self.radial_select_button, self.radial_hotkey_button, self.radial_clear, size=radial_control_size), 0, 1)
        quick_grid.addWidget(macro_cell(
            self.previous_character, self.previous_character_hotkey_button,
            self.previous_character_clear,
        ), 1, 0)
        quick_grid.addWidget(macro_cell(
            self.next_character, self.next_character_hotkey_button,
            self.next_character_clear,
        ), 1, 1)
        # Honest placeholders: reserve the cells without advertising a
        # non-existent action. Real actions can replace these later.
        self.quick_placeholder_1 = OrganizerGlassButton("Action libre 1")
        self.quick_placeholder_2 = OrganizerGlassButton("Action libre 2")
        for placeholder in (self.quick_placeholder_1, self.quick_placeholder_2):
            placeholder.setObjectName("secondaryButton")
            placeholder.setFixedSize(control_size)
            placeholder.setToolTip("Emplacement réservé : aucune action configurée")
            placeholder.setEnabled(False)
        quick_grid.addWidget(self.quick_placeholder_1, 2, 0)
        quick_grid.addWidget(self.quick_placeholder_2, 2, 1)
        # Vitesse stays in the canonical Controls panel, not Macro.
        speed_row = QWidget()
        speed_row.setObjectName("OrganizerTransparentHost")
        speed_row.setFixedSize(panel_inner_width, BUTTON_HEIGHT)
        speed_row_layout = QHBoxLayout(speed_row)
        speed_row_layout.setContentsMargins(0, 0, 0, 0)
        speed_row_layout.setSpacing(4)
        speed_row_layout.addWidget(self.script_speed_title)
        self.speed_selector = OrganizerSpeedSelector(
            self.script_speed_normal, self.script_speed_fast,
            self.script_speed_instant,
        )
        self.speed_selector.setFixedWidth(panel_inner_width - 52 - 4)
        speed_row_layout.addWidget(self.speed_selector)
        # Preserve an existing Classique profile without silently accelerating
        # it. This legacy-only choice is no longer offered to the user.
        macro_layout.addWidget(self.script_speed_legacy)
        self.script_speed_legacy.hide()
        stop_row = QWidget()
        stop_row.setObjectName("OrganizerTransparentHost")
        stop_row.setFixedSize(panel_inner_width, BUTTON_HEIGHT)
        stop_row.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        stop_row_layout = QHBoxLayout(stop_row)
        stop_row_layout.setContentsMargins(0, 0, 0, 0)
        stop_row_layout.setSpacing(8)
        # The emergency hotkey badge is inside the Stop button, not beside it.
        stop_row_layout.addWidget(macro_cell(
            self.stop_script_button, self.stop_script_hotkey_button,
            self.stop_script_clear, size=stop_size,
        ))
        for column in range(2):
            quick_grid.setColumnMinimumWidth(column, control_size.width())
            quick_grid.setColumnStretch(column, 0)
        for row in range(3):
            quick_grid.setRowMinimumHeight(row, BUTTON_HEIGHT)
        quick_layout.addWidget(quick_grid_host, alignment=Qt.AlignLeft)

        self.controls_panel = OrganizerGlassCard()
        self.controls_panel.setObjectName("card")
        self.controls_panel.setMinimumWidth(panel_width)
        self.controls_panel.setFixedHeight(controls_panel_height)
        self.controls_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        control_layout = QVBoxLayout(self.controls_panel)
        control_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        control_layout.setSpacing(CARD_SPACING)
        control_layout.setAlignment(Qt.AlignTop)
        controls_title = QLabel("Contrôles")
        controls_title.setObjectName("cardTitle")
        controls_title.setFixedHeight(20)
        controls_host = QWidget()
        controls_host.setObjectName("OrganizerTransparentHost")
        controls_host.setFixedWidth(panel_inner_width)
        controls_host.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        control_grid = QGridLayout(controls_host)
        control_grid.setContentsMargins(0, 0, 0, 0)
        control_grid.setHorizontalSpacing(8)
        control_grid.setVerticalSpacing(8)
        control_grid.addWidget(speed_row, 0, 0, 1, 2)
        control_grid.addWidget(self.reload_runtime_button, 1, 0)
        control_grid.addWidget(self.debug_button, 1, 1)
        control_grid.addWidget(stop_row, 2, 0, 1, 2)
        for column in range(2):
            control_grid.setColumnMinimumWidth(column, control_size.width())
        control_layout.addWidget(controls_host, alignment=Qt.AlignLeft)

        # A common header line; the actual mode switch lives inside Macro,
        # under the four actions, never as two separated header buttons.
        self.macro_section_title = QLabel("Macro / Miroir")
        self.macro_section_title.setObjectName("cardTitle")
        self.macro_section_title.setFixedHeight(20)
        self.macro_mode_header = QWidget()
        self.macro_mode_header.setObjectName("OrganizerTransparentHost")
        mode_title_layout = QVBoxLayout(self.macro_mode_header)
        mode_title_layout.setContentsMargins(0, 0, 0, 0)
        mode_title_layout.setSpacing(0)
        mode_title_layout.addLayout(make_card_header(self.macro_section_title))
        self.macro_mode_header.setFixedHeight(BUTTON_HEIGHT)
        self.quick_actions_title.setFixedHeight(20)
        self._organizer_panel_headers = [self.macro_mode_header]
        for section_title in (self.quick_actions_title, controls_title):
            section_header = QWidget()
            section_header.setObjectName("OrganizerTransparentHost")
            header_layout = QVBoxLayout(section_header)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(0)
            header_layout.addLayout(make_card_header(section_title))
            section_header.setFixedHeight(BUTTON_HEIGHT)
            self._organizer_panel_headers.append(section_header)
        self.controls_panels_grid = QGridLayout()
        self.controls_panels_grid.setContentsMargins(0, 0, 0, 0)
        self.controls_panels_grid.setHorizontalSpacing(8)
        self.controls_panels_grid.setVerticalSpacing(4)
        self._organizer_panels = (
            self.macro_panel, self.quick_actions_panel, self.controls_panel,
        )
        self._organizer_panel_columns = 0
        root.addLayout(self.controls_panels_grid)
        self._reflow_organizer_panels(self.width())

        self.sessions_refresh_button = OrganizerGlassButton("")
        self.sessions_refresh_button.setObjectName("iconButton")
        self.sessions_refresh_button.setFixedSize(32, BUTTON_HEIGHT)
        self.sessions_refresh_button.setIcon(_organizer_refresh_icon())
        self.sessions_refresh_button.setIconSize(QSize(22, 22))
        self.sessions_refresh_button.setAccessibleName("Actualiser les personnages")
        self.sessions_refresh_button.setToolTip("Actualiser les fenêtres Dofus")
        self.sessions_panel = CharacterSlotsPanel(self.sessions_refresh_button)
        self.sessions_content = self.sessions_panel.content
        self.sessions_grid = self.sessions_panel.grid

        # Characters span two top modules, Zaap spans one (2:1); heights match.
        # Both panels share the same height; the eight slots stay permanent.
        self.zaap_panel = OrganizerGlassCard()
        self.zaap_panel.setObjectName("card")
        self.zaap_panel.setMinimumWidth(220)
        self.zaap_panel.setFixedHeight(self.sessions_panel.calculated_height())
        self.zaap_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        zaap_layout = QVBoxLayout(self.zaap_panel)
        zaap_layout.setContentsMargins(CARD_PADDING, CARD_PADDING, CARD_PADDING, CARD_PADDING)
        zaap_layout.setSpacing(CARD_SPACING)
        zaap_title = QLabel("Zaap")
        zaap_title.setObjectName("cardTitle")
        zaap_title.setFixedHeight(20)
        zaap_layout.addLayout(make_card_header(zaap_title))

        # The title already says Zaap; a second 46px label would leave
        # almost no room to search in the narrow right-hand sidebar.
        self.zaap.zaap_label.hide()
        self.zaap.search_input.setMinimumWidth(90)
        self.zaap.setMinimumWidth(0)
        self.zaap.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.zaap_scroll = QScrollArea(self.zaap_panel)
        self.zaap_scroll.setObjectName("OrganizerZaapScroll")
        self.zaap_scroll.setFrameShape(QFrame.NoFrame)
        self.zaap_scroll.setWidgetResizable(True)
        self.zaap_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.zaap_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.zaap_scroll.setMinimumWidth(0)
        self.zaap_scroll.viewport().setObjectName("OrganizerZaapViewport")
        self.zaap_scroll.setWidget(self.zaap)
        zaap_layout.addWidget(self.zaap_scroll, 1)

        self.bottom_panels_row = QHBoxLayout()
        self.bottom_panels_row.setContentsMargins(0, 0, 0, 0)
        self.bottom_panels_row.setSpacing(8)
        self.bottom_panels_row.addWidget(self.sessions_panel, 2, Qt.AlignTop)
        self.bottom_panels_row.addWidget(self.zaap_panel, 1, Qt.AlignTop)
        root.addLayout(self.bottom_panels_row)
        for panel in (
            self.macro_panel, self.quick_actions_panel, self.controls_panel,
            self.sessions_panel, self.zaap_panel,
        ):
            _organizer_card_shadow(panel)
        root.addStretch(1)

    def _reflow_organizer_panels(self, width: int) -> None:
        columns = 3 if width >= 1300 else 2 if width >= 880 else 1
        if self._organizer_panel_columns == columns:
            return
        self._organizer_panel_columns = columns
        while self.controls_panels_grid.count():
            self.controls_panels_grid.takeAt(0)
        for index, panel in enumerate(self._organizer_panels):
            row, column = divmod(index, columns)
            self.controls_panels_grid.addWidget(
                self._organizer_panel_headers[index], row * 2, column,
            )
            self.controls_panels_grid.addWidget(panel, row * 2 + 1, column)
        for column in range(3):
            self.controls_panels_grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:
        if hasattr(self, "controls_panels_grid"):
            self._reflow_organizer_panels(event.size().width())
        super().resizeEvent(event)

    def set_runtime_active(self, connected: bool) -> None:
        if not isValid(self):
            return
        if not connected:
            # Stop urgence owns the radial popup too; never keep a live
            # selection on screen after the runtime has been stopped.
            controller = getattr(self, "_radial_controller", None)
            if controller is not None:
                controller.cancel()
        status_dot = getattr(self, "runtime_status_dot", None)
        if status_dot is None or not isValid(status_dot):
            return
        status_dot.setObjectName("runtimeStatusActive" if connected else "runtimeStatusInactive")
        self.restyle_button(status_dot)

    def restyle_button(self, button: QPushButton) -> None:
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def set_toggle_button(self, button: QPushButton, label: str, enabled: bool) -> None:
        button.setText(label)
        button.setToolTip(f"{label} actif" if enabled else f"{label} inactif")
        button.setObjectName("primaryButton" if enabled else "secondaryButton")
        self.restyle_button(button)

    def update_macro_mode_buttons(self) -> None:
        mirror = self.profiles.get(KEY_ORGANIZER_MACRO_MODE) == "mirror"
        self.mode_switch.set_selected(
            mirror, armed=bool(getattr(self, "_mirror_arm_active", False))
        )
        # Qt desaturates all four macro controls, not just their text.
        self.macro_grid_host.setEnabled(not mirror)
        for button in (
            self.switch_character, self.switch_click, self.switch_movement,
            self.switch_double_click, self.click_button, self.click_clear,
            self.double_click_button, self.double_click_clear,
        ):
            button.setEnabled(not mirror)
        self.mirror_arm_button.setEnabled(mirror)
        self.set_mirror_arm_active(
            bool(mirror and getattr(self, "_mirror_arm_active", False))
        )

    def set_mirror_arm_active(self, active: bool) -> None:
        button = getattr(self, "mirror_arm_button", None)
        if button is None or not isValid(button):
            return
        active = active is True and self.profiles.get(KEY_ORGANIZER_MACRO_MODE) == "mirror"
        self._mirror_arm_active = active
        can_navigate = (profile_bool(self.profiles, KEY_SWITCH_CHARACTER, True)
                        and not active)
        for control in (
            self.next_character, self.previous_character,
            self.next_character_hotkey_button, self.previous_character_hotkey_button,
            self.next_character_clear, self.previous_character_clear,
        ):
            control.setEnabled(can_navigate)
        button.setText("Arrêter Miroir" if active else "Activer Miroir")
        button.setObjectName("primaryButton" if active else "secondaryButton")
        button.setToolTip(
            "Arrêter immédiatement la copie des gestes."
            if active else "Activer explicitement la copie des gestes du personnage favori."
        )
        self.restyle_button(button)
        self.mode_switch.set_selected(
            self.profiles.get(KEY_ORGANIZER_MACRO_MODE) == "mirror", armed=active
        )
        self.mirror_mode_button.setToolTip(
            "Arrêter la copie Miroir (clics, touches courtes, molette)."
            if active else "Activer la copie Miroir du personnage favori."
        )
        self.restyle_button(self.mirror_mode_button)

    def update_switch_buttons(self) -> None:
        self.set_toggle_button(self.switch_character, "Switch Personnage", profile_bool(self.profiles, KEY_SWITCH_CHARACTER, True))
        # Switch Personnage is the single navigation authorization control.
        self.set_mirror_arm_active(bool(getattr(self, "_mirror_arm_active", False)))
        self.set_toggle_button(self.switch_click, "Switch Clique", profile_bool(self.profiles, KEY_SWITCH_CLICK, False))
        self.set_toggle_button(self.switch_double_click, "Switch clic x2", profile_bool(self.profiles, KEY_SWITCH_DOUBLE_CLICK, False))
        self.set_toggle_button(self.switch_movement, "Switch Deplacement", profile_bool(self.profiles, KEY_SWITCH_MOVEMENT, False))

    def update_global_buttons(self) -> None:
        click = self.hotkey_label(KEY_CLICK_HOTKEY)
        double_click = self.hotkey_label(KEY_DOUBLE_CLICK_HOTKEY)
        stop_script = self.hotkey_label(KEY_STOP_SCRIPT_HOTKEY)
        radial_hotkey = self.hotkey_label(KEY_RADIAL_HOTKEY)
        next_hotkey = self.hotkey_label(KEY_NEXT_CHARACTER_HOTKEY)
        previous_hotkey = self.hotkey_label(KEY_PREVIOUS_CHARACTER_HOTKEY)
        mirror_hotkey = self.hotkey_label(KEY_MIRROR_TOGGLE_HOTKEY)
        self.click_button.setText(short_label(click, 9) if click else "...")
        self.click_button.setToolTip(f"Switch Clique: {click}" if click else "Raccourci Switch Clique")
        self.click_clear.setVisible(bool(click))
        self.double_click_button.setText(short_label(double_click, 9) if double_click else "...")
        self.double_click_button.setToolTip(f"Switch clic x2: {double_click}" if double_click else "Raccourci Switch clic x2")
        self.double_click_clear.setVisible(bool(double_click))
        self.stop_script_hotkey_button.setText(short_label(stop_script, 9) if stop_script else "...")
        self.stop_script_hotkey_button.setToolTip(f"Stop script: {stop_script}" if stop_script else "Raccourci Stop script")
        self.stop_script_clear.setVisible(bool(stop_script))
        self.radial_hotkey_button.setText(short_label(radial_hotkey, 9) if radial_hotkey else "...")
        radial_owner = self.client_hotkey_owner(radial_hotkey) if radial_hotkey else ""
        self.radial_hotkey_button.setToolTip(
            (f"Sélection : {radial_hotkey} ; roue prioritaire sur {radial_owner}"
             if radial_owner else f"Sélection personnage : {radial_hotkey}")
            if radial_hotkey else "Définir la touche maintenue pour le camembert"
        )
        self.radial_clear.setVisible(bool(radial_hotkey))
        radial_active = profile_bool(self.profiles, KEY_RADIAL_ENABLED, True)
        self.radial_select_button.setObjectName(
            "primaryButton" if radial_active else "secondaryButton"
        )
        self.radial_select_button.setToolTip(
            "Désactiver la roue de sélection" if radial_active
            else "Activer la roue de sélection"
        )
        self.restyle_button(self.radial_select_button)
        self.next_character_hotkey_button.setText(short_label(next_hotkey, 9) if next_hotkey else "...")
        self.next_character_hotkey_button.setToolTip(f"Personnage suivant : {next_hotkey}" if next_hotkey else "Raccourci personnage suivant")
        self.next_character_clear.setVisible(bool(next_hotkey))
        self.previous_character_hotkey_button.setText(short_label(previous_hotkey, 9) if previous_hotkey else "...")
        self.previous_character_hotkey_button.setToolTip(
            f"Personnage précédent : {previous_hotkey}" if previous_hotkey else "Raccourci personnage précédent"
        )
        self.previous_character_clear.setVisible(bool(previous_hotkey))
        self.mirror_toggle_hotkey_button.setText(short_label(mirror_hotkey, 9) if mirror_hotkey else "...")
        self.mirror_toggle_hotkey_button.setToolTip(
            f"Activation Miroir : {mirror_hotkey}" if mirror_hotkey else "Configurer le raccourci Miroir"
        )
        self.mirror_toggle_clear.setVisible(bool(mirror_hotkey))

    def update_script_speed_buttons(self) -> None:
        speed = self.script_speed()
        self.script_speed_legacy.setObjectName(
            "segmentedButtonActive" if speed == "classique" else "segmentedButton"
        )
        self.restyle_button(self.script_speed_legacy)
        # In legacy Classique there is deliberately no active indicator:
        # rendering it as Normal would falsely imply changed runtime timings.
        self.speed_selector.set_selected(speed)

    def update_debug_button(self) -> None:
        enabled = profile_bool(self.profiles, KEY_DEBUG_MODE, False)
        self.debug_button.setObjectName("primaryButton" if enabled else "secondaryButton")
        self.debug_button.setToolTip(
            "Debug actif: logs runtime detailles" if enabled else "Debug inactif: logs runtime allegees"
        )
        self.restyle_button(self.debug_button)

    def request_sessions_render(self) -> None:
        if self.isVisible():
            self.render_sessions()
            return
        self._sessions_render_dirty = True

    def flush_sessions_render_if_dirty(self) -> None:
        if self._sessions_render_dirty:
            self.render_sessions()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.flush_sessions_render_if_dirty()

    def hideEvent(self, event) -> None:
        # The Organizer service and Unity watcher must stay alive while
        # navigating Atlas, but its eight richly decorated/interactive rows
        # are purely presentational. Free only those Qt objects on Home.
        # Session identities, profile state, macro timers and watcher are
        # intentionally untouched; fresh rows bind the current state on show.
        if self.drag_session_index is None:
            self.sessions_panel.clear_slots()
            self.session_row_widgets = []
            self.session_slot_widgets = []
            self.sessions_placeholder = None
            self._sessions_render_dirty = True
        super().hideEvent(event)

    def render_sessions(self) -> None:
        self.sessions_panel.clear_slots()
        self.session_row_widgets = []
        self.session_slot_widgets = []
        self.sessions_grid = self.sessions_panel.grid
        self.sessions_placeholder = None
        primary = str(self.profiles.get(KEY_PRIMARY_WINDOW, ""))
        primary_matched = False
        slot_count = self.session_slot_count()
        while len(self.sessions) < slot_count:
            self.sessions.append(empty_session_slot())
        # Exactly eight permanent, reorderable slots; no collapse/expand UI.
        self.sessions_panel.slot_count = slot_count
        self.sessions_panel.row_height = CHARACTER_SLOT_HEIGHT

        for index in range(slot_count):
            session = self.sessions[index]
            name = session_name(session)
            hwnd = session_hwnd(session)
            is_empty = session_is_empty(session)
            is_detected = session_is_detected(session)
            is_primary = is_detected and self.session_is_primary(name, hwnd, primary, session)
            if is_primary and not primary.startswith("hwnd:"):
                if primary_matched:
                    is_primary = False
                else:
                    primary_matched = True

            if is_empty:
                slot = QFrame()
                slot.setAttribute(Qt.WA_Hover, True)
                slot.setObjectName("characterSlotDropTarget" if index == self.drag_hover_index else "characterSlotEmpty")
                slot.setFixedHeight(self.sessions_panel.row_height)
                slot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                slot_layout = QHBoxLayout(slot)
                slot_layout.setContentsMargins(8, 0, 8, 0)
                slot_layout.setSpacing(7)
                add_marker = QLabel("+")
                add_marker.setObjectName("EmptySlotAdd")
                add_marker.setFixedWidth(18)
                add_marker.setAlignment(Qt.AlignCenter)
                slot_layout.addWidget(add_marker)
                empty_label = QLabel("Slot vide")
                empty_label.setObjectName("MutedLabel")
                empty_label.setAlignment(Qt.AlignVCenter)
                slot_layout.addWidget(empty_label, 1)
                self.sessions_panel.add_slot(slot, index)
                self.session_slot_widgets.append((slot, index))
                continue

            row = QFrame()
            row.setAttribute(Qt.WA_Hover, True)
            if index == self.drag_session_index:
                row.setObjectName("characterSlotDragging")
            elif index == self.drag_hover_index:
                row.setObjectName("characterSlotDropTarget")
            elif is_detected:
                row.setObjectName("characterSlot")
            else:
                row.setObjectName("characterSlotMissing")
            row.setFixedHeight(self.sessions_panel.row_height)
            row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout = QHBoxLayout(row)
            layout.setContentsMargins(8, 0, 8, 0)
            layout.setSpacing(7)
            grip = OrganizerGlassButton("")
            grip.setIcon(_organizer_grip_icon())
            grip.setIconSize(QSize(13, 19))
            grip.setAccessibleName("Déplacer ce personnage")
            grip.setObjectName("DragHandle")
            grip.setFixedSize(14, 24)
            grip.setCursor(Qt.OpenHandCursor)
            grip.setToolTip("Déplacer ce personnage")
            self.bind_session_drag_events(grip, index, row)
            layout.addWidget(grip)
            star = OrganizerGlassButton("")
            star.setIcon(_organizer_favorite_icon(is_primary))
            star.setIconSize(QSize(19, 19))
            star.setAccessibleName("Personnage principal" if is_primary else "Définir comme principal")
            star.setObjectName("FavoriteButtonActive" if is_primary else "FavoriteButton")
            star.setFixedSize(22, 24)
            star.setToolTip("Fenêtre principale")
            star.setEnabled(is_detected)
            if is_detected:
                star.clicked.connect(lambda _checked=False, target=session: self.set_primary_window(target))
                # A favorite is an action, not a drag handle: swallowing its
                # mouse release during a tiny drag loses the click/selection.
            layout.addWidget(star)
            # The radial selector uses Organizer's shared participant roster.
            # Avoid a second unexplained per-slot selector beside the favorite.
            icon = QLabel()
            icon.setFixedSize(24, 24)
            icon.setAlignment(Qt.AlignCenter)
            verified_key = self.verified_character_token_for_session(session)
            verified_row = next(
                (row for character_id, row in self._verified_character_rows()
                 if verified_key == f"character:{character_id}"),
                {},
            )
            class_key = str(verified_row.get("class_key") or "").strip().casefold()
            verified_class = class_key in DOFUS_CLASS_DEFINITIONS
            if not verified_class:
                # Cosmetic hint only: a visible Unity window can show its
                # class portrait before network proof exists. Never promote
                # this title-derived class into a progression identity.
                class_key = dofus_class_key_from_window_name(name) or ""
            if class_key not in DOFUS_CLASS_DEFINITIONS:
                class_key = ""
            icon_path = next(
                (path for path in class_icon_candidates(class_key) if path.is_file()),
                None,
            ) if class_key else None
            pixmap = _organizer_class_pixmap(str(icon_path)) if icon_path is not None else QPixmap()
            if pixmap.isNull() and ICON_PATH.exists():
                pixmap = _organizer_class_pixmap(str(ICON_PATH))
            if not pixmap.isNull():
                icon.setPixmap(pixmap)
            if class_key:
                label = DOFUS_CLASS_DEFINITIONS[class_key]["label"]
                icon.setToolTip(
                    label if verified_class else f"{label} (titre Unity, non vérifié)"
                )
            icon.setCursor(Qt.OpenHandCursor)
            self.bind_session_drag_events(icon, index, row)
            layout.addWidget(icon)
            display_name = clean_auto_group_name(name) or name
            label = QLabel(display_name)
            label.setObjectName("CompactLabel" if is_detected else "MutedLabel")
            label.setWordWrap(False)
            label.setFixedHeight(24)
            label.setAlignment(Qt.AlignVCenter)
            label.setCursor(Qt.OpenHandCursor)
            label.setToolTip(display_name)
            self.bind_session_drag_events(label, index, row)
            layout.addWidget(label, 1)
            binding = self.slot_hotkey_label(index)
            shortcut = OrganizerGlassButton(binding or "...")
            shortcut.setObjectName("keyBadge")
            shortcut.setFixedSize(52, KEY_BADGE_HEIGHT)
            shortcut.setToolTip("Raccourci client")
            shortcut.clicked.connect(lambda _checked=False, slot=index, button=shortcut: self.begin_capture("client", slot=slot, button=button))
            remove = OrganizerGlassButton("x")
            remove.setObjectName("iconButtonDanger")
            remove.setFixedSize(14, 14)
            remove.setVisible(bool(binding))
            remove.setToolTip("Supprimer le raccourci client")
            remove.clicked.connect(lambda _checked=False, slot=index: self.remove_client_hotkey(slot))
            self.bind_session_drag_events(shortcut, index, row)
            self.bind_session_drag_events(remove, index, row)
            shortcut_wrap = QWidget()
            shortcut_wrap.setObjectName("OrganizerTransparentHost")
            shortcut_wrap.setStyleSheet("QWidget#OrganizerTransparentHost { background: transparent; border: none; }")
            shortcut_wrap.setFixedSize(58, 24)
            shortcut_wrap.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.bind_session_drag_events(shortcut_wrap, index, row)
            shortcut_grid = QGridLayout(shortcut_wrap)
            shortcut_grid.setContentsMargins(0, 0, 0, 0)
            shortcut_grid.setHorizontalSpacing(0)
            shortcut_grid.setVerticalSpacing(0)
            shortcut_grid.addWidget(shortcut, 0, 0)
            shortcut_grid.addWidget(remove, 0, 0, alignment=Qt.AlignTop | Qt.AlignRight)
            remove.raise_()
            layout.addWidget(shortcut_wrap)
            self.sessions_panel.add_slot(row, index)
            row.setCursor(Qt.OpenHandCursor)
            self.bind_session_drag_events(row, index, row)
            self.session_row_widgets.append((row, index))
            self.session_slot_widgets.append((row, index))
        self.sessions_panel.content.setFixedHeight(self.sessions_panel.slot_grid_height())
        self.sessions_panel.setFixedHeight(self.sessions_panel.calculated_height())
        self._sessions_render_dirty = False
