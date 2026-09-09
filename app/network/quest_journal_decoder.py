from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable

from app.network.normalizer import DecodedClientMessage
from app.network.protobuf_fields import ProtobufDecodeError, parse_protobuf_fields
from app.network.transport import CapturedProtocolMessage, ProtocolMessageDecoder
from app.network.wire import IncompleteVarint, InvalidVarint, decode_varint


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
        version = str(mapping_version or "").strip()
        fingerprint = str(mapping_fingerprint or "").strip().casefold()
        if not version:
            raise ValueError("mapping_version cannot be empty")
        if not self._is_sha256(fingerprint):
            raise ValueError("mapping_fingerprint must be a SHA-256 digest")
        if active_fingerprint_provider is None:
            raise ValueError("active_fingerprint_provider is required")
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
            additional = self._decode_packed_positive_varints(packed)
            if additional is None:
                return None
            finished_ids.extend(additional)

        if len(finished_ids) > self.max_finished_quests:
            return None

        active = self._dedupe(active_ids)
        finished = self._dedupe(finished_ids)
        digest = hashlib.sha256()
        digest.update(self.mapping_version.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.mapping_fingerprint.encode("ascii"))
        digest.update(b"\0quest_journal_snapshot\0")
        digest.update(message.type_url.encode("utf-8", errors="strict"))
        digest.update(b"\0")
        digest.update(message.payload)
        return DecodedClientMessage(
            session_id=message.session_id,
            event_type="quest_journal_snapshot",
            fields={
                "active_quest_ids": active,
                "finished_quest_ids": finished,
            },
            event_id=f"proto:{digest.hexdigest()[:32]}",
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
        values: list[int] = []
        offset = 0
        try:
            while offset < len(payload):
                value, offset = decode_varint(payload, offset)
                if value <= 0:
                    return None
                values.append(int(value))
        except (IncompleteVarint, InvalidVarint):
            return None
        return tuple(values)

    @staticmethod
    def _dedupe(values: list[int]) -> tuple[int, ...]:
        result: list[int] = []
        seen: set[int] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return tuple(result)

    def session_closed(self, session_id: str) -> None:
        hook = getattr(self.delegate, "session_closed", None)
        if callable(hook):
            hook(session_id)

    def reset(self) -> None:
        hook = getattr(self.delegate, "reset", None)
        if callable(hook):
            hook()

    def _build_matches(self) -> bool:
        try:
            active = str(self.active_fingerprint_provider() or "").strip().casefold()
        except Exception:
            return False
        return active == self.mapping_fingerprint

    @staticmethod
    def _is_sha256(value: str) -> bool:
        if len(value) != 64:
            return False
        try:
            bytes.fromhex(value)
        except ValueError:
            return False
        return True


__all__ = ["QuestJournalDecoder", "QuestJournalRule"]
