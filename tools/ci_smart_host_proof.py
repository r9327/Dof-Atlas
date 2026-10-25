from __future__ import annotations

"""Post-execution HIGH -> SMART proof from GitHub-hosted job/step records.

This is not a release/phase FULL certificate. A successful domain-only PR is
not SMART until independent real Windows resource, Qt and user journeys pass.
No PR-authored benchmark JSON is accepted as a substitute for the host jobs.
"""

import re
from typing import Any

SHA = re.compile(r"^[0-9a-f]{40}$")

# Each measurement is executed and budget-checked by existing pinned workflows.
# The Qt verdict on Ubuntu authenticates real selected Windows UI evidence.
HOST_CONTRACTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "phase8_memory_benchmark / Phase 8 / Staged Memory Benchmark": (
        "windows-latest", (
            "Checkout exact candidate",
            "Measure staged process and process-tree memory",
            "Validate memory evidence shape",
            "Upload memory evidence",
        ),
    ),
    "phase8_preload_benchmark / Phase 8 / Comparable Preload Benchmark": (
        "windows-latest", (
            "Verify exact candidate checkout",
            "Measure base and candidate on the same runner",
            "Validate and compare benchmark evidence",
            "Upload Phase 8 benchmark evidence",
        ),
    ),
    "doctor_ui / Doctor UI / Selected real Qt scenarios": (
        "windows-latest", (
            "Verify immutable candidate and selection before expensive setup",
            "Run one session for the union of selected scenarios",
            "Upload unified UI evidence including failures",
        ),
    ),
    "doctor_ui / Doctor UI / Verdict": (
        "ubuntu-latest", (
            "Reject skipped required job or failed plan",
            "Verify selection, assertions, real PNG and hashes at candidate SHA",
        ),
    ),
    "doctor_certification / Doctor / Windows User Journey Contracts": (
        "windows-latest", (
            "Verify exact candidate",
            "Exercise independent user journey contracts",
            "Publish user journey contract evidence",
        ),
    ),
}
REQUIRED_METRICS = (
    "preload_time", "process_tree_peak", "qt_lifecycle",
    "startup_time", "steady_rss_home",
)


def validate_host_metrics(run: dict[str, Any], jobs: list[dict[str, Any]], *,
                          candidate_sha: str) -> tuple[str, ...]:
    """Require every same-run, same-SHA GitHub Actions host budget verdict."""
    if not isinstance(candidate_sha, str) or not SHA.fullmatch(candidate_sha):
        raise ValueError("Invalid SMART candidate SHA")
    if (run.get("head_sha") != candidate_sha or run.get("event") != "pull_request"
            or type(run.get("id")) is not int):
        raise ValueError("SMART evidence is not an exact-head PR run")
    if not isinstance(jobs, list):
        raise ValueError("Missing SMART host jobs")
    for name, (runner, required) in HOST_CONTRACTS.items():
        matched = [job for job in jobs if job.get("name") == name]
        if len(matched) != 1:
            raise ValueError("Missing/ambiguous SMART host job: " + name)
        job = matched[0]
        if (job.get("run_id") != run["id"]
                or job.get("head_sha") != candidate_sha
                or job.get("status") != "completed"
                or job.get("conclusion") != "success"
                or job.get("labels") != [runner]):
            raise ValueError("SMART host job did not prove required Windows/Qt evidence: " + name)
        steps = job.get("steps")
        if not isinstance(steps, list):
            raise ValueError("Missing SMART host step inventory: " + name)
        for required_name in required:
            rows = [step for step in steps if step.get("name") == required_name]
            if (len(rows) != 1 or rows[0].get("status") != "completed"
                    or rows[0].get("conclusion") != "success"):
                raise ValueError("SMART host budget step missing/failed/skipped: "
                                 + name + " / " + required_name)
    return REQUIRED_METRICS
