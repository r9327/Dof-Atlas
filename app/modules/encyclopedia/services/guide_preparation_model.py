"""Conservative, pure-data preparation accounting for authored Atlas Guide cards.

No character selection, stock, progress or Ganymède action candidate is inferred
here. Qt controls may display these findings, but cannot turn an unknown amount
into a certified inventory claim.
"""
from __future__ import annotations

import json
import re
import unicodedata
import zlib
from dataclasses import dataclass
from typing import Any, Iterable

_COMPACT_DECODE_LIMIT = 4 * 1024 * 1024
_COMPACT_PREPARATION_FIELDS = (
    "preparation", "a_preparer", "resource_plan", "resources",
    "required_items", "items_to_prepare", "manual_preparation",
    "keep_in_bank", "bank_items",
)
_COMPACT_PROFESSION_FIELDS = (
    "profession", "professions", "profession_gates", "jobs",
)
_COMPACT_GATE_FIELDS = (
    "conditions", "runtime_conditions", "runtime_gate",
    "runtime_gates", "hard_runtime_gates", "hard_gates",
)


def _compact_data(payload: Any, expected_type: type) -> Any | None:
    """Read one compressed source, never hydrate the Qt card or all 267 cards."""
    if not isinstance(payload, (bytes, bytearray)) or len(payload) > _COMPACT_DECODE_LIMIT:
        return None
    try:
        decoder = zlib.decompressobj()
        raw = decoder.decompress(bytes(payload), _COMPACT_DECODE_LIMIT + 1)
        if not decoder.eof or len(raw) > _COMPACT_DECODE_LIMIT:
            return None
        decoded = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError, TypeError, zlib.error):
        return None
    return decoded if isinstance(decoded, expected_type) else None


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
    if category in {"prerequis", "prerequisite", "gate", "condition"}:
        return "Prérequis"
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


def _gate_labels(raw: Any) -> Iterable[str]:
    """Yield only human-readable authored constraints; never invent an ID's name."""
    if isinstance(raw, str):
        text = " ".join(raw.split()).strip()
        if text:
            yield text
        return
    if isinstance(raw, (list, tuple)):
        for row in raw:
            yield from _gate_labels(row)
        return
    if not isinstance(raw, dict):
        return
    for key in ("label", "name", "text", "description", "requirement",
                "condition", "warning", "policy"):
        text = raw.get(key)
        if isinstance(text, str) and text.strip():
            yield " ".join(text.split())
            return
    for value in raw.values():
        if isinstance(value, (list, tuple, dict)):
            yield from _gate_labels(value)


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
    """Merge authored evidence, including compact stage payloads, without Qt.

    The compact route stays compressed: decode one card at a time, do not call
    manual_lines_for_card/manual_sections_for_card, and never modify the card.
    """
    if isinstance(card.get("_manual_stage_payload"), (bytes, bytearray)):
        stage_source = _compact_data(card.get("_manual_stage_payload"), dict)
        if stage_source is None:
            return ()
        authored_rows: list[dict[str, Any]] = []
        captions: list[dict[str, str]] = []
        for field in _COMPACT_PREPARATION_FIELDS:
            value = stage_source.get(field)
            authored_rows.extend(_structured_entries(value, origin=field))
            if isinstance(value, str):
                captions.append({"text": value})
        chapter_rows = _compact_data(card.get("_manual_chapter_preparation_payload"), list)
        if chapter_rows:
            authored_rows.extend(_structured_entries(
                chapter_rows, origin="chapter_preparation",
            ))
        professions = []
        for field in _COMPACT_PROFESSION_FIELDS:
            value = stage_source.get(field)
            if isinstance(value, (list, tuple)):
                professions.extend(value)
            elif value not in (None, "", False):
                professions.append(value)
        gates = []
        for field in _COMPACT_GATE_FIELDS:
            value = stage_source.get(field)
            if value not in (None, "", False, [], {}):
                gates.append(value)
        given_sections = stage_source.get("manual_sections")
        if isinstance(given_sections, dict):
            captions.extend(given_sections.get("prepare", ()) or ())
        return card_claims(
            {
                "manual_stage_id": card.get("manual_stage_id"),
                "a_preparer": authored_rows,
                "profession_gates": professions,
                "hard_runtime_gates": gates,
            },
            sections={"prepare": captions},
        )
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
    seen_gates: set[str] = set()
    for index, name in enumerate(_gate_labels(card.get("hard_runtime_gates", ()) or ())):
        identity = f"gate:{normalized_name(name)}"
        if identity in seen_gates or identity == "gate:":
            continue
        seen_gates.add(identity)
        claims.append(PreparationClaim(
            identity, None, name, "Prérequis", None, "reusable",
            "hard_runtime_gates", stage, f"gate:{index}",
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
    # The chapter's authored global inventory is anchored to one card for
    # compact storage, but it remains due until the entire chapter is complete.
    # Finishing that anchor card must not hide Blé / Goujon needed further on.
    rows = tuple(card_rows)
    incomplete_chapters = {
        str(card.get("manual_chapter_id") or "")
        for card, complete in rows if not complete
    }
    grouped: dict[tuple[str, str], list[PreparationClaim]] = {}
    for card, complete in rows:
        chapter = str(card.get("manual_chapter_id") or "")
        if complete and (not chapter or chapter not in incomplete_chapters):
            continue
        sections = sections_for_card(card) if callable(sections_for_card) else None
        for claim in card_claims(card, sections=sections):
            if complete and claim.source != "chapter_preparation":
                continue
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
