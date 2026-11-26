from __future__ import annotations

from collections.abc import Callable, Mapping
from logging import Logger

from app.core.logger import get_runtime_logger
from app.network.character_runtime_state import (
    CharacterRuntimeStateStore,
    character_runtime_state,
)
from app.network.contracts import forward_decoder_reset, forward_decoder_session_closed
from app.network.current_protocol_profile import DOFUS_361010_PROFILE
from app.network.diagnostics import network_debug_enabled, network_debug_log
from app.network.protobuf_fields import (
    ProtobufDecodeError,
    parse_protobuf_fields,
    resolve_field_path,
)
from app.network.transport import CapturedProtocolMessage, ProtocolMessageDecoder


# These aliases/shapes come from independently reconstructed Unity protocols in
# the same protocol family as Atlas' reviewed 3.6.x profile. Alias names can
# rotate between client builds, so the known alias is accepted only when the
# payload also matches the strict structure. A rotated alias is learned only on
# the already verified Npcap transport session and only after stronger shape
# evidence; learned aliases are volatile and never persisted as a global mapping.
# Real 3.6.10.10 captures identify kub as the character-characteristics sheet.
# Unlike the family-reference aliases above, Atlas accepts this alias only as
# the exact captured 3.6.10.10 shape and never learns a rotated equivalent.
_CHARACTER_CHARACTERISTICS_TYPE_URL = "type.ankama.com/kub"
# Reviewed 3.6.10.10 selection payload: f1.f1.f1 is the character detail
# block, where f2 is the already-reviewed character name and f3 is the level.
# This path is consumed only after the exact-build identity decoder accepted
# the same kva packet as a verified character identity.
_VERIFIED_SELECTED_LEVEL_PATH = (1, 1, 1, 3)
_CANDIDATE_LEVEL_PATHS = ((1, 4, 2), (1, 4, 4))
_MIN_ACHIEVEMENT_SNAPSHOT_MATCHES = 3
_MAX_PROFILE_DISCOVERY_PAYLOAD_BYTES = 512 * 1024

# Names are kept semantic and UI-neutral. IDs are the ones explicitly resolved
# from the 3.6.10.10 client characteristic table and real kub captures by Jondo.
_CHARACTERISTIC_STAT_KEYS_BY_ID: dict[int, str] = {
    0: "life_points",
    1: "action_points",
    10: "strength",
    11: "vitality",
    12: "wisdom",
    13: "chance",
    14: "agility",
    15: "intelligence",
    18: "critical",
    19: "range",
    23: "movement_points",
    25: "power",
    26: "summons",
    27: "dodge_action_points",
    28: "dodge_movement_points",
    40: "pods",
    44: "initiative",
    47: "energy",
    48: "prospecting",
    49: "heals",
    78: "escape",
    79: "lock",
    82: "withdraw_action_points",
    83: "withdraw_movement_points",
    96: "shield",
}
_CORE_CHARACTERISTIC_IDS = frozenset({0, 1, 10, 11, 12, 13, 14, 15, 23})
_BODY_ALLOWED_FIELDS = frozenset({1, 4, 7, 8, 9, 10, 11})
_ENTRY_ALLOWED_FIELDS = frozenset({1, 2, 4, 5})


def _candidate_level(payload: bytes) -> tuple[int | None, tuple[int | None, int | None]]:
    """Return a level only when both independent level fields agree."""

    if len(payload) > _MAX_PROFILE_DISCOVERY_PAYLOAD_BYTES:
        return None, (None, None)
    try:
        candidates = tuple(
            resolve_field_path(payload, path, expected_kind="positive_int")
            for path in _CANDIDATE_LEVEL_PATHS
        )
    except ProtobufDecodeError:
        return None, (None, None)
    normalized = (
        int(candidates[0]) if candidates and candidates[0] is not None else None,
        int(candidates[1]) if len(candidates) > 1 and candidates[1] is not None else None,
    )
    level = (
        normalized[0]
        if normalized[0] is not None
        and normalized[0] == normalized[1]
        and 1 <= normalized[0] <= 200
        else None
    )
    return level, normalized


def _signed_int64(raw_value: int) -> int | None:
    """Interpret protobuf int32/int64 negative varints without guessing zig-zag fields."""

    value = int(raw_value)
    if value < 0 or value > (1 << 64) - 1:
        return None
    if value >= 1 << 63:
        value -= 1 << 64
    return value


