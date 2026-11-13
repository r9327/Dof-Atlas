"""Canonical Qt-free Unity color tokens shared by the main UI and Tk launcher.

Keep all color literals here. Importing this module must never initialize Qt,
local artwork or any game runtime; the updater is an independent small EXE.
"""
from __future__ import annotations

from collections.abc import Mapping


UNITY_PALETTE = {
    "BG": "#151821",
    "BG_GRADIENT_START": "#253967",
    "SIDEBAR": "#19243F",
    "PANEL": "#1B2746",
    "PANEL_2": "#213154",
    "PANEL_HOVER": "#2C3C69",
    "PANEL_ACTIVE": "#344978",
    # Glass/overlay surfaces are semantic Unity roles, never per-page palettes.
    "LIST_SURFACE": "#15203B",
    "NAV_SURFACE": "#19264B",
    "SCROLL_SURFACE": "#151D32",
    "TOOLTIP_SURFACE": "#192657",
    "FIELD_SURFACE": "#141D37",
    "BORDER": "#475F89",
    "BORDER_SOFT": "#354966",
    "BORDER_CARD": "#617CA6",
    "BORDER_STRONG": "#7B9BC8",
    "TEXT": "#F1F6FB",
    "TEXT_SOFT": "#D9EAF2",
    "TEXT_MUTED": "#B8C6E3",
    "TEXT_DISABLED": "#8998B6",
    "GREEN": "#9FCE51",
    "GREEN_HOVER": "#B1DC64",
    "GREEN_DARK": "#497332",
    "GREEN_BORDER": "#94BA62",
    "GUIDE_PREPARATION_BORDER": "#8299C0",
    "GUIDE_PREPARATION_TEXT": "#FFFFFF",
    "GUIDE_ITEM_TEXT": "#F6F8FE",
    "GUIDE_STATUS_TEXT": "#E4EDFC",
    "GUIDE_NAV_BORDER": "#6B87B3",
    "GUIDE_TOGGLE_TOP": "#445B89",
    "GUIDE_TOGGLE_BOTTOM": "#273A62",
    "GUIDE_TOGGLE_BORDER": "#8098BF",
    "GUIDE_TOGGLE_ACTIVE": "#536F9D",
    "GUIDE_TOGGLE_ACTIVE_BORDER": "#B8CBE8",
    "GUIDE_TOGGLE_HOVER": "#516EA0",
    # Dedicated Guide surfaces: named in the same Unity palette and not QSS literals.
    "GUIDE_COMPACT_SURFACE": "#182546",
    "GUIDE_SUMMARY_TOP": "#455B8C",
    "GUIDE_SUMMARY_BOTTOM": "#18264A",
    "GUIDE_PREPARATION_ROW": "#1F3057",
    "GUIDE_PREPARATION_ROW_BORDER": "#7295C4",
    "GUIDE_COPY_HOVER": "#668BC4",
    "GUIDE_MANUAL_NAV_SURFACE": "#131F3B",
    "SHELL_GRADIENT": "qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #192657, stop:1 #151821)",
    "PANEL_GRADIENT": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #24395F, stop:1 #192657)",
    "ACTIVE_GRADIENT": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6E9B41, stop:1 #497332)",
}


_LAUNCHER_ROLES = {
    "background": "BG",
    "panel": "PANEL",
    "border": "BORDER",
    "track": "PANEL_2",
    "text": "TEXT",
    "muted": "TEXT_MUTED",
    "accent": "GREEN",
    "accent_hover": "GREEN_HOVER",
}


def launcher_colors(palette: Mapping[str, str] | None = None) -> dict[str, str]:
    """Adapt the same Unity tokens for Tk without loading Qt or game files."""
    tokens = UNITY_PALETTE if palette is None else palette
    return {label: tokens[role] for label, role in _LAUNCHER_ROLES.items()}
