"""Read-only review of signed Ganymède starts against Atlas canonical maps.

A corroborated candidate does not authorize travel. The caller must still
explicitly review and bind a typed RouteAction to an individual source step.
"""
from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

from app.core.character_identity import require_character_key
from app.modules.encyclopedia.services.adventure_route_engine import RouteAction
from app.modules.encyclopedia.services.guide_ganymede_continuous_plan import (
    _reviewed_start_travel,
)
from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    certified_payload_sha256,
    select_verified_replacement_path,
)


def review_ganymede_start_correspondences(
    guides_dir: Path,
    atlas_guide_id: str,
    character_keys: Iterable[str],
    canonical_actions: Iterable[RouteAction],
    canonical_map_positions: Mapping[int, tuple[int, int]],
) -> dict[str, object]:
    """Make a source-order audit report without creating executable plans."""
    selected = tuple(require_character_key(key) for key in character_keys)
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("Review requires distinct selected characters")
    if not isinstance(canonical_map_positions, Mapping):
        raise ValueError("Review requires canonical map information")
    path = select_verified_replacement_path(
        Path(guides_dir),
        {"id": atlas_guide_id, "category": "dofus"},
        allow_source_manual=True,
    )
    if path is None:
        raise ValueError("No integrity-checked Ganymède source for review")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (payload.get("replacement_status") != "TRUSTED_SOURCE_STEPS"
            or payload.get("canonical_objectives_certified") is not False
            or payload.get("auto_completion_allowed") is not False):
        raise ValueError("Only manual unverified sources may be reviewed")

    by_quest: dict[int, list[RouteAction]] = defaultdict(list)
    seen_action_ids: set[str] = set()
    for action in canonical_actions:
        if not isinstance(action, RouteAction):
            raise ValueError("Canonical actions must be typed RouteAction objects")
        if action.action_id in seen_action_ids:
            raise ValueError("Duplicate canonical action ID")
        seen_action_ids.add(action.action_id)
        if action.kind == "start":
            if type(action.quest_id) is not int or action.quest_id <= 0:
                raise ValueError("Invalid canonical start quest ID")
            by_quest[action.quest_id].append(action)

    report: list[dict[str, object]] = []
    steps = payload["sections"][0]["steps"]
    for step in steps:
        starts = [
            row for row in step["source_action_candidates"]
            if row.get("kind") == "quest_start"
        ]
        if not starts:
            continue
        quest_id = starts[0].get("quest_id") if len(starts) == 1 else None
        action_id = None
        map_id = None
        confirmed = False
        if len(starts) != 1:
            reason = "ambiguous_source_starts"
        elif type(quest_id) is not int or quest_id <= 0:
            reason = "invalid_source_quest_id"
        else:
            candidates = by_quest.get(quest_id, [])
            if not candidates:
                reason = "canonical_start_not_found"
            elif len(candidates) != 1:
                reason = "ambiguous_canonical_starts"
            else:
                action = candidates[0]
                try:
                    # Use the same evidence checks as the planner but discard
                    # the resulting transient travel plan; never expose it here.
                    _reviewed_start_travel(
                        step, action, list(selected), canonical_map_positions,
                    )
                except ValueError as exc:
                    reason = str(exc)
                else:
                    reason = "exact_quest_map_and_coordinates"
                    confirmed = True
                    action_id = action.action_id
                    map_id = action.location.map_id
        report.append({
            "source_step_id": step["id"],
            "source_step_number": step["source_step_number"],
            "source_quest_id": quest_id,
            "source_observed_coordinates": step["source_coordinates_mentioned"],
            "canonical_action_id": action_id,
            "canonical_map_id": map_id,
            "status": "CORROBORATED_REVIEW_ONLY" if confirmed else "REVIEW_REQUIRED",
            "reason": reason,
            "travel_authorized": False,
        })
    corroborated = sum(
        row["status"] == "CORROBORATED_REVIEW_ONLY" for row in report
    )
    return {
        "schema_version": 1,
        "status": "REVIEW_ONLY_NO_AUTOMATIC_TRAVEL",
        "atlas_guide_id": atlas_guide_id,
        "source_guide_id": payload["source_guide_id"],
        "source_payload_sha256": certified_payload_sha256(payload),
        "selected_character_keys": list(selected),
        "source_step_count": len(steps),
        "candidate_count": len(report),
        "corroborated_count": corroborated,
        "requires_review_count": len(report) - corroborated,
        "ready_for_automatic_travel": False,
        "runtime_verified_travel_plans": {},
        "candidates": report,
    }


__all__ = ["review_ganymede_start_correspondences"]
