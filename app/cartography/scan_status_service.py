from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor

import app.cartography.world_db as world_db

STATUS_COLORS = {
    "unknown": QColor("#303946"),
    "unverified": QColor("#D71920"),
    "verified": QColor("#16C766"),
    "current": QColor("#2F8CFF"),
    "suspect": QColor("#F8C84E"),
}


def normalize_status(status: str | None) -> str:
    value = str(status or "unknown").strip().casefold()
    if value == "doubtful":
        return "suspect"
    return value if value in STATUS_COLORS else "unknown"


def get_status_color(status: str | None, alpha: int = 130) -> QColor:
    color = QColor(STATUS_COLORS[normalize_status(status)])
    color.setAlpha(max(0, min(255, int(alpha))))
    return color


def get_map_status(view_key: str, x: int, y: int) -> str:
    for row in world_db.get_maps_for_view(view_key):
        if int(row.get("x") or 0) == int(x) and int(row.get("y") or 0) == int(y):
            return normalize_status(str(row.get("status") or "unknown"))
    return "unknown"


def mark_verified(view_key: str, x: int, y: int) -> dict[str, Any]:
    return world_db.mark_map_verified(view_key, x, y)


def mark_unverified(view_key: str, x: int, y: int) -> dict[str, Any]:
    return world_db.mark_map_unverified(view_key, x, y)


def set_current(view_key: str, x: int, y: int) -> dict[str, Any]:
    return world_db.set_current_map(view_key, x, y)
