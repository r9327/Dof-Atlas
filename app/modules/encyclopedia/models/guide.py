from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.encyclopedia.models.dofus_item import DofusItem
from app.modules.encyclopedia.models.entity_ref import EntityRef
from app.modules.encyclopedia.models.guide_part import GuidePart
from app.modules.encyclopedia.models.guide_section import GuideSection
from app.modules.encyclopedia.models.guide_step import GuideStep


@dataclass(frozen=True, slots=True)
class Guide:
    id: str
    title: str
    category: str
    category_label: str = ""
    description: str = ""
    recommended_level_min: int | None = None
    recommended_level_max: int | None = None
    reward_item_id: int | None = None
    illustration_item_id: int | None = None
    reward_item: DofusItem | None = None
    illustration_item: DofusItem | None = None
    image_path: str = ""
    order: int = 0
    completeness_status: str = "complete"
    verified_steps: int | None = None
    total_steps: int | None = None
    validation_warnings: tuple[str, ...] = ()
    generation_source: str = ""
    parts: tuple[GuidePart, ...] = ()
    sections: tuple[GuideSection, ...] = ()
    context_entities: tuple[EntityRef, ...] = ()
    validation_errors: tuple[str, ...] = ()
    search_text: str = ""
    raw: dict[str, object] = field(default_factory=dict)

    @property
    def steps(self) -> tuple[GuideStep, ...]:
        if self.parts:
            return tuple(step for part in self.parts for step in part.steps)
        return tuple(step for section in self.sections for step in section.steps)

    @property
    def quest_ids(self) -> tuple[int, ...]:
        seen: set[int] = set()
        ids: list[int] = []
        for step in self.steps:
            if step.step_type == "quest" and step.entity_id is not None and int(step.entity_id) not in seen:
                seen.add(int(step.entity_id))
                ids.append(int(step.entity_id))
        return tuple(ids)

    @property
    def required_steps(self) -> tuple[GuideStep, ...]:
        return tuple(step for step in self.steps if step.counts_for_completion)

    @property
    def linked_entities(self) -> tuple[EntityRef, ...]:
        refs: dict[tuple[str, int], EntityRef] = {}
        for ref in self.context_entities:
            refs.setdefault((ref.entity_type, ref.entity_id), ref)
        for step in self.steps:
            if step.entity_ref is not None:
                refs.setdefault((step.entity_ref.entity_type, step.entity_ref.entity_id), step.entity_ref)
            for ref in step.prerequisites:
                refs.setdefault((ref.entity_type, ref.entity_id), ref)
        return tuple(refs.values())
