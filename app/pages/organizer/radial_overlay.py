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
        return all(bool(user32.GetAsyncKeyState(int(vk)) & 0x8000) for vk in keys)
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
        self._start_cursor = QPoint()
        self._icons: list[QPixmap] = []

    def open_for(self, characters: list[dict]) -> bool:
        if not characters:
            return False
        self._characters = [dict(row) for row in characters[:8]]
        self._hovered = None
        self._start_cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(self._start_cursor) or QGuiApplication.primaryScreen()
        if screen is None:
            return False
        # The user requested the centre of the selected screen, not cursor.
        centre = screen.availableGeometry().center()
        self.move(centre.x() - self.width() // 2, centre.y() - self.height() // 2)
        self._icons = []
        for row in self._characters:
            icon = class_icon_path_for_window_name(str(row.get("nom", "")))
            self._icons.append(QPixmap(str(icon)) if icon else QPixmap())
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
        if selected != self._hovered:
            self._hovered = selected
            self.update()

    def finish(self, current: list[dict], *, cancel: bool = False) -> int | None:
        selected = None if cancel else self._hovered
        snapshot = self._characters
        # Hide FIRST, including releases with no valid selection.
        self.hide()
        self._hovered = None
        self._characters = []
        self._icons = []
        return confirmed_radial_target(snapshot, current, selected)

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
            painter.setPen(QPen(QColor("#C7AA70"), 1.4))
            painter.setBrush(QColor("#A78247" if index == self._hovered else "#354249" if index % 2 else "#263238"))
            painter.drawPath(shape)
            x, y = centre.x() + label_x, centre.y() + label_y
            icon = self._icons[index] if index < len(self._icons) else QPixmap()
            if not icon.isNull():
                painter.drawPixmap(int(x - 17), int(y - 30), 34, 34, icon)
            painter.setPen(QColor("#FFFFFF"))
            font = QFont()
            font.setPointSize(9)
            font.setBold(index == self._hovered)
            painter.setFont(font)
            label = str(self._characters[index].get("nom") or "")[:17]
            painter.drawText(int(x - 55), int(y + 6), 110, 35, Qt.AlignCenter | Qt.TextWordWrap, label)
        painter.setPen(QPen(QColor("#D6BD8F"), 2))
        painter.setBrush(QColor("#18252B"))
        painter.drawEllipse(centre, INNER_RADIUS, INNER_RADIUS)
        painter.setPen(QColor("#F3E5CD"))
        painter.drawText(
            int(centre.x() - 38), int(centre.y() - 24), 76, 48,
            Qt.AlignCenter | Qt.TextWordWrap, "CHOISIR\nPERSO",
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
        self._timer.start()

    def set_shortcut(self, text: str) -> bool:
        self.cancel()
        self.keys = frozenset()
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
                handle = self.overlay.finish(
                    self.participants(), cancel=cancelled
                ) if self.overlay.isVisible() else None
                if handle is not None:
                    self.activate(handle)
            return
        if self._cancel_until_release:
            return
        if self._down:
            if self.overlay.isVisible():
                self.overlay.track_cursor()
            return
        self._down = True
        if self.can_open():
            self.overlay.open_for(self.participants())
