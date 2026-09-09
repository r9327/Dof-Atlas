from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from typing import Sequence

from app.core.settings import load_settings
from app.network.build_fingerprint import ActiveProtocolBuildFingerprintProvider
from app.network.discovery import ProtocolTargetDiscoveryCollector
from app.network.transport import CapturedProtocolMessage
from app.network.windows_capture import WindowsRawProtocolSource
from app.quest_catalog import load_quest_characters, normalize_text


_EVENT_CHARACTER_IDENTIFIED = "character_identified"
_EVENT_QUEST_COMPLETED = "quest_completed"
_EVENT_ACHIEVEMENT_COMPLETED = "achievement_completed"
_EVENT_CHOICES = (
    _EVENT_CHARACTER_IDENTIFIED,
    _EVENT_QUEST_COMPLETED,
    _EVENT_ACHIEVEMENT_COMPLETED,
)


def run_discovery_probe(
    *,
    event_type: str,
    capture_seconds: float,
    expected_id: int | None = None,
    character_slot: int | None = None,
) -> dict:
    event = str(event_type or "").strip().casefold()
    if event not in _EVENT_CHOICES:
        raise ValueError(f"unsupported discovery event: {event_type!r}")

    settings = load_settings()
    handles = tuple(
        dict.fromkeys(
            int(client.handle)
            for client in settings.clients
            if _positive_int(getattr(client, "handle", None)) is not None
        )
    )
    if not handles:
        raise RuntimeError("No connected Dofus window handle is configured in Dofus Atlas.")

    fingerprint_provider = ActiveProtocolBuildFingerprintProvider(lambda: handles)
    build_sha256 = fingerprint_provider()
    if not build_sha256:
        raise RuntimeError(
            "Could not fingerprint the active Dofus Unity build from GameAssembly.dll and global-metadata.dat."
        )

    collector = _collector_for_event(
        event,
        expected_id=expected_id,
        character_slot=character_slot,
    )
    capture_id = uuid.uuid4().hex
    duration = min(3600.0, max(1.0, float(capture_seconds)))
    source = WindowsRawProtocolSource(lambda: handles)
    deadline = time.monotonic() + duration
    source.start()
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                break
            item = source.read_item(min(0.25, remaining))
            if isinstance(item, CapturedProtocolMessage):
                collector.observe(item)
    finally:
        source.stop()

    candidates = [row.to_dict() for row in collector.snapshot()]
    return {
        "schema_version": 1,
        "purpose": "protocol_mapping_discovery_evidence_only",
        "authoritative_mapping": False,
        "privacy": "no_payload_no_scalar_value_no_session_no_address_storage",
        "direction": "server_to_client",
        "capture_id": capture_id,
        "build_sha256": str(build_sha256),
        "event_type": event,
        "capture_seconds": duration,
        "observed_message_count": collector.observed_message_count,
        "malformed_message_count": collector.malformed_message_count,
        "dropped_candidate_count": collector.dropped_candidate_count,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _collector_for_event(
    event_type: str,
    *,
    expected_id: int | None,
    character_slot: int | None,
) -> ProtocolTargetDiscoveryCollector:
    if event_type == _EVENT_CHARACTER_IDENTIFIED:
        names = _character_names_for_slot(character_slot)
        if not names:
            raise RuntimeError(
                "No usable Atlas character name is available for the requested slot."
            )
        return ProtocolTargetDiscoveryCollector(expected_strings=names)

    ident = _positive_int(expected_id)
    if ident is None:
        raise ValueError(f"--id must be a positive integer for {event_type}")
    return ProtocolTargetDiscoveryCollector(expected_positive_ints=(ident,))


def _character_names_for_slot(character_slot: int | None) -> tuple[str, ...]:
    wanted_slot = _positive_int(character_slot) if character_slot is not None else None
    names: list[str] = []
    for character in load_quest_characters():
        if wanted_slot is not None and int(character.slot) != wanted_slot:
            continue
        label = str(character.label or "").strip()
        if not label or normalize_text(label) == f"slot_{int(character.slot)}":
            continue
        if wanted_slot is None and not bool(character.connected):
            continue
        if label not in names:
            names.append(label)
    return tuple(names)


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect exact-build protobuf field-path evidence without storing "
            "packet payloads, scalar values, sessions, addresses or ports. "
            "Run it only around the known game action selected with --event."
        )
    )
    parser.add_argument("--event", choices=_EVENT_CHOICES, required=True)
    parser.add_argument(
        "--id",
        dest="expected_id",
        type=int,
        default=None,
        help="Known quest/achievement id for numeric discovery events. Not written to the report.",
    )
    parser.add_argument(
        "--slot",
        dest="character_slot",
        type=int,
        default=None,
        help="Atlas slot to use for character identification discovery. The name is not written to the report.",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=15.0,
        help="Capture duration in seconds (1-3600, default: 15).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_discovery_probe(
            event_type=args.event,
            capture_seconds=args.seconds,
            expected_id=args.expected_id,
            character_slot=args.character_slot,
        )
    except (PermissionError, RuntimeError, ValueError) as exc:
        print(f"network discovery probe failed: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("network discovery probe interrupted", file=sys.stderr)
        return 130
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
