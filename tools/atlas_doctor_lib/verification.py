from __future__ import annotations

"""Doctor executes Agent plans; existing engines retain their validation contracts."""

import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .core import git_state, load_json, milliseconds, run_git, utc_now, write_json
from .gates import run_integrity_gate


def _run_command(root: Path, key: str, command: list[str], *, timeout: int = 900) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"key": key, "status": "REVIEW", "command": command,
                "duration_ms": milliseconds(started), "reason": str(exc),
                "failure_ids": [], "stdout_tail": [], "stderr_tail": []}
    output = completed.stdout + "\n" + completed.stderr
    failed = []
    for name, context in re.findall(r"^(?:FAIL|ERROR): (\w+) \(([^)]+)\)", output, re.MULTILINE):
        failed.append(context if context.endswith("." + name) else context + "." + name)
    return {"key": key, "status": "PASS" if completed.returncode == 0 else "FAIL",
            "command": command, "returncode": completed.returncode,
            "duration_ms": milliseconds(started), "failure_ids": sorted(set(failed)),
            "reason": None if completed.returncode == 0 else f"{key} exited with code {completed.returncode}.",
            "stdout_tail": completed.stdout.splitlines()[-40:],
            "stderr_tail": completed.stderr.splitlines()[-40:]}


def _python_command(command: list[str]) -> list[str]:
    if command[:2] != ["py", "-3.13"]:
        raise ValueError("Expected a canonical Python module command.")
    return [sys.executable, "-X", "faulthandler", *command[2:]]


def _review_reasons(plan: dict[str, Any]) -> list[str]:
    reasons = []
    ownership = plan.get("ownership") or {}
    if ownership.get("review_required"):
        reasons.append("Ownership remains unowned or ambiguous: " + ", ".join(
            [*ownership.get("unowned_paths", []), *ownership.get("ambiguous_paths", [])]))
    source = plan.get("source_diagnostics") or {}
    if source.get("status") == "REVIEW":
        reasons.append("Targeted source inspection reached its file budget.")
    architecture = plan.get("architecture_preflight") or {}
    graph = architecture.get("graph") or {}
    impact = architecture.get("impact") or {}
    if architecture.get("required") and graph.get("status") != "PASS":
        reasons.append(graph.get("reason") or "Required current graph is unavailable.")
    if impact and impact.get("status") != "PASS":
        reasons.append(impact.get("reason") or "Graph consumers require source/contract review.")
    if architecture.get("required") and not impact and plan.get("status") == "REVIEW_REQUIRED":
        reasons.append("Structural consumer coverage is insufficient.")
    return reasons


def _resolved_commit(root: Path, base_ref: str) -> tuple[str | None, str | None]:
    try:
        resolved = run_git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    except RuntimeError as exc:
        return None, str(exc)
    return resolved or None, None


def _comparison_key(
    plan: dict[str, Any], *, base_ref: str, base_sha: str | None,
) -> dict[str, Any]:
    architecture = plan.get("architecture_preflight") or {}
    return {
        "base_ref": base_ref,
        "base_sha": base_sha,
        "requested_paths": sorted(
            str(path) for path in (plan.get("requested_paths") or plan.get("paths") or [])
        ),
        "scopes": sorted(str(scope) for scope in plan.get("scopes", [])),
        "level": str(plan.get("level", "UNKNOWN")),
        "integrity_mode": str(
            plan.get("integrity_mode") or plan.get("minimum_integrity_mode") or "UNKNOWN"
        ).upper(),
        "structural": bool(architecture.get("required")),
        "validation_authority": "tools.atlas_integrity",
    }


