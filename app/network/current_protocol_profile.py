from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any, Mapping

from app.network.mapping_manifest import ProtocolMappingManifest, parse_protocol_mapping


@dataclass(frozen=True, slots=True)
class ReviewedProtocolProfile:
    """Reviewed public protocol facts that are not a runtime mapping by themselves."""

    game_version: str
    evidence_revision: str
    source_commit: str
    character_roster_type_url: str
    character_selected_type_url: str
    quest_step_validated_type_url: str
    quest_journal_type_url: str


DOFUS_361010_PROFILE = ReviewedProtocolProfile(
    game_version="3.6.10.10",
    evidence_revision="jondo-401-quest-captures-2026-08-idz-final-step",
    source_commit="cd97a887718b1d19eb449f096098511549947e3c",
    character_roster_type_url="type.ankama.com/kvi",
    character_selected_type_url="type.ankama.com/kva",
    quest_step_validated_type_url="type.ankama.com/idz",
    quest_journal_type_url="type.ankama.com/idr",
)

# These values come from reviewed real captures and the reconstructed quest
# state machine. idz is a server-to-client "step validated" message carrying
# quest id in f1 and validated step id in f2. Atlas does not equate every idz to
# a completed quest: progression is written only when f2 is exactly the final
# step in the local ordered quest step list. The 3.6.10.10 -> 3.6.10.11 mapping
# keeps kvi/kva/idz/idr structurally stable; installed rules are still bound to
# the exact local executable SHA-256 before any progression can be touched.
_DOFUS_361010_MAPPING_BODY: Mapping[str, Any] = MappingProxyType(
    {
        "character_identity": {
            "roster_type_url": "type.ankama.com/kvi",
            "selected_type_url": "type.ankama.com/kva",
            "roster_entry_field": 1,
            "roster_character_id_path": [2],
            "roster_character_name_path": [1, 2],
            "selected_character_id_path": [1, 1, 2],
            "selected_character_name_path": [1, 1, 1, 2],
        },
        "quest_step_validated": {
            "type_url": "type.ankama.com/idz",
            "quest_id_path": [1],
            "validated_step_id_path": [2],
        },
        "quest_journal_snapshot": {
            "type_url": "type.ankama.com/idr",
            "active_entry_field": 1,
            "active_body_field": 2,
            "active_quest_id_field": 3,
            "finished_entry_field": 3,
            "finished_marker_field": 1,
            "finished_quest_id_field": 2,
            "additional_finished_packed_field": 4,
        },
    }
)

# Previous Atlas builds generated a specialized lqn rule and could persist it in
# data/local/network mappings. Real capture evidence disproves that use: lqn is
# intentionally retained only as a migration marker so old mappings can be
# stripped/overwritten, never decoded as progression again.
LEGACY_UNSAFE_QUEST_COMPLETION_TYPE_URL = "type.ankama.com/lqn"


