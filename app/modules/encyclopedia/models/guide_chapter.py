from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.encyclopedia.models.guide_activity import GuideActivity
from app.modules.encyclopedia.models.guide_required_item import GuideRequiredItem
from app.modules.encyclopedia.models.guide_series import GuideSeries


@dataclass(frozen=True, slots=True)
class GuideChapter:
    id: str
    title: str
    order: int = 0
    description: str = ""
    level_min: int | None = None
    level_max: int | None = None
    series: tuple[GuideSeries, ...] = ()
    activities: tuple[GuideActivity, ...] = ()
    required_items: tuple[GuideRequiredItem, ...] = ()
    raw: dict[str, object] = field(default_factory=dict)

    @property
    def steps(self):
        return tuple(step for series in self.series for step in series.steps)
