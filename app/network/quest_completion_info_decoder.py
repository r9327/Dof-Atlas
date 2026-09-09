from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Callable

from app.network.normalizer import DecodedClientMessage
from app.network.protobuf_fields import ProtobufDecodeError, parse_protobuf_fields
from app.network.transport import CapturedProtocolMessage, ProtocolMessageDecoder


@dataclass(frozen=True, slots=True)
class QuestCompletionInfoRule:
    """Legacy compatibility contract for an information-message completion rule.

    This parser is retained so Atlas can still read older mapping files and keep
    their behavior testable. It is **not** part of the reviewed current Dofus
    3.6.10.10 profile: capture-derived opcode evidence disproved the old Atlas
    assumption that ``type.ankama.com/lqn`` message 56 is a reliable quest-end
    signal. Current live progression uses reviewed ``idz`` step validation and
    accepts it only when the validated step is the quest's final local step.

    Current-profile bootstrap strips the legacy ``lqn`` rule before capability
    checks, so this compatibility decoder cannot authorize progression there.
    """

    type_url: str
    message_id_field: int
    parameters_field: int
    completion_message_id: int
    quest_id_parameter_index: int = 0
    message_type_field: int | None = None
    completion_message_type: int = 0

    def __post_init__(self) -> None:
        if not str(self.type_url or "").startswith("type.ankama.com/"):
            raise ValueError("quest completion info type_url must use type.ankama.com/")
        if int(self.message_id_field) <= 0:
            raise ValueError("message_id_field must be positive")
        if int(self.parameters_field) <= 0:
            raise ValueError("parameters_field must be positive")
        if int(self.completion_message_id) <= 0:
            raise ValueError("completion_message_id must be positive")
        if int(self.quest_id_parameter_index) < 0:
            raise ValueError("quest_id_parameter_index cannot be negative")
        if self.message_type_field is not None and int(self.message_type_field) <= 0:
            raise ValueError("message_type_field must be positive when configured")
        if int(self.completion_message_type) < 0:
            raise ValueError("completion_message_type cannot be negative")
        numbered_fields = {
            int(self.message_id_field),
            int(self.parameters_field),
        }
        if self.message_type_field is not None:
            numbered_fields.add(int(self.message_type_field))
        expected_count = 3 if self.message_type_field is not None else 2
        if len(numbered_fields) != expected_count:
            raise ValueError("quest completion info fields must use distinct protobuf numbers")


class QuestCompletionInfoDecoder:
    """Compatibility decoder for a mapping-defined information-message semantic.

    The implementation remains strict and build-bound for old/custom manifests,
    but no such rule is trusted by the current reviewed profile. In particular,
    the historical ``lqn`` message-56 interpretation is quarantined by current
    bootstrap and calibration code and must not be used as current evidence.
    """

    def __init__(
        self,
        delegate: ProtocolMessageDecoder,
        rule: QuestCompletionInfoRule,
        *,
        mapping_version: str,
        mapping_fingerprint: str,
        active_fingerprint_provider: Callable[[], str | None],
        max_parameters: int = 32,
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
        self.max_parameters = max(1, min(int(max_parameters), 256))

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

        message_id_rows = fields.get(int(self.rule.message_id_field), ())
        if len(message_id_rows) != 1:
            return None
        message_id = message_id_rows[0]
        if not isinstance(message_id, int) or message_id != int(self.rule.completion_message_id):
            return None

        type_field = self.rule.message_type_field
        if type_field is not None:
            type_rows = fields.get(int(type_field), ())
            if len(type_rows) > 1:
                return None
            if type_rows:
                message_type = type_rows[0]
                if not isinstance(message_type, int):
                    return None
                if message_type != int(self.rule.completion_message_type):
                    return None
            elif int(self.rule.completion_message_type) != 0:
                # Proto3 omits scalar zero values. Absence can prove only zero.
                return None

        parameter_rows = fields.get(int(self.rule.parameters_field), ())
        if len(parameter_rows) > self.max_parameters:
            return None
        parameter_index = int(self.rule.quest_id_parameter_index)
        if parameter_index >= len(parameter_rows):
            return None
        if any(not isinstance(row, bytes) for row in parameter_rows):
            return None

        raw_quest_id = parameter_rows[parameter_index]
        try:
            quest_id_text = raw_quest_id.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError:
            return None
        if not quest_id_text or not quest_id_text.isascii() or not quest_id_text.isdecimal():
            return None
        try:
            quest_id = int(quest_id_text, 10)
        except ValueError:
            return None
        if quest_id <= 0:
            return None

        digest = hashlib.sha256()
        digest.update(self.mapping_version.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.mapping_fingerprint.encode("ascii"))
        digest.update(b"\0quest_completed_info\0")
        digest.update(message.type_url.encode("utf-8", errors="strict"))
        digest.update(b"\0")
        digest.update(message.payload)
        return DecodedClientMessage(
            session_id=message.session_id,
            event_type="quest_completed",
            fields={"quest_id": quest_id},
            event_id=f"proto:{digest.hexdigest()[:32]}",
            verified=True,
        )

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


__all__ = ["QuestCompletionInfoDecoder", "QuestCompletionInfoRule"]
