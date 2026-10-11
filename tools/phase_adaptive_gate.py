from __future__ import annotations

"""Fail-closed exact-SHA bridge between Doctor and the Phase CI workflow.

The phase workflow owns this gate. Doctor's SCOPED_TESTS_PASS is *not* FULL
or release certification. Changed certification policy always mandates FULL.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"^[0-9a-f]{40}$")

# Root-of-trust changes must never use scoped evidence, even if the changed
# Doctor planner claims that they are low-risk. Include this very bridge.
TRUST_FILES = frozenset({
    "PHASE_CERTIFICATION.md",
    "DOCTOR_ADAPTIVE_CERTIFICATION.md",
    "tools/atlas_integrity.py",
    "tools/atlas_full_suite_proof.py",
    "tools/atlas_integrity_policy.json",
    "tools/ci_scope_gate.py",
    "tools/doctor_certification.py",
    "tools/doctor_policy_authority.py",
    "tools/phase_certification_verdict.py",
    "tools/phase_adaptive_gate.py",
    "tools/ci_guide_full_evidence.py",
    "tools/run_guide_ultime_ci.ps1",
})
TRUST_PREFIXES = ("tools/atlas_doctor_lib/", ".github/workflows/")
SCOPED = "READY_TO_RUN_SCOPED"
FULL = "FULL_REQUIRED"


def critical_changed(paths: list[str]) -> list[str]:
    return sorted({p for p in paths if p in TRUST_FILES or p.startswith(TRUST_PREFIXES)})


def choose_route(
    report: dict[str, Any] | None, paths: list[str], *,
    base_sha: str, candidate_sha: str, forced: bool = False,
) -> dict[str, Any]:
    if not SHA.fullmatch(base_sha) or not SHA.fullmatch(candidate_sha):
        raise ValueError("Missing exact candidate/base SHA")
    critical = critical_changed(paths)
    reasons: list[str] = []
    if forced:
        reasons.append("FULL_DISPATCH_EXPLICIT_OR_MAIN_PUSH")
    if critical:
        reasons.append("ROOT_OF_TRUST_CHANGED")
    if report is None:
        reasons.append("DOCTOR_PLAN_UNAVAILABLE")
    else:
        if report.get("candidate_sha") != candidate_sha or report.get("base_sha") != base_sha:
            reasons.append("DOCTOR_EXACT_SHA_MISMATCH")
        if report.get("status") != SCOPED:
            reasons.append("DOCTOR_REQUIRES_FULL")
        if (report.get("independent_verdict") or {}).get("status") != "POLICY_CONFORMING":
            reasons.append("INDEPENDENT_POLICY_UNVERIFIED")
        if (not isinstance(report.get("test_modules"), list)
                or not report["test_modules"]
                or len(report["test_modules"]) != len(set(report["test_modules"]))):
            reasons.append("NO_COMPLETE_SCOPED_TEST_SET")
        if report.get("reasons"):
            reasons.append("DOCTOR_REPORTED_RISK")
        if (report.get("independent_policy") or {}).get("root_of_trust_changed"):
            reasons.append("DOCTOR_ROOT_OF_TRUST_CHANGE")
        if (report.get("independent_policy") or {}).get("canonical_risk") in ("HIGH", "CRITICAL"):
            reasons.append("HIGH_OR_CRITICAL_RISK")
        if (not isinstance(report.get("plan_fingerprint"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", report["plan_fingerprint"])):
            reasons.append("MISSING_PLAN_FINGERPRINT")
    route = "FULL" if reasons else "SCOPED"
    return {
        "schema_version": 1,
        "kind": "phase_adaptive_route",
        "candidate_sha": candidate_sha,
        "base_sha": base_sha,
        "route": route,
        "status": FULL if route == "FULL" else SCOPED,
        "root_of_trust_changes": critical,
        "reasons": sorted(set(reasons)),
        "doctor_fingerprint": report.get("plan_fingerprint") if report else None,
        "test_modules": list(report.get("test_modules", [])) if route == "SCOPED" else [],
        "full_suite_executed": False,
        "scoped_tests_executed": False,
        "phase_certified": False,
        "merge_authorized": False,
    }


def verify_scoped(route: dict[str, Any], report: dict[str, Any]) -> None:
    if route.get("route") != "SCOPED" or route.get("reasons") or route.get("root_of_trust_changes"):
        raise ValueError("The phase route did not authorize scoped tests")
    if route.get("candidate_sha") != report.get("candidate_sha") or route.get("base_sha") != report.get("base_sha"):
        raise ValueError("Stale scoped execution")
    if route.get("doctor_fingerprint") != report.get("plan_fingerprint"):
        raise ValueError("Scoped tests ran with a changed plan")
    if route.get("test_modules") != report.get("test_modules"):
        raise ValueError("Scoped tests omitted required modules")
    ex = report.get("execution") or {}
    passport = report.get("passport") or {}
    pv = report.get("passport_validation") or {}
    if (report.get("status") != SCOPED
            or (report.get("independent_verdict") or {}).get("status") != "POLICY_CONFORMING"
            or ex.get("status") != "SCOPED_TESTS_PASS"
            or ex.get("exit_code") != 0
            or ex.get("executed_modules") != route.get("test_modules")
            or passport.get("verdict") != "SCOPED_PASS_NOT_FULL"
            or pv.get("status") != "INTEGRITY_CHECKED_NOT_ATTESTED"):
        raise ValueError("Exact-SHA scoped tests/passport are incomplete")
    # A targeted gate must not manufacture an authoritative FULL verdict.
    if (report.get("phase_certified") is True
            or passport.get("phase_certified") is True
            or passport.get("merge_authorized") is True
            or passport.get("full_suite_waived") is True):
        raise ValueError("Unsupported release/phase certification claim")


def _git(*args: str) -> str:
    done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", timeout=40, check=True)
    return done.stdout.strip()


def _load(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 3_000_000:
        raise ValueError("Unsafe/missing phase evidence")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Phase evidence must be a JSON object")
    return payload


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("decide", "verify-scoped"))
    parser.add_argument("--base-ref", default="")
    parser.add_argument("--expected-sha", default="")
    parser.add_argument("--force-full", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--route", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if args.action == "verify-scoped":
        verify_scoped(_load(args.route), _load(args.report))
        print("SCOPED_TESTS_PASS_NOT_PHASE_CERTIFIED: exact-SHA complete evidence verified")
        return 0
    head = _git("rev-parse", "HEAD")
    base = _git("rev-parse", "--verify", f"{args.base_ref}^{{commit}}")
    if args.expected_sha != head or not SHA.fullmatch(head):
        raise ValueError("Candidate SHA does not equal exact checked-out HEAD")
    paths = _git("diff", "--name-only", "--no-renames", base, head).splitlines()
    trust = critical_changed(paths)
    # A changed policy is automatically FULL_REQUIRED, before loading any PR-
    # supplied Doctor plan. This also covers direct workflow modifications.
    plan = None
    if not args.force_full and not trust:
        plan_path = Path("artifacts/phase_certification/doctor_route_plan.json")
        cmd = [sys.executable, "-X", "faulthandler", "-m", "tools.doctor_certification",
               "--base-ref", base, "--expected-sha", head,
               "--output", str(plan_path)]
        finished = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                  timeout=180, check=False)
        if finished.returncode == 0:
            try:
                plan = _load(ROOT / plan_path)
            except (ValueError, OSError, json.JSONDecodeError):
                pass
        else:
            print("Doctor could not prove targeted eligibility: FULL_REQUIRED", file=sys.stderr)
    route = choose_route(plan, paths, base_sha=base, candidate_sha=head,
                         forced=args.force_full)
    if args.output:
        _save(args.output, route)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as stream:
            stream.write("run_full=" + ("true" if route["route"] == "FULL" else "false") + "\n")
            stream.write("run_scoped=" + ("true" if route["route"] == "SCOPED" else "false") + "\n")
    print(json.dumps(route, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
