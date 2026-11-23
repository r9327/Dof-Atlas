"""Qt-free saved Craft selection primitives shared with Quest preparation."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.numbers import optional_int


def selection_item_id(row: Mapping[str, Any]) -> int | None:
    """Preserve legacy Ankama-ID precedence, including falsy-ID fallback."""
    return optional_int(row.get("ankama_id") or row.get("item_id"))
