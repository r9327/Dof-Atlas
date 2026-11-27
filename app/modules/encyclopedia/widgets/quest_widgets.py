from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt

from app.quest_catalog import QuestRecord
from app.ui.unity_palette import UNITY_SIZES_PX

QUEST_ID_ROLE = Qt.UserRole + 31
QUEST_ROLE = Qt.UserRole + 32
QUEST_STATE_ROLE = Qt.UserRole + 33


class QuestListModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.quests: list[QuestRecord] = []
        self.state_by_quest: dict[int, str] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.quests)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self.quests):
            return None
        quest = self.quests[index.row()]
        if role == Qt.DisplayRole:
            return quest.name
        if role == QUEST_ID_ROLE:
            return quest.id
        if role == QUEST_ROLE:
            return quest
        if role == QUEST_STATE_ROLE:
            return self.state_by_quest.get(quest.id, "Disponible")
        if role == Qt.ToolTipRole:
            return quest.name
        if role == Qt.SizeHintRole:
            return QSize(280, UNITY_SIZES_PX["control_normal"])
        return None

    def set_quests(self, quests: list[QuestRecord], states: dict[int, str]) -> None:
        self.beginResetModel()
        self.quests = list(quests)
        self.state_by_quest = dict(states)
        self.endResetModel()

    def row_for_quest(self, quest_id: int) -> int:
        for row, quest in enumerate(self.quests):
            if quest.id == int(quest_id):
                return row
        return -1
