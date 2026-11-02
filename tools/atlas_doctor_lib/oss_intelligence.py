from __future__ import annotations

"""Select relevant OSS candidates from the canonical study, without a second registry.

Planning is advisory. Only the existing Doctor owner may execute explicitly
approved and opted-in diagnostic adapters; a candidate is never certified merely
because it was selected, detected or named in the study.
"""

from pathlib import Path
from typing import Any, Iterable

from tools.ai_context import classify_path

# Selection *policy*, not an inventory. Candidate names, study decisions and
# descriptions remain exclusively in the ATOSS study consumed by oss_router.
_SCOPES: dict[str, tuple[str, ...]] = {
    "python": ("ATOSS-20", "ATOSS-18", "ATOSS-19"),
    "workflow": ("ATOSS-21", "ATOSS-22"),
    "qt": ("ATOSS-01", "ATOSS-02"),
    "guide": ("ATOSS-02", "ATOSS-15"),
    "launcher": ("ATOSS-03", "ATOSS-02", "ATOSS-14", "AT-SUP-02", "AT-SUP-03"),
    "json": ("ATOSS-11", "ATOSS-12", "ATOSS-13", "AT-SUP-01", "AT-SUP-05"),
    "perf": ("ATOSS-06", "ATOSS-10", "ATOSS-07", "ATOSS-08", "ATOSS-09", "ATOSS-04", "ATOSS-25"),
    "assets": ("ATOSS-16", "ATOSS-17"),
    "dependencies": ("ATOSS-23", "AT-SUP-04"),
    "test_tools": ("ATOSS-05", "ATOSS-02", "ATOSS-01"),
    "agent_eval": ("ATOSS-24",),
}
# Dedicated adapters, never expanded automatically to other discovered tools.
_EXECUTABLE = frozenset({"ATOSS-20", "ATOSS-21"})
_EXISTING = frozenset({"ATOSS-06", "ATOSS-10"})
_REJECTED = frozenset({"ATOSS-28", "ATOSS-29"})
_EXTERNAL_OWNER = frozenset({"ATOSS-26", "ATOSS-27"})
# Lower value is preferred. Not a certificate or license assessment.
_PRIORITY = {
    "ATOSS-20": 0, "ATOSS-21": 0,
    "ATOSS-01": 1, "ATOSS-02": 1, "ATOSS-03": 1,
    "ATOSS-06": 1, "ATOSS-10": 1, "ATOSS-11": 1,
    "ATOSS-15": 2, "ATOSS-16": 2,
}
# Only lookup aliases for read-only local package metadata (never imports or installs).
# Candidate names, IDs and acceptance decisions still come from the study.
_DISTRIBUTIONS = {
    "ATOSS-01": "pytest-qt", "ATOSS-02": "hypothesis",
    "ATOSS-03": "pywinauto", "ATOSS-04": "pytest-benchmark",
    "ATOSS-05": "pytest-xdist", "ATOSS-06": "py-spy",
    "ATOSS-07": "viztracer", "ATOSS-08": "scalene",
    "ATOSS-09": "pyinstrument", "ATOSS-10": "psutil",
    "ATOSS-11": "msgspec", "ATOSS-12": "orjson",
    "ATOSS-13": "ijson", "ATOSS-14": "zstandard",
    "ATOSS-15": "rapidfuzz", "ATOSS-16": "ImageHash",
    "ATOSS-17": "fonttools", "ATOSS-19": "semgrep",
    "ATOSS-20": "ruff", "ATOSS-21": "zizmor",
    "ATOSS-25": "opentelemetry-api",
    "AT-SUP-01": "jsonschema", "AT-SUP-02": "pyinstaller",
    "AT-SUP-04": "pip-audit", "AT-SUP-05": "pydantic",
}
_MAX_RECOMMENDATIONS = 8


