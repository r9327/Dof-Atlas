"""Qt-free saved Craft selection primitives shared with Quest preparation."""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from app.core.numbers import optional_int


def selection_item_id(row: Mapping[str, Any]) -> int | None:
    """Preserve legacy Ankama-ID precedence, including falsy-ID fallback."""
    return optional_int(row.get("ankama_id") or row.get("item_id"))


def selection_item_row(item_id: int, name: str, quantity: int) -> dict[str, Any]:
    """Canonical persisted row for Craft and Quest preparation editors."""
    return {
        "item_id": item_id,
        "ankama_id": item_id,
        "name": name,
        "quantity": quantity,
    }


def iter_selection_item_rows(
    payload: object, *, allow_legacy: bool = False,
) -> Iterator[dict[str, Any]]:
    """Read valid saved rows; Quest-only legacy mappings stay opt-in."""
    if not isinstance(payload, dict):
        return
    rows = payload.get("items")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                yield row
        return
    if allow_legacy:
        for ident, row in payload.items():
            yield {
                "item_id": ident,
                "quantity": row.get("quantity") if isinstance(row, dict) else 0,
            }
