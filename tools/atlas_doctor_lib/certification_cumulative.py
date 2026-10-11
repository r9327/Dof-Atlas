from __future__ import annotations

"""Read-only cumulative change detector since an explicitly supplied Git base.

A commit ancestry check is evidence of ancestry only; it does NOT attest
that this base ever passed a FULL. Cumulative analysis can only *raise* the
test floor, never downgrade a canonical or independent gate.
"""
import re
import subprocess
from pathlib import Path
from typing import Any

from tools.atlas_integrity import affected_groups, classify_risk

SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_CHANGED = 250


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True,
                            timeout=25, check=False)
    if result.returncode:
        raise RuntimeError(
            "Git cumulative comparison unavailable: "
            + result.stderr.decode("utf-8", "replace").strip()
        )
    return result


def assess_cumulative(root: Path, *, baseline_sha: str,
                      candidate_sha: str) -> dict[str, Any]:
    """Fail closed on unknown ancestry, too many changes, or risky accumulation."""
    if (not isinstance(baseline_sha, str) or not SHA.fullmatch(baseline_sha)
            or not isinstance(candidate_sha, str) or not SHA.fullmatch(candidate_sha)):
        return {
            "status": "BLOCKED", "reasons": ["INVALID_EXACT_SHA"],
            "authorizes_skipping_tests": False, "base_full_proven": False,
        }
    try:
        head = _git(root, "rev-parse", "HEAD").stdout.decode().strip()
        if head != candidate_sha:
            raise RuntimeError("Candidate worktree SHA does not match input")
        _git(root, "merge-base", "--is-ancestor", baseline_sha, candidate_sha)
        changed = sorted({
            name.decode("utf-8", "replace") for name in _git(
                root, "diff", "-z", "--name-only", baseline_sha, candidate_sha
            ).stdout.split(b"\0") if name
        })
        removed = sorted({
            name.decode("utf-8", "replace") for name in _git(
                root, "diff", "-z", "--name-only", "--diff-filter=DR",
                baseline_sha, candidate_sha
            ).stdout.split(b"\0") if name
        })
    except (RuntimeError, OSError, subprocess.TimeoutExpired, UnicodeError):
        return {
            "status": "BLOCKED", "reasons": ["UNVERIFIED_CUMULATIVE_GIT_HISTORY"],
            "authorizes_skipping_tests": False, "base_full_proven": False,
        }

    classification = classify_risk(changed)
    groups = affected_groups(changed)
    reasons = []
    if removed:
        reasons.append("CUMULATIVE_REMOVAL_OR_RENAME")
    if len(changed) > MAX_CHANGED:
        reasons.append("CUMULATIVE_BUDGET_EXCEEDED")
    if classification["risk"] in {"HIGH", "CRITICAL"}:
        reasons.append("CUMULATIVE_RISK_" + classification["risk"])
    # Independent small edits in distinct runtime/data domains can interact.
    domains = set()
    for path in changed:
        if path.startswith("app/modules/encyclopedia/"):
            domains.add("encyclopedia")
        elif path.startswith("app/"):
            domains.add("app")
        elif path.startswith(("data/", "local_dofus_data/")):
            domains.add("data")
        elif path.startswith((".github/", "tools/")):
            domains.add("quality")
    if len(domains & {"encyclopedia", "app", "data"}) >= 2:
        reasons.append("CROSS_DOMAIN_ACCUMULATION")
    if len(changed) > 32:
        reasons.append("CUMULATIVE_DIFF_TOO_LARGE")

    return {
        "kind": "doctor_certification_cumulative_risk",
        "status": "FULL_REQUIRED" if reasons else "NO_ADDITIONAL_ESCALATION",
        "baseline_sha": baseline_sha, "candidate_sha": candidate_sha,
        "changed_count": len(changed),
        "changed_paths": changed[:MAX_CHANGED],
        "removed_or_renamed": removed[:MAX_CHANGED],
        "affected_integrity_groups": groups,
        "risk": classification["risk"],
        "domains": sorted(domains),
        "reasons": sorted(set(reasons)),
        "authorizes_skipping_tests": False,
        "base_full_proven": False,
        "interpretation": "Advisory comparison base; a trusted exact-SHA FULL attestation is not established by ancestry.",
    }