def classify_scope(paths: Iterable[str]) -> list[str]:
    """Compose canonical AI context ownership with precise specialist hints."""
    scopes: set[str] = set()
    for path in paths:
        lowered = path.casefold()
        domain = classify_path(path)
        if lowered.endswith((".py", ".pyi")):
            scopes.add("python")
        if lowered.startswith("tests/") and lowered.endswith(".py"):
            scopes.add("test_tools")
        if any(token in lowered for token in ("local_ai", "agent_task", "agent_protocol")):
            scopes.add("agent_eval")
        if lowered.startswith(".github/workflows/") and lowered.endswith((".yaml", ".yml")):
            scopes.add("workflow")
        if domain in {"ui"} or any(token in lowered for token in (
                "qt_", "qt/", "widget", "unity_skin", "theme.py")):
            scopes.add("qt")
        if domain == "guide" or any(token in lowered for token in (
                "ganymede", "guide_ultime", "quest_source", "progression", "achievement")):
            scopes.add("guide")
        if any(token in lowered for token in (
                "distribution/", "launcher", "install", "updater", "release_client")):
            scopes.add("launcher")
        if lowered.endswith(".json") or any(token in lowered for token in (
                "json_", "json/", "quest_source_index", "/providers/")):
            scopes.add("json")
        if any(token in lowered for token in (
                "benchmark", "performance", "ram_", "perf_lab", "phase8", "cost_attribution")):
            scopes.add("perf")
        if lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".ttf", ".otf")):
            scopes.add("assets")
        if lowered in {"requirements-pyside.txt", "pyproject.toml"} or any(
                token in lowered for token in ("requirements-", "dependency_lock")):
            scopes.add("dependencies")
    return sorted(scopes)


def intelligent_plan(paths: Iterable[str], inventory: dict[str, Any],
                     *, limit: int = _MAX_RECOMMENDATIONS) -> dict[str, Any]:
    """Bounded, reproducible explanation of why a specialist was selected."""
    if not 1 <= limit <= _MAX_RECOMMENDATIONS:
        raise ValueError("recommendation limit must be 1..8")
    scopes = classify_scope(paths)
    priority: dict[str, int] = {}
    reasons: dict[str, list[str]] = {}
    for scope in scopes:
        for position, candidate_id in enumerate(_SCOPES[scope]):
            priority[candidate_id] = min(priority.get(candidate_id, 999),
                                         _PRIORITY.get(candidate_id, 10) + position)
            reasons.setdefault(candidate_id, []).append(scope)

    source = [*inventory.get("candidates", []), *inventory.get("supplemental", [])]
    source_map = {row["id"]: row for row in source if isinstance(row, dict)
                  and isinstance(row.get("id"), str)}
    rows: list[dict[str, Any]] = []
    for cid in sorted(priority, key=lambda c: (priority[c], c)):
        found = source_map.get(cid)
        if not found:
            continue
        state = ("REJECTED" if cid in _REJECTED
                 else "EXTERNAL_OWNER" if cid in _EXTERNAL_OWNER
                 else "REUSE_EXISTING" if cid in _EXISTING
                 else "OPT_IN_APPROVED_ADAPTER" if cid in _EXECUTABLE
                 else "EVALUATION_REQUIRED")
        if "REJECT" in found.get("study_decision", ""):
            state = "REJECTED"
        rows.append({
            "id": cid, "name": found.get("name"), "decision": state,
            "reason_scopes": sorted(reasons[cid]),
            "priority": priority[cid],
            "tool_executed": False,
            "licensed_for_automation": False,
            "local_distribution": _DISTRIBUTIONS.get(cid),
        })
    # Never truncate executable recommendations behind multiple optional
    # alternatives; the full inventory remains accessible separately.
    included = rows[:limit]
    omitted = len(rows) - len(included)
    native_routes = []
    if "workflow" in scopes:
        native_routes.append("tools.atlas_doctor ci (canonical CI plan)")
    if "qt" in scopes:
        native_routes.append("tools.atlas_doctor ui (existing Qt scenarios)")
    if "guide" in scopes:
        native_routes.append("tools.atlas_doctor certify (guide owner)")
    if "perf" in scopes:
        native_routes.append("tools.atlas_doctor perf (single Perf Lab)")
    if "json" in scopes:
        native_routes.append("tools.atlas_json_inventory (existing JSON owner)")
    if "python" in scopes:
        native_routes.append("tools.atlas_doctor agent check (existing targeted tests)")
    complete_inventory = {
        "canonical_count": inventory.get("count", 0),
        "supplemental_count": inventory.get("supplemental_count", 0),
        "candidate_total": len(source),
        "recommended_total": len(rows),
        "evaluated_not_executed": sum(row["decision"] == "EVALUATION_REQUIRED"
                                       for row in rows),
        "rejected_in_selection": sum(row["decision"] == "REJECTED"
                                      for row in rows),
        "execution_evidence_count": 0,
        "note": "Recommendation does not prove installation or execution",
    }
    return {
        "schema_version": 1,
        "source": "canonical ATOSS study + ai_context.classify_path",
        "status": "ADVISORY_ONLY" if inventory.get("status") == "INVENTORIED_NOT_CERTIFIED"
                  else "REVIEW",
        "scopes": scopes,
        "recommended": included,
        "omitted_count": omitted,
        "native_routes": list(dict.fromkeys(native_routes)),
        "inventory_coverage": complete_inventory,
        "local_package_probes": [
            {"id": row["id"], "distribution": row["local_distribution"]}
            for row in included
            if row["decision"] not in {"REJECTED", "EXTERNAL_OWNER"}
            and row["local_distribution"]
        ],
        "no_automatic_installation": True,
        "certified": False,
    }


