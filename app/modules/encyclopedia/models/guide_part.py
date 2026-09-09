from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.encyclopedia.models.guide_activity import GuideActivity
from app.modules.encyclopedia.models.guide_chapter import GuideChapter
from app.modules.encyclopedia.models.guide_required_item import GuideRequiredItem


@dataclass(frozen=True, slots=True)
class GuidePart:
    id: str
    title: str
    order: int = 0
    part_type: str = "quest_category"
    description: str = ""
    progress_mode: str = "quests"
    level_min: int | None = None
    level_max: int | None = None
    chapters: tuple[GuideChapter, ...] = ()
    activities: tuple[GuideActivity, ...] = ()
    required_items: tuple[GuideRequiredItem, ...] = ()
    raw: dict[str, object] = field(default_factory=dict)

    @property
    def steps(self):
        return tuple(step for chapter in self.chapters for step in chapter.steps)
