"""Pure selection logic for the future Organizer radial character picker.

No Qt objects, Win32 calls or secondary character registry: the UI must pass
the existing Organizer sessions and the handles explicitly enabled for the pie.
"""
from __future__ import annotations

import math
from typing import Collection, Mapping, Any

from app.core.text import clean_auto_group_name, normalize_key
from .common import DOFUS_CLASS_DEFINITIONS


def _exact_native_id(value: object, maximum: int, *, allow_zero: bool = False) -> int | None:
    """Accept only real Win32 integer IDs or persisted ASCII decimal text."""
    if type(value) is int:
        number = value
    elif type(value) is str and value.isascii() and value.strip().isdecimal():
        try:
            number = int(value.strip())
        except (ValueError, OverflowError):
            return None
    else:
        return None
    return number if (0 if allow_zero else 1) <= number <= maximum else None


def radial_roster_key(session: Mapping[str, Any]) -> str:
    """A verified character ID when known, otherwise a process-local identity.

    The fallback includes PID to avoid selecting a different client after a
    window handle is recycled. It intentionally requires re-selection after
    reopening an unverified game client.
    """
    verified = str(session.get("character_key") or "").strip()
    if verified.startswith("character:") and len(verified) > len("character:"):
        return verified
    name = " ".join(str(session.get("nom") or "").strip().casefold().split())
    raw_pid = session.get("pid")
    pid = _exact_native_id(raw_pid if raw_pid not in (None, "") else 0,
                           2**32 - 1, allow_zero=True)
    hwnd = _exact_native_id(session.get("hwnd"), 2**64 - 1)
    if not name or hwnd is None or pid is None:
        return ""
    return f"unverified:{name}:{pid if pid > 0 else hwnd}"


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
        handle = _exact_native_id(value, 2**64 - 1)
        if handle is not None:
            selected.add(handle)
    found: list[dict[str, Any]] = []
    seen: set[int] = set()
    for session in sessions:
        if not isinstance(session, Mapping):
            # A malformed legacy/session cache must not crash the picker.
            continue
        handle = _exact_native_id(session.get("hwnd", 0), 2**64 - 1)
        if handle is None:
            continue
        label = str(session.get("nom", "") or "").strip()
        if (
            handle not in selected
            or handle in seen
            or not label
            or session.get("_empty_slot")
            or session.get("enabled") is False
        ):
            continue
        seen.add(handle)
        found.append(dict(session))
    return found[:8]


def radial_display_label(session: Mapping[str, Any]) -> str:
    """Use the character name, never a redundant breed/class-only title.

    Window titles sometimes append a breed after " - ". The class
    portrait already identifies the breed, so keep only the actual name.
    No change to the HWND/roster identity used for selection.
    """
    if not isinstance(session, Mapping):
        return ""
    raw = session.get("character_name") or session.get("nom") or ""
    if not isinstance(raw, str):
        return ""
    label = clean_auto_group_name(raw)
    key = normalize_key(label)
    if key in DOFUS_CLASS_DEFINITIONS or any(
        key == normalize_key(alias)
        for definition in DOFUS_CLASS_DEFINITIONS.values()
        for alias in definition["aliases"]
    ):
        return ""
    return label[:17]


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


def constrained_popup_center(
    cursor_x: float,
    cursor_y: float,
    bounds: tuple[float, float, float, float],
    radius: float,
) -> tuple[float, float]:
    """Keep the circular popup inside the selected screen's usable bounds.

    The UI supplies the screen containing the cursor, its availableGeometry,
    and a device-independent Qt radius. Negative multi-screen origins are valid.
    """
    left, top, width, height = (float(value) for value in bounds)
    if width <= 0 or height <= 0:
        return float(cursor_x), float(cursor_y)
    edge = max(0.0, float(radius))
    if width < edge * 2:
        center_x = left + width / 2
    else:
        center_x = min(max(float(cursor_x), left + edge), left + width - edge)
    if height < edge * 2:
        center_y = top + height / 2
    else:
        center_y = min(max(float(cursor_y), top + edge), top + height - edge)
    return center_x, center_y


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
    if (type(selected_index) is not int
            or not 0 <= selected_index < len(snapshot)):
        return None
    original = snapshot[selected_index]
    if not isinstance(original, Mapping):
        return None
    handle = _exact_native_id(original.get("hwnd"), 2**64 - 1)
    if handle is None:
        return None
    identity = str(original.get("character_key") or "").strip()
    name = str(original.get("nom") or "").strip()
    pid = original.get("pid")
    # A recycled HWND with a corrupt PID must never be released as an
    # authenticated radial target, even if its title still matches.
    if pid is not None and _exact_native_id(
        pid, 2**32 - 1, allow_zero=True,
    ) is None:
        return None
    for item in current:
        if not isinstance(item, Mapping):
            continue
        candidate = _exact_native_id(item.get("hwnd"), 2**64 - 1)
        if candidate != handle or str(item.get("nom") or "").strip() != name:
            continue
        if identity and str(item.get("character_key") or "").strip() != identity:
            continue
        if pid is not None and (
                item.get("pid") != pid
                or _exact_native_id(
                    item.get("pid"), 2**32 - 1, allow_zero=True,
                ) is None):
            continue
        return handle
    return None
