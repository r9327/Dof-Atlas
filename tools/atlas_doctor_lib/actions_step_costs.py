"""Doctor / actual GitHub Actions step timings, per job not across parallel jobs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _seconds(begin: str | None, end: str | None) -> float | None:
    if not begin or not end:
        return None
    try:
        left = datetime.fromisoformat(begin.replace("Z", "+00:00"))
        right = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return max(0.0, (right - left).total_seconds())
    except ValueError:
        return None


def step_costs(jobs: list[dict[str, Any]], *, sha: str, run_id: int) -> dict[str, Any]:
    if not isinstance(run_id, int) or run_id <= 0 or len(sha) != 40:
        raise ValueError("Invalid exact run provenance")
    result: dict[str, Any] = {
        "schema": 1, "kind": "atlas_doctor_actions_step_costs",
        "git_head": sha, "github_run_id": run_id, "jobs": [],
        "status": "OBSERVED", "is_certification": False,
        "denominator_note": (
            "Percentages are wall-clock shares of each independent job's completed GitHub steps. "
            "Parallel job durations overlap; no cross-job or CPU/RAM share is inferred."
        ),
    }
    for job in jobs:
        if job.get("status") != "completed" or not job.get("steps"):
            continue
        group = []
        for step in job["steps"]:
            seconds = _seconds(step.get("started_at"), step.get("completed_at"))
            if seconds is not None:
                group.append({
                    "step": str(step.get("name") or ""), "duration_seconds": round(seconds, 3),
                    "conclusion": step.get("conclusion"),
                })
        duration = sum(row["duration_seconds"] for row in group)
        if duration <= 0:
            continue
        for row in group:
            row["percent_of_job_measured_steps"] = round(
                row["duration_seconds"] * 100.0 / duration, 2)
        result["jobs"].append({
            "job": str(job.get("name") or ""), "job_id": job.get("id"),
            "measured_steps_seconds": round(duration, 3),
            "steps": sorted(group, key=lambda x: -x["duration_seconds"]),
        })
    if not result["jobs"]:
        result["status"] = "NOT_MEASURED"
    return result
