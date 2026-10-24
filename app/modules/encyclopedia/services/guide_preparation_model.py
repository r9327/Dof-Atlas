"""Conservative, pure-data preparation accounting for authored Atlas Guide cards.

No character selection, stock, progress or Ganymède action candidate is inferred
here. Qt controls may display these findings, but cannot turn an unknown amount
into a certified inventory claim.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

_EXPLICIT_QUANTITY = re.compile(
    r"\b(?:pr[ée]pare(?:r|z)?|apporte(?:r|z)?)\s+(\d+)\s*[×x]\s*(.+?)(?:[.;]|$)",
    re.IGNORECASE,
)


def normalized_name(text: str) -> str:
    decomposed = "".join(
        ch for ch in unicodedata.normalize("NFKD", str(text or "").casefold())
        if not unicodedata.combining(ch)
    )
    return " ".join("".join(ch if ch.isalnum() else " " for ch in decomposed).split())


def item_identity(item_id: int | None, name: str) -> str:
    return f"item:{item_id}" if item_id is not None else f"name:{normalized_name(name)}"


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def category_for(name: str, kind: str = "") -> str:
    category = normalized_name(kind)
    label = normalized_name(name)
    if category in {"metier", "metiers", "profession"}:
        return "Métiers"
    if "pierre d ame" in label or "soul stone" in label:
        return "Pierres d'âme"
    if "potion" in label:
        return "Potions"
    if label.startswith(("clef ", "cle ", "clefs ", "cles ")):
        return "Clefs"
    return "Objets"


def _structured_entries(raw: Any, *, origin: str = "") -> Iterable[dict[str, Any]]:
    """Unwrap nested authored preparation containers without mining actions.

    Guide Ultime can store a resource_plan with named groups of item rows.
    The caller only passes an already-authored a_preparer container, never
    source_action_candidates or general walkthrough text.
    """
    if isinstance(raw, (list, tuple)):
        for child in raw:
            yield from _structured_entries(child, origin=origin)
        return
    if not isinstance(raw, dict):
        return
    source = str(raw.get("_source_field") or origin or "")
    if any(raw.get(key) not in (None, "") for key in ("name", "label", "item", "resource")):
        row = dict(raw)
        if source:
            row.setdefault("_source_field", source)
        yield row
        return
    for key, child in raw.items():
        if key.startswith("_"):
            continue
        if isinstance(child, (dict, list, tuple)):
            yield from _structured_entries(child, origin=source or key)


def _consumption(record: dict[str, Any]) -> str:
    # No default: without a proven reusable/consumed status the amount across
    # multiple stages is ambiguous. Do not assume every displayed mention is use.
    kind = normalized_name(record.get("consumption") or record.get("usage") or "")
    if kind in {"consumable", "consumed", "usage unique"} or record.get("consumable") is True:
        return "consumable"
    if kind in {"reusable", "reutilisable", "conserve", "keep"} or record.get("reusable") is True:
        return "reusable"
    return "unknown"


@dataclass(frozen=True, slots=True)
class PreparationClaim:
    identity: str
    item_id: int | None
    name: str
    category: str
    quantity: int | None
    consumption: str
    source: str
    stage_id: str
    occurrence: str


@dataclass(frozen=True, slots=True)
class PreparationNeed:
    identity: str
    item_id: int | None
    name: str
    category: str
    quantity: int | None
    confidence: str
    claim_count: int
    sources: tuple[str, ...]


def card_claims(
    card: dict[str, Any],
    *,
    sections: dict[str, Any] | None = None,
) -> tuple[PreparationClaim, ...]:
    """Merge structured requirements and explicit authored text without mirrors.

    Two independently identified consumptions are kept; the same structured
    requirement mirrored in its 'Prépare N × ...' caption is counted once.
    Unverified source_action_candidates are never treated as stock demands.
    """
    stage = str(card.get("manual_stage_id") or "")
    claims: list[PreparationClaim] = []
    structured_keys: set[tuple[str, int | None]] = set()
    exact_rows: set[tuple[str, int | None, str, str]] = set()
    for index, raw in enumerate(_structured_entries(card.get("a_preparer", ()) or ())):
        name = str(
            raw.get("name") or raw.get("label") or raw.get("item") or raw.get("resource") or ""
        ).strip()
        if not name:
            continue
        item_id = _positive_int(raw.get("item_id"))
        quantity = _positive_int(raw.get("quantity"))
        identity = item_identity(item_id, name)
        source = str(raw.get("_source_field") or "a_preparer")
        occurrence = str(raw.get("occurrence_id") or raw.get("source_step_id") or "")
        # Without an independently identified occurrence, duplicated identical
        # source rows are display mirrors, not proof of two purchases.
        signature = (identity, quantity, source, occurrence)
        if signature in exact_rows:
            continue
        exact_rows.add(signature)
        claims.append(PreparationClaim(
            identity, item_id, name, category_for(name, str(raw.get("category") or "")),
            quantity, _consumption(raw), source, stage, occurrence or f"structured:{index}",
        ))
        structured_keys.add((item_identity(None, name), quantity))
    src_sections = sections if sections is not None else card.get("manual_sections", {})
    prepare = src_sections.get("prepare", ()) if isinstance(src_sections, dict) else ()
    seen_text: set[tuple[str, int, str]] = set()
    for index, row in enumerate(prepare or ()):
        text = str(row.get("text") or "") if isinstance(row, dict) else str(row or "")
        for match in _EXPLICIT_QUANTITY.finditer(text):
            name = " ".join(match.group(2).split()).strip()
            if not name:
                continue
            quantity = _positive_int(match.group(1))
            identity = item_identity(None, name)
            if (identity, quantity) in structured_keys:
                continue
            # Identical repeated captions have no proven distinct consumption.
            signature = (identity, quantity, text)
            if signature in seen_text:
                continue
            seen_text.add(signature)
            claims.append(PreparationClaim(
                identity, None, name, category_for(name), quantity, "unknown",
                "manual_sections.prepare", stage, f"text:{index}",
            ))
    for index, raw in enumerate(card.get("profession_gates", ()) or ()):
        name = str(
            raw.get("name") or raw.get("label") or raw.get("text") or ""
            if isinstance(raw, dict) else raw or ""
        ).strip()
        if not name:
            continue
        identity = f"profession:{normalized_name(name)}"
        if any(claim.identity == identity for claim in claims):
            continue
        claims.append(PreparationClaim(
            identity, None, name, "Métiers", None, "reusable",
            "profession_gates", stage, f"profession:{index}",
        ))
    return tuple(claims)


def aggregate_remaining(
    card_rows: Iterable[tuple[dict[str, Any], bool]],
    *,
    sections_for_card=None,
) -> tuple[PreparationNeed, ...]:
    """Aggregate only incomplete stages; report unknown rather than false sums.

    sections_for_card may apply the production filter which removes items
    obtained on the same map. Only the caller owns loading those sections.
    """
    grouped: dict[tuple[str, str], list[PreparationClaim]] = {}
    for card, complete in card_rows:
        if complete:
            continue
        sections = sections_for_card(card) if callable(sections_for_card) else None
        for claim in card_claims(card, sections=sections):
            grouped.setdefault((claim.identity, claim.category), []).append(claim)
    needs = []
    for (identity, category), group in sorted(grouped.items()):
        quantities = [claim.quantity for claim in group]
        usages = {claim.consumption for claim in group}
        if None in quantities:
            quantity = None
            confidence = "quantity_unverified"
        elif len(group) == 1:
            quantity = quantities[0]
            confidence = "single_occurrence"
        elif usages == {"consumable"}:
            quantity = sum(quantities)
            confidence = "additive_consumption"
        elif usages == {"reusable"}:
            quantity = max(quantities)
            confidence = "reusable_maximum"
        else:
            quantity = None
            confidence = "multiple_uses_ambiguous"
        first = group[0]
        needs.append(PreparationNeed(
            identity, first.item_id, first.name, category, quantity,
            confidence, len(group),
            tuple(dict.fromkeys(f"{claim.stage_id}:{claim.source}" for claim in group)),
        ))
    return tuple(needs)


__all__ = [
    "PreparationClaim", "PreparationNeed", "card_claims", "aggregate_remaining",
    "category_for", "item_identity", "normalized_name",
]
