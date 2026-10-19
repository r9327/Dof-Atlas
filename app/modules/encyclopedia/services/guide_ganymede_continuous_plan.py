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


def project_ganymede_continuous_plan(
    guides_dir: Path,
    audited_needs: Mapping[str, object],
    atlas_guide_id: str,
    character_keys: Iterable[str],
    *,
    completed_source_steps: Mapping[str, Iterable[str]] | None = None,
    french_label_evidence: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Join all signed source steps and audited needs without losing empty stages.

    `completed_source_steps` is *manual*, scoped by stable character key to
    step IDs for this one guide. It cannot certify linked quests or items.
    Positions are observational hints only; Organizer needs an independently
    verified travel command and explicit live participants.
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

    labels = _localized_labels(french_label_evidence)
    stages = []
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
        for index, action in enumerate(candidates):
            if not isinstance(action, dict) or not isinstance(action.get("label"), str):
                raise ValueError("Malformed source action")
            row = audited_at_step.get(index)
            if row is not None:
                if row["source_label"] != action["label"]:
                    raise ValueError("Audited action no longer matches signed source")
                covered.add(row["proposal_id"])
                classification = row["classification"]
                label = row["display_label"]
                localized = row["localized_name_verified"]
                references = row["source_references"]
                optional = row["optional"]
            else:
                # Steps with no audited preparation still belong to the route.
                # Their action references are display-only, not canonical.
                reference = {
                    "object_ids": list(dict.fromkeys(
                        ([action["object_id"]] if type(action.get("object_id")) is int else [])
                        + (action.get("object_ids") or [])
                    )),
                    "quest_id": action.get("quest_id"),
                    "monster_id": action.get("monster_id"),
                    "dungeon_id": action.get("dungeon_id"),
                    "guide_id": action.get("guide_id"),
                }
                overlay = {
                    "source_guide_id": guide_id,
                    "stable_step_id": sid,
                    "source_action_index": index,
                    "source_references": reference,
                    "source_label": action["label"],
                }
                _apply_localized_label(overlay, labels)
                label = overlay["display_label"]
                localized = overlay["localized_name_verified"]
                references = reference
                optional = action.get("optional") is True
                classification = "source_action_reference"
            action_rows.append({
                "source_action_index": index,
                "kind": action.get("kind"),
                "source_label": action["label"],
                "display_label": label,
                "localized_name_verified": localized,
                "classification": classification,
                "source_references": references,
                "optional": optional,
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
        stages.append({
            "id": sid,
            "source_step_number": number,
            "source_page": step["source_page"],
            "title": step["title"],
            "source_coordinates_mentioned": positions,
            "verified_travel_plan": None,
            "action_rows": action_rows,
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
        "source_step_count": len(stages),
        "source_action_count": sum(len(step["action_rows"]) for step in stages),
        "audited_action_count": len(covered),
        "actual_step_id": actual,
        "manual_progress_only": True,
        "auto_completion_allowed": False,
        "ready_for_automatic_planning": False,
        "stages": stages,
    }


__all__ = ["project_ganymede_continuous_plan"]
