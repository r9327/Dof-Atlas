from __future__ import annotations

"""Canonical lightweight ID normalization for catalogue and Craft items."""

from typing import Any

from app.core.numbers import optional_int


def item_id(item: dict[str, Any]) -> int | None:
    value = item.get("id_dofus") or item.get("ankama_id") or item.get("id")
    return optional_int(value)
