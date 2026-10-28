"""Summarize opt-in launcher-to-Home traces, never certify performance alone."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

SEGMENTS = (
    ("launcher_entry", "home_event_loop", "Launcher entry -> Home event loop"),
    ("launcher_update_begin", "launcher_update_end", "Update + startup"),
    ("update_check_begin", "update_check_end", "Update check"),
    ("app_spawn_begin", "app_health_ack", "Spawn -> Qt health ACK (not Home)"),
    ("app_import_begin", "app_import_end", "Python/Qt import"),
    ("app_main_begin", "qt_application_created", "App main -> QApplication"),
    ("qt_application_created", "home_visible", "QApplication -> Home shown"),
    ("home_visible", "home_event_loop", "Home shown -> responsive event loop"),
)


def collect(lines: list[str]) -> dict[str, dict[str, int]]:
    sessions: dict[str, dict[str, int]] = defaultdict(dict)
    for raw in lines:
        try:
            row = json.loads(raw)
            if not isinstance(row, dict):
                continue
            session, event, stamp = row.get("session"), row.get("event"), row.get("t_ns")
            if (not isinstance(session, str) or not isinstance(event, str)
                    or not isinstance(stamp, int) or isinstance(stamp, bool)):
                continue
            sessions[session].setdefault(event, stamp)
        except (ValueError, TypeError):
            continue
    return sessions


def durations_ms(sessions: dict[str, dict[str, int]], start: str, end: str) -> list[float]:
    return [round((events[end] - events[start]) / 1_000_000, 3)
            for events in sessions.values() if start in events and end in events
            and events[end] >= events[start]]


def percentile(values: list[float], percentage: int) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentage * len(ordered) / 100) - 1)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Display measured startup p50/p95; use same PC and cache state.")
    parser.add_argument("trace", type=Path, help="startup_profile.jsonl collected on Windows")
    options = parser.parse_args(argv)
    try:
        rows = options.trace.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        parser.error(str(exc))
    sessions = collect(rows)
    print(f"Sessions: {len(sessions)} (missing checkpoints are excluded per segment)")
    for start, end, label in SEGMENTS:
        values = durations_ms(sessions, start, end)
        if values:
            print(f"{label}: n={len(values)} p50={median(values):.1f}ms p95={percentile(values, 95):.1f}ms")
        else:
            print(f"{label}: NOT RUN / no matching checkpoints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
