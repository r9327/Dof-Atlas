from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from app.network.correlated_identity_decoder import (
    CorrelatedCharacterIdentityDecoder,
    CorrelatedCharacterIdentityRule,
)
from app.network.mapped_decoder import (
    ProtocolFieldRule,
    ProtocolMessageRule,
    StrictMappedProtocolDecoder,
)
from app.network.quest_completion_info_decoder import (
    QuestCompletionInfoDecoder,
    QuestCompletionInfoRule,
)
from app.network.quest_journal_decoder import QuestJournalDecoder, QuestJournalRule
from app.network.quest_snapshot_decoder import (
    FinishedQuestsSnapshotDecoder,
    FinishedQuestsSnapshotRule,
)
from app.network.transport import ProtocolMessageDecoder


_SCHEMA_VERSION = 1
_ALLOWED_EVENTS: dict[str, dict[str, str]] = {
    "character_identified": {
        "character_name": "string",
        "character_id": "positive_int",
    },
    "quest_started": {"quest_id": "positive_int"},
    "quest_objective_completed": {
        "quest_id": "positive_int",
        "objective_id": "positive_int",
    },
    # ``validated_step_id`` is optional at the generic schema level because a
    # future reviewed protocol may expose a true one-shot completion event.
    # The current Dofus profile maps idz and always requires this extra field;
    # the progression bridge then proves it is the quest's final local step.
    "quest_completed": {
        "quest_id": "positive_int",
        "validated_step_id": "positive_int",
    },
    "achievement_objective_completed": {
        "achievement_id": "positive_int",
        "objective_id": "positive_int",
    },
    "achievement_completed": {"achievement_id": "positive_int"},
}
_REQUIRED_OUTPUTS: dict[str, frozenset[str]] = {
    "character_identified": frozenset({"character_name"}),
    "quest_started": frozenset({"quest_id"}),
    "quest_objective_completed": frozenset({"quest_id", "objective_id"}),
    "quest_completed": frozenset({"quest_id"}),
    "achievement_objective_completed": frozenset({"achievement_id", "objective_id"}),
    "achievement_completed": frozenset({"achievement_id"}),
}
_ANKAMA_TYPE_PREFIXES = ("type.ankama.com/", "ankama.com/")


class ProtocolMappingError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProtocolMappingManifest:
    game_version: str
    build_sha256: str
    rules: Mapping[str, ProtocolMessageRule]
    character_identity: CorrelatedCharacterIdentityRule | None = None
    quest_completion_info: QuestCompletionInfoRule | None = None
    quest_journal_snapshot: QuestJournalRule | None = None
    finished_quests_snapshot: FinishedQuestsSnapshotRule | None = None

    @property
    def provided_event_types(self) -> frozenset[str]:
        events = {str(rule.event_type).strip().casefold() for rule in self.rules.values()}
        if self.character_identity is not None:
            events.add("character_identified")
        if self.quest_completion_info is not None:
            events.add("quest_completed")
        if self.quest_journal_snapshot is not None:
            events.add("quest_journal_snapshot")
        if self.finished_quests_snapshot is not None:
            events.add("finished_quests_snapshot")
        if (
            "quest_completed" in events
            or "quest_journal_snapshot" in events
            or "finished_quests_snapshot" in events
        ):
            events.add("quest_completion")
        return frozenset(event for event in events if event)

    def build_decoder(
        self,
        *,
        active_build_sha256_provider: Callable[[], str | None],
        active_version_provider: Callable[[], str | None] | None = None,
    ) -> ProtocolMessageDecoder:
        """Build a fail-closed decoder bound to the exact local Unity build.

        ``game_version`` remains useful metadata and may be checked when a
        trustworthy local provider exists, but ``build_sha256`` is the primary
        runtime identity and is always required by a mapping manifest.
        """

        decoder: ProtocolMessageDecoder = StrictMappedProtocolDecoder(
            mapping_version=self.game_version,
            active_version_provider=active_version_provider,
            rules=self.rules,
            mapping_fingerprint=self.build_sha256,
            active_fingerprint_provider=active_build_sha256_provider,
        )
        if self.character_identity is not None:
            decoder = CorrelatedCharacterIdentityDecoder(
                decoder,
                self.character_identity,
                mapping_version=self.game_version,
                mapping_fingerprint=self.build_sha256,
                active_fingerprint_provider=active_build_sha256_provider,
            )
        if self.quest_completion_info is not None:
            decoder = QuestCompletionInfoDecoder(
                decoder,
                self.quest_completion_info,
                mapping_version=self.game_version,
                mapping_fingerprint=self.build_sha256,
                active_fingerprint_provider=active_build_sha256_provider,
            )
        if self.quest_journal_snapshot is not None:
            decoder = QuestJournalDecoder(
                decoder,
                self.quest_journal_snapshot,
                mapping_version=self.game_version,
                mapping_fingerprint=self.build_sha256,
                active_fingerprint_provider=active_build_sha256_provider,
            )
        if self.finished_quests_snapshot is not None:
            decoder = FinishedQuestsSnapshotDecoder(
                decoder,
                self.finished_quests_snapshot,
                mapping_version=self.game_version,
                mapping_fingerprint=self.build_sha256,
                active_fingerprint_provider=active_build_sha256_provider,
            )
        return decoder


