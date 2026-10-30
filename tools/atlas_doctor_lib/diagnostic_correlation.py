from __future__ import annotations

"""Read-only correlation of existing Doctor evidence and canonical tool metadata.

Hypotheses are triage leads, NOT root-cause proof or certification. No tests,
benchmarks, external commands or repository mutations are executed here.
"""

import math
from typing import Any

MAX_HYPOTHESES = 12
MAX_TOOLS_PER_HYPOTHESIS = 5


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except OverflowError:
        return None
    return result if math.isfinite(result) and abs(result) < 1e15 else None


def _catalog_tools(
    capabilities: tuple[str, ...], catalog_report: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve observed, automation-safe entries through the canonical selector."""
    if catalog_report is None:
        return {"status": "NOT_PROVIDED", "selected": [],
                "unresolved_capabilities": list(capabilities), "not_executed": True}
    if not isinstance(catalog_report.get("tools"), list):
        return {"status": "INVALID_CATALOG", "selected": [],
                "unresolved_capabilities": list(capabilities), "not_executed": True}
    from tools.tool_catalog import select_tools

    selected: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for capability in capabilities:
        if len(selected) >= MAX_TOOLS_PER_HYPOTHESIS:
            unresolved.append("TOOL_BUDGET_EXCEEDED:" + capability)
            continue
        # A guarded mutation tool can be agent-ready while still being the
        # wrong choice for an automatic read-only investigation.
        preferred = select_tools(
            catalog_report, capability=capability, safe_only=True,
            ready_only=True, preferred_only=True,
        )["tools"]
        alternatives = select_tools(
            catalog_report, capability=capability, safe_only=True,
            ready_only=True,
        )["tools"]
        entry = next(
            (row for row in [*preferred, *alternatives]
             if row.get("side_effects") in {"read_only", "artifact_output"}),
            None,
        )
        if entry is None:
            unresolved.append(capability)
            continue
        if any(r["path"] == entry["path"] for r in selected):
            continue
        selected.append({
            "path": entry["path"], "invocation": entry["invocation"],
            "capability": capability, "cost_hint": entry["cost_hint"],
            "selection_reason": "CANONICAL_CATALOG_SAFE_READY",
            "automation_executed": False,
        })
    return {
        "status": "READY_TO_REVIEW" if not unresolved else
                  "PARTIAL_TOOL_COVERAGE" if selected else "NO_SAFE_TOOLS",
        "selected": selected,
        "unresolved_capabilities": unresolved,
        "not_executed": True,
    }


def plan_investigation(
    sha: str, hypotheses: list[dict[str, Any]], gaps: list[str],
) -> dict[str, Any]:
    """Bounded decision DAG using existing specialists, never running them.

    Specialists are de-duplicated across correlated symptoms. Inspection is
    ordered before costly runtime experiments; final certification remains
    owned by Atlas Integrity and the Phase workflow.
    """
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Full candidate SHA required")
    if not hypotheses:
        return {
            "status": "BLOCKED_MISSING_EVIDENCE" if gaps else "NO_ACTION",
            "candidate_sha": sha, "steps": [], "unresolved": sorted(set(gaps)),
            "tests_executed": False, "tools_executed": False,
            "certification_granted": False,
        }

    tools: dict[str, dict[str, Any]] = {}
    unresolved = set(gaps)
    # Cap the number of safe actions. No direct command is executed or
    # allowed to replace mandatory risk/certification obligations.
    for hypothesis in hypotheses[:MAX_HYPOTHESES]:
        tool_plan = hypothesis.get("tool_plan", {})
        for capability in tool_plan.get("unresolved_capabilities", []):
            unresolved.add("tool_unavailable: " + str(capability))
        for tool in tool_plan.get("selected", [])[:MAX_TOOLS_PER_HYPOTHESIS]:
            if not isinstance(tool, dict):
                continue
            name = tool.get("path")
            if not isinstance(name, str) or not name.startswith("tools/"):
                continue
            item = tools.setdefault(name, {
                "tool": name, "capabilities": [],
                "hypotheses": [], "cost_hint": tool.get("cost_hint", "unknown"),
                "recommended_invocation": tool.get("invocation"),
                "status": "PLANNED_NOT_EXECUTED",
            })
            if tool.get("capability") not in item["capabilities"]:
                item["capabilities"].append(tool.get("capability"))
            if hypothesis.get("id") not in item["hypotheses"]:
                item["hypotheses"].append(hypothesis.get("id"))

    # These are bands, not execution permissions. Specialist invocation
    # strings are for human review, not commands to run implicitly.
    def phase(item: dict[str, Any]) -> int:
        if "validation" in item["capabilities"]:
            return 2
        if item["cost_hint"] in {"cheap", "unknown"}:
            return 0
        return 1

    # Reuse canonical Doctor scenarios: this plan does not run an extra
    # benchmark and does not remove any phase-required sentinels.
    ids = {row.get("id") for row in hypotheses}
    probes: list[dict[str, Any]] = []
    if "PRELOAD_WALL_CORRELATION" in ids:
        probes.append({
            "scenario": "preload_cold_warm", "owner": "tools.atlas_doctor perf --app",
            "condition": "AFTER_CHEAP_TRIAGE_IF_UNRESOLVED",
            "measure": ["preload_ms", "source_phase_ms", "cold_vs_warm", "p50_p95_p99"],
            "repeat_count_min": 3, "status": "NOT_RUN",
        })
    if "HOME_REVISIT_CORRELATION" in ids:
        probes.append({
            "scenario": "home_module_home_stabilized",
            "owner": "tools.atlas_doctor perf --app",
            "condition": "AFTER_CHEAP_TRIAGE_IF_UNRESOLVED",
            "measure": ["home_rss_stabilized", "peak_tree_rss", "worker_lifetime"],
            "repeat_count_min": 3, "status": "NOT_RUN",
            "measurement_caveat": "RAM forensics opt-in uses different timing overhead",
        })
    if "GUIDE_HOTSPOT_AND_REVISIT" in ids or "GUIDE_METHOD_HOTSPOT" in ids:
        probes.append({
            "scenario": "guides_cold_warm_regression",
            "owner": "tools.atlas_doctor perf --deep",
            "condition": "AFTER_CHEAP_TRIAGE_IF_UNRESOLVED",
            "measure": ["guide_open_p50_p95_p99", "qt_freeze_count", "method_hotspots"],
            "repeat_count_min": 3, "status": "NOT_RUN",
        })

    ranked_tools = sorted(tools.values(), key=lambda row: (phase(row), row["tool"]))
    truncated = len(ranked_tools) > 32
    if truncated:
        unresolved.add("TOOL_PLAN_TRUNCATED:" + str(len(ranked_tools) - 32))
    steps = []
    for item in ranked_tools[:32]:
        steps.append({
            **item,
            "phase": ("READ_ONLY_TRIAGE" if phase(item) == 0 else
                      "TARGETED_FOLLOW_UP" if phase(item) == 1 else
                      "VALIDATION_AFTER_CODE_COMPLETE"),
            "selection_reason": "COVERS_CORRELATED_HYPOTHESES",
            "requires_same_sha": True,
            "requires_prior_evidence_review": phase(item) > 0,
            "mutation_authorized": False,
        })
    return {
        "status": "REVIEW_REQUIRED" if unresolved else "READY_TO_REVIEW",
        "candidate_sha": sha, "steps": steps, "unresolved": sorted(unresolved),
        "tools_considered": len(ranked_tools), "tools_truncated": truncated,
        "adaptive_benchmark_probes": probes,
        "all_required_certification_scenarios_retained": True,
        "stopping_conditions": [
            "Stop if an artifact is stale, truncated, failed, or from another SHA",
            "Stop if a tool is unavailable or requires mutation approval",
            "Escalate only the unresolved hypotheses after cheap probes",
        ],
        "verification_contract": {
            "before_after_same_runner": "REQUIRED_NOT_RUN",
            "cold_warm_repeats": "REQUIRED_NOT_RUN",
            "targeted_regression_tests": "REQUIRED_NOT_RUN",
            "RAM_HOME_STABILIZED_AND_PEAK": "REQUIRED_NOT_RUN",
            "final_phase_certification": "REQUIRED_NOT_RUN",
            "no_not_run_as_pass": True,
        },
        "tests_executed": False, "tools_executed": False,
        "certification_granted": False,
    }


def correlate_diagnostics(
    sha: str, app: dict[str, Any], *,
    hub: dict[str, Any] | None = None,
    guides: dict[str, Any] | None = None,
    catalog_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cross-correlate independent observations; fail closed on stale evidence."""
    valid_sha = len(sha) == 40 and all(x in "0123456789abcdef" for x in sha)
    if not valid_sha:
        raise ValueError("Correlation requires the full immutable candidate SHA")

    gaps: list[str] = []
    if app.get("git_head") != sha or app.get("status") != "PASS":
        return {
            "schema_version": 1, "kind": "doctor_diagnostic_correlation",
            "candidate_sha": sha, "status": "BLOCKED",
            "evidence_gaps": ["app: STALE_OR_NOT_PASS"],
            "hypotheses": [], "tests_executed": False,
            "tools_executed": False, "causes_proven": False,
            "certification": False,
            "investigation_plan": plan_investigation(
                sha, [], ["app: STALE_OR_NOT_PASS"]),
        }

    if hub is None:
        gaps.append("evidence_hub: NOT_PROVIDED")
    elif hub.get("git_head") != sha or hub.get("status") != "PASS":
        gaps.append("evidence_hub: STALE_OR_NOT_PASS")
    if guides is None:
        gaps.append("guides: NOT_PROVIDED")
    elif (guides.get("observed_sha") or guides.get("git_head")) != sha or guides.get("status") != "PASS":
        gaps.append("guides: STALE_OR_NOT_PASS")
    if catalog_report is None:
        gaps.append("tool_catalog: NOT_PROVIDED")
    elif not isinstance(catalog_report.get("tools"), list):
        gaps.append("tool_catalog: INVALID")

    hypotheses: list[dict[str, Any]] = []

    def add(code: str, priority: str, title: str, observations: list[dict[str, Any]],
            interpretation: str, next_probe: str, capabilities: tuple[str, ...]) -> None:
        if len(hypotheses) >= MAX_HYPOTHESES:
            return
        independent = len({str(x.get("source", "")) for x in observations}) > 1
        hypotheses.append({
            "id": code, "priority": priority, "title": title,
            "observations": observations,
            # Different source labels are a stronger lead, never proof of
            # independent experiments or a validated root cause.
            "evidence_strength": (
                "MULTI_SPECIALIST_LEAD" if independent else "SINGLE_REPORT_LEAD"
            ),
            "interpretation": interpretation,
            "inference": "CORRELATION_NOT_CAUSATION",
            "root_cause_proven": False,
            "next_probe": next_probe,
            "tool_plan": _catalog_tools(capabilities, catalog_report),
        })

    cost = app.get("cost_attribution")
    shares = cost.get("shares", []) if isinstance(cost, dict) and cost.get("status") == "OBSERVED" else []
    if not isinstance(shares, list):
        shares = []
    preload = _number(app.get("preload_ms"))
    preload_phase = next((r for r in shares
                         if isinstance(r, dict) and r.get("phase") == "functional_preload"
                         and _number(r.get("wall_ms")) is not None), None)
    if preload is not None and preload >= 5000 and preload_phase is not None:
        add(
            "PRELOAD_WALL_CORRELATION", "P0", "Long preload corroborated by two fields in one benchmark",
            [
                {"source": "app_navigation", "metric": "preload_ms", "value": preload, "unit": "ms"},
                {"source": "cost_attribution", "metric": "functional_preload.wall_ms",
                 "value": _number(preload_phase["wall_ms"]), "unit": "ms"},
            ],
            "Both fields describe overlapping work within one benchmark, not independent runs; neither identifies the slow function.",
            "Profile exact-SHA source indexing, I/O and startup workers before changing cache policy.",
            ("performance", "quest_data", "runtime_trace", "coverage"),
        )
    elif preload is not None and preload >= 5000:
        gaps.append("preload: MISSING_VALID_COST_ATTRIBUTION")

    idle = _number(app.get("idle_tree_rss_delta_mib"))
    revisits = app.get("revisit_comparison")
    drifts = []
    if isinstance(revisits, dict):
        for route, row in revisits.items():
            if not isinstance(row, dict):
                continue
            delta = _number(row.get("home_tree_delta_first_to_last_mib"))
            if delta is not None and delta >= 10:
                drifts.append((str(route), delta))
    drifts.sort(key=lambda x: (-x[1], x[0]))
    if idle is not None and idle >= 10 and drifts:
        add(
            "HOME_REVISIT_CORRELATION", "P1", "Home RSS drift coincides with repeated route drift",
            [
                {"source": "app_navigation", "metric": "idle_tree_rss_delta_mib",
                 "value": idle, "unit": "MiB"},
                {"source": "app_navigation", "metric": "revisit_comparison",
                 "route": drifts[0][0], "value": drifts[0][1], "unit": "MiB"},
            ],
            "The samples do not prove a memory leak or allocate bytes to a specific module.",
            "Repeat Home-module-Home with stabilized RSS, worker lifetime and QObject ownership.",
            ("memory", "performance", "runtime_trace", "coverage"),
        )
    elif idle is not None and idle >= 10:
        gaps.append("home_ram: MISSING_REVISIT_CORROBORATION")

    if guides is not None and (guides.get("observed_sha") or guides.get("git_head")) == sha and guides.get("status") == "PASS":
        rows = guides.get("bottleneck_candidates")
        if isinstance(rows, list):
            measured = [
                row for row in rows
                if isinstance(row, dict) and row.get("kind") == "python_method"
                and _number(row.get("cost_ms")) is not None
            ]
            if measured:
                slow = max(measured, key=lambda row: _number(row["cost_ms"]) or 0)
                if (_number(slow.get("cost_ms")) or 0) >= 150:
                    observations = [
                        {"source": "guides", "metric": "instrumented_python_method",
                         "location": str(slow.get("location", "UNKNOWN"))[:200],
                         "value": _number(slow["cost_ms"]), "unit": "ms"},
                    ]
                    repeated = (
                        cost.get("repeated_work_suspects", [])
                        if isinstance(cost, dict) and cost.get("status") == "OBSERVED"
                        else []
                    )
                    guide_revisit = next(
                        (row for row in repeated
                         if isinstance(row, dict)
                         and "guide" in str(row.get("route", "")).lower()
                         and _number(row.get("max_warm_ms")) is not None),
                        None,
                    ) if isinstance(repeated, list) else None
                    if guide_revisit is not None:
                        observations.append({
                            "source": "app_navigation",
                            "metric": "repeated_work_suspects.max_warm_ms",
                            "route": str(guide_revisit.get("route"))[:100],
                            "value": _number(guide_revisit["max_warm_ms"]),
                            "unit": "ms",
                        })
                    add(
                        "GUIDE_HOTSPOT_AND_REVISIT" if guide_revisit else "GUIDE_METHOD_HOTSPOT",
                        "P0" if guide_revisit else "P1",
                        "Guide method cost correlates with slow repeated opening" if guide_revisit
                        else "Guide method hotspot observed at candidate SHA",
                        observations,
                        "Multiple measurements suggest a shared path, not function-level causality."
                        if guide_revisit else
                        "Instrumented method cost is a hotspot lead, not root-cause proof.",
                        "Compare exact-SHA warm/cold opens and map the observed method to Graphify consumers.",
                        ("guide", "performance", "graphify", "validation"),
                    )

    hypotheses.sort(key=lambda r: ({"P0": 0, "P1": 1, "P2": 2}[r["priority"]], r["id"]))
    return {
        "schema_version": 1, "kind": "doctor_diagnostic_correlation",
        "candidate_sha": sha,
        "status": "REVIEW" if hypotheses else "NO_CORRELATION",
        "evidence_gaps": sorted(set(gaps)),
        "investigation_plan": plan_investigation(sha, hypotheses, gaps),
        "hypotheses": hypotheses,
        "tests_executed": False, "tools_executed": False,
        "causes_proven": False, "certification": False,
        "limits": [
            "Metrics from the same run are correlated observations, not independent experiments.",
            "No RAM-by-module attribution without an allocation/ownership trace.",
            "Catalog routing is advisory. No tools run or certification gates waived.",
        ],
    }
