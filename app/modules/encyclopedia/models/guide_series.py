from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.encyclopedia.models.guide_activity import GuideActivity
from app.modules.encyclopedia.models.guide_objective import GuideObjective
from app.modules.encyclopedia.models.guide_required_item import GuideRequiredItem
from app.modules.encyclopedia.models.guide_step import GuideStep


@dataclass(frozen=True, slots=True)
class GuideSeries:
    id: str
    title: str
    order: int = 0
    achievement_id: int | None = None
    description: str = ""
    quest_ids: tuple[int, ...] = ()
    steps: tuple[GuideStep, ...] = ()
    objectives: tuple[GuideObjective, ...] = ()
    activities: tuple[GuideActivity, ...] = ()
    required_items: tuple[GuideRequiredItem, ...] = ()
    chapter_info: tuple[str, ...] = ()
    source_reference: str = ""
    local_resolution_status: str = "resolved"
    raw: dict[str, object] = field(default_factory=dict)

    @property
    def required_steps(self) -> tuple[GuideStep, ...]:
        return tuple(step for step in self.steps if step.counts_for_completion)