def dofus_361010_profile_digest() -> str:
    """Return a stable digest of every reviewed current decoding rule."""

    payload = {
        "profile": asdict(DOFUS_361010_PROFILE),
        "mapping_body": {
            "character_identity": _copy_identity(),
            "quest_step_validated": _copy_step_validated(),
            "quest_journal_snapshot": dict(_DOFUS_361010_MAPPING_BODY["quest_journal_snapshot"]),
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dofus_361010_candidate_mapping_payload(
    build_sha256: str,
    *,
    include_quest_journal: bool = False,
    finished_quests_snapshot_type_url: str = "",
) -> dict[str, Any]:
    """Build a non-installed exact-build candidate from reviewed facts.

    Live completion evidence is idz plus the local final-step proof. Calibration
    requires two distinct quests to reach that condition on one identified
    transport session. ``include_quest_journal`` adds the independently reviewed
    idr catch-up rule. The optional historical snapshot alias remains
    compatibility-only and is never supplied by current calibration.
    """

    fingerprint = str(build_sha256 or "").strip().casefold()
    if not _is_sha256(fingerprint):
        raise ValueError("build_sha256 must be a 64-character SHA-256 digest")
    snapshot_type_url = str(finished_quests_snapshot_type_url or "").strip()
    if snapshot_type_url:
        if not _is_current_type_url(snapshot_type_url):
            raise ValueError("finished_quests_snapshot_type_url must be a current type.ankama.com alias")
        if snapshot_type_url in {
            DOFUS_361010_PROFILE.character_roster_type_url,
            DOFUS_361010_PROFILE.character_selected_type_url,
            DOFUS_361010_PROFILE.quest_step_validated_type_url,
            DOFUS_361010_PROFILE.quest_journal_type_url,
            LEGACY_UNSAFE_QUEST_COMPLETION_TYPE_URL,
        }:
            raise ValueError("finished_quests_snapshot_type_url conflicts with a reviewed opcode")

    step_rule = _copy_step_validated()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "game_version": DOFUS_361010_PROFILE.game_version,
        "build_sha256": fingerprint,
        "character_identity": _copy_identity(),
        "messages": {
            step_rule["type_url"]: {
                "event_type": "quest_completed",
                "fields": [
                    {
                        "output_name": "quest_id",
                        "path": list(step_rule["quest_id_path"]),
                        "kind": "positive_int",
                        "required": True,
                    },
                    {
                        "output_name": "validated_step_id",
                        "path": list(step_rule["validated_step_id_path"]),
                        "kind": "positive_int",
                        "required": True,
                    },
                ],
            }
        },
    }
    if include_quest_journal:
        payload["quest_journal_snapshot"] = dict(
            _DOFUS_361010_MAPPING_BODY["quest_journal_snapshot"]
        )
    if snapshot_type_url:
        payload["finished_quests_snapshot"] = {
            "type_url": snapshot_type_url,
            "finished_entry_field": 1,
            "quest_id_path_from_entry": [1],
            "player_id_field": 4,
        }
    return payload


def dofus_361010_candidate_manifest(
    build_sha256: str,
    *,
    include_quest_journal: bool = False,
    finished_quests_snapshot_type_url: str = "",
) -> ProtocolMappingManifest:
    """Parse a candidate through the same strict manifest contract as runtime."""

    return parse_protocol_mapping(
        dofus_361010_candidate_mapping_payload(
            build_sha256,
            include_quest_journal=include_quest_journal,
            finished_quests_snapshot_type_url=finished_quests_snapshot_type_url,
        )
    )


def _copy_identity() -> dict[str, Any]:
    identity = dict(_DOFUS_361010_MAPPING_BODY["character_identity"])
    identity["roster_character_id_path"] = list(identity["roster_character_id_path"])
    identity["roster_character_name_path"] = list(identity["roster_character_name_path"])
    identity["selected_character_id_path"] = list(identity["selected_character_id_path"])
    identity["selected_character_name_path"] = list(
        identity["selected_character_name_path"]
    )
    return identity


def _copy_step_validated() -> dict[str, Any]:
    row = dict(_DOFUS_361010_MAPPING_BODY["quest_step_validated"])
    row["quest_id_path"] = list(row["quest_id_path"])
    row["validated_step_id_path"] = list(row["validated_step_id_path"])
    return row


def _is_current_type_url(value: str) -> bool:
    prefix = "type.ankama.com/"
    alias = value[len(prefix) :] if value.startswith(prefix) else ""
    return len(alias) == 3 and alias.isascii() and alias.isalpha() and alias.islower()


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


__all__ = [
    "DOFUS_361010_PROFILE",
    "LEGACY_UNSAFE_QUEST_COMPLETION_TYPE_URL",
    "ReviewedProtocolProfile",
    "dofus_361010_candidate_manifest",
    "dofus_361010_candidate_mapping_payload",
    "dofus_361010_profile_digest",
]
