from __future__ import annotations

"""GitHub-hosted, bounded CI incident repair. NOT a merge certification.

Only one known deterministic fix is supported: regenerate the committed AI
context fingerprint using the repository's existing, trusted ai_context tool.
Never execute Python or shell instructions from candidate PRs or CI logs.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from tools import ai_context

SHA = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
LOG_LIMIT = 2_000_000
INDEX = ".ai/context_index.json"
JOB = "AI Context / Targeted Validation"
STEP = "Verify committed context index"
MARKER = "AI context index: STALE/MISSING"
_API = "https://api.github.com"


def _request(repo: str, endpoint: str, token: str, *, method: str = "GET",
             data: dict[str, Any] | None = None) -> Any:
    if not REPOSITORY.fullmatch(repo) or not endpoint.startswith("/"):
        raise ValueError("Unsafe repository or API path")
    if not token:
        raise ValueError("GitHub token unavailable")
    body = None if data is None else json.dumps(data).encode("utf-8")
    request = Request(
        f"{_API}/repos/{repo}{endpoint}", data=body, method=method,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "atlas-bounded-ci-autofix"},
    )
    with urlopen(request, timeout=20) as response:
        raw = response.read(LOG_LIMIT + 1)
    if len(raw) > LOG_LIMIT:
        raise ValueError("GitHub response too large; manual review")
    if endpoint.endswith("/logs"):
        return raw.decode("utf-8", errors="replace")
    return json.loads(raw)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True, encoding="utf-8", timeout=20, check=False)
    if proc.returncode:
        raise ValueError("Git checkout cannot be independently verified")
    return proc.stdout.strip()


def classify_failure(run: dict[str, Any], jobs: dict[str, Any],
                     pr: dict[str, Any], log: str, *,
                     repo: str, run_id: int, pr_number: int) -> dict[str, Any]:
    """No guessed fixes. Hosted failure, step, immutable SHA and marker required."""
    reasons: list[str] = []
    if (run.get("id") != run_id or run.get("event") != "pull_request"
            or run.get("status") != "completed" or run.get("conclusion") != "failure"
            or (run.get("repository") or {}).get("full_name") != repo):
        reasons.append("UNVERIFIED_FAILED_PR_RUN")
    if (pr.get("number") != pr_number or pr.get("state") != "open"
            or (pr.get("head") or {}).get("repo", {}).get("full_name") != repo
            or (pr.get("base") or {}).get("repo", {}).get("full_name") != repo):
        reasons.append("UNTRUSTED_FORK_OR_CLOSED_PR")
    head = (pr.get("head") or {}).get("sha")
    ref = (pr.get("head") or {}).get("ref")
    if (not isinstance(head, str) or not SHA.fullmatch(head)
            or run.get("head_sha") != head
            or not isinstance(ref, str) or not ref
            or ref in {"main", "master"}):
        reasons.append("HEAD_SHA_OR_BRANCH_MISMATCH")
    all_jobs = jobs.get("jobs", [])
    if (not isinstance(all_jobs, list) or jobs.get("total_count", len(all_jobs)) > 100
            or len(all_jobs) > 100):
        reasons.append("INCOMPLETE_JOB_INVENTORY")
        all_jobs = []
    matched = [job for job in all_jobs if job.get("name") == JOB]
    if len(matched) != 1 or matched[0].get("conclusion") != "failure":
        reasons.append("NO_UNAMBIGUOUS_FAILED_AI_CONTEXT_JOB")
    else:
        steps = matched[0].get("steps", [])
        failing = [s for s in steps if s.get("name") == STEP
                   and s.get("conclusion") == "failure"]
        if len(failing) != 1:
            reasons.append("NO_FAILED_CONTEXT_INDEX_STEP")
    if not isinstance(log, str) or MARKER not in log or len(log) > LOG_LIMIT:
        reasons.append("MISSING_EXACT_STALE_INDEX_LOG_EVIDENCE")
    eligible = not reasons
    return {
        "schema_version": 1,
        "kind": "atlas_ci_failure_autofix_triage",
        "status": "ELIGIBLE_FOR_CONTEXT_INDEX_PROPOSAL" if eligible else "REVIEW_REQUIRED",
        "eligible": eligible,
        "reason_codes": reasons,
        "run_id": run_id, "pr_number": pr_number, "repository": repo,
        "candidate_sha": head if isinstance(head, str) else "",
        "candidate_branch": ref if isinstance(ref, str) else "",
        "allowed_patch_paths": [INDEX] if eligible else [],
        "run_verified_from_github": not ("UNVERIFIED_FAILED_PR_RUN" in reasons),
        "tests_executed_here": False, "full_suite_executed": False,
        "phase_certified": False, "merge_authorized": False,
        "note": "A proposed index regeneration cannot certify or repair other failing jobs.",
    }


def collect(repo: str, token: str, *, run_id: int, pr_number: int) -> dict[str, Any]:
    if run_id < 1 or pr_number < 1:
        raise ValueError("Run and PR identifiers must be positive")
    run = _request(repo, f"/actions/runs/{run_id}", token)
    jobs = _request(repo, f"/actions/runs/{run_id}/jobs?per_page=100", token)
    pr = _request(repo, f"/pulls/{pr_number}", token)
    matching = [item for item in jobs.get("jobs", []) if item.get("name") == JOB]
    log = ""
    if len(matching) == 1 and isinstance(matching[0].get("id"), int):
        log = _request(repo, f"/actions/jobs/{matching[0]['id']}/logs", token)
    return classify_failure(run, jobs, pr, log, repo=repo,
                            run_id=run_id, pr_number=pr_number)


def regenerate_index(candidate: Path, report: dict[str, Any]) -> bytes:
    """Call trusted ai_context on data-only candidate checkout, never import PR code."""
    candidate = candidate.resolve()
    if not report.get("eligible") or report.get("allowed_patch_paths") != [INDEX]:
        raise ValueError("Triage did not authorize bounded index repair")
    sha = report.get("candidate_sha", "")
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ValueError("Candidate has no exact SHA")
    if _git(candidate, "rev-parse", "HEAD") != sha:
        raise ValueError("Candidate checkout is stale")
    if _git(candidate, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("Candidate checkout is not clean")
    dest = candidate / INDEX
    if (dest.is_symlink() or dest.parent.is_symlink()
            or not dest.resolve().is_relative_to(candidate)):
        raise ValueError("Unsafe index path or symlink")
    if ai_context.check_index(candidate):
        raise ValueError("Index already current; diagnosis is stale")
    changed = ai_context.sync_index(candidate)
    if not changed or not ai_context.check_index(candidate):
        raise ValueError("Canonical index regeneration failed")
    changed_paths = _git(candidate, "status", "--porcelain", "--untracked-files=all")
    if changed_paths not in {f" M {INDEX}", f"?? {INDEX}"}:
        raise ValueError("Repair modified unexpected paths")
    raw = dest.read_bytes()
    if len(raw) > 200_000 or raw.decode("utf-8") != ai_context.render_index(
            ai_context.build_index(candidate, ai_context.committed_tree_sha(candidate))):
        raise ValueError("Regenerated index does not match committed tree")
    return raw


def publish(repo: str, token: str, report: dict[str, Any],
            candidate: Path) -> str:
    """Create a new Draft stacked PR; never push/merge the failing PR branch."""
    if not report.get("eligible") or report.get("repository") != repo:
        raise ValueError("Ineligible remediation")
    run_id = report["run_id"]
    pr_number = report["pr_number"]
    # Re-authenticate host state at time of WRITE, not from candidate JSON.
    fresh = collect(repo, token, run_id=run_id, pr_number=pr_number)
    if not fresh["eligible"] or any(fresh[k] != report.get(k)
                                   for k in ("candidate_sha", "candidate_branch", "pr_number")):
        raise ValueError("Host state changed since diagnosis; refuse write")
    index = regenerate_index(candidate, fresh)
    original = _request(repo, f"/contents/{INDEX}?ref={fresh['candidate_sha']}", token)
    branch = (f"ci-autofix/context-{pr_number}-"
              f"{fresh['candidate_sha'][:12]}-{run_id}")
    # GitHub will reject duplicate ref, preventing repeated run dispatch
    # from opening duplicate repair branches or overwriting existing work.
    _request(repo, "/git/refs", token, method="POST",
             data={"ref": f"refs/heads/{branch}", "sha": fresh["candidate_sha"]})
    payload = {
        "message": f"fix(ai): resync context index for PR #{pr_number} (run {run_id})",
        "content": base64.b64encode(index).decode("ascii"),
        "branch": branch,
    }
    if isinstance(original.get("sha"), str):
        payload["sha"] = original["sha"]
    _request(repo, f"/contents/{INDEX}", token, method="PUT", data=payload)
    body = (
        f"Bounded, deterministic GitHub CI repair for #{pr_number}.\n\n"
        f"- Failed run: https://github.com/{repo}/actions/runs/{run_id}\n"
        f"- Exact inspected candidate SHA: {fresh['candidate_sha']}\n"
        f"- Failure evidence: {JOB} / {STEP}; {MARKER}\n"
        f"- Only changed path: {INDEX}\n"
        "- Regenerated by the canonical trusted tools.ai_context implementation, "
        "without importing code or shell from the failing candidate.\n"
        "- Review and merge this stacked Draft into the original PR branch only "
        "after its usual checks; do not merge directly to main.\n"
        "- No claim of tests passing, FULL, Phase certification or merge authorization.\n"
        "- If the source PR moves, abandon this stale proposal and rerun triage.\n"
    )
    created = _request(repo, "/pulls", token, method="POST", data={
        "title": f"fix(ai): resync index for #{pr_number} [CI bounded autofix]",
        "head": branch, "base": fresh["candidate_branch"],
        "body": body, "draft": True, "maintainer_can_modify": True,
    })
    return str(created["html_url"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("triage", "publish"))
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        if not REPOSITORY.fullmatch(repo):
            raise ValueError("No trusted repository identity")
        if args.command == "triage":
            report = collect(repo, token, run_id=args.run_id, pr_number=args.pr_number)
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            if args.github_output:
                with args.github_output.open("a", encoding="utf-8") as output:
                    output.write(f"eligible={str(report['eligible']).lower()}\n")
                    output.write(f"head_sha={report['candidate_sha'] if report['eligible'] else ''}\n")
            print(json.dumps(report, indent=2))
            return 0  # Diagnostic without a recognized repair is advisory.
        if args.candidate is None:
            raise ValueError("Publishing requires exact-SHA checkout")
        report = json.loads(args.report.read_text(encoding="utf-8"))
        if (report.get("run_id") != args.run_id or
                report.get("pr_number") != args.pr_number):
            raise ValueError("Repair report does not match inputs")
        url = publish(repo, token, report, args.candidate)
        print("Draft remediation PR created: " + url)
        return 0
    except (ValueError, HTTPError, URLError, OSError, KeyError,
            json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        # Never print token, raw log, arbitrary candidate code or unbounded API response.
        label = type(exc).__name__
        print(json.dumps({"status": "BLOCKED", "reason": label,
                          "tests_executed_here": False,
                          "phase_certified": False,
                          "merge_authorized": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
