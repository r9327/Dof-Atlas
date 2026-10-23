"""Read-only candidate review for signed Ganymède and Atlas quest-start maps.

A matching quest ID and location are NOT permission to issue game commands.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
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


def signed_source_start_ids(
    steps: Iterable[Mapping[str, object]], *, strict: bool = True,
) -> tuple[int, ...]:
    """Extract only typed source quest-start IDs in one shared audit contract.

    Interactive previews can use strict=False to skip malformed suggestions,
    but both full CLI audits MUST use the strict default. No text inference.
    """
    unique: set[int] = set()
    for step in steps:
        if not isinstance(step, Mapping):
            raise ValueError("Malformed signed Ganymède step")
        actions = step.get("source_action_candidates")
        if not isinstance(actions, list):
            raise ValueError("Signed step lacks structured source actions")
        for row in actions:
            if not isinstance(row, Mapping):
                if strict:
                    raise ValueError("Malformed signed source action")
                continue
            if row.get("kind") != "quest_start":
                continue
            quest_id = row.get("quest_id")
            if type(quest_id) is not int or quest_id <= 0:
                if strict:
                    raise ValueError("Malformed signed quest start ID")
                continue
            unique.add(quest_id)
    return tuple(sorted(unique))


def review_signed_ganymede_start_candidates(
    guides_dir: Path,
    atlas_guide_id: str,
    actions: Iterable[RouteAction],
    canonical_map_positions: Mapping[int, tuple[int, int]],
    character_keys: Iterable[str],
) -> dict[str, object]:
    """Find exact candidates, always requiring a separate explicit approval."""
    keys = tuple(require_character_key(key) for key in character_keys)
    if not keys or len(keys) != len(set(keys)):
        raise ValueError("Review requires unique explicit participants")
    if not isinstance(canonical_map_positions, Mapping):
        raise ValueError("Atlas map registry must be supplied independently")
    path = select_verified_replacement_path(
        Path(guides_dir), {"id": atlas_guide_id, "category": "dofus"},
        allow_source_manual=True,
    )
    if path is None:
        raise ValueError("No signed Ganymède source route available")
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest = json.loads((path.parent / "cutover_manifest.json").read_text(encoding="utf-8"))
    record = manifest.get("guides", {}).get(atlas_guide_id)
    sha = certified_payload_sha256(payload)
    if (not isinstance(record, dict)
            or record.get("status") != "TRUSTED_SOURCE_STEPS"
            or record.get("payload_sha256") != sha
            or payload.get("id") != atlas_guide_id):
        raise ValueError("Ganymède cutover signature mismatch")
    steps = payload["sections"][0]["steps"]
    if len(steps) != record["source_step_count"]:
        raise ValueError("Signed source stage count mismatch")

    by_quest: dict[int, list[RouteAction]] = defaultdict(list)
    for action in actions:
        if not isinstance(action, RouteAction):
            raise ValueError("Atlas review requires typed canonical RouteAction")
        if (type(action.quest_id) is int and action.quest_id > 0
                and action.kind == "start"
                and action.action_id == f"quest:{action.quest_id}:start"
                and action.activates_quest is True):
            by_quest[action.quest_id].append(action)
    source_starts: Counter[int] = Counter(
        row["quest_id"]
        for step in steps
        for row in step["source_action_candidates"]
        if isinstance(row, Mapping) and row.get("kind") == "quest_start"
        and type(row.get("quest_id")) is int
    )

    entries: list[dict[str, object]] = []
    for step in steps:
        starts = [
            row for row in step["source_action_candidates"]
            if isinstance(row, Mapping) and row.get("kind") == "quest_start"
        ]
        if not starts:
            continue
        quest_id = starts[0].get("quest_id") if len(starts) == 1 else None
        action_id: str | None = None
        map_id: int | None = None
        if len(starts) != 1:
            status, reason = "BLOCKED_SOURCE_AMBIGUOUS", "Multiple quest starts in source stage"
        elif type(quest_id) is not int or quest_id <= 0:
            status, reason = "BLOCKED_QUEST_ID", "Source quest start lacks positive integer ID"
        elif source_starts[quest_id] != 1:
            status, reason = "BLOCKED_SOURCE_REPEATED", "Quest start repeats across stages"
        else:
            matches = by_quest.get(quest_id, ())
            if not matches:
                status, reason = "BLOCKED_ATLAS_MISSING", "No canonical start for this quest ID"
            elif len(matches) != 1:
                status, reason = "BLOCKED_ATLAS_AMBIGUOUS", "Canonical quest has duplicate starts"
            else:
                action = matches[0]
                action_id = action.action_id
                map_id = action.location.map_id
                try:
                    _reviewed_start_travel(
                        step, action, list(keys), canonical_map_positions,
                    )
                except ValueError as exc:
                    status, reason = "BLOCKED_LOCATION_UNVERIFIED", str(exc)
                else:
                    status = "CANDIDATE_REQUIRES_APPROVAL"
                    reason = "Exact quest, single source action and Atlas map agree"
        entries.append({
            "source_step_id": step["id"],
            "source_step_number": step["source_step_number"],
            "source_observed_coordinates": step["source_coordinates_mentioned"],
            "quest_id": quest_id,
            "canonical_action_id": action_id,
            "canonical_map_id": map_id,
            "status": status,
            "reason": reason,
        })
    return {
        "schema_version": 1,
        "status": "REVIEW_ONLY_NO_AUTOMATIC_TRAVEL",
        "atlas_guide_id": atlas_guide_id,
        "source_guide_id": payload["source_guide_id"],
        "source_payload_sha256": sha,
        "selected_character_keys": list(keys),
        "source_step_count": len(steps),
        "candidate_count": sum(
            row["status"] == "CANDIDATE_REQUIRES_APPROVAL" for row in entries
        ),
        "blocked_count": sum(
            row["status"] != "CANDIDATE_REQUIRES_APPROVAL" for row in entries
        ),
        "entries": entries,
        "verified_stage_travel": {},
        "ready_for_automatic_planning": False,
    }


def bind_explicitly_approved_starts(
    guides_dir: Path,
    atlas_guide_id: str,
    canonical_actions: Iterable[RouteAction],
    canonical_map_positions: Mapping[int, tuple[int, int]],
    character_keys: Iterable[str],
    approvals: Mapping[str, Mapping[str, object]],
) -> dict[str, RouteAction]:
    """Bind only individually approved, freshly rechecked signed source starts.

    An audit candidate is never an approval. Before returning any typed
    bindings, rerun the signed guide + canonical map checks, then require an
    explicit decision naming the source payload SHA, action and map ID.
    The caller still must pass the result to the manual-only planner; no
    macro is dispatched by this function.
    """
    if not isinstance(approvals, Mapping):
        raise ValueError("Explicit approvals must be a step-ID mapping")
    actions = tuple(canonical_actions)
    review = review_signed_ganymede_start_candidates(
        guides_dir, atlas_guide_id, actions,
        canonical_map_positions, character_keys,
    )
    by_id: dict[str, RouteAction] = {}
    for action in actions:
        if action.action_id in by_id:
            raise ValueError("Duplicate canonical action ID in approval lookup")
        by_id[action.action_id] = action
    candidates = {row["source_step_id"]: row for row in review["entries"]}
    approved: dict[str, RouteAction] = {}
    for step_id, decision in approvals.items():
        if not isinstance(step_id, str) or step_id not in candidates:
            raise ValueError("Approval references an unknown signed source step")
        row = candidates[step_id]
        if row["status"] != "CANDIDATE_REQUIRES_APPROVAL":
            raise ValueError("Blocked review candidate cannot be approved")
        if (not isinstance(decision, Mapping)
                or decision.get("approval_status") != "USER_APPROVED_EXACT_QUEST_MAP"
                or decision.get("source_payload_sha256") != review["source_payload_sha256"]
                or decision.get("canonical_action_id") != row["canonical_action_id"]
                or type(decision.get("canonical_map_id")) is not int
                or decision["canonical_map_id"] != row["canonical_map_id"]):
            raise ValueError("Approval must pin exact source, action and map")
        action = by_id.get(row["canonical_action_id"])
        if action is None or action.location.map_id != row["canonical_map_id"]:
            raise ValueError("Approved canonical action was changed")
        approved[step_id] = action
    return approved


__all__ = [
    "review_signed_ganymede_start_candidates",
    "signed_source_start_ids",
    "bind_explicitly_approved_starts",
]
