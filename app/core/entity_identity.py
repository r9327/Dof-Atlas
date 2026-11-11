"""Type-safe DOFUS entity references shared by Guide, catalogue and UI.

No name, Organizer slot or source-local index is an authoritative entity ID.
This module stores identity only; assets and game facts stay with their owners.
"""
from __future__ import annotations

from app.core.character_identity import character_key

_ENTITY_ALIASES = {
    "object": "item", "resource": "item", "equipment": "item",
    "potion": "item", "soul_stone": "item", "key": "item",
    "job": "profession", "trade": "profession",
    "mob": "monster", "creature": "monster",
    "success": "achievement", "character_class": "class",
}
_ENTITY_KINDS = frozenset({
    "item", "profession", "class", "monster", "boss", "dungeon",
    "npc", "quest", "achievement", "character",
})


def canonical_entity_key(kind: str, game_id: int | str) -> str:
    """Give identical numeric IDs distinct namespaces by entity kind."""
    if not isinstance(kind, str):
        raise ValueError("entity kind must be a string")
    normalized_kind = kind.strip().casefold()
    normalized_kind = _ENTITY_ALIASES.get(normalized_kind, normalized_kind)
    if normalized_kind not in _ENTITY_KINDS:
        raise ValueError("unsupported entity kind")
    if normalized_kind == "character":
        return character_key(game_id)
    if isinstance(game_id, bool) or not isinstance(game_id, (int, str)):
        raise ValueError("entity ID must be a positive integer")
    raw = str(game_id).strip()
    if not raw.isascii() or not raw.isdigit():
        raise ValueError("entity ID must be a positive integer")
    number = int(raw)
    if number <= 0:
        raise ValueError("entity ID must be positive")
    return f"{normalized_kind}:{number}"


def parse_entity_key(value: str) -> tuple[str, int]:
    """Reject noncanonical aliases and ambiguously formatted persisted IDs."""
    if not isinstance(value, str) or ":" not in value:
        raise ValueError("invalid canonical entity reference")
    kind, raw_id = value.split(":", 1)
    if not raw_id.isascii() or not raw_id.isdigit():
        raise ValueError("invalid canonical entity ID")
    normalized = canonical_entity_key(kind, raw_id)
    if normalized != value:
        raise ValueError("noncanonical entity reference")
    return kind, int(raw_id)


__all__ = ["canonical_entity_key", "parse_entity_key"]
