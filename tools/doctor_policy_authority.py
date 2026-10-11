from __future__ import annotations

"""Independent protected-default-branch trust checks for artifact policy.

Policy/source comparisons alone cannot prove protected branch restrictions:
only a read-only, independently fetched GitHub branch-protection response
can establish that. This module never unblocks FULL or skips tests.
"""
import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SHA = re.compile(r"^[0-9a-f]{40}$")
REPO = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")
API = "https://api.github.com"
# Explicitly define every module that can change the scope, risk, runtime
# traces, scenario contracts, evidence/reuse or source policy.
TRUST_PATHS = (
    ".github/workflows/doctor-certification.yml",
    ".github/workflows/scoped-pr-ci.yml",
    ".github/workflows/phase-certification.yml",
    "PHASE_CERTIFICATION.md",
    "tools/atlas_integrity_policy.json",
    "tools/atlas_integrity.py",
    "tools/ci_scope_gate.py",
    "tools/atlas_doctor_lib/certification_engine.py",
    "tools/atlas_doctor_lib/certification_policy.py",
    "tools/atlas_doctor_lib/certification_passport.py",
    "tools/atlas_doctor_lib/certification_evidence.py",
    "tools/atlas_doctor_lib/certification_runtime.py",
    "tools/atlas_doctor_lib/certification_shadow.py",
    "tools/doctor_certification.py",
    "tools/phase_adaptive_gate.py",
    "tools/doctor_github_provenance.py",
    "tools/doctor_shadow_campaign.py",
    "tools/doctor_scenario_runner.py",
    "tools/ci_guide_full_evidence.py",
    "tools/run_guide_ultime_ci.ps1",
    "tests/test_guides_catalog_fill.py",
    "tests/test_guide_full_suite_fixture_budget.py",
)
# Data-file changes outside TRUST_PATHS still block cross-SHA eligibility
# under certification_evidence.py (only docs/**/*.md eligible).


def assess_policy_authority(
    *, candidate_sha: str, trusted_main_sha: str,
    candidate_blobs: dict[str, str],
    trusted_blobs: dict[str, str],
    protection: dict[str, Any],
    trusted_branch: str = "main",
) -> dict[str, Any]:
    errors = []
    if (not isinstance(candidate_sha, str) or not SHA.fullmatch(candidate_sha)
            or not isinstance(trusted_main_sha, str) or not SHA.fullmatch(trusted_main_sha)):
        errors.append("INVALID_EXACT_SHA")
    if trusted_branch != "main":
        errors.append("NOT_CANONICAL_PROTECTED_MAIN")
    missing = []
    divergent = []
    for path in TRUST_PATHS:
        a, b = candidate_blobs.get(path), trusted_blobs.get(path)
        if not isinstance(a, str) or not SHA.fullmatch(a) or not isinstance(b, str) or not SHA.fullmatch(b):
            missing.append(path)
        elif a != b:
            divergent.append(path)
    if missing:
        errors.append("POLICY_FILES_UNVERIFIED")
    if divergent:
        errors.append("CANDIDATE_POLICY_DIFFERS_FROM_MAIN")
    # Branch protection is a host assertion. Never accept a PR-generated
    # boolean or an artifact's self-declared protection status.
    if not isinstance(protection, dict) or not protection.get("enabled_by_host"):
        errors.append("PROTECTED_MAIN_NOT_VERIFIED")
    elif (not protection.get("required_pr_reviews")
          or not protection.get("required_status_checks")
          or protection.get("allow_force_pushes")
          or protection.get("allow_deletions")):
        errors.append("PROTECTED_MAIN_RULES_INSUFFICIENT")
    return {
        "kind": "doctor_independent_policy_authority",
        "candidate_sha": candidate_sha, "trusted_main_sha": trusted_main_sha,
        "status": "SAME_CODE_ON_PROTECTED_MAIN" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "missing": missing, "divergent": divergent,
        "trusted_branch": trusted_branch,
        "source_code_identical_to_protected_main": not missing and not divergent,
        "policy_complete_for_dynamic_dependencies": False,
        "automated_test_reuse_authorized": False,
        "phase_certified": False, "full_suite_waived": False,
        "note": "Policy identity is necessary but insufficient for cross-SHA proof.",
    }


def _api(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": "Bearer " + token,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Dofus-Atlas-Doctor",
    })
    with urllib.request.urlopen(request, timeout=15) as res:
        payload = res.read(512_001)
    if len(payload) > 512_000:
        raise ValueError("Unbounded GitHub response")
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("Unexpected GitHub API payload")
    return data


def check_online(repo: str, *, candidate_sha: str, trusted_main_sha: str) -> dict[str, Any]:
    """Opt-in read-only GitHub query. Unavailable ruleset is a BLOCKED result."""
    if not REPO.fullmatch(repo) or not SHA.fullmatch(candidate_sha) or not SHA.fullmatch(trusted_main_sha):
        raise ValueError("Invalid immutable GitHub coordinates")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError("Read-only GitHub token required for independent trust")
    def blobs(ref: str) -> dict[str, str]:
        found = {}
        for path in TRUST_PATHS:
            try:
                info = _api(f"{API}/repos/{repo}/contents/{path}?ref={ref}", token)
                found[path] = info.get("sha")
            except (urllib.error.HTTPError, ValueError):
                found[path] = None
        return found
    protected = {
        "enabled_by_host": False,
        "required_pr_reviews": False,
        "required_status_checks": False,
        "allow_force_pushes": True,
        "allow_deletions": True,
    }
    try:
        info = _api(f"{API}/repos/{repo}/branches/main/protection", token)
        protected = {
            "enabled_by_host": True,
            "required_pr_reviews": bool(info.get("required_pull_request_reviews")),
            "required_status_checks": bool(info.get("required_status_checks")),
            "allow_force_pushes": bool((info.get("allow_force_pushes") or {}).get("enabled", True)),
            "allow_deletions": bool((info.get("allow_deletions") or {}).get("enabled", True)),
        }
    except (urllib.error.HTTPError, ValueError):
        pass
    return assess_policy_authority(
        candidate_sha=candidate_sha, trusted_main_sha=trusted_main_sha,
        candidate_blobs=blobs(candidate_sha), trusted_blobs=blobs(trusted_main_sha),
        protection=protected,
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--candidate-sha", required=True)
    ap.add_argument("--trusted-main-sha", required=True)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args(argv)
    try:
        outcome = check_online(args.repo, candidate_sha=args.candidate_sha,
                               trusted_main_sha=args.trusted_main_sha)
    except (ValueError, OSError, urllib.error.URLError, TimeoutError) as exc:
        outcome = {"status": "BLOCKED", "errors": [type(exc).__name__],
                   "automated_test_reuse_authorized": False, "phase_certified": False}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(outcome, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(outcome, indent=2))
    return 0 if outcome["status"] == "SAME_CODE_ON_PROTECTED_MAIN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
