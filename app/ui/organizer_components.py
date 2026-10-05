from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class CharacterSlotsPanel(QFrame):
    """Organizer card that owns the fixed eight-slot character grid layout."""

    def __init__(
        self,
        refresh_button: QWidget,
        *,
        slot_count: int,
        row_height: int,
        columns: int = 2,
        horizontal_spacing: int = 8,
        vertical_spacing: int = 6,
        card_padding: int = 12,
        card_spacing: int = 10,
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
        title_accent = QFrame()
        title_accent.setObjectName("CardTitleAccent")
        title_accent.setFixedSize(3, 16)
        header.addWidget(title_accent, alignment=Qt.AlignVCenter)
        header.addWidget(self.title, alignment=Qt.AlignVCenter)
        header.addStretch(1)
        header.addWidget(refresh_button, alignment=Qt.AlignVCenter)
        self.panel_layout.addLayout(header)

        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(horizontal_spacing)
        self.grid.setVerticalSpacing(self.vertical_spacing)
        for column in range(self.columns):
            self.grid.setColumnStretch(column, 1)
        self.panel_layout.addWidget(self.content)

    def row_count(self) -> int:
        if not self.slot_count:
            return 0
        return (self.slot_count + self.columns - 1) // self.columns

    def slot_grid_height(self) -> int:
        rows = self.row_count()
        if rows == 0:
            return 0
        return (rows * self.row_height) + ((rows - 1) * self.vertical_spacing)

    def calculated_height(self) -> int:
        margins = self.panel_layout.contentsMargins()
        header_height = max(self.title.height(), self.panel_layout.itemAt(0).sizeHint().height())
        return (
            margins.top()
            + header_height
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