def load_protocol_mapping(path: str | Path) -> ProtocolMappingManifest:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolMappingError(f"cannot load protocol mapping: {source}") from exc
    return parse_protocol_mapping(raw)


def parse_protocol_mapping(raw: Any) -> ProtocolMappingManifest:
    if not isinstance(raw, Mapping):
        raise ProtocolMappingError("protocol mapping root must be an object")

    schema_version = _strict_int(raw.get("schema_version"))
    if schema_version != _SCHEMA_VERSION:
        raise ProtocolMappingError(f"unsupported protocol mapping schema_version: {schema_version}")

    game_version = str(raw.get("game_version") or "").strip()
    if not game_version:
        raise ProtocolMappingError("game_version cannot be empty")

    build_sha256 = str(raw.get("build_sha256") or "").strip().casefold()
    if not _is_sha256(build_sha256):
        raise ProtocolMappingError("build_sha256 must be a 64-character SHA-256 hex digest")

    raw_identity = raw.get("character_identity")
    character_identity = _parse_character_identity(raw_identity) if raw_identity is not None else None
    raw_completion_info = raw.get("quest_completion_info")
    quest_completion_info = (
        _parse_quest_completion_info(raw_completion_info)
        if raw_completion_info is not None
        else None
    )
    raw_journal = raw.get("quest_journal_snapshot")
    quest_journal_snapshot = (
        _parse_quest_journal_snapshot(raw_journal) if raw_journal is not None else None
    )
    raw_snapshot = raw.get("finished_quests_snapshot")
    finished_quests_snapshot = (
        _parse_finished_quests_snapshot(raw_snapshot) if raw_snapshot is not None else None
    )

    raw_messages = raw.get("messages")
    if not isinstance(raw_messages, Mapping):
        raise ProtocolMappingError("messages must be an object")
    if (
        not raw_messages
        and character_identity is None
        and quest_completion_info is None
        and quest_journal_snapshot is None
        and finished_quests_snapshot is None
    ):
        raise ProtocolMappingError(
            "mapping must contain messages, character_identity, quest_completion_info, "
            "quest_journal_snapshot or finished_quests_snapshot"
        )

    rules: dict[str, ProtocolMessageRule] = {}
    for raw_type_url, raw_rule in raw_messages.items():
        type_url = str(raw_type_url or "").strip()
        if not _is_ankama_type_url(type_url):
            raise ProtocolMappingError(f"invalid Ankama type URL: {type_url!r}")
        if not isinstance(raw_rule, Mapping):
            raise ProtocolMappingError(f"mapping for {type_url!r} must be an object")

        event_type = str(raw_rule.get("event_type") or "").strip().casefold()
        allowed_outputs = _ALLOWED_EVENTS.get(event_type)
        if allowed_outputs is None:
            raise ProtocolMappingError(f"unsupported event_type: {event_type!r}")

        raw_fields = raw_rule.get("fields")
        if not isinstance(raw_fields, list) or not raw_fields:
            raise ProtocolMappingError(f"fields for {type_url!r} must be a non-empty list")

        fields: list[ProtocolFieldRule] = []
        output_names: set[str] = set()
        required_output_names: set[str] = set()
        for raw_field in raw_fields:
            if not isinstance(raw_field, Mapping):
                raise ProtocolMappingError(f"field rule for {type_url!r} must be an object")
            output_name = str(raw_field.get("output_name") or "").strip()
            expected_kind = allowed_outputs.get(output_name)
            if expected_kind is None:
                raise ProtocolMappingError(
                    f"unsupported output {output_name!r} for event {event_type!r}"
                )
            if output_name in output_names:
                raise ProtocolMappingError(
                    f"duplicate output {output_name!r} for type {type_url!r}"
                )
            output_names.add(output_name)

            kind = str(raw_field.get("kind") or "").strip()
            if kind != expected_kind:
                raise ProtocolMappingError(
                    f"output {output_name!r} for event {event_type!r} must use kind {expected_kind!r}"
                )

            raw_path = raw_field.get("path")
            path = _parse_path(raw_path, label=f"path for output {output_name!r}")
            required = raw_field.get("required", True)
            if not isinstance(required, bool):
                raise ProtocolMappingError(f"required for output {output_name!r} must be boolean")
            if required:
                required_output_names.add(output_name)
            fields.append(
                ProtocolFieldRule(
                    output_name=output_name,
                    path=path,
                    kind=kind,
                    required=required,
                )
            )

        missing = _REQUIRED_OUTPUTS[event_type] - required_output_names
        if missing:
            raise ProtocolMappingError(
                f"event {event_type!r} is missing required outputs: {sorted(missing)}"
            )
        rules[type_url] = ProtocolMessageRule(event_type=event_type, fields=tuple(fields))

    specialized_urls: list[str] = []
    if character_identity is not None:
        specialized_urls.extend(
            [character_identity.roster_type_url, character_identity.selected_type_url]
        )
        if any(rule.event_type == "character_identified" for rule in rules.values()):
            raise ProtocolMappingError(
                "direct and correlated character_identified mappings cannot be enabled together"
            )
    if quest_completion_info is not None:
        specialized_urls.append(quest_completion_info.type_url)
    if quest_journal_snapshot is not None:
        specialized_urls.append(quest_journal_snapshot.type_url)
    if finished_quests_snapshot is not None:
        specialized_urls.append(finished_quests_snapshot.type_url)

    if len(set(specialized_urls)) != len(specialized_urls):
        raise ProtocolMappingError("specialized decoder type URLs must be distinct")
    conflicting_urls = set(specialized_urls) & set(rules)
    if conflicting_urls:
        raise ProtocolMappingError(
            f"specialized decoder URLs cannot also be message rules: {sorted(conflicting_urls)}"
        )

    return ProtocolMappingManifest(
        game_version=game_version,
        build_sha256=build_sha256,
        rules=MappingProxyType(rules),
        character_identity=character_identity,
        quest_completion_info=quest_completion_info,
        quest_journal_snapshot=quest_journal_snapshot,
        finished_quests_snapshot=finished_quests_snapshot,
    )


