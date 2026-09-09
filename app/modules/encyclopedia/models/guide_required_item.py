from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class GuideRequiredItem:
    item_id: int | None = None
    name: str = ""
    quantity: int = 1
    item_type: str = ""
    image_path: str = ""
    mandatory: bool = True
    consumed: bool = True
    quest_id: int | None = None
    chapter_id: str = ""
    part_id: str = ""
    raw: dict[str, object] = field(default_factory=dict)
