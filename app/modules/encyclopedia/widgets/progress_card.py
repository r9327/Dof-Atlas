from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout


class ProgressCard(QFrame):
    def __init__(self, title: str = "Progression", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ProgressCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        self.title = QLabel(title)
        self.title.setObjectName("PanelTitle")
        self.value_label = QLabel("")
        self.value_label.setObjectName("MutedLabel")
        self.bar = QProgressBar()
        self.bar.setObjectName("EncyclopediaProgressBar")
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        layout.addWidget(self.title)
        layout.addWidget(self.value_label)
        layout.addWidget(self.bar)

    def set_progress(self, completed: int, total: int) -> None:
        total = max(0, int(total))
        completed = max(0, min(int(completed), total)) if total else 0
        percent = int(round((completed / total) * 100)) if total else 0
        self.value_label.setText(f"{completed} / {total} · {percent}%")
        self.bar.setValue(percent)
