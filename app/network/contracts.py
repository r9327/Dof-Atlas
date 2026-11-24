from __future__ import annotations

import hashlib
import re

from types import MappingProxyType
from typing import Callable, Iterable, Mapping

from app.constants import DATA_DIR


def _is_sha256(value: object) -> bool:
    """True only for exactly 32 bytes represented as 64 ASCII hex digits.

    bytes.fromhex is not suitable as a validator: it silently accepts spaces
    inside a 64-character input and may decode far fewer than 32 bytes.
    Preserve uppercase hexadecimal without trimming or coercing the input.
    """
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def protocol_event_id(
    version: str, fingerprint: str, type_url: str, payload: bytes, *, namespace: str = "",
) -> str:
    """Preserve byte-for-byte legacy event IDs across all verified decoders."""
    digest = hashlib.sha256()
    digest.update(version.encode("utf-8"))
    digest.update(b"\0")
    digest.update(fingerprint.encode("ascii"))
    digest.update(b"\0")
    if namespace:
        digest.update(namespace.encode("ascii"))
        digest.update(b"\0")
    digest.update(type_url.encode("utf-8", errors="strict"))
    digest.update(b"\0")
    digest.update(payload)
    return f"proto:{digest.hexdigest()[:32]}"


def required_mapping_identity(version: object, fingerprint: object, provider: object) -> tuple[str, str]:
    """Shared normalization for decoders requiring a fingerprint provider."""
    normalized_version = str(version or "").strip()
    normalized_fingerprint = str(fingerprint or "").strip().casefold()
    if not normalized_version:
        raise ValueError("mapping_version cannot be empty")
    if not _is_sha256(normalized_fingerprint):
        raise ValueError("mapping_fingerprint must be a SHA-256 digest")
    if provider is None:
        raise ValueError("active_fingerprint_provider is required")
    return normalized_version, normalized_fingerprint


def active_build_matches(
    provider: Callable[[], str | None], expected_fingerprint: str,
) -> bool:
    """Fail closed if the live build cannot be read or does not match."""
    try:
        active = str(provider() or "").strip().casefold()
    except Exception:
        return False
    return active == expected_fingerprint


def forward_decoder_session_closed(delegate: object, session_id: str) -> None:
    hook = getattr(delegate, "session_closed", None)
    if callable(hook):
        hook(session_id)


def forward_decoder_reset(delegate: object) -> None:
    hook = getattr(delegate, "reset", None)
    if callable(hook):
        hook()


def is_current_ankama_alias(value: str) -> bool:
    """Match only the reviewed three-letter lower-case current aliases."""
    prefix = "type.ankama.com/"
    alias = value[len(prefix) :] if value.startswith(prefix) else ""
    return len(alias) == 3 and alias.isascii() and alias.isalpha() and alias.islower()


DEFAULT_PROTOCOL_MAPPING_DIR = DATA_DIR / "network" / "protocol_mappings"

# Production live tracking requires an exact character identity route and a
# direct quest-completion capability. For the reviewed current profile that
# capability comes from idz {quest, validated step} only after the catalog-aware
# final-step filter proves the validated step is the quest's last ordered step.
# The login idr journal is a separate catch-up capability and must never
# masquerade as live tracking on its own.
REQUIRED_RUNTIME_EVENTS = frozenset({"character_identified", "quest_completed"})
RUNTIME_IDENTITY_EVENTS = frozenset({"character_identified"})
RUNTIME_QUEST_COMPLETION_EVENTS = frozenset({"quest_completed"})

# Full in-app calibration is stricter than the live runtime: Atlas must prove
# both final-step live completion evidence and the reviewed idr quest journal
# used to recover quests completed while Atlas was closed.
REQUIRED_FULL_CALIBRATION_EVENTS = frozenset(
    {"character_identified", "quest_completed", "quest_journal_snapshot"}
)

# The original discovery/deobfs audit works on one singular semantic scalar per
# event. Keep its evidence contract explicit instead of pretending the abstract
# ``quest_completion`` capability or specialized decoders fit that format.
DIRECT_MAPPING_EVIDENCE_EVENTS = frozenset({"character_identified", "quest_completed"})

# Clear-proto semantic names are used only as independent deobfuscation
# reference labels. They are not current-build aliases and never authorize
# progression on their own. In particular, current live evidence is reviewed
# idz step validation plus the local final-step check; the historical semantic
# name below is only a research label. The reviewed current whole-journal
# message is idr and has a different wire contract from historical QuestsEvent.
REQUIRED_RUNTIME_SEMANTICS: Mapping[str, str] = MappingProxyType(
    {
        "character_identified": "CharacterSelectionEvent",
        "quest_completed": "QuestValidatedEvent",
    }
)


def _normalized_events(provided_events: Iterable[str]) -> set[str]:
    return {
        str(event or "").strip().casefold()
        for event in provided_events
        if str(event or "").strip()
    }


def missing_runtime_capabilities(provided_events: Iterable[str]) -> tuple[str, ...]:
    """Return missing production live-tracking capabilities."""

    provided = _normalized_events(provided_events)
    missing: list[str] = []
    if not (provided & RUNTIME_IDENTITY_EVENTS):
        missing.append("character_identified")
    # Do not trust the abstract ``quest_completion`` marker here. A manifest can
    # also expose that marker because it contains a quest journal/snapshot; the
    # catch-up journal is not proof of a live completion signal.
    if not (provided & RUNTIME_QUEST_COMPLETION_EVENTS):
        missing.append("quest_completion")
    return tuple(missing)


def runtime_capabilities_ready(provided_events: Iterable[str]) -> bool:
    return not missing_runtime_capabilities(provided_events)


def missing_full_calibration_capabilities(provided_events: Iterable[str]) -> tuple[str, ...]:
    """Return what is missing for live tracking *and* login quest catch-up."""

    provided = _normalized_events(provided_events)
    missing = list(missing_runtime_capabilities(provided))
    if "quest_journal_snapshot" not in provided:
        missing.append("quest_journal_snapshot")
    return tuple(dict.fromkeys(missing))


def full_calibration_capabilities_ready(provided_events: Iterable[str]) -> bool:
    return not missing_full_calibration_capabilities(provided_events)


__all__ = [
    "DEFAULT_PROTOCOL_MAPPING_DIR",
    "active_build_matches",
    "forward_decoder_session_closed",
    "forward_decoder_reset",
    "is_current_ankama_alias",
    "DIRECT_MAPPING_EVIDENCE_EVENTS",
    "REQUIRED_FULL_CALIBRATION_EVENTS",
    "REQUIRED_RUNTIME_EVENTS",
    "REQUIRED_RUNTIME_SEMANTICS",
    "RUNTIME_IDENTITY_EVENTS",
    "RUNTIME_QUEST_COMPLETION_EVENTS",
    "full_calibration_capabilities_ready",
    "missing_full_calibration_capabilities",
    "missing_runtime_capabilities",
    "runtime_capabilities_ready",
]
