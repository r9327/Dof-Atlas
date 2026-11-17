"""Existing Cawotte candidate steps as read-only Guide sheets, never as an authorized route.

Only local factual candidate labels/coordinates are displayed; source rights,
quest objectives, actions, runtime travel and progress remain unverified.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.constants import DATA_DIR

CAWOTTE_CANDIDATES = DATA_DIR / "encyclopedia" / "guides" / "ganymede_2205_action_candidates.json"
_MAX_BYTES = 512 * 1024


class CawottePilotDataError(ValueError):
    """The local candidate file is not the exact 64-step draft."""


def cawotte_review_cards(path: Path = CAWOTTE_CANDIDATES) -> tuple[dict[str, Any], ...]:
    if path.stat().st_size > _MAX_BYTES:
        raise CawottePilotDataError("Candidate file exceeds review size limit")
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or any((
        doc.get("schema_version") != 1,
        doc.get("atlas_guide_id") != "dofus_cawotte",
        type(doc.get("source_guide_id")) is not int or doc["source_guide_id"] != 2205,
        doc.get("source_url") != "https://ganymede-app.com/guides/2205",
        doc.get("source_step_count") != 64,
        doc.get("evidence_level") != "FACTUAL_ACTION_CANDIDATES_NEED_CANONICAL_OBJECTIVE_VERIFICATION",
        doc.get("editorial_text_copied") is not False,
        type(doc.get("certified_actions")) is not int or doc["certified_actions"] != 0,
        doc.get("ready_to_replace") is not False,
    )):
        raise CawottePilotDataError("Source is not the fixed unverified Cawotte candidate")
    steps = doc.get("steps")
    if not isinstance(steps, list) or len(steps) != 64:
        raise CawottePilotDataError("Cawotte candidate step count mismatch")
    cards: list[dict[str, Any]] = []
    for number, step in enumerate(steps, 1):
        step_id = f"ganymede_2205_step_{number:04d}"
        if (not isinstance(step, dict)
                or type(step.get("source_step_number")) is not int
                or step["source_step_number"] != number
                or step.get("stable_step_id") != step_id
                or step.get("review_status") != "REVIEW_SOURCE_ACTION"
                or step.get("quest_objectives_verified") is not False):
            raise CawottePilotDataError(f"Invalid draft step {number}")
        coords, actions = step.get("at"), step.get("actions")
        if (not isinstance(coords, list) or len(coords) != 2
                or any(type(value) is not int or abs(value) > 2**16 for value in coords)
                or not isinstance(actions, list) or not actions):
            raise CawottePilotDataError(f"Incomplete step {number}")
        rows: list[dict[str, Any]] = []
        prerequisites: list[dict[str, Any]] = []
        preparations: list[dict[str, Any]] = []
        for action_index, action in enumerate(actions):
            if not isinstance(action, dict):
                raise CawottePilotDataError(f"Invalid action at step {number}")
            kind, label = action.get("kind"), action.get("label")
            if (not isinstance(kind, str) or not kind.strip()
                    or not isinstance(label, str) or not label.strip() or len(label) > 512):
                raise CawottePilotDataError(f"Missing candidate action at step {number}")
            # Use explicit candidate types, never heuristics on guide prose.
            # This is a non-playable review, not Ganymede source evidence.
            if kind in {"guide_dependency", "quest_prerequisite"}:
                typed_key = "quest_id" if kind == "quest_prerequisite" else "guide_id"
                typed_id = action.get(typed_key)
                if type(typed_id) is not int or typed_id <= 0:
                    raise CawottePilotDataError(
                        f"Invalid {kind} at step {number}"
                    )
                prerequisites.append({"name": label, typed_key: typed_id})
            elif kind in {"prepare_object", "optional_preparation"}:
                item_id, quantity = action.get("object_id"), action.get("quantity")
                if (type(item_id) is not int or item_id <= 0
                        or type(quantity) is not int or quantity <= 0):
                    raise CawottePilotDataError(
                        f"Invalid preparation at step {number}"
                    )
                preparations.append({
                    "name": label, "item_id": item_id, "quantity": quantity,
                    "category": "Objets",
                    "occurrence_id": f"{step_id}:action_{action_index + 1}",
                })
            else:
                rows.append({
                    "kind": "action", "text": label,
                    "position": f"[{coords[0]}, {coords[1]}]",
                    "source_action_kind": kind,
                })
        cards.append({
            "manual_source": True, "manual_review_only": True,
            "source_step_id": step_id, "manual_stage_id": step_id,
            "manual_title": f"Étape {number}",
            "manual_chapter_label": "Cawotte · revue",
            "manual_review_position": f"[{coords[0]}, {coords[1]}]",
            "manual_sections": {"now": rows},
            "hard_runtime_gates": prerequisites,
            "a_preparer": preparations,
            "manual_quest_ids": [],
            # Keep all 191 candidate records intact for independent review.
            # Not source_step.actions: those are reserved for authorized data.
            "manual_runtime_metadata": {
                "source_step": {"actions": []},
                "candidate_actions": actions,
            },
        })
    return tuple(cards)


__all__ = ["CAWOTTE_CANDIDATES", "CawottePilotDataError", "cawotte_review_cards"]