def _singular_signed_scalar(fields, field_number: int) -> int | None:
    rows = fields.get(int(field_number), ())
    if not rows:
        return 0
    if len(rows) != 1 or not isinstance(rows[0], int):
        return None
    return _signed_int64(rows[0])


def _characteristic_container_value(container_field: int, payload: bytes) -> int | None:
    try:
        fields = parse_protobuf_fields(payload, max_bytes=64 * 1024)
    except ProtobufDecodeError:
        return None

    if container_field == 4:
        if not set(fields).issubset({2, 3, 7}):
            return None
        components = tuple(_singular_signed_scalar(fields, field) for field in (2, 3, 7))
    elif container_field == 5:
        if not set(fields).issubset({1, 5}):
            return None
        components = tuple(_singular_signed_scalar(fields, field) for field in (1, 5))
    elif container_field == 2:
        if not set(fields).issubset({2}):
            return None
        components = (_singular_signed_scalar(fields, 2),)
    else:
        return None

    if any(component is None for component in components):
        return None
    return sum(int(component) for component in components if component is not None)


def _expected_characteristic_container(characteristic_id: int) -> int:
    if characteristic_id in {1, 23}:
        return 5
    if characteristic_id in {47, 96}:
        return 2
    return 4


def _candidate_character_stats(payload: bytes) -> tuple[tuple[str, int], ...] | None:
    """Decode the exact 3.6.10.10 kub character sheet conservatively.

    kub is f2 { ... f11 repeated characteristic entries ... }. Each entry has
    an optional f1 id (life is id zero and therefore omits it) and exactly one
    value container. The captured client uses f4 for most characteristics, f5
    for AP/MP and f2 for a small special family. Values shown by the character
    sheet are the sum of the captured base/parchment/equipment components.
    """

    if not payload or len(payload) > _MAX_PROFILE_DISCOVERY_PAYLOAD_BYTES:
        return None
    try:
        root = parse_protobuf_fields(payload, max_bytes=_MAX_PROFILE_DISCOVERY_PAYLOAD_BYTES)
    except ProtobufDecodeError:
        return None
    if set(root) != {2}:
        return None
    body_rows = root.get(2, ())
    if len(body_rows) != 1 or not isinstance(body_rows[0], bytes):
        return None
    try:
        body = parse_protobuf_fields(body_rows[0], max_bytes=_MAX_PROFILE_DISCOVERY_PAYLOAD_BYTES)
    except ProtobufDecodeError:
        return None
    if 11 not in body or not set(body).issubset(_BODY_ALLOWED_FIELDS):
        return None

    for field_number in (1, 4, 7, 8, 10):
        rows = body.get(field_number, ())
        if len(rows) > 1 or any(not isinstance(value, int) for value in rows):
            return None
    metadata_rows = body.get(9, ())
    if len(metadata_rows) > 1 or any(not isinstance(value, bytes) for value in metadata_rows):
        return None

    seen_ids: set[int] = set()
    decoded_by_key: dict[str, int] = {}
    characteristic_rows = body.get(11, ())
    if len(characteristic_rows) < len(_CORE_CHARACTERISTIC_IDS):
        return None

    for raw_entry in characteristic_rows:
        if not isinstance(raw_entry, bytes):
            return None
        try:
            entry = parse_protobuf_fields(raw_entry, max_bytes=64 * 1024)
        except ProtobufDecodeError:
            return None
        if not entry or not set(entry).issubset(_ENTRY_ALLOWED_FIELDS):
            return None

        id_rows = entry.get(1, ())
        if len(id_rows) > 1 or any(not isinstance(value, int) for value in id_rows):
            return None
        characteristic_id = int(id_rows[0]) if id_rows else 0
        if characteristic_id < 0 or characteristic_id in seen_ids:
            return None
        seen_ids.add(characteristic_id)

        containers = tuple(field for field in (2, 4, 5) if field in entry)
        if len(containers) != 1:
            return None
        container_field = containers[0]
        container_rows = entry.get(container_field, ())
        if len(container_rows) != 1 or not isinstance(container_rows[0], bytes):
            return None

        stat_key = _CHARACTERISTIC_STAT_KEYS_BY_ID.get(characteristic_id)
        if stat_key is None:
            continue
        if container_field != _expected_characteristic_container(characteristic_id):
            return None
        value = _characteristic_container_value(container_field, container_rows[0])
        if value is None:
            return None
        decoded_by_key[stat_key] = value

    if not _CORE_CHARACTERISTIC_IDS.issubset(seen_ids):
        return None
    return tuple(
        (stat_key, decoded_by_key[stat_key])
        for stat_key in _CHARACTERISTIC_STAT_KEYS_BY_ID.values()
        if stat_key in decoded_by_key
    )


