from __future__ import annotations

"""Lightweight Zaap shortcut reader shared by macro runtime and UI settings."""

from pathlib import Path
from typing import Any

from app.constants import ZAAP_SHORTCUTS_FILE
from app.core.json_store import read_json_resilient


def parse_unit_ratio(value: Any) -> float | None:
    try:
        ratio = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if 0.0 <= ratio <= 1.0:
        return ratio
    return None


def zaap_ratios_from_payload(payload: dict[str, Any]) -> tuple[float, float] | None:
    button = payload.get("zaap_button")
    if not isinstance(button, dict):
        return None
    x_ratio = parse_unit_ratio(button.get("x_ratio"))
    y_ratio = parse_unit_ratio(button.get("y_ratio"))
    if x_ratio is None or y_ratio is None:
        return None
    return (x_ratio, y_ratio)


def read_zaap_button_ratios(payload: dict[str, Any] | None = None) -> tuple[float, float] | None:
    """Preserve the storage reader's non-profile JSON and ratio semantics."""
    if not isinstance(payload, dict):
        payload = read_json_resilient(ZAAP_SHORTCUTS_FILE, {})
    return zaap_ratios_from_payload(payload) if isinstance(payload, dict) else None
