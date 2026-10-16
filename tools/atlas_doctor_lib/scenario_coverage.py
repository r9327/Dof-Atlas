from __future__ import annotations

"""Bounded, read-only evidence of runtime scenarios; never launches an app."""
import json
import re
import subprocess
from pathlib import Path
from typing import Any

MAX_TRACES = 12
MAX_BYTES = 10_000_000
MAX_EVENTS = 50000
MAX_FILES = 128
MAX_SYMBOLS = 256
SYMBOL_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*(?:\.(?:[A-Za-z_][A-Za-z_0-9]*|<locals>))*\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


def observed_executing_python_files(event: dict[str, Any]) -> set[str]:
    """Positive execution only, not arbitrary file references in runtime logs."""
    kind = event.get("type")
    if not isinstance(kind, str) or len(kind) > 80:
        return set()
    sources = [event.get("source")]
    if kind in {"python_call_edge", "python_symbol_call"} or (
        kind == "qt_callback_invoked" and
        event.get("confidence") == "WRAPPED_PYTHON_CALLBACK_ENTERED"
    ):
        sources.append(event.get("target"))
    # Explicitly exclude target of file_open, import_attempt, returned
    # importlib module (which may be cached), and registered Qt callbacks.
    return {
        path for path in sources if (
            isinstance(path, str) and path.endswith(".py")
            and not path.startswith("/") and "\\" not in path
            and all(part not in {"", ".", ".."} for part in path.split("/"))
        )
    }


def observed_entered_symbols(event: dict[str, Any]) -> set[str]:
    """Require a real function/callback entry, not a source mention."""
    kind = event.get("type")
    if kind == "python_symbol_call":
        if event.get("confidence") != "OBSERVED_CALL_ENTRY":
            return set()
    elif kind == "qt_callback_invoked":
        if event.get("confidence") != "WRAPPED_PYTHON_CALLBACK_ENTERED":
            return set()
    else:
        return set()
    target, symbol = event.get("target"), event.get("callee_symbol")
    if (not isinstance(target, str) or not target.endswith(".py")
            or target.startswith("/") or "\\" in target
            or any(segment in {"", ".", ".."} for segment in target.split("/"))
            or not isinstance(symbol, str) or len(symbol) > 180
            or not SYMBOL_RE.fullmatch(symbol)):
        return set()
    return {f"{target}::{symbol}"}


