"""Summarize Organizer Miroir diagnostics without exposing window/user data.

Usage: python -m tools.organizer_mirror_log_report --logs logs/atlas.log --accounts 8
The result is log evidence only; it cannot certify Windows/Unity rendering.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from collections.abc import Iterable

MAX_LOG_BYTES = 64 * 1024 * 1024
ACCOUNTS = (1, 2, 4, 6, 8)

# Existing Atlas senders report different timings. Do not mix these into a
# fictitious end-to-end latency: a SendInput event is not a Unity frame.
METRIC_PATTERNS = {
    "click_pointer_block_ms": re.compile(
        r"\bMiroir blocage_souris_ms=(?P<value>\d+(?:\.\d+)?) cibles=(?P<accounts>\d+)"
    ),
    "wheel_pointer_block_ms": re.compile(
        r"\bMiroir molette blocage_souris_ms=(?P<value>\d+(?:\.\d+)?) cibles=(?P<accounts>\d+)"
    ),
    "click_dispatch_to_last_emit_ms": re.compile(
        r"\bMiroir clic dispatch_to_worker_ms=\S+ "
        r"dispatch_to_last_emit_ms=(?P<value>\d+(?:\.\d+)?|NOT_MEASURED)"
    ),
    "key_worker_ms": re.compile(
        r"\bMiroir key: envoyés=\d+/(?P<accounts>\d+) worker_total_ms=(?P<value>\d+(?:\.\d+)?)"
    ),
    "wheel_worker_ms": re.compile(
        r"\bMiroir wheel: envoyés=\d+/(?P<accounts>\d+) worker_total_ms=(?P<value>\d+(?:\.\d+)?)"
    ),
}
STATUS = re.compile(
    r"\bMiroir(?: (?:Clavier|Molette))?"
    r"(?: (interrompu|incomplet))? : (\d+)/(\d+) fenêtres"
)
BLOCKED_COUNTERS = re.compile(
    r"Organizer entrées physiques bloquées: clics=(\d+) molettes=(\d+)"
)
STOP_COUNTERS = re.compile(
    r"Organizer hooks arrêtés: clics bloqués=(\d+) molettes bloquées=(\d+)"
)


def _percentiles(values: list[float]) -> dict[str, float | int] | None:
    """Nearest-rank, matching Atlas' canonical telemetry quantile contract."""
    if not values:
        return None
    ordered = sorted(values)
    return {
        "n": len(ordered),
        **{
            f"p{pct}_ms": round(ordered[math.ceil(len(ordered) * pct / 100) - 1], 3)
            for pct in (50, 95, 99)
        },
    }


def summarize(lines: Iterable[str], accounts: int) -> dict:
    if accounts not in ACCOUNTS:
        raise ValueError("accounts must be one of 1, 2, 4, 6, 8")
    samples = {key: [] for key in METRIC_PATTERNS}
    statuses = {"complete": 0, "partial": 0, "interrupted": 0}
    losses = {"clicks": 0, "wheel_ticks": 0}
    previous = (0, 0)
    mismatched_roster_lines = 0
    observed_non_replayed = 0
    for line in lines:
        match = BLOCKED_COUNTERS.search(line) or STOP_COUNTERS.search(line)
        if match:
            counts = (int(match[1]), int(match[2]))
            for i, name in enumerate(("clicks", "wheel_ticks")):
                # Counters reset on hook restart; a lower number starts a new
                # session. Only observed losses are counted, never invented.
                losses[name] += counts[i] if counts[i] < previous[i] else counts[i] - previous[i]
            previous = counts
            if STOP_COUNTERS.search(line):
                previous = (0, 0)
        status = STATUS.search(line)
        if status:
            sent, total = int(status[2]), int(status[3])
            if total != accounts:
                mismatched_roster_lines += 1
            elif status[1] == "interrompu":
                statuses["interrupted"] += 1
            elif status[1] == "incomplet" or sent != total:
                statuses["partial"] += 1
            else:
                statuses["complete"] += 1
            if total == accounts and "geste physique non rejoué" in line:
                observed_non_replayed += 1
        for name, pattern in METRIC_PATTERNS.items():
            metric = pattern.search(line)
            if metric is None or metric.group("value") == "NOT_MEASURED":
                continue
            observed_accounts = metric.groupdict().get("accounts")
            if observed_accounts is not None and int(observed_accounts) != accounts:
                mismatched_roster_lines += 1
                continue
            duration = float(metric.group("value"))
            if math.isfinite(duration) and duration >= 0:
                samples[name].append(duration)
    if mismatched_roster_lines:
        # Click dispatch logs lack an account count; never attribute their
        # timing to one roster if the file contains mixed-size sessions.
        samples["click_dispatch_to_last_emit_ms"].clear()
    return {
        "account_count": accounts,
        "evidence": "LOG_ONLY_NOT_UNITY_CERTIFIED",
        "unity_render_latency": "NOT_MEASURED",
        "cpu_ram": "NOT_MEASURED",
        "metrics": {k: _percentiles(v) for k, v in samples.items()},
        "actions": statuses,
        "observed_blocked_physical_inputs": losses,
        "blocked_input_scope": "WHOLE_LOG",
        "non_replayed_statuses": observed_non_replayed,
        "roster_mismatch_lines": mismatched_roster_lines,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logs", required=True, type=Path)
    parser.add_argument("--accounts", required=True, type=int, choices=ACCOUNTS)
    args = parser.parse_args(argv)
    if not args.logs.is_file() or args.logs.stat().st_size > MAX_LOG_BYTES:
        parser.error("log file missing or larger than 64 MiB")
    with args.logs.open("r", encoding="utf-8", errors="replace") as stream:
        data = summarize(stream, args.accounts)
    print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
