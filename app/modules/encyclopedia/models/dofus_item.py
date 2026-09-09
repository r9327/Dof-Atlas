from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class DofusItem:
    id: int
    original_id: int
    name: str
    level: int | None
    type_id: int
    type_name: str
    description: str = ""
    icon_id: int | None = None
    image_path: str = ""
    effects: tuple[str, ...] = ()
    guide_id: str = ""
    raw: dict[str, object] = field(default_factory=dict)
