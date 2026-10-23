"""Compatibility adapter for read-only Ganymède start correspondence reports.

All canonical map/source decisions come from guide_ganymede_travel_review.
This module only preserves the historic report shape used by the audit CLI.
Neither report enables executable GuideTravelPlan objects.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from app.core.character_identity import require_character_key
from app.modules.encyclopedia.services.adventure_route_engine import RouteAction
from app.modules.encyclopedia.services.guide_ganymede_travel_review import (
    review_signed_ganymede_start_candidates,
)


def review_ganymede_start_correspondences(
    guides_dir: Path,
    atlas_guide_id: str,
    character_keys: Iterable[str],
    canonical_actions: Iterable[RouteAction],
    canonical_map_positions: Mapping[int, tuple[int, int]],
) -> dict[str, object]:
    """Return the original read-only report, with one shared review engine."""
    selected = tuple(require_character_key(key) for key in character_keys)
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("Review requires distinct selected characters")
    if not isinstance(canonical_map_positions, Mapping):
        raise ValueError("Review requires canonical map information")

    # Preserve the audit CLI's strict duplicate-ID contract. The lower-level
    # review API reports duplicate starts as BLOCKED_ATLAS_AMBIGUOUS instead.
    actions = tuple(canonical_actions)
    if any(not isinstance(action, RouteAction) for action in actions):
        raise ValueError("Canonical actions must be typed RouteAction objects")
    identifiers = [action.action_id for action in actions]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Duplicate canonical action ID")
    try:
        raw = review_signed_ganymede_start_candidates(
            guides_dir, atlas_guide_id, actions, canonical_map_positions,
            selected,
        )
    except ValueError as exc:
        if str(exc) == "No signed Ganymède source route available":
            raise ValueError(
                "No integrity-checked Ganymède source for review"
            ) from exc
        raise

    candidates = []
    for row in raw["entries"]:
        corroborated = row["status"] == "CANDIDATE_REQUIRES_APPROVAL"
        candidates.append({
            "source_step_id": row["source_step_id"],
            "source_step_number": row["source_step_number"],
            "source_quest_id": row["quest_id"],
            "source_observed_coordinates": row["source_observed_coordinates"],
            "canonical_action_id": row["canonical_action_id"],
            "canonical_map_id": row["canonical_map_id"],
            "status": "CORROBORATED_REVIEW_ONLY" if corroborated else "REVIEW_REQUIRED",
            "reason": (
                "exact_quest_map_and_coordinates" if corroborated
                else row["reason"]
            ),
            "travel_authorized": False,
        })
    count = sum(row["status"] == "CORROBORATED_REVIEW_ONLY" for row in candidates)
    return {
        "schema_version": 1,
        "status": "REVIEW_ONLY_NO_AUTOMATIC_TRAVEL",
        "atlas_guide_id": raw["atlas_guide_id"],
        "source_guide_id": raw["source_guide_id"],
        "source_payload_sha256": raw["source_payload_sha256"],
        "selected_character_keys": raw["selected_character_keys"],
        "source_step_count": raw["source_step_count"],
        "candidate_count": len(candidates),
        "corroborated_count": count,
        "requires_review_count": len(candidates) - count,
        "ready_for_automatic_travel": False,
        "runtime_verified_travel_plans": {},
        "candidates": candidates,
    }


__all__ = ["review_ganymede_start_correspondences"]
