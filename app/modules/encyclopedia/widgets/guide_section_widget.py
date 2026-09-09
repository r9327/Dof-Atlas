from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.modules.encyclopedia.models import GuideSection
from app.storage import AtlasButton


class GuideSectionWidget(QFrame):
    def __init__(self, section: GuideSection, completed: int = 0, total: int = 0, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("GuideSectionWidget")
        self.section = section
        self.expanded = True
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)
        title = QLabel(section.title)
        title.setObjectName("GuideSectionTitle")
        title.setWordWrap(True)
        title_col.addWidget(title)
        if section.description:
            description = QLabel(section.description)
            description.setObjectName("MutedLabel")
            description.setWordWrap(True)
            title_col.addWidget(description)
        header.addLayout(title_col, 1)

        self.progress_label = QLabel(f"{completed} / {total}" if total else "")
        self.progress_label.setObjectName("MutedLabel")
        header.addWidget(self.progress_label)
        self.toggle_button = AtlasButton("⌄")
        self.toggle_button.setObjectName("GuideChevronButton")
        self.toggle_button.setFixedWidth(24)
        self.toggle_button.clicked.connect(lambda: self.set_expanded(not self.expanded))
        header.addWidget(self.toggle_button)
        root.addLayout(header)

        self.steps_container = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(5)
        root.addWidget(self.steps_container)

    def add_step(self, widget: QWidget) -> None:
        self.steps_layout.addWidget(widget)

    def finish(self) -> None:
        self.steps_layout.addStretch(1)

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = bool(expanded)
        self.steps_container.setVisible(self.expanded)
        self.toggle_button.setText("⌄" if self.expanded else "›")
