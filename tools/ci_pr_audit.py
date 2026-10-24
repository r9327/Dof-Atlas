from __future__ import annotations

"""Read-only impact review of a Doctor CI plan; NEVER merge authorization."""

import argparse
import json
from pathlib import Path
import re

SHA = re.compile(r"^[0-9a-f]{40}$")


def safe(value: object) -> str:
    return str(value).replace(chr(10), " ").replace(chr(13), " ").replace("|", "/").replace(chr(96), "'")[:220]


def audit_plan(plan: dict) -> dict:
    """Report observable routing risks and gaps, without claiming source review."""
    if not isinstance(plan, dict):
        raise ValueError("Missing Doctor CI plan")
    if not SHA.fullmatch(str(plan.get("candidate_sha", ""))) or not SHA.fullmatch(str(plan.get("base_sha", ""))):
        raise ValueError("Plan has no exact SHA/base")
    changed, deleted = plan.get("changed_paths"), plan.get("deleted_paths")
    required, workflows = plan.get("required_jobs"), plan.get("workflows")
    if (not isinstance(changed, list) or not changed or
            not all(isinstance(x, str) for x in changed) or
            not isinstance(deleted, list) or not all(isinstance(x, str) for x in deleted) or
            not isinstance(required, list) or not all(isinstance(x, str) for x in required) or
            not isinstance(workflows, dict)):
        raise ValueError("Doctor plan missing essential change or job inventory")
    phase = plan.get("phase_route") if isinstance(plan.get("phase_route"), dict) else {}
    ui = plan.get("ui_plan") if isinstance(plan.get("ui_plan"), dict) else {}
    root_of_trust = phase.get("root_of_trust_changes", [])
    if not isinstance(root_of_trust, list):
        root_of_trust = []
    sensitive = sorted(set(root_of_trust) | {
        p for p in changed if p.startswith((".github/workflows/", ".github/rulesets/"))
        or p in {"tools/ci_scope_gate.py", "tools/ci_required_certification.py",
                 "tools/atlas_integrity.py", "tools/phase_adaptive_gate.py"}
    })
    ui_uncertainty = ui.get("uncertainty", [])
    if not isinstance(ui_uncertainty, list):
        ui_uncertainty = []
    selected_ui_scenarios = ui.get("selected_scenarios", [])
    if not isinstance(selected_ui_scenarios, list):
        selected_ui_scenarios = []
    recommended_tests = ui.get("recommended_tests", [])
    if not isinstance(recommended_tests, list):
        recommended_tests = []
    uncovered = phase.get("uncovered_paths", [])
    if not isinstance(uncovered, list):
        uncovered = []
    unclassified = phase.get("unclassified_paths", [])
    if not isinstance(unclassified, list):
        unclassified = []
    categories = {
        prefix: sum(x.startswith(prefix + "/") for x in changed)
        for prefix in ("app", "tests", "tools", "docs", ".github")
    }
    findings = []
    if deleted:
        findings.append({"level": "HIGH", "code": "REMOVED_OR_RENAMED",
                         "detail": f"{len(deleted)} paths removed or changed type; FULL required"})
    if sensitive:
        findings.append({"level": "HIGH", "code": "CI_TRUST_SURFACE",
                         "detail": f"{len(sensitive)} policy/CI files need strict validation"})
    if unclassified:
        findings.append({"level": "HIGH", "code": "UNCLASSIFIED_PATHS",
                         "detail": f"{len(unclassified)} paths lack an owner"})
    if uncovered:
        findings.append({"level": "HIGH", "code": "UNMAPPED_TESTS",
                         "detail": f"{len(uncovered)} paths lack test mapping"})
    if ui.get("status") == "REVIEW_REQUIRED" or ui_uncertainty:
        findings.append({"level": "HIGH", "code": "UI_IMPACT_UNPROVEN",
                         "detail": f"{len(ui_uncertainty)} UI import/dependency uncertainties; independent UI contracts mandatory"})
    if root_of_trust:
        findings.append({"level": "HIGH", "code": "ROOT_OF_TRUST_CHANGED",
                         "detail": f"{len(root_of_trust)} host-verified CI/trust owners changed"})
    if phase.get("route") not in {"SCOPED", "FULL", "FULL_REQUIRED", "SMART"}:
        findings.append({"level": "HIGH", "code": "UNKNOWN_ROUTE",
                         "detail": "Canonical Phase routing is unavailable"})
    if plan.get("specialist_fallback"):
        findings.append({"level": "INFO", "code": "BROAD_SPECIALISTS",
                         "detail": "Full specialist fallback required"})
    selected = [n for n, item in workflows.items()
                if isinstance(item, dict) and item.get("selected") is True]
    reasons = phase.get("reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    return {
        "schema_version": 1, "kind": "atlas_pr_mini_audit",
        "status": "REVIEW_REQUIRED" if any(f["level"] == "HIGH" for f in findings) else "OBSERVED",
        "candidate_sha": plan["candidate_sha"], "base_sha": plan["base_sha"],
        "risk": safe(plan.get("risk", "UNVERIFIED")),
        "phase_route": safe(phase.get("route", "UNVERIFIED")),
        "ui_status": safe(ui.get("status", "UNVERIFIED")),
        "changed_paths": changed, "deleted_paths": deleted,
        "sensitive_paths": sensitive, "root_of_trust_paths": root_of_trust,
        "ui_uncertainty": [safe(x) for x in ui_uncertainty[:40]],
        "selected_ui_scenarios": [safe(x) for x in selected_ui_scenarios[:40]],
        "recommended_tests": [safe(x) for x in recommended_tests[:50]],
        "uncovered_paths": uncovered,
        "unclassified_paths": unclassified, "categories": categories,
        "phase_reasons": [safe(x) for x in reasons[:30]],
        "selected_specialists": selected, "required_jobs": required,
        "findings": findings, "tests_executed": False,
        "phase_certified": False, "merge_authorized": False,
        "full_suite_waived": False,
        "limitations": "Advisory diff/coverage/routing inventory, not security review or test certification.",
    }


