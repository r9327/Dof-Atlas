"""Doctor optimization report over existing benchmark JSON; no extra test engine."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def number(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and -1e15 < value < 1e15 else None


def comparable(a, b):
    keys = ("qt_platform", "cycles", "one_core_requested",
            "idle_seconds_requested", "home_stabilization_wait_ms", "expected_routes")
    return all(a.get(k) == b.get(k) for k in keys) and a.get("status") == b.get("status") == "PASS"


def optimization_report(sha: str, app: dict, hub: dict | None = None,
                        baseline: dict | None = None, guides: dict | None = None,
                        ci_costs: dict | None = None,
                        tool_catalog_report: dict | None = None) -> dict[str, Any]:
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Full immutable hexadecimal SHA required")
    hub, guides = hub or {}, guides or {}
    valid = app.get("git_head") == sha
    findings = []
    def add(priority, code, title, evidence, action):
        findings.append({"priority": priority, "id": code, "title": title,
                         "evidence": evidence, "recommended_action": action,
                         "automatic_fix": False})
    if not valid:
        add("P0", "STALE_APP", "Atlas benchmark missing or stale",
            str(app.get("git_head") or "NOT_RUN"), "Execute Doctor perf --app on the candidate SHA")
    elif app.get("status") != "PASS":
        add("P0", "APP_FAILED", "Atlas benchmark failed",
            str(app.get("failed_routes") or app.get("fatal") or app.get("preload_states")),
            "Repair benchmark failures before interpreting timings")
    cost = app.get("cost_attribution", {}) if valid else {}
    shares = sorted(
        [x for x in cost.get("shares", []) if isinstance(x, dict) and number(x.get("wall_ms")) is not None],
        key=lambda x: -x["wall_ms"]) if cost.get("status") == "OBSERVED" else []
    if valid and not shares:
        add("P0", "COST_MISSING", "No trustworthy measured cost distribution",
            str(cost.get("reason") or cost.get("status") or "NOT_RUN"),
            "Verify disjoint phase timers and preserve uninstrumented time")
    # The menu probe intentionally waits ~750 ms on each Home return and may
    # spend 60 seconds in post-Home idle. Those wall spans are BENCHMARK COST,
    # not an actionable Atlas performance hotspot.
    non_actionable = {"home_return", "post_home_idle", "other_or_uninstrumented"}
    if shares:
        biggest = next((r for r in shares if r.get("phase") not in non_actionable), None)
        if biggest:
            add("P1", "HOT_PHASE", "Most expensive measured phase: " + str(biggest["phase"]),
                str(biggest["wall_ms"]) + " ms / " + str(biggest.get("wall_pct_of_entire_probe")) + "% wall",
                "Profile the functions and workers within this phase before changing code")
    repeats = list(cost.get("repeated_work_suspects") or []) if valid else []
    for item in repeats:
        add("P1", "REPEAT_" + str(item.get("route")), "Repeated slow menu opening",
            str(item.get("route")) + " max warm " + str(item.get("max_warm_ms")) + " ms",
            "Inspect cache reads/reinitialization. Repeated cost is not proven duplicate code")
    # An observed per-route Home delta is a lead, never attribution to that route.
    # The reused benchmark logs this after 750 ms, not stable native Qt memory.
    home_drifts = []
    for route, sample in ((app.get("revisit_comparison") or {}) if valid else {}).items():
        if not isinstance(sample, dict):
            continue
        delta = number(sample.get("home_tree_delta_first_to_last_mib"))
        if delta is not None:
            home_drifts.append({"route": route, "delta_mib": round(delta, 2),
                                "scope": "0.75s_post_home_correlated_not_causal"})
            if delta >= 10:
                add("P1", "HOME_ROUTE_" + str(route),
                    "Repeated Home RSS drift after route " + str(route),
                    "+" + str(round(delta, 2)) + " MiB across tested cycles",
                    "Inspect retained widgets and process lifetimes; route is correlation, not proven owner")
    home_drifts.sort(key=lambda x: -x["delta_mib"])
    peak = number(app.get("peak_process_tree_rss_mib")) if valid else None
    if peak is not None and peak > 250:
        add("P0", "RAM_PEAK", "Process-tree RAM exceeds 250 MiB objective",
            str(peak) + " MiB, phase " + str(app.get("worst_tree_phase")),
            "Profile owner and worker allocations in the measured peak phase")
    idle_delta = number(app.get("idle_tree_rss_delta_mib")) if valid else None
    if idle_delta is not None and idle_delta >= 10:
        add("P1", "HOME_DRIFT", "Observed RSS increase at idle Home",
            str(idle_delta) + " MiB", "Repeat comparable runs; drift alone is NOT proof of a leak")
    if valid and not app.get("idle_samples"):
        add("P2", "IDLE_UNMEASURED", "No extended idle Home recovery observation",
            "NOT_RUN", "Run Doctor perf --app --idle-seconds 60")
    if valid and app.get("preload_status") != "PASS":
        add("P0", "PRELOAD_FAILED", "Preloading failed",
            str(app.get("preload_states")), "Fix real preload errors; never mark FAILED as READY")
    rows = app.get("routes", []) if valid else []
    measured = len({r.get("id") for r in rows
                    if isinstance(r, dict) and r.get("status") in ("PASS", "PLACEHOLDER")})
    add("P1", "INTERNAL_ACTIONS", "All internal business interactions are not fully tested",
        str(measured) + "/20 menu entries visited; internal operations NOT_RUN",
        "Expand focused business interaction contracts, not redundant menu loops")
    hub_coverage = hub.get("coverage", {}) if hub.get("git_head") == sha else {}
    dist = hub_coverage.get("distribution", {}).get("status", "NOT_RUN")
    add("P1", "NATIVE_DESKTOP", "Actual desktop GPU/FPS and public network update not certified",
        "Distribution CI: " + dist + "; Qt offscreen is not desktop validation",
        "Retain native launcher install/update/repair and network rollback acceptance testing")
    if hub and hub.get("git_head") != sha:
        add("P0", "STALE_HUB", "Doctor evidence hub is stale", str(hub.get("git_head")),
            "Join specialist results again at the exact same SHA")
    # Doctor's existing exhaustive guide verdict already contains instrumented
    # method samples even when intrusive startup cProfile is disabled.
    guide_sha = guides.get("observed_sha") or guides.get("git_head")
    guide_verified = guide_sha == sha and guides.get("status") == "PASS"
    startup_functions = guides.get("startup_cpu_functions") or [] if guide_verified else []
    candidates = guides.get("bottleneck_candidates") or [] if guide_verified else []
    measured_methods = [row for row in candidates
                        if isinstance(row, dict) and row.get("kind") == "python_method"
                        and number(row.get("cost_ms")) is not None]
    measured_methods.sort(key=lambda row: -row["cost_ms"])
    profiled = bool(startup_functions or measured_methods)
    if not profiled:
        add("P2", "FUNCTION_PROFILE", "No verified Python function/method hotlist",
            "NOT_RUN", "Provide same-SHA exhaustive Doctor guide evidence; startup cProfile remains opt-in")
    comparison = {"status": "NOT_RUN", "reason": "No baseline provided"}
    if baseline is not None:
        if not valid or len(str(baseline.get("git_head") or "")) != 40 or not comparable(app, baseline):
            comparison = {"status": "NOT_COMPARABLE",
                          "reason": "Mismatched SHA, run result, scenario or measurement settings"}
        else:
            metrics = []
            for field, unit in (("preload_ms", "ms"), ("constructor_to_visible_ms", "ms"),
                                ("peak_process_tree_rss_mib", "MiB"), ("elapsed_seconds", "s")):
                before, after = number(baseline.get(field)), number(app.get(field))
                if before is not None and before > 0 and after is not None and after >= 0:
                    metrics.append({"name": field, "unit": unit, "before": before, "after": after,
                                    "delta": round(after - before, 3),
                                    "delta_pct": round((after - before) / before * 100, 2),
                                    "claim": "directional_only_not_a_certified_optimization"})
            comparison = {"status": "DIRECTIONAL_ONLY" if metrics else "NOT_MEASURED",
                          "baseline_sha": baseline["git_head"], "metrics": metrics,
                          "warning": "Same scenario not proof of same hardware/load; repeat before claiming gain"}
    findings.sort(key=lambda x: ({"P0": 0, "P1": 1, "P2": 2}[x["priority"]], x["id"]))
    # Correlate the same immutable evidence without introducing a second
    # benchmark or promoting advisory hypotheses to certification.
    from .diagnostic_correlation import correlate_diagnostics
    correlation = correlate_diagnostics(
        sha, app, hub=hub if hub else None, guides=guides if guides else None,
        catalog_report=tool_catalog_report,
    )
    return {
        "schema": 1, "kind": "atlas_doctor_optimization_report", "git_head": sha,
        "status": "DIAGNOSTIC_READY" if valid and shares else "BLOCKED",
        "is_certification": False, "priority_findings": findings,
        "measured_costs": shares[:30], "repeated_work_suspects": repeats,
        "non_actionable_benchmark_phases": [
            row for row in shares if row.get("phase") in {"home_return", "post_home_idle"}
        ],
        "home_route_drift": home_drifts[:20],
        "memory": {"process_tree_peak_mib": peak, "worst_tree_phase": app.get("worst_tree_phase") if valid else None,
                   "idle_rss_delta_mib": idle_delta, "module_rss_percentages": None,
                   "limitation": "Native Qt, shared pages and worker RSS are non-additive"},
        "function_hotlist": startup_functions[:20] if startup_functions else measured_methods[:20],
        "function_hotlist_status": "OBSERVED" if profiled else "NOT_RUN",
        "function_hotlist_scope": ("python_startup_cprofile" if startup_functions else
                                   "guide_instrumented_exclusive_method_time" if measured_methods else "NOT_RUN"),
        "guide_bottleneck_candidates": candidates[:20] if guide_verified else [],
        "ci_step_costs": (ci_costs.get("jobs", [])[:15] if ci_costs and ci_costs.get("git_head") == sha else []),
        "functional_coverage": {"menu_entries_visited": measured,
            "internal_screen_operations": "NOT_RUN", "real_desktop_fps": "NOT_RUN",
            "eight_real_dofus_clients": "NOT_RUN", "public_network_rollback": "NOT_RUN"},
        "comparison": comparison,
        "diagnostic_correlation": correlation,
        "limitations": ["Phase wall% and process CPU% have different denominators",
                        "Worker CPU excluded from main-process CPU ratios",
                        "Suspected repeated work is not proof of duplicate code",
                        "Memory drift is not proof of leak; no fake RAM share/savings",
                        "This report never runs tests or overrides specialist PASS/FAIL"],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = ["# Doctor — Rapport réel d'optimisation", "",
             "SHA: " + report["git_head"] + " | " + report["status"] + " (diagnostic, non certification)",
             "", "## Optimisations à étudier en priorité", "",
             "| Priorité | Problème | Preuve | Action conseillée |",
             "|---|---|---|---|"]
    for r in report["priority_findings"]:
        safe = lambda s: str(s).replace("|", "/").replace("\n", " ")
        lines.append("| " + " | ".join(safe(r[k]) for k in
            ("priority", "title", "evidence", "recommended_action")) + " |")
    lines += ["", "## Temps et CPU — coûts mesurés", "",
              "| Phase | ms | Temps % | CPU ms | CPU % |", "|---|---:|---:|---:|---:|"]
    for r in report["measured_costs"]:
        lines.append("| " + " | ".join(str(r.get(k)) for k in
            ("phase", "wall_ms", "wall_pct_of_entire_probe", "process_cpu_ms",
             "cpu_pct_of_measured_process_cpu")) + " |")
    lines += ["", "## Temps imposés par le banc (non optimisables dans Atlas)", ""]
    for r in report["non_actionable_benchmark_phases"]:
        lines.append("- " + str(r.get("phase")) + ": " + str(r.get("wall_ms")) +
                     " ms / " + str(r.get("wall_pct_of_entire_probe")) +
                     "% de la sonde. Inclut les pauses forcées, ne pas classer comme lenteur applicative.")
    lines += ["", "## Fonctions et méthodes instrumentées", ""]
    if not report["function_hotlist"]:
        lines.append("Profil de fonctions: NOT_RUN (ne pas attribuer des coûts non mesurés).")
    for fn in report["function_hotlist"][:12]:
        lines.append("- " + str(fn.get("location") or fn.get("function")) + ": " +
                     str(fn.get("cost_ms") or fn.get("cumulative_cpu_ms")) + " ms (instrumenté)")
    lines += ["", "## Temps des jobs CI / installation (pourcentages par job)", ""]
    for job in report["ci_step_costs"][:10]:
        lines.append("### " + str(job.get("job")))
        for step in job.get("steps", [])[:5]:
            lines.append("- " + str(step.get("step")) + ": " +
                         str(step.get("duration_seconds")) + " s (" +
                         str(step.get("percent_of_job_measured_steps")) + "% du job)")
    if not report["ci_step_costs"]:
        lines.append("NOT_RUN: aucun temps des étapes CI attribuable à ce SHA.")
    lines += ["", "## Dérives RSS observées après retour Home par écran", ""]
    for entry in report["home_route_drift"][:15]:
        lines.append("- " + str(entry["route"]) + ": " + str(entry["delta_mib"]) +
                     " MiB (corrélation après 750 ms, sans preuve de fuite)")
    lines += ["", "## Mémoire", "",
              "Pic process-tree: " + str(report["memory"]["process_tree_peak_mib"]) + " MiB.",
              "Variation Home: " + str(report["memory"]["idle_rss_delta_mib"]) + " MiB (pas fuite prouvée).",
              "RAM par module: NOT_MEASURED (pics non additifs).",
              "", "## Comparaison avant / après", "",
              "Statut: " + report["comparison"]["status"]]
    for item in report["comparison"].get("metrics", []):
        lines.append("- " + item["name"] + ": " + str(item["before"]) + " -> " +
                     str(item["after"]) + " " + item["unit"] + " (" +
                     str(item["delta_pct"]) + "% indicatif)")
    correlation = report.get("diagnostic_correlation") or {}
    lines += ["", "## Corrélation Doctor et orchestration conseillée", "",
              "Statut: " + str(correlation.get("status", "NOT_RUN")) +
              " (hypothèses non causales, aucun outil exécuté)."]
    for row in correlation.get("hypotheses", []):
        lines += ["", "### " + str(row["id"]) + " — " + str(row["title"]),
                  "Constat: " + str(row["interpretation"]),
                  "Prochaine mesure: " + str(row["next_probe"])]
        selection = row.get("tool_plan") or {}
        for tool in selection.get("selected", []):
            lines.append("- Outil disponible: " + str(tool["path"]) +
                         " (" + str(tool["capability"]) + ", non exécuté)")
        for capability in selection.get("unresolved_capabilities", []):
            lines.append("- Outil non prêt / absent pour: " + str(capability))
    for gap in correlation.get("evidence_gaps", []):
        lines.append("- Preuve manquante: " + str(gap))
    investigation = correlation.get("investigation_plan") or {}
    lines += ["", "### Plan de décision adaptatif (pas encore exécuté)",
              "Statut: " + str(investigation.get("status", "NOT_RUN"))]
    for step in investigation.get("steps", []):
        lines.append("- " + str(step.get("phase")) + " : " +
                     str(step.get("tool")) + " (" +
                     ", ".join(str(cap) for cap in step.get("capabilities", [])) + ")")
    for probe in investigation.get("adaptive_benchmark_probes", []):
        lines.append("- Benchmark proposé " + str(probe.get("scenario")) +
                     " via " + str(probe.get("owner")) +
                     " : " + str(probe.get("status", "NOT_RUN")))
    for unready in investigation.get("unresolved", []):
        lines.append("- Investigation incomplète : " + str(unready))
    lines.append("Certification finale obligatoire : " +
                 str((investigation.get("verification_contract") or {}).get(
                     "final_phase_certification", "NOT_RUN")))
    lines += ["", "## Couverture non prouvée", ""]
    lines.extend("- " + k + ": " + str(v) for k, v in report["functional_coverage"].items())
    lines += ["", "## Limites", ""]
    lines.extend("- " + x for x in report["limitations"])
    return "\n".join(lines) + "\n"


def load(root: Path, path: Path | None) -> dict | None:
    if path is None:
        return None
    dest = (root / path).resolve()
    if not dest.is_relative_to((root / "artifacts").resolve()) or not dest.is_file() or dest.stat().st_size > 8_000_000:
        raise ValueError("All evidence must be existing JSON artifacts under artifacts/, max 8MB")
    result = json.loads(dest.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Expected JSON object")
    return result


def generate(root: Path, *, sha: str, app_report: Path, hub_report: Path | None = None,
             baseline: Path | None = None, guides: Path | None = None,
             ci_costs: Path | None = None,
             output: Path = Path("artifacts/doctor_complete/optimization.json")) -> dict:
    root = root.resolve()
    target = (root / output).resolve()
    if target.suffix != ".json" or not target.is_relative_to((root / "artifacts").resolve()):
        raise ValueError("Optimization report output must be a JSON file under artifacts/")
    # Query the single canonical repository tool catalog. Correlation only
    # recommends safe tools; it never dispatches or executes them.
    from tools.tool_catalog import catalog
    tooling = catalog(root)
    report = optimization_report(sha, load(root, app_report) or {},
        hub=load(root, hub_report), baseline=load(root, baseline),
        guides=load(root, guides), ci_costs=load(root, ci_costs),
        tool_catalog_report=tooling)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    target.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Doctor optimization from existing measurements")
    p.add_argument("--sha", required=True)
    p.add_argument("--app-report", type=Path, required=True)
    p.add_argument("--hub-report", type=Path)
    p.add_argument("--baseline", type=Path)
    p.add_argument("--guides", type=Path)
    p.add_argument("--ci-costs", type=Path)
    p.add_argument("--output", type=Path, default=Path("artifacts/doctor_complete/optimization.json"))
    opts = p.parse_args(argv)
    result = generate(Path(__file__).resolve().parents[2], sha=opts.sha,
        app_report=opts.app_report, hub_report=opts.hub_report,
        baseline=opts.baseline, guides=opts.guides, ci_costs=opts.ci_costs, output=opts.output)
    print(json.dumps({"status": result["status"], "findings": len(result["priority_findings"])}))
    return 0 if result["status"] == "DIAGNOSTIC_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
