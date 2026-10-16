from __future__ import annotations

"""Independently verify same-SHA GitHub-hosted Phase FULL before reuse on main.

This script does NOT run unittest, waive a failing workflow, declare a new
certification, or reuse across commits. The unique lifecycle contract is
executed separately by the consuming Application CI job.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
PHASE_JOB = "Phase Certification / Full Validation"
REQUIRED_STEPS = (
    "Verify exact certification checkout",
    "Resolve adaptive Doctor route on exact SHA",
    "Materialize certification LFS fixtures",
    "Materialize local Dofus catalog",
    "Run full Atlas phase certification gate",
    "Compare Doctor plan with actual exact-SHA FULL evidence",
    "Enforce phase certification verdict",
)


def verify_event(payload: dict, *, repository: str, head_sha: str) -> int:
    if not REPO.fullmatch(repository) or not SHA.fullmatch(head_sha):
        raise ValueError("Invalid exact GitHub repository or SHA")
    if not isinstance(payload, dict):
        raise ValueError("Missing trusted workflow_run event")
    run = payload.get("workflow_run")
    if not isinstance(run, dict):
        raise ValueError("Not a workflow_run event")
    if ((payload.get("repository") or {}).get("full_name") != repository
            or (run.get("repository") or {}).get("full_name") != repository
            or (run.get("head_repository") or {}).get("full_name") != repository):
        raise ValueError("Workflow source repository differs from trusted main")
    if (run.get("name") != "Phase Certification"
            or run.get("event") != "push"
            or run.get("head_branch") != "main"
            or run.get("head_sha") != head_sha
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"):
        raise ValueError("No completed, passing exact-SHA main push Phase FULL")
    path = str(run.get("path") or "")
    if (not path.endswith(".github/workflows/phase-certification.yml@main")
            and path != ".github/workflows/phase-certification.yml"):
        raise ValueError("Unrecognized Phase workflow source path")
    run_id = run.get("id")
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("Invalid host Phase run identifier")
    return run_id


def verify_jobs(jobs_response: dict, *, head_sha: str) -> dict:
    if not isinstance(jobs_response, dict):
        raise ValueError("Missing host job result")
    jobs = jobs_response.get("jobs")
    if (not isinstance(jobs, list) or jobs_response.get("total_count") != len(jobs)
            or not jobs):
        raise ValueError("Expected complete Doctor workflow jobs response")
    full_jobs = [j for j in jobs if isinstance(j, dict) and j.get("name") == PHASE_JOB]
    if len(full_jobs) != 1:
        raise ValueError("Missing or ambiguous Phase FULL job")
    job = full_jobs[0]
    if (not isinstance(job, dict) or job.get("name") != PHASE_JOB
            or job.get("status") != "completed"
            or job.get("conclusion") != "success"
            or job.get("head_sha") not in (None, head_sha)):
        raise ValueError("Phase FULL job was not independently successful")
    rows = job.get("steps")
    if not isinstance(rows, list):
        raise ValueError("Phase FULL step evidence missing")
    steps = {}
    for step in rows:
        if not isinstance(step, dict):
            raise ValueError("Invalid step evidence")
        name = step.get("name")
        if not isinstance(name, str) or name in steps:
            raise ValueError("Duplicate or malformed step evidence")
        steps[name] = step.get("conclusion")
    full_executed = steps.get("Run full Atlas phase certification gate") == "success"
    tree_equivalent_pr_full = (
        steps.get("Check merged PR FULL provenance") == "success"
        and steps.get("Run full Atlas phase certification gate") == "skipped"
        and steps.get("Resolve adaptive Doctor route on exact SHA") == "skipped"
        and steps.get("Execute and verify exact-SHA targeted modules") == "skipped"
    )
    if tree_equivalent_pr_full:
        proof_steps = ("Verify exact certification checkout",
                       "Check merged PR FULL provenance",
                       "Enforce phase certification verdict")
        if (any(steps.get(x) != "success" for x in proof_steps)
                or steps.get("Resolve adaptive Doctor route on exact SHA") != "skipped"
                or steps.get("Materialize certification LFS fixtures") != "skipped"
                or steps.get("Materialize local Dofus catalog") != "skipped"
                or steps.get("Compare Doctor plan with actual exact-SHA FULL evidence") != "skipped"):
            raise ValueError("Incomplete attested identical-tree PR FULL reuse")
    elif not full_executed:
        required_scoped = (
            "Verify exact certification checkout",
            "Resolve adaptive Doctor route on exact SHA",
            "Execute and verify exact-SHA targeted modules",
            "Enforce phase certification verdict",
        )
        if (steps.get("Run full Atlas phase certification gate") != "skipped"
                or any(steps.get(step) != "success" for step in required_scoped)
                or steps.get("Materialize certification LFS fixtures") != "skipped"
                or steps.get("Materialize local Dofus catalog") != "skipped"):
            raise ValueError("Incomplete or counterfeit Doctor scoped main result")
    else:
        for step in REQUIRED_STEPS:
            if steps.get(step) != "success":
                raise ValueError(f"Mandatory Phase FULL evidence absent/failed: {step}")
        if steps.get("Execute and verify exact-SHA targeted modules") == "success":
            raise ValueError("Scoped execution cannot impersonate canonical FULL")
    return {
        "kind": ("main_application_tree_equivalent_pr_full" if tree_equivalent_pr_full
                 else "main_application_reused_phase_full" if full_executed
                 else "main_application_verified_scoped"),
        "candidate_sha": head_sha,
        "phase_job": PHASE_JOB,
        "independent_host_steps": list(REQUIRED_STEPS),
        "phase_full_host_verified": full_executed or tree_equivalent_pr_full,
        "application_full_suite_executed": False,
        "application_unique_lifecycle_pending": full_executed or tree_equivalent_pr_full,
        "cross_sha_reuse": tree_equivalent_pr_full,
        "git_tree_equivalence_host_attested": tree_equivalent_pr_full,
        "phase_certified_by_this_script": False,
    }


def _get_jobs(repo: str, run_id: int, token: str) -> dict:
    if not token:
        raise ValueError("Read-only GITHUB_TOKEN required; cannot reuse FULL")
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Dof-Atlas-Main-Phase-Full-Proof",
    })
    with urllib.request.urlopen(req, timeout=20) as reply:
        raw = reply.read(1_500_001)
    if len(raw) > 1_500_000:
        raise ValueError("Oversized GitHub host jobs evidence")
    return json.loads(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            args.output.unlink()
        if args.event_path.is_symlink() or args.event_path.stat().st_size > 2_000_000:
            raise ValueError("Unsafe workflow event evidence")
        event = json.loads(args.event_path.read_text(encoding="utf-8"))
        run_id = verify_event(event, repository=args.repo, head_sha=args.candidate_sha)
        checked_out = subprocess.run(
            ["git", "rev-parse", "HEAD"], text=True, capture_output=True,
            check=True, timeout=15,
        ).stdout.strip()
        if checked_out != args.candidate_sha:
            raise ValueError("Checkout does not match certified exact SHA")
        report = verify_jobs(
            _get_jobs(args.repo, run_id, os.getenv("GITHUB_TOKEN", "")),
            head_sha=args.candidate_sha,
        )
        report["phase_run_id"] = run_id
        report["repository"] = args.repo
        report["phase_run_url"] = (
            f"https://github.com/{args.repo}/actions/runs/{run_id}"
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError,
            urllib.error.URLError, json.JSONDecodeError) as exc:
        args.output.unlink(missing_ok=True)
        print("BLOCKED: no reusable authenticated exact-SHA Phase FULL: "
              + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
