from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.constants import (
    KEY_DEBUG_MODE,
    KEY_SCRIPT_SPEED,
    KEY_SESSION_ORDER,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_SWITCH_CHARACTER,
    KEY_SWITCH_CLICK,
    KEY_SWITCH_DOUBLE_CLICK,
    KEY_SWITCH_MOVEMENT,
    KEY_TOPMOST,
    KEY_ZAAP_CLICK_LOCKED,
    KEY_ZAAP_CLICK_POSITION,
    ZAAP_CLICK_POSITION_DEFAULT,
    ZAAP_CLICK_X,
    ZAAP_CLICK_Y,
    ZAAP_SHORTCUTS_FILE,
)
from app.core.json_store import read_json_resilient


def default_profiles() -> dict[str, Any]:
    return {
        KEY_SWITCH_CHARACTER: True,
        KEY_SWITCH_CLICK: False,
        KEY_SWITCH_DOUBLE_CLICK: False,
        KEY_SWITCH_MOVEMENT: False,
        KEY_STOP_SCRIPT_HOTKEY: "",
        KEY_ZAAP_CLICK_POSITION: ZAAP_CLICK_POSITION_DEFAULT,
        KEY_ZAAP_CLICK_LOCKED: True,
        KEY_SESSION_ORDER: [],
        KEY_TOPMOST: False,
        KEY_SCRIPT_SPEED: "normal",
        KEY_DEBUG_MODE: False,
    }


def profile_bool(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, str):
        return value.strip().casefold() not in ("0", "false", "faux", "non", "off", "")
    return bool(value)


def parse_zaap_click_position(
    value: Any,
    default: tuple[int, int] = (ZAAP_CLICK_X, ZAAP_CLICK_Y),
) -> tuple[int, int]:
    text = str(value or "").strip()
    match = re.search(r"(-?\d+)\s*[,;:xX ]\s*(-?\d+)", text)
    if not match:
        return default
    try:
        return (max(0, int(match.group(1))), max(0, int(match.group(2))))
    except ValueError:
        return default


def parse_unit_ratio(value: Any) -> float | None:
    try:
        ratio = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if 0.0 <= ratio <= 1.0:
        return ratio
    return None


def read_zaap_button_ratios(
    payload: dict[str, Any] | None = None,
    *,
    path: Path = ZAAP_SHORTCUTS_FILE,
) -> tuple[float, float] | None:
    source = payload
    if not isinstance(source, dict):
        loaded = read_json_resilient(path, {})
        source = loaded if isinstance(loaded, dict) else {}
    button = source.get("zaap_button")
    if not isinstance(button, dict):
        return None
    x_ratio = parse_unit_ratio(button.get("x_ratio"))
    y_ratio = parse_unit_ratio(button.get("y_ratio"))
    if x_ratio is None or y_ratio is None:
        return None
    return (x_ratio, y_ratio)
