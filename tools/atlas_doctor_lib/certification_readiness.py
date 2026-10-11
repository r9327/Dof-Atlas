from __future__ import annotations

"""Doctor single advisory readiness decision; independent FULL remains required.

Provides actionable missing-proof reasons instead of a generic green planner
that users could mistake for an actual phase certification.
"""
from typing import Any


def readiness(report: dict[str, Any]) -> dict[str, Any]:
    blockers = []
    actions = []
    head = report.get("candidate_sha")
    if report.get("status") == "BLOCKED":
        blockers.append("DOCTOR_PLANNER_BLOCKED")
        actions.append("Repair planner input, Git identity or independent policy first")
    if report.get("independent_verdict", {}).get("status") != "POLICY_CONFORMING":
        blockers.append("INDEPENDENT_POLICY_NOT_CONFORMING")
        actions.append("Resolve required test mappings and critical risk findings")
    execution = report.get("execution") or {}
    if report.get("status") == "READY_TO_RUN_SCOPED":
        if execution.get("status") != "SCOPED_TESTS_PASS":
            blockers.append("SCOPED_TESTS_UNEXECUTED_OR_FAILED")
            actions.append("Run the selected tests on the exact SHA with canonical runner")
    else:
        blockers.append("FULL_REQUIRED_BY_SCOPE")
        actions.append("Run the independent Atlas Integrity FULL when development is complete")
    runtime = report.get("runtime_observation") or {}
    if runtime.get("status") != "OBSERVED_NOT_CERTIFIED":
        blockers.append("DYNAMIC_RUNTIME_IMPACT_UNPROVEN")
        actions.append("Capture matching .ai/runtime traces covering affected consumers")
    scenario = report.get("scenario_execution") or {}
    if scenario.get("status") != "CONTRACTS_PASS_METRICS_NOT_RUN":
        blockers.append("USER_JOURNEY_CONTRACTS_NOT_VALIDATED")
        actions.append("Run doctor_scenario_runner on Windows for impacted Guide/Quest/Success/Home flows")
    policy = report.get("independent_policy") or {}
    metrics = set(policy.get("required_metrics") or [])
    executed = set(report.get("metrics_executed") or [])
    missing_metrics = sorted(metrics - executed)
    if missing_metrics:
        blockers.append("RESOURCE_METRICS_NOT_ATTESTED")
        actions.append("Run exact-SHA memory/preload/Qt benchmarks once during final certification")
    origin = report.get("github_origin_verification") or {}
    if origin.get("status") != "ARTIFACT_ORIGIN_VERIFIED_NOT_POLICY_TRUSTED":
        blockers.append("GITHUB_ARTIFACT_ORIGIN_UNVERIFIED")
        actions.append("Verify GitHub run and artifact SHA256 using doctor_github_provenance")
    trust = report.get("policy_authority") or {}
    if trust.get("status") != "SAME_CODE_ON_PROTECTED_MAIN":
        blockers.append("INDEPENDENT_POLICY_PROVENANCE_NOT_TRUSTED")
        actions.append("Compare policy blobs and verify protected main rules independently")
    shadow = report.get("shadow_comparison") or {}
    if shadow.get("status") not in ("NO_OBSERVED_DIVERGENCE", "FULL_REMAINED_REQUIRED"):
        blockers.append("SAME_SHA_SHADOW_PROOF_UNAVAILABLE")
        actions.append("Compare a real, completed FULL report against a Doctor plan on the same SHA")
    full = report.get("independent_full_attestation") or {}
    if not (full.get("status") == "EXACT_SHA_FULL_VERIFIED"
            and full.get("candidate_sha") == head
            and full.get("authenticated") is True):
        blockers.append("MANDATORY_EXACT_SHA_FULL_UNVERIFIED")
        actions.append("Complete existing Phase Certification FULL; independently verify GitHub provenance")
    unique_actions = list(dict.fromkeys(actions))
    return {
        "kind": "doctor_certification_readiness",
        "candidate_sha": head,
        "status": "BLOCKED_OR_PENDING_REQUIRED_EVIDENCE" if blockers else "EVIDENCE_REVIEW_REQUIRED",
        "blocking_reasons": sorted(set(blockers)),
        "next_checks": unique_actions,
        "missing_metrics": missing_metrics,
        "tests_reused": False,
        "full_suite_waived": False,
        "merge_authorized": False,
        "phase_certified": False,
        "readiness_is_not_a_merge_gate": True,
        "note": "This summary cannot authorize merge, including when no blockers remain. Existing GitHub branch/phase rules are authoritative.",
    }
