"""Select one exact-run Doctor artifact when GitHub Actions jobs are re-run.

A job-only retry keeps successful artifacts from earlier attempts in the SAME
workflow run. Download-artifact's wildcard returns every matching attempt.
Choose the most recent available attempt; do not combine independent runs or
silently accept a missing/ambiguous report from the selected attempt.
"""
from __future__ import annotations

from pathlib import Path


def latest_attempt_report(
    directory: Path,
    *,
    artifact_prefix: str,
    report_name: str,
    run_id: int | str,
    max_attempt: int | str,
) -> Path | None:
    """Return exactly one report from the latest available same-run attempt.

    A retry of *only* the aggregator may have no current-attempt producer
    artifact; in that case the most recent preceding producer attempt is valid.
    The caller still verifies the report's source SHA, content and job status.
    """
    run = str(run_id)
    attempt = str(max_attempt)
    if not run.isdecimal() or int(run) <= 0 or not attempt.isdecimal() or int(attempt) <= 0:
        raise ValueError("Invalid GitHub run/attempt identity")
    if (not artifact_prefix or "/" in artifact_prefix or "\\" in artifact_prefix
            or Path(report_name).name != report_name or not report_name):
        raise ValueError("Invalid Doctor artifact selector")

    directory = Path(directory)
    if not directory.is_dir():
        return None
    prefix = f"{artifact_prefix}-{run}-"
    candidates: list[tuple[int, Path]] = []
    for item in directory.iterdir():
        if not item.is_dir() or item.is_symlink() or not item.name.startswith(prefix):
            continue
        number = item.name[len(prefix):]
        if number.isdecimal() and 1 <= int(number) <= int(attempt):
            candidates.append((int(number), item))
    if not candidates:
        return None

    selected_attempt, selected_dir = max(candidates, key=lambda row: row[0])
    reports = [path for path in selected_dir.rglob(report_name)
               if path.is_file() and not path.is_symlink()]
    if len(reports) != 1:
        raise ValueError(
            f"Doctor artifact {artifact_prefix} attempt {selected_attempt} has "
            f"{len(reports)} {report_name} reports (expected exactly one)"
        )
    return reports[0]
