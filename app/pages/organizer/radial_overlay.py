"""Non-activating, screen-centred radial overlay for Organizer.

Qt owns painting and lifecycle. A cheap Windows key-state poll keeps the global
hold gesture independent of Organizer's visibility; no second macro engine,
Win32 hook, Dofus process injection or background-window input is introduced.
"""
from __future__ import annotations

import ctypes
import logging
import math
import os
from typing import Callable

from PySide6.QtCore import QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from app.constants import LOGO_PATH
from app.ui.unity_skin import UNITY_PALETTE

from .common import class_icon_path_for_window_name
from .radial_selection import confirmed_radial_target, selected_slice, sector_layout

LOG = logging.getLogger(__name__)
RADIUS = 145
INNER_RADIUS = 48
DIAMETER = 2 * (RADIUS + 14)


def physical_key_held(keys: frozenset[int]) -> bool:
    """Poll only explicitly configured physical shortcut keys (Windows only).

    This read does not suppress the shortcut in the game. No Win32 calls are
    made on non-Windows or during Qt offscreen tests.
    """
    if not keys or os.name != "nt" or os.environ.get("QT_QPA_PLATFORM", "").casefold() == "offscreen":
        return False
    try:
        user32 = ctypes.windll.user32
        if not all(bool(user32.GetAsyncKeyState(int(vk)) & 0x8000) for vk in keys):
            return False
        # F6 must not become Alt+F6 or Ctrl+F6 while the user is typing
        # a system/game combination. Query modifiers only when matched.
        from app.input.hotkeys import MODIFIER_VKS

        return all(
            bool(user32.GetAsyncKeyState(vk) & 0x8000) == (vk in keys)
            for vk in MODIFIER_VKS
        )
    except (AttributeError, OSError, ValueError):
        return False


def escape_pressed() -> bool:
    if os.name != "nt" or os.environ.get("QT_QPA_PLATFORM", "").casefold() == "offscreen":
        return False
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)
    except (AttributeError, OSError, ValueError):
        return False


class OrganizerRadialOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFixedSize(DIAMETER, DIAMETER)
        self._characters: list[dict] = []
        self._hovered: int | None = None
        self._center_hovered = False
        self._start_cursor = QPoint()
        self._icons: list[QPixmap] = []
        self._atlas_logo: QPixmap | None = None

    def open_for(self, characters: list[dict]) -> bool:
        if not characters:
            return False
        self._characters = [dict(row) for row in characters[:8]]
        self._hovered = None
        self._center_hovered = False
        self._start_cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(self._start_cursor) or QGuiApplication.primaryScreen()
        if screen is None:
            return False
        # The user requested the centre of the selected screen, not cursor.
        centre = screen.geometry().center()
        self.move(centre.x() - self.width() // 2, centre.y() - self.height() // 2)
        if self._atlas_logo is None:
            logo = QPixmap(str(LOGO_PATH))
            if logo.isNull():
                self._atlas_logo = QPixmap()
            else:
                # Clean at thumbnail size, once, not on every repaint.
                from app.ui.splash_image import clear_connected_dark_background

                thumb = logo.scaled(
                    68, 68, Qt.KeepAspectRatio, Qt.SmoothTransformation,
                ).toImage()
                self._atlas_logo = QPixmap.fromImage(
                    clear_connected_dark_background(thumb)
                )
        self._icons = []
        for row in self._characters:
            portrait = str(row.get("portrait_path") or "").strip()
            icon = class_icon_path_for_window_name(str(row.get("nom", "")))
            image = QPixmap(portrait) if portrait else QPixmap()
            if image.isNull() and icon is not None:
                image = QPixmap(str(icon))
            self._icons.append(image)
        self.show()
        self.update()
        return True

    def track_cursor(self) -> None:
        if not self.isVisible():
            return
        cursor = QCursor.pos()
        moved = (cursor - self._start_cursor).manhattanLength() >= 9
        x = cursor.x() - (self.x() + self.width() / 2)
        y = cursor.y() - (self.y() + self.height() / 2)
        distance = math.hypot(x, y)
        selected = (
            selected_slice(x, y, len(self._characters), INNER_RADIUS)
            if moved and distance <= RADIUS else None
        )
        center = bool(moved and distance <= INNER_RADIUS)
        if selected != self._hovered or center != self._center_hovered:
            self._hovered = selected
            self._center_hovered = center
            self.update()

    def finish(self, current: list[dict], *, cancel: bool = False) -> int | None:
        selected = None if cancel else self._hovered
        center = not cancel and self._center_hovered
        snapshot = self._characters
        # Hide FIRST, including releases with no valid selection.
        self.hide()
        self._hovered = None
        self._center_hovered = False
        self._characters = []
        self._icons = []
        # HWND=0 is the existing Atlas app, never a DOFUS game HWND.
        return 0 if center else confirmed_radial_target(snapshot, current, selected)

    def paintEvent(self, event) -> None:
        if not self._characters:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        centre = QPointF(self.width() / 2, self.height() / 2)
        count = len(self._characters)
        for index, (start, end, label_x, label_y) in enumerate(sector_layout(count, 93)):
            points = [centre]
            for step in range(19):
                angle = start + (end - start) * step / 18
                points.append(centre + QPointF(RADIUS * math.cos(angle), RADIUS * math.sin(angle)))
            shape = QPainterPath()
            shape.moveTo(points[0])
            for pt in points[1:]:
                shape.lineTo(pt)
            shape.closeSubpath()
            painter.setPen(QPen(QColor(UNITY_PALETTE["BORDER_STRONG"]), 1.4))
            painter.setBrush(QColor(
                UNITY_PALETTE["PANEL_ACTIVE"] if index == self._hovered
                else UNITY_PALETTE["PANEL_2"] if index % 2
                else UNITY_PALETTE["PANEL"]
            ))
            painter.drawPath(shape)
            x, y = centre.x() + label_x, centre.y() + label_y
            icon = self._icons[index] if index < len(self._icons) else QPixmap()
            if not icon.isNull():
                painter.drawPixmap(int(x - 17), int(y - 30), 34, 34, icon)
            painter.setPen(QColor(UNITY_PALETTE["TEXT"]))
            font = QFont()
            font.setPointSize(9)
            font.setBold(index == self._hovered)
            painter.setFont(font)
            label = str(self._characters[index].get("nom") or "")[:17]
            painter.drawText(int(x - 55), int(y + 6), 110, 35, Qt.AlignCenter | Qt.TextWordWrap, label)
        painter.setPen(QPen(QColor(
            UNITY_PALETTE["GREEN"] if self._center_hovered
            else UNITY_PALETTE["BORDER_STRONG"]
        ), 2))
        painter.setBrush(QColor(
            UNITY_PALETTE["PANEL_ACTIVE"] if self._center_hovered
            else UNITY_PALETTE["SIDEBAR"]
        ))
        painter.drawEllipse(centre, INNER_RADIUS, INNER_RADIUS)
        logo = self._atlas_logo
        if logo is not None and not logo.isNull():
            painter.drawPixmap(
                int(centre.x() - logo.width() / 2),
                int(centre.y() - logo.height() / 2),
                logo,
            )
        else:
            painter.setPen(QColor(UNITY_PALETTE["TEXT"]))
            painter.drawText(
                int(centre.x() - 38), int(centre.y() - 24), 76, 48,
                Qt.AlignCenter, "ATLAS",
            )


class OrganizerRadialHoldController:
    """Small UI-thread state machine: press opens, release *always* closes."""

    def __init__(
        self,
        overlay: OrganizerRadialOverlay,
        participants: Callable[[], list[dict]],
        activate: Callable[[int], None],
        *,
        parent: QWidget,
        key_reader: Callable[[frozenset[int]], bool] = physical_key_held,
        can_open: Callable[[], bool] | None = None,
        interval_ms: int = 25,
    ) -> None:
        self.overlay = overlay
        self.participants = participants
        self.activate = activate
        self.key_reader = key_reader
        self.can_open = can_open or (lambda: True)
        self.keys: frozenset[int] = frozenset()
        self._down = False
        self._cancel_until_release = False
        self._timer = QTimer(parent)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.poll)
        # No polling cost at all until the user assigns a shortcut.

    def set_shortcut(self, text: str) -> bool:
        self.cancel()
        self.keys = frozenset()
        self._timer.stop()
        # Rebinding is not a cancelled hold: the next deliberate press
        # should work immediately after the old shortcut is released.
        self._cancel_until_release = False
        if not text:
            return True
        from app.input.hotkeys import parse_hotkey
        spec, error = parse_hotkey(text)
        if spec is None or error:
            return False
        self.keys = spec.keys
        if self.keys:
            # Binding a shortcut while its key is already down must not
            # open the wheel retroactively. Require a fresh key release
            # before the next deliberate press.
            self._cancel_until_release = bool(self.key_reader(self.keys))
            self._timer.start()
        return True

    def cancel(self) -> None:
        self._down = False
        self._cancel_until_release = True
        if self.overlay.isVisible():
            self.overlay.finish([], cancel=True)

    def poll(self) -> None:
        held = bool(self.keys) and self.key_reader(self.keys)
        if not held:
            cancelled = self._cancel_until_release
            self._cancel_until_release = False
            if self._down:
                self._down = False
                if self.overlay.isVisible():
                    self.overlay.track_cursor()
                    # Close before any session resolution or Windows focus work.
                    self.overlay.hide()
                    # A focus loss between key polls must never refocus a
                    # Dofus window on release (e.g. Alt+Tab to another app).
                    handle = self.overlay.finish(
                        self.participants(), cancel=cancelled or not self.can_open()
                    )
                else:
                    handle = None
                if handle is not None:
                    self.activate(handle)
            return
        if self._cancel_until_release:
            return
        if escape_pressed():
            self.cancel()
            return
        if self._down:
            if not self.can_open():
                # Disarm until the original key is released; do not let the
                # overlay bring the user back from another application.
                self.cancel()
                return
            if self.overlay.isVisible():
                self.overlay.track_cursor()
            return
        self._down = True
        if self.can_open():
            self.overlay.open_for(self.participants())
