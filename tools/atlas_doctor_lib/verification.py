from __future__ import annotations

"""Doctor executes Agent plans; existing engines retain their validation contracts."""
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .core import git_state, milliseconds, utc_now, write_json
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


def execute_plan(
    root: Path, plan: dict[str, Any], *, base_ref: str = "HEAD",
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    started = time.perf_counter()
    state = git_state(root)
    checks: list[dict[str, Any]] = []
    tools_executed: list[str] = []
    tests_executed: list[str] = []
    reviews = _review_reasons(plan)
    blocking_plan = [
        *plan.get("unsafe_recommended_tools", []),
        *plan.get("non_automated_recommended_tools", []),
        *plan.get("missing_validation_tools", []),
    ]
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
    payload = {
        "schema_version": 1, "kind": "verification", "source": "tools.atlas_doctor_lib.verification",
        "generated_at": utc_now(), "status": status, "level": plan.get("level", "UNKNOWN"),
        "git": state, "base_ref": base_ref, "scopes": plan.get("scopes", []),
        "paths": plan.get("paths", []), "requested_paths": plan.get("requested_paths", []),
        "risk": plan.get("risk"), "depth": plan.get("depth"), "architecture": plan.get("architecture_preflight"),
        "checks": checks, "tests_executed": tests_executed, "tools_executed": tools_executed,
        "tests_delegated_to_integrity": plan.get("tests_delegated_to_integrity", False),
        "early_stop": bool(blocking_plan or failed), "review_reasons": reviews,
        "primary_cause": cause, "diagnosis": diagnosis, "duration_ms": milliseconds(started),
        "next_action": "Reproduce the recorded failing check; inspect its evidence before changing code."
            if failed else "Review ownership/graph limits, then rerun verify." if reviews else None,
        "validation_authority": "tools.atlas_integrity",
        "cache": "Graph and catalog reuse HEAD/worktree caches; validation checks are executed against current inputs.",
    }
    write_json(root, "latest_verification", payload, rotate=True)
    return payload
