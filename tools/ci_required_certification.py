from __future__ import annotations

"""GitHub merge certification policy: exact-head, authenticated, fail-closed.

The advisory workflow exposes the final required-check name before the
repository administrator separately enables enforcement in branch rules.
Never trust PR-supplied artifacts or a local file as a successful FULL.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from tools.atlas_integrity import classify_risk
from tools.phase_adaptive_gate import critical_changed

_SHA = re.compile(r"^[0-9a-f]{40}$")
_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_MAX_PROOF_AGE = timedelta(days=7)
_CERT_WORKFLOW = ".github/workflows/phase-certification.yml"
_REQUIRED_FULL_STEPS = (
    "Verify exact certification checkout",
    "Materialize certification LFS fixtures",
    "Materialize local Dofus catalog",
    "Run full Atlas phase certification gate",
    "Enforce phase certification verdict",
)


def classify_merge_route(paths: list[str]) -> dict[str, Any]:
    """A risk route independent of text/metadata supplied by the PR author."""
    paths = sorted(set(paths))
    if not paths or any(not isinstance(p, str) or not p or p.startswith("/") or ".." in p.split("/") for p in paths):
        raise ValueError("Untrusted or empty candidate diff")
    risk = classify_risk(paths)
    trust = sorted(set(critical_changed(paths)) | {
        p for p in paths if (
            p.startswith(".github/rulesets/")
            or p in {"tools/ci_required_certification.py", "tests/test_ci_required_certification.py"}
        )
    })
    docs_only = all(
        p.startswith("docs/") and p.endswith((".md", ".txt"))
        or p in {".ai/context_index.json", "README.md"}
        for p in paths
    )
    full_required = bool(trust) or risk["risk"] in ("HIGH", "CRITICAL")
    return {
        "route": "FULL_REQUIRED" if full_required else "SCOPED",
        "risk": risk["risk"],
        "changed_files": paths,
        "root_of_trust_changes": trust,
        "docs_only": docs_only,
        "reason": "root of trust" if trust else
                  "high/critical risk" if full_required else
                  "docs-only low risk" if docs_only else
                  "ordinary low/medium risk; safe-validation required",
    }


def _parsed_date(value: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("Missing GitHub run timestamp")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.utcoffset() is None:
        raise ValueError("Naive GitHub run timestamp")
    return d.astimezone(timezone.utc)


def validate_full_run(
    run: dict[str, Any],
    jobs: list[dict[str, Any]],
    *,
    candidate_sha: str,
    repo: str,
    now: datetime,
) -> None:
    """Verify *GitHub API* run/job/step records, not user-controlled JSON."""
    if not _SHA.fullmatch(candidate_sha) or not _REPO.fullmatch(repo):
        raise ValueError("Invalid run identity")
    if run.get("head_sha") != candidate_sha:
        raise ValueError("FULL evidence belongs to a different HEAD")
    if run.get("event") not in ("workflow_dispatch", "pull_request"):
        raise ValueError("FULL evidence has an unauthorized event")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise ValueError("FULL workflow did not succeed")
    workflow_path = str(run.get("path") or "")
    if not (workflow_path == _CERT_WORKFLOW
            or f"/{_CERT_WORKFLOW}@" in workflow_path
            or workflow_path.startswith(_CERT_WORKFLOW + "@")):
        raise ValueError("Wrong certification workflow")
    origin = run.get("repository") or {}
    if origin.get("full_name") != repo:
        raise ValueError("Proof belongs to another repository")
    created = _parsed_date(run.get("created_at", ""))
    completed = _parsed_date(run.get("updated_at", ""))
    if created > now + timedelta(minutes=5) or completed > now + timedelta(minutes=5):
        raise ValueError("Proof timestamp is in the future")
    if completed < created or now - completed > _MAX_PROOF_AGE:
        raise ValueError("Stale or inconsistent FULL proof")
    full_jobs = [
        job for job in jobs
        if job.get("name") == "Phase Certification / Full Validation"
    ]
    if len(full_jobs) != 1:
        raise ValueError("Missing or ambiguous real FULL job")
    job = full_jobs[0]
    if job.get("status") != "completed" or job.get("conclusion") != "success":
        raise ValueError("FULL job is not successful")
    if job.get("run_id") != run.get("id"):
        raise ValueError("FULL job belongs to a different run")
    steps = job.get("steps") or []
    for name in _REQUIRED_FULL_STEPS:
        found = [s for s in steps if s.get("name") == name]
        if len(found) != 1 or found[0].get("status") != "completed" or found[0].get("conclusion") != "success":
            raise ValueError(f"Mandatory FULL step failed or skipped: {name}")


def evaluate_merge(
    *,
    candidate_sha: str,
    base_sha: str,
    paths: list[str],
    safe_validation: str,
    repo: str,
    now: datetime,
    runs: list[dict[str, Any]] | None = None,
    jobs_by_run: dict[int, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    if not _SHA.fullmatch(candidate_sha) or not _SHA.fullmatch(base_sha):
        raise ValueError("Expected exact 40-digit candidate/base SHA")
    if candidate_sha == base_sha or not _REPO.fullmatch(repo):
        raise ValueError("Invalid PR candidate identity")
    route = classify_merge_route(paths)
    result: dict[str, Any] = {
        "schema_version": 1,
        "candidate_sha": candidate_sha,
        "base_sha": base_sha,
        "repo": repo,
        "route": route,
        "status": "BLOCKED",
        "full_evidence_run": None,
        "reasons": [],
    }
    if safe_validation != "success":
        result["reasons"].append("Public PR / Safe Validation was not successful")
        return result
    if route["route"] == "SCOPED":
        result["status"] = "PASS_SCOPED_NOT_FULL"
        result["reasons"].append("Exact-HEAD Public PR / Safe Validation passed; FULL not required by route")
        return result
    failures = []
    for run in runs or []:
        try:
            validate_full_run(
                run, (jobs_by_run or {}).get(run.get("id"), []),
                candidate_sha=candidate_sha, repo=repo, now=now,
            )
            result["status"] = "PASS_FULL_AUTHENTICATED"
            result["full_evidence_run"] = run["id"]
            return result
        except (ValueError, TypeError) as exc:
            failures.append(str(exc))
    result["reasons"] = failures[:10] or [
        "FULL_REQUIRED: no successful, fresh, exact-HEAD Phase Certification run with every mandatory stage"
    ]
    return result


def github_get(repo: str, endpoint: str, token: str) -> dict[str, Any]:
    if not token or not _REPO.fullmatch(repo):
        raise ValueError("A valid repository and GITHUB_TOKEN are mandatory")
    url = f"https://api.github.com/repos/{repo}/{endpoint}"
    req = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "dofus-atlas-certification-policy",
    })
    try:
        with urlopen(req, timeout=25) as response:
            return json.load(response)
    except (OSError, HTTPError, URLError, ValueError) as exc:
        raise ValueError(f"Authenticated GitHub evidence unavailable: {exc}") from exc


def retrieve_full_proofs(repo: str, sha: str, token: str) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    endpoint = "actions/workflows/phase-certification.yml/runs?head_sha=" + quote(sha) + "&per_page=100"
    data = github_get(repo, endpoint, token)
    runs = data.get("workflow_runs")
    if not isinstance(runs, list) or int(data.get("total_count", 0)) > 100:
        raise ValueError("Incomplete FULL run inventory (pagination not implemented)")
    jobs: dict[int, list[dict[str, Any]]] = {}
    for run in runs:
        if run.get("head_sha") != sha or run.get("conclusion") != "success":
            continue
        run_id = run.get("id")
        if type(run_id) is not int:
            continue
        rows = github_get(repo, f"actions/runs/{run_id}/jobs?per_page=100", token)
        if not isinstance(rows.get("jobs"), list) or int(rows.get("total_count", 0)) > 100:
            raise ValueError("Incomplete certification job inventory")
        jobs[run_id] = rows["jobs"]
    return runs, jobs


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], check=True, capture_output=True,
                            text=True, encoding="utf-8", timeout=45)
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--safe-result", required=True)
    parser.add_argument("--enforce", choices=("true", "false"), default="false")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    candidate = git("rev-parse", "HEAD")
    if candidate != args.candidate_sha:
        raise ValueError("Checkout differs from PR's exact HEAD")
    paths = git("diff", "--name-only", "--no-renames", args.base_sha, candidate).splitlines()
    route = classify_merge_route(paths)
    runs: list[dict[str, Any]] = []
    jobs: dict[int, list[dict[str, Any]]] = {}
    if route["route"] == "FULL_REQUIRED":
        try:
            runs, jobs = retrieve_full_proofs(args.repo, candidate, os.environ.get("GITHUB_TOKEN", ""))
        except ValueError as exc:
            print(f"FULL proof retrieval failed closed: {exc}")
    result = evaluate_merge(candidate_sha=candidate, base_sha=args.base_sha,
                            paths=paths, safe_validation=args.safe_result, repo=args.repo,
                            now=datetime.now(timezone.utc), runs=runs, jobs_by_run=jobs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
            summary.write(f"## Certification Policy / Merge Gate ({'ENFORCED' if args.enforce == 'true' else 'ADVISORY'})\n")
            summary.write(f"- Exact HEAD: `{candidate}`\n")
            summary.write(f"- Risk route: `{route['route']}` ({route['reason']})\n")
            summary.write(f"- Verdict: `{result['status']}`\n")
            summary.write("- Remote ruleset not modified by this workflow.\n")
    return 0 if result["status"].startswith("PASS_") or args.enforce == "false" else 1


if __name__ == "__main__":
    raise SystemExit(main())
