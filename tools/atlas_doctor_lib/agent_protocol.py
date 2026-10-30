from __future__ import annotations

"""Compact, stable Atlas Doctor protocol for coding agents."""

from pathlib import Path
from typing import Any, Iterable

from .core import git_state


PROTOCOL = "atlas-doctor-agent/v1"
STATUSES = ("READY", "PASS", "REVIEW", "BLOCKED", "FAIL")
PROTECTED_PATHS = (
    "data/local/zaaps.json",
    ".github/workflows/",
    ".github/rulesets/",
    "tools/atlas_integrity_policy.json",
    "PHASE_CERTIFICATION.md",
)
FORBIDDEN_CLAIMS = (
    "Do not claim FULL_CERTIFIED from a plan, check, targeted validation or local JSON.",
    "Do not claim a file is dead from graph isolation or missing static references alone.",
    "Do not hide failures with skip, xfail, ignore, whitelist or weakened gates.",
    "Do not modify persistent user data without an explicit compatibility or migration proof.",
)


def _unique(values: Iterable[str], *, limit: int = 80) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))[:limit]


def _status(value: str, *, automation_safe: bool = False) -> str:
    value = str(value).upper()
    if value in {"FAIL"}:
        return "FAIL"
    if value in {"BLOCKED"}:
        return "BLOCKED"
    if value in {"PASS", "FOCUSED_CHECKED"}:
        return "PASS"
    if value in {"READY", "READY_TO_RUN_SCOPED"} and automation_safe:
        return "READY"
    return "REVIEW"


def _exit_code(status: str) -> int:
    return 0 if status in {"READY", "PASS"} else 1 if status == "REVIEW" else 2


def _plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    architecture = plan.get("architecture_preflight") or {}
    return {
        "risk": (plan.get("risk") or {}).get("risk", "UNKNOWN"),
        "level": plan.get("level", "UNKNOWN"),
        "integrity_mode": plan.get("minimum_integrity_mode", "FAST"),
        "graph_required": bool(architecture.get("required")),
        "graph_status": architecture.get("status", "OPTIONAL"),
        "tests": _unique(plan.get("execution_tests", []), limit=40),
        "rules": _unique(plan.get("rules", []), limit=30),
    }


def _review_causes(plan: dict[str, Any], result: dict[str, Any]) -> list[str]:
    causes: list[str] = []
    direct = result.get("primary_cause") or result.get("reason") or plan.get("reason")
    if direct:
        causes.append(str(direct))
    ownership = plan.get("ownership") or {}
    unresolved = _unique([
        *ownership.get("unowned_paths", []),
        *ownership.get("ambiguous_paths", []),
    ], limit=20)
    if unresolved:
        causes.append("Resolve scope ownership before editing: " + ", ".join(unresolved))
    for field, label in (
        ("unsafe_recommended_tools", "Unsafe tools require review"),
        ("non_automated_recommended_tools", "Tools are not automation-ready"),
        ("missing_validation_tools", "Required validation tools are missing"),
    ):
        values = _unique(plan.get(field, []), limit=20)
        if values:
            causes.append(label + ": " + ", ".join(values))
    source = plan.get("source_diagnostics") or {}
    if source.get("status") in {"FAIL", "REVIEW"}:
        causes.append("Inspect incomplete or invalid source diagnostics before editing.")
    return _unique(causes, limit=10)


