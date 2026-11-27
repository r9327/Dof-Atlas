from __future__ import annotations

from app.network.contracts import (
    _is_sha256 as _strict_sha256, active_build_matches,
    forward_decoder_reset, forward_decoder_session_closed,
    protocol_event_id, required_mapping_identity,
)

from dataclasses import dataclass
from typing import Callable

from app.network.normalizer import DecodedClientMessage
from app.network.protobuf_fields import ProtobufDecodeError, parse_protobuf_fields, decode_packed_positive_varints
from app.network.transport import CapturedProtocolMessage, ProtocolMessageDecoder


@dataclass(frozen=True, slots=True)
class QuestJournalRule:
    """Exact current-build contract for the full quest journal.

    The reviewed ``idr`` wire message contains active quests in repeated root
    field 1, finished quests in repeated root field 3, and an additional packed
    finished-quest list in root field 4. The rule is still inert until a mapping
    binds it to the exact local IL2CPP fingerprint.
    """

    type_url: str
    active_entry_field: int = 1
    active_quest_id_field: int = 3
    active_body_field: int = 2
    finished_entry_field: int = 3
    finished_quest_id_field: int = 2
    finished_marker_field: int = 1
    additional_finished_packed_field: int = 4

    def __post_init__(self) -> None:
        if not str(self.type_url or "").startswith("type.ankama.com/"):
            raise ValueError("quest journal type_url must use type.ankama.com/")
        root_fields = {
            int(self.active_entry_field),
            int(self.finished_entry_field),
            int(self.additional_finished_packed_field),
        }
        if any(field <= 0 for field in root_fields) or len(root_fields) != 3:
            raise ValueError("quest journal root fields must be distinct positive integers")
        nested_fields = (
            self.active_quest_id_field,
            self.active_body_field,
            self.finished_quest_id_field,
            self.finished_marker_field,
        )
        if any(int(field) <= 0 for field in nested_fields):
            raise ValueError("quest journal nested fields must be positive integers")
        if int(self.active_quest_id_field) == int(self.active_body_field):
            raise ValueError("active quest id/body fields must be distinct")
        if int(self.finished_quest_id_field) == int(self.finished_marker_field):
            raise ValueError("finished quest id/marker fields must be distinct")


class QuestJournalDecoder:
    """Decode the reviewed ``idr`` journal without guessing by payload shape."""

    def __init__(
        self,
        delegate: ProtocolMessageDecoder,
        rule: QuestJournalRule,
        *,
        mapping_version: str,
        mapping_fingerprint: str,
        active_fingerprint_provider: Callable[[], str | None],
        max_active_quests: int = 4096,
        max_finished_quests: int = 8192,
    ) -> None:
        version, fingerprint = required_mapping_identity(
            mapping_version, mapping_fingerprint, active_fingerprint_provider,
        )
        self.delegate = delegate
        self.rule = rule
        self.mapping_version = version
        self.mapping_fingerprint = fingerprint
        self.active_fingerprint_provider = active_fingerprint_provider
        self.max_active_quests = max(1, min(int(max_active_quests), 16384))
        self.max_finished_quests = max(1, min(int(max_finished_quests), 32768))

    def decode(self, message: CapturedProtocolMessage) -> DecodedClientMessage | None:
        if str(message.type_url or "") != self.rule.type_url:
            return self.delegate.decode(message)
        if str(message.direction or "").strip().casefold() != "server_to_client":
            return None
        if not self._build_matches():
            return None

        try:
            fields = parse_protobuf_fields(message.payload)
        except ProtobufDecodeError:
            return None

        allowed_root_fields = {
            int(self.rule.active_entry_field),
            int(self.rule.finished_entry_field),
            int(self.rule.additional_finished_packed_field),
        }
        if not fields or not set(fields).issubset(allowed_root_fields):
            return None

        active_rows = fields.get(int(self.rule.active_entry_field), ())
        finished_rows = fields.get(int(self.rule.finished_entry_field), ())
        packed_rows = fields.get(int(self.rule.additional_finished_packed_field), ())
        if len(active_rows) > self.max_active_quests or len(finished_rows) > self.max_finished_quests:
            return None
        if len(packed_rows) > 1:
            return None

        active_ids: list[int] = []
        for row in active_rows:
            quest_id = self._active_quest_id(row)
            if quest_id is None:
                return None
            active_ids.append(quest_id)

        finished_ids: list[int] = []
        for row in finished_rows:
            quest_id = self._finished_quest_id(row)
            if quest_id is None:
                return None
            finished_ids.append(quest_id)

        if packed_rows:
            packed = packed_rows[0]
            if not isinstance(packed, bytes):
                return None
            additional = decode_packed_positive_varints(packed, limit=self.max_finished_quests - len(finished_ids))
            if additional is None:
                return None
            finished_ids.extend(additional)

        if len(finished_ids) > self.max_finished_quests:
            return None

        active = self._dedupe(active_ids)
        finished = self._dedupe(finished_ids)
        return DecodedClientMessage(
            session_id=message.session_id,
            event_type="quest_journal_snapshot",
            fields={
                "active_quest_ids": active,
                "finished_quest_ids": finished,
            },
            event_id=protocol_event_id(
                self.mapping_version, self.mapping_fingerprint, message.type_url, message.payload,
                namespace="quest_journal_snapshot",
            ),
            verified=True,
        )

    def _active_quest_id(self, row: object) -> int | None:
        if not isinstance(row, bytes):
            return None
        try:
            fields = parse_protobuf_fields(row)
        except ProtobufDecodeError:
            return None
        allowed = {int(self.rule.active_body_field), int(self.rule.active_quest_id_field)}
        if not set(fields).issubset(allowed):
            return None
        body_rows = fields.get(int(self.rule.active_body_field), ())
        quest_rows = fields.get(int(self.rule.active_quest_id_field), ())
        if len(body_rows) != 1 or not isinstance(body_rows[0], bytes):
            return None
        if len(quest_rows) != 1 or not isinstance(quest_rows[0], int) or quest_rows[0] <= 0:
            return None
        return int(quest_rows[0])

    def _finished_quest_id(self, row: object) -> int | None:
        if not isinstance(row, bytes):
            return None
        try:
            fields = parse_protobuf_fields(row)
        except ProtobufDecodeError:
            return None
        allowed = {int(self.rule.finished_marker_field), int(self.rule.finished_quest_id_field)}
        if not set(fields).issubset(allowed):
            return None
        marker_rows = fields.get(int(self.rule.finished_marker_field), ())
        quest_rows = fields.get(int(self.rule.finished_quest_id_field), ())
        if len(marker_rows) != 1 or marker_rows[0] != 1:
            return None
        if len(quest_rows) != 1 or not isinstance(quest_rows[0], int) or quest_rows[0] <= 0:
            return None
        return int(quest_rows[0])

    @staticmethod
    def _decode_packed_positive_varints(payload: bytes) -> tuple[int, ...] | None:
        return decode_packed_positive_varints(payload)

    @staticmethod
    def _dedupe(values: list[int]) -> tuple[int, ...]:
        return tuple(dict.fromkeys(values))

    def session_closed(self, session_id: str) -> None:
        forward_decoder_session_closed(self.delegate, session_id)

    def reset(self) -> None:
        forward_decoder_reset(self.delegate)

    def _build_matches(self) -> bool:
        return active_build_matches(
            self.active_fingerprint_provider, self.mapping_fingerprint,
        )

    @staticmethod
    def _is_sha256(value: str) -> bool:
        """Compatibility method delegating to the single network contract."""
        return _strict_sha256(value)


__all__ = ["QuestJournalDecoder", "QuestJournalRule"]
