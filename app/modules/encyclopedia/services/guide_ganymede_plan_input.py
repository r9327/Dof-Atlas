"""Source-scoped Ganymède suggestions for the Atlas multi-character planner.

This accepts the audited #229 stage-needs report, never raw scraped links.
Proposals are NOT canonical AdventureRouteEngine actions: the planner needs
verified quest objectives and participant state before automatic scheduling.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from app.core.character_identity import require_character_key


_ALLOWED = {
    "needs": "preparation_candidate",
    "prerequisites": "prerequisite_candidate",
    "related_guide_links": "related_guide_reference",
    "encounters": "encounter_candidate",
    "goal_rewards": "reward_goal",
}
_ON_ROUTE_KINDS = {"drop_object", "optional_drop", "collect_object"}



def _localized_labels(evidence: Mapping[str, object] | None) -> dict[tuple[int, str, int], dict]:
    """Index only pinned #229 French-name evidence, keyed by the original action."""
    if evidence is None:
        return {}
    if (evidence.get("schema_version") != 1
            or evidence.get("status") != "REVIEW_NAMES_RESOLVED"
            or evidence.get("source") != "doduda_pinned_french_names_and_ganymede_public_index"
            or not isinstance(evidence.get("pinned_release"), str)
            or not evidence["pinned_release"]
            or evidence.get("canonical_objectives_verified") != 0
            or evidence.get("ready_to_replace") is not False
            or evidence.get("unresolved_reference_count") != 0
            or evidence.get("resolved_action_labels") != evidence.get("generic_label_actions")):
        raise ValueError("Ganymède French names lack pinned, complete source evidence")
    guides = evidence.get("guides")
    if not isinstance(guides, list):
        raise ValueError("Missing localized guides")
    result: dict[tuple[int, str, int], dict] = {}
    for guide in guides:
        if not isinstance(guide, Mapping):
            raise ValueError("Malformed localized guide")
        gid = guide.get("source_guide_id")
        rows = guide.get("label_overrides")
        if type(gid) is not int or gid < 1 or not isinstance(rows, list):
            raise ValueError("Invalid localized guide identity")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Invalid localized action")
            step, index = row.get("stable_step_id"), row.get("action_index")
            if (not isinstance(step, str)
                    or not step.startswith(f"ganymede_{gid}_step_")
                    or type(index) is not int or index < 0
                    or not isinstance(row.get("source_label"), str)
                    or not isinstance(row.get("display_label"), str)
                    or not row["display_label"].strip()
                    or not isinstance(row.get("resolved_entities"), list)
                    or row.get("canonical_objective_verified") is not False):
                raise ValueError("Untrusted localized label identity")
            key = (gid, step, index)
            if key in result:
                raise ValueError("Duplicate localized action")
            result[key] = row
    if len(result) != evidence["resolved_action_labels"]:
        raise ValueError("Localized evidence is incomplete")
    return result


def _apply_localized_label(proposal: dict, labels: Mapping[tuple[int, str, int], dict]) -> None:
    """A display name can replace a number, never prove quest completion."""
    proposal["display_label"] = proposal["source_label"]
    proposal["localized_name_verified"] = False
    key = (proposal["source_guide_id"], proposal["stable_step_id"],
           proposal["source_action_index"])
    override = labels.get(key)
    if override is None:
        return
    if override["source_label"] != proposal["source_label"]:
        raise ValueError("Localized name belongs to a different source action")
    fields = {
        "object": "object_ids", "quest": "quest_id", "monster": "monster_id",
        "dungeon": "dungeon_id", "guide": "guide_id",
    }
    refs = proposal["source_references"]
    if not override["resolved_entities"]:
        raise ValueError("Localized name has no entity proof")
    for entity in override["resolved_entities"]:
        if not isinstance(entity, Mapping):
            raise ValueError("Malformed localized entity")
        kind, identifier = entity.get("namespace"), entity.get("source_entity_id")
        if kind not in fields or type(identifier) is not int or identifier <= 0:
            raise ValueError("Localized entity must have a typed source ID")
        reference = refs[fields[kind]]
        if not (identifier in reference if kind == "object" and isinstance(reference, list)
                else identifier == reference):
            raise ValueError("Localized name is not attached to its source action ID")
        if (not isinstance(entity.get("source_name"), str)
                or f"«{entity['source_name']}»" not in override["display_label"]
                or entity.get("name_locale") != (
                    "source_title_original" if kind == "guide" else "fr"
                )):
            raise ValueError("Unverified localized source name or locale")
    proposal["display_label"] = override["display_label"]
    proposal["localized_name_verified"] = True



