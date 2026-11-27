"""Shared fallback pictograms for Guide and Quest rows (not game artwork)."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygon

from app.ui.theme import PALETTE


@lru_cache(maxsize=16)
def atlas_icon(kind: str) -> QIcon:
    # Bounded cache for the fixed Unity fallback icons. Reward rows otherwise
    # repaint the same 20px QPixmap hundreds of times on the Qt UI thread.
    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(PALETTE["GREEN"]), 1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    if kind == "quest":
        painter.drawRoundedRect(5, 3, 10, 14, 2, 2)
        painter.drawLine(7, 8, 13, 8)
        painter.drawLine(7, 12, 12, 12)
    elif kind == "solo":
        painter.drawLine(6, 16, 14, 4)
        painter.drawLine(10, 12, 14, 16)
        painter.drawLine(9, 11, 5, 7)
        painter.drawLine(5, 17, 8, 14)
    elif kind == "group":
        painter.drawLine(4, 16, 13, 5)
        painter.drawLine(7, 13, 3, 9)
        painter.drawLine(3, 17, 6, 14)
        painter.drawLine(16, 16, 7, 5)
        painter.drawLine(13, 13, 17, 9)
        painter.drawLine(17, 17, 14, 14)
    elif kind == "dungeon":
        painter.drawRoundedRect(4, 7, 12, 10, 1, 1)
        painter.drawArc(5, 2, 10, 10, 0, 180 * 16)
        painter.drawLine(7, 7, 7, 17)
        painter.drawLine(13, 7, 13, 17)
        painter.drawEllipse(9, 12, 2, 2)
    elif kind == "tactical":
        painter.drawEllipse(4, 4, 12, 12)
        painter.drawEllipse(8, 8, 4, 4)
        painter.drawLine(10, 2, 10, 6)
        painter.drawLine(10, 14, 10, 18)
        painter.drawLine(2, 10, 6, 10)
        painter.drawLine(14, 10, 18, 10)
    elif kind == "drop":
        painter.drawLine(10, 3, 15, 10)
        painter.drawArc(5, 8, 10, 9, 200 * 16, 140 * 16)
        painter.drawLine(10, 3, 5, 10)
    elif kind == "item":
        painter.drawPolygon(QPolygon([QPoint(10, 3), QPoint(16, 9), QPoint(10, 17), QPoint(4, 9)]))
    elif kind == "combat":
        painter.drawLine(4, 15, 16, 5)
        painter.drawLine(5, 5, 16, 16)
    else:
        painter.drawEllipse(5, 5, 10, 10)
        painter.drawLine(10, 2, 10, 5)
        painter.drawLine(10, 15, 10, 18)
    painter.end()
    return QIcon(pixmap)
