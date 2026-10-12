from __future__ import annotations

"""Reuse a GitHub-attested PR FULL only for a tree-identical main merge."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
WORKFLOW = ".github/workflows/phase-certification.yml"
STEPS = (
    "Verify exact certification checkout",
    "Resolve adaptive Doctor route on exact SHA",
    "Materialize certification LFS fixtures",
    "Materialize local Dofus catalog",
    "Run full Atlas phase certification gate",
    "Compare Doctor plan with actual exact-SHA FULL evidence",
    "Enforce phase certification verdict",
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, timeout=20).strip()


def merge_identity(sha: str) -> dict:
    if not SHA.fullmatch(sha) or git("rev-parse", "HEAD") != sha:
        raise ValueError("Unexpected candidate SHA")
    parents = git("show", "-s", "--format=%P", "HEAD").split()
    if len(parents) != 2 or any(not SHA.fullmatch(p) for p in parents):
        raise ValueError("Not a two-parent Git merge")
    previous, head = parents
    tree = git("rev-parse", "HEAD^{tree}")
    if tree != git("rev-parse", f"{head}^{{tree}}"):
        raise ValueError("Merged tree is not identical to the certified PR")
    trust_paths = (WORKFLOW, "tools/ci_pr_full_reuse.py",
                   "tools/ci_main_phase_evidence.py")
    if git("diff", "--name-only", previous, sha, "--", *trust_paths):
        raise ValueError("Certification trust boundary changed: run fresh FULL")
    return dict(main_sha=sha, previous_main_sha=previous,
                pr_head_sha=head, tree_sha=tree)


def choose_pr(prs: list, identity: dict, repo: str) -> dict:
    valid = [p for p in prs if
             p.get("merged_at") and p.get("merge_commit_sha") == identity["main_sha"]
             and (p.get("head") or {}).get("sha") == identity["pr_head_sha"]
             and (p.get("base") or {}).get("sha") == identity["previous_main_sha"]
             and ((p.get("head") or {}).get("repo") or {}).get("full_name") == repo
             and ((p.get("base") or {}).get("repo") or {}).get("full_name") == repo]
    if len(valid) != 1:
        raise ValueError("No unique verified merged PR")
    return valid[0]


def verify_run(run: dict, pr: dict, identity: dict, repo: str) -> None:
    if (run.get("name") != "Phase Certification"
            or run.get("path") != WORKFLOW
            or run.get("event") != "pull_request"
            or run.get("head_sha") != identity["pr_head_sha"]
            or run.get("head_branch") != (pr.get("head") or {}).get("ref")
            or (run.get("repository") or {}).get("full_name") != repo
            or (run.get("head_repository") or {}).get("full_name") != repo
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"):
        raise ValueError("Untrusted PR FULL workflow run")
    completed = run.get("updated_at")
    if (not completed or datetime.fromisoformat(completed.replace("Z", "+00:00"))
            > datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))):
        raise ValueError("PR FULL completed after merge")


def verify_jobs(payload: dict, head: str) -> None:
    jobs = payload.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != 1 or payload.get("total_count") != 1:
        raise ValueError("Partial job evidence")
    job = jobs[0]
    if (job.get("name") != "Phase Certification / Full Validation"
            or job.get("head_sha") not in (None, head)
            or job.get("status") != "completed" or job.get("conclusion") != "success"):
        raise ValueError("Not a passing FULL job")
    rows = job.get("steps")
    if not isinstance(rows, list):
        raise ValueError("No full job step evidence")
    steps = {}
    for step in rows:
        name = step.get("name") if isinstance(step, dict) else None
        if not isinstance(name, str) or name in steps:
            raise ValueError("Malformed host step evidence")
        steps[name] = step.get("conclusion")
    if any(steps.get(n) != "success" for n in STEPS):
        raise ValueError("Missing real FULL mandatory step")
    if steps.get("Execute and verify exact-SHA targeted modules") == "success":
        raise ValueError("Scoped evidence is not FULL")


def api(repo: str, path: str, token: str) -> dict | list:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{path}",
        headers={"Accept": "application/vnd.github+json",
                 "Authorization": "Bearer " + token,
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "Dof-Atlas-PR-Full-Reuse"})
    with urllib.request.urlopen(req, timeout=20) as reply:
        raw = reply.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Too large response")
    return json.loads(raw)


def inspect(repo: str, sha: str, token: str) -> dict:
    if not REPO.fullmatch(repo) or not token:
        raise ValueError("Authenticated GitHub provenance required")
    ident = merge_identity(sha)
    prs = api(repo, f"commits/{sha}/pulls?per_page=100", token)
    if not isinstance(prs, list) or len(prs) >= 100:
        raise ValueError("Incomplete associated PR list")
    pr = choose_pr(prs, ident, repo)
    payload = api(repo, f"actions/runs?head_sha={ident['pr_head_sha']}&per_page=100", token)
    if (not isinstance(payload, dict) or payload.get("total_count", 101) > 100
            or not isinstance(payload.get("workflow_runs"), list)):
        raise ValueError("Incomplete host run list")
    for run in payload["workflow_runs"]:
        try:
            verify_run(run, pr, ident, repo)
            jobs = api(repo, f"actions/runs/{run['id']}/jobs?per_page=100", token)
            verify_jobs(jobs, ident["pr_head_sha"])
        except (ValueError, TypeError, KeyError):
            continue
        return {**ident, "status": "VERIFIED_PR_FULL_SAME_TREE",
                "source_pr": pr["number"], "source_run": run["id"],
                "source_url": f"https://github.com/{repo}/actions/runs/{run['id']}"}
    raise ValueError("No complete trusted previous PR FULL")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True)
    p.add_argument("--candidate-sha", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    args.output.unlink(missing_ok=True)
    ok = False
    try:
        if os.getenv("GITHUB_EVENT_NAME") != "push":
            raise ValueError("Not a main push")
        proof = inspect(args.repo, args.candidate_sha, os.getenv("GITHUB_TOKEN", ""))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
        ok = True
        print("Authenticated PR FULL: " + proof["source_url"])
    except Exception as exc:
        print("No reusable PR FULL; canonical FULL required: " + str(exc))
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write("reuse_full=" + ("true" if ok else "false") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
