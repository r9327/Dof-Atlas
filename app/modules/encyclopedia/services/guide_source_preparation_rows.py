"""Read-only semantic presentation of Ganymède's authored preparation blocks.

Only explicitly typed item/equipment runs can become a resource row. Other
authored paragraphs (including linked Quest titles) are contextual headings,
never countable objects or proof that the player owns a quantity.
The canonical source rich_blocks are never changed or rewritten.
"""
from __future__ import annotations

import re
from typing import Any

_SOURCE_ITEM_ROLES = frozenset({"item", "equipment"})
_QUANTITY_PREFIX = re.compile(r"^\s*(\d{1,4})(?:\s*[×x])?\s+", re.I)


def _typed_material_row(runs: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(runs, list) or not runs:
        raise ValueError("Source preparation requires its original text runs")
    typed = [r for r in runs if r.get("role") in _SOURCE_ITEM_ROLES]
    if not typed:
        # Preserve guide/Quest headings as grouped context, never objects.
        return {"kind": "context", "runs": runs}
    kinds = {str(r["role"]) for r in typed}
    if len(typed) != 1 or len(kinds) != 1:
        # Cannot prove a single item and quantity from one mixed source
        # paragraph: preserve the authored phrase, but do not count it.
        return {"kind": "context", "runs": runs}
    full_text = "".join(str(r["text"]) for r in runs)
    item_name = str(typed[0]["text"]).strip()
    if not item_name:
        raise ValueError("Source typed object has empty display identity")
    prefix = full_text.split(item_name, 1)[0]
    quantity = _QUANTITY_PREFIX.match(prefix)
    return {
        "kind": next(iter(kinds)),
        "name": item_name,
        "quantity": int(quantity.group(1)) if quantity else None,
        "item_id": typed[0].get("entity_id"),
        "runs": runs,
    }


def authored_material_rows(cards: Any) -> tuple[dict[str, Any], ...]:
    """Project only explicitly indexed material blocks, with original runs."""
    rows: list[dict[str, Any]] = []
    for card in cards:
        indexes = card.get("manual_preparation_block_indexes") or ()
        if not indexes:
            continue
        step = (card.get("manual_runtime_metadata") or {}).get("source_step") or {}
        actions = step.get("actions") or ()
        if not isinstance(actions, list) or len(actions) != 1:
            raise ValueError("Source material indexes require one authored action")
        blocks = actions[0].get("rich_blocks")
        if not isinstance(blocks, list):
            raise ValueError("Missing immutable source rich blocks")
        for index in indexes:
            if type(index) is not int or not 0 <= index < len(blocks):
                raise ValueError("Unverified material index")
            block = blocks[index]
            if block.get("type") in {"paragraph", "heading"}:
                rows.append(_typed_material_row(block["runs"]))
            elif block.get("type") == "checklist":
                for item in block["items"]:
                    runs = item.get("runs") or [
                        {"text": item["text"], "role": "plain"}
                    ]
                    rows.append(_typed_material_row(runs))
            else:
                raise ValueError("Unrenderable source material block")
    return tuple(rows)


_OPTIONAL_WORDS = re.compile(
    r"(?:\b(?:facultatif|facultative|optionnel|optionnelle|optional)\b"
    r"|\bsi vous (?:souhaitez|voulez)\b)", re.I,
)


def global_source_material_rows(cards: Any) -> tuple[dict[str, Any], ...]:
    """One global row per verified Ganymède item ID, never per Quest or step.

    Quantities sum only for explicit non-optional mentions, and an unknown
    quantity never becomes 1. A missing ID stays individually identifiable
    only as an unverified row; names are not trusted identifiers.
    """
    original = authored_material_rows(cards)
    grouped: dict[int, dict[str, Any]] = {}
    untyped: list[dict[str, Any]] = []
    for row in original:
        if row["kind"] == "context":
            continue  # Source headings/Quest titles belong in the author text.
        item_id = row.get("item_id")
        if type(item_id) is not int or item_id <= 0:
            untyped.append({
                "item_id": None, "kind": row["kind"], "name": row["name"],
                "quantity": None, "verified_quantity": False,
                "optional": False,
            })
            continue
        optional = bool(_OPTIONAL_WORDS.search(
            "".join(str(run["text"]) for run in row["runs"])
        ))
        if item_id not in grouped:
            grouped[item_id] = {
                "item_id": item_id, "kind": row["kind"],
                "name": row["name"], "quantity": 0,
                "verified_quantity": True, "optional": True,
            }
        current = grouped[item_id]
        if current["name"] != row["name"]:
            # Same verified ID takes precedence over an alternative spelling.
            # Never present the author's two labels as two different objects.
            pass
        if not optional:
            current["optional"] = False
            if row["quantity"] is None:
                current["verified_quantity"] = False
            elif current["verified_quantity"]:
                current["quantity"] += row["quantity"]
    return tuple(
        {**entry, "quantity": (
            entry["quantity"] if entry["verified_quantity"] and not entry["optional"]
            else None
        )}
        for entry in grouped.values()
    ) + tuple(untyped)