def render(report: dict) -> str:
    lines = [
        "", "### PR mini-audit — exact-SHA change impact (advisory)", "",
        f"- Risk: **{safe(report['risk'])}**; Phase route: {safe(report['phase_route'])}; UI: {safe(report['ui_status'])}",
        f"- Changes: **{len(report['changed_paths'])}**; removed/type-changed: **{len(report['deleted_paths'])}**; sensitive: **{len(report['sensitive_paths'])}**",
        f"- Required jobs: **{len(report['required_jobs'])}**; selected specialists: **{len(report['selected_specialists'])}**",
        f"- Review flags: **{len(report['findings'])}**; advisory status: **{report['status']}**",
    ]
    for finding in report["findings"][:15]:
        lines.append(f"- [{finding['level']}] {finding['code']}: {safe(finding['detail'])}")
    for reason in report["phase_reasons"][:12]:
        lines.append("- Route constraint: " + safe(reason))
    if report["ui_uncertainty"]:
        lines.append("- UI impact uncertainties (up to 12):")
        for reason in report["ui_uncertainty"][:12]:
            lines.append("  - " + safe(reason))
    if report["selected_ui_scenarios"]:
        lines.append("- Selected UI scenarios: " + ", ".join(safe(x) for x in report["selected_ui_scenarios"][:12]))
    if report["recommended_tests"]:
        lines.append("- Tests suggested by Doctor (not executed here): " + ", ".join(
            safe(x) for x in report["recommended_tests"][:14]))
    lines.extend(["", "| Changed path | Reason to inspect |", "|---|---|"])
    for path in report["changed_paths"][:35]:
        tags = []
        for key, label in (
            ("deleted_paths", "removed / type-changed"),
            ("sensitive_paths", "CI/trust policy"),
            ("unclassified_paths", "unclassified"),
            ("uncovered_paths", "test mapping unproven"),
        ):
            if path in report[key]:
                tags.append(label)
        lines.append(f"| {safe(path)} | {', '.join(tags) if tags else 'Doctor routing applies'} |")
    if len(report["changed_paths"]) > 35:
        lines.append(f"- {len(report['changed_paths']) - 35} further paths included in JSON artifact.")
    lines.append("")
    lines.append("Selection and findings are NOT test execution, deep source/security review, or certification.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    report = audit_plan(json.loads(args.plan.read_text(encoding="utf-8")))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with args.summary.open("a", encoding="utf-8") as stream:
        stream.write(render(report))
    print(f"PR mini-audit: {report['status']} with {len(report['findings'])} findings; not certification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
