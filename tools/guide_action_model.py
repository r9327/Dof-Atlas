from __future__ import annotations

"""Shared structured semantics for Guide runtime/UI/validation migration."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class GuideActionType(StrEnum):
    TALK = "talk"
    BUY = "buy"
    DROP = "drop"
    FIGHT = "fight"
    TRAVEL = "travel"
    INTERACT = "interact"
    USE_ITEM = "use_item"
    TURN_IN = "turn_in"


@dataclass(frozen=True, slots=True)
class GuideAction:
    action_type: GuideActionType
    actor_id: int | str | None = None
    item_id: int | str | None = None
    monster_id: int | str | None = None
    quantity: int = 1
    map_id: int | str | None = None
    position: str | None = None
    quest_ids: tuple[int, ...] = ()
    primary_acquisition: str | None = None
    purchase_alternative: bool = False
    first_use_step: str | None = None
    natural_acquisition_step: str | None = None
    requires_preparation: bool = False
    metadata: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise ValueError("GuideAction.quantity must be >= 1")
        if self.requires_preparation and self.natural_acquisition_step:
            raise ValueError("naturally acquired actions must not be marked as preparation")

    @property
    def canonical_target(self) -> tuple[str, int | str | None]:
        if self.action_type is GuideActionType.TALK:
            return ("actor", self.actor_id)
        if self.action_type in {GuideActionType.BUY, GuideActionType.DROP, GuideActionType.USE_ITEM, GuideActionType.TURN_IN}:
            return ("item", self.item_id)
        if self.action_type is GuideActionType.FIGHT:
            return ("monster", self.monster_id)
        return ("map", self.map_id)

    def to_payload(self) -> dict[str, Any]:
        """Stable JSON-safe boundary shared by runtime, UI and validators."""
        payload: dict[str, Any] = {
            "action_type": self.action_type.value,
            "quantity": self.quantity,
            "quest_ids": list(self.quest_ids),
            "purchase_alternative": self.purchase_alternative,
            "requires_preparation": self.requires_preparation,
        }
        optional = {
            "actor_id": self.actor_id,
            "item_id": self.item_id,
            "monster_id": self.monster_id,
            "map_id": self.map_id,
            "position": self.position,
            "primary_acquisition": self.primary_acquisition,
            "first_use_step": self.first_use_step,
            "natural_acquisition_step": self.natural_acquisition_step,
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload
