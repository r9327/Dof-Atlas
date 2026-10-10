from __future__ import annotations

"""Exact-SHA Doctor certification planning and opt-in scoped test execution.

This reports advisory evidence. It NEVER declares a release/phase certified.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from tools import ci_scope_gate
from tools.atlas_doctor_lib.certification_engine import plan, verify_scoped_evidence


ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False, timeout=30,
    )
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> dict:
    head = _git("rev-parse", "HEAD")
    base = _git("rev-parse", "--verify", f"{args.base_ref}^{{commit}}")
    expected = args.expected_sha
    # PR checkouts must use exact head SHA, not GitHub's implicit merge commit.
    if expected and expected != head:
        raise RuntimeError(f"candidate checkout mismatch: expected={expected} actual={head}")
    if _git("status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("tracked worktree is dirty; cannot plan exact-SHA evidence")
    paths, deleted = ci_scope_gate.changed_paths(ROOT, base)
    report = plan(ROOT, paths, base_sha=base, head_sha=head, deleted_paths=deleted)
    report["execution"] = {"status": "NOT_RUN", "exit_code": None}
    if args.run and report["status"] == "READY_TO_RUN_SCOPED":
        started = time.perf_counter()
        try:
            # Canonical selector remains the *only* owner of executing selected
            # modules and rejecting empty test collections.
            code = ci_scope_gate._run_scoped_modules(ROOT, report["test_modules"])
        except (OSError, subprocess.TimeoutExpired) as exc:
            report["execution"] = {"status": "BLOCKED", "reason": type(exc).__name__}
        else:
            evidence = {
                "candidate_sha": head,
                "base_sha": base,
                "plan_fingerprint": report["plan_fingerprint"],
                "executed_modules": report["test_modules"],
                "exit_code": code,
                "completed": True,
            }
            report["execution"] = {
                **verify_scoped_evidence(report, evidence),
                "exit_code": code,
                "executed_modules": report["test_modules"],
                "duration_seconds": round(time.perf_counter() - started, 3),
                "environment": {"os": os.name, "python": sys.version.split()[0]},
            }
    elif args.run:
        report["execution"] = {"status": "FULL_REQUIRED_NOT_DISPATCHED", "exit_code": None}
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--expected-sha", default="")
    parser.add_argument("--run", action="store_true", help="Run safe selected modules; never a FULL.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = run(args)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report = {
            "schema_version": 1,
            "status": "BLOCKED",
            "profile": "FULL_REQUIRED",
            "reasons": [f"PLANNER_ERROR:{type(exc).__name__}:{exc}"],
            "phase_certified": False,
            "full_suite_waived": False,
            "certified": False,
            "execution": {"status": "BLOCKED"},
        }
    if args.output:
        _write_report(args.output, report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    # Exit 0 when a FULL is required: this workflow is *advisory*, never
    # marks the mandatory FULL as passing. A broken plan/test does fail.
    if report["status"] == "BLOCKED":
        return 2
    if report["execution"].get("status") == "BLOCKED" or report["execution"].get("exit_code") not in (None, 0):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
