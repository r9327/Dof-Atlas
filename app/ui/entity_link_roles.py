"""Shared, Qt-free presentation contract for clickable game entity names.

Category -> approved Unity palette role lives only here. No new colors,
per-guide styles, entity guessing or imports of game/Qt runtimes.
"""
from __future__ import annotations

from collections.abc import Mapping
from html import escape


ENTITY_LINK_COLOR_ROLES = {
    "monster": "DANGER_TEXT",
    "boss": "RED_HOVER",
    "item": "GREEN",
    "equipment": "BORDER_STRONG",
    "npc": "YELLOW",
    "position": "TEXT_SOFT",
    "quest": "TEXT_SOFT",
}
# Keep existing Guide consumers/source indexes compatible with the global map.
GUIDE_ENTITY_LINK_ROLES = ENTITY_LINK_COLOR_ROLES


def entity_link_colors(palette: Mapping[str, str]) -> dict[str, str]:
    """Resolve all categories from the application's current Unity palette."""
    return {
        category: palette[role]
        for category, role in ENTITY_LINK_COLOR_ROLES.items()
    }


def entity_link_markup(
    label: str,
    category: str,
    href: str,
    palette: Mapping[str, str],
) -> str:
    """One safe inline link shape for Guide, Bestiary, Quests and Dev UI.

    The caller owns the destination and identity; this helper styles only.
    Unknown categories fail closed rather than inventing a fallback link.
    """
    color = palette[ENTITY_LINK_COLOR_ROLES[category]]
    return (
        f'<a href="{escape(href, quote=True)}" '
        f'style="color:{color};text-decoration:none;">'
        f'<b>{escape(label)}</b></a>'
    )


def entity_text_markup(
    label: str, category: str, palette: Mapping[str, str],
) -> str:
    """Theme-colored non-link names, e.g. NPCs lacking a destination."""
    color = palette[ENTITY_LINK_COLOR_ROLES[category]]
    return f'<span style="color:{color};"><b>{escape(label)}</b></span>'
