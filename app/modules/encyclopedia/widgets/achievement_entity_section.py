from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from app.modules.encyclopedia.models.entity_ref import EntityRef


class AchievementEntityRow(QFrame):
    """Directly clickable entity line used inside achievement details."""

    entityActivated = Signal(str, object)

    def __init__(self, entity: EntityRef, parent=None) -> None:
        super().__init__(parent)
        self.entity = entity
        self.setObjectName("AchievementEntityRow")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"Ouvrir {entity.label}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)

        label = QLabel(entity.label)
        label.setObjectName("AchievementEntityRowText")
        label.setWordWrap(True)
        label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(label, 1)

        chevron = QLabel("›")
        chevron.setObjectName("AchievementEntityChevron")
        chevron.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(chevron, 0, Qt.AlignRight | Qt.AlignVCenter)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.entityActivated.emit(self.entity.entity_type, self.entity.entity_id)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class AchievementEntitySection(QFrame):
    """Shared Lot 7 entity section used by Quests, Monsters and Dungeons.

    Lots 8 and 9 can replace the rendering or navigation for a specific entity
    type without changing the achievement catalogue/detail contract.
    """

    def __init__(
        self,
        title: str,
        refs: Iterable[EntityRef],
        navigate_callback: Callable[[str, int], bool] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EntityLinksPanel")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.refs = tuple(refs)
        self.navigate_callback = navigate_callback

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        heading = QLabel(title)
        heading.setObjectName("AchievementSectionTitle")
        layout.addWidget(heading)

        for ref in self.refs:
            row = AchievementEntityRow(ref)
            row.entityActivated.connect(self.on_entity_activated)
            layout.addWidget(row)

    def on_entity_activated(self, entity_type: str, entity_id: object) -> None:
        if self.navigate_callback is None:
            return
        self.navigate_callback(str(entity_type), int(entity_id))
