from __future__ import annotations

"""Canonical lightweight ID normalization for catalogue and Craft items."""

from typing import Any


def item_id(item: dict[str, Any]) -> int | None:
    value = item.get("id_dofus") or item.get("ankama_id") or item.get("id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