def _candidate_achievement_snapshot(
    payload: bytes,
    achievement_points_by_id: Mapping[int, int],
    *,
    minimum_matches: int = _MIN_ACHIEVEMENT_SNAPSHOT_MATCHES,
) -> tuple[tuple[int, ...], int] | None:
    """Recognize the clear-proto AchievementsEvent shape.

    The event is one repeated field 1 containing AchievedAchievement rows. Each
    row is scalar-only with achievement id in field 1 and optional metadata in
    fields 2..4. Every id must exist in Atlas' current achievement catalogue.
    This makes a false match across unrelated protobuf messages extremely
    unlikely while still allowing a rotated Any alias to be learned at runtime.
    """

    if not achievement_points_by_id or len(payload) > _MAX_PROFILE_DISCOVERY_PAYLOAD_BYTES:
        return None
    try:
        fields = parse_protobuf_fields(payload, max_bytes=_MAX_PROFILE_DISCOVERY_PAYLOAD_BYTES)
    except ProtobufDecodeError:
        return None
    if set(fields) != {1}:
        return None
    rows = fields.get(1, ())
    if len(rows) < max(1, int(minimum_matches)):
        return None

    achievement_ids: list[int] = []
    for raw_row in rows:
        if not isinstance(raw_row, bytes):
            return None
        try:
            row = parse_protobuf_fields(raw_row, max_bytes=64 * 1024)
        except ProtobufDecodeError:
            return None
        if not row or not set(row).issubset({1, 2, 3, 4}):
            return None
        id_rows = row.get(1, ())
        if len(id_rows) != 1 or not isinstance(id_rows[0], int):
            return None
        achievement_id = int(id_rows[0])
        if achievement_id <= 0 or achievement_id not in achievement_points_by_id:
            return None
        for values in row.values():
            if any(not isinstance(value, int) for value in values):
                return None
        achievement_ids.append(achievement_id)

    unique_ids = tuple(dict.fromkeys(achievement_ids))
    if len(unique_ids) != len(achievement_ids):
        return None
    points = sum(
        max(0, int(achievement_points_by_id[achievement_id]))
        for achievement_id in unique_ids
    )
    return unique_ids, points


