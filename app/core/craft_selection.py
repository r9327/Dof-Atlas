"""Qt-free saved Craft selection primitives shared with Quest preparation."""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any
from pathlib import Path

from app.core.numbers import INT32_MAX, optional_int


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
                **(row if isinstance(row, dict) else {}),
                "item_id": ident,
                "quantity": row.get("quantity") if isinstance(row, dict) else 0,
            }


def selection_quantities(payload: object, *, allow_legacy: bool = False) -> dict[int, int]:
    """Aggregate positive saved quantities consistently in source order."""
    totals: dict[int, int] = {}
    for row in iter_selection_item_rows(payload, allow_legacy=allow_legacy):
        ident = selection_item_id(row)
        quantity = optional_int(row.get("quantity") or 0)
        if ident is not None and ident > 0 and quantity is not None and quantity > 0:
            totals[ident] = totals.get(ident, 0) + quantity
    return totals


def replace_selection_quantity(payload: object, item_id: int, name: str, quantity: int) -> dict[str, Any]:
    """Replace one total, not every duplicate occurrence of that item.

    Preserve unrelated rows, source order and first-row metadata. Convert
    the old dictionary representation only when an explicit edit is made.
    """
    rows = []
    replaced = False
    for row in iter_selection_item_rows(payload, allow_legacy=True):
        if selection_item_id(row) != item_id:
            rows.append(row)
            continue
        if not replaced and quantity > 0:
            updated = dict(row)
            updated.update(selection_item_row(
                item_id, name or str(row.get("name") or ""), quantity,
            ))
            rows.append(updated)
        replaced = True
    if not replaced and quantity > 0:
        rows.append(selection_item_row(item_id, name, quantity))
    result = dict(payload) if isinstance(payload, dict) and isinstance(payload.get("items"), list) else {}
    result["items"] = rows
    return result


def _selection_schema_error(value: object) -> str | None:
    if not isinstance(value, dict):
        return "la sélection doit être un objet"
    if "items" in value and not isinstance(value["items"], list):
        return "items doit être une liste"
    return None


def read_selection_payload(path: Path) -> dict[str, Any]:
    """Read the shared selection without replacing damaged state with an empty list."""
    from app.core.json_store import read_json_validated
    return read_json_validated(path, {"items": []}, _selection_schema_error)


def persist_selection_quantity(path: Path, item_id: int, name: str, quantity: int) -> None:
    """Serialize a targeted edit against the latest shared Craft/Quest file."""
    from app.core.json_store import write_json_atomic
    from app.core.progress_coordinator import coordinator_for

    coordinator = coordinator_for(path)
    with coordinator.lock:
        payload = read_selection_payload(path)
        updated = replace_selection_quantity(payload, item_id, name, quantity)
        if updated != payload:
            write_json_atomic(path, updated)
            coordinator.mark_changed()


def clear_persisted_selection(path: Path) -> None:
    """Only an explicit full clear replaces every saved row."""
    from app.core.json_store import write_json_atomic
    from app.core.progress_coordinator import coordinator_for

    coordinator = coordinator_for(path)
    with coordinator.lock:
        payload = read_selection_payload(path)
        updated = dict(payload) if isinstance(payload.get("items"), list) else {}
        updated["items"] = []
        if updated != payload:
            write_json_atomic(path, updated)
            coordinator.mark_changed()


def resolve_selection(payload: object, get_item, *, allow_legacy: bool = False) -> dict[int, dict[str, Any]]:
    """Resolve each distinct saved item once, with the same total everywhere."""
    selection = {}
    for ident, quantity in selection_quantities(payload, allow_legacy=allow_legacy).items():
        item = get_item(ident)
        if isinstance(item, dict) and item:
            selection[ident] = {"item": item, "quantity": quantity}
    return selection


def selection_editor_maximum(quantity: int) -> int:
    """Keep ordinary counters compact without clipping a bulk craft quantity."""
    return max(999, min(INT32_MAX, max(999_999, quantity))) if quantity > 999 else 999
