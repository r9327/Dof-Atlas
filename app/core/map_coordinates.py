"""Pure-data coordinate normalization shared by the Guide and Macro paths.

The caller is responsible for matching its own input format (bracketed
source coordinates or DOFUS chat commands). Never import Qt or Windows here.
"""
from __future__ import annotations

import re


BRACKETED_POSITION_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")


def extract_bracketed_coordinates(value: object) -> tuple[int, int] | None:
    """Decode the first bracketed coordinate, without imposing map bounds."""
    match = BRACKETED_POSITION_RE.search(str(value or ""))
    if match is None:
        return None
    try:
        return int(match.group(1)), int(match.group(2))
    except ValueError:
        # Python limits decimal conversion for pathological source strings.
        return None


def extract_bracketed_position(value: object) -> str | None:
    """Format the same source coordinate for route keys and text consumers."""
    coords = extract_bracketed_coordinates(value)
    return f"{coords[0]},{coords[1]}" if coords is not None else None



def normalize_coordinate_pair(
    x: str, y: str, *, lower_exclusive: int = -(2**31),
) -> str | None:
    """Return canonical signed coordinates without accepting overflow.

    Keep the historical ten-digit input limit and reject the reserved
    signed-32-bit lower bound. A caller may provide its source sentinel.
    """
    parts = (x, y)
    if any(len(part.lstrip("-")) > 10 for part in parts):
        return None
    try:
        first, second = (int(part) for part in parts)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(lower_exclusive < value < 2**31 for value in (first, second)):
        return None
    return f"{first},{second}"


def canonical_declared_coordinate(value: object) -> str:
    """Strict source coordinate, without treating free text as a launch map."""
    match = BRACKETED_POSITION_RE.fullmatch(str(value or "").strip())
    if match is None:
        return ""
    position = normalize_coordinate_pair(*match.groups())
    return f"[{position}]" if position is not None else ""


def declared_quest_start(source_info: object) -> tuple[str, str, tuple[str, str]]:
    """Return declared start, source status and the two normalized declarations.

    A valid declaration may be shown when the other is invalid or conflicts,
    but is then review evidence, never a confirmed start.
    """
    info = source_info if isinstance(source_info, dict) else {}
    launch, meta = info.get("launch_position"), info.get("source_meta")
    raw = (
        str(launch.get("position") or "").strip() if isinstance(launch, dict) else "",
        str(meta.get("startCoords") or "").strip() if isinstance(meta, dict) else "",
    )
    positions = tuple(canonical_declared_coordinate(value) for value in raw)
    if not any(raw):
        status = "NO_DECLARED_START"
    elif any(value and not position for value, position in zip(raw, positions)):
        status = "INVALID_START_COORDINATES"
    elif len({position for position in positions if position}) > 1:
        status = "CONFLICTING_DECLARED_START"
    else:
        status = "LOCAL_START_DECLARED"
    return positions[0] or positions[1], status, (positions[0], positions[1])
