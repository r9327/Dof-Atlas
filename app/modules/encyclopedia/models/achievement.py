from __future__ import annotations

from dataclasses import dataclass, field

from app.modules.encyclopedia.models.entity_ref import EntityRef
from app.modules.encyclopedia.models.reward import Reward


@dataclass(frozen=True, slots=True)
class AchievementCategory:
    id: int
    name: str
    parent_id: int
    order: int = 0
    achievement_ids: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class AchievementObjective:
    id: int
    achievement_id: int
    text: str
    criterion: str
    order: int = 0
    objective_type: str = ""
    required_quantity: int | None = None
    entity_ref: EntityRef | None = None
    entity_refs: tuple[EntityRef, ...] = ()


@dataclass(frozen=True, slots=True)
class Achievement:
    id: int
    original_id: int
    name: str
    description: str
    category_id: int
    category_name: str
    subcategory_id: int | None
    subcategory_name: str
    level: int | None
    points: int
    icon_id: int | None = None
    image_path: str = ""
    order: int = 0
    objective_ids: tuple[int, ...] = ()
    reward_ids: tuple[int, ...] = ()
    objectives: tuple[AchievementObjective, ...] = ()
    rewards: tuple[Reward, ...] = ()
    linked_quests: tuple[EntityRef, ...] = ()
    linked_monsters: tuple[EntityRef, ...] = ()
    linked_dungeons: tuple[EntityRef, ...] = ()
    linked_achievements: tuple[EntityRef, ...] = ()
    resolved_linked_quests: tuple[EntityRef, ...] = ()
    resolved_linked_monsters: tuple[EntityRef, ...] = ()
    resolved_linked_dungeons: tuple[EntityRef, ...] = ()
    search_text: str = ""
    raw: dict[str, object] = field(default_factory=dict)
