from __future__ import annotations

import json
import math
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap, QPolygonF, QWheelEvent
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.cartography.scan_status_service import get_status_color, normalize_status
from app.core.numbers import optional_int
from app.ui.unity_palette import UNITY_MODULE_GEOMETRY_PX, UNITY_PALETTE, unity_painted_ui_color


class MapCanvasWidget(QWidget):
    mapSelected = Signal(str, int, int)
    linkSelected = Signal(object)
    linkActivated = Signal(str)
    viewChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("MapCanvas")
        self.setMinimumSize(*UNITY_MODULE_GEOMETRY_PX["world_map"]["canvas_min_size"])
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self.view: dict[str, Any] | None = None
        self.view_key = ""
        self.maps: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self._map_rects: dict[int, QRectF | None] = {}
        self._coord_rects: dict[tuple[int, int], QRectF] = {}
        self._link_points: dict[int, QPointF | None] = {}
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
        self._clear_geometry()
        for row in maps:
            rect = self._decode_map_rect(row)
            self._map_rects[id(row)] = rect
            coord = self._row_coord(row, "x", "y")
            if coord is not None and rect is not None:
                self._coord_rects.setdefault(coord, rect)
        for link in links:
            self._link_points[id(link)] = self._decode_link_point(link)
        self.asset_path = asset_path
        self.is_placeholder = is_placeholder
        self._selected_coord = None
        self._selected_link_id = None
        self._fit_pending = True
        self.update()
        if self.view_key:
            self.viewChanged.emit(self.view_key)

    def _clear_geometry(self) -> None:
        self._map_rects.clear()
        self._coord_rects.clear()
        self._link_points.clear()

    def suspend_rendering(self) -> None:
        """Drop reconstructible native pixels and hit-test geometry together."""
        self.pixmap = QPixmap()
        self._clear_geometry()
        self._left_press_pos = None
        self._panning = False
        self.unsetCursor()
        self._fit_pending = True
        self.update()

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
        painter.fillRect(self.rect(), QColor(unity_painted_ui_color("world_scan.placeholder")))

        if self.view is None or self.pixmap.isNull():
            self._draw_placeholder_text(painter)
            painter.end()
            return

        if self._fit_pending:
            self._fit_to_canvas()

        if self.is_placeholder:
            painter.save()
            painter.translate(self.offset)
            painter.scale(self.zoom, self.zoom)
            painter.setPen(QPen(QColor(UNITY_PALETTE["MAP_GRID"]), 1 / max(self.zoom, 0.01)))
            for x in range(0, self.pixmap.width(), 100):
                painter.drawLine(x, 0, x, self.pixmap.height())
            for y in range(0, self.pixmap.height(), 100):
                painter.drawLine(0, y, self.pixmap.width(), y)
        else:
            painter.save()
            painter.translate(self.offset)
            painter.scale(self.zoom, self.zoom)
            painter.drawPixmap(0, 0, self.pixmap)
        painter.setPen(QPen(QColor(UNITY_PALETTE["MAP_OUTLINE"]), 2 / max(self.zoom, 0.01)))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
        self._draw_overlays(painter)
        self._draw_links(painter)
        painter.restore()
        if self.is_placeholder:
            self._draw_placeholder_text(painter)
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
        painter.setPen(QPen(QColor(UNITY_PALETTE["BORDER"]), 1))
        glass = QColor(UNITY_PALETTE["PANEL_2"])
        glass.setAlpha(230)
        painter.setBrush(glass)
        painter.drawRoundedRect(rect, 8, 8)
        painter.setPen(QColor(UNITY_PALETTE["TEXT"]))
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

    @staticmethod
    def _row_coord(row: dict[str, Any], x_key: str, y_key: str) -> tuple[int, int] | None:
        x, y = optional_int(row.get(x_key)), optional_int(row.get(y_key))
        return (x, y) if x is not None and y is not None else None

    def rect_for_map(self, map_row: dict[str, Any]) -> QRectF | None:
        key = id(map_row)
        if key in self._map_rects:
            return self._map_rects[key]
        return self._decode_map_rect(map_row)

    @staticmethod
    def _decode_map_rect(map_row: dict[str, Any]) -> QRectF | None:
        payload = map_row.get("rect_json") or map_row.get("rect")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return None
        if not isinstance(payload, dict):
            return None
        try:
            values = tuple(float(payload[key]) for key in ("x", "y", "w", "h"))
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if not all(math.isfinite(value) for value in values) or values[2] <= 0 or values[3] <= 0:
            return None
        return QRectF(*values)

    def map_at(self, point: QPointF) -> dict[str, Any] | None:
        for map_row in reversed(self.maps):
            rect = self.rect_for_map(map_row)
            if rect is not None and self._row_coord(map_row, "x", "y") is not None and rect.contains(point):
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
        key = id(link)
        if key in self._link_points:
            return self._link_points[key]
        return self._decode_link_point(link)

    def _decode_link_point(self, link: dict[str, Any]) -> QPointF | None:
        if link.get("marker_x") not in (None, "") and link.get("marker_y") not in (None, ""):
            try:
                x, y = float(link["marker_x"]), float(link["marker_y"])
                return QPointF(x, y) if math.isfinite(x) and math.isfinite(y) else None
            except (TypeError, ValueError, OverflowError):
                return None
        coord = self._row_coord(link, "from_x", "from_y")
        rect = self._coord_rects.get(coord) if coord is not None else None
        return rect.center() if rect is not None else None

    def _draw_overlays(self, painter: QPainter) -> None:
        for map_row in self.maps:
            rect = self.rect_for_map(map_row)
            if rect is None:
                continue
            status = normalize_status(str(map_row.get("status") or "unknown"))
            coord = self._row_coord(map_row, "x", "y")
            if coord is None:
                continue
            selected = self._selected_coord == coord
            painter.setBrush(get_status_color(status, 118 if not selected else 170))
            painter.setPen(QPen(get_status_color(status, 230), 2.0 / max(self.zoom, 0.01)))
            painter.drawRoundedRect(rect, 3, 3)
            if selected:
                painter.setPen(QPen(QColor(UNITY_PALETTE["MAP_SELECTION"]), 3.0 / max(self.zoom, 0.01)))
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
            painter.setBrush(QColor(UNITY_PALETTE["MAP_SELECTION"]) if selected else QColor(UNITY_PALETTE["MAP_LINK"]))
            painter.setPen(QPen(QColor(UNITY_PALETTE["MAP_LINK_BORDER"]), 2.0 / max(self.zoom, 0.01)))
            painter.drawPolygon(polygon)

            label = str(link.get("label") or "").strip()
            if label:
                font = painter.font()
                font.setPointSizeF(max(8.0, 10.0 / max(self.zoom, 0.4)))
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor(UNITY_PALETTE["MAP_LABEL"]))
                painter.drawText(QPointF(marker.x() + 18, marker.y() - 10), label)
