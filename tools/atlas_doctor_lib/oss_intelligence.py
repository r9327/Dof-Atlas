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
    "launcher": ("ATOSS-03", "ATOSS-02", "ATOSS-14"),
    "json": ("ATOSS-11", "ATOSS-12", "ATOSS-13", "AT-SUP-01"),
    "perf": ("ATOSS-06", "ATOSS-10", "ATOSS-07", "ATOSS-08", "ATOSS-09"),
    "assets": ("ATOSS-16", "ATOSS-17"),
    "dependencies": ("ATOSS-23", "AT-SUP-04"),
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
_MAX_RECOMMENDATIONS = 8


def classify_scope(paths: Iterable[str]) -> list[str]:
    """Compose canonical AI context ownership with precise specialist hints."""
    scopes: set[str] = set()
    for path in paths:
        lowered = path.casefold()
        domain = classify_path(path)
        if lowered.endswith((".py", ".pyi")):
            scopes.add("python")
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

    source = inventory.get("candidates", [])
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
    return {
        "schema_version": 1,
        "source": "canonical ATOSS study + ai_context.classify_path",
        "status": "ADVISORY_ONLY" if inventory.get("status") == "INVENTORIED_NOT_CERTIFIED"
                  else "REVIEW",
        "scopes": scopes,
        "recommended": included,
        "omitted_count": omitted,
        "native_routes": list(dict.fromkeys(native_routes)),
        "no_automatic_installation": True,
        "certified": False,
    }
