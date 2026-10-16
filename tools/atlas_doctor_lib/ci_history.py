from __future__ import annotations

"""Advisory cost and duplicated-coverage evidence from completed CI runs.

This module never executes tests or changes certification requirements.
"""

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Mapping

MAX_LOG_BYTES = 16_000_000
MAX_JOB_BYTES = 2_000_000
_TEST = re.compile(r"^([^ ]+)Z\s+.*?(test_[A-Za-z0-9_]+ \(([^)]+)\) \.\.\. (?:ok|FAIL|ERROR|skipped[^\r\n]*))")
_SUMMARY = re.compile(r"Ran (\d+) tests? in ([0-9.]+)s")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_TEST_MODULE = re.compile(r"\btests\.test_[A-Za-z0-9_]+\b")


def _timestamp(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def application_log_profile(source: str) -> dict[str, object]:
    """Approximate durations from GitHub timestamped, streamed unittest output.

    Never label completion-to-completion intervals as instrumented test times.
    """
    if len(source.encode("utf-8")) > MAX_LOG_BYTES:
        raise ValueError("Actions job log exceeds size limit")
    lines = _ANSI.sub("", source).splitlines()
    starts = [index for index, value in enumerate(lines) if "-m unittest discover -v -s tests" in value]
    if not starts:
        raise ValueError("No canonical FULL suite marker")
    start = starts[-1]
    ending = next((i for i in range(start + 1, len(lines)) if _SUMMARY.search(lines[i])), -1)
    if ending == -1:
        raise ValueError("FULL suite has no completed unittest summary")
    total, wall_seconds = _SUMMARY.search(lines[ending]).groups()
    events: list[tuple[datetime, str, str]] = []
    for line in lines[start + 1:ending]:
        matched = _TEST.match(line)
        if matched:
            try:
                stamp = _timestamp(matched.group(1) + "Z")
            except ValueError:
                continue
            events.append((stamp, matched.group(2), matched.group(3)))
    if not events:
        raise ValueError("No timestamped unittest verdicts")
    intervals: list[dict[str, object]] = []
    modules: Counter[str] = Counter()
    for previous, current in zip(events, events[1:]):
        delta = (current[0] - previous[0]).total_seconds()
        if delta < 0:
            raise ValueError("Out-of-order Actions log timestamps")
        module = current[2].split(".")[0]
        intervals.append({"test": current[1], "module": module, "approx_seconds": round(delta, 3)})
        modules[module] += delta
    intervals.sort(key=lambda row: (-row["approx_seconds"], row["test"]))
    # A stream/log gap is not evidence of an individual slow test.
    return {
        "schema_version": 1,
        "kind": "atlas_actions_full_unittest_timing_evidence",
        "status": "ADVISORY",
        "test_count_declared": int(total),
        "test_verdict_lines_seen": len(events),
        "intervals_measured": len(intervals),
        "reported_full_suite_seconds": float(wall_seconds),
        "top_20_approx_intervals": intervals[:20],
        "top_modules_by_approx_interval_seconds": [
            {"module": name, "approx_seconds": round(seconds, 3)}
            for name, seconds in modules.most_common(20)
        ],
        "limitations": "GitHub output timestamps measure gaps between reported verdicts, not individual test runtimes; test setup, buffering and other output may contribute. No FULL tests executed by this profiler.",
        "tests_executed": False,
        "full_suite_waived": False,
    }


def actions_job_step_profile(job: dict[str, object]) -> dict[str, object]:
    """Report measured workflow-step intervals from GitHub's existing jobs JSON."""
    if not isinstance(job, dict) or not isinstance(job.get("steps"), list):
        raise ValueError("Expected a GitHub Actions job object with steps")
    values = []
    for step in job["steps"]:
        if not isinstance(step, dict) or not step.get("started_at") or not step.get("completed_at"):
            continue
        duration = (_timestamp(step["completed_at"]) - _timestamp(step["started_at"])).total_seconds()
        if duration < 0:
            raise ValueError("Invalid negative duration")
        values.append({"name": str(step.get("name", "")), "seconds": round(duration, 3),
                       "conclusion": str(step.get("conclusion") or "unknown")})
    return {
        "schema_version": 1, "kind": "atlas_actions_job_step_profile",
        "status": "ADVISORY", "job": str(job.get("name") or ""),
        "conclusion": str(job.get("conclusion") or "unknown"),
        "top_20_steps": sorted(values, key=lambda row: (-row["seconds"], row["name"]))[:20],
        "steps_with_timing": len(values), "tests_executed": False, "full_suite_waived": False,
    }


def duplicate_unittest_modules(workflows: Mapping[str, str]) -> dict[str, object]:
    """Static overlap inventory, never authorization to skip an existing gate."""
    occurrences: dict[str, set[str]] = defaultdict(set)
    for filename, source in sorted(workflows.items()):
        if not filename.endswith((".yml", ".yaml")) or len(source) > 1_000_000:
            raise ValueError("Expected bounded GitHub Actions workflow YAML")
        section = "(unassigned)"
        command = False
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("- name:"):
                section = stripped.split(":", 1)[1].strip().strip("'\"")
                command = False
            if "unittest" in stripped and ("python" in stripped or "py -" in stripped or "-m unittest" in stripped):
                command = True
            if command:
                for module in _TEST_MODULE.findall(stripped):
                    occurrences[module].add(f"{filename}::{section}")
            if stripped.startswith(("- uses:", "- run:")):
                command = False
    duplicates = [
        {"module": name, "owners": sorted(owners), "repetitions": len(owners)}
        for name, owners in occurrences.items() if len(owners) > 1
    ]
    duplicates.sort(key=lambda item: (-item["repetitions"], item["module"]))
    return {
        "schema_version": 1, "kind": "atlas_ci_workflow_duplicate_inventory",
        "status": "ADVISORY", "distinct_explicit_modules": len(occurrences),
        "duplicated_modules": duplicates, "duplicate_module_count": len(duplicates),
        "elisions_authorized": 0, "tests_executed": False,
        "certified": False, "full_suite_waived": False,
        "limitations": "Static references only. A shared test name is not equivalent execution evidence; FULL discovery and all required gates remain mandatory.",
    }


def report_from_files(*, log_path: Path | None = None, job_path: Path | None = None,
                      workflow_paths: list[Path] | None = None) -> dict[str, object]:
    """Read stored evidence without network requests or launching test processes."""
    result: dict[str, object] = {"schema_version": 1, "kind": "atlas_ci_history", "read_only": True}
    if log_path is not None:
        if log_path.stat().st_size > MAX_LOG_BYTES:
            raise ValueError("Oversize log")
        result["full_suite"] = application_log_profile(log_path.read_text(encoding="utf-8-sig"))
    if job_path is not None:
        if job_path.stat().st_size > MAX_JOB_BYTES:
            raise ValueError("Oversize job JSON")
        result["job"] = actions_job_step_profile(json.loads(job_path.read_text(encoding="utf-8-sig")))
    if workflow_paths:
        result["duplicates"] = duplicate_unittest_modules({str(p): p.read_text(encoding="utf-8") for p in workflow_paths})
    if len(result) == 3:
        raise ValueError("At least one existing log, job or workflow required")
    return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actions-log', type=Path)
    parser.add_argument('--job-json', type=Path)
    parser.add_argument('--workflow', action='append', type=Path, default=[])
    args = parser.parse_args(argv)
    try:
        payload = report_from_files(log_path=args.actions_log, job_path=args.job_json,
                                    workflow_paths=args.workflow)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
