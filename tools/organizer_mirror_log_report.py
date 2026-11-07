"""Summarize Organizer Miroir diagnostics without exposing window/user data.

Usage: python -m tools.organizer_mirror_log_report --logs logs/atlas.log --accounts 8
Compare separate sessions (same SHA, Windows machine and settings):
    python -m tools.organizer_mirror_log_report --compare 2=atlas_2.log --compare 4=atlas_4.log --compare 6=atlas_6.log --compare 8=atlas_8.log
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
        r"dispatch_to_last_emit_ms=(?P<value>\d+(?:\.\d+)?|NOT_MEASURED) "
        r"cibles=(?P<accounts>\d+)"
    ),
    "click_dispatch_to_worker_ms": re.compile(
        r"\bMiroir clic dispatch_to_worker_ms=(?P<value>\d+(?:\.\d+)?) "
        r"dispatch_to_last_emit_ms=\S+ cibles=(?P<accounts>\d+)"
    ),
    # Key and wheel delivery are measured at dispatch time, independently
    # of worker/runtime duration. Only account-scoped logs are comparable.
    "key_dispatch_to_worker_ms": re.compile(
        r"\bMiroir key: dispatch_to_worker_ms=(?P<value>\d+(?:\.\d+)?) "
        r"dispatch_to_last_emit_ms=\S+ cibles=(?P<accounts>\d+)"
    ),
    "key_dispatch_to_last_emit_ms": re.compile(
        r"\bMiroir key: dispatch_to_worker_ms=\S+ "
        r"dispatch_to_last_emit_ms=(?P<value>\d+(?:\.\d+)?|NOT_MEASURED) "
        r"cibles=(?P<accounts>\d+)"
    ),
    "wheel_dispatch_to_worker_ms": re.compile(
        r"\bMiroir wheel: dispatch_to_worker_ms=(?P<value>\d+(?:\.\d+)?) "
        r"dispatch_to_last_emit_ms=\S+ cibles=(?P<accounts>\d+)"
    ),
    "wheel_dispatch_to_last_emit_ms": re.compile(
        r"\bMiroir wheel: dispatch_to_worker_ms=\S+ "
        r"dispatch_to_last_emit_ms=(?P<value>\d+(?:\.\d+)?|NOT_MEASURED) "
        r"cibles=(?P<accounts>\d+)"
    ),
    "click_worker_ms": re.compile(
        # A worker which emitted no synthetic clicks is not a latency
        # sample for delivered actions; no fast abort may bias p95.
        r"\bMiroir mesures delivery_step: n=[1-9]\d* "
        r"p50_ms=\S+ p95_ms=\S+ p99_ms=\S+ "
        r"total_ms=(?P<value>\d+(?:\.\d+)?) "
        r"envoyés=\d+/(?P<accounts>\d+)"
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
ACTION_COLLISIONS = re.compile(
    r"\bMiroir (clic|molette) collisions_physiques=(\d+) cibles=(\d+)"
)
# Click workers log their terminal outcome even if the UI status callback is
# not mirrored to the diagnostic file. Count this only as a fallback: some
# hosts also log the UI message, and one click must not count twice.
CLICK_WORKER_STATUS = re.compile(
    r"\bMiroir (terminé|partiel|interrompu): envoyés=(\d+)/(\d+)\b"
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
    logged_click_statuses = {"complete": 0, "partial": 0, "interrupted": 0}
    losses = {"clicks": 0, "wheel_ticks": 0}
    per_action_losses = {"click": 0, "wheel": 0}
    previous = (0, 0)
    mismatched_roster_lines = 0
    observed_non_replayed = 0
    profile_changed_after_send = 0
    for line in lines:
        collision = ACTION_COLLISIONS.search(line)
        if collision:
            if int(collision[3]) != accounts:
                mismatched_roster_lines += 1
            else:
                target = "click" if collision[1] == "clic" else "wheel"
                per_action_losses[target] += int(collision[2])
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
        worker_status = CLICK_WORKER_STATUS.search(line)
        if worker_status:
            if int(worker_status[3]) != accounts:
                mismatched_roster_lines += 1
            else:
                outcome = {"terminé": "complete", "partiel": "partial",
                           "interrompu": "interrupted"}[worker_status[1]]
                logged_click_statuses[outcome] += 1
        status = STATUS.search(line)
        if status:
            sent, total = int(status[2]), int(status[3])
            if total != accounts:
                mismatched_roster_lines += 1
            elif status[1] == "interrompu":
                statuses["interrupted"] += 1
            elif (status[1] == "incomplet" or sent != total
                  or "profil modifié après envoi" in line):
                # A complete SendInput count with a changed Organizer profile
                # is not a completed gesture under the original roster.
                statuses["partial"] += 1
            else:
                statuses["complete"] += 1
            if total == accounts and "profil modifié après envoi" in line:
                profile_changed_after_send += 1
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
    return {
        "account_count": accounts,
        "evidence": "LOG_ONLY_NOT_UNITY_CERTIFIED",
        "unity_render_latency": "NOT_MEASURED",
        "cpu_ram": "NOT_MEASURED",
        "metrics": {k: _percentiles(v) for k, v in samples.items()},
        # Status messages may only reach the UI. The engine log provides
        # the same final click outcomes when those messages are absent.
        "actions": statuses if any(statuses.values()) else logged_click_statuses,
        "observed_blocked_physical_inputs": losses,
        "blocked_input_scope": "WHOLE_LOG",
        "observed_blocked_inputs_per_mirror_action": per_action_losses,
        "non_replayed_statuses": observed_non_replayed,
        "profile_changed_after_send": profile_changed_after_send,
        "roster_mismatch_lines": mismatched_roster_lines,
    }



def _comparison_exclusions(report: dict) -> list[str]:
    """Exclude fast-but-lost gestures from apparent responsiveness results."""
    reasons: list[str] = []
    if report["actions"]["partial"] or report["actions"]["interrupted"]:
        reasons.append("PARTIAL_OR_INTERRUPTED_ACTIONS")
    if any(report["observed_blocked_physical_inputs"].values()):
        reasons.append("BLOCKED_PHYSICAL_INPUTS_IN_LOG")
    if any(report["observed_blocked_inputs_per_mirror_action"].values()):
        reasons.append("BLOCKED_PHYSICAL_INPUTS_PER_ACTION")
    if report["profile_changed_after_send"]:
        reasons.append("PROFILE_CHANGED_AFTER_SEND")
    if report["non_replayed_statuses"]:
        reasons.append("UNREPLAYED_PHYSICAL_GESTURES")
    if report["roster_mismatch_lines"]:
        reasons.append("MIXED_OR_MISMATCHED_ROSTERS")
    return reasons


def compare_reports(reports: dict[int, dict]) -> dict:
    """Compare measured p95 to two accounts; never certify gameplay feel."""
    baseline = reports.get(2, {}).get("metrics", {})
    exclusions = {str(count): _comparison_exclusions(report)
                  for count, report in sorted(reports.items())}
    ratios: dict[str, dict[str, float | None]] = {}
    for metric_name in METRIC_PATTERNS:
        baseline_measurement = baseline.get(metric_name)
        current: dict[str, float | None] = {}
        for account_count, report in sorted(reports.items()):
            measure = report["metrics"].get(metric_name)
            # p95 based on one or two samples is too weak for a comparison.
            if (not baseline_measurement or not measure
                    or exclusions.get("2") or exclusions[str(account_count)]
                    or baseline_measurement["n"] < 5 or measure["n"] < 5
                    or baseline_measurement["p95_ms"] <= 0):
                current[str(account_count)] = None
            else:
                current[str(account_count)] = round(
                    measure["p95_ms"] / baseline_measurement["p95_ms"], 3
                )
        ratios[metric_name] = current
    return {
        "evidence": "LOG_ONLY_NOT_UNITY_CERTIFIED",
        "comparison_baseline_accounts": 2,
        "minimum_samples_for_ratio": 5,
        "ratio_exclusion_reasons": exclusions,
        "p95_ratio_vs_2_accounts": ratios,
        "reports": {str(count): result for count, result in sorted(reports.items())},
    }


def _read_report(path: Path, accounts: int, parser: argparse.ArgumentParser) -> dict:
    if not path.is_file() or path.stat().st_size > MAX_LOG_BYTES:
        parser.error(f"log file missing or larger than 64 MiB: {path}")
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        return summarize(stream, accounts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--logs", type=Path)
    group.add_argument("--compare", action="append", metavar="ACCOUNTS=LOGFILE")
    parser.add_argument("--accounts", type=int, choices=ACCOUNTS)
    args = parser.parse_args(argv)
    if args.logs is not None:
        if args.accounts is None:
            parser.error("--accounts is required with --logs")
        data = _read_report(args.logs, args.accounts, parser)
    else:
        if args.accounts is not None:
            parser.error("use --accounts only with --logs")
        reports: dict[int, dict] = {}
        for argument in args.compare:
            count_text, delimiter, path_text = argument.partition("=")
            if not delimiter or not count_text.isascii() or not count_text.isdecimal():
                parser.error("--compare expects ACCOUNTS=LOGFILE")
            count = int(count_text)
            if count not in ACCOUNTS or not path_text or count in reports:
                parser.error("invalid, empty, or duplicate comparison run")
            reports[count] = _read_report(Path(path_text), count, parser)
        if len(reports) < 2:
            parser.error("--compare requires at least two different account counts")
        data = compare_reports(reports)
    print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
