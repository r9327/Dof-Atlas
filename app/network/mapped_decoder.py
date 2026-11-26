from __future__ import annotations

from app.network.contracts import _is_sha256 as _strict_sha256, active_build_matches, protocol_event_id

from dataclasses import dataclass
from typing import Mapping

from app.network.normalizer import DecodedClientMessage
from app.network.protobuf_fields import (
    ProtobufDecodeError,
    resolve_field_path,
    resolve_repeated_positive_int_path,
)
from app.network.transport import CapturedProtocolMessage


@dataclass(frozen=True, slots=True)
class ProtocolFieldRule:
    output_name: str
    path: tuple[int, ...]
    kind: str
    required: bool = True

    def __post_init__(self) -> None:
        if not self.output_name.strip():
            raise ValueError("protocol field output_name cannot be empty")
        if not self.path or any(int(field_number) <= 0 for field_number in self.path):
            raise ValueError("protocol field path must contain positive field numbers")
        if self.kind not in {"positive_int", "non_negative_int", "string", "repeated_positive_int"}:
            raise ValueError(f"unsupported protocol field kind: {self.kind}")
        if self.kind == "repeated_positive_int" and len(self.path) < 2:
            raise ValueError("repeated_positive_int needs a row field and an ID path")


@dataclass(frozen=True, slots=True)
class ProtocolMessageRule:
    event_type: str
    fields: tuple[ProtocolFieldRule, ...]

    def __post_init__(self) -> None:
        if not self.event_type.strip():
            raise ValueError("protocol event_type cannot be empty")


class StrictMappedProtocolDecoder:
    """Decode only explicitly mapped server messages for one exact protocol build.

    No structural guessing is performed. A decoder must have at least one live
    identity check. An exact Unity build fingerprint is sufficient on its own
    and is stronger than a display/version string. When an active version
    provider is also configured, both checks must match before a message can be
    marked verified.
    """

    def __init__(
        self,
        *,
        mapping_version: str,
        rules: Mapping[str, ProtocolMessageRule],
        active_version_provider=None,
        mapping_fingerprint: str = "",
        active_fingerprint_provider=None,
    ) -> None:
        version = str(mapping_version or "").strip()
        if not version:
            raise ValueError("mapping_version cannot be empty")
        fingerprint = str(mapping_fingerprint or "").strip().casefold()
        version_provider_configured = active_version_provider is not None
        fingerprint_provider_configured = active_fingerprint_provider is not None
        if bool(fingerprint) != fingerprint_provider_configured:
            raise ValueError(
                "mapping_fingerprint and active_fingerprint_provider must be configured together"
            )
        if fingerprint and not self._is_sha256(fingerprint):
            raise ValueError("mapping_fingerprint must be a 64-character SHA-256 hex digest")
        if not version_provider_configured and not fingerprint_provider_configured:
            raise ValueError("at least one active protocol identity provider is required")

        self.mapping_version = version
        self.active_version_provider = active_version_provider
        self.rules = {str(type_url): rule for type_url, rule in rules.items() if str(type_url).strip()}
        self.mapping_fingerprint = fingerprint
        self.active_fingerprint_provider = active_fingerprint_provider
        self._reported_failures: set[str] = set()

    def decode(self, message: CapturedProtocolMessage) -> DecodedClientMessage | None:
        rule = self.rules.get(str(message.type_url))
        if rule is None:
            # Unmapped traffic cannot produce a semantic event, so do not pay
            # process/file identity costs merely to reject it afterwards.
            return None
        if str(message.direction or "").strip().casefold() != "server_to_client":
            return None

        if self.active_version_provider is not None:
            try:
                active_version = str(self.active_version_provider() or "").strip()
            except Exception:
                return None
            if not active_version or active_version != self.mapping_version:
                return None

        if self.mapping_fingerprint and not active_build_matches(
            self.active_fingerprint_provider, self.mapping_fingerprint,
        ):
            return None

        fields: dict[str, object] = {}
        try:
            for field_rule in rule.fields:
                if field_rule.kind == "repeated_positive_int":
                    value = resolve_repeated_positive_int_path(message.payload, field_rule.path)
                else:
                    value = resolve_field_path(
                        message.payload,
                        field_rule.path,
                        expected_kind=field_rule.kind,
                    )
                if value is None:
                    if field_rule.required:
                        return None
                    continue
                fields[field_rule.output_name] = value
        except ProtobufDecodeError:
            if message.type_url not in self._reported_failures:
                from app.core.logger import get_runtime_logger
                get_runtime_logger().warning("Invalid mapped protobuf payload: type=%s", message.type_url, exc_info=True)
                self._reported_failures.add(message.type_url)
            return None

        return DecodedClientMessage(
            session_id=message.session_id,
            event_type=rule.event_type,
            fields=fields,
            event_id=protocol_event_id(
                self.mapping_version, self.mapping_fingerprint, message.type_url, message.payload,
            ),
            verified=True,
        )

    @staticmethod
    def _is_sha256(value: str) -> bool:
        """Compatibility method delegating to the single network contract."""
        return _strict_sha256(value)


__all__ = [
    "ProtocolFieldRule",
    "ProtocolMessageRule",
    "StrictMappedProtocolDecoder",
]
