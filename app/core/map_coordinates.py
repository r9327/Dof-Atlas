"""Pure-data coordinate normalization shared by the Guide and Macro paths.

The caller is responsible for matching its own input format (bracketed
source coordinates or DOFUS chat commands). Never import Qt or Windows here.
"""
from __future__ import annotations

import re
from collections.abc import Mapping

from app.core.numbers import INT32_MIN, INT32_MAX


SENTINEL_COORD = INT32_MIN
BRACKETED_POSITION_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")
DOCUMENTARY_POSITION_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*(!?)\s*\]")
TRAVEL_URL_RE = re.compile(r"atlas-travel:(-?\d+),(-?\d+)")
_PAIR_RE = re.compile(r"(-?\d+),(-?\d+)")
_DIRECT_GUIDE_RE = re.compile(r"/travel (-?\d+),(-?\d+)")
_TRAVEL_RE = re.compile(r"^/travel\s+(-?\d+)\s*,\s*(-?\d+)$", re.IGNORECASE)
_ZAAP_COMMAND_RE = re.compile(r"^/zaap\s+(-?\d+)\s*,\s*(-?\d+)$", re.IGNORECASE)
_GUIDE_SEQUENCE_RE = re.compile(
    r"^/zaap\s+(-?\d+)\s*,\s*(-?\d+)\s*;\s*/travel\s+(-?\d+)\s*,\s*(-?\d+)$",
    re.IGNORECASE,
)


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
    x: str, y: str, *, lower_exclusive: int = SENTINEL_COORD,
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
    if not all(lower_exclusive < value <= INT32_MAX for value in (first, second)):
        return None
    return f"{first},{second}"


def exact_map_coordinates(value: object) -> tuple[int, int] | None:
    """Runtime evidence must carry exact signed integer coordinates, not hints."""
    if not isinstance(value, Mapping):
        return None
    x, y = value.get("x"), value.get("y")
    if type(x) is not int or type(y) is not int:
        return None
    return (x, y) if all(SENTINEL_COORD < n <= INT32_MAX for n in (x, y)) else None


def travel_command_from_pair(x: str, y: str) -> str | None:
    position = normalize_coordinate_pair(x, y)
    return f"/travel {position}" if position is not None else None


def travel_command_from_position(value: object) -> str | None:
    """Copy the first explicitly bracketed source coordinate; never infer a map."""
    match = BRACKETED_POSITION_RE.search(str(value or ""))
    return travel_command_from_pair(*match.groups()) if match is not None else None


def travel_command_from_link(value: object, *, manual: bool = False) -> str | None:
    text = str(value or "")
    if manual:
        if not text.startswith("travel-copy:"):
            return None
        match = _PAIR_RE.fullmatch(text.removeprefix("travel-copy:"))
    else:
        match = TRAVEL_URL_RE.fullmatch(text)
    return travel_command_from_pair(*match.groups()) if match is not None else None


def normalize_direct_guide_travel(value: object) -> str | None:
    """Strict UI command: a source hint can never authorize a Zaap sequence."""
    match = _DIRECT_GUIDE_RE.fullmatch(str(value or "").strip())
    return travel_command_from_pair(*match.groups()) if match is not None else None


def normalize_guide_travel_command(value: str) -> str | None:
    """Validate direct travel or a separately authorized Zaap/travel sequence."""
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    match = _TRAVEL_RE.fullmatch(text)
    if match is not None:
        return travel_command_from_pair(*match.groups())
    match = _GUIDE_SEQUENCE_RE.fullmatch(text)
    if match is None:
        return None
    parts = match.groups()
    zaap = normalize_coordinate_pair(*parts[:2])
    destination = travel_command_from_pair(*parts[2:])
    return f"/zaap {zaap} ; {destination}" if zaap is not None and destination is not None else None


def parse_zaap_command(value: str) -> tuple[int, int] | None:
    match = _ZAAP_COMMAND_RE.fullmatch(str(value or "").strip())
    canonical = normalize_coordinate_pair(*match.groups()) if match is not None else None
    return tuple(map(int, canonical.split(","))) if canonical is not None else None


def canonical_declared_coordinate(value: object) -> str:
    """Strict source coordinate, without treating free text as a launch map."""
    match = BRACKETED_POSITION_RE.fullmatch(str(value or "").strip())
    if match is None:
        return ""
    position = normalize_coordinate_pair(*match.groups())
    return f"[{position}]" if position is not None else ""


def documentary_coordinate_candidates(text: str) -> set[str | None]:
    """Normalize documentary map candidates; dimensions and invalid maps stay unknown."""
    return {
        normalize_coordinate_pair(x, y) if not marker else None
        for x, y, marker in DOCUMENTARY_POSITION_RE.findall(text)
    }