def _source_provenance(plan: dict[str, Any], state: dict[str, Any],
                       result: dict[str, Any], checks: dict[str, Any]) -> dict[str, Any]:
    """Agent-readable evidence; AST source anchors are never defect findings."""
    inventory = plan.get("source_diagnostics") or {}
    raw_files = inventory.get("files") if isinstance(inventory, dict) else None
    anchors: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    if isinstance(raw_files, list):
        for file in raw_files[:40]:
            if not isinstance(file, dict) or not isinstance(file.get("path"), str):
                continue
            path = file["path"]
            symbols = file.get("symbols")
            if isinstance(symbols, list):
                for symbol in symbols[:80]:
                    if not isinstance(symbol, dict):
                        continue
                    name, line = symbol.get("name"), symbol.get("line")
                    if isinstance(name, str) and type(line) is int and line > 0:
                        anchors.append({
                            "path": path, "symbol": name, "line": line,
                            "evidence_level": "SOURCE_DEFINITION_ONLY",
                        })
            if file.get("status") == "FAIL":
                findings.append({
                    "path": path, "symbol": None, "line": None,
                    "status": "FAIL", "reason": str(file.get("reason") or "SOURCE_ERROR"),
                    "priority": "UNASSESSED", "proposed_action": "Inspect source error",
                    "selected_tests": checks["tests"],
                    "ci_run_url": None, "independently_attested": False,
                })
    return {
        "schema_version": 1,
        "source_sha": state["head"],
        "source_inventory_status": inventory.get("status", "NOT_PROVIDED") if isinstance(inventory, dict) else "BLOCKED",
        "source_anchors": anchors[:100],
        "diagnostics": findings[:40],
        "selected_tests": checks["tests"],
        "execution_status": result.get("status", "NOT_RUN"),
        "ci_run_url": None,
        "ci_run_id": None,
        "independent_ci_attested": False,
        "limits": (
            "Source anchors are AST inventory, not proven defects. Missing line, "
            "function, priority, run link or attestation stays null/UNASSESSED; "
            "local check and scoped validation never certify the release."
        ),
    }


def _verified_check_modules(result: dict[str, Any]) -> list[str]:
    """Export names ONLY if the focused unittest process actually passed.

    A boolean tests_executed=True is not proof of which tests ran. Reconcile
    execution and selection modules from the same bounded development run.
    """
    if not isinstance(result, dict) or result.get("status") != "FOCUSED_CHECKED":
        return []
    execution = result.get("targeted_test_execution")
    selection = result.get("targeted_test_selection")
    if not isinstance(execution, dict) or not isinstance(selection, dict):
        return []
    modules = execution.get("modules")
    selected = selection.get("selected")
    if (execution.get("status") != "PASS"
            or execution.get("tests_executed") is not True
            or result.get("tests_executed") is not True
            or type(execution.get("exit_code")) is not int
            or execution["exit_code"] != 0
            or selection.get("status") != "READY"
            or not isinstance(modules, list) or not 1 <= len(modules) <= 100
            or modules != selected
            or any(type(name) is not str or not 1 <= len(name) <= 240
                   or not name.startswith("tests.")
                   or not all(part.isidentifier() for part in name.split("."))
                   for name in modules)
            or len(set(modules)) != len(modules)):
        return []
    return modules


