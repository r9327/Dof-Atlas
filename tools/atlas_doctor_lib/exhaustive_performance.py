"""Opt-in deep guide performance profiling controlled by Atlas Doctor.

Doctor is the only public entrypoint. The internal engine writes raw evidence,
Doctor validates the exact git SHA, completeness and produces a stable verdict.
This tier does not change Phase 8 RAM budgets or quick PR certification.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

VALID_CYCLES = frozenset((1, 2, 5, 10))
SCHEMA_VERSION = 1


def output_under_artifacts(root: Path, output: Path) -> Path:
    root = root.resolve()
    target = (root / output).resolve()
    artifacts = (root / "artifacts").resolve()
    if target.suffix != ".json" or not target.is_relative_to(artifacts):
        raise ValueError("Doctor Performance Lab output must be a JSON file inside artifacts/")
    return target



def bottleneck_candidates(payload: dict[str, Any], *, limit: int = 20) -> list[dict[str, Any]]:
    """Rank observed costs; never assert causation based on a timing correlation.

    Native Qt time is not explained by Python stacks. Preserve that uncertainty
    so Doctor can guide a developer to the next targeted probe.
    """
    candidates: list[dict[str, Any]] = []
    for phase, elapsed in (payload.get("timeline") or {}).items():
        if phase == "first_guide_reachable_ms":
            continue  # cumulative metric: double-counts other startup phases
        if isinstance(elapsed, (int, float)) and elapsed >= 0:
            candidates.append({"kind": "startup_phase", "location": phase,
                               "cost_ms": round(float(elapsed), 2),
                               "evidence": "wall_clock_phase"})
    for row in payload.get("samples") or []:
        guide = str(row.get("guide_id", ""))
        cycle = row.get("cycle")
        prefix = f"{guide} cycle {cycle}"
        open_ms = row.get("open_ms")
        if isinstance(open_ms, (int, float)) and open_ms >= 0:
            candidates.append({"kind": "guide_open", "location": prefix,
                               "cost_ms": round(float(open_ms), 2),
                               "profiled": bool(row.get("profiled")),
                               "evidence": "qt_ready_wall_clock"})
        for phase_name, hotspots in (("open", row.get("method_hotspots") or []),
                                     ("home", row.get("home_method_hotspots") or [])):
            for item in hotspots:
                self_ms = item.get("self_ms")
                if isinstance(self_ms, (int, float)) and self_ms > 0:
                    candidates.append({
                        "kind": "python_method", "location": item.get("method"),
                        "guide": guide, "cycle": cycle, "phase": phase_name,
                        "cost_ms": round(float(self_ms), 2),
                        "calls": item.get("calls"),
                        "evidence": "instrumented_exclusive_time",
                    })
        for checkpoint in row.get("checkpoints") or []:
            elapsed = checkpoint.get("elapsed_ms")
            if isinstance(elapsed, (int, float)) and elapsed >= 0:
                candidates.append({"kind": "guide_checkpoint",
                                   "location": f"{prefix} {checkpoint.get('label')}",
                                   "cost_ms": round(float(elapsed), 2),
                                   "evidence": "qt_checkpoint_wall_clock"})
        for stall in row.get("stall_stacks") or []:
            stack = stall.get("stack") or []
            if stack:
                leaf = stack[-1]
                candidates.append({
                    "kind": "qt_stall_stack_sample",
                    "location": f"{leaf.get('file')}:{leaf.get('line')}:{leaf.get('function')}",
                    "guide": guide, "cycle": cycle,
                    "cost_ms": stall.get("qt_unresponsive_ms_at_sample"),
                    "evidence": "sampled_not_causal",
                })
    return sorted(candidates, key=lambda item: (
        -float(item["cost_ms"] or 0), str(item.get("kind")), str(item.get("location"))
    ))[:max(0, limit)]


def review_evidence(payload: dict[str, Any], *, expected_sha: str, cycles: int,
                    process_exit: int) -> dict[str, Any]:
    problems: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        problems.append("WRONG_SCHEMA")
    if payload.get("git_head") != expected_sha:
        problems.append("WRONG_COMMIT_SHA")
    ids = payload.get("atlas_guide_ids") or []
    manifest = payload.get("manifest_enabled_guide_ids") or []
    if not ids or len(ids) != len(set(ids)) or set(ids) != set(manifest):
        problems.append("INCOMPLETE_MANIFEST")
    samples = payload.get("samples") or []
    expected = {(cycle, ident) for cycle in range(1, cycles + 1) for ident in ids}
    actual = [(r.get("cycle"), r.get("guide_id")) for r in samples]
    if len(samples) != len(expected) or set(actual) != expected or len(set(actual)) != len(actual):
        problems.append("MISSING_OR_DUPLICATED_GUIDE_MEASURES")
    if any(row.get("status") != "PASS" for row in samples):
        problems.append("FAILED_GUIDE_NAVIGATION")
    if payload.get("status") != "PASS" or not payload.get("coverage_complete"):
        problems.append("BENCHMARK_ENGINE_DID_NOT_PASS")
    if process_exit:
        problems.append(f"PROCESS_EXIT_{process_exit}")
    if "peak_process_tree_mb" not in payload:
        problems.append("NO_TREE_PEAK")
    if not isinstance(payload.get("timeline"), dict) or not payload["timeline"].get("functional_preload_ms"):
        problems.append("NO_STARTUP_TIMELINE")
    failures = [
        {"guide_id": row.get("guide_id"), "cycle": row.get("cycle"),
         "error": row.get("error", "")}
        for row in samples if row.get("status") != "PASS"
    ]
    return {
        "schema_version": 1, "kind": "atlas_doctor_exhaustive_guide_lab",
        "status": "BLOCKED" if problems else "PASS",
        "is_certification": False,
        "expected_sha": expected_sha, "observed_sha": payload.get("git_head"),
        "required_cycles": cycles, "atlas_guides": len(ids),
        "measured_routes": len(actual), "expected_routes": len(expected),
        "ganymede_metadata_listings": payload.get("ganymede_source_count"),
        "summary": payload.get("summary", {}),
        "bottleneck_candidates": bottleneck_candidates(payload),
        "attribution_warning": ("Measured hotspots are suspects, not confirmed root causes; "
                                "native Qt/Windows paths need desktop profiling."),
        "startup_timeline_ms": payload.get("timeline", {}),
        "peak_atlas_rss_mib": payload.get("peak_atlas_process_mb"),
        "peak_process_tree_rss_mib": payload.get("peak_process_tree_mb"),
        "failures": failures,
        "blocking_reasons": problems,
        "separate_native_desktop_validation_required": True,
    }


def run_doctor_lab(root: Path, *, cycles: int, output: Path, timeout: float = 45.0,
                   diagnose_slow_ms: float = 1000.0,
                   diagnose_guides: tuple[str, ...] = (),
                   py_spy: bool = False, checkpoints: int = 3) -> dict[str, Any]:
    if checkpoints not in (0, 3):
        raise ValueError("Supported checkpoint modes are 0 or 3")
    if cycles not in VALID_CYCLES:
        raise ValueError("Unsupported Doctor exhaustive cycles")
    if not 5 <= timeout <= 180 or not 0 <= diagnose_slow_ms <= 300000:
        raise ValueError("Invalid timeout or slow threshold")
    if len(diagnose_guides) > 30 or any(
        not ident or len(ident) > 100 or
        not all(ch.isascii() and (ch.isalnum() or ch in "_-") for ch in ident)
        for ident in diagnose_guides
    ):
        raise ValueError("Invalid exact guide ID in diagnostic selection")
    root = root.resolve()
    destination = output_under_artifacts(root, output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Prevent accidental use of results produced by an earlier, unrelated SHA.
    destination.unlink(missing_ok=True)
    args = [
        sys.executable, "-X", "faulthandler", "-m", "tools.benchmark_atlas_exhaustive",
        "--cycles", str(cycles), "--timeout", str(timeout), "--output", str(destination),
        "--diagnose-slow-ms", str(diagnose_slow_ms), "--checkpoints", str(checkpoints),
    ]
    for ident in diagnose_guides:
        args += ["--diagnose-guide", ident]
    if py_spy:
        # Optional third-party sampler, never installed or assumed by Doctor.
        # Native Windows profiling can require extra host permissions.
        from shutil import which
        executable = which("py-spy")
        if not executable:
            return {
                "status": "BLOCKED", "blocking_reasons": ["PY_SPY_NOT_INSTALLED"],
                "message": "Install the optional py-spy tool or omit --py-spy.",
                "is_certification": False,
            }
        args = [
            executable, "record", "--format", "speedscope", "--output",
            str(destination.with_suffix(".speedscope.json")), "--", *args,
        ]
    process = subprocess.run(args, cwd=root, check=False)
    try:
        evidence = json.loads(destination.read_text(encoding="utf-8"))
        if not isinstance(evidence, dict):
            raise ValueError("Guide benchmark evidence must be an object")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "BLOCKED",
            "blocking_reasons": ["MISSING_OR_INVALID_BENCHMARK_EVIDENCE"],
            "error": f"{type(exc).__name__}: {exc}",
            "exit_code": process.returncode,
            "is_certification": False,
        }
    from tools.atlas_doctor_lib.runtime_benchmark import git_head
    report = review_evidence(evidence, expected_sha=git_head(root), cycles=cycles,
                             process_exit=process.returncode)
    report["raw_json"] = str(destination.relative_to(root))
    report["raw_csv"] = str(destination.with_suffix(".csv").relative_to(root))
    report["raw_html"] = str(destination.with_suffix(".html").relative_to(root))
    report_path = destination.with_name(destination.stem + ".doctor.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    report["doctor_report"] = str(report_path.relative_to(root))
    return report
