from __future__ import annotations

"""Comparable Doctor evidence; validation remains owned by existing engines."""

import hashlib
import os
import platform
import re
import sys
from pathlib import Path
from typing import Any

from .core import load_json, run_git, runtime_dir, write_json

def _resolved_commit(root: Path, base_ref: str) -> tuple[str | None, str | None]:
    try:
        resolved = run_git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    except RuntimeError as exc:
        return None, str(exc)
    return resolved or None, None


def _comparison_key(
    plan: dict[str, Any], *, base_ref: str, base_sha: str | None, root: Path,
) -> dict[str, Any]:
    architecture = plan.get("architecture_preflight") or {}
    return {
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
        "execution_tests": sorted(plan.get("execution_tests", [])),
        "required_groups": sorted(plan.get("required_groups", [])),
        "tools": [{k: row.get(k) for k in ("path", "mode", "command")}\
                  for row in sorted(plan.get("recommended_tools", []), key=lambda row: row.get("path", ""))],
        "environment": environment_fingerprint(root),
    }


def compare_verifications(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """Compare only verification runs that share an explicit execution contract."""
    if not isinstance(previous, dict) or not previous:
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
    previous_rows = {str(row.get("key")): row for row in previous.get("checks", []) if row.get("key")}
    current_rows = {str(row.get("key")): row for row in current.get("checks", []) if row.get("key")}
    new_failure_ids, preexisting_failure_ids, recovered_failure_ids, unknown_checks = [], [], [], []
    for key in sorted(previous_rows.keys() & current_rows.keys()):
        before, after = previous_rows[key], current_rows[key]
        old = {str(item) for item in before.get("failure_ids", [])}
        new = {str(item) for item in after.get("failure_ids", [])}
        new_failure_ids.extend({"check": key, "id": item} for item in sorted(new - old))
        preexisting_failure_ids.extend({"check": key, "id": item} for item in sorted(new & old))
        recovered_failure_ids.extend({"check": key, "id": item} for item in sorted(old - new)
                                     if after.get("status") == "PASS" or new)
        if before.get("status") != "PASS" and after.get("status") != "PASS" and not old and not new:
            unknown_checks.append(key)
    unassessed = [row for row in new_non_pass if row["previous"] is None]
    new_non_pass = [row for row in new_non_pass if row["previous"] is not None]
    if new_non_pass or new_failure_ids:
        status = "REGRESSION"
    elif unassessed or unknown_checks:
        status = "REVIEW"
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
        "new_failure_ids": new_failure_ids,
        "preexisting_failure_ids": preexisting_failure_ids,
        "recovered_failure_ids": recovered_failure_ids,
        "unassessed_checks": unassessed,
        "unknown_failure_identity": unknown_checks,
        "not_rechecked": sorted(previous_rows.keys() - current_rows.keys()),
        "causality": "Observed contract results only; source causality is not established.",
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



def _file_digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def environment_fingerprint(root: Path) -> dict[str, Any]:
    return {
        "machine": platform.node(), "system": platform.system(), "release": platform.release(),
        "processor": platform.processor(), "cpu_count": os.cpu_count(),
        "python": platform.python_version(), "executable": sys.executable,
        "dependency_lock": _file_digest(root / "requirements-pyside.txt"),
        "authority_policy": _file_digest(root / "tools/atlas_integrity_policy.json"),
        "qt_environment": {key: os.environ.get(key) for key in (
            "QT_QPA_PLATFORM", "QTWEBENGINE_DISABLE_SANDBOX", "QTWEBENGINE_CHROMIUM_FLAGS")},
    }


def baseline_key(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("Baseline name must contain 1-64 letters, digits, underscores or hyphens.")
    return "baseline_" + name


def prepare_baseline(root: Path, *, compare: str | None, save: str | None) -> dict[str, Any] | None:
    if compare and save:
        raise ValueError("Choose baseline comparison or baseline creation.")
    if save:
        key = baseline_key(save)
        if (runtime_dir(root) / (key + ".json")).exists():
            raise ValueError("Baseline already exists; choose a new name to preserve the before snapshot.")
    if not compare:
        return None
    payload = load_json(root, baseline_key(compare))
    if (not isinstance(payload, dict) or payload.get("schema_version") != 1
            or payload.get("kind") != "verification" or not isinstance(payload.get("comparison_key"), dict)
            or not isinstance(payload.get("baseline"), dict)
            or not re.fullmatch(r"[0-9a-f]{40}", str(payload["baseline"].get("resolved_sha", "")))):
        raise ValueError("Requested baseline is missing, invalid or incompatible.")
    return payload


def finalize_evidence(
    root: Path, payload: dict[str, Any], *, total_ms: float, planning_ms: float,
    graph_ms: float, previous: dict[str, Any] | None, save: str | None = None,
) -> dict[str, Any]:
    execution_ms = payload["duration_ms"]
    payload["duration_ms"] = total_ms
    payload["cost"].update(total_duration_ms=total_ms, execution_duration_ms=execution_ms,
                           planning_duration_ms=planning_ms, graph_rebuild_duration_ms=graph_ms)
    payload["comparison"] = compare_verifications(previous, payload)
    if payload["comparison"].get("comparable") and previous:
        before = (previous.get("cost") or {}).get("total_duration_ms")
        if isinstance(before, (int, float)) and before > 0:
            delta = total_ms - before
            payload["comparison"]["timing"] = {
                "delta_ms": round(delta, 3), "delta_percent": round(delta / before * 100, 2),
                "review_required": delta >= 1000 and delta / before >= 0.15,
                "rule": "Advisory measurement on a matching machine and execution contract; never a gate waiver.",
            }
    if save:
        key = baseline_key(save)
        payload["baseline_snapshot"] = {"name": save, "path": str(runtime_dir(root) / (key + ".json"))}
        write_json(root, key, payload)
    write_json(root, "latest_verification", payload)
    return payload
