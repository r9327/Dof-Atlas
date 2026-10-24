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
from tools.atlas_doctor_lib.ci_tooling_scope import eligible as tooling_eligible
from tools.atlas_doctor_lib.high_smart_scope import eligible as high_smart_eligible

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


def classify_merge_route(paths: list[str], *, root: Path | None = None, base_sha='',
                         deleted_paths: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    """A risk route independent of text/metadata supplied by the PR author."""
    paths = sorted(set(paths))
    if not paths or any(not isinstance(p, str) or not p or p.startswith("/") or ".." in p.split("/") for p in paths):
        raise ValueError("Untrusted or empty candidate diff")
    deleted = sorted(set(deleted_paths))
    if any(path not in paths for path in deleted):
        raise ValueError('Deleted paths must occur in the candidate diff')
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
    tooling_only = tooling_eligible(paths, deleted=deleted, root=root, base_sha=base_sha)
    bounded_high = (
        not tooling_only and not trust and risk["risk"] == "HIGH"
        and high_smart_eligible(root, paths, deleted=deleted)
    )
    full_required = bool(deleted) or (not tooling_only and (
        bool(trust) or risk["risk"] == "CRITICAL"
        or (risk["risk"] == "HIGH" and not bounded_high)
    ))
    return {
        "route": "FULL_REQUIRED" if full_required else "SMART" if bounded_high else "SCOPED",
        "risk": risk["risk"],
        "changed_files": paths,
        "deleted_files": deleted,
        "root_of_trust_changes": trust,
        "docs_only": docs_only,
        "tooling_only": tooling_only,
        "smart_requires_host_proof": bounded_high,
        "reason": "bounded CI contracts; Safe Validation must pass; not Phase certification" if tooling_only else
                  "bounded HIGH SMART; require exact-SHA host-scoped execution, not FULL" if bounded_high else
                  "removed or replaced path" if deleted else
                  "root of trust" if trust else
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


def _require_authenticated_run_state(
    run: dict[str, Any], jobs: list[dict[str, Any]],
) -> None:
    """Require the independent Safe Validation from the same PR run.

    While this merge gate is evaluating the current run, its final outcome
    cannot be known yet. A completed run can be accepted only after success,
    but even a completed SUCCESS may contain skipped jobs and must prove the
    mandatory public validation independently. Manual FULL runs keep their
    separate step attestation.
    """
    status = run.get("status")
    if status == "completed":
        if run.get("conclusion") != "success":
            raise ValueError("Certification workflow did not succeed")
    elif (status != "in_progress"
          or run.get("conclusion") is not None
          or run.get("event") != "pull_request"):
        raise ValueError("Certification workflow is neither successful nor attestable")
    if run.get("event") != "pull_request":
        return
    matched = [job for job in jobs
               if job.get("name") == "Public PR / Safe Validation"]
    if len(matched) != 1:
        raise ValueError("Missing or ambiguous successful independent Safe Validation")
    job = matched[0]
    if (job.get("run_id") != run.get("id")
            or job.get("status") != "completed"
            or job.get("conclusion") != "success"):
        raise ValueError("Safe Validation not successful on the current run")


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
    _require_authenticated_run_state(run, jobs)
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



_SCOPED_HIGH_STEPS = (
    "Verify exact certification checkout",
    "Resolve adaptive Doctor route on exact SHA",
    "Execute and verify exact-SHA targeted modules",
    "Enforce phase certification verdict",
)


def _verify_smart_pr_identity(
    run: dict[str, Any], *, candidate_sha: str, base_sha: str,
    pr_number: int | None, head_ref: str, base_ref: str,
) -> None:
    """Bind PR host evidence to the actual candidate PR, base and source branch."""
    if (type(pr_number) is not int or pr_number < 1 or not _SHA.fullmatch(base_sha)
            or not head_ref or not base_ref
            or run.get("head_branch") != head_ref):
        raise ValueError("Missing or mismatched SMART PR identity")
    linked = run.get("pull_requests")
    if not isinstance(linked, list) or not linked:
        raise ValueError("SMART proof has no GitHub-linked pull request")
    def matches(pr: Any) -> bool:
        if not isinstance(pr, dict) or pr.get("number") != pr_number:
            return False
        head = pr.get("head") or {}
        base = pr.get("base") or {}
        return (isinstance(head, dict) and isinstance(base, dict)
                and head.get("sha") == candidate_sha
                and head.get("ref") == head_ref
                and type((head.get("repo") or {}).get("id")) is int
                and (head.get("repo") or {}).get("id") == (run.get("head_repository") or {}).get("id")
                and base.get("sha") == base_sha
                and base.get("ref") == base_ref
                and type((base.get("repo") or {}).get("id")) is int
                and (base.get("repo") or {}).get("id") == (run.get("repository") or {}).get("id"))
    if not any(matches(pr) for pr in linked):
        raise ValueError("SMART proof belongs to a different PR, base or branch")


def validate_scoped_high_run(
    run: dict[str, Any], jobs: list[dict[str, Any]], *,
    candidate_sha: str, repo: str, now: datetime,
    base_sha: str, pr_number: int, head_ref: str, base_ref: str,
) -> None:
    """Only the GitHub host can attest SMART execution; PR JSON never can."""
    if not _SHA.fullmatch(candidate_sha) or not _REPO.fullmatch(repo):
        raise ValueError("Invalid SMART run identity")
    if (run.get("head_sha") != candidate_sha
            or run.get("event") != "pull_request"
            ):
        raise ValueError("SMART proof missing exact-HEAD PR run")
    _verify_smart_pr_identity(run, candidate_sha=candidate_sha, base_sha=base_sha,
                              pr_number=pr_number, head_ref=head_ref, base_ref=base_ref)
    _require_authenticated_run_state(run, jobs)
    path = str(run.get("path") or "")
    if not (path == _CERT_WORKFLOW or f"/{_CERT_WORKFLOW}@" in path
            or path.startswith(_CERT_WORKFLOW + "@")):
        raise ValueError("SMART proof belongs to another workflow")
    if (run.get("repository") or {}).get("full_name") != repo:
        raise ValueError("SMART proof belongs to another repository")
    created = _parsed_date(run.get("created_at", ""))
    finished = _parsed_date(run.get("updated_at", ""))
    if (created > now + timedelta(minutes=5)
            or finished > now + timedelta(minutes=5)
            or finished < created or now - finished > _MAX_PROOF_AGE):
        raise ValueError("Stale or invalid SMART host evidence")
    matched = [job for job in jobs
               if job.get("name") == "Phase Certification / Full Validation"]
    if len(matched) != 1:
        raise ValueError("Missing or ambiguous host Phase job for SMART")
    job = matched[0]
    if (job.get("run_id") != run.get("id")
            or job.get("status") != "completed"
            or job.get("conclusion") != "success"):
        raise ValueError("SMART Phase job not successful on this run")
    steps = job.get("steps") or []
    for name in _SCOPED_HIGH_STEPS:
        matches = [step for step in steps if step.get("name") == name]
        if (len(matches) != 1 or matches[0].get("status") != "completed"
                or matches[0].get("conclusion") != "success"):
            raise ValueError("SMART mandatory step missing/failed: " + name)
    # A FULL result is never relabeled SMART. An actual FULL proof can only
    # satisfy the independent FULL policy and always stays separately named.
    full_steps = [step for step in steps
                  if step.get("name") == "Run full Atlas phase certification gate"]
    if len(full_steps) != 1 or full_steps[0].get("conclusion") != "skipped":
        raise ValueError("SMART proof cannot conceal a FULL execution")


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
    root: Path | None = None,
    deleted_paths: tuple[str, ...] | list[str] = (),
    pr_number: int | None = None,
    head_ref: str = '', base_ref: str = '',
) -> dict[str, Any]:
    if not _SHA.fullmatch(candidate_sha) or not _SHA.fullmatch(base_sha):
        raise ValueError("Expected exact 40-digit candidate/base SHA")
    if candidate_sha == base_sha or not _REPO.fullmatch(repo):
        raise ValueError("Invalid PR candidate identity")
    route = classify_merge_route(paths, root=root, base_sha=base_sha,
                                 deleted_paths=deleted_paths)
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
    if route["route"] == "SMART":
        for run in runs or []:
            try:
                validate_scoped_high_run(
                    run, (jobs_by_run or {}).get(run.get("id"), []),
                    candidate_sha=candidate_sha, repo=repo, now=now,
                    base_sha=base_sha, pr_number=pr_number,
                    head_ref=head_ref, base_ref=base_ref,
                )
                result["status"] = "PASS_SMART_AUTHENTICATED_NOT_FULL"
                result["scoped_evidence_run"] = run["id"]
                result["reasons"].append("Host-verified exact-SHA SMART; no Phase/FULL certification")
                return result
            except (ValueError, TypeError) as exc:
                # Independent Phase may conservatively run FULL even on this
                # bounded candidate (unmapped consumer, metrics or unknown
                # dependency). A *real* exact-head FULL proof still wins.
                try:
                    if run.get("event") == "pull_request":
                        _verify_smart_pr_identity(
                            run, candidate_sha=candidate_sha, base_sha=base_sha,
                            pr_number=pr_number, head_ref=head_ref, base_ref=base_ref,
                        )
                    validate_full_run(
                        run, (jobs_by_run or {}).get(run.get("id"), []),
                        candidate_sha=candidate_sha, repo=repo, now=now,
                    )
                    result["status"] = "PASS_FULL_AUTHENTICATED"
                    result["full_evidence_run"] = run["id"]
                    result["reasons"].append("Doctor escalated bounded HIGH to verified real FULL")
                    return result
                except (ValueError, TypeError):
                    failures.append(str(exc))
        result["reasons"] = failures[:10] or [
            "HIGH SMART BLOCKED: missing successful exact-SHA scoped or FULL host steps"
        ]
        return result
    for run in runs or []:
        try:
            if run.get("event") == "pull_request":
                _verify_smart_pr_identity(
                    run, candidate_sha=candidate_sha, base_sha=base_sha,
                    pr_number=pr_number, head_ref=head_ref, base_ref=base_ref,
                )
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
        if run.get("head_sha") != sha or not (
            (run.get("status") == "completed" and run.get("conclusion") == "success")
            or (run.get("status") == "in_progress"
                and run.get("conclusion") is None
                and run.get("event") == "pull_request")
        ):
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


def candidate_paths(base_sha: str, candidate: str) -> tuple[list[str], list[str]]:
    """Preserve deletions/type changes; --no-renames makes moves D+A."""
    finished = subprocess.run(
        ["git", "diff", "--name-status", "-z", "--no-renames", base_sha, candidate],
        check=True, capture_output=True, text=True, encoding="utf-8", timeout=45,
    )
    fields = finished.stdout.split("\0")
    if not fields or fields[-1] != "" or (len(fields) - 1) % 2:
        raise ValueError("Malformed Git name-status diff")
    paths, deleted = [], []
    for i in range(0, len(fields) - 1, 2):
        status, path = fields[i:i + 2]
        if status not in {"A", "M", "D", "T"} or not path:
            raise ValueError("Unrecognized or unsafe diff status")
        paths.append(path)
        if status in {"D", "T"}:
            deleted.append(path)
    return paths, deleted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--head-ref", required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--safe-result", required=True)
    parser.add_argument("--enforce", choices=("true", "false"), default="false")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    candidate = git("rev-parse", "HEAD")
    if candidate != args.candidate_sha:
        raise ValueError("Checkout differs from PR's exact HEAD")
    paths, deleted = candidate_paths(args.base_sha, candidate)
    route = classify_merge_route(paths, root=Path.cwd(), base_sha=args.base_sha,
                                 deleted_paths=deleted)
    runs: list[dict[str, Any]] = []
    jobs: dict[int, list[dict[str, Any]]] = {}
    if route["route"] in {"FULL_REQUIRED", "SMART"}:
        try:
            runs, jobs = retrieve_full_proofs(args.repo, candidate, os.environ.get("GITHUB_TOKEN", ""))
        except ValueError as exc:
            print(f"FULL proof retrieval failed closed: {exc}")
    result = evaluate_merge(candidate_sha=candidate, base_sha=args.base_sha,
                            paths=paths, deleted_paths=deleted, safe_validation=args.safe_result, repo=args.repo,
                            now=datetime.now(timezone.utc), runs=runs, jobs_by_run=jobs, root=Path.cwd(),
                            pr_number=args.pr_number, head_ref=args.head_ref, base_ref=args.base_ref)
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
