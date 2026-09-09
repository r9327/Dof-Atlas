from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.encyclopedia.models.entity_ref import EntityRef

GUIDE_STEP_TYPES = frozenset(
    {
        "info",
        "quest",
        "achievement",
        "dungeon",
        "monster",
        "wanted",
        "archmonster",
    }
)


@dataclass(frozen=True, slots=True)
class GuideStep:
    id: str
    step_type: str
    order: int
    title: str = ""
    content: str = ""
    entity_id: int | None = None
    optional: bool = False
    notes: str = ""
    prerequisites: tuple[EntityRef, ...] = ()
    entity_ref: EntityRef | None = None
    available: bool = True
    validation_errors: tuple[str, ...] = ()
    raw: dict[str, object] = field(default_factory=dict)

    @property
    def display_title(self) -> str:
        if self.entity_ref is not None:
            return self.entity_ref.label
        return self.title or self.content or self.id

    @property
    def counts_for_completion(self) -> bool:
        return not self.optional
