from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "tools" / "guide_phase2_baseline.json"
MANIFEST = ROOT / "data" / "routes" / "guide_ultime_manual" / "manifest_v1.json"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON object expected: {path}")
    return payload


def _digest(value: Any) -> str:
    rendered = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _run_git(arguments: list[str]) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(arguments)} failed: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return completed.stdout.strip()


def _changed_paths(base_ref: str) -> list[str]:
    output = _run_git(["diff", "--name-only", f"{base_ref}...HEAD"])
    return sorted(
        {
            line.strip().replace("\\", "/")
            for line in output.splitlines()
            if line.strip()
        }
    )


def _protected_changes(
    changed: list[str],
    protected_globs: list[str],
    allowed_changed_paths: set[str],
) -> list[str]:
    blocked: list[str] = []
    for path in changed:
        if path in allowed_changed_paths:
            continue
        if any(fnmatch.fnmatchcase(path, pattern) for pattern in protected_globs):
            blocked.append(path)
    return sorted(blocked)


def evaluate_phase(
    *,
    integrity: dict[str, Any],
    baseline: dict[str, Any],
    prerequisite: dict[str, Any],
    coverage: dict[str, Any],
    manifest: dict[str, Any],
    base_ref: str,
    resolved_base: str,
    candidate_sha: str,
    changed: list[str],
) -> dict[str, Any]:
    errors: list[str] = []
    raw_verdict = str(integrity.get("verdict") or "")
    report_head = str(integrity.get("head") or "")
    if report_head != candidate_sha:
        errors.append(f"candidate SHA mismatch: report={report_head}, expected={candidate_sha}")

    if raw_verdict == "PASS":
        return {
            "schema_version": 1,
            "status": "PASS",
            "raw_integrity_verdict": raw_verdict,
            "candidate_sha": candidate_sha,
            "base_ref": base_ref,
            "baseline_debt": [],
            "errors": [],
        }

    expected_base = str(baseline.get("base_commit") or "")
    if resolved_base != expected_base:
        errors.append(f"baseline ref mismatch: expected {expected_base}, got {resolved_base}")

    blockers = {str(value) for value in integrity.get("blockers", [])}
    allowed_blockers = {str(value) for value in baseline.get("allowed_blockers", [])}
    if not blockers:
        errors.append("blocked integrity report has no blocker IDs")
    if blockers - allowed_blockers:
        errors.append(
            "unexpected integrity blockers: " + ", ".join(sorted(blockers - allowed_blockers))
        )

    groups = integrity.get("groups") if isinstance(integrity.get("groups"), dict) else {}
    required = [str(value) for value in integrity.get("validations_required", [])]
    for name in required:
        group = groups.get(name) if isinstance(groups.get(name), dict) else {}
        status = str(group.get("status") or "NOT_RUN")
        if name == "DATA_INTEGRITY":
            if status != "BLOCKED":
                errors.append(f"DATA_INTEGRITY must be BLOCKED for baseline handling, got {status}")
            group_blockers = {str(value) for value in group.get("blockers", [])}
            if group_blockers - allowed_blockers:
                errors.append(
                    "unexpected DATA_INTEGRITY blockers: "
                    + ", ".join(sorted(group_blockers - allowed_blockers))
                )
            continue
        if status != "PASS":
            errors.append(f"required group is not PASS: {name}={status}")

    full_suite = groups.get("FULL_SUITE") if isinstance(groups.get("FULL_SUITE"), dict) else {}
    if str(full_suite.get("status") or "") != "PASS":
        errors.append("FULL_SUITE is not absolute PASS")

    expected_status = str(baseline.get("required_manifest_status") or "")
    actual_status = str(manifest.get("status") or "")
    if actual_status != expected_status:
        errors.append(
            f"manifest status changed: expected {expected_status}, got {actual_status}"
        )

    protected = _protected_changes(
        changed,
        [str(value) for value in baseline.get("protected_globs", [])],
        {str(value) for value in baseline.get("allowed_changed_paths", [])},
    )
    if protected:
        errors.append("Guide baseline owners changed: " + ", ".join(protected))

    pre_contract = baseline.get("prerequisite") or {}
    hard_errors = prerequisite.get("hard_errors") or []
    if not isinstance(hard_errors, list):
        errors.append("prerequisite hard_errors is not a list")
        hard_errors = []
    if int(prerequisite.get("hard_error_count") or 0) != int(
        pre_contract.get("hard_error_count") or 0
    ):
        errors.append("prerequisite hard error count drift")
    pre_digest = _digest(hard_errors)
    if pre_digest != str(pre_contract.get("hard_errors_sha256") or ""):
        errors.append("prerequisite baseline fingerprint drift")

    coverage_contract = baseline.get("final_coverage") or {}
    states = coverage.get("state_counts") or {}
    if int(coverage.get("achievement_count") or 0) != int(
        coverage_contract.get("achievement_count") or 0
    ):
        errors.append("achievement scope count drift")
    if int(states.get("partial") or 0) != int(coverage_contract.get("partial_count") or 0):
        errors.append("partial achievement count drift")
    if int(states.get("uncovered") or 0) != int(
        coverage_contract.get("uncovered_count") or 0
    ):
        errors.append("uncovered achievement count drift")

    contract_report = coverage.get("verified_success_contracts") or {}
    if str(contract_report.get("status") or "") != str(
        coverage_contract.get("contract_status") or ""
    ):
        errors.append("verified success contract status drift")
    if int(contract_report.get("failed_contract_count") or 0) != int(
        coverage_contract.get("failed_contract_count") or 0
    ):
        errors.append("verified success contract failure count drift")

    debt_rows: list[dict[str, Any]] = []
    for row in [
        *(coverage.get("partial_achievements") or []),
        *(coverage.get("uncovered_achievements") or []),
    ]:
        if not isinstance(row, dict):
            continue
        debt_rows.append(
            {
                "id": row.get("id"),
                "state": row.get("state"),
                "missing": row.get("missing"),
            }
        )
    debt_rows.sort(key=lambda row: int(row.get("id") or 0))
    coverage_digest = _digest(debt_rows)
    if coverage_digest != str(coverage_contract.get("debt_sha256") or ""):
        errors.append("final coverage baseline fingerprint drift")

    return {
        "schema_version": 1,
        "status": "PASS_BASELINE_NON_REGRESSION" if not errors else "FAIL",
        "raw_integrity_verdict": raw_verdict,
        "candidate_sha": candidate_sha,
        "base_ref": base_ref,
        "resolved_base": resolved_base,
        "baseline_id": baseline.get("baseline_id"),
        "baseline_debt": sorted(blockers),
        "protected_changes": protected,
        "prerequisite_fingerprint": pre_digest,
        "coverage_fingerprint": coverage_digest,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Enforce Phase 2 certification while carrying only the exact, frozen "
            "Guide BUILDING debt already present on the Phase 1 base."
        )
    )
    parser.add_argument("--integrity-report", type=Path, required=True)
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument(
        "--prerequisite-report",
        type=Path,
        default=ROOT / "artifacts" / "ci_guide_ultime_logs" / "prerequisite_order.json",
    )
    parser.add_argument(
        "--coverage-report",
        type=Path,
        default=ROOT / "artifacts" / "ci_guide_ultime_logs" / "final_coverage.json",
    )
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    integrity = _load_json(args.integrity_report)
    baseline = _load_json(args.baseline)
    prerequisite = _load_json(args.prerequisite_report)
    coverage = _load_json(args.coverage_report)
    manifest = _load_json(MANIFEST)
    resolved_base = _run_git(["rev-parse", "--verify", f"{args.base_ref}^{{commit}}"])
    changed = _changed_paths(args.base_ref)

    report = evaluate_phase(
        integrity=integrity,
        baseline=baseline,
        prerequisite=prerequisite,
        coverage=coverage,
        manifest=manifest,
        base_ref=args.base_ref,
        resolved_base=resolved_base,
        candidate_sha=args.candidate_sha,
        changed=changed,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["status"] in {"PASS", "PASS_BASELINE_NON_REGRESSION"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
