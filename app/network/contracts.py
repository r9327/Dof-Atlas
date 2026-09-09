from __future__ import annotations

from types import MappingProxyType
from typing import Iterable, Mapping

from app.constants import DATA_DIR


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
