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
        rows = []
        for action in actions:
            if not isinstance(action, dict):
                raise CawottePilotDataError(f"Invalid action at step {number}")
            kind, label = action.get("kind"), action.get("label")
            if (not isinstance(kind, str) or not kind.strip()
                    or not isinstance(label, str) or not label.strip() or len(label) > 512):
                raise CawottePilotDataError(f"Missing candidate action at step {number}")
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
            "manual_sections": {"now": rows},
            "manual_quest_ids": [],
            "manual_runtime_metadata": {"source_step": {"actions": []}},
        })
    return tuple(cards)


__all__ = ["CAWOTTE_CANDIDATES", "CawottePilotDataError", "cawotte_review_cards"]
