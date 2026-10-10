from __future__ import annotations

"""Doctor's read-only, fail-closed adaptive certification planner.

The scope router owns direct test mappings. Source Impact provides extra
dependency evidence. Neither can override Atlas Integrity's mandatory FULL
phase/release certification contract. No graph rebuild or tests during plan().
"""
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from tools import ai_context, ci_scope_gate
from tools.atlas_integrity import classify_risk

SCHEMA_VERSION = 1
POLICY_VERSION = "doctor-certification-v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CRITICAL_PATHS = frozenset({
    "tools/doctor_certification.py",
    "tools/atlas_doctor_lib/certification_engine.py",
    "tests/test_doctor_certification.py",
    ".github/workflows/doctor-certification.yml",
    "PHASE_CERTIFICATION.md",
})
DOMAINS = ("functional", "architecture", "qt_lifecycle", "performance",
           "data", "security", "regression")
# Explicit, existing boundary contracts; these augment, never replace, direct tests.
BOUNDARY_TESTS = {
    "app/modules/encyclopedia/widgets/__init__.py": (
        "tests.test_encyclopedia_on_demand_loading",
        "tests.test_encyclopedia_tab_demand_loading",
    ),
    "app/modules/encyclopedia/providers/__init__.py": (
        "tests.test_encyclopedia_on_demand_loading",
        "tests.test_encyclopedia_tab_demand_loading",
    ),
}
MAX_IMPACT_FILES = 6
MAX_SELECTED_MODULES = 16


def fingerprint(payload: Any) -> str:
    """Stable report identity, *not* a cryptographic attestation."""
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()


def classify_domains(paths: list[str], consumers: list[str]) -> dict[str, list[str]]:
    result: dict[str, set[str]] = {name: set() for name in DOMAINS}
    for path in sorted(set(paths + consumers)):
        lower = path.casefold()
        if path.startswith(("app/", "tests/")):
            result["functional"].add(path)
            result["regression"].add(path)
        if path.endswith(".py") or path.startswith(".github/"):
            result["architecture"].add(path)
        if any(word in lower for word in ("qt", "widget", "view", "ui/", "worker",
                                         "thread", "timer", "webengine", "lifecycle")):
            result["qt_lifecycle"].add(path)
        if any(word in lower for word in ("startup", "preload", "memory", "ram",
                                         "cache", "lazy", "perf", "import")):
            result["performance"].add(path)
        if path.startswith(("data/", "local_dofus_data/", "config/")) or any(
            word in lower for word in ("guide", "quest", "achievement", "persistence", "json_store")
        ):
            result["data"].add(path)
        if path.startswith(".github/") or any(word in lower for word in (
            "integrity", "security", "certification", "ci_scope_gate", "doctor_certification"
        )):
            result["security"].add(path)
    return {name: sorted(paths) for name, paths in result.items() if paths}


def _required_boundary_modules(root: Path, paths: list[str]) -> list[str]:
    modules: list[str] = []
    for path in paths:
        for module in BOUNDARY_TESTS.get(path, ()):
            target = root / Path(*module.split(".")).with_suffix(".py")
            if not target.is_file():
                raise ValueError(f"missing required boundary contract: {module}")
            modules.append(module)
    return sorted(set(modules))


def _safe_paths(paths: list[str]) -> bool:
    if not paths or len(paths) > 100:
        return False
    for path in paths:
        if not isinstance(path, str):
            return False
        value = Path(path)
        if (not path or "\\" in path
                or path.startswith("/") or value.is_absolute()
                or any(part in ("", ".", "..") for part in value.parts)
                or "\0" in path):
            return False
    return True


