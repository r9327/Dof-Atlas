from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable

from app.network.normalizer import DecodedClientMessage
from app.network.protobuf_fields import (
    ProtobufDecodeError,
    ProtobufFields,
    parse_protobuf_fields,
    resolve_field_path,
)
from app.network.transport import CapturedProtocolMessage, ProtocolMessageDecoder
from app.network.wire import IncompleteVarint, InvalidVarint, decode_varint


@dataclass(frozen=True, slots=True)
class FinishedQuestsSnapshotRule:
    """Exact protobuf shape for one authoritative server quest snapshot."""

    type_url: str
    finished_entry_field: int
    quest_id_path_from_entry: tuple[int, ...]
    player_id_field: int | None = None

    def __post_init__(self) -> None:
        if not str(self.type_url or "").startswith("type.ankama.com/"):
            raise ValueError("finished quest snapshot type_url must use type.ankama.com/")
        if int(self.finished_entry_field) <= 0:
            raise ValueError("finished_entry_field must be positive")
        if not self.quest_id_path_from_entry or any(
            int(field_number) <= 0 for field_number in self.quest_id_path_from_entry
        ):
            raise ValueError("quest_id_path_from_entry must contain positive fields")
        if self.player_id_field is None or int(self.player_id_field) <= 0:
            raise ValueError("player_id_field is required and must be positive")
        if int(self.player_id_field) == int(self.finished_entry_field):
            raise ValueError("player_id_field must differ from finished_entry_field")


