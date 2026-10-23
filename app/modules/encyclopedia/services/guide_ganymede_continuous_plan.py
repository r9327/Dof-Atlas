"""Project the exact signed Ganymède cutover route into per-character stages.

The public Ganymède stage order is authoritative for manual step tracking.
Source action references and coordinates are *not* proof of quest completion,
possessed resources, eligible Zaaps, or executable travel. No auto-checks.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    certified_payload_sha256,
    select_verified_replacement_path,
)
from app.modules.encyclopedia.services.guide_ganymede_plan_input import (
    _apply_localized_label,
    _localized_labels,
    prepare_ganymede_plan_input,
)
from app.modules.encyclopedia.services.guide_ganymede_preparation import (
    stage_preparation_preview,
    summarize_stage_preparation,
)
from app.modules.encyclopedia.services.guide_route_naming import (
    title_for_ganymede_step,
)
from app.modules.encyclopedia.services.adventure_route_engine import RouteAction
from app.modules.encyclopedia.services.guide_route_planner import GuideTravelPlan, TravelMode


def _quest_link_by_id(
    quest_id: int | None,
    provider: object | None,
    names: dict[int, str | None],
) -> dict[str, object] | None:
    """Match a source quest ID to the existing Atlas QuestProvider by ID only."""
    if quest_id is None:
        return None
    if type(quest_id) is not int or quest_id <= 0:
        raise ValueError("Invalid source quest ID")
    if quest_id not in names:
        resolved = None
        if provider is not None:
            getter = getattr(provider, "get_quest", None)
            if not callable(getter):
                raise ValueError("Expected the existing get_quest(id) provider contract")
            record = getter(quest_id)
            if record is not None:
                if type(getattr(record, "id", None)) is not int or record.id != quest_id:
                    raise ValueError("Source quest and Atlas catalogue IDs do not match")
                name = getattr(record, "name", None)
                if isinstance(name, str) and name.strip():
                    resolved = name.strip()
        names[quest_id] = resolved
    name = names[quest_id]
    return {
        "quest_id": quest_id,
        "quest_name": name,
        "catalog_id_verified": name is not None,
        "navigation_allowed": name is not None,
        "quest_completion_verified": False,
    }


def canonical_map_positions_from_doduda(
    raw_maps: Mapping[int, Mapping[str, object]],
    map_ids: Iterable[int],
) -> dict[int, tuple[int, int]]:
    """Resolve only requested map IDs from the already-loaded Atlas snapshot.

    AdventureRouteAdapter.raw_maps comes from Doduda maps_information.json.
    Unavailable, malformed or sentinel map positions are deliberately omitted;
    they can never become travel proof through this helper.
    """
    if not isinstance(raw_maps, Mapping):
        raise ValueError("Canonical game map records must be a mapping")
    result: dict[int, tuple[int, int]] = {}
    for map_id in dict.fromkeys(map_ids):
        if type(map_id) is not int or map_id <= 0:
            raise ValueError("Canonical map IDs must be positive integers")
        record = raw_maps.get(map_id)
        if not isinstance(record, Mapping):
            continue
        if ("id" in record
                and (type(record["id"]) is not int or record["id"] != map_id)):
            continue
        x, y = record.get("posX"), record.get("posY")
        if (type(x) is int and type(y) is int
                and -(2**31) not in (x, y)
                and abs(x) <= 10000 and abs(y) <= 10000):
            result[map_id] = (x, y)
    return result


def _reviewed_start_travel(
    step: Mapping[str, object],
    action: RouteAction,
    participant_keys: list[str],
    canonical_map_positions: Mapping[int, tuple[int, int]],
) -> GuideTravelPlan:
    """Check an explicitly reviewed source-to-canonical binding before travel.

    This only verifies a direct location, not the quest completion or Zaap
    eligibility. A Ganymède quest ID or observed coordinate alone cannot
    produce a command: the caller must supply the independently mapped Atlas
    start action, and both sources must agree without ambiguity. The map ID
    must also exist in an independent Atlas map-information snapshot.
    """
    if not isinstance(action, RouteAction):
        raise ValueError("Reviewed binding must provide a canonical RouteAction")
    candidates = step.get("source_action_candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Reviewed source step has no structured actions")
    starts = [
        row for row in candidates
        if isinstance(row, Mapping) and row.get("kind") == "quest_start"
    ]
    passive = {"prepare_object", "optional_preparation", "optional_drop"}
    if (len(starts) != 1
            or any(not isinstance(row, Mapping)
                   or row.get("kind") not in passive | {"quest_start"}
                   for row in candidates)):
        raise ValueError("Source step has ambiguous destinations or actions")
    quest_id = starts[0].get("quest_id")
    if (type(quest_id) is not int or quest_id <= 0
            or action.quest_id != quest_id
            or action.action_id != f"quest:{quest_id}:start"
            or action.kind != "start"
            or action.activates_quest is not True
            or action.requires_active_quest is not False):
        raise ValueError("Canonical quest start does not match source action")
    observed = step.get("source_coordinates_mentioned")
    location = action.location
    if (not isinstance(observed, list) or len(observed) != 1
            or not isinstance(observed[0], list) or len(observed[0]) != 2
            or any(type(v) is not int for v in observed[0])
            or type(location.map_id) is not int or location.map_id <= 0
            or type(location.x) is not int or type(location.y) is not int
            or -(2**31) in (location.x, location.y)
            or abs(location.x) > 10000 or abs(location.y) > 10000
            or observed[0] != [location.x, location.y]):
        raise ValueError("Canonical map coordinates do not corroborate source")
    # The route adapter may supply an action with a map ID but without a
    # resolved maps_information record. A positive map ID alone is not proof.
    if not isinstance(canonical_map_positions, Mapping):
        raise ValueError("Atlas map registry must be explicitly supplied")
    atlas_position = canonical_map_positions.get(location.map_id)
    if (not isinstance(atlas_position, tuple) or len(atlas_position) != 2
            or any(type(coord) is not int for coord in atlas_position)
            or -(2**31) in atlas_position
            or atlas_position != (location.x, location.y)):
        raise ValueError("Atlas map record does not corroborate quest start")
    return GuideTravelPlan(
        TravelMode.DIRECT, location, tuple(participant_keys),
        evidence=f"atlas:reviewed-quest-start:{quest_id}:map:{location.map_id}",
    )


def project_ganymede_continuous_plan(
    guides_dir: Path,
    audited_needs: Mapping[str, object],
    atlas_guide_id: str,
    character_keys: Iterable[str],
    *,
    completed_source_steps: Mapping[str, Iterable[str]] | None = None,
    known_owned_items: Mapping[str, Mapping[int, int]] | None = None,
    french_label_evidence: Mapping[str, object] | None = None,
    quest_provider: object | None = None,
    verified_stage_travel: Mapping[str, GuideTravelPlan] | None = None,
    reviewed_start_action_bindings: Mapping[str, RouteAction] | None = None,
    canonical_map_positions: Mapping[int, tuple[int, int]] | None = None,
) -> dict[str, object]:
    """Join all signed source steps and audited needs without losing empty stages.

    `completed_source_steps` is *manual*, scoped by stable character key to
    step IDs for this one guide. It cannot certify linked quests or items.
    Positions are observational hints only. An optional, independent Atlas
    planner overlay may carry typed travel commands; source JSON cannot enable
    game input and no coordinates or eligibility are inferred here.
    """
    source = prepare_ganymede_plan_input(
        audited_needs, character_keys,
        atlas_guide_ids=[atlas_guide_id],
        french_label_evidence=french_label_evidence,
    )
    selected = source["selected_character_keys"]
    path = select_verified_replacement_path(
        Path(guides_dir), {"id": atlas_guide_id, "category": "dofus"},
        allow_source_manual=True,
    )
    if path is None:
        raise ValueError("No signed, manually trackable Ganymède replacement")
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest = json.loads((path.parent / "cutover_manifest.json").read_text(encoding="utf-8"))
    record = manifest.get("guides", {}).get(atlas_guide_id, {})
    if (not isinstance(record, dict)
            or record.get("status") != "TRUSTED_SOURCE_STEPS"
            or certified_payload_sha256(payload) != record.get("payload_sha256")):
        raise ValueError("Signed Ganymède route changed while loading")
    steps = payload["sections"][0]["steps"]
    guide_id = payload["source_guide_id"]
    if (audited_needs["guides"][atlas_guide_id]["source_guide_id"] != guide_id
            or len(steps) != record["source_step_count"]):
        raise ValueError("Audited needs and signed Ganymède route disagree")

    by_step: dict[str, dict[int, dict]] = {}
    for proposal in source["source_action_proposals"]:
        sid, action_index = proposal["stable_step_id"], proposal["source_action_index"]
        if action_index in by_step.setdefault(sid, {}):
            raise ValueError("Duplicate audited action at source position")
        by_step[sid][action_index] = proposal

    manual_marks = completed_source_steps or {}
    if not isinstance(manual_marks, Mapping) or any(
        key not in selected for key in manual_marks
    ):
        raise ValueError("Manual progress must belong to a selected character")
    valid_ids = {step["id"] for step in steps}
    start_bindings = (reviewed_start_action_bindings
                      if reviewed_start_action_bindings is not None else {})
    if (not isinstance(start_bindings, Mapping)
            or any(step_id not in valid_ids for step_id in start_bindings)):
        raise ValueError("Reviewed start binding refers to an unknown signed step")
    if start_bindings and not selected:
        raise ValueError("Reviewed start bindings need explicit participants")
    if any(not isinstance(action, RouteAction) for action in start_bindings.values()):
        raise ValueError("Reviewed binding must be a canonical RouteAction")
    action_ids = [action.action_id for action in start_bindings.values()]
    if len(action_ids) != len(set(action_ids)):
        raise ValueError("One canonical start action cannot bind multiple source steps")
    if start_bindings and not isinstance(canonical_map_positions, Mapping):
        raise ValueError("Reviewed start bindings need Atlas map records")
    travel_by_step = verified_stage_travel if verified_stage_travel is not None else {}
    if (not isinstance(travel_by_step, Mapping)
            or any(step_id not in valid_ids for step_id in travel_by_step)):
        raise ValueError("Verified travel must reference a signed source step")
    if set(travel_by_step) & set(start_bindings):
        raise ValueError("Ambiguous direct travel and reviewed start binding")
    # Do not turn an unbound or stale planner export into a source route command.
    for step_id, travel in travel_by_step.items():
        if (not isinstance(travel, GuideTravelPlan)
                or tuple(travel.participant_keys) != tuple(selected)
                or not isinstance(travel.evidence, str)
                or not travel.evidence.strip()
                or travel.evidence == "exact_destination_coordinates"):
            raise ValueError("Verified travel needs an explicit scoped Atlas plan")
    marks: dict[str, frozenset[str]] = {}
    for key in selected:
        values = manual_marks.get(key, ())
        if isinstance(values, (str, bytes)) or not isinstance(
            values, (set, frozenset, list, tuple)
        ):
            raise ValueError("Manual progress needs explicit stable step IDs")
        items = tuple(values)
        if (any(not isinstance(item, str) or item not in valid_ids for item in items)
                or len(items) != len(set(items))):
            raise ValueError("Foreign, duplicated or invalid Ganymède progress ID")
        marks[key] = frozenset(items)

    preparation = stage_preparation_preview(
        source,
        known_owned_items=known_owned_items,
        completed_source_steps={
            key: {atlas_guide_id: marks[key]} for key in selected
        },
    )
    preparation_by_step: dict[str, list[dict]] = {}
    preparation_due_step: dict[int, list[dict]] = {}
    for row in preparation["rows"]:
        preparation_by_step.setdefault(row["source_step_id"], []).append(row)
        due = row["needed_at_source_step"]
        if type(due) is not int or not 1 <= due <= len(steps):
            raise ValueError("Preparation need points outside signed Ganymède steps")
        preparation_due_step.setdefault(due, []).append(row)
    compact = summarize_stage_preparation(preparation)
    labels = _localized_labels(french_label_evidence)
    quest_names: dict[int, str | None] = {}
    stages = []
    runtime_travel_plans: dict[str, dict[str, object]] = {}
    covered = set()
    for number, step in enumerate(steps, 1):
        sid = f"ganymede_{guide_id}_step_{number:04d}"
        if (step["id"] != sid
                or step["source_step_number"] != number
                or step["source_guide_id"] != guide_id
                or step["auto_completion_allowed"] is not False
                or step["manual_completion_allowed"] is not True):
            raise ValueError("Invalid signed step identity or completion contract")
        pending = [key for key in selected if sid not in marks[key]]
        completed = [key for key in selected if sid in marks[key]]
        candidates = step["source_action_candidates"]
        if not isinstance(candidates, list):
            raise ValueError("Missing source actions")
        audited_at_step = by_step.get(sid, {})
        action_rows = []
        linked_quests = []
        seen_quest_ids: set[int] = set()
        for index, action in enumerate(candidates):
            if not isinstance(action, dict) or not isinstance(action.get("label"), str):
                raise ValueError("Malformed source action")
            signed_references = {
                "object_ids": list(dict.fromkeys(
                    ([action["object_id"]] if type(action.get("object_id")) is int else [])
                    + (action.get("object_ids") or [])
                )),
                "quest_id": action.get("quest_id"),
                "monster_id": action.get("monster_id"),
                "dungeon_id": action.get("dungeon_id"),
                "guide_id": action.get("guide_id"),
            }
            row = audited_at_step.get(index)
            if row is not None:
                if row["source_label"] != action["label"]:
                    raise ValueError("Audited action no longer matches signed source")
                covered.add(row["proposal_id"])
                classification = row["classification"]
                label = row["display_label"]
                localized = row["localized_name_verified"]
                audited_references = row["source_references"]
                for namespace, observed in audited_references.items():
                    signed = signed_references[namespace]
                    # A preparation audit can omit the associated quest ID,
                    # but must never contradict an ID actually reported.
                    if namespace == "object_ids":
                        if observed and set(observed) != set(signed):
                            raise ValueError("Conflicting source object IDs")
                    elif observed is not None and observed != signed:
                        raise ValueError(f"Conflicting source {namespace} ID")
                references = signed_references
                optional = row["optional"]
                details = row["source_details"]
                tree_predecessor = (
                    details.get("public_tree_predecessor_verified") is True
                    if row["kind"] == "guide_dependency" else False
                )
                if (classification == "related_guide_reference"
                        and details.get("public_tree_predecessor_verified") is not False):
                    raise ValueError("Navigation link cannot block the route")
                if (row["kind"] == "guide_dependency"
                        and classification == "prerequisite_candidate"
                        and details.get("public_tree_predecessor_verified") is not True):
                    raise ValueError("Only proven Ganymède tree ancestors are predecessors")
                quantity = row["quantity_candidate"]
                on_route = classification == "acquire_on_route_candidate"
            else:
                # Steps with no audited preparation still belong to the route.
                # Their action references are display-only, not canonical.
                overlay = {
                    "source_guide_id": guide_id,
                    "stable_step_id": sid,
                    "source_action_index": index,
                    "source_references": signed_references,
                    "source_label": action["label"],
                }
                _apply_localized_label(overlay, labels)
                label = overlay["display_label"]
                localized = overlay["localized_name_verified"]
                references = signed_references
                optional = action.get("optional") is True
                classification = "source_action_reference"
                tree_predecessor = False
                quantity = None
                on_route = False
            quest_link = _quest_link_by_id(
                references["quest_id"], quest_provider, quest_names,
            )
            show_quest_button = False
            if quest_link is not None:
                qid = quest_link["quest_id"]
                if qid not in seen_quest_ids:
                    seen_quest_ids.add(qid)
                    linked_quests.append(quest_link)
                    show_quest_button = quest_link["navigation_allowed"]
            action_rows.append({
                "source_action_index": index,
                "quest_reference": quest_link,
                "quest_hover_name": (
                    quest_link["quest_name"] if quest_link else None
                ),
                "show_quest_button": show_quest_button,
                "kind": action.get("kind"),
                "source_label": action["label"],
                "display_label": label,
                "localized_name_verified": localized,
                "classification": classification,
                "source_references": references,
                "optional": optional,
                "quantity_candidate": quantity,
                "obtainable_on_route_candidate": on_route,
                "public_tree_predecessor_verified": tree_predecessor,
                "navigation_only": classification == "related_guide_reference",
                "must_purchase": False,
                "canonical_objective_verified": False,
                "auto_completion_allowed": False,
            })

        positions = step.get("source_coordinates_mentioned", [])
        if not isinstance(positions, list):
            raise ValueError("Malformed observed coordinates")
        if any(not isinstance(p, list) or len(p) != 2 or any(
            type(v) is not int for v in p
        ) for p in positions):
            raise ValueError("Invalid observed Ganymède coordinates")
        title = title_for_ganymede_step(step["title"], number)
        travel = travel_by_step.get(sid)
        if travel is not None and tuple(pending) != tuple(selected):
            # A plan prepared for the entire original team is no longer valid
            # after one participant completes this step. Never move someone
            # who has already checked this source stage.
            travel = None
        if sid in start_bindings and pending:
            if len(pending) != len(selected):
                # Completed characters must not be dragged back to a stage
                # needed by only a subset of the selected team.
                travel = None
            else:
                travel = _reviewed_start_travel(
                    step, start_bindings[sid], pending, canonical_map_positions,
                )
        if travel is not None:
            # This is a transient result from the canonical planner, not a
            # property read from (or written back into) the source JSON.
            runtime_travel_plans[sid] = {
                "atlas_guide_id": atlas_guide_id,
                "source_step_id": sid,
                "source_payload_sha256": record["payload_sha256"],
                **travel.to_payload(),
            }
        stages.append({
            "id": sid,
            "source_step_number": number,
            "source_page": step["source_page"],
            "title": step["title"],
            "short_title": title.text,
            "title_review_required": title.review_required,
            "source_coordinates_mentioned": positions,
            "verified_travel_plan": runtime_travel_plans.get(sid),
            "action_rows": action_rows,
            "linked_quests": linked_quests,
            "preparation_rows": preparation_by_step.get(sid, []),
            # Source occurrence and due time are different: a need mentioned
            # early can matter just before a much later dungeon/action.
            "preparation_due_rows": preparation_due_step.get(number, []),
            "pending_character_keys": pending,
            "manually_completed_character_keys": completed,
            "all_selected_participants_completed": bool(selected) and not pending,
            "automatic_completion_allowed": False,
        })
    missing = {
        row["proposal_id"] for row in source["source_action_proposals"]
    } - covered
    if missing:
        raise ValueError("Audited source actions are absent from signed route")
    actual = next(
        (step["id"] for step in stages if step["pending_character_keys"]), None
    )
    return {
        "schema_version": 1,
        "status": "TRUSTED_SOURCE_STEPS_MANUAL_ONLY",
        "atlas_guide_id": atlas_guide_id,
        "source_guide_id": guide_id,
        "source_payload_sha256": record["payload_sha256"],
        "selected_character_keys": selected,
        "runtime_verified_travel_plans": runtime_travel_plans,
        "source_step_count": len(stages),
        "source_action_count": sum(len(step["action_rows"]) for step in stages),
        "audited_action_count": len(covered),
        "catalog_quest_ids_resolved": sum(name is not None for name in quest_names.values()),
        "catalog_quest_ids_unresolved": sum(name is None for name in quest_names.values()),
        "preparation_item_occurrences": preparation["open_item_occurrences_per_character"],
        "preparation_summary": compact,
        "unknown_stock_rows": preparation["unknown_stock_rows"],
        "must_purchase": False,
        "actual_step_id": actual,
        "manual_progress_only": True,
        "auto_completion_allowed": False,
        "ready_for_automatic_planning": False,
        "stages": stages,
    }


__all__ = [
    "canonical_map_positions_from_doduda", "project_ganymede_continuous_plan",
]