class CharacterRuntimeProtocolMessageDecoder:
    """Project Npcap character facts into the central volatile read model.

    Identity still comes exclusively from Atlas' exact-build verified decoder.
    Profile packets are accepted only server->client, only after that same
    transport session is routed to a stable character id, and only when their
    reviewed protobuf shape is verified. Only the selection level and the
    reviewed statistics opcode are projected; historical family aliases and
    rotated structural candidates remain non-authoritative.
    """

    def __init__(
        self,
        delegate: ProtocolMessageDecoder,
        *,
        state: CharacterRuntimeStateStore | None = None,
        achievement_points_by_id: Mapping[int, int] | None = None,
        active_profile_matches: Callable[[], bool] | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.delegate = delegate
        self.state = state or character_runtime_state()
        self.active_profile_matches = active_profile_matches
        # Keep the legacy keyword for callers. Profile projection uses the
        # reviewed live profile and no longer constructs a points lookup.
        self.logger = logger or get_runtime_logger()

    def decode(self, message: CapturedProtocolMessage):
        decoded = self.delegate.decode(message)
        if decoded is not None:
            self._project_verified_identity(message, decoded)
        self._project_profile_facts(message)
        return decoded

    def session_closed(self, session_id: str) -> None:
        try:
            forward_decoder_session_closed(self.delegate, session_id)
        finally:
            self.state.close_session(session_id)

    def reset(self) -> None:
        try:
            forward_decoder_reset(self.delegate)
        finally:
            self.state.clear_sessions()

    def _project_verified_identity(self, message: CapturedProtocolMessage, decoded) -> None:
        if not bool(getattr(decoded, "verified", False)):
            return
        if str(getattr(decoded, "event_type", "") or "").casefold() != "character_identified":
            return
        decoded_session = str(getattr(decoded, "session_id", "") or "").strip()
        if not decoded_session or decoded_session != str(message.session_id or "").strip():
            return
        fields = getattr(decoded, "fields", {})
        if not isinstance(fields, Mapping):
            return
        try:
            character_id = int(fields.get("character_id") or 0)
        except (TypeError, ValueError, OverflowError):
            return
        name = str(fields.get("character_name") or "").strip()
        if character_id <= 0 or not name:
            return

        next_key = f"character:{character_id}"
        identified = self.state.identify(
            session_id=decoded_session,
            character_key=next_key,
            character_id=character_id,
            name=name,
        )
        if identified:
            self._project_verified_selection_level(message, decoded_session)

    def _project_verified_selection_level(
        self,
        message: CapturedProtocolMessage,
        session_id: str,
    ) -> None:
        """Project the level carried by the already-verified kva identity.

        Jondo's real 3.6.10.10 captures document the selected-character detail
        block as f1.f1.f1 with name in f2 and level in f3. Atlas already proves
        the id/name correlation on this exact kva before this method is reached,
        so level is supplementary data on a trusted identity, never an identity
        heuristic of its own.
        """

        if str(message.direction or "").strip().casefold() != "server_to_client":
            return
        if str(message.type_url or "").strip() != DOFUS_361010_PROFILE.character_selected_type_url:
            return
        if len(message.payload) > _MAX_PROFILE_DISCOVERY_PAYLOAD_BYTES:
            return
        try:
            raw_level = resolve_field_path(
                message.payload,
                _VERIFIED_SELECTED_LEVEL_PATH,
                expected_kind="positive_int",
            )
        except ProtobufDecodeError:
            return
        try:
            level = int(raw_level) if raw_level is not None else 0
        except (TypeError, ValueError, OverflowError):
            return
        if not 1 <= level <= 200:
            return
        self.state.update_verified_profile(session_id, level=level)
        if network_debug_enabled():
            network_debug_log(
                self.logger,
                "[NETWORK][CHARACTER_PROFILE][LEVEL]",
                session=session_id,
                message_type=message.type_url,
                candidate_paths=(_VERIFIED_SELECTED_LEVEL_PATH,),
                candidate_values=(level,),
                level=level,
                trusted=True,
                reason="verified_character_selection_identity",
            )

    def _project_profile_facts(self, message: CapturedProtocolMessage) -> None:
        if message.type_url != _CHARACTER_CHARACTERISTICS_TYPE_URL:
            return
        if str(message.direction or "").strip().casefold() != "server_to_client":
            return
        if len(message.payload) > _MAX_PROFILE_DISCOVERY_PAYLOAD_BYTES:
            return

        session = str(message.session_id or "").strip()
        if not session or self.state.snapshot_for_session(session) is None:
            # Profile facts before verified kvi+kva identity are intentionally
            # discarded instead of being queued for a later character.
            return

        if self.active_profile_matches is not None and not self.active_profile_matches():
            return
        self._try_apply_character_stats(session, message.payload)

    def _try_apply_character_stats(self, session: str, payload: bytes) -> None:
        stats = _candidate_character_stats(payload)
        if stats is None:
            if network_debug_enabled():
                network_debug_log(
                    self.logger,
                    "[NETWORK][CHARACTER_PROFILE][STATS]",
                    session=session,
                    message_type=_CHARACTER_CHARACTERISTICS_TYPE_URL,
                    trusted=False,
                    reason="exact_kub_shape_rejected",
                )
            return
        changed = self.state.update_verified_profile(session, stats=stats)
        if network_debug_enabled():
            network_debug_log(
                self.logger,
                "[NETWORK][CHARACTER_PROFILE][STATS]",
                session=session,
                message_type=_CHARACTER_CHARACTERISTICS_TYPE_URL,
                stat_count=len(stats),
                stat_keys=tuple(key for key, _value in stats),
                trusted=True,
                changed=changed,
                reason="reviewed_361010_kub_shape",
            )

__all__ = ["CharacterRuntimeProtocolMessageDecoder"]
