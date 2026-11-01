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
    selected: set[int] = set()
    for value in included_handles:
        try:
            handle = int(value)
        except (TypeError, ValueError):
            continue
        if handle > 0:
            selected.add(handle)
    found: list[dict[str, Any]] = []
    seen: set[int] = set()
    for session in sessions:
        if not isinstance(session, Mapping):
            # A malformed legacy/session cache must not crash the picker.
            continue
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


def sector_layout(count: int, label_radius: float = 96.0) -> list[tuple[float, float, float, float]]:
    """Equal slice start/end angles and label offsets in screen coordinates.

    Radians increase clockwise from the screen's positive X direction.
    Sector zero is centered at 12 o'clock, matching selected_slice.
    """
    if count <= 0:
        return []
    if count > 8:
        raise ValueError("At most eight Organizer characters can be displayed")
    span = 2.0 * math.pi / count
    radius = max(0.0, float(label_radius))
    layout: list[tuple[float, float, float, float]] = []
    for index in range(count):
        center = -math.pi / 2.0 + index * span
        start, end = center - span / 2.0, center + span / 2.0
        layout.append((start, end, radius * math.cos(center), radius * math.sin(center)))
    return layout


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


def confirmed_radial_target(
    snapshot: list[Mapping[str, Any]],
    current: list[Mapping[str, Any]],
    selected_index: int | None,
) -> int | None:
    """Fail closed if a radial sector's window vanished or changed identity.

    A slice chosen while the key is held is an identity snapshot, not a
    mutable index into a freshly sorted roster at key-release time.
    Call with `current` already filtered through visible_characters().
    """
    if selected_index is None or not 0 <= selected_index < len(snapshot):
        return None
    original = snapshot[selected_index]
    try:
        handle = int(original.get("hwnd") or 0)
    except (TypeError, ValueError):
        return None
    if handle <= 0:
        return None
    identity = str(original.get("character_key") or "").strip()
    name = str(original.get("nom") or "").strip()
    pid = original.get("pid")
    for item in current:
        if not isinstance(item, Mapping):
            continue
        try:
            candidate = int(item.get("hwnd") or 0)
        except (TypeError, ValueError):
            continue
        if candidate != handle or str(item.get("nom") or "").strip() != name:
            continue
        if identity and str(item.get("character_key") or "").strip() != identity:
            continue
        if pid is not None and item.get("pid") != pid:
            continue
        return handle
    return None
