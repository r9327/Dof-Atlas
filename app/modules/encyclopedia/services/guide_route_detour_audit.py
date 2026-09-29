from __future__ import annotations

import re
from typing import Any, Iterable


_COORD_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")
_SENTINEL_COORD = -2147483648
_BARRIER_FIELDS = (
    "entry",
    "activation",
    "prerequisite",
    "prerequisites",
    "requirements",
    "hard_gates",
    "conditions",
    "runtime_conditions",
    "runtime_gate",
    "runtime_gates",
    "hard_runtime_gates",
    "temporal_hook",
    "temporal_hooks",
    "conditional_route",
)


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return bool(value)


def _coord_pair(value_x: Any, value_y: Any) -> tuple[int, int] | None:
    try:
        x = int(value_x)
        y = int(value_y)
    except (TypeError, ValueError):
        return None
    if x == _SENTINEL_COORD or y == _SENTINEL_COORD:
        return None
    return x, y


def card_map_key(card: dict[str, Any]) -> str:
    """Return a stable map key only when the card exposes concrete coordinates."""

    direct = _coord_pair(card.get("x"), card.get("y"))
    if direct is not None:
        return f"{direct[0]},{direct[1]}"

    destination = str(card.get("destination") or "")
    match = _COORD_RE.search(destination)
    if match:
        return f"{int(match.group(1))},{int(match.group(2))}"

    stage = card.get("manual_stage_data")
    if isinstance(stage, dict):
        direct = _coord_pair(stage.get("x"), stage.get("y"))
        if direct is not None:
            return f"{direct[0]},{direct[1]}"
        for field in ("start", "entry", "destination", "position"):
            match = _COORD_RE.search(str(stage.get(field) or ""))
            if match:
                return f"{int(match.group(1))},{int(match.group(2))}"
    return ""


def has_explicit_route_barrier(card: dict[str, Any]) -> bool:
    """Conservatively identify cards that may make a revisit causally necessary."""

    sources: list[dict[str, Any]] = [card]
    stage = card.get("manual_stage_data")
    if isinstance(stage, dict):
        sources.append(stage)
    return any(_nonempty(source.get(field)) for source in sources for field in _BARRIER_FIELDS)


def _stage_id(card: dict[str, Any]) -> str:
    return str(card.get("manual_stage_id") or card.get("id") or "").strip()


def _segments(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for index, card in enumerate(cards):
        key = card_map_key(card)
        if not key:
            # Unknown location deliberately breaks the chain: do not infer a detour
            # across a stage whose real movement is not known.
            current = None
            result.append({"map": "", "start": index, "end": index})
            continue
        if current is not None and current["map"] == key and current["end"] == index - 1:
            current["end"] = index
            continue
        current = {"map": key, "start": index, "end": index}
        result.append(current)
    return result


def find_avoidable_revisits(cards: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return conservative A→…→A route-review candidates.

    The function never reorders cards. A revisit is reported only when every card
    between the first departure and the return has concrete map data and none of
    those cards exposes an explicit prerequisite/runtime/temporal barrier. The
    result is therefore a review queue, not an automatic routing decision.
    """

    rows = [card for card in cards if isinstance(card, dict)]
    segments = _segments(rows)
    findings: list[dict[str, Any]] = []

    for left_index, left in enumerate(segments):
        map_key = str(left.get("map") or "")
        if not map_key:
            continue
        for right_index in range(left_index + 2, len(segments)):
            right = segments[right_index]
            if not right.get("map"):
                break
            if right.get("map") != map_key:
                continue

            first_end = int(left["end"])
            return_start = int(right["start"])
            window = rows[first_end + 1 : int(right["end"]) + 1]
            if any(has_explicit_route_barrier(card) for card in window):
                break

            intermediate = [
                str(segment["map"])
                for segment in segments[left_index + 1 : right_index]
                if segment.get("map")
            ]
            findings.append(
                {
                    "map": map_key,
                    "first_card_index": int(left["start"]),
                    "first_card_end_index": first_end,
                    "return_card_index": return_start,
                    "return_card_end_index": int(right["end"]),
                    "gap_card_count": max(0, return_start - first_end - 1),
                    "intermediate_maps": intermediate,
                    "first_stage_id": _stage_id(rows[int(left["start"])]),
                    "return_stage_id": _stage_id(rows[return_start]),
                }
            )
            # Report the nearest safe revisit for this departure. A later return
            # would otherwise duplicate the same actionable review.
            break

    return findings
