from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget


class DetailPanel(QScrollArea):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("EncyclopediaDetailPanel")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.content = QWidget()
        self.content.setObjectName("EncyclopediaDetailContent")
        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(8)
        self.setWidget(self.content)

    def clear_content(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def add_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("DetailTitle")
        label.setWordWrap(True)
        self.layout.addWidget(label)
        return label

    def add_meta(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("MutedLabel")
        label.setWordWrap(True)
        self.layout.addWidget(label)
        return label

    def add_section_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("PanelTitle")
        label.setWordWrap(True)
        self.layout.addWidget(label)
        return label

    def add_text(self, text: str, muted: bool = False) -> QLabel:
        label = QLabel(text)
        label.setObjectName("MutedLabel" if muted else "CompactLabel")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.layout.addWidget(label)
        return label

    def add_widget(self, widget: QWidget) -> QWidget:
        self.layout.addWidget(widget)
        return widget

    def finish(self) -> None:
        self.layout.addStretch(1)
