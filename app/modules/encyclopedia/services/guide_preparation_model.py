"""Conservative, pure-data preparation accounting for authored Atlas Guide cards.

No character selection, stock, progress or Ganymède action candidate is inferred
here. Qt controls may display these findings, but cannot turn an unknown amount
into a certified inventory claim.
"""
from __future__ import annotations

import hashlib
import re

from app.core.numbers import positive_int as _positive_int
from app.core.text import normalize_key, strip_accents
from dataclasses import dataclass
from typing import Any, Iterable

from app.core.json_store import decode_compact_json
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
    return decode_compact_json(payload, expected_type)


_EXPLICIT_QUANTITY = re.compile(
    r"\b(?:pr[ée]pare(?:r|z)?|apporte(?:r|z)?)\s+(\d+)\s*[×x]\s*(.+?)(?:[.;]|$)",
    re.IGNORECASE,
)


def normalized_name(text: str) -> str:
    # Preserve the Guide's Unicode-aware item names; only accent removal is
    # delegated to the same Qt-free helper as the rest of the application.
    decomposed = strip_accents(str(text or "").casefold())
    return " ".join("".join(ch if ch.isalnum() else " " for ch in decomposed).split())


def item_identity(item_id: int | None, name: str) -> str:
    return f"item:{item_id}" if item_id is not None else f"name:{normalized_name(name)}"




PREPARATION_CATEGORIES = (
    "Prérequis", "Métiers", "Potions", "Pierres d'âme", "Clefs", "Objets",
)


def category_for(name: str, kind: str = "") -> str:
    """One category source for authored data, summary, filter and Guide UI."""
    category = normalized_name(kind)
    label = normalized_name(name)
    if category in {"prerequis", "prerequisite", "gate", "condition"}:
        return "Prérequis"
    if category in {"metier", "metiers", "profession", "professions"}:
        return "Métiers"
    # The real item name wins over a generic "Objets" tag. An explicit
    # semantic category wins when the name is descriptive rather than literal.
    if "pierre d ame" in label or "soul stone" in label:
        return "Pierres d'âme"
    if category in {"pierre d ame", "pierres d ame", "soul stone", "soul stones"}:
        return "Pierres d'âme"
    if category in {"potion", "potions"} or "potion" in label:
        return "Potions"
    if category in {"clef", "clefs", "cle", "cles", "key", "keys"}:
        return "Clefs"
    if label.startswith(("clef ", "cle ", "clefs ", "cles ")):
        return "Clefs"
    return "Objets"


def matches_preparation_category(
    category: str, name: str, selected: str,
) -> bool:
    """The summary, read-only preview and live selector filter identically."""
    return selected == "Tout" or category_for(name, category) == selected


def preparation_stock_presentation(
    required: int,
    owned: int,
    *,
    ready: bool,
    confirmed: int = 0,
    participants: int = 1,
) -> tuple[str, str]:
    """One stock label and explanation for both Guide and Dev UI.

    Owned quantities are unsaved session drafts. Reaching the target never
    implies that the user confirmed the durable Prêt state.
    """
    remaining = max(0, int(required) - int(owned))
    if ready:
        label = "Prêt"
    elif remaining:
        label = f"Manque {remaining}"
    elif participants > 1 and confirmed:
        label = f"{confirmed}/{participants} prêts"
    else:
        label = "À valider"
    if ready:
        hint = "Prêt confirmé"
        if remaining:
            hint += f" · brouillon : {remaining} restant(s)"
    else:
        hint = (f"Encore {remaining} à obtenir" if remaining
                else "Quantité atteinte · coche Prêt pour confirmer")
    if participants > 1:
        hint += f" · {confirmed}/{participants} personnages prêts"
    return label, hint


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


@dataclass(frozen=True, slots=True)
class TeamPreparationNeed:
    """Combined authored need for the selected, explicitly identified team."""

    item_key: str
    item_id: int | None
    name: str
    category: str
    required_by_character: tuple[tuple[str, int | None], ...]
    confidence_by_character: tuple[tuple[str, str], ...] = ()
    sources: tuple[str, ...] = ()

    @property
    def required_total(self) -> int | None:
        quantities = [value for _character, value in self.required_by_character]
        return sum(quantities) if all(value is not None for value in quantities) else None