def _parse_character_identity(raw: Any) -> CorrelatedCharacterIdentityRule:
    if not isinstance(raw, Mapping):
        raise ProtocolMappingError("character_identity must be an object")
    roster_type_url = str(raw.get("roster_type_url") or "").strip()
    selected_type_url = str(raw.get("selected_type_url") or "").strip()
    if not roster_type_url.startswith("type.ankama.com/"):
        raise ProtocolMappingError("character_identity roster_type_url must use type.ankama.com/")
    if not selected_type_url.startswith("type.ankama.com/"):
        raise ProtocolMappingError("character_identity selected_type_url must use type.ankama.com/")
    roster_entry_field = _positive_int(raw.get("roster_entry_field"), label="roster_entry_field")
    roster_character_id_path = _parse_path(
        raw.get("roster_character_id_path"),
        label="roster_character_id_path",
    )
    roster_character_name_path = _parse_path(
        raw.get("roster_character_name_path"),
        label="roster_character_name_path",
    )
    selected_character_id_path = _parse_path(
        raw.get("selected_character_id_path"),
        label="selected_character_id_path",
    )
    raw_selected_character_name_path = raw.get("selected_character_name_path")
    selected_character_name_path = (
        ()
        if raw_selected_character_name_path in (None, "", [])
        else _parse_path(
            raw_selected_character_name_path,
            label="selected_character_name_path",
        )
    )
    try:
        return CorrelatedCharacterIdentityRule(
            roster_type_url=roster_type_url,
            selected_type_url=selected_type_url,
            roster_entry_field=roster_entry_field,
            roster_character_id_path=roster_character_id_path,
            roster_character_name_path=roster_character_name_path,
            selected_character_id_path=selected_character_id_path,
            selected_character_name_path=selected_character_name_path,
        )
    except ValueError as exc:
        raise ProtocolMappingError(str(exc)) from exc