def summarize_scenarios(
    traces: list[dict[str, Any]], *, expected_sha: str,
    required_files: list[str] | None = None,
    required_symbols: list[str] | None = None,
) -> dict[str, Any]:
    if not SHA_RE.fullmatch(expected_sha) or len(traces) > MAX_TRACES:
        raise ValueError("Expected exact 40-character SHA and at most 12 traces")
    required = sorted(set(required_files or []))
    if len(required) > MAX_FILES or any(
        not path.endswith(".py") or path.startswith("/")
        or "\\" in path or ".." in path.split("/")
        for path in required
    ):
        raise ValueError("Required paths must be repository-relative Python files (max 128)")
    required_function_symbols = sorted(set(required_symbols or []))
    if (len(required_function_symbols) > MAX_SYMBOLS or
            any(not isinstance(item, str) or len(item) > 320
                or item.count("::") != 1 or not item.split("::")[0].endswith(".py")
                or item.split("::")[0].startswith("/")
                or "\\" in item.split("::")[0]
                or any(part in {"", ".", ".."} for part in item.split("::")[0].split("/"))
                or not SYMBOL_RE.fullmatch(item.split("::")[1])
                for item in required_function_symbols)):
        raise ValueError("Required symbols must be path.py::qualified_name (maximum 256)")
    confirmed: set[str] = set()
    entered_symbols: set[str] = set()
    event_counts: dict[str, int] = {}
    invalid = 0
    trace_summaries: list[dict[str, Any]] = []
    for i, trace in enumerate(traces):
        events = trace.get("events") if isinstance(trace, dict) else None
        valid = (
            isinstance(trace, dict)
            and trace.get("kind") == "doctor_runtime_observation"
            and trace.get("candidate_sha") == expected_sha
            and trace.get("worktree_clean") is True
            and trace.get("truncated") is False
            and isinstance(events, list) and len(events) <= MAX_EVENTS
            and all(isinstance(row, dict) for row in events)
        )
        if not valid:
            invalid += 1
            trace_summaries.append({"index": i, "status": "STALE_OR_INCOMPLETE",
                                    "events": 0})
            continue
        trace_files: set[str] = set()
        trace_symbols: set[str] = set()
        for row in events:
            kind = row.get("type")
            if not isinstance(kind, str) or len(kind) > 80:
                continue
            event_counts[kind] = event_counts.get(kind, 0) + 1
            trace_files.update(observed_executing_python_files(row))
            trace_symbols.update(observed_entered_symbols(row))
        confirmed.update(trace_files)
        entered_symbols.update(trace_symbols)
        trace_summaries.append({"index": i, "status": "OBSERVED",
                                "events": len(events), "python_files": len(trace_files),
                                "entered_symbols": len(trace_symbols)})
    missing = sorted(set(required) - confirmed)
    observed = sorted(set(required) & confirmed)
    missing_symbols = sorted(set(required_function_symbols) - entered_symbols)
    observed_symbols = sorted(set(required_function_symbols) & entered_symbols)
    return {
        "schema_version": 1, "kind": "doctor_scenario_coverage",
        "status": ("REVIEW" if invalid or not traces or missing or missing_symbols else "OBSERVED"),
        "candidate_sha": expected_sha,
        "traces_checked": len(traces), "traces_invalid": invalid,
        "scenario_results": trace_summaries,
        "required_files": required, "observed_required_files": observed,
        "unobserved_required_files": missing,
        "required_symbols": required_function_symbols,
        "observed_required_symbols": observed_symbols,
        "unobserved_required_symbols": missing_symbols,
        "entered_symbols_count": len(entered_symbols),
        "entered_symbols_examples": sorted(entered_symbols)[:MAX_SYMBOLS],
        "observed_python_files_count": len(confirmed),
        "observed_python_files_examples": sorted(confirmed)[:MAX_FILES],
        "events_by_type": dict(sorted(event_counts.items())),
        "truncated": len(confirmed) > MAX_FILES or len(entered_symbols) > MAX_SYMBOLS,
        "safe_to_delete_unobserved": False,
        "tests_executed": False, "benchmarks_executed": False,
        "limits": "Scenario-specific executed source sites and positive callback entries only; merely opened Python files or registered Qt receivers are not execution coverage. No negative code-death proof or full-app certification.",
    }


def load_scenario_coverage(
    root: Path, paths: list[Path], *, required_files: list[str] | None = None,
    required_symbols: list[str] | None = None,
) -> dict[str, Any]:
    if not 1 <= len(paths) <= MAX_TRACES:
        raise ValueError("Expected 1..12 local Doctor trace files")
    root = root.resolve()
    boundary = (root / ".ai/runtime").resolve()
    result = subprocess.run(["git", "rev-parse", "--verify", "HEAD"],
                            cwd=root, text=True, capture_output=True,
                            timeout=5, check=False)
    sha = result.stdout.strip()
    if result.returncode != 0 or not SHA_RE.fullmatch(sha):
        raise ValueError("Cannot establish current repository HEAD")
    read: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in paths:
        candidate = Path(path)
        selected = candidate if candidate.is_absolute() else root / candidate
        resolved = selected.resolve()
        try:
            if selected.is_symlink() or not resolved.is_relative_to(boundary):
                raise ValueError("Trace outside runtime directory or symlink")
            if not resolved.is_file() or resolved.stat().st_size > MAX_BYTES:
                raise ValueError("Trace missing or larger than 10 MB")
            data = json.loads(resolved.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Trace JSON is not an object")
            read.append(data)
        except (OSError, ValueError, UnicodeError) as exc:
            errors.append(f"{path}: {type(exc).__name__}")
            read.append({})
    result = summarize_scenarios(read, expected_sha=sha, required_files=required_files,
                                 required_symbols=required_symbols)
    result["file_errors"] = errors[:MAX_TRACES]
    result["status"] = "REVIEW" if errors else result["status"]
    return result
