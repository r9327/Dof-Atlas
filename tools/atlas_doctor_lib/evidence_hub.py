"""Doctor's evidence bus: verified, explainable, de-duplicated tool observations.

The hub NEVER invents tests, treats a stale SHA as success, or changes an
underlying specialist's result. Other tools publish JSON to their own files;
Doctor reads and cross-references these exact immutable run artifacts.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

EXPECTED = (
    "app_navigation", "guides", "phase8_memory", "phase8_preload",
    "qt_ui", "distribution", "functional_contracts", "graphify",
    "app_multi_instance", "one_core",
)
ALIASES = {
    "atlas_quick_full_app_navigation": "app_navigation",
    "doctor_eight_independent_atlas_processes_not_dofus_clients": "app_multi_instance",
    "atlas_doctor_complete_automated_suite": "ci",
}
BAD = frozenset({"FAIL", "FAILED", "BLOCKED", "ERROR", "CANCELLED", "TIMED_OUT"})
GOOD = frozenset({"PASS", "SUCCESS", "OBSERVED", "AUTOMATED_PASS_NATIVE_NOT_CERTIFIED"})


JOB_CAPABILITIES = {
    "MENUS": "app_navigation", "GUIDES": "guides", "MEMORY": "phase8_memory",
    "PRELOAD": "phase8_preload", "CONTRACTS": "functional_contracts",
    "UI": "qt_ui", "DISTRIBUTION": "distribution", "GRAPHIFY": "graphify",
    "EIGHT_ATLAS": "app_multi_instance", "ONE_CORE": "one_core",
}


def job_result_sources(sha: str, jobs: dict[str, str]) -> list[tuple[str, str, dict[str, Any]]]:
    """CI job results supplied by trusted needs, explicitly marked job-level."""
    result = []
    for job, capability in JOB_CAPABILITIES.items():
        if job not in jobs:
            continue
        status = str(jobs[job]).lower()
        result.append((capability, f"github-actions-needs/{job}", {
            "kind": "github_actions_job_result", "git_head": sha,
            "status": "PASS" if status == "success" else "FAIL",
            "original_job_conclusion": status,
            "evidence_level": "job_result_only_not_individual_measurement",
        }))
    return result


def summarize_sources(
    *,
    sha: str,
    inputs: list[tuple[str, str, dict[str, Any]]],
    required: tuple[str, ...] = EXPECTED,
    job_results: dict[str, str] | None = None,
) -> dict[str, Any]:
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("Candidate SHA must be a complete immutable commit")
    if len(inputs) > 100:
        raise ValueError("Evidence limit exceeded")

    sources = []
    by_capability: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[tuple[str, str, str]] = set()
    for capability, path, data in inputs:
        if not isinstance(data, dict):
            raise ValueError("Invalid evidence object")
        cap = str(capability or ALIASES.get(data.get("kind"), "unknown"))
        provenance = data.get("git_head") or data.get("candidate_sha") or data.get("sha") or data.get("source_sha")
        verdict = str(data.get("status") or data.get("conclusion") or "UNKNOWN").upper()
        identity = (cap, str(path), str(provenance))
        if identity in seen:
            continue
        seen.add(identity)
        if provenance != sha:
            status = "STALE" if isinstance(provenance, str) and len(provenance) == 40 else "UNVERIFIED"
        elif verdict in GOOD:
            status = "PASS"
        elif verdict in BAD:
            status = "FAIL"
        else:
            status = "UNKNOWN"
        source = {
            "capability": cap, "path": path, "source_kind": data.get("kind"),
            "source_sha": provenance, "verdict": verdict, "status": status,
        }
        if data.get("evidence_level"):
            source["evidence_level"] = str(data["evidence_level"])
        if cap == "app_navigation" and isinstance(data.get("cost_attribution"), dict):
            source["cost_attribution"] = data["cost_attribution"]
        if isinstance(data.get("blocking_reasons"), list):
            source["blocking_reasons"] = data["blocking_reasons"][:20]
        if data.get("fatal"):
            source["fatal"] = str(data["fatal"])[:350]
        sources.append(source)
        by_capability[cap].append(source)

    coverage = {}
    for cap in sorted(set(required) | set(by_capability)):
        rows = by_capability.get(cap, [])
        status = ("NOT_RUN" if not rows else
                  "FAIL" if any(r["status"] == "FAIL" for r in rows) else
                  "STALE" if any(r["status"] == "STALE" for r in rows) else
                  "PASS" if all(r["status"] == "PASS" for r in rows) else
                  "UNVERIFIED")
        coverage[cap] = {"status": status, "sources": len(rows)}
    jobs = {str(k): str(v).lower() for k, v in (job_results or {}).items()}
    ci_blockers = sorted(k for k, v in jobs.items() if v != "success")
    missing = sorted(cap for cap in required if coverage[cap]["status"] != "PASS")

    cost_rows = []
    duplicate_suspects = []
    for source in sources:
        cost = source.get("cost_attribution") or {}
        for row in cost.get("shares", []):
            cost_rows.append({"source": source["path"], **row})
        for row in cost.get("repeated_work_suspects", []):
            key = (str(row.get("route")), str(row.get("classification")))
            if key not in {(x["route"], x["classification"]) for x in duplicate_suspects}:
                duplicate_suspects.append({"route": key[0], "classification": key[1],
                                           "evidence": source["path"], "observation": row})

    result = {
        "schema": 1, "kind": "atlas_doctor_evidence_hub",
        "git_head": sha,
        "status": "PASS" if not missing and not ci_blockers else "BLOCKED",
        "coverage": coverage, "required_missing_or_bad": missing,
        "job_results": jobs, "ci_blockers": ci_blockers,
        "sources": sources,
        "cost_shares": cost_rows,
        "duplicate_work_suspects": duplicate_suspects,
        "source_contract": "canonical_Doctorgate_source_SHA_and_specialist_original_verdict",
        "limits": [
            "Source reports must be explicitly supplied; absent sources are NOT_RUN",
            "No percentages for non-additive native Qt RSS or mixed asynchronous worker CPU",
            "Overlapping functions and screens are NOT duplicated allocations by default",
            "Graphify/Doctor static duplicate findings require a separate code audit",
            "Native installer and human-visible UI never pass merely from Python contract tests",
        ],
    }
    return result


def build_hub(root: Path, *, sha: str, sources: list[str],
              jobs_json: Path | None = None, output: Path) -> dict[str, Any]:
    root = root.resolve()
    out = (root / output).resolve()
    if out.suffix != ".json" or not out.is_relative_to(root / "artifacts"):
        raise ValueError("Evidence hub output must be under artifacts/")
    files = []
    for entry in sources:
        cap, sep, raw = entry.partition("=")
        if not sep or cap not in (*EXPECTED, "ci"):
            raise ValueError(f"Unknown evidence capability: {cap[:60]}")
        path = (root / raw).resolve()
        if not path.is_relative_to(root / "artifacts") or not path.is_file():
            raise ValueError("Source must be an existing JSON under artifacts/")
        if path.stat().st_size > 8_000_000:
            raise ValueError("Evidence source is too large")
        payload = json.loads(path.read_text(encoding="utf-8"))
        files.append((cap, path.relative_to(root).as_posix(), payload))
    jobs = None
    if jobs_json is not None:
        p = (root / jobs_json).resolve()
        if not p.is_relative_to(root / "artifacts") or not p.is_file():
            raise ValueError("Job results missing under artifacts/")
        jobs = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(jobs, dict):
            raise ValueError("Job result map must be a dictionary")
    report = summarize_sources(sha=sha, inputs=job_result_sources(sha, jobs or {}) + files, job_results=jobs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Doctor / immutable shared specialist evidence")
    parser.add_argument("--sha", required=True)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("--jobs-json", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/doctor_complete/doctor_evidence.json"))
    opts = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    result = build_hub(root, sha=opts.sha, sources=opts.source, jobs_json=opts.jobs_json, output=opts.output)
    print(json.dumps({"status": result["status"], "coverage": result["coverage"],
                      "ci_blockers": result["ci_blockers"],
                      "cost_rows": len(result["cost_shares"])}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