def plan(
    root: Path,
    paths: list[str],
    *,
    base_sha: str,
    head_sha: str,
    deleted_paths: list[str] | None = None,
    impact_provider: Callable[[Path, list[str]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Plan for the exact Git candidate; uncertain inputs escalate to FULL.

    The returned FULL_REQUIRED means "no targeted certification", *not* that
    this function has run or passed the FULL gate.
    """
    root = root.resolve()
    changed = sorted(set(paths))
    deleted = sorted(set(deleted_paths or []))
    reasons: list[str] = []
    baseline_ok = bool(SHA_RE.fullmatch(base_sha)) and bool(SHA_RE.fullmatch(head_sha))
    if not baseline_ok:
        reasons.append("INVALID_EXACT_SHA")
    if not _safe_paths(changed) or (deleted and not _safe_paths(deleted)):
        reasons.append("INVALID_DIFF_PATHS")
    if (root / ".git").is_dir() and any(not (root / p).exists() for p in changed if p not in deleted):
        reasons.append("MISSING_WORKTREE_PATH")
    if set(changed) & CRITICAL_PATHS:
        reasons.append("CERTIFICATION_ROOT_OF_TRUST_CHANGE")

    risk = classify_risk(changed) if _safe_paths(changed) else {"risk": "CRITICAL"}
    if risk.get("risk") in {"HIGH", "CRITICAL"}:
        reasons.append("INDEPENDENT_RISK_" + risk["risk"])
    scoped: dict[str, Any] = {}
    if not reasons:
        scoped = ci_scope_gate.classify_diff(
            root, changed, before_sha=base_sha, deletion_paths=deleted, head=head_sha
        )
        if scoped.get("status") != "TARGETED" or scoped.get("full_required"):
            reasons.extend(["CANONICAL_SCOPE_REQUIRES_FULL", *scoped.get("reasons", [])])

    impacted: dict[str, Any] = {"status": "NOT_REQUIRED", "consumer_files": [],
                               "literal_dynamic_import_candidates": []}
    python_sources = [p for p in changed if p.endswith(".py") and not p.startswith("tests/")]
    if not reasons and python_sources:
        if len(python_sources) > MAX_IMPACT_FILES:
            reasons.append("IMPACT_BUDGET_EXCEEDED")
        else:
            if impact_provider is None:
                from tools.atlas_doctor_lib.source_impact import source_reverse_impact
                impact_provider = lambda selected_root, selected: source_reverse_impact(
                    selected_root, selected, depth=2
                )
            try:
                impacted = impact_provider(root, python_sources)
                if impacted.get("status") != "SOURCE_CONFIRMED" or impacted.get("truncated"):
                    reasons.append("INCOMPLETE_SOURCE_IMPACT")
                if impacted.get("source_errors"):
                    reasons.append("SOURCE_IMPACT_ERRORS")
                if impacted.get("literal_dynamic_import_candidates"):
                    reasons.append("UNPROVEN_DYNAMIC_CONSUMERS")
            except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
                impacted = {"status": "ERROR", "reason": type(exc).__name__,
                            "consumer_files": []}
                reasons.append("SOURCE_IMPACT_UNAVAILABLE")
    consumers = [row["path"] for row in impacted.get("consumer_files", [])
                 if isinstance(row, dict) and isinstance(row.get("path"), str)]
    if len(consumers) > 160:
        reasons.append("IMPACT_SCOPE_TOO_LARGE")
    domains = classify_domains(changed, consumers)

    modules = list(scoped.get("modules", [])) if not reasons else []
    if not reasons:
        try:
            modules = list(dict.fromkeys(modules + _required_boundary_modules(root, changed)))
        except ValueError:
            reasons.append("BOUNDARY_CONTRACT_UNAVAILABLE")
        if len(modules) > MAX_SELECTED_MODULES or not modules:
            reasons.append("TEST_SCOPE_TOO_LARGE_OR_EMPTY")
        if any(not (root / Path(*module.split(".")).with_suffix(".py")).is_file()
               for module in modules):
            reasons.append("SELECTED_TEST_MISSING")
        # A newly impacted consumer that has no explicitly mapped test cannot
        # be treated as covered by the changed file's unit test.
        unsupported = [path for path in consumers if path.startswith("app/")
                       and not ci_scope_gate._path_has_direct_test_coverage(root, path)]
        if unsupported:
            reasons.append("UNMAPPED_TRANSITIVE_CONSUMER")

    if reasons:
        profile = "FULL_REQUIRED"
        modules = []
    elif domains.keys() & {"performance", "qt_lifecycle", "data"}:
        profile = "SMART"
    else:
        profile = "FAST"
    data = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": POLICY_VERSION,
        "kind": "doctor_adaptive_certification_plan",
        "candidate_sha": head_sha,
        "base_sha": base_sha,
        "changed_paths": changed,
        "deleted_paths": deleted,
        "risk": risk.get("risk", "CRITICAL"),
        "profile": profile,
        "status": "FULL_REQUIRED" if reasons else "READY_TO_RUN_SCOPED",
        "reasons": sorted(set(reasons)),
        "domains": domains,
        "test_modules": modules,
        "source_impact": {
            "status": impacted.get("status"),
            "consumers": consumers[:160],
            "dynamic_candidates": len(impacted.get("literal_dynamic_import_candidates", [])),
        },
        "validation": {
            "certified": False,
            "full_suite_waived": False,
            "phase_certified": False,
            "required_existing_gate": "Atlas Integrity FULL + Phase Certification",
            "automatic_full_dispatched": False,
        },
        "read_only": True,
        "tests_executed": False,
    }
    data["plan_fingerprint"] = fingerprint(data)
    return data


def verify_scoped_evidence(
    plan_report: dict[str, Any], evidence: dict[str, Any],
) -> dict[str, Any]:
    """Local CI result contract. NEVER a substitute for GitHub job attestation."""
    reasons = []
    for key in ("candidate_sha", "base_sha", "plan_fingerprint"):
        if evidence.get(key) != plan_report.get(key):
            reasons.append("EVIDENCE_" + key.upper() + "_MISMATCH")
    if plan_report.get("status") != "READY_TO_RUN_SCOPED":
        reasons.append("PLAN_REQUIRES_FULL")
    if evidence.get("executed_modules") != plan_report.get("test_modules"):
        reasons.append("INCOMPLETE_TEST_EXECUTION")
    if evidence.get("exit_code") != 0 or not evidence.get("completed"):
        reasons.append("FAILED_OR_INCOMPLETE_TESTS")
    return {
        "status": "BLOCKED" if reasons else "SCOPED_TESTS_PASS",
        "reasons": sorted(set(reasons)),
        "candidate_sha": plan_report.get("candidate_sha"),
        "plan_fingerprint": plan_report.get("plan_fingerprint"),
        "phase_certified": False,
        "full_suite_waived": False,
        "certified": False,
        "evidence_reusable_across_shas": False,
    }


def historical_evidence_usable(plan_report: dict[str, Any], previous: dict[str, Any]) -> bool:
    """Fail-closed exact-candidate replay; cross-SHA reuse needs a future proof of complete closure."""
    return (
        bool(SHA_RE.fullmatch(str(plan_report.get("candidate_sha", ""))))
        and plan_report.get("status") == "READY_TO_RUN_SCOPED"
        and previous.get("status") == "SCOPED_TESTS_PASS"
        and previous.get("candidate_sha") == plan_report.get("candidate_sha")
        and previous.get("plan_fingerprint") == plan_report.get("plan_fingerprint")
        and previous.get("environment") == {
            "os": os.name,
            "python": __import__("sys").version.split()[0],
        }
    )
