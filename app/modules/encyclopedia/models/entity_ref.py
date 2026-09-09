from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EntityRef:
    entity_type: str
    entity_id: int | str
    label: str
    metadata: dict[str, object] | None = None