def preparation_progress_item_key(item_id: int | None, name: str) -> str:
    """Stable saved ready-key. Do not change this encoding or old ticks reset."""
    if item_id is not None:
        return f"item:{item_id}"
    digest = hashlib.sha256(normalize_key(name).encode("utf-8")).hexdigest()[:16]
    return f"name:{digest}"


def preparation_ready_key(guide_id: str, item_key: str) -> str:
    """Stable persisted Prêt marker shared by every Guide renderer."""
    return f"__ui:preparation_ready:{guide_id or 'guide_complet'}:{item_key}"


def aggregate_team_remaining(
    per_character: Iterable[tuple[str, Iterable[PreparationNeed]]],
) -> tuple[TeamPreparationNeed, ...]:
    """Combine per-character needs without mixing their progress or stock.

    Only already-verified participant keys are passed by the caller.
    Unknown required quantities stay unknown, even for one team member.
    """
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for character_key, needs in per_character:
        for need in needs:
            key = preparation_progress_item_key(need.item_id, need.name)
            item = grouped.setdefault(
                (key, need.category),
                {
                    "item_id": need.item_id,
                    "name": need.name,
                    "category": need.category,
                    "required": {},
                    "confidence": {},
                    "sources": set(),
                },
            )
            item["required"][character_key] = need.quantity
            item["confidence"][character_key] = need.confidence
            item["sources"].update(need.sources)
    return tuple(
        TeamPreparationNeed(
            item_key=key, item_id=row["item_id"],
            name=row["name"], category=row["category"],
            required_by_character=tuple(sorted(row["required"].items())),
            confidence_by_character=tuple(sorted(row["confidence"].items())),
            sources=tuple(sorted(row["sources"])),
        )
        for (key, _category), row in sorted(
            grouped.items(),
            key=lambda item: (
                item[1]["category"],
                normalize_key(item[1]["name"]),
            ),
        )
    )


def aggregate_route_team_remaining(
    cards, completion_by_character, *, sections_for_character_card=None,
) -> tuple[TeamPreparationNeed, ...]:
    """Share static authored preparation for identical remaining routes.

    Character-dependent sections must still be resolved separately. For compact
    and lazy authored cards, identical completion flags imply identical claims.
    Keep only one aggregated group's needs alive at a time.
    """
    cards = tuple(cards)
    static = not callable(sections_for_character_card) or all(
        "_manual_stage_payload" in card or card.get("_catalog_route_detail_lazy")
        for card in cards
    )
    def needs_for(key, flags):
        if len(flags) != len(cards):
            raise ValueError("completion flags must cover the entire route")
        return aggregate_remaining(
            ((card, bool(done)) for card, done in zip(cards, flags)),
            sections_for_card=lambda card: (
                None if "_manual_stage_payload" in card else
                card.get("manual_sections", {}) if card.get("_catalog_route_detail_lazy") else
                sections_for_character_card(key, card) if callable(sections_for_character_card) else
                card.get("manual_sections", {})
            ),
        )

    def per_character():
        if not static:
            for key, flags in completion_by_character:
                yield key, needs_for(key, flags)
            return
        groups = {}
        for key, flags in completion_by_character:
            groups.setdefault(bytes(flags), []).append(key)
        for flags, keys in groups.items():
            needs = needs_for(keys[0], flags)
            for key in keys:
                yield key, needs

    return aggregate_team_remaining(per_character())


__all__ = [
    "PreparationClaim", "PreparationNeed", "card_claims", "aggregate_remaining",
    "PREPARATION_CATEGORIES", "category_for", "matches_preparation_category",
    "preparation_stock_presentation", "item_identity", "normalized_name",
    "TeamPreparationNeed", "preparation_progress_item_key", "preparation_ready_key",
    "aggregate_team_remaining", "aggregate_route_team_remaining",
]
