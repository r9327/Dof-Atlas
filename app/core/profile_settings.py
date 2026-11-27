from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.constants import (
    KEY_DEBUG_MODE,
    KEY_ORGANIZER_MACRO_MODE,
    KEY_SCRIPT_SPEED,
    KEY_SESSION_ORDER,
    KEY_STOP_SCRIPT_HOTKEY,
    KEY_RADIAL_HOTKEY,
    KEY_RADIAL_ENABLED,
    KEY_RADIAL_EXCLUDED,
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
from app.core.zaap_shortcuts import read_zaap_button_ratios as _read_zaap_button_ratios


def default_profiles() -> dict[str, Any]:
    return {
        KEY_SWITCH_CHARACTER: True,
        KEY_SWITCH_CLICK: False,
        KEY_SWITCH_DOUBLE_CLICK: False,
        KEY_SWITCH_MOVEMENT: False,
        KEY_STOP_SCRIPT_HOTKEY: "",
        KEY_RADIAL_HOTKEY: "",
        KEY_RADIAL_ENABLED: True,
        KEY_RADIAL_EXCLUDED: [],
        KEY_ZAAP_CLICK_POSITION: ZAAP_CLICK_POSITION_DEFAULT,
        KEY_ZAAP_CLICK_LOCKED: True,
        KEY_SESSION_ORDER: [],
        KEY_TOPMOST: False,
        KEY_ORGANIZER_MACRO_MODE: "macro",
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


def read_zaap_button_ratios(
    payload: dict[str, Any] | None = None,
    *,
    path: Path = ZAAP_SHORTCUTS_FILE,
) -> tuple[float, float] | None:
    return _read_zaap_button_ratios(payload, path=path)
