from __future__ import annotations

from PySide6.QtCore import Signal

from app.modules.encyclopedia.models.entity_ref import EntityRef
from app.storage import AtlasButton


class EntityLinkButton(AtlasButton):
    entityActivated = Signal(str, object)

    def __init__(self, entity: EntityRef, parent=None, text: str | None = None) -> None:
        super().__init__(text or entity.label, parent)
        self.entity = entity
        self.setObjectName("EntityLinkButton")
        self.setToolTip(f"Ouvrir {entity.label}")
        self.clicked.connect(self.emit_entity)

    def emit_entity(self) -> None:
        self.entityActivated.emit(self.entity.entity_type, self.entity.entity_id)
