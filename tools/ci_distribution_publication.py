from __future__ import annotations

"""Prove that an upstream Distribution run actually published a release."""

import argparse
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.request


_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_WORKFLOW = "Atlas Windows Distribution"
_WORKFLOW_PATH = ".github/workflows/atlas-windows-distribution.yml"
_PUBLICATION_STEPS = {
    "Windows bundle (gated certification)": "Publish certified stable release",
    "Certified JSON-only update without PyInstaller":
        "Publish verified JSON-only release",
}


def verify_event(payload: dict, *, repository: str) -> tuple[int, str]:
    """Return the trusted upstream run id and exact source SHA."""
    if not _REPO.fullmatch(repository) or not isinstance(payload, dict):
        raise ValueError("Invalid repository or workflow event")
    run = payload.get("workflow_run")
    source_repo = (payload.get("repository") or {}).get("full_name")
    if not isinstance(run, dict):
        raise ValueError("Missing workflow_run event")
    sha = run.get("head_sha")
    if (source_repo != repository
            or (run.get("repository") or {}).get("full_name") != repository
            or (run.get("head_repository") or {}).get("full_name") != repository):
        raise ValueError("Distribution run belongs to another repository")
    if (run.get("name") != _WORKFLOW
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
            or run.get("head_branch") != "main"
            or not isinstance(sha, str) or not _SHA.fullmatch(sha)):
        raise ValueError("No successful exact-main Distribution run")
    path = str(run.get("path") or "")
    if path not in (_WORKFLOW_PATH, f"{_WORKFLOW_PATH}@main") and not path.endswith(
            f"/{_WORKFLOW_PATH}@main"):
        raise ValueError("Unrecognized Distribution workflow source path")
    run_id = run.get("id")
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("Invalid Distribution run identifier")
    return run_id, sha


def classify_publication(jobs_response: dict, *, run_id: int,
                         source_sha: str) -> dict:
    """Classify host job evidence without treating workflow success as publish."""
    if not isinstance(jobs_response, dict):
        raise ValueError("Missing Distribution job evidence")
    jobs = jobs_response.get("jobs")
    total = jobs_response.get("total_count")
    if (not isinstance(jobs, list) or type(total) is not int
            or total != len(jobs) or total > 100):
        raise ValueError("Incomplete Distribution job inventory")

    published: list[tuple[str, str]] = []
    for job in jobs:
        if not isinstance(job, dict) or job.get("name") not in _PUBLICATION_STEPS:
            continue
        if job.get("run_id") not in (None, run_id):
            raise ValueError("Distribution job belongs to another run")
        if job.get("head_sha") not in (None, source_sha):
            raise ValueError("Distribution job belongs to another source SHA")
        if job.get("conclusion") != "success":
            continue
        expected = _PUBLICATION_STEPS[job["name"]]
        matches = [step for step in job.get("steps", [])
                   if isinstance(step, dict) and step.get("name") == expected]
        if len(matches) != 1:
            raise ValueError("Successful release job lacks its publication step")
        if (matches[0].get("status") == "completed"
                and matches[0].get("conclusion") == "success"):
            published.append((job["name"], expected))
        elif matches[0].get("conclusion") != "skipped":
            raise ValueError("Publication step has an invalid successful-run outcome")

    if len(published) > 1:
        raise ValueError("Ambiguous Distribution run published multiple release routes")
    if not published:
        return {
            "schema_version": 1,
            "status": "NO_RELEASE",
            "published": False,
            "source_sha": source_sha,
            "distribution_run_id": run_id,
        }
    job_name, step_name = published[0]
    return {
        "schema_version": 1,
        "status": "PUBLISHED",
        "published": True,
        "source_sha": source_sha,
        "distribution_run_id": run_id,
        "publication_job": job_name,
        "publication_step": step_name,
    }


def _get_jobs(repository: str, run_id: int, token: str) -> dict:
    if not token:
        raise ValueError("Read-only GITHUB_TOKEN is required")
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/jobs?per_page=100",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Dof-Atlas-Distribution-Publication-Proof",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(1_500_001)
    if len(raw) > 1_500_000:
        raise ValueError("Oversized Distribution job evidence")
    return json.loads(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.event_path.is_symlink() or args.event_path.stat().st_size > 2_000_000:
            raise ValueError("Unsafe workflow event evidence")
        payload = json.loads(args.event_path.read_text(encoding="utf-8"))
        run_id, source_sha = verify_event(payload, repository=args.repo)
        report = classify_publication(
            _get_jobs(args.repo, run_id, os.getenv("GITHUB_TOKEN", "")),
            run_id=run_id,
            source_sha=source_sha,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if args.github_output:
            with args.github_output.open("a", encoding="utf-8") as stream:
                stream.write(f"published={str(report['published']).lower()}\n")
                stream.write(f"status={report['status']}\n")
                stream.write(f"source_sha={source_sha}\n")
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError,
            urllib.error.URLError) as exc:
        args.output.unlink(missing_ok=True)
        print("BLOCKED: publication evidence unavailable: " + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
