from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QVBoxLayout

from app.modules.encyclopedia.models.achievement import Achievement
from app.modules.encyclopedia.models.progress_state import ProgressState


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
        done = sum(1 for objective in achievement.objectives if progress.is_objective_completed(achievement.id, objective.id))
        total = len(achievement.objectives)
        completed = progress.is_achievement_completed(achievement.id)
        percent = 100 if completed else int(round((done / total) * 100)) if total else 0
        meta = QLabel(f"{achievement.points} point(s) • {done} / {total} objectif(s) • {percent} %")
        meta.setObjectName("MutedLabel")
        layout.addWidget(meta)
        bar = QProgressBar()
        bar.setObjectName("EncyclopediaProgressBar")
        bar.setTextVisible(False)
        bar.setRange(0, 100)
        bar.setValue(percent)
        layout.addWidget(bar)
