from __future__ import annotations

import re
from typing import Any, Mapping

from app.modules.encyclopedia.services.adventure_route_adapter import AdventureRouteAdapter
from app.modules.encyclopedia.services.adventure_route_engine import RouteLocation


SENTINEL_COORD = -2147483648
COORD_RE = re.compile(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]")


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_map_id(value: Any) -> int | None:
    ident = _safe_int(value)
    return ident if ident is not None and ident > 0 else None


def _safe_coord(value: Any) -> int | None:
    coord = _safe_int(value)
    if coord is None or coord == SENTINEL_COORD or abs(coord) > 10000:
        return None
    return coord


def _coord_from_text(value: Any) -> tuple[int, int] | None:
    match = COORD_RE.search(str(value or ""))
    if not match:
        return None
    x = _safe_coord(match.group(1))
    y = _safe_coord(match.group(2))
    return (x, y) if x is not None and y is not None else None


def _array(value: Any) -> list[Any]:
    if isinstance(value, dict):
        inner = value.get("Array", [])
        return inner if isinstance(inner, list) else []
    return value if isinstance(value, list) else []


class GuideUltimeRouteAdapter(AdventureRouteAdapter):
    """Adventure adapter with player-safe map semantics for Guide Ultime.

    The generic adapter historically accepted Dofus' INT32_MIN coordinate
    sentinel and mapId=0 as real geographical identities.  That made thousands
    of unrelated actions look geolocated and could group mapId=0 actions
    together.  This subclass is used by V5 generation only and deliberately
    keeps the generic adapter unchanged for other application features.
    """

    def _start_location(self, quest_id: int) -> RouteLocation:
        raw = self.raw_quests.get(int(quest_id), {})
        map_ids: list[int] = []
        for row in _array(raw.get("startPosition")):
            if not isinstance(row, dict):
                continue
            ident = _safe_map_id(row.get("mapId"))
            if ident is not None and ident not in map_ids:
                map_ids.append(ident)

        quest = self.catalog.by_id.get(int(quest_id))
        source_info = getattr(quest, "source_info", {}) if quest is not None else {}
        source_info = source_info if isinstance(source_info, dict) else {}
        launch = source_info.get("launch_position") if isinstance(source_info.get("launch_position"), dict) else {}
        meta = source_info.get("source_meta") if isinstance(source_info.get("source_meta"), dict) else {}
        documentary = _coord_from_text(launch.get("position")) or _coord_from_text(meta.get("startCoords"))
        zone = str(meta.get("zone") or "").strip()
        if not zone and quest is not None:
            zones = list(getattr(quest, "zones", ()) or ())
            zone = str(zones[0] if zones else "").strip()

        if len(map_ids) == 1:
            fallback = {"x": documentary[0], "y": documentary[1]} if documentary else None
            return self._location_from_map(map_ids[0], fallback, zone=zone)
        if documentary is not None:
            return RouteLocation(x=documentary[0], y=documentary[1], zone=zone, label=f"[{documentary[0]},{documentary[1]}]")
        return RouteLocation(zone=zone, label="Départ de quête à confirmer")

    def _location_from_map(
        self,
        map_id: int | None,
        coords: Mapping[str, Any] | None,
        *,
        zone: str,
        fallback_label: str = "",
    ) -> RouteLocation:
        effective_map_id = _safe_map_id(map_id)
        row = self.raw_maps.get(effective_map_id, {}) if effective_map_id is not None else {}

        # Exact positive mapId + maps_information is the strongest local game
        # evidence.  Raw objective coords are only a fallback because many rows
        # contain INT32_MIN or stale coordinates while mapId is still correct.
        map_x = _safe_coord(row.get("posX"))
        map_y = _safe_coord(row.get("posY"))
        if map_x is not None and map_y is not None:
            x, y = map_x, map_y
        else:
            x = _safe_coord(coords.get("x")) if isinstance(coords, Mapping) else None
            y = _safe_coord(coords.get("y")) if isinstance(coords, Mapping) else None
            if x is None or y is None:
                fallback = _coord_from_text(fallback_label)
                if fallback is not None:
                    x, y = fallback

        label = f"[{x},{y}]" if x is not None and y is not None else str(fallback_label or "").strip()
        if str(SENTINEL_COORD) in label:
            label = ""
        return RouteLocation(
            map_id=effective_map_id,
            x=x,
            y=y,
            zone=str(zone or ""),
            label=label,
        )
