"""Non-destructive, per-character preparation preview for #229 source proposals.

Inventory is NEVER assumed. A known quantity is an explicitly provided
snapshot for one character/item, not a stock claim about anyone else.
Repeated actions stay distinct; no speculative purchase or route optimization.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_ACCEPTED = "REVIEW_ONLY_NOT_READY_FOR_OPTIMIZATION"
_ACTION_CLASSES = frozenset({"preparation_candidate", "acquire_on_route_candidate"})
_VALID_QUANTITY_SCOPES = frozenset({None, "per_character", "each_item", "per_item"})


def _quantity_for_item(row: Mapping[str, Any], item_count: int) -> int | None:
    info = row.get("source_details")
    if not isinstance(info, Mapping):
        raise ValueError("Missing audited proposal details")
    scope = info.get("quantity_scope_candidate")
    if scope not in _VALID_QUANTITY_SCOPES:
        return None
    value = info.get("quantity_per_character_candidate")
    if value is None:
        value = row.get("quantity_candidate")
    if type(value) is not int or value <= 0:
        return None
    if item_count > 1 and scope not in {"each_item", "per_item"}:
        return None
    return value


def stage_preparation_preview(
    plan_input: Mapping[str, Any],
    *,
    known_owned_items: Mapping[str, Mapping[int, int]] | None = None,
    completed_source_steps: Mapping[str, Mapping[str, set[str] | frozenset[str]]] | None = None,
) -> dict[str, Any]:
    """Project stage-scoped candidate needs for explicit selected participants.

    `known_owned_items`: absent character OR absent item => UNKNOWN, not zero.
    `completed_source_steps`: explicit stable step IDs, keyed by character then
    Atlas guide; never infer quest progress from manual marks. Completed steps
    are hidden from actionable previews, without changing stored source data.

    A quantity is an advisory **per occurrence**. Multiple prepare/check/drop
    actions may refer to the same items without implying repeated consumption.
    Thus never sum them or state any purchase as mandatory.
    """
    if (plan_input.get("status") != _ACCEPTED
            or plan_input.get("ready_for_automatic_planning") is not False
            or plan_input.get("inventory_assumed") is not False
            or plan_input.get("canonical_objectives_verified") != 0):
        raise ValueError("Only audited, non-playable source proposals are accepted")
    participants = plan_input.get("selected_character_keys")
    proposals = plan_input.get("source_action_proposals")
    if (not isinstance(participants, list) or
            any(not isinstance(key, str) or not key for key in participants) or
            len(participants) != len(set(participants)) or
            not isinstance(proposals, list)):
        raise ValueError("Invalid participant or source proposal contract")
    inventory = known_owned_items if known_owned_items is not None else {}
    marks = completed_source_steps if completed_source_steps is not None else {}
    if not isinstance(inventory, Mapping) or not isinstance(marks, Mapping):
        raise ValueError("Inventory and manual step marks must be maps")
    if any(k not in participants for k in (*inventory.keys(), *marks.keys())):
        raise ValueError("Unselected character must never affect plan")
    for character, items in inventory.items():
        if not isinstance(items, Mapping) or any(
            type(i) is not int or i <= 0 or type(q) is not int or q < 0
            for i, q in items.items()
        ):
            raise ValueError(f"Invalid explicit stock for {character}")
    for character, by_guide in marks.items():
        if not isinstance(by_guide, Mapping):
            raise ValueError("Invalid manual progress map")
        for guide, step_ids in by_guide.items():
            if not isinstance(guide, str) or not isinstance(step_ids, (set, frozenset)):
                raise ValueError("Invalid manual step ID collection")
            if any(not isinstance(s, str) for s in step_ids):
                raise ValueError("Invalid manual step ID")

    rows: list[dict[str, Any]] = []
    seen_proposals: set[str] = set()
    for source in proposals:
        if not isinstance(source, Mapping):
            raise ValueError("Invalid source action")
        proposal_id = source.get("proposal_id")
        if not isinstance(proposal_id, str) or proposal_id in seen_proposals:
            raise ValueError("Repeated or missing source action identifier")
        seen_proposals.add(proposal_id)
        if (source.get("route_planning_ready") is not False
                or source.get("auto_completion_allowed") is not False
                or source.get("canonical_objective_verified") is not False
                or source.get("selected_character_keys") != participants):
            raise ValueError("Source action cannot certify completion or new participants")
        if source.get("classification") not in _ACTION_CLASSES:
            continue
        details = source.get("source_details")
        refs = source.get("source_references")
        if not isinstance(details, Mapping) or not isinstance(refs, Mapping):
            raise ValueError("Source item references must be structured")
        item_ids = refs.get("object_ids")
        if not isinstance(item_ids, list) or any(
            type(i) is not int or i <= 0 for i in item_ids
        ) or len(set(item_ids)) != len(item_ids):
            raise ValueError("Unverified or duplicated source item IDs")
        step = source.get("source_step_number")
        due = details.get("needed_at_source_step")
        if due is None:
            due = step
        if (type(step) is not int or step < 1 or type(due) is not int
                or due < step):
            raise ValueError("Invalid source stage position or due date")
        window_end = details.get("collection_window_end_candidate")
        if window_end is not None and (type(window_end) is not int or window_end < step):
            raise ValueError("Invalid source collection window")
        quantity = _quantity_for_item(source, len(item_ids))
        optional = source.get("optional") is True
        on_route = (source["classification"] == "acquire_on_route_candidate"
                    or details.get("obtainable_on_route_candidate") is True)
        # A preparation mentioned at stage 2 but needed at stage 34 must
        # survive completion of stage 2. It is obsolete only when stage 34
        # itself has been completed for this particular character.
        prefix, _, suffix = source["stable_step_id"].rpartition("_")
        if not prefix or not suffix.isdigit() or int(suffix) != step:
            raise ValueError("Preparation has an invalid signed step identity")
        due_stage_id = f"{prefix}_{due:04d}"
        for item_id in item_ids:
            for character in participants:
                if due_stage_id in marks.get(character, {}).get(source["atlas_guide_id"], set()):
                    continue
                owned = inventory.get(character, {}).get(item_id)
                remaining = (max(0, quantity - owned)
                             if owned is not None and quantity is not None else None)
                rows.append({
                    "proposal_id": proposal_id,
                    "atlas_guide_id": source["atlas_guide_id"],
                    "source_step_id": source["stable_step_id"],
                    "source_step_number": step,
                    "needed_at_source_step": due,
                    "collection_window_end_candidate": window_end,
                    "character_key": character,
                    "item_id": item_id,
                    "source_label": source["source_label"],
                    "display_label": source.get("display_label", source["source_label"]),
                    "localized_name_verified": source.get("localized_name_verified", False),
                    "quantity_per_character_candidate": quantity,
                    "owned_quantity_explicit": owned,
                    "remaining_quantity_candidate": remaining,
                    "stock_known": owned is not None,
                    "optional_or_conditional": optional,
                    "obtainable_on_route_candidate": on_route,
                    "acquisition_guidance": (
                        "OPTIONAL_OR_CONDITIONAL" if optional
                        else "COLLECT_OR_DROP_ON_ROUTE" if on_route
                        else "REVIEW_PREPARATION"
                    ),
                    "must_purchase": False,
                    "canonical_requirement_verified": False,
                })
    rows.sort(key=lambda x: (
        x["atlas_guide_id"], x["needed_at_source_step"],
        x["source_step_number"], x["proposal_id"], x["item_id"], x["character_key"]
    ))
    return {
        "schema_version": 1,
        "status": "REVIEW_PREPARATION_BY_CHARACTER",
        "selected_character_keys": list(participants),
        "source_proposal_count": len(seen_proposals),
        "open_item_occurrences_per_character": len(rows),
        "unknown_stock_rows": sum(not r["stock_known"] for r in rows),
        "unknown_quantity_rows": sum(r["quantity_per_character_candidate"] is None for r in rows),
        "on_route_rows": sum(r["obtainable_on_route_candidate"] for r in rows),
        "manual_progress_only": True,
        "auto_completion_allowed": False,
        "mandatory_purchase_claimed": False,
        "aggregated_purchase_total": None,
        "note": "Quantités indicatives par occurrence; répétitions non sommées sans preuve de consommation.",
        "rows": rows,
    }


def summarize_stage_preparation(preview: Mapping[str, Any]) -> dict[str, Any]:
    """A compact, conservative item/character summary for Guide UI.

    Group repeated observations by *item ID*, without treating distinct source
    references as separate consumptions. A numeric need is informative only
    if its character has exactly one known, non-optional, non-route-acquirable
    occurrence. No item category, transferable stock, or shopping quantity is
    inferred from an action label.
    """
    if (preview.get("status") != "REVIEW_PREPARATION_BY_CHARACTER"
            or preview.get("manual_progress_only") is not True
            or preview.get("mandatory_purchase_claimed") is not False
            or preview.get("auto_completion_allowed") is not False):
        raise ValueError("Only non-automatic Ganymède preparation may be summarized")
    selected = preview.get("selected_character_keys")
    sources = preview.get("rows")
    if (not isinstance(selected, list) or not isinstance(sources, list)
            or any(not isinstance(key, str) or not key for key in selected)
            or len(set(selected)) != len(selected)):
        raise ValueError("Invalid preparation participants or rows")
    grouped: dict[tuple[str, int], dict[str, list[Mapping[str, Any]]]] = {}
    for row in sources:
        if not isinstance(row, Mapping):
            raise ValueError("Malformed item occurrence")
        guide_id, item_id, key = (
            row.get("atlas_guide_id"), row.get("item_id"), row.get("character_key")
        )
        if (not isinstance(guide_id, str) or not guide_id
                or type(item_id) is not int or item_id <= 0 or key not in selected
                or row.get("must_purchase") is not False
                or row.get("canonical_requirement_verified") is not False
                or not isinstance(row.get("proposal_id"), str)
                or not isinstance(row.get("source_step_id"), str)):
            raise ValueError("Untrusted item occurrence or character")
        grouped.setdefault((guide_id, item_id), {}).setdefault(key, []).append(row)
    result = []
    for (guide_id, item_id), by_person in sorted(grouped.items()):
        occurrences = sorted(
            {
                (row["source_step_id"], row["proposal_id"])
                for entries in by_person.values() for row in entries
            }
        )
        characters: dict[str, dict[str, Any]] = {}
        total_required = 0
        total_missing = 0
        totals_known = bool(by_person)
        for key in selected:
            entries = by_person.get(key, [])
            if not entries:
                continue
            owned = {row.get("owned_quantity_explicit") for row in entries}
            if len(owned) != 1:
                raise ValueError("Conflicting inventory for one item and character")
            owned_value = next(iter(owned))
            if owned_value is not None and (
                type(owned_value) is not int or owned_value < 0
            ):
                raise ValueError("Invalid stock quantity")
            optional = any(row.get("optional_or_conditional") is True for row in entries)
            on_route = any(row.get("obtainable_on_route_candidate") is True for row in entries)
            single = len(entries) == 1
            raw = entries[0].get("quantity_per_character_candidate") if single else None
            known_quantity = type(raw) is int and raw > 0
            candidate = raw if (
                single and known_quantity and not optional and not on_route
            ) else None
            missing = (
                max(0, candidate - owned_value)
                if candidate is not None and owned_value is not None else None
            )
            if candidate is None or missing is None:
                totals_known = False
            else:
                total_required += candidate
                total_missing += missing
            characters[key] = {
                "source_occurrence_count": len(entries),
                "required_candidate": candidate,
                "owned_quantity_explicit": owned_value,
                "remaining_quantity_candidate": missing,
                "optional_or_conditional": optional,
                "obtainable_on_route_candidate": on_route,
                "requires_quantity_review": candidate is None,
            }
        labels = sorted({
            row.get("display_label", row.get("source_label", ""))
            for entries in by_person.values() for row in entries
            if isinstance(row.get("display_label", row.get("source_label")), str)
        })
        result.append({
            "atlas_guide_id": guide_id,
            "item_id": item_id,
            "source_labels": labels,
            "source_occurrences": [
                {"source_step_id": step_id, "proposal_id": proposal_id}
                for step_id, proposal_id in occurrences
            ],
            "selected_character_keys": list(selected),
            "by_character": characters,
            "required_total_candidate": total_required if totals_known else None,
            "remaining_total_candidate": total_missing if totals_known else None,
            "quantity_review_required": not totals_known,
            "must_purchase": False,
            "canonical_requirement_verified": False,
        })
    return {
        "schema_version": 1,
        "status": "REVIEW_PREPARATION_COMPACT",
        "selected_character_keys": list(selected),
        "distinct_item_count": len(result),
        "automatic_completion_allowed": False,
        "mandatory_purchase_claimed": False,
        "items": result,
    }


__all__ = ["stage_preparation_preview", "summarize_stage_preparation"]