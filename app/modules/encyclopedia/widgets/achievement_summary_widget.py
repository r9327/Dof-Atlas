from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout

from app.modules.encyclopedia.models.achievement import Achievement
from app.modules.encyclopedia.services.achievement_progress_logic import achievement_progress_snapshot
from app.modules.encyclopedia.models.progress_state import ProgressState
from app.ui.components import configure_unity_progress_bar


class AchievementSummaryWidget(QFrame):
    def __init__(self, achievement: Achievement, progress: ProgressState, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("AchievementSummaryWidget")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(4)
        title = QLabel(achievement.name)
        title.setObjectName("PanelTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        done, total, _completed, percent = achievement_progress_snapshot(achievement, progress)
        meta = QLabel(f"{achievement.points} point(s) • {done} / {total} objectif(s) • {percent} %")
        meta.setObjectName("MutedLabel")
        layout.addWidget(meta)
        bar = configure_unity_progress_bar(
            QProgressBar(), object_name="EncyclopediaProgressBar",
        )
        bar.setValue(percent)
        layout.addWidget(bar)
