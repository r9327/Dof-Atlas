"""Summarize opt-in launcher-to-Home traces, never certify performance alone."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from collections import defaultdict
from pathlib import Path
from statistics import median

SEGMENTS = (
    ("launcher_entry", "home_event_loop", "Launcher entry -> Home event loop"),
    ("launcher_entry", "home_first_paint", "Launcher entry -> first Home paint"),
    ("atlas_window_create_begin", "atlas_window_created", "AtlasWindow construction"),
    ("install_stage_begin", "install_stage_verified", "Install stage and verify"),
    ("install_stage_verified", "install_activation_committed", "Install activate"),
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


COUNTER_EVENTS = {
    "download_archive_ready": ("network_bytes",),
    "install_stage_verified": ("reused_bytes", "decompressed_bytes",
                               "staged_bytes", "reused_files", "extracted_files"),
}


def collect_counters(lines: list[str]) -> dict[str, dict[str, int]]:
    """Count only verified completed operations; missing samples stay missing."""
    totals: dict[str, dict[str, int]] = defaultdict(dict)
    for raw in lines:
        try:
            row = json.loads(raw)
            if not isinstance(row, dict):
                continue
            session = row.get("session")
            keys = COUNTER_EVENTS.get(row.get("event"))
            if not isinstance(session, str) or not keys:
                continue
            for key in keys:
                value = row.get(key)
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                    totals[session][key] = totals[session].get(key, 0) + value
        except (ValueError, TypeError):
            continue
    return totals


def summarize(lines: list[str]) -> dict[str, object]:
    sessions = collect(lines)
    counters = collect_counters(lines)
    segments: dict[str, dict[str, float | int] | None] = {}
    for start, end, _label in SEGMENTS:
        values = durations_ms(sessions, start, end)
        segments[f"{start}_to_{end}"] = (
            {"n": len(values), "p50_ms": round(median(values), 3),
             "p95_ms": percentile(values, 95),
             "min_ms": min(values), "max_ms": max(values)}
            if values else None
        )
    measured: dict[str, dict[str, float | int]] = {}
    for key in sorted({key for totals in counters.values() for key in totals}):
        values = [counts[key] for counts in counters.values() if key in counts]
        measured[key] = {
            "n": len(values), "p50": median(values),
            "p95": percentile(values, 95), "min": min(values), "max": max(values),
        }
    return {"schema_version": 1, "sessions": len(sessions),
            "segments": segments, "completed_operation_counters": measured}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Display measured startup p50/p95; use same PC and cache state.")
    parser.add_argument("trace", type=Path, help="startup_profile.jsonl collected on Windows")
    parser.add_argument("--json", action="store_true", help="Print a versioned machine-readable report")
    options = parser.parse_args(argv)
    try:
        rows = options.trace.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        parser.error(str(exc))
    data = summarize(rows)
    if options.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True))
        return 0
    print(f"Sessions: {data['sessions']} (missing checkpoints are excluded per segment)")
    for start, end, label in SEGMENTS:
        summary = data["segments"][f"{start}_to_{end}"]
        if summary is None:
            print(f"{label}: NOT RUN / no matching checkpoints")
        else:
            print(f"{label}: n={summary['n']} p50={summary['p50_ms']:.1f}ms p95={summary['p95_ms']:.1f}ms")
    print("Counters from completed operations only (not process-tree totals):")
    for name, summary in data["completed_operation_counters"].items():
        print(f"  {name}: n={summary['n']} p50={summary['p50']} p95={summary['p95']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
