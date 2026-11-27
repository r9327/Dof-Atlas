from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

from app.core.numbers import format_grouped_int
from app.modules.encyclopedia.services.guide_quest_view_model import DisplayItem
from app.ui.components import AtlasButton, configure_unity_tool_button, set_unity_widget_property
from app.modules.encyclopedia.services.image_service import ENCYCLOPEDIA_IMAGE_SERVICE
from app.ui.guide_glyphs import atlas_icon


def _fallback_item_icon() -> QIcon:
    return atlas_icon("item")

def _apply_item_row_state(row: QFrame, image: QToolButton, checked: bool) -> None:
    state = "done" if checked else "todo"
    for widget in (row, image):
        set_unity_widget_property(widget, "state", state)


def set_item_row_checked(row: QWidget, checked: bool) -> None:
    """Refresh an existing preparation row without emitting a second edit."""
    image = row.findChild(QToolButton, "GuideItemIcon")
    if image is None or not image.isCheckable():
        return
    with QSignalBlocker(image):
        image.setChecked(bool(checked))
    _apply_item_row_state(row, image, bool(checked))


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

    image = configure_unity_tool_button(
        QToolButton(), object_name="GuideItemIcon", box=(26, 26), icon_size=20,
    )
    icon = QIcon()
    if item.image_path:
        pixmap = ENCYCLOPEDIA_IMAGE_SERVICE.load_scaled(Path(item.image_path), image.iconSize())
        if not pixmap.isNull():
            icon = QIcon(pixmap)
    image.setIcon(icon if not icon.isNull() else _fallback_item_icon())
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
        quantity = QLabel(f"x{format_grouped_int(item.quantity)}")
        quantity.setObjectName("GuideItemQuantity")
        layout.addWidget(quantity, 0, Qt.AlignVCenter)
    layout.addStretch(1)
    return row


__all__ = ["item_row", "set_item_row_checked"]