def prepare_ganymede_plan_input(
    audited: Mapping[str, object],
    character_keys: Iterable[str],
    *,
    atlas_guide_ids: Iterable[str] | None = None,
    french_label_evidence: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Preserve every source action occurrence without fabricating facts.

    Participants are explicitly selected (including zero); inventory remains
    unknown. Do not turn public references into mandatory quests/purchases.
    """
    if (audited.get("status") != "REVIEW_ONLY_NOT_READY_FOR_OPTIMIZATION"
            or audited.get("issues") != []
            or audited.get("source_candidate_guides") != 20
            or audited.get("source_stages") != 1694
            or audited.get("canonical_requirements_certified") != 0
            or audited.get("stock_assumed") is not False
            or audited.get("participants_assumed") is not False):
        raise ValueError("Ganymède preparation report not validated")
    guides = audited.get("guides")
    if not isinstance(guides, Mapping) or len(guides) != 20:
        raise ValueError("Missing 20 Ganymède guide plans")
    if sum(guide.get("source_step_count", 0) for guide in guides.values()) != 1694:
        raise ValueError("Source step count inconsistent with audited corpus")

    keys = tuple(require_character_key(v) for v in character_keys)
    if len(set(keys)) != len(keys):
        raise ValueError("Duplicate selected character")
    requested = list(atlas_guide_ids) if atlas_guide_ids is not None else list(guides)
    if len(set(requested)) != len(requested) or any(
        not isinstance(gid, str) or gid not in guides for gid in requested
    ):
        raise ValueError("Unknown or duplicate Atlas guide selected")

    labels = _localized_labels(french_label_evidence)
    proposals = []
    counts = {kind: 0 for kind in _ALLOWED}
    for guide_id in requested:
        guide = guides[guide_id]
        source_id = guide.get("source_guide_id")
        steps = guide.get("stages_with_requirements")
        if (guide.get("atlas_guide_id") != guide_id
                or type(source_id) is not int or source_id < 1
                or guide.get("canonical_requirements_certified") != 0
                or guide.get("source_status") != "REVIEW_ONLY_NOT_READY_FOR_OPTIMIZATION"
                or not isinstance(steps, list)):
            raise ValueError(f"Invalid source guide {guide_id}")
        seen = set()
        for stage in steps:
            number = stage.get("source_step_number")
            stable = stage.get("stable_step_id")
            if (type(number) is not int or number < 1
                    or number > guide["source_step_count"]
                    or stable != f"ganymede_{source_id}_step_{number:04d}"
                    or number in seen):
                raise ValueError(f"Invalid source stage for {guide_id}")
            seen.add(number)
            action_indices = set()
            for bucket, classification in _ALLOWED.items():
                rows = stage.get(bucket)
                if not isinstance(rows, list):
                    raise ValueError(f"Missing source classification {bucket}")
                for action in rows:
                    index = action.get("source_action_index")
                    if type(index) is not int or index < 0 or index in action_indices:
                        raise ValueError("Missing or duplicated source action identity")
                    action_indices.add(index)
                    if (action.get("canonical_requirement_verified") is True
                            or action.get("canonical_objective_verified") is True
                            or action.get("character_completion_known") is True
                            or action.get("owned_or_prepared_by_any_character") is True
                            or action.get("owned_or_obtained_by_character") is True):
                        raise ValueError("Unverified source action claims certified facts")
                    optional = action.get("optional") is True
                    route_pickup = (bucket == "needs"
                                    and action.get("kind") in _ON_ROUTE_KINDS)
                    if bucket == "related_guide_links":
                        if action.get("public_tree_predecessor_verified") is not False:
                            raise ValueError("Related guide cannot be a prerequisite")
                    proposal = {
                        "atlas_guide_id": guide_id,
                        "source_guide_id": source_id,
                        "stable_step_id": stable,
                        "source_step_number": number,
                        "source_action_index": index,
                        "proposal_id": f"{stable}:action:{index:03d}",
                        "classification": (
                            "acquire_on_route_candidate" if route_pickup
                            else classification
                        ),
                        "kind": action.get("kind"),
                        "source_label": action.get("source_action_label"),
                        "optional": optional,
                        "quantity_candidate": action.get("quantity_candidate"),
                        "source_references": {
                            "object_ids": action.get("external_dofusdb_object_ids") or (
                                [action["external_dofusdb_object_id"]]
                                if type(action.get("external_dofusdb_object_id")) is int else []
                            ),
                            "monster_id": action.get("external_dofusdb_monster_id"),
                            "dungeon_id": action.get("external_dofusdb_dungeon_id"),
                            "quest_id": action.get("external_dofusdb_quest_id"),
                            "guide_id": action.get("ganymede_prerequisite_guide_id"),
                        },
                        "source_review_status": action.get("source_review_status"),
                        "source_details": dict(action),
                        "selected_character_keys": list(keys),
                        "inventory_status": "UNKNOWN",
                        "remaining_quantity": None,
                        "auto_completion_allowed": False,
                        "canonical_objective_verified": False,
                        "route_planning_ready": False,
                    }
                    _apply_localized_label(proposal, labels)
                    proposals.append(proposal)
                    counts[bucket] += 1
    return {
        "schema_version": 1,
        "status": "REVIEW_ONLY_NOT_READY_FOR_OPTIMIZATION",
        "atlas_guide_ids": requested,
        "selected_character_keys": list(keys),
        "source_candidate_guides": 20,
        "source_stages": 1694,
        "counts_by_source_bucket": counts,
        "source_action_proposals": proposals,
        "inventory_assumed": False,
        "canonical_objectives_verified": 0,
        "ready_for_automatic_planning": False,
    }


def preview_ganymede_preparation(
    audited: Mapping[str, object],
    character_keys: Iterable[str],
    *,
    atlas_guide_ids: Iterable[str] | None = None,
    known_owned_items: Mapping[str, Mapping[int, int]] | None = None,
    completed_source_steps: Mapping[str, Mapping[str, set[str] | frozenset[str]]] | None = None,
    french_label_evidence: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Hand verified source *proposals* to the JIT, per-character preview.

    This explicitly does not construct canonical RouteAction instances or
    claim game completion, and never assumes that missing inventory is zero.
    """
    from app.modules.encyclopedia.services.guide_ganymede_preparation import (
        stage_preparation_preview,
    )

    plan = prepare_ganymede_plan_input(
        audited, character_keys, atlas_guide_ids=atlas_guide_ids,
        french_label_evidence=french_label_evidence,
    )
    return stage_preparation_preview(
        plan, known_owned_items=known_owned_items,
        completed_source_steps=completed_source_steps,
    )


__all__ = ["prepare_ganymede_plan_input", "preview_ganymede_preparation"]
