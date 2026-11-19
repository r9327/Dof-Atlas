"""Lightweight Doduda list decoding without importing the Quest catalogue."""
from __future__ import annotations

from typing import Any


def array_rows(value: Any) -> list[Any]:
    """Accept a list or Doduda's {"Array": [...]} wrapper, else return []."""
    if isinstance(value, dict):
        inner = value.get("Array", [])
        return inner if isinstance(inner, list) else []
    return value if isinstance(value, list) else []
