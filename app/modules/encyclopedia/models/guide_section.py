from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.encyclopedia.models.guide_step import GuideStep


@dataclass(frozen=True, slots=True)
class GuideSection:
    id: str
    title: str
    description: str = ""
    order: int = 0
    steps: tuple[GuideStep, ...] = ()
    validation_errors: tuple[str, ...] = ()
    raw: dict[str, object] = field(default_factory=dict)
