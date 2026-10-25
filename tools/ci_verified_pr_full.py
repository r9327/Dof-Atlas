from __future__ import annotations
"""Trust a previously executed PR FULL only for an identical Git-tree merge."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

WORKFLOW = ".github/workflows/phase-certification.yml"
SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MANDATORY_STEPS = (
    "Verify exact certification checkout",
    "Resolve adaptive Doctor route on exact SHA",
    "Materialize certification LFS fixtures",
    "Materialize local Dofus catalog",
    "Run full Atlas phase certification gate",
    "Compare Doctor plan with actual exact-SHA FULL evidence",
    "Enforce phase certification verdict",
)
TRUST_FILES = (WORKFLOW, "tools/ci_verified_pr_full.py",
               "tools/ci_main_phase_evidence.py")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, timeout=20).strip()


def verify_merge(sha: str) -> dict:
    if not SHA.fullmatch(sha) or git("rev-parse", "HEAD") != sha:
        raise ValueError("Not the checked-out main SHA")
    parents = git("show", "-s", "--format=%P", "HEAD").split()
    if len(parents) != 2:
        raise ValueError("Not a regular merge (two parents)")
    base, pr_head = parents
    tree = git("rev-parse", "HEAD^{tree}")
    if tree != git("rev-parse", pr_head + "^{tree}"):
        raise ValueError("Merged code differs from certified PR head")
    if git("diff", "--name-only", base, sha, "--", *TRUST_FILES):
        raise ValueError("Certification trust source modified")
    return {"main_sha": sha, "base_sha": base,
            "pr_head_sha": pr_head, "git_tree": tree}


def verify_pr(prs: list, identity: dict, repo: str) -> dict:
    valid = [p for p in prs
        if p.get("merged_at") and p.get("merge_commit_sha") == identity["main_sha"]
        and (p.get("head") or {}).get("sha") == identity["pr_head_sha"]
        and (p.get("base") or {}).get("sha") == identity["base_sha"]
        and ((p.get("head") or {}).get("repo") or {}).get("full_name") == repo
        and ((p.get("base") or {}).get("repo") or {}).get("full_name") == repo]
    if len(valid) != 1:
        raise ValueError("Missing unique matching merged PR")
    return valid[0]


def verify_run(run: dict, pr: dict, identity: dict, repo: str) -> None:
    if (run.get("name") != "Phase Certification" or run.get("path") != WORKFLOW
            or run.get("event") != "pull_request"
            or run.get("head_sha") != identity["pr_head_sha"]
            or run.get("head_branch") != pr["head"]["ref"]
            or run.get("conclusion") != "success" or run.get("status") != "completed"
            or (run.get("repository") or {}).get("full_name") != repo
            or (run.get("head_repository") or {}).get("full_name") != repo):
        raise ValueError("Ineligible PR certification run")
    completed = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
    merged = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
    if completed > merged:
        raise ValueError("PR certification completed after merge")


def verify_job(body: dict, head: str) -> None:
    jobs = body.get("jobs")
    if not isinstance(jobs, list) or not jobs or body.get("total_count") != len(jobs):
        raise ValueError("Incomplete PR job results")
    full_jobs = [j for j in jobs if isinstance(j, dict) and j.get("name") == "Phase Certification / Domain or Release Validation"]
    if len(full_jobs) != 1:
        raise ValueError("Missing or ambiguous Phase FULL job")
    job = full_jobs[0]
    if (job.get("name") != "Phase Certification / Domain or Release Validation"
            or job.get("head_sha") not in (None, head)
            or job.get("conclusion") != "success" or job.get("status") != "completed"):
        raise ValueError("No successful FULL job")
    steps = {}
    for item in job.get("steps") or []:
        name = item.get("name")
        if not isinstance(name, str) or name in steps:
            raise ValueError("Invalid FULL job steps")
        steps[name] = item.get("conclusion")
    if any(steps.get(step) != "success" for step in MANDATORY_STEPS):
        raise ValueError("Real FULL step missing or failed")
    if steps.get("Execute and verify exact-SHA targeted modules") == "success":
        raise ValueError("Scoped tests do not count as FULL")


def fetch(repo: str, path: str, token: str):
    req = urllib.request.Request(
        "https://api.github.com/repos/" + repo + "/" + path,
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": "Bearer " + token,
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "Atlas-CI-Verified-PR-Reuse"})
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read(3000001)
    if len(raw) > 3000000:
        raise ValueError("Oversized GitHub provenance result")
    return json.loads(raw)


def inspect(repo: str, sha: str, token: str) -> dict:
    if not REPO.fullmatch(repo) or not token:
        raise ValueError("Missing repository / GitHub Actions token")
    identity = verify_merge(sha)
    prs = fetch(repo, "commits/" + sha + "/pulls?per_page=100", token)
    if not isinstance(prs, list) or len(prs) >= 100:
        raise ValueError("Incomplete associated PR list")
    pr = verify_pr(prs, identity, repo)
    runs = fetch(repo, "actions/runs?head_sha=" + identity["pr_head_sha"]
                 + "&per_page=100", token)
    if (not isinstance(runs, dict) or runs.get("total_count", 101) > 100
            or not isinstance(runs.get("workflow_runs"), list)):
        raise ValueError("Incomplete GitHub workflow evidence")
    for run in sorted(runs["workflow_runs"], key=lambda item: item.get("id", 0),
                      reverse=True):
        try:
            verify_run(run, pr, identity, repo)
            verify_job(fetch(repo, "actions/runs/" + str(run["id"])
                             + "/jobs?per_page=100", token), identity["pr_head_sha"])
        except (ValueError, KeyError, TypeError):
            continue
        return {**identity, "status": "VERIFIED_PR_FULL_SAME_TREE",
                "pr_number": pr["number"], "source_run_id": run["id"],
                "source_run_url": "https://github.com/" + repo
                    + "/actions/runs/" + str(run["id"]),
                "host_verified_real_full": True}
    raise ValueError("No completed, host-attested exact-PR FULL")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--candidate-sha", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    a.output.unlink(missing_ok=True)
    reused = False
    try:
        if os.getenv("GITHUB_EVENT_NAME") != "push":
            raise ValueError("Not main push")
        report = inspect(a.repo, a.candidate_sha, os.getenv("GITHUB_TOKEN", ""))
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("Authenticated prior real FULL: " + report["source_run_url"])
        reused = True
    except Exception as exc:
        # Fail closed: a missing/stale/invalid proof triggers the normal FULL/Doctor gate.
        print("No admissible tree-equivalent FULL; Doctor decides: " + str(exc))
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write("reuse_full=" + ("true" if reused else "false") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