def _parse_quest_completion_info(raw: Any) -> QuestCompletionInfoRule:
    if not isinstance(raw, Mapping):
        raise ProtocolMappingError("quest_completion_info must be an object")
    type_url = str(raw.get("type_url") or "").strip()
    if not type_url.startswith("type.ankama.com/"):
        raise ProtocolMappingError("quest_completion_info type_url must use type.ankama.com/")
    message_id_field = _positive_int(raw.get("message_id_field"), label="message_id_field")
    parameters_field = _positive_int(raw.get("parameters_field"), label="parameters_field")
    completion_message_id = _positive_int(
        raw.get("completion_message_id"),
        label="completion_message_id",
    )
    raw_parameter_index = raw.get("quest_id_parameter_index", 0)
    quest_id_parameter_index = _non_negative_int(
        raw_parameter_index,
        label="quest_id_parameter_index",
    )
    raw_type_field = raw.get("message_type_field")
    message_type_field = (
        None
        if raw_type_field in (None, "")
        else _positive_int(raw_type_field, label="message_type_field")
    )
    completion_message_type = _non_negative_int(
        raw.get("completion_message_type", 0),
        label="completion_message_type",
    )
    try:
        return QuestCompletionInfoRule(
            type_url=type_url,
            message_id_field=message_id_field,
            parameters_field=parameters_field,
            completion_message_id=completion_message_id,
            quest_id_parameter_index=quest_id_parameter_index,
            message_type_field=message_type_field,
            completion_message_type=completion_message_type,
        )
    except ValueError as exc:
        raise ProtocolMappingError(str(exc)) from exc


def _parse_quest_journal_snapshot(raw: Any) -> QuestJournalRule:
    if not isinstance(raw, Mapping):
        raise ProtocolMappingError("quest_journal_snapshot must be an object")
    type_url = str(raw.get("type_url") or "").strip()
    if not type_url.startswith("type.ankama.com/"):
        raise ProtocolMappingError("quest_journal_snapshot type_url must use type.ankama.com/")
    try:
        return QuestJournalRule(
            type_url=type_url,
            active_entry_field=_positive_int(
                raw.get("active_entry_field"), label="active_entry_field"
            ),
            active_quest_id_field=_positive_int(
                raw.get("active_quest_id_field"), label="active_quest_id_field"
            ),
            active_body_field=_positive_int(
                raw.get("active_body_field"), label="active_body_field"
            ),
            finished_entry_field=_positive_int(
                raw.get("finished_entry_field"), label="finished_entry_field"
            ),
            finished_quest_id_field=_positive_int(
                raw.get("finished_quest_id_field"), label="finished_quest_id_field"
            ),
            finished_marker_field=_positive_int(
                raw.get("finished_marker_field"), label="finished_marker_field"
            ),
            additional_finished_packed_field=_positive_int(
                raw.get("additional_finished_packed_field"),
                label="additional_finished_packed_field",
            ),
        )
    except ValueError as exc:
        raise ProtocolMappingError(str(exc)) from exc


def _parse_finished_quests_snapshot(raw: Any) -> FinishedQuestsSnapshotRule:
    if not isinstance(raw, Mapping):
        raise ProtocolMappingError("finished_quests_snapshot must be an object")
    type_url = str(raw.get("type_url") or "").strip()
    if not type_url.startswith("type.ankama.com/"):
        raise ProtocolMappingError("finished_quests_snapshot type_url must use type.ankama.com/")
    finished_entry_field = _positive_int(
        raw.get("finished_entry_field"),
        label="finished_entry_field",
    )
    quest_id_path_from_entry = _parse_path(
        raw.get("quest_id_path_from_entry"),
        label="quest_id_path_from_entry",
    )
    raw_player_id_field = raw.get("player_id_field")
    player_id_field = (
        None
        if raw_player_id_field in (None, "")
        else _positive_int(raw_player_id_field, label="player_id_field")
    )
    try:
        return FinishedQuestsSnapshotRule(
            type_url=type_url,
            finished_entry_field=finished_entry_field,
            quest_id_path_from_entry=quest_id_path_from_entry,
            player_id_field=player_id_field,
        )
    except ValueError as exc:
        raise ProtocolMappingError(str(exc)) from exc


def _parse_path(raw_path: Any, *, label: str) -> tuple[int, ...]:
    if not isinstance(raw_path, list) or not raw_path:
        raise ProtocolMappingError(f"{label} must be a non-empty list")
    return tuple(_positive_int(value, label=label) for value in raw_path)


def _is_ankama_type_url(value: str) -> bool:
    return any(value.startswith(prefix) and len(value) > len(prefix) for prefix in _ANKAMA_TYPE_PREFIXES)


def _strict_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _positive_int(value: Any, *, label: str) -> int:
    parsed = _strict_int(value)
    if parsed is None or parsed <= 0:
        raise ProtocolMappingError(f"{label} values must be positive integers")
    return parsed


def _non_negative_int(value: Any, *, label: str) -> int:
    parsed = _strict_int(value)
    if parsed is None or parsed < 0:
        raise ProtocolMappingError(f"{label} must be a non-negative integer")
    return parsed


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


__all__ = [
    "ProtocolMappingError",
    "ProtocolMappingManifest",
    "load_protocol_mapping",
    "parse_protocol_mapping",
]
