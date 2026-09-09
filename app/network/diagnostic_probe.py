from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Sequence

from app.core.settings import load_settings
from app.network.build_fingerprint import ActiveProtocolBuildFingerprintProvider
from app.network.diagnostics import ProtocolDiagnosticsCollector
from app.network.transport import CapturedProtocolMessage
from app.network.windows_capture import WindowsRawProtocolSource


def run_probe(*, capture_seconds: float) -> dict:
    settings = load_settings()
    handles = tuple(
        int(client.handle)
        for client in settings.clients
        if int(client.handle) > 0
    )
    if not handles:
        raise RuntimeError("No connected Dofus window handle is configured in Dofus Atlas.")

    fingerprint_provider = ActiveProtocolBuildFingerprintProvider(lambda: handles)
    build_sha256 = fingerprint_provider()
    if not build_sha256:
        raise RuntimeError(
            "Could not fingerprint the active Dofus Unity build from GameAssembly.dll and global-metadata.dat."
        )

    collector = ProtocolDiagnosticsCollector()
    source = WindowsRawProtocolSource(lambda: handles)
    duration = min(3600.0, max(1.0, float(capture_seconds)))
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

    messages = [row.to_dict() for row in collector.snapshot()]
    return {
        "schema_version": 1,
        "privacy": "metadata_only_no_payload_storage",
        "direction": "server_to_client",
        "build_sha256": build_sha256,
        "capture_seconds": duration,
        "message_type_count": len(messages),
        "dropped_type_count": collector.dropped_type_count,
        "messages": messages,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Observe local Dofus protobuf metadata without storing packet payloads, "
            "addresses, ports, sessions, character names or decoded IDs."
        )
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=30.0,
        help="Capture duration in seconds (1-3600, default: 30).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_probe(capture_seconds=args.seconds)
    except (PermissionError, RuntimeError) as exc:
        print(f"network protocol probe failed: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("network protocol probe interrupted", file=sys.stderr)
        return 130
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