def _envelope(root: Path, *, action: str, paths: list[str], base_ref: str,
              plan: dict[str, Any], result: dict[str, Any] | None = None) -> dict[str, Any]:
    from .guardian_packs import guardian_plan

    state = git_state(root)
    result = result or {}
    raw_status = result.get("status", plan.get("status", "REVIEW"))
    status = _status(raw_status, automation_safe=bool(plan.get("automation_safe")))
    # Never turn an unqualified boolean into scoped PASS. In the focused
    # development path, independently reconcile the actual unittest module
    # list with the modules selected before running it.
    check_modules = _verified_check_modules(result) if action == "check" else []
    if action == "check" and status == "PASS" and not check_modules:
        status = "REVIEW"
    requested = _unique(paths)
    planned = _unique(plan.get("paths", requested))
    checks = _plan_summary(plan)
    next_actions = []
    if checks["graph_required"] and checks["graph_status"] != "PASS":
        next_actions.append("Rebuild and inspect exact-SHA Graphify evidence before structural edits.")
    if status in {"BLOCKED", "FAIL", "REVIEW"}:
        next_actions.extend(_review_causes(plan, result))
    if not next_actions:
        if status == "READY":
            next_actions.append("Apply only the requested change, then run `doctor agent check`.")
        elif status == "PASS" and action == "validate":
            next_actions.append("Scoped validation passed; await required CI and exact-SHA certification.")
        elif status == "PASS":
            next_actions.append("Focused checks passed; run `doctor agent validate` before proposing merge.")
        else:
            next_actions.append(
                "Inspect the full plan evidence; automatic editing is not authorized while status is REVIEW."
            )
    certification = "SCOPED_VALIDATED" if action == "validate" and status == "PASS" else "NOT_RUN"
    payload = {
        "schema_version": 1,
        "protocol": PROTOCOL,
        "action": action,
        "status": status,
        "exit_code": _exit_code(status),
        "exact_sha": state["head"],
        "base_ref": base_ref,
        "worktree": {"dirty": state["dirty"], "dirty_digest": state["dirty_digest"]},
        "edit_contract": {
            "requested_paths": requested,
            "planned_paths": planned,
            "expansion_requires_replan": True,
            "protected_paths": list(PROTECTED_PATHS),
        },
        "selected_checks": checks,
        "source_evidence": _source_provenance(plan, state, result, checks),
        "guardians": guardian_plan(plan),
        "budgets": {
            "save_seconds": 1,
            "pre_commit_seconds": 10,
            "pre_push_seconds": 90,
            "full_during_development": False,
        },
        "certification": {
            "status": certification,
            "full_certified": False,
            "release_certified": False,
            "exact_sha_required": True,
        },
        "next_actions": _unique(next_actions, limit=10),
        "forbidden_claims": list(FORBIDDEN_CLAIMS),
    }
    if action in {"check", "validate"}:
        payload["execution"] = {
            "status": result.get("status", "NOT_RUN"),
            "checks": result.get("checks", []),
            "tests_executed": check_modules if action == "check" else result.get("tests_executed", []),
            "duration_ms": result.get("duration_ms"),
        }
    if action == "explain":
        payload["explanation"] = {
            "planning_reasons": _unique(plan.get("planning_reasons", []), limit=12),
            "ownership": plan.get("ownership", {}),
            "policy": plan.get("policy", {}),
        }
    return payload


def run_agent_action(
    root: Path,
    *,
    action: str,
    paths: Iterable[str],
    base_ref: str = "HEAD",
    structural: bool = False,
    level: str | None = None,
    run_tests: bool = False,
    max_tests: int = 8,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    """Compose existing Agent and Doctor engines; never create a parallel gate."""
    from tools import agent

    normalized = _unique(paths)
    if not normalized:
        return {
            "schema_version": 1, "protocol": PROTOCOL, "action": action,
            "status": "BLOCKED", "exit_code": 2,
            "reason": "At least one repository-relative path is required.",
            "source_evidence": {"schema_version": 1, "source_inventory_status": "NOT_RUN",
                                "source_anchors": [], "diagnostics": [], "independent_ci_attested": False},
            "forbidden_claims": list(FORBIDDEN_CLAIMS),
        }
    try:
        plan = agent.plan_payload(
            root, normalized, level=level, structural=structural,
            base_ref=base_ref,
        )
        if action in {"plan", "explain"}:
            return _envelope(root, action=action, paths=normalized,
                             base_ref=base_ref, plan=plan)
        if action == "check":
            from .development_preflight import development_preflight
            result = development_preflight(
                root, base_ref=base_ref, run_tests=run_tests,
                max_tests=max_tests, timeout_seconds=timeout_seconds,
            )
        elif action == "validate":
            result = agent.verify_payload(
                root, normalized, level=level, structural=structural,
                base_ref=base_ref, prepared_plan=plan,
            )
        else:
            raise ValueError(f"Unsupported agent action: {action}")
        return _envelope(root, action=action, paths=normalized,
                         base_ref=base_ref, plan=plan, result=result)
    except (agent.AgentConfigError, OSError, RuntimeError, ValueError) as exc:
        return {
            "schema_version": 1, "protocol": PROTOCOL, "action": action,
            "status": "BLOCKED", "exit_code": 2, "reason": str(exc),
            "source_evidence": {"schema_version": 1, "source_inventory_status": "BLOCKED",
                                "source_anchors": [], "diagnostics": [], "independent_ci_attested": False},
            "forbidden_claims": list(FORBIDDEN_CLAIMS),
        }
