from __future__ import annotations

_CATALOG_ROUTE_MAP_COUNT_HINTS = {
    "dofus_sylvestre": 237,
}


def catalog_route_map_count_hint(guide_id: str) -> int:
    """Return certified metadata-only route counts for the Guide catalogue."""

    return max(0, int(_CATALOG_ROUTE_MAP_COUNT_HINTS.get(str(guide_id or ""), 0)))


__all__ = ["catalog_route_map_count_hint"]
