from __future__ import annotations


from collections.abc import Iterator
from typing import Any

CHARACTER_KEY_PREFIX = "character:"
VERIFIED_NETWORK_IDENTITY = "verified_network_identity"


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


def is_verified_character_binding(row: object) -> bool:
    """All consumers require the same saved network provenance."""
    return isinstance(row, dict) and row.get("source") == VERIFIED_NETWORK_IDENTITY


def iter_verified_character_bindings(
    payload: object, *, include_legacy_slots: bool = False,
    strict_registry_keys: bool = False,
) -> Iterator[tuple[int, dict[str, Any]]]:
    """Read actual verified IDs, never promote an Organizer slot to identity.

    Keep the stricter Organizer registry-key policy and the Guide's historical
    slots reader explicit. Callers decide whether to retain or copy each row.
    """
    if not isinstance(payload, dict):
        return
    groups = ("characters", "slots") if include_legacy_slots else ("characters",)
    for group in groups:
        rows = payload.get(group)
        if not isinstance(rows, dict):
            continue
        for key, row in rows.items():
            if not is_verified_character_binding(row):
                continue
            raw_id = row.get("character_id") if group == "slots" else key
            if group == "characters" and strict_registry_keys and not str(raw_id).isdigit():
                continue
            try:
                canonical = character_key(raw_id)
                ident = int(canonical[len(CHARACTER_KEY_PREFIX):])
            except (TypeError, ValueError, OverflowError):
                continue
            yield ident, row


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
    try:
        parsed = int(raw)
    except (TypeError, ValueError, OverflowError):
        # Python rejects unbounded integer strings. An untrusted network
        # identity must return False from is_character_key(), not raise into
        # the Qt event loop or escape a UI signal handler.
        return None
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
    "VERIFIED_NETWORK_IDENTITY",
    "is_verified_character_binding",
    "iter_verified_character_bindings",
    "character_id_from_key",
    "character_key",
    "is_character_key",
    "require_character_key",
]
