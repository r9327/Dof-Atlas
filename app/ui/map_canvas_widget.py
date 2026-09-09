from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap, QPolygonF, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.cartography.scan_status_service import get_status_color, normalize_status


class MapCanvasWidget(QWidget):
    mapSelected = Signal(str, int, int)
    linkSelected = Signal(object)
    linkActivated = Signal(str)
    viewChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("MapCanvas")
        self.setMinimumSize(420, 320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.view: dict[str, Any] | None = None
        self.view_key = ""
        self.maps: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.pixmap = QPixmap()
        self.asset_path = ""
        self.is_placeholder = True
        self.placeholder_text = ""

        self.zoom = 1.0
        self.offset = QPointF(0, 0)
        self._fit_pending = True
        self._panning = False
        self._pan_last = QPointF(0, 0)
        self._left_press_pos: QPointF | None = None
        self._drag_threshold = 5.0
        self._selected_coord: tuple[int, int] | None = None
        self._selected_link_id: int | None = None

    def set_view(
        self,
        view: dict[str, Any] | None,
        pixmap: QPixmap,
        maps: list[dict[str, Any]],
        links: list[dict[str, Any]],
        asset_path: str,
        is_placeholder: bool,
    ) -> None:
        self.view = view
        self.view_key = str((view or {}).get("view_key") or "")
        self.pixmap = pixmap
        self.maps = maps
        self.links = links
        self.asset_path = asset_path
        self.is_placeholder = is_placeholder
        self._selected_coord = None
        self._selected_link_id = None
        self._fit_pending = True
        self.update()
        if self.view_key:
            self.viewChanged.emit(self.view_key)

    def set_map_placeholder(self, text: str = "") -> None:
        self.placeholder_text = text or ""
        self.update()

    def reset_zoom(self) -> None:
        self._fit_pending = True
        self.update()

    def select_map_coord(self, x: int, y: int) -> None:
        self._selected_coord = (int(x), int(y))
        self._selected_link_id = None
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#070D16"))

        if self.view is None:
            painter.end()
            return

        if self.pixmap.isNull():
            painter.end()
            return

        if self._fit_pending:
            self._fit_to_canvas()

        if self.is_placeholder:
            painter.save()
            painter.translate(self.offset)
            painter.scale(self.zoom, self.zoom)
            painter.setPen(QPen(QColor("#182536"), 1 / max(self.zoom, 0.01)))
            for x in range(0, self.pixmap.width(), 100):
                painter.drawLine(x, 0, x, self.pixmap.height())
            for y in range(0, self.pixmap.height(), 100):
                painter.drawLine(0, y, self.pixmap.width(), y)
            painter.setPen(QPen(QColor("#223044"), 2 / max(self.zoom, 0.01)))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
            self._draw_overlays(painter)
            self._draw_links(painter)
            painter.restore()
            self._draw_placeholder_text(painter)

        else:
            painter.save()
            painter.translate(self.offset)
            painter.scale(self.zoom, self.zoom)
            painter.drawPixmap(0, 0, self.pixmap)
            painter.setPen(QPen(QColor("#223044"), 2 / max(self.zoom, 0.01)))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
            self._draw_overlays(painter)
            self._draw_links(painter)
            painter.restore()
        painter.end()

    def _draw_placeholder_text(self, painter: QPainter) -> None:
        if not self.placeholder_text:
            return
        margin = 24
        width = min(720, max(240, self.width() - (margin * 2)))
        metrics = painter.fontMetrics()
        lines = self.placeholder_text.splitlines() or [self.placeholder_text]
        line_height = max(18, metrics.height())
        height = 28 + line_height * len(lines)
        rect = QRectF((self.width() - width) / 2, max(margin, (self.height() - height) / 2), width, height)
        painter.save()
        painter.setPen(QPen(QColor("#2E4058"), 1))
        painter.setBrush(QColor(9, 17, 28, 230))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QColor("#E7EEF8"))
        painter.drawText(rect.adjusted(16, 12, -16, -12), Qt.AlignLeft | Qt.AlignVCenter, self.placeholder_text)
        painter.restore()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_pending = True

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.view is None or self.pixmap.isNull():
            return
        position = event.position()
        image_position = self.widget_to_image(position)
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.zoom = max(0.12, min(5.0, self.zoom * factor))
        self.offset = position - QPointF(image_position.x() * self.zoom, image_position.y() * self.zoom)
        self.update()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        if self.view is None or self.pixmap.isNull():
            return
        self._left_press_pos = event.position()
        self._pan_last = event.position()
        self._panning = False
        event.accept()

    def select_at_position(self, position: QPointF) -> None:
        image_point = self.widget_to_image(position)
        link = self.link_at(image_point)
        if link is not None:
            self._selected_link_id = int(link.get("id") or -1)
            self.linkSelected.emit(link)
            self.update()
            return
        map_row = self.map_at(image_point)
        if map_row is not None:
            x = int(map_row["x"])
            y = int(map_row["y"])
            self._selected_coord = (x, y)
            self._selected_link_id = None
            self.mapSelected.emit(str(map_row.get("view_key") or self.view_key), x, y)
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        link = self.link_at(self.widget_to_image(event.position()))
        if link is not None:
            target = str(link.get("target_view_key") or "").strip()
            if target:
                self.linkActivated.emit(target)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._left_press_pos is None or not (event.buttons() & Qt.LeftButton):
            return
        position = event.position()
        if not self._panning:
            delta = position - self._left_press_pos
            if abs(delta.x()) + abs(delta.y()) < self._drag_threshold:
                return
            self._panning = True
            self.setCursor(Qt.ClosedHandCursor)
        self.offset += position - self._pan_last
        self._pan_last = position
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            return
        was_panning = self._panning
        self._panning = False
        self._left_press_pos = None
        self.unsetCursor()
        if not was_panning and self.view is not None and not self.pixmap.isNull():
            self.select_at_position(event.position())
        event.accept()

    def _fit_to_canvas(self) -> None:
        self._fit_pending = False
        if self.pixmap.isNull():
            return
        margin = 24
        available_width = max(1, self.width() - (margin * 2))
        available_height = max(1, self.height() - (margin * 2))
        scale_x = available_width / max(1, self.pixmap.width())
        scale_y = available_height / max(1, self.pixmap.height())
        self.zoom = max(0.12, min(1.0, scale_x, scale_y))
        drawn_width = self.pixmap.width() * self.zoom
        drawn_height = self.pixmap.height() * self.zoom
        self.offset = QPointF((self.width() - drawn_width) / 2, (self.height() - drawn_height) / 2)

    def widget_to_image(self, point: QPointF) -> QPointF:
        if self.zoom <= 0:
            return QPointF(0, 0)
        return QPointF((point.x() - self.offset.x()) / self.zoom, (point.y() - self.offset.y()) / self.zoom)

    def rect_for_map(self, map_row: dict[str, Any]) -> QRectF | None:
        payload = map_row.get("rect_json") or map_row.get("rect")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return None
        if not isinstance(payload, dict):
            return None
        try:
            return QRectF(
                float(payload["x"]),
                float(payload["y"]),
                float(payload["w"]),
                float(payload["h"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def map_at(self, point: QPointF) -> dict[str, Any] | None:
        for map_row in reversed(self.maps):
            rect = self.rect_for_map(map_row)
            if rect is not None and rect.contains(point):
                return map_row
        return None

    def link_at(self, point: QPointF) -> dict[str, Any] | None:
        for link in reversed(self.links):
            marker = self.link_point(link)
            if marker is None:
                continue
            radius = 18
            if (point.x() - marker.x()) ** 2 + (point.y() - marker.y()) ** 2 <= radius**2:
                return link
        return None

    def link_point(self, link: dict[str, Any]) -> QPointF | None:
        if link.get("marker_x") not in (None, "") and link.get("marker_y") not in (None, ""):
            try:
                return QPointF(float(link["marker_x"]), float(link["marker_y"]))
            except (TypeError, ValueError):
                return None
        from_x = link.get("from_x")
        from_y = link.get("from_y")
        if from_x in (None, "") or from_y in (None, ""):
            return None
        for map_row in self.maps:
            if int(map_row.get("x") or 0) == int(from_x) and int(map_row.get("y") or 0) == int(from_y):
                rect = self.rect_for_map(map_row)
                if rect is not None:
                    return rect.center()
        return None

    def _draw_overlays(self, painter: QPainter) -> None:
        for map_row in self.maps:
            rect = self.rect_for_map(map_row)
            if rect is None:
                continue
            status = normalize_status(str(map_row.get("status") or "unknown"))
            selected = self._selected_coord == (int(map_row["x"]), int(map_row["y"]))
            painter.setBrush(get_status_color(status, 118 if not selected else 170))
            painter.setPen(QPen(get_status_color(status, 230), 2.0 / max(self.zoom, 0.01)))
            painter.drawRoundedRect(rect, 3, 3)
            if selected:
                painter.setPen(QPen(QColor("#F8C84E"), 3.0 / max(self.zoom, 0.01)))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(-2, -2, 2, 2), 4, 4)

    def _draw_links(self, painter: QPainter) -> None:
        for link in self.links:
            marker = self.link_point(link)
            if marker is None:
                continue
            selected = self._selected_link_id == int(link.get("id") or -1)
            radius = 14
            polygon = QPolygonF(
                [
                    QPointF(marker.x(), marker.y() - radius),
                    QPointF(marker.x() + radius, marker.y()),
                    QPointF(marker.x(), marker.y() + radius),
                    QPointF(marker.x() - radius, marker.y()),
                ]
            )
            painter.setBrush(QColor("#F8C84E") if selected else QColor("#A98222"))
            painter.setPen(QPen(QColor("#FFE082"), 2.0 / max(self.zoom, 0.01)))
            painter.drawPolygon(polygon)

            label = str(link.get("label") or "").strip()
            if label:
                font = painter.font()
                font.setPointSizeF(max(8.0, 10.0 / max(self.zoom, 0.4)))
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor("#F2F6FF"))
                painter.drawText(QPointF(marker.x() + 18, marker.y() - 10), label)
