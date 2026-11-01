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
    ("launcher_entry", "home_first_paint", "Launcher entry -> first Home paint"),
    ("atlas_window_create_begin", "atlas_window_created", "AtlasWindow construction"),
    ("install_stage_begin", "install_stage_verified", "Install stage and verify"),
    ("install_stage_verified", "install_activation_committed", "Install activate"),
    ("install_relocation_begin", "install_relocation_committed", "Runtime relocation"),
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
    "install_relocation_committed": ("copied_bytes",),
    "download_archive_ready": ("network_bytes",),
    "multipart_archive_ready": ("network_bytes", "cached_bytes"),
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
             "p95_ms": percentile(values, 95), "p99_ms": percentile(values, 99),
             "min_ms": min(values), "max_ms": max(values)}
            if values else None
        )
    measured: dict[str, dict[str, float | int]] = {}
    for key in sorted({key for totals in counters.values() for key in totals}):
        values = [counts[key] for counts in counters.values() if key in counts]
        measured[key] = {
            "n": len(values), "p50": median(values),
            "p95": percentile(values, 95), "p99": percentile(values, 99),
            "min": min(values), "max": max(values),
        }
    return {"schema_version": 1, "sessions": len(sessions),
            "segments": segments, "completed_operation_counters": measured}


def compare_traces(baseline: list[str], candidate: list[str],
                   *, min_samples: int = 5) -> dict[str, object]:
    """Preliminary p50/p95 alerts, never statistical or Windows certification.

    Missing/low-N baselines remain explicitly inconclusive. A negative change
    means the candidate was faster; no test can declare an unmeasured PASS.
    """
    first, second = collect(baseline), collect(candidate)
    segments: dict[str, dict[str, object]] = {}
    for start, end, _ in SEGMENTS:
        name = f"{start}_to_{end}"
        old, new = durations_ms(first, start, end), durations_ms(second, start, end)
        result: dict[str, object] = {"baseline_n": len(old), "candidate_n": len(new),
                                     "status": "INSUFFICIENT_EVIDENCE"}
        if len(old) >= min_samples and len(new) >= min_samples:
            old_p50, new_p50 = median(old), median(new)
            old_p95, new_p95 = percentile(old, 95), percentile(new, 95)
            old_p99, new_p99 = percentile(old, 99), percentile(new, 99)
            if old_p50 > 0 and old_p95 > 0:
                p50_pct = round((new_p50 - old_p50) * 100 / old_p50, 2)
                p95_pct = round((new_p95 - old_p95) * 100 / old_p95, 2)
                # P99 is diagnostic only for small samples. The existing 5%
                # regression alert remains based on P50/P95, not a noisy max.
                p99_pct = (round((new_p99 - old_p99) * 100 / old_p99, 2)
                           if old_p99 > 0 else None)
                result.update(
                    baseline_p50_ms=old_p50, candidate_p50_ms=new_p50,
                    baseline_p95_ms=old_p95, candidate_p95_ms=new_p95,
                    baseline_p99_ms=old_p99, candidate_p99_ms=new_p99,
                    p50_change_percent=p50_pct, p95_change_percent=p95_pct,
                    p99_change_percent=p99_pct,
                    status=("INVESTIGATE_OVER_5_PERCENT"
                            if max(p50_pct, p95_pct) > 5 else "NO_5_PERCENT_ALERT"),
                )
        segments[name] = result
    return {"schema_version": 1, "min_samples": min_samples,
            "kind": "advisory_comparison_not_certification", "segments": segments}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Display measured startup p50/p95; use same PC and cache state.")
    parser.add_argument("trace", type=Path, help="startup_profile.jsonl collected on Windows")
    parser.add_argument("--json", action="store_true", help="Print a versioned machine-readable report")
    parser.add_argument("--baseline", type=Path, help="Compare against a separate baseline trace (same PC/scenario)")
    options = parser.parse_args(argv)
    try:
        rows = options.trace.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        parser.error(str(exc))
    data = summarize(rows)
    if options.baseline is not None:
        try:
            baseline_rows = options.baseline.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            parser.error(str(exc))
        data["comparison"] = compare_traces(baseline_rows, rows)
    if options.json:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True))
        return 0
    print(f"Sessions: {data['sessions']} (missing checkpoints are excluded per segment)")
    for start, end, label in SEGMENTS:
        summary = data["segments"][f"{start}_to_{end}"]
        if summary is None:
            print(f"{label}: NOT RUN / no matching checkpoints")
        else:
            print(f"{label}: n={summary['n']} p50={summary['p50_ms']:.1f}ms p95={summary['p95_ms']:.1f}ms p99={summary['p99_ms']:.1f}ms")
    if "comparison" in data:
        print("Baseline comparison (advisory, same PC/scenario required):")
        for name, value in data["comparison"]["segments"].items():
            print(f"  {name}: {value['status']} (n={value['baseline_n']}/{value['candidate_n']})")
    print("Counters from completed operations only (not process-tree totals):")
    for name, summary in data["completed_operation_counters"].items():
        print(f"  {name}: n={summary['n']} p50={summary['p50']} p95={summary['p95']} p99={summary['p99']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
