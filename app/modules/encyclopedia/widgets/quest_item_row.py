from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygon
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from app.modules.encyclopedia.services.guide_quest_view_model import DisplayItem, format_number
from app.ui.components import AtlasButton
from app.ui.styles.quests import quest_item_row_stylesheet
from app.ui.theme import PALETTE


def _fallback_item_icon() -> QIcon:
    """Render the same item glyph that the legacy Guide view used."""

    pixmap = QPixmap(20, 20)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(PALETTE["GREEN"]), 1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPolygon(QPolygon([QPoint(10, 3), QPoint(16, 9), QPoint(10, 17), QPoint(4, 9)]))
    painter.end()
    return QIcon(pixmap)


def _apply_item_row_state(row: QFrame, image: QToolButton, checked: bool) -> None:
    state = "done" if checked else "todo"
    row.setProperty("state", state)
    image.setProperty("state", state)
    for widget in (row, image):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()


def item_row(
    item: DisplayItem,
    leading_widget: QWidget | None = None,
    *,
    checked: bool | None = None,
    on_toggle: Callable[[bool], None] | None = None,
    on_copy: Callable[[str], None] | None = None,
) -> QWidget:
    """Shared quest/guide item row, independent from the legacy Guide monolith."""

    row = QFrame()
    row.setObjectName("GuideItemRow")
    row.setStyleSheet(quest_item_row_stylesheet())
    layout = QHBoxLayout(row)
    layout.setContentsMargins(
        3 if checked is not None else 0,
        2 if checked is not None else 0,
        3 if checked is not None else 0,
        2 if checked is not None else 0,
    )
    layout.setSpacing(3)
    if leading_widget is not None:
        layout.addWidget(leading_widget, 0, Qt.AlignVCenter)

    icon = QIcon(item.image_path) if item.image_path and Path(item.image_path).exists() else _fallback_item_icon()
    image = QToolButton()
    image.setObjectName("GuideItemIcon")
    image.setFixedSize(26, 26)
    image.setIconSize(QSize(20, 20))
    image.setIcon(icon)
    if checked is not None:
        image.setCheckable(True)
        image.setChecked(bool(checked))
        image.setCursor(Qt.PointingHandCursor)
        image.setToolTip("Valider ou annuler cette ligne")
        image.setAccessibleName(f"Valider {item.name}")
        _apply_item_row_state(row, image, bool(checked))

        def toggle(value: bool) -> None:
            _apply_item_row_state(row, image, value)
            if on_toggle is not None:
                on_toggle(value)

        image.toggled.connect(toggle)
    else:
        image.setFocusPolicy(Qt.NoFocus)
        image.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    layout.addWidget(image, 0, Qt.AlignVCenter)

    name = AtlasButton(item.name)
    name.setObjectName("GuideItemNameButton")
    name.setToolTip("Copier le nom de l'objet")
    name.setCursor(Qt.PointingHandCursor)
    name.setProperty("copyText", item.name)
    name.clicked.connect(
        lambda _checked=False, value=item.name: (
            on_copy(value) if on_copy is not None else QApplication.clipboard().setText(value)
        )
    )
    layout.addWidget(name, 0)
    if item.quantity is not None:
        quantity = QLabel(f"x{format_number(item.quantity)}")
        quantity.setObjectName("GuideItemQuantity")
        layout.addWidget(quantity, 0, Qt.AlignVCenter)
    layout.addStretch(1)
    return row


__all__ = ["item_row"]
