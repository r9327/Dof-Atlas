from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QListView

from app.constants import LOGO_PATH
from app.modules.encyclopedia.models.achievement import Achievement
from app.modules.encyclopedia.models.progress_state import ProgressState

ACHIEVEMENT_ID_ROLE = Qt.UserRole + 1
ACHIEVEMENT_ROLE = Qt.UserRole + 2


class AchievementListModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.achievements: list[Achievement] = []
        self.progress = ProgressState()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.achievements)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self.achievements):
            return None
        achievement = self.achievements[index.row()]
        completed = self.progress.is_achievement_completed(achievement.id)
        done_objectives = sum(1 for objective in achievement.objectives if self.progress.is_objective_completed(achievement.id, objective.id))
        total_objectives = len(achievement.objectives)
        if role == Qt.DisplayRole:
            status = "✓" if completed else " "
            level = f"Niv. {achievement.level}" if achievement.level is not None else "Niv. ?"
            progress = f"{done_objectives}/{total_objectives} obj." if total_objectives else "0 obj."
            return f"{status} {achievement.name}\n{level} · {achievement.points} pts · {progress}"
        if role == Qt.DecorationRole:
            if achievement.image_path and Path(achievement.image_path).exists():
                return QIcon(achievement.image_path)
            if LOGO_PATH.exists():
                return QIcon(str(LOGO_PATH))
        if role == Qt.ToolTipRole:
            return achievement.description or achievement.name
        if role == ACHIEVEMENT_ID_ROLE:
            return achievement.id
        if role == ACHIEVEMENT_ROLE:
            return achievement
        if role == Qt.SizeHintRole:
            return QSize(260, 48)
        return None

    def set_achievements(self, achievements: list[Achievement]) -> None:
        self.beginResetModel()
        self.achievements = list(achievements)
        self.endResetModel()

    def set_progress(self, progress: ProgressState) -> None:
        self.progress = progress
        if self.achievements:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self.achievements) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole])

    def achievement_at(self, index: QModelIndex) -> Achievement | None:
        if not index.isValid() or index.row() < 0 or index.row() >= len(self.achievements):
            return None
        return self.achievements[index.row()]


class ResultList(QListView):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("EncyclopediaResultList")
        self.setUniformItemSizes(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setSelectionMode(QListView.SingleSelection)