class FinishedQuestsSnapshotDecoder:
    """Decode a full completed-quest snapshot without structural guessing.

    The wrapper is intentionally narrow. It only handles one explicitly mapped
    current-build type URL, delegates every other message, and verifies the
    active Unity fingerprint before marking the snapshot semantic envelope as
    trusted. Repeated finished entries are expected here and therefore cannot be
    represented by the generic singular-field mapper.

    ``player_id_field`` is mandatory for every snapshot mapping. Current Atlas
    runtime does not enable this decoder because the exact 3.6.10.10 alias is not
    independently verified; the class remains for compatibility and focused
    decoder tests.

    The calibrated 3.6.10.10 rule is additionally revalidated against the same
    reviewed QuestsEvent wire envelope at runtime. Learning an alias once must
    not turn a later malformed payload under that alias into trusted progress.
    """

    def __init__(
        self,
        delegate: ProtocolMessageDecoder,
        rule: FinishedQuestsSnapshotRule,
        *,
        mapping_version: str,
        mapping_fingerprint: str,
        active_fingerprint_provider: Callable[[], str | None],
        max_finished_entries: int = 4096,
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
        self.max_finished_entries = max(1, min(int(max_finished_entries), 16384))

    def decode(self, message: CapturedProtocolMessage) -> DecodedClientMessage | None:
        if str(message.type_url or "") != self.rule.type_url:
            return self.delegate.decode(message)
        if str(message.direction or "").strip().casefold() != "server_to_client":
            return None
        try:
            active_fingerprint = str(self.active_fingerprint_provider() or "").strip().casefold()
        except Exception:
            return None
        if active_fingerprint != self.mapping_fingerprint:
            return None

        try:
            fields = parse_protobuf_fields(message.payload)
        except ProtobufDecodeError:
            return None
        entries = fields.get(int(self.rule.finished_entry_field), ())
        if len(entries) > self.max_finished_entries:
            return None

        quest_ids: list[int] = []
        seen: set[int] = set()
        for entry in entries:
            if not isinstance(entry, bytes):
                return None
            try:
                quest_id = resolve_field_path(
                    entry,
                    self.rule.quest_id_path_from_entry,
                    expected_kind="positive_int",
                )
            except ProtobufDecodeError:
                return None
            if not isinstance(quest_id, int) or quest_id <= 0:
                return None
            if quest_id not in seen:
                seen.add(quest_id)
                quest_ids.append(quest_id)

        player_id_field = int(self.rule.player_id_field)
        rows = fields.get(player_id_field, ())
        if len(rows) != 1:
            return None
        player_id = rows[0]
        if not isinstance(player_id, int) or player_id <= 0:
            return None

        if self._uses_reviewed_quests_event_shape() and not self._reviewed_shape_is_valid(
            fields,
            tuple(quest_ids),
        ):
            return None

        decoded_fields: dict[str, object] = {
            "quest_ids": tuple(quest_ids),
            "player_id": int(player_id),
        }
        digest = hashlib.sha256()
        digest.update(self.mapping_version.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.mapping_fingerprint.encode("ascii"))
        digest.update(b"\0")
        digest.update(message.type_url.encode("utf-8", errors="strict"))
        digest.update(b"\0")
        digest.update(message.payload)
        return DecodedClientMessage(
            session_id=message.session_id,
            event_type="finished_quests_snapshot",
            fields=decoded_fields,
            event_id=f"proto:{digest.hexdigest()[:32]}",
            verified=True,
        )

    def _uses_reviewed_quests_event_shape(self) -> bool:
        return (
            int(self.rule.finished_entry_field) == 1
            and tuple(self.rule.quest_id_path_from_entry) == (1,)
            and int(self.rule.player_id_field) == 4
        )

    def _reviewed_shape_is_valid(
        self,
        fields: ProtobufFields,
        finished_quest_ids: tuple[int, ...],
    ) -> bool:
        if not fields or not set(fields).issubset({1, 2, 3, 4}):
            return False

        for raw_entry in fields.get(1, ()):
            if not self._finished_entry_is_valid(raw_entry):
                return False

        active_ids: list[int] = []
        active_rows = fields.get(2, ())
        if len(active_rows) > 4096:
            return False
        for raw_entry in active_rows:
            quest_id = self._active_entry_quest_id(raw_entry)
            if quest_id is None:
                return False
            active_ids.append(quest_id)
        if set(finished_quest_ids) & set(active_ids):
            return False

        return self._reinitialized_rows_are_valid(fields.get(3, ()))

    @staticmethod
    def _finished_entry_is_valid(raw_entry: object) -> bool:
        if not isinstance(raw_entry, bytes):
            return False
        try:
            fields = parse_protobuf_fields(raw_entry)
        except ProtobufDecodeError:
            return False
        if not fields or not set(fields).issubset({1, 2}):
            return False
        quest_rows = fields.get(1, ())
        if len(quest_rows) != 1 or not isinstance(quest_rows[0], int) or quest_rows[0] <= 0:
            return False
        count_rows = fields.get(2, ())
        return (
            len(count_rows) == 1
            and isinstance(count_rows[0], int)
            and count_rows[0] > 0
        )

    @staticmethod
    def _active_entry_quest_id(raw_entry: object) -> int | None:
        if not isinstance(raw_entry, bytes):
            return None
        try:
            fields = parse_protobuf_fields(raw_entry)
        except ProtobufDecodeError:
            return None
        if not fields or not set(fields).issubset({1, 2}):
            return None
        quest_rows = fields.get(1, ())
        if len(quest_rows) != 1 or not isinstance(quest_rows[0], int) or quest_rows[0] <= 0:
            return None
        details_rows = fields.get(2, ())
        if len(details_rows) > 1 or any(not isinstance(value, bytes) for value in details_rows):
            return None
        return int(quest_rows[0])

    @staticmethod
    def _reinitialized_rows_are_valid(rows: tuple[object, ...]) -> bool:
        for row in rows:
            if isinstance(row, int):
                if row <= 0:
                    return False
                continue
            if not isinstance(row, bytes):
                return False
            offset = 0
            try:
                while offset < len(row):
                    value, offset = decode_varint(row, offset)
                    if int(value) <= 0:
                        return False
            except (IncompleteVarint, InvalidVarint):
                return False
        return True

    def session_closed(self, session_id: str) -> None:
        hook = getattr(self.delegate, "session_closed", None)
        if callable(hook):
            hook(session_id)

    def reset(self) -> None:
        hook = getattr(self.delegate, "reset", None)
        if callable(hook):
            hook()

    @staticmethod
    def _is_sha256(value: str) -> bool:
        if len(value) != 64:
            return False
        try:
            bytes.fromhex(value)
        except ValueError:
            return False
        return True


__all__ = ["FinishedQuestsSnapshotDecoder", "FinishedQuestsSnapshotRule"]
