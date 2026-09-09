from __future__ import annotations


CHARACTER_KEY_PREFIX = "character:"


def character_key(character_id: object) -> str:
    """Build the one canonical Atlas business key for a Dofus character id."""

    if isinstance(character_id, bool) or not isinstance(character_id, (int, str)):
        raise ValueError("character_id must be a positive integer")
    raw = str(character_id or "").strip()
    if not raw.isdigit():
        raise ValueError("character_id must be a positive integer")
    parsed = int(raw)
    if parsed <= 0:
        raise ValueError("character_id must be a positive integer")
    return f"{CHARACTER_KEY_PREFIX}{parsed}"


def character_id_from_key(value: object) -> int | None:
    """Parse only canonical ID-backed business identities.

    Historical position-based values deliberately do not parse here. They
    belong to the compatibility/migration boundary and must never become new
    identities.
    """

    text = str(value or "").strip()
    if not text.startswith(CHARACTER_KEY_PREFIX):
        return None
    raw = text[len(CHARACTER_KEY_PREFIX) :]
    if not raw.isdigit():
        return None
    parsed = int(raw)
    if parsed <= 0:
        return None
    return parsed if text == character_key(parsed) else None


def is_character_key(value: object) -> bool:
    return character_id_from_key(value) is not None


def require_character_key(value: object) -> str:
    """Return the canonical key or reject an unsafe persistence identity."""

    character_id = character_id_from_key(value)
    if character_id is None:
        raise ValueError("character_key must use the canonical character:<id> format")
    return character_key(character_id)


__all__ = [
    "CHARACTER_KEY_PREFIX",
    "character_id_from_key",
    "character_key",
    "is_character_key",
    "require_character_key",
]
