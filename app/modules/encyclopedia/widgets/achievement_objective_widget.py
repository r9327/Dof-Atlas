from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from app.modules.encyclopedia.models.achievement import AchievementObjective
from app.modules.encyclopedia.models.entity_ref import EntityRef
from app.modules.encyclopedia.services.serialized_achievement_progress_service import AchievementProgressService


class AchievementObjectiveWidget(QFrame):
    def __init__(
        self,
        objective: AchievementObjective,
        completed: bool,
        progress_service: AchievementProgressService | None = None,
        character_key: str = "",
        text_override: str | None = None,
        entity_ref_override: EntityRef | None = None,
        navigate_callback: Callable[[str, int], bool] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ObjectiveRow")
        self.objective = objective
        self.progress_service = progress_service
        self.character_key = character_key
        self.navigate_callback = navigate_callback
        self.entity_ref = entity_ref_override or objective.entity_ref
        if self.entity_ref is not None and navigate_callback is not None:
            self.setCursor(Qt.PointingHandCursor)
            self.setToolTip(f"Ouvrir {self.entity_ref.label}")

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(8)

        self.check = QCheckBox()
        self.check.setObjectName("AchievementObjectiveCheck")
        self.check.setChecked(completed)
        self.check.setEnabled(progress_service is not None)
        if progress_service is not None:
            self.check.toggled.connect(self.on_toggled)
        root.addWidget(self.check)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        label_text = text_override or objective.text or (self.entity_ref.label if self.entity_ref is not None else "")
        title = QLabel(label_text)
        title.setObjectName("CompactLabel")
        title.setWordWrap(True)
        title.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        text_col.addWidget(title)
        root.addLayout(text_col, 1)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.LeftButton
            and self.entity_ref is not None
            and self.navigate_callback is not None
        ):
            self.navigate_callback(str(self.entity_ref.entity_type), int(self.entity_ref.entity_id))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def on_toggled(self, checked: bool) -> None:
        if self.progress_service is None:
            return
        self.progress_service.set_objective_completed(
            self.character_key,
            self.objective.achievement_id,
            self.objective.id,
            checked,
        )
