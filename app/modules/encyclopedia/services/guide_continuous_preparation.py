"""Read-only, compact object references from an audited manual source route.

A public source action is never proof of possession, quantity, item category or
a requirement to buy. Names and item IDs are documentary hints only.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

_OBJECT_KINDS = frozenset({
    "prepare_object", "optional_preparation", "collect_object",
    "drop_object", "optional_drop", "check_object",
})


@dataclass(frozen=True, slots=True)
class SourceObjectReference:
    item_id: int
    label: str
    needed_at_step: int
    optional_or_conditional: bool
    obtainable_on_route: bool


def visible_object_references(
    route: Mapping[str, object], viewed_step_id: str
) -> tuple[SourceObjectReference, ...]:
    """Keep early-mentioned objects visible until their explicit source due step."""
    if (route.get("route_origin") != "GANYMEDE_CONTINUOUS_STEP_ORDER"
            or route.get("replacement_status") != "TRUSTED_SOURCE_STEPS"
            or route.get("auto_completion_allowed") is not False):
        raise ValueError("Object preview requires manual, source-trusted route")
    sections = route.get("sections")
    if (not isinstance(sections, list) or len(sections) != 1
            or not isinstance(sections[0], Mapping)
            or not isinstance(sections[0].get("steps"), list)):
        raise ValueError("Invalid continuous route sections")
    steps = sections[0]["steps"]
    if not steps or any(not isinstance(row, Mapping) for row in steps):
        raise ValueError("Invalid continuous route steps")
    positions = [index for index, row in enumerate(steps, 1)
                 if row.get("id") == viewed_step_id]
    if len(positions) != 1:
        raise ValueError("Viewed step is not uniquely part of this source route")
    viewed = positions[0]
    references: dict[tuple[int, int], SourceObjectReference] = {}
    for source_number, step in enumerate(steps[:viewed], 1):
        candidates = step.get("source_action_candidates", ())
        if not isinstance(candidates, (list, tuple)):
            raise ValueError("Malformed source action candidates")
        for action in candidates:
            if not isinstance(action, Mapping):
                raise ValueError("Malformed source action")
            kind = action.get("kind")
            if kind not in _OBJECT_KINDS:
                continue
            due = action.get("needed_at_source_step", source_number)
            if type(due) is not int or not source_number <= due <= len(steps):
                raise ValueError("Object reference has an invalid due step")
            if viewed > due:
                continue
            raw_ids = ([action["object_id"]] if "object_id" in action else [])
            if "object_ids" in action:
                extra = action["object_ids"]
                if not isinstance(extra, list):
                    raise ValueError("Malformed source object IDs")
                raw_ids += extra
            if not raw_ids:
                continue
            if any(type(item_id) is not int or item_id <= 0 for item_id in raw_ids):
                raise ValueError("Unverified source object identifier")
            title = action.get("label")
            if not isinstance(title, str) or not title.strip():
                raise ValueError("Missing source object label")
            optional = (
                kind.startswith("optional_")
                or action.get("optional") is True
                or bool(action.get("conditional"))
            )
            on_route = action.get("can_obtain_on_route") is True
            for item_id in dict.fromkeys(raw_ids):
                key = (item_id, due)
                candidate = SourceObjectReference(
                    item_id=item_id,
                    label=title.strip(),
                    needed_at_step=due,
                    optional_or_conditional=optional,
                    obtainable_on_route=on_route,
                )
                existing = references.get(key)
                if existing is None:
                    references[key] = candidate
                else:
                    references[key] = SourceObjectReference(
                        item_id=item_id,
                        label=existing.label,
                        needed_at_step=due,
                        optional_or_conditional=(
                            existing.optional_or_conditional or optional
                        ),
                        obtainable_on_route=(
                            existing.obtainable_on_route or on_route
                        ),
                    )
    return tuple(sorted(
        references.values(),
        key=lambda item: (item.needed_at_step, item.label.casefold(), item.item_id),
    ))


__all__ = ["SourceObjectReference", "visible_object_references"]
