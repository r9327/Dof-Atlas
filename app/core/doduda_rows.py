"""Lightweight Doduda list decoding without importing the Quest catalogue."""
from __future__ import annotations

from typing import Any

from app.core.numbers import optional_int


def array_rows(value: Any) -> list[Any]:
    """Accept a list or Doduda's {"Array": [...]} wrapper, else return []."""
    if isinstance(value, dict):
        inner = value.get("Array", [])
        return inner if isinstance(inner, list) else []
    return value if isinstance(value, list) else []


def reference_rows(payload: object) -> list[Any]:
    """One shape reader for the source's RefIds container."""
    references = payload.get("references") if isinstance(payload, dict) else None
    return array_rows(references.get("RefIds")) if isinstance(references, dict) else []


def rows_by_id(payload: object) -> dict[int, dict[str, Any]]:
    """Index real source data by ID; keep the last duplicate as before."""
    result: dict[int, dict[str, Any]] = {}
    for ref in reference_rows(payload):
        data = ref.get("data") if isinstance(ref, dict) else None
        if not isinstance(data, dict):
            continue
        ident = optional_int(data.get("id"))
        if ident is not None:
            result[ident] = data
    return result


def keyed_rows(payload: object) -> dict[int, dict[str, Any]]:
    """Resolve Doduda's parallel key/RID arrays against source references."""
    objects = payload.get("objectsById") if isinstance(payload, dict) else None
    if not isinstance(objects, dict):
        return {}
    keys = array_rows(objects.get("m_keys"))
    values = array_rows(objects.get("m_values"))
    refs_by_rid = {
        rid: ref["data"]
        for ref in reference_rows(payload)
        if isinstance(ref, dict) and isinstance(ref.get("data"), dict)
        and (rid := optional_int(ref.get("rid"))) is not None
    }
    rows: dict[int, dict[str, Any]] = {}
    for key, value in zip(keys, values):
        ident = optional_int(key)
        rid = optional_int(value.get("rid")) if isinstance(value, dict) else None
        if ident is None or rid is None:
            continue
        row = refs_by_rid.get(rid)
        if isinstance(row, dict):
            rows[ident] = row
    return rows
