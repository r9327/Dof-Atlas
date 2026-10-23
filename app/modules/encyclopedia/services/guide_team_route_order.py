"""Topological team action ordering with a participant-scoped travel heuristic.

Only canonical RouteAction prerequisites decide *when* actions are allowed.
The geographic score is an estimate using existing engine weights, not a
verified transit path, route duration, distance or actual economy.
"""
from __future__ import annotations

from collections.abc import Mapping
from math import hypot, inf
from typing import Any


def order_team_actions(
    successors: Mapping[str, set[str]],
    incoming: Mapping[str, int],
    memberships: Mapping[str, list[tuple[int, str]]],
    engine: Any,
    participant_starts: Mapping[str, Any],
) -> tuple[str, ...] | None:
    """Choose cheapest ready action, updating only characters it concerns."""
    pending = dict(incoming)
    if set(pending) != set(memberships) or set(pending) != set(successors):
        raise ValueError("Action graph and selected memberships differ")
    known = set(participant_starts)
    member_keys: dict[str, tuple[str, ...]] = {}
    for action_id, rows in memberships.items():
        keys = tuple(dict.fromkeys(key for _index, key in rows))
        if not keys or any(key not in known for key in keys):
            raise ValueError("Unknown or missing participant membership")
        member_keys[action_id] = keys

    current = dict(participant_starts)
    visited_zones: dict[str, set[str]] = {key: set() for key in known}
    visited_maps: dict[str, set[tuple[object, ...]]] = {
        key: set() for key in known
    }
    for key, location in current.items():
        if location is None or location.key[0] == "unknown":
            continue
        visited_maps[key].add(location.key)
        if location.zone_key:
            visited_zones[key].add(location.zone_key)

    available = {action_id for action_id, degree in pending.items()
                 if degree == 0}
    ordered: list[str] = []

    def priority(action_id: str) -> tuple[float, float, int, str]:
        action = engine.by_id[action_id]
        score = sum(
            engine._movement_cost(
                current[key], action.location,
                visited_zones=visited_zones[key],
                visited_maps=visited_maps[key],
            )
            for key in member_keys[action_id]
        )
        # The engine deliberately rounds short same-zone trips to one cost.
        # Break those ties with comparable coordinates before source order.
        distance = 0.0
        for key in member_keys[action_id]:
            origin, destination = current[key], action.location
            if (origin is None or not origin.zone_key
                    or origin.zone_key != destination.zone_key
                    or any(value is None for value in (
                        origin.x, origin.y, destination.x, destination.y,
                    ))):
                distance = inf
                break
            distance += hypot(destination.x - origin.x, destination.y - origin.y)
        return (
            round(score, 7),
            distance,
            min(index for index, _key in memberships[action_id]),
            action_id,
        )

    while available:
        action_id = min(available, key=priority)
        available.remove(action_id)
        location = engine.by_id[action_id].location
        ordered.append(action_id)
        if location.key[0] != "unknown":
            for key in member_keys[action_id]:
                current[key] = location
                visited_maps[key].add(location.key)
                if location.zone_key:
                    visited_zones[key].add(location.zone_key)
        for successor in successors[action_id]:
            pending[successor] -= 1
            if pending[successor] == 0:
                available.add(successor)
    return tuple(ordered) if len(ordered) == len(pending) else None


__all__ = ["order_team_actions"]
