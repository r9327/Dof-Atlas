from __future__ import annotations

"""Read-only historical test costs from existing Atlas Integrity reports."""
import json
import math
from pathlib import Path
from statistics import median
from typing import Any

MAX_REPORTS = 8
MAX_REPORT_BYTES = 4_000_000
MAX_COMMANDS = 256


def suggest_targeted_test_order(required_groups: list[str], cost_evidence: dict[str, Any]) -> dict[str, Any]:
    """Non-binding cheap-first ordering, never a smaller test floor."""
    if not isinstance(required_groups, list) or len(required_groups) > 64:
        raise ValueError("Expected at most 64 required test groups")
    groups = list(dict.fromkeys(g for g in required_groups if isinstance(g, str) and 0 < len(g) <= 100))
    durations: dict[str, float] = {}
    for row in cost_evidence.get("groups", [])[:256]:
        if not isinstance(row, dict):
            continue
        name, seconds = row.get("group"), row.get("median_seconds")
        if (isinstance(name, str) and isinstance(seconds, (int, float))
                and not isinstance(seconds, bool) and math.isfinite(seconds) and seconds >= 0
                and isinstance(row.get("samples"), int) and row["samples"] > 0):
            durations[name] = float(seconds)
    ranked = sorted(enumerate(groups), key=lambda x: (x[1] not in durations,
                    durations.get(x[1], 0), x[0]))
    ordered = [name for _, name in ranked]
    return {
        "status": "ADVISORY" if cost_evidence.get("status") == "PASS" and durations else "INSUFFICIENT_COST_EVIDENCE",
        "requested_groups": groups, "suggested_order": ordered,
        "historical_order_costs_seconds": [{"group": name, "median_seconds": durations.get(name)}
                                           for name in ordered],
        "historically_measured_groups": sum(name in durations for name in groups),
        "unknown_cost_groups": [name for name in groups if name not in durations],
        "full_suite_waived": False, "tests_executed": False,
        "limits": "Ordering is advisory and costs historical; unchanged required groups, no predicted runtime or skipped certification.",
    }


def test_cost_report(root: Path, report_paths: list[Path]) -> dict[str, Any]:
    root = root.resolve()
    boundary = (root / ".ai" / "runtime").resolve()
    if not 1 <= len(report_paths) <= MAX_REPORTS:
        raise ValueError(f"Expected 1..{MAX_REPORTS} existing reports")
    observations: dict[str, list[float]] = {}
    refs: list[dict[str, Any]] = []
    errors: list[str] = []
    reused_count = failed_count = 0
    for path in report_paths:
        requested = Path(path)
        original = requested if requested.is_absolute() else root / requested
        selected = original.resolve()
        if original.is_symlink() or not selected.is_relative_to(boundary):
            errors.append(f"{path}: report must stay inside .ai/runtime")
            continue
        try:
            if not selected.is_file() or selected.stat().st_size > MAX_REPORT_BYTES:
                raise ValueError("report missing or exceeds 4 MB")
            report = json.loads(selected.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise ValueError("report payload must be an object")
            head = report.get("head")
            commands = report.get("commands")
            if (not isinstance(head, str) or len(head) != 40
                    or not all(char in "0123456789abcdef" for char in head.lower())
                    or not isinstance(commands, list)
                    or len(commands) > MAX_COMMANDS):
                raise ValueError("invalid SHA or command budget")
        except (OSError, ValueError, UnicodeError) as exc:
            errors.append(f"{path}: {type(exc).__name__}")
            continue
        used = 0
        for row in commands:
            if not isinstance(row, dict):
                errors.append(f"{path}: malformed command")
                continue
            if row.get("evidence_reused_from"):
                reused_count += 1
                continue
            seconds = row.get("duration_seconds")
            name = row.get("group")
            if (not isinstance(name, str) or not name or len(name) > 100
                    or not isinstance(seconds, (int, float))
                    or isinstance(seconds, bool) or not math.isfinite(seconds)
                    or seconds < 0 or seconds > 86400
                    or not isinstance(row.get("exit_code"), int)):
                errors.append(f"{path}: incomplete command duration")
                continue
            if row["exit_code"] != 0:
                failed_count += 1
                continue
            observations.setdefault(name, []).append(float(seconds))
            used += 1
        refs.append({"path": selected.relative_to(root).as_posix(),
                     "head": head, "mode": report.get("mode"),
                     "successful_executed_commands": used})
    groups = [{
        "group": name, "samples": len(values),
        "median_seconds": round(median(values), 3),
        "min_seconds": round(min(values), 3),
        "max_seconds": round(max(values), 3),
        "historical_observation_only": True,
    } for name, values in observations.items()]
    groups.sort(key=lambda item: (-item["median_seconds"], item["group"]))
    return {
        "schema_version": 1, "kind": "doctor_test_cost_evidence",
        "status": "REVIEW" if errors or not refs or not groups else "PASS",
        "reports": refs, "groups": groups,
        "reused_full_suite_commands_excluded": reused_count,
        "failed_commands_excluded": failed_count,
        "errors": errors[:40], "truncated": len(errors) > 40,
        "read_only": True, "tests_executed": False, "benchmarks_executed": False,
        "limits": "At most 8 local reports, 4 MB each and 256 commands/report. Only real successful command durations; historical samples are not predictions or certification.",
    }
