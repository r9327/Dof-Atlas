from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

from app.core.settings import load_settings
from app.network.build_fingerprint import ActiveProtocolBuildFingerprintProvider
from app.network.contracts import DEFAULT_PROTOCOL_MAPPING_DIR, missing_runtime_capabilities
from app.network.mapping_registry import ProtocolMappingRegistry


@dataclass(frozen=True, slots=True)
class LocalProtocolStatus:
    ready_for_composition: bool
    reason: str
    build_sha256: str = ""
    mapping_name: str = ""
    matched_mapping_count: int = 0
    invalid_mapping_names: tuple[str, ...] = ()
    missing_required_events: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "purpose": "local_protocol_status_no_capture",
            "capture_started": False,
            "ready_for_composition": self.ready_for_composition,
            "reason": self.reason,
            "build_sha256": self.build_sha256,
            "mapping_name": self.mapping_name,
            "matched_mapping_count": self.matched_mapping_count,
            "invalid_mapping_names": list(self.invalid_mapping_names),
            "missing_required_events": list(self.missing_required_events),
        }


def inspect_local_protocol_status(
    window_handles_provider: Callable[[], Iterable[int]],
    *,
    mapping_roots: Iterable[str | Path] | None = None,
    build_sha256_provider: Callable[[], str | None] | None = None,
) -> LocalProtocolStatus:
    try:
        handles = tuple(
            dict.fromkeys(
                int(handle)
                for handle in (window_handles_provider() or ())
                if _positive_int(handle) is not None
            )
        )
    except Exception:
        handles = ()
    if not handles:
        return LocalProtocolStatus(False, "no_window_handles")

    fingerprint_provider = build_sha256_provider or ActiveProtocolBuildFingerprintProvider(
        lambda: handles
    )
    try:
        build_sha256 = str(fingerprint_provider() or "").strip().casefold()
    except Exception:
        return LocalProtocolStatus(False, "build_fingerprint_error")
    if not _is_sha256(build_sha256):
        return LocalProtocolStatus(False, "build_fingerprint_unavailable")

    registry = ProtocolMappingRegistry(
        tuple(mapping_roots) if mapping_roots is not None else (DEFAULT_PROTOCOL_MAPPING_DIR,)
    )
    selection = registry.select(build_sha256)
    invalid_names = tuple(path.name for path in selection.invalid_paths)
    if not selection.usable or selection.manifest is None:
        return LocalProtocolStatus(
            False,
            f"mapping_{selection.reason}",
            build_sha256=build_sha256,
            matched_mapping_count=len(selection.matched_paths),
            invalid_mapping_names=invalid_names,
        )

    missing = missing_runtime_capabilities(selection.manifest.provided_event_types)
    mapping_name = selection.matched_paths[0].name if selection.matched_paths else ""
    if missing:
        return LocalProtocolStatus(
            False,
            "mapping_missing_required_events",
            build_sha256=build_sha256,
            mapping_name=mapping_name,
            matched_mapping_count=1,
            invalid_mapping_names=invalid_names,
            missing_required_events=missing,
        )
    return LocalProtocolStatus(
        True,
        "mapping_ready_not_started",
        build_sha256=build_sha256,
        mapping_name=mapping_name,
        matched_mapping_count=1,
        invalid_mapping_names=invalid_names,
    )


def _configured_handles() -> tuple[int, ...]:
    settings = load_settings()
    return tuple(
        dict.fromkeys(
            int(client.handle)
            for client in settings.clients
            if _positive_int(getattr(client, "handle", None)) is not None
        )
    )


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Show the active Dofus Unity build fingerprint and exact mapping status "
            "without opening any capture socket or mutating progression."
        )
    )
    parser.add_argument(
        "--mapping-root",
        action="append",
        default=None,
        help="Optional mapping directory/file; repeat to inspect custom roots.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        status = inspect_local_protocol_status(
            _configured_handles,
            mapping_roots=args.mapping_root,
        )
    except Exception as exc:
        print(f"network protocol status failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(status.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


__all__ = ["LocalProtocolStatus", "inspect_local_protocol_status"]


if __name__ == "__main__":
    raise SystemExit(main())
