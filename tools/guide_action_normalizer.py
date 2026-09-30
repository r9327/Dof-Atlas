from __future__ import annotations

"""Small boundary normalizer from runtime dictionaries to GuideAction values."""

from collections.abc import Mapping
from typing import Any

from tools.guide_action_model import GuideAction, GuideActionType


def normalize_action(payload: Mapping[str, Any]) -> GuideAction:
    raw_type = str(payload.get("action_type") or "").strip().casefold()
    try:
        action_type = GuideActionType(raw_type)
    except ValueError as exc:
        raise ValueError(f"unknown Guide action_type: {raw_type!r}") from exc
    quest_ids = tuple(int(value) for value in (payload.get("quest_ids") or ()))
    return GuideAction(
        action_type=action_type,
        actor_id=payload.get("actor_id"),
        item_id=payload.get("item_id"),
        monster_id=payload.get("monster_id"),
        quantity=int(payload.get("quantity") or 1),
        map_id=payload.get("map_id"),
        position=str(payload["position"]) if payload.get("position") is not None else None,
        quest_ids=quest_ids,
        primary_acquisition=payload.get("primary_acquisition"),
        purchase_alternative=bool(payload.get("purchase_alternative", False)),
        first_use_step=payload.get("first_use_step"),
        natural_acquisition_step=payload.get("natural_acquisition_step"),
        requires_preparation=bool(payload.get("requires_preparation", False)),
        metadata=dict(payload.get("metadata") or {}),
    )