def quest_launch_instruction(source_info: object) -> str:
    """Read an independently sourced instruction, without deriving a map from it."""
    launch = source_info.get("launch_position") if isinstance(source_info, dict) else None
    if not isinstance(launch, dict):
        return ""
    instruction = launch.get("instruction")
    source_url = launch.get("source_url")
    if not isinstance(instruction, str) or not isinstance(source_url, str) or not source_url.startswith("https://"):
        return ""
    return instruction.strip()


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
        # Item use, conditional starts and special access have a useful
        # instruction but cannot supply a single travel destination.
        if quest_launch_instruction(info):
            return "", "DOCUMENTED_START", positions
        status = "NO_DECLARED_START"
    elif any(value and not position for value, position in zip(raw, positions)):
        status = "INVALID_START_COORDINATES"
    elif len({position for position in positions if position}) > 1:
        status = "CONFLICTING_DECLARED_START"
    else:
        status = "LOCAL_START_DECLARED"
    # Older imports could keep the first map. Newer imports can keep only the
    # wording. In both cases, preserve documentary ambiguity for review.
    primary = positions[0] or positions[1]
    if status in {"NO_DECLARED_START", "LOCAL_START_DECLARED"} and isinstance(launch, dict):
        source_text = launch.get("source_text")
        candidates = documentary_coordinate_candidates(source_text) if isinstance(source_text, str) else set()
        if None in candidates:
            status = "INVALID_START_COORDINATES"
        elif len(candidates) > 1 or (primary and candidates and candidates != {primary[1:-1]}):
            status = "CONFLICTING_DECLARED_START"
    return primary, status, (positions[0], positions[1])


def quest_launch_position_evidence(source_info: object) -> tuple[str, str, tuple[str, ...]]:
    """Combine native start-map and documentary declarations without guessing.

    Native evidence is compiled only from the local game's explicit
    startPosition maps and maps_information rows, never from objectives.
    Multiple map identities may establish coordinates only when all coincide.
    Contradictory documentary declarations remain visible as review evidence.
    """
    primary, status, positions = declared_quest_start(source_info)
    if status == "DOCUMENTED_START":
        return "", status, positions
    info = source_info if isinstance(source_info, dict) else {}
    native = info.get("native_start")
    map_id = native.get("map_id") if isinstance(native, dict) else None
    map_ids = native.get("map_ids") if isinstance(native, dict) else None
    coincident = (
        map_id is None and isinstance(map_ids, list) and len(map_ids) > 1
        and all(type(ident) is int and ident > 0 for ident in map_ids)
        and len(set(map_ids)) == len(map_ids)
    )
    unique = type(map_id) is int and map_id > 0 and map_ids is None
    native_position = (
        canonical_declared_coordinate(native.get("position"))
        if unique or coincident else ""
    )
    if not native_position:
        return primary, status, positions
    declared = (*positions, native_position)
    if status == "NO_DECLARED_START":
        return native_position, "NATIVE_START_DECLARED", declared
    if status == "LOCAL_START_DECLARED":
        return (
            native_position,
            "NATIVE_START_DECLARED" if primary == native_position else "CONFLICTING_DECLARED_START",
            declared,
        )
    return native_position, status, declared


def explicit_coordinate_query(value: object) -> tuple[int, int] | None:
    """Read a coordinate search, not arbitrary numbers inside a place name."""
    text = str(value or "").strip()
    match = BRACKETED_POSITION_RE.fullmatch(text) or re.fullmatch(
        r"(-?\d+)(?:\s*,\s*|\s+)(-?\d+)", text,
    )
    if match is None:
        return None
    canonical = normalize_coordinate_pair(*match.groups())
    return tuple(map(int, canonical.split(","))) if canonical is not None else None


def declared_zaap_coordinates(row: object) -> tuple[int, int] | None:
    """Use explicit local map data; refuse malformed or contradictory claims."""
    if not isinstance(row, dict):
        return None
    label = str(row.get("label") or "")
    matches = list(BRACKETED_POSITION_RE.finditer(label))
    if len(matches) > 1:
        return None
    label_coords = explicit_coordinate_query(matches[0].group(0) if matches else label)
    if matches and label_coords is None:
        return None
    if "posX" in row or "posY" in row:
        parts = (row.get("posX"), row.get("posY"))
        if any(type(part) not in (int, str) for part in parts):
            return None
        coords = explicit_coordinate_query(",".join(str(part).strip() for part in parts))
        if coords is None or (label_coords is not None and coords != label_coords):
            return None
        return coords
    return label_coords