def ai_tool_workflow(action: str, core_report: dict[str, Any],
                     selection: dict[str, Any], *,
                     advisory: dict[str, Any] | None = None,
                     dispatch: dict[str, Any] | None = None) -> dict[str, Any]:
    """Expose the *actual* Doctor-driven agent workflow, not a new runner.

    Native routes are suggestions until their canonical owner is invoked.
    Only explicit Ruff/zizmor adapters can have external execution witnesses.
    This is an explanation contract; it never alters Doctor verdicts.
    """
    phases = (
        {"id": "doctor_plan", "when": "BEFORE_CODE", "required": True,
         "command": "py -3.13 -m tools.atlas_doctor agent plan <paths> --json"},
        {"id": "targeted_code_change", "when": "DEVELOPMENT", "required": True,
         "command": None},
        {"id": "doctor_check", "when": "AFTER_CODE", "required": True,
         "command": "py -3.13 -m tools.atlas_doctor agent check <paths> --run-tests --json"},
        {"id": "doctor_validate", "when": "BEFORE_PR_READY", "required": True,
         "command": "py -3.13 -m tools.atlas_doctor agent validate <paths> --json"},
        {"id": "commit_audit_and_phase_certification", "when": "PR_READY", "required": True,
         "command": None},
    )
    selection_rows = selection.get("recommended") or []
    special = [
        {"tool_id": row.get("id"), "name": row.get("name"),
         "decision": row.get("decision"),
         "reason_scopes": list(row.get("reason_scopes") or []),
         "automatic_execution": False}
        for row in selection_rows if isinstance(row, dict)
    ]
    expected = (["ruff"] if "python" in (selection.get("scopes") or []) else []) + (
        ["zizmor"] if "workflow" in (selection.get("scopes") or []) else [])
    summary = (advisory or {}).get("execution_summary") or {}
    witnessed = {
        row.get("tool"): row.get("status")
        for row in (advisory or {}).get("execution_results", [])
        if isinstance(row, dict) and isinstance(row.get("tool"), str)
    }
    tools = []
    for name in expected:
        observed = witnessed.get(name)
        tools.append({
            "name": name,
            "selected": True,
            "status": observed if observed else "NOT_RUN",
            "executed": observed in {"CLEAN", "FINDINGS"},
            "missing_or_incomplete": observed not in {"CLEAN", "FINDINGS"},
        })
    blockers = [
        {"tool": row["name"], "status": row["status"]}
        for row in tools if row["missing_or_incomplete"]
    ]
    truncated = bool((dispatch or {}).get("truncated_count"))
    if truncated:
        blockers.append({"tool": "scope", "status": "TRUNCATED"})
    return {
        "schema_version": 1,
        "source": "tools.atlas_doctor_lib.oss_intelligence.ai_tool_workflow",
        "action": action,
        "doctor_status": core_report.get("status", "BLOCKED"),
        "doctor_exit_code": core_report.get("exit_code", 2),
        "required_phases": list(phases),
        "native_routes": list(selection.get("native_routes") or []),
        "native_routes_executed_by_selection": False,
        "oss_recommendations": special,
        "approved_oss_execution": {
            "expected_tools": expected,
            "tools": tools,
            "all_executed": bool(expected) and not blockers,
            "coverage_incomplete": truncated,
            "reported_execution_summary_status": summary.get("status", "NOT_RUN"),
            "gaps": blockers,
        },
        "may_claim_full_certification": False,
        "phase_certification_authority": "exact-SHA Phase Certification workflow",
        "agent_instructions": [
            "Read AI_ENTRYPOINT.md, AGENTS.md and required nested rules first.",
            "Do not edit a non-trivial scope without an actual Doctor plan.",
            "Inspect the source and exact-SHA Graphify before structural edits.",
            "Invoke selected native owners separately when relevant; selection is not execution.",
            "Do not claim a recommended, unavailable or mocked OSS tool was executed.",
            "Audit each commit and the full PR before exact-SHA Phase Certification.",
        ],
    }
