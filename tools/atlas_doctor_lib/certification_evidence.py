from __future__ import annotations

"""Conservative cross-SHA evidence eligibility analysis.

An eligible certificate is NOT reusable in an automated gate until its
source GitHub workflow/artifact provenance is authenticated independently.
Currently this module NEVER skips any test, even when only docs changed.
"""
import re
import subprocess
from pathlib import Path
from typing import Any

from .certification_passport import verify_passport, environment

SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_FILES = 512


def _git(root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args], cwd=root, check=False, timeout=20, capture_output=True,
    )
    if completed.returncode:
        raise ValueError("Unable to establish immutable Git source closure")
    return completed.stdout.strip()


def inspect_previous_evidence(
    root: Path, previous_passport: dict[str, Any], current_plan: dict[str, Any],
) -> dict[str, Any]:
    """Explain whether exact Git source closure remained identical.

    Eligible means *review only*. Cryptographic JSON digests alone are NOT
    GitHub provenance; a PR can submit a fabricated digest and forged report.
    """
    current = current_plan.get("candidate_sha")
    previous = previous_passport.get("candidate_sha")
    reasons = []
    if (not isinstance(current, str) or not SHA.fullmatch(current)
            or not isinstance(previous, str) or not SHA.fullmatch(previous)
            or current == previous):
        reasons.append("INVALID_OR_IDENTICAL_SHA")
    if current_plan.get("status") != "READY_TO_RUN_SCOPED":
        reasons.append("CURRENT_PLAN_NOT_SCOPED")
    if previous_passport.get("verdict") != "SCOPED_PASS_NOT_FULL":
        reasons.append("PREVIOUS_SCOPED_PASS_NOT_PROVEN")
    current_env = environment(root)
    if previous_passport.get("environment") != current_env:
        reasons.append("EXECUTION_ENVIRONMENT_CHANGED")
    if not isinstance(previous_passport.get("plan_fingerprint"), str):
        reasons.append("MISSING_PRIOR_PLAN_FINGERPRINT")
    else:
        check = verify_passport(
            previous_passport, head_sha=previous or "",
            plan_fingerprint=previous_passport["plan_fingerprint"],
            runner_environment=current_env,
        )
        if check["status"] != "INTEGRITY_CHECKED_NOT_ATTESTED":
            reasons.append("INVALID_PRIOR_PASSPORT_INTEGRITY")
    current_modules = current_plan.get("test_modules")
    previous_modules = previous_passport.get("tests_passed")
    if (not isinstance(current_modules, list)
            or not current_modules or not isinstance(previous_modules, list)
            or not set(current_modules).issubset(previous_modules)):
        reasons.append("PREVIOUS_TEST_SET_NOT_SUPERSET")

    changes: list[str] = []
    if not reasons:
        try:
            if _git(root, "rev-parse", "HEAD").decode("ascii") != current:
                raise ValueError("Candidate HEAD mismatch")
            _git(root, "merge-base", "--is-ancestor", previous, current)
            raw = _git(root, "diff", "-z", "--name-only", previous, current)
            changes = sorted({name.decode("utf-8") for name in raw.split(b"\0") if name})
            if not changes or len(changes) > MAX_FILES:
                reasons.append("EMPTY_OR_EXCESSIVE_DIFF")
            # Crucial: ALL runtime code, data, tests, policy, CI, assets,
            # fixtures and requirements must have unchanged git objects.
            # Never infer closure from Graphify's absence of an edge.
            unknown = [p for p in changes if not (
                p.startswith("docs/")
                and p.endswith(".md")
                and ".." not in p.split("/")
            )]
            if unknown:
                reasons.append("NON_DOCUMENTATION_GIT_OBJECT_CHANGED")
        except (ValueError, OSError, UnicodeError, subprocess.TimeoutExpired):
            reasons.append("UNVERIFIED_EXACT_GIT_ANCESTRY")
    return {
        "kind": "doctor_cross_sha_evidence_eligibility",
        "status": ("CANDIDATE_FOR_INDEPENDENT_PROVENANCE_REVIEW" if not reasons
                   else "NOT_ELIGIBLE"),
        "previous_sha": previous,
        "candidate_sha": current,
        "changed_files": changes[:MAX_FILES],
        "reasons": sorted(set(reasons)),
        "test_scope_subset_proved": "PREVIOUS_TEST_SET_NOT_SUPERSET" not in reasons,
        "git_non_doc_objects_unchanged": not reasons and bool(changes),
        "github_provenance_authenticated": False,
        "automated_test_reuse_authorized": False,
        "tests_skipped": False,
        "full_suite_waived": False,
        "limitations": "Only docs/*.md git deltas can be eligible for later provenance review. "
                       "No cross-SHA proof is accepted by CI yet.",
    }
