from __future__ import annotations

from dataclasses import dataclass, field


GUIDE_ACTIVITY_TYPES = frozenset(
    {
        "quest",
        "dungeon",
        "solo_fight",
        "group_fight",
        "tactical_fight",
        "dreams",
        "farm",
        "slab",
        "boss",
        "other",
    }
)


@dataclass(frozen=True, slots=True)
class GuideActivity:
    activity_id: str
    activity_type: str
    quest_id: int | None = None
    objective_id: int | None = None
    quantity: int = 1
    monster_ids: tuple[int, ...] = ()
    dungeon_id: int | None = None
    boss_id: int | None = None
    item_ids: tuple[int, ...] = ()
    map_id: int | None = None
    mandatory: bool = True
    label: str = ""
    raw: dict[str, object] = field(default_factory=dict)
