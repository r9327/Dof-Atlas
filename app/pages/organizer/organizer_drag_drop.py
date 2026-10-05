from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtWidgets import QLabel, QWidget

from .common import SESSION_SLOT_COUNT, empty_session_slot, session_is_detected, session_is_empty

_LOGGER = logging.getLogger(__name__)


class OrganizerDragDropMixin:
    def base_session_slot_object_name(self, index: int) -> str:
        if index < 0 or index >= len(self.sessions):
            return "characterSlotEmpty"
        session = self.sessions[index]
        if session_is_empty(session):
            return "characterSlotEmpty"
        return "characterSlot" if session_is_detected(session) else "characterSlotMissing"

    def set_session_row_state(self, row: QWidget, object_name: str) -> None:
        row.setObjectName(object_name)
        row.style().unpolish(row)
        row.style().polish(row)
        row.update()

    def bind_session_drag_events(self, widget: QWidget, index: int, row: QWidget) -> None:
        widget._atlas_drag_index = index
        widget._atlas_drag_row = row
        widget.installEventFilter(self)

    def eventFilter(self, watched, event) -> bool:
        index = getattr(watched, "_atlas_drag_index", None)
        row = getattr(watched, "_atlas_drag_row", None)
        if index is None or row is None:
            return super().eventFilter(watched, event)

        event_type = event.type()
        if event_type == QEvent.MouseButtonPress:
            if hasattr(event, "button") and event.button() == Qt.LeftButton:
                self.prepare_session_drag(index, row, event)
            return False

        if event_type == QEvent.MouseMove:
            if not hasattr(event, "buttons") or not (event.buttons() & Qt.LeftButton):
                return False
            if self.drag_session_index is None:
                if self.drag_pending_index != index or self.drag_start_global is None:
                    return False
                global_point = self.event_global_point(event)
                self.drag_last_global = global_point
                if (global_point - self.drag_start_global).manhattanLength() < 3:
                    return False
                self.begin_session_drag(index, row, None)
            self.update_session_drag_hover(event)
            return True

        if event_type == QEvent.MouseButtonRelease:
            if hasattr(event, "button") and event.button() == Qt.LeftButton:
                if self.drag_session_index is not None:
                    self.finish_session_drag(event)
                    return True
                self.clear_session_drag_pending()
            return False

        return super().eventFilter(watched, event)

    def event_global_point(self, event) -> QPoint:
        try:
            return event.globalPosition().toPoint()
        except AttributeError:
            return event.globalPos()

    def prepare_session_drag(self, index: int, row: QWidget, event) -> None:
        if index < 0 or index >= len(self.sessions) or session_is_empty(self.sessions[index]):
            return
        self.drag_pending_index = index
        self.drag_pending_row = row
        self.drag_start_global = self.event_global_point(event)
        self.drag_last_global = self.drag_start_global
        self.set_session_row_state(row, "characterSlotDragging")

    def clear_session_drag_pending(self) -> None:
        if self.drag_session_index is None and self.drag_pending_row is not None:
            try:
                index = self.drag_pending_index if self.drag_pending_index is not None else 0
                self.set_session_row_state(self.drag_pending_row, self.base_session_slot_object_name(index))
            except RuntimeError:
                _LOGGER.debug("Pending drag row was deleted before restyle.", exc_info=True)
        self.drag_pending_index = None
        self.drag_pending_row = None
        self.drag_start_global = None

    def session_drag_key(self, session: dict[str, Any]) -> str:
        try:
            hwnd = int(session.get("hwnd", 0))
        except (AttributeError, TypeError, ValueError):
            hwnd = 0
        name = str(session.get("nom", "")).strip() if isinstance(session, dict) else ""
        return f"hwnd:{hwnd}" if hwnd > 0 else f"name:{name}"

    def current_drag_session_index(self) -> int | None:
        if self.drag_session_key:
            for index, session in enumerate(self.sessions):
                if self.session_drag_key(session) == self.drag_session_key:
                    return index
        if self.drag_session_index is not None and 0 <= self.drag_session_index < len(self.sessions):
            return self.drag_session_index
        return None

    def begin_session_drag(self, index: int, row: QWidget, event) -> None:
        if event is not None and hasattr(event, "button") and event.button() != Qt.LeftButton:
            event.ignore()
            return
        if index < 0 or index >= len(self.sessions) or session_is_empty(self.sessions[index]):
            return
        if event is not None:
            self.drag_last_global = self.event_global_point(event)
        if self.drag_last_global is None:
            self.drag_last_global = row.mapToGlobal(QPoint(row.width() // 2, row.height() // 2))
        self.drag_session_index = index
        self.drag_session_row = row
        self.drag_session_key = self.session_drag_key(self.sessions[index])
        self.drag_session_moved = False
        self.drag_drop_index = None
        self.drag_hover_index = None
        self.set_session_row_state(row, "characterSlotDragging")
        self.show_session_drag_ghost(row, self.drag_last_global)
        row.raise_()
        row.setCursor(Qt.ClosedHandCursor)
        row.grabMouse()
        if event is not None:
            event.accept()

    def update_session_drag_hover(self, event) -> None:
        if self.drag_session_index is None:
            return
        global_point = self.event_global_point(event)
        self.drag_last_global = global_point
        self.move_session_drag_ghost(global_point)
        target_index = self.session_drop_index(global_point)
        self.drag_drop_index = target_index
        self.drag_hover_index = target_index
        if self.drag_hover_index == self.current_drag_session_index():
            self.drag_hover_index = None
        self.restyle_drag_rows()
        if event is not None:
            event.accept()

    def session_hover_index(self, global_point: QPoint) -> int | None:
        for slot, index in self.session_slot_widgets:
            local = slot.mapFromGlobal(global_point)
            if slot.rect().contains(local):
                return index
        return None

    def show_session_drag_ghost(self, row: QWidget, global_point: QPoint) -> None:
        self.clear_session_drag_ghost()
        pixmap = row.grab()
        ghost = QLabel()
        ghost.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        ghost.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        ghost.setAttribute(Qt.WA_ShowWithoutActivating, True)
        ghost.setPixmap(pixmap)
        ghost.resize(pixmap.size())
        ghost.setWindowOpacity(0.72)
        self.drag_ghost = ghost
        self.drag_ghost_offset = global_point - row.mapToGlobal(QPoint(0, 0))
        self.move_session_drag_ghost(global_point)
        ghost.show()
        ghost.raise_()

    def move_session_drag_ghost(self, global_point: QPoint) -> None:
        if self.drag_ghost is None:
            return
        self.drag_ghost.move(global_point - self.drag_ghost_offset)

    def clear_session_drag_ghost(self) -> None:
        if self.drag_ghost is None:
            return
        try:
            self.drag_ghost.close()
            self.drag_ghost.deleteLater()
        except RuntimeError:
            _LOGGER.debug("Drag ghost was already deleted during cleanup.", exc_info=True)
        self.drag_ghost = None
        self.drag_ghost_offset = QPoint(0, 0)

    def move_dragged_session_to_drop_index(self, target_index: int | None) -> bool:
        if target_index is None:
            return False
        source_index = self.current_drag_session_index()
        if source_index is None:
            return False
        target_index = max(0, min(target_index, self.session_slot_count() - 1))
        if not self.move_session_to_slot(source_index, target_index):
            self.drag_session_index = source_index
            return False
        self.drag_session_index = target_index
        self.drag_session_moved = True
        self.render_sessions()
        return True

    def reflow_session_rows(self) -> None:
        if self.sessions_grid is None:
            return
        for widget, index in self.session_slot_widgets:
            self.sessions_grid.removeWidget(widget)
            self.sessions_grid.addWidget(widget, index // 2, index % 2)
        self.sessions_content.updateGeometry()
        self.sessions_content.update()

    def restyle_drag_rows(self) -> None:
        for widget, index in self.session_slot_widgets:
            if index == self.drag_session_index and not session_is_empty(self.sessions[index]):
                object_name = "characterSlotDragging"
            elif index == self.drag_hover_index:
                object_name = "characterSlotDropTarget"
            else:
                object_name = self.base_session_slot_object_name(index)
            self.set_session_row_state(widget, object_name)

    def clear_session_drag_visuals(self) -> None:
        self.clear_session_drag_ghost()
        if self.drag_session_row is not None:
            try:
                self.drag_session_row.releaseMouse()
            except RuntimeError:
                _LOGGER.debug("Dragged row mouse grab was already released/deleted.", exc_info=True)
            try:
                self.drag_session_row.setCursor(Qt.OpenHandCursor)
            except RuntimeError:
                _LOGGER.debug("Dragged row was deleted before cursor reset.", exc_info=True)
        for widget, index in self.session_slot_widgets:
            self.set_session_row_state(widget, self.base_session_slot_object_name(index))
        self.drag_session_index = None
        self.drag_session_row = None
        self.drag_session_key = None
        self.drag_session_moved = False
        self.drag_drop_index = None
        self.drag_hover_index = None
        self.drag_pending_index = None
        self.drag_pending_row = None
        self.drag_start_global = None
        self.drag_last_global = None

    def finish_session_drag(self, event) -> None:
        if self.drag_session_index is None:
            return
        if event is not None:
            self.update_session_drag_hover(event)
        source_index = self.current_drag_session_index()
        target_index = self.drag_drop_index
        moved_live = self.drag_session_moved
        self.clear_session_drag_visuals()
        if moved_live:
            self.export_client_index()
            self.render_sessions()
            self.notify_sessions_changed()
            self.status_callback("Ordre des personnages mis à jour.")
        elif source_index is not None and target_index is not None:
            self.reorder_session(source_index, target_index)
        if event is not None:
            event.accept()

    def session_drop_index(self, global_point: QPoint) -> int | None:
        if not self.session_slot_widgets:
            return None
        ordered_slots = sorted(self.session_slot_widgets, key=lambda entry: entry[1])
        for slot, index in ordered_slots:
            local = slot.mapFromGlobal(global_point)
            if slot.rect().contains(local):
                return index
        return self.nearest_session_drop_index(global_point, ordered_slots)

    def nearest_session_drop_index(
        self,
        global_point: QPoint,
        slots: list[tuple[QWidget, int]] | None = None,
    ) -> int | None:
        ordered_slots = slots if slots is not None else sorted(self.session_slot_widgets, key=lambda entry: entry[1])
        if not ordered_slots:
            return None
        return min(
            ordered_slots,
            key=lambda entry: (
                global_point - entry[0].mapToGlobal(entry[0].rect().center())
            ).manhattanLength(),
        )[1]

    def move_session_to_slot(self, source_index: int, target_index: int) -> bool:
        while len(self.sessions) < SESSION_SLOT_COUNT:
            self.sessions.append(empty_session_slot())
        if source_index < 0 or source_index >= len(self.sessions):
            return False
        target_index = max(0, min(target_index, len(self.sessions) - 1))
        if target_index == source_index or session_is_empty(self.sessions[source_index]):
            return False
        session = self.sessions[source_index]
        if session_is_empty(self.sessions[target_index]):
            self.sessions[target_index] = session
            self.sessions[source_index] = empty_session_slot()
            return True
        self.sessions[source_index], self.sessions[target_index] = self.sessions[target_index], session
        return True

    def reorder_session(self, source_index: int, target_index: int) -> None:
        if not self.move_session_to_slot(source_index, target_index):
            return
        self.save_session_order()
        self.export_client_index()
        self.render_sessions()
        self.notify_sessions_changed()
        self.status_callback("Ordre des personnages mis à jour.")
