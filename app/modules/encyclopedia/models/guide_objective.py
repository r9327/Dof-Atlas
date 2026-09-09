from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.encyclopedia.models.entity_ref import EntityRef


@dataclass(frozen=True, slots=True)
class GuideObjective:
    id: str
    title: str
    objective_type: str = "info"
    entity_ref: EntityRef | None = None
    quantity_current: int | None = None
    quantity_required: int | None = None
    optional: bool = False
    raw: dict[str, object] = field(default_factory=dict)
