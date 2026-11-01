"""Pure selection logic for the future Organizer radial character picker.

No Qt objects, Win32 calls or secondary character registry: the UI must pass
the existing Organizer sessions and the handles explicitly enabled for the pie.
"""
from __future__ import annotations

import math
from typing import Collection, Mapping, Any


def visible_characters(
    sessions: Collection[Mapping[str, Any]],
    included_handles: Collection[int],
) -> list[dict[str, Any]]:
    """Only present, named, explicitly opted-in Organizer characters.

    Detection alone must not create a slice; windows that are not in the
    Organizer's current session list are never displayed.
    """
    selected = {int(hwnd) for hwnd in included_handles if int(hwnd) > 0}
    found: list[dict[str, Any]] = []
    seen: set[int] = set()
    for session in sessions:
        try:
            handle = int(session.get("hwnd", 0))
        except (TypeError, ValueError):
            continue
        label = str(session.get("nom", "") or "").strip()
        if (
            handle <= 0
            or handle not in selected
            or handle in seen
            or not label
            or session.get("_empty_slot")
            or session.get("enabled") is False
        ):
            continue
        seen.add(handle)
        found.append(dict(session))
    return found[:8]


def slice_count(characters: Collection[object]) -> int:
    """No padding to eight slots; zero means the popup must stay closed."""
    return min(len(characters), 8)


def selected_slice(dx: float, dy: float, count: int, dead_zone: float = 32.0) -> int | None:
    """Clockwise slots starting at 12 o'clock; None cancels at the centre."""
    if count <= 0:
        return None
    if not 1 <= count <= 8:
        raise ValueError("Organizer radial selection supports at most eight characters")
    if math.hypot(dx, dy) <= max(0.0, dead_zone):
        return None
    angle = math.atan2(dx, -dy) % (2 * math.pi)
    sector = 2 * math.pi / count
    return int((angle + sector / 2) % (2 * math.pi) / sector)