def compare_verifications(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """Compare only verification runs that share an explicit execution contract."""
    if not previous:
        return {
            "status": "UNAVAILABLE",
            "comparable": False,
            "reason": "No previous verification snapshot is available.",
            "new_non_pass": [],
            "recovered": [],
            "status_changes": [],
        }
    if previous.get("schema_version") != 1 or previous.get("kind") != "verification":
        return {
            "status": "UNAVAILABLE",
            "comparable": False,
            "reason": "Previous verification uses an incompatible schema or kind.",
            "new_non_pass": [],
            "recovered": [],
            "status_changes": [],
        }
    previous_key = previous.get("comparison_key")
    current_key = current.get("comparison_key")
    if not isinstance(previous_key, dict) or previous_key != current_key:
        differing = []
        if isinstance(previous_key, dict) and isinstance(current_key, dict):
            differing = sorted(
                key for key in set(previous_key) | set(current_key)
                if previous_key.get(key) != current_key.get(key)
            )
        return {
            "status": "UNAVAILABLE",
            "comparable": False,
            "reason": "Verification contracts differ; use the same explicit base, targets and work depth.",
            "differing_fields": differing,
            "new_non_pass": [],
            "recovered": [],
            "status_changes": [],
        }

    previous_checks = {
        str(row.get("key")): str(row.get("status"))
        for row in previous.get("checks", [])
        if row.get("key")
    }
    current_checks = {
        str(row.get("key")): str(row.get("status"))
        for row in current.get("checks", [])
        if row.get("key")
    }
    changes = [
        {"key": key, "previous": previous_checks.get(key), "current": current_checks.get(key)}
        for key in sorted(set(previous_checks) | set(current_checks))
        if previous_checks.get(key) != current_checks.get(key)
    ]
    new_non_pass = [
        row for row in changes
        if row["current"] not in {None, "PASS"} and row["previous"] in {None, "PASS"}
    ]
    recovered = [
        row for row in changes
        if row["current"] == "PASS" and row["previous"] not in {None, "PASS"}
    ]
    if new_non_pass:
        status = "REGRESSION"
    elif recovered:
        status = "IMPROVED"
    else:
        status = "STABLE"
    return {
        "status": status,
        "comparable": True,
        "reason": None,
        "previous_status": previous.get("status"),
        "current_status": current.get("status"),
        "new_non_pass": new_non_pass,
        "recovered": recovered,
        "status_changes": changes,
    }


def _check_duration_ms(check: dict[str, Any]) -> float:
    value = check.get("duration_ms")
    if isinstance(value, (int, float)):
        return float(value)
    seconds = check.get("duration_seconds")
    if isinstance(seconds, (int, float)):
        return round(float(seconds) * 1000.0, 3)
    return 0.0


def _cost_evidence(
    plan: dict[str, Any],
    checks: list[dict[str, Any]],
    *,
    total_duration_ms: float,
) -> dict[str, Any]:
    measured = [
        {"key": str(check.get("key", "unknown")), "duration_ms": _check_duration_ms(check)}
        for check in checks
    ]
    measured.sort(key=lambda row: row["duration_ms"], reverse=True)
    return {
        "total_duration_ms": total_duration_ms,
        "checks_duration_ms": round(sum(row["duration_ms"] for row in measured), 3),
        "slowest_checks": measured[:5],
        "planned_tool_cost_hints": [
            {
                "path": row.get("path"),
                "cost_hint": row.get("cost_hint"),
                "mode": row.get("mode"),
            }
            for row in plan.get("recommended_tools", [])
        ],
        "planner_catalog_cache": plan.get("planner_cache") or {"status": "UNKNOWN"},
        "validation_reused": False,
    }


def _actionable_diagnostics(
    checks: list[dict[str, Any]],
    reviews: list[str],
) -> list[dict[str, Any]]:
    diagnostics = []
    for check in checks:
        if check.get("status") == "PASS":
            continue
        diagnostics.append({
            "key": check.get("key"),
            "status": check.get("status"),
            "reason": check.get("reason") or f"{check.get('key', 'check')} requires review.",
            "failure_ids": list(check.get("failure_ids", [])),
            "reproduction_command": list(check.get("command", [])),
            "next_action": "Reproduce this exact check and inspect its recorded evidence before changing source.",
        })
    for reason in reviews:
        diagnostics.append({
            "key": "review",
            "status": "REVIEW",
            "reason": reason,
            "failure_ids": [],
            "reproduction_command": [],
            "next_action": "Resolve the recorded review condition, then rerun the same verification contract.",
        })
    return diagnostics


def execute_plan(
    root: Path, plan: dict[str, Any], *, base_ref: str = "HEAD",
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    started = time.perf_counter()
    state = git_state(root)
    previous_verification = load_json(root, "latest_verification")
    base_sha, baseline_error = _resolved_commit(root, base_ref)
    checks: list[dict[str, Any]] = []
    tools_executed: list[str] = []
    tests_executed: list[str] = []
    reviews = _review_reasons(plan)
    blocking_plan = [
        *plan.get("unsafe_recommended_tools", []),
        *plan.get("non_automated_recommended_tools", []),
        *plan.get("missing_validation_tools", []),
    ]
    if baseline_error:
        reviews.append("Baseline cannot be resolved: " + baseline_error)
        blocking_plan.append("baseline")
    if blocking_plan:
        reviews.append("Unsafe, unsupported or missing canonical engines: " + ", ".join(blocking_plan))
    if preflight is not None and preflight.get("status") != "PASS":
        reviews.append("Agent/AI Context preflight failed: " + "; ".join(preflight.get("errors", [])))
        blocking_plan.append("agent_preflight")
    source = plan.get("source_diagnostics") or {}
    if source.get("status") == "FAIL":
        checks.append({"key": "source", "status": "FAIL", "command": [sys.executable, "-m", "tools.agent", "plan", *plan.get("paths", []), "--json"],
                       "reason": "Current Python source could not be parsed.",
                       "evidence": source.get("errors", []), "failure_ids": []})
    authority = next((row for row in plan.get("recommended_tools", [])
                      if row.get("path") == "tools/atlas_integrity.py"), None)
    if authority is None and "tools/atlas_integrity.py" not in blocking_plan:
        blocking_plan.append("tools/atlas_integrity.py")
        reviews.append("Canonical Atlas Integrity authority is missing.")
    for row in plan.get("recommended_tools", []):
        if not row.get("safe_for_agent") or not row.get("automation_ready"):
            blocking_plan.append(str(row.get("path")))
        if row.get("side_effects") not in {"read_only", "artifact_output"}:
            blocking_plan.append(str(row.get("path")))
            reviews.append("Repository mutation is never executed by verify.")

    def can_continue() -> bool:
        return not blocking_plan and not any(check["status"] != "PASS" for check in checks)

    if can_continue():
        checks.append(_run_command(root, "ai_context", [sys.executable, "-m", "tools.ai_context", "check"]))
        tools_executed.append("tools/ai_context.py")
    modules = list(plan.get("execution_tests", plan.get("recommended_tests", [])))
    if can_continue() and modules:
        if not all(re.fullmatch(r"tests\.test_[A-Za-z0-9_]+", module) for module in modules):
            checks.append({"key": "tests", "status": "REVIEW", "command": [],
                           "reason": "Invalid targeted test module metadata.", "failure_ids": []})
        else:
            checks.append(_run_command(root, "tests",
                [sys.executable, "-X", "faulthandler", "-m", "unittest", "-v", *modules]))
            tests_executed = modules
    for row in plan.get("recommended_tools", []):
        path = row.get("path", "")
        if path == "tools/atlas_integrity.py" or not can_continue():
            continue
        if not re.fullmatch(r"tools/[A-Za-z0-9_/]+\.py", path) or ".." in path:
            raise ValueError("Invalid canonical tool path in plan.")
        command = list(row.get("command") or [])
        expected = path[:-3].replace("/", ".")
        if len(command) < 5 or command[:3] != ["py", "-3.13", "-m"] or command[3] != expected:
            raise ValueError("Selected command does not match its canonical engine.")
        checks.append(_run_command(root, path, _python_command(command),
                                   timeout=3600 if plan.get("level") == "HARD" else 900))
        tools_executed.append(path)
    if can_continue():
        mode = str(plan.get("integrity_mode") or plan["minimum_integrity_mode"]).casefold()
        gate = run_integrity_gate(root, mode, base_ref=base_ref,
                                  timeout=7200 if mode in {"full", "deep"} else 900)
        gate["key"] = "atlas_integrity"
        if gate.get("status") not in {"PASS", "FAIL"}:
            gate["status"] = "REVIEW"
        elif gate.get("status") == "FAIL" and not gate.get("report"):
            gate["status"] = "REVIEW"
        gate["failure_ids"] = list((gate.get("report") or {}).get("blockers", []))
        gate["reason"] = gate.get("reason") or (
            ", ".join(str(item) for item in gate["failure_ids"])
            if gate["failure_ids"] else None)
        checks.append(gate)
        tools_executed.append("tools/atlas_integrity.py")
    final_state = git_state(root)
    if final_state["head"] != state["head"] or final_state["dirty_digest"] != state["dirty_digest"]:
        reviews.append("Repository changed during verification; results require a fresh run.")
    status = "FAIL" if any(row["status"] == "FAIL" for row in checks) else (
        "REVIEW" if reviews or not checks or any(row["status"] != "PASS" for row in checks) else "PASS")
    failed = next((row for row in checks if row["status"] != "PASS"), None)
    if failed:
        cause = failed.get("reason") or failed["key"] + " has insufficient evidence."
        diagnosis = {"certainty": "OBSERVED_FAILURE" if status == "FAIL" else "UNKNOWN",
                     "check": failed["key"], "failure_ids": failed.get("failure_ids", []),
                     "evidence": failed.get("evidence", []), "command": failed.get("command", []),
                     "stdout_tail": failed.get("stdout_tail", []), "stderr_tail": failed.get("stderr_tail", [])}
    else:
        cause = "; ".join(reviews) if reviews else None
        diagnosis = {"certainty": "REVIEW" if reviews else "PASS"}

    duration_ms = milliseconds(started)
    comparison_key = _comparison_key(plan, base_ref=base_ref, base_sha=base_sha)
    architecture = plan.get("architecture_preflight") or {}
    graph = architecture.get("graph") or {}
    payload = {
        "schema_version": 1, "kind": "verification", "source": "tools.atlas_doctor_lib.verification",
        "generated_at": utc_now(), "status": status, "level": plan.get("level", "UNKNOWN"),
        "git": state, "base_ref": base_ref,
        "baseline": {
            "requested_ref": base_ref,
            "resolved_sha": base_sha,
            "resolution_status": "PASS" if base_sha else "REVIEW",
            "reason": baseline_error,
        },
        "comparison_key": comparison_key,
        "scopes": plan.get("scopes", []),
        "paths": plan.get("paths", []), "requested_paths": plan.get("requested_paths", []),
        "risk": plan.get("risk"), "depth": plan.get("depth"), "architecture": architecture,
        "checks": checks, "tests_executed": tests_executed, "tools_executed": tools_executed,
        "tests_delegated_to_integrity": plan.get("tests_delegated_to_integrity", False),
        "early_stop": bool(blocking_plan or failed), "review_reasons": reviews,
        "primary_cause": cause, "diagnosis": diagnosis, "duration_ms": duration_ms,
        "next_action": "Reproduce the recorded failing check; inspect its evidence before changing code."
            if failed else "Review ownership/graph limits, then rerun verify." if reviews else None,
        "validation_authority": "tools.atlas_integrity",
        "diagnostics": _actionable_diagnostics(checks, reviews),
        "cost": _cost_evidence(plan, checks, total_duration_ms=duration_ms),
        "cache": {
            "planner_catalog": plan.get("planner_cache") or {"status": "UNKNOWN"},
            "graph_status": graph.get("status") if isinstance(graph, dict) else None,
            "validation_reused": False,
            "rule": "Only derived planning/graph evidence may be cached; current validation checks are executed.",
        },
    }
    payload["comparison"] = compare_verifications(previous_verification, payload)
    write_json(root, "latest_verification", payload, rotate=True)
    return payload
