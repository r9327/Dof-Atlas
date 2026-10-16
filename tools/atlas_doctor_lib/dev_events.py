from __future__ import annotations

"""Fast, explicit development-event hints; never an unattended watcher.

Pre-commit uses only the *staged* Git diff. Save mode accepts explicit
paths from an editor hook. Push mode is already handled by Atlas Integrity and
GitHub CI; Doctor can describe its impact without rerunning these gates.
"""
import subprocess
from pathlib import Path
from typing import Any

from tools import ai_context

MAX_PATHS = 80
MAX_TESTS = 24


def _git(root: Path, *arguments: str) -> bytes:
    try:
        command = subprocess.run(
            ["git", *arguments], cwd=root, check=False, capture_output=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Cannot read Git change event: {exc}") from exc
    if command.returncode:
        raise RuntimeError("Cannot read Git change event (Git exit code "
                           + str(command.returncode) + ")")
    return command.stdout


def _normalized(relative: str) -> str:
    relative = relative.replace("\\", "/")
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts:
        raise ValueError("Expected a repository-relative path")
    return path.as_posix()


def _name_status_z(raw: bytes) -> list[dict[str, str]]:
    """Git -z emits status NUL path [NUL second path for R/C]."""
    fields = [x.decode("utf-8", errors="replace") for x in raw.split(b"\0") if x]
    results: list[dict[str, str]] = []
    pos = 0
    while pos < len(fields):
        status = fields[pos]
        pos += 1
        if not status or status[0] not in "ACDMRTUXB" or pos >= len(fields):
            raise ValueError("Unexpected Git diff status format")
        former = _normalized(fields[pos])
        pos += 1
        current = former
        if status[0] in "RC":
            if pos >= len(fields):
                raise ValueError("Incomplete Git rename/copy event")
            current = _normalized(fields[pos])
            pos += 1
        results.append({"status": status, "before": former, "path": current})
    return results


def dev_event(
    root: Path, event: str, *, paths: list[str] | None = None,
    base_ref: str | None = None,
) -> dict[str, Any]:
    """Return bounded change/test hints; no Graphify rebuild, tests or worker."""
    if event not in {"pre-commit", "save", "push"}:
        raise ValueError("Unsupported developer event")
    root = root.resolve()
    if event == "save":
        if not paths:
            raise ValueError("Save event requires changed paths")
        changes = [{"status": "M", "before": _normalized(p),
                    "path": _normalized(p)} for p in paths]
    elif event == "pre-commit":
        changes = _name_status_z(_git(
            root, "diff", "--cached", "--name-status", "-z", "--find-renames", "HEAD", "--",
        ))
    else:
        if not base_ref:
            raise ValueError("Push event requires --base-ref")
        # Do not allow an arbitrary -option to be passed into Git.
        if base_ref.startswith("-"):
            raise ValueError("Invalid base ref")
        base_sha = _git(root, "rev-parse", "--verify", base_ref + "^{commit}").decode().strip()
        changes = _name_status_z(_git(
            root, "diff", "--name-status", "-z", "--find-renames",
            base_sha + "...HEAD", "--",
        ))
    unique = sorted({row["path"] for row in changes})
    deltas = [row for row in changes if row["status"].startswith(("D", "R"))]
    truncated = len(unique) > MAX_PATHS
    selected = unique[:MAX_PATHS]
    tests = ai_context.recommended_tests(root, selected)
    return {
        "schema_version": 1, "kind": "doctor_dev_event",
        "event": event, "read_only": True, "status": "REVIEW" if deltas or truncated else "READY",
        "changed_count": len(unique), "changed_files": selected,
        "source_structural_changes": deltas[:MAX_PATHS],
        "source_structural_total": len(deltas),
        "truncated": truncated, "recommended_tests": tests[:MAX_TESTS],
        "tests_truncated": len(tests) > MAX_TESTS,
        "automatic_tests_executed": False, "graph_rebuilt": False,
        "next_action": "Review structural consumers in Doctor change-plan before deletion/rename."
        if deltas else "Proceed with the existing policy-required targeted validation.",
        "limits": "Hints only; Git staged content may differ from worktree. No code-deadness proof.",
    }
