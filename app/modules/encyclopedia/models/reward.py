from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Reward:
    kind: str
    name: str
    quantity: int | None = None
    entity_id: int | None = None
    image_path: str = ""
    source_id: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)
