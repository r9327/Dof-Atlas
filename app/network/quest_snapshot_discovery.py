from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet

from app.network.protobuf_fields import ProtobufDecodeError, parse_protobuf_fields
from app.network.transport import CapturedProtocolMessage
from app.network.wire import IncompleteVarint, InvalidVarint, decode_varint


@dataclass(frozen=True, slots=True)
class QuestSnapshotDiscoveryCandidate:
    """One payload-only candidate for the historical QuestsEvent wire shape.

    This helper is diagnostic evidence only and can never authorize progression.
    The current reviewed quest journal has its own exact ``idr`` decoder and is
    explicitly excluded here so the old shape-discovery path cannot compete with
    or reinterpret the authoritative current contract.
    """

    type_url: str
    player_id: int
    finished_quest_ids: tuple[int, ...]
    active_quest_ids: tuple[int, ...]
    reinitialized_quest_ids: tuple[int, ...]


_KNOWN_NON_SNAPSHOT_TYPE_URLS = frozenset(
    {
        # Reviewed current identity/live-completion/journal aliases.
        "type.ankama.com/kvi",
        "type.ankama.com/kva",
        "type.ankama.com/lqn",
        "type.ankama.com/idr",
        # Historical quest labels that were previously treated as QuestsEvent
        # leads. The reconstructed 3.6.10.10 schema disproves them explicitly:
        #   isf = repeated message + string
        #   izu = strings/bool/int32 payload
        #   lry = map<string,int64> + int32
        # None can be the reviewed historical QuestsEvent envelope. Keep them
        # denied even if arbitrary bytes happen to resemble that old shape.
        "type.ankama.com/isf",
        "type.ankama.com/izu",
        "type.ankama.com/lry",
    }
)


def discover_current_quest_snapshot(
    message: CapturedProtocolMessage,
    *,
    selected_character_id: int,
    known_quest_ids: AbstractSet[int],
    minimum_finished_quests: int = 2,
) -> QuestSnapshotDiscoveryCandidate | None:
    """Recognize the historical QuestsEvent structure without guessing its alias.

    The clear quest protocol historically defined QuestsEvent as:
      f1 repeated QuestFinished { f1 quest_id, f2 finished_count }
      f2 repeated QuestActive   { f1 quest_id, f2 optional details }
      f3 repeated/packed int32 reinitialized_done_quests_id
      f4 optional int64 player_id

    Current reviewed captures identify ``idr`` as the real whole-journal message
    with a different wire contract. This function remains only to reject or
    inspect legacy evidence; it must never authorize progression by itself.
    """

    try:
        character_id = int(selected_character_id)
        minimum = int(minimum_finished_quests)
    except (TypeError, ValueError, OverflowError):
        return None
    if character_id <= 0 or minimum < 2:
        return None
    if str(message.direction or "").strip().casefold() != "server_to_client":
        return None

    type_url = str(message.type_url or "").strip()
    if not _is_current_type_url(type_url) or type_url in _KNOWN_NON_SNAPSHOT_TYPE_URLS:
        return None

    try:
        fields = parse_protobuf_fields(message.payload)
    except ProtobufDecodeError:
        return None
    if not fields or not set(fields).issubset({1, 2, 3, 4}):
        return None

    player_rows = fields.get(4, ())
    if len(player_rows) != 1 or not isinstance(player_rows[0], int):
        return None
    if int(player_rows[0]) != character_id:
        return None

    finished_rows = fields.get(1, ())
    if len(finished_rows) < minimum or len(finished_rows) > 4096:
        return None
    finished_ids: list[int] = []
    for raw_entry in finished_rows:
        quest_id = _finished_quest_id(raw_entry)
        if quest_id is None or quest_id not in known_quest_ids:
            return None
        finished_ids.append(quest_id)
    finished = _unique_positive(finished_ids)
    if len(finished) < minimum:
        return None

    active_rows = fields.get(2, ())
    if len(active_rows) > 4096:
        return None
    active_ids: list[int] = []
    for raw_entry in active_rows:
        quest_id = _active_quest_id(raw_entry)
        if quest_id is None or quest_id not in known_quest_ids:
            return None
        active_ids.append(quest_id)

    reinitialized = _parse_reinitialized_ids(fields.get(3, ()))
    if reinitialized is None:
        return None
    if any(quest_id not in known_quest_ids for quest_id in reinitialized):
        return None

    active = _unique_positive(active_ids)
    if set(finished) & set(active):
        return None

    return QuestSnapshotDiscoveryCandidate(
        type_url=type_url,
        player_id=character_id,
        finished_quest_ids=finished,
        active_quest_ids=active,
        reinitialized_quest_ids=reinitialized,
    )


def _finished_quest_id(raw_entry: object) -> int | None:
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
    count_rows = fields.get(2, ())
    if len(count_rows) != 1 or not isinstance(count_rows[0], int) or count_rows[0] <= 0:
        return None
    return int(quest_rows[0])


def _active_quest_id(raw_entry: object) -> int | None:
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


def _parse_reinitialized_ids(rows: tuple[object, ...]) -> tuple[int, ...] | None:
    values: list[int] = []
    for row in rows:
        if isinstance(row, int):
            if row <= 0:
                return None
            values.append(int(row))
            continue
        if not isinstance(row, bytes):
            return None
        offset = 0
        try:
            while offset < len(row):
                value, offset = decode_varint(row, offset)
                if int(value) <= 0:
                    return None
                values.append(int(value))
        except (IncompleteVarint, InvalidVarint):
            return None
    return _unique_positive(values)


def _unique_positive(values: list[int]) -> tuple[int, ...]:
    return tuple(dict.fromkeys(int(value) for value in values if int(value) > 0))


def _is_current_type_url(value: str) -> bool:
    prefix = "type.ankama.com/"
    alias = value[len(prefix) :] if value.startswith(prefix) else ""
    return len(alias) == 3 and alias.isascii() and alias.isalpha() and alias.islower()


__all__ = ["QuestSnapshotDiscoveryCandidate", "discover_current_quest_snapshot"]
