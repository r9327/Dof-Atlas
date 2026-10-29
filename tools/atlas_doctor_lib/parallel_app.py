"""Eight *Atlas* processes in an isolated Windows CI sandbox; never Dofus clients.

This is a Doctor-only load scenario. A PASS means eight complete Atlas menu
passes with real Qt and complete preload, not eight real DOFUS accounts.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def validate_instance(report: dict[str, Any], *, sha: str) -> list[str]:
    errors: list[str] = []
    if report.get("git_head") != sha:
        errors.append("WRONG_COMMIT")
    if report.get("status") != "PASS" or report.get("cycles") != 1:
        errors.append("INCOMPLETE_ATLAS_PROCESS")
    if report.get("planned_samples") != 20 or report.get("measured_routes") != 20:
        errors.append("INCOMPLETE_20_MENU_COVERAGE")
    if report.get("functional_pass") != 15 or report.get("placeholder_pass") != 5:
        errors.append("FALSE_FUNCTIONAL_COVERAGE")
    if set((report.get("preload_states") or {}).values()) != {"READY"} or len(report.get("preload_states") or {}) != 3:
        errors.append("PRELOAD_NOT_READY")
    if report.get("failed_routes") or report.get("fatal"):
        errors.append("FAILED_ROUTE_OR_FATAL")
    return errors


def run_eight(root: Path, *, output: Path, max_seconds: float = 540) -> dict[str, Any]:
    root = root.resolve()
    output = output.resolve()
    if os.name != "nt":
        raise ValueError("Eight-instance Atlas scenario requires a real Windows runner")
    if (output.suffix != ".json" or not output.is_relative_to((root / "artifacts").resolve())
            or not 120 <= max_seconds <= 1200):
        raise ValueError("Unsafe output path or unbounded deadline")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                         capture_output=True, check=True)
    sha = git.stdout.strip()
    if len(sha) != 40:
        raise RuntimeError("Invalid exact candidate SHA")
    result: dict[str, Any] = {
        "kind": "doctor_eight_independent_atlas_processes_not_dofus_clients",
        "git_head": sha, "expected_instances": 8, "instances": [],
        "measurement_limits": [
            "Eight independent Atlas processes, NOT eight DOFUS game clients",
            "Qt offscreen, not real rendered Windows FPS or low-end hardware",
            "Isolated per-process APPDATA/LOCALAPPDATA/TEMP, shared read-only CI datasets",
            "Not a full business-interaction or native EXE certification",
        ],
        "is_certification": False,
    }
    from tools.benchmark_phase8_memory import PeakTreeSampler
    sampler = PeakTreeSampler()
    processes: list[tuple[int, subprocess.Popen, Path, Path]] = []
    started = time.monotonic()
    sampler.start()
    try:
        for i in range(8):
            sandbox = output.parent / "users" / f"user_{i + 1:02d}"
            for dirname in ("appdata", "localappdata", "temp"):
                (sandbox / dirname).mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env.update({
                "APPDATA": str(sandbox / "appdata"),
                "LOCALAPPDATA": str(sandbox / "localappdata"),
                "TMP": str(sandbox / "temp"), "TEMP": str(sandbox / "temp"),
            })
            child_report = output.parent / f"instance_{i + 1:02d}.json"
            child_report.unlink(missing_ok=True)
            child_log = output.parent / f"instance_{i + 1:02d}.log"
            cmd = [sys.executable, "-X", "faulthandler", "-m", "tools.atlas_doctor",
                   "perf", "--app", "--cycles", "1", "--timeout", "18",
                   "--max-seconds", "240", "--output",
                   child_report.relative_to(root).as_posix()]
            with child_log.open("w", encoding="utf-8") as stream:
                proc = subprocess.Popen(
                    cmd, cwd=root, env=env, stdin=subprocess.DEVNULL,
                    stdout=stream, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            processes.append((i + 1, proc, child_report, child_log))
        deadline = time.monotonic() + max_seconds
        while any(proc.poll() is None for _, proc, _, _ in processes):
            if time.monotonic() >= deadline:
                result["timeout"] = True
                break
            time.sleep(0.25)
    except Exception as exc:
        result["fatal"] = f"{type(exc).__name__}: {exc}"[:400]
    finally:
        for _i, proc, _json, _log in processes:
            if proc.poll() is None:
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               capture_output=True, timeout=15, check=False)
                if proc.poll() is None:
                    proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    result["fatal"] = "UNREAPED_ATLAS_CHILD"
        sampler.stop()
        result["peak_process_tree_rss_mib"] = round(sampler.peak_tree_rss_mb, 2)
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
        for i, proc, path, log in processes:
            row: dict[str, Any] = {"index": i, "pid": proc.pid,
                                   "exit_code": proc.poll(), "json": path.name,
                                   "log": log.name}
            if path.is_file():
                try:
                    child = json.loads(path.read_text(encoding="utf-8"))
                    row["issues"] = validate_instance(child, sha=sha)
                    row["elapsed_seconds"] = child.get("elapsed_seconds")
                    row["peak_tree_mib"] = child.get("peak_process_tree_rss_mib")
                except (OSError, ValueError, TypeError) as exc:
                    row["issues"] = [f"INVALID_CHILD_JSON:{type(exc).__name__}"]
            else:
                row["issues"] = ["NO_CHILD_EVIDENCE"]
            if proc.returncode != 0:
                row["issues"].append("NONZERO_CHILD_EXIT")
            result["instances"].append(row)
        result["status"] = ("PASS" if len(result["instances"]) == 8
                            and not result.get("fatal") and not result.get("timeout")
                            and all(not row["issues"] for row in result["instances"])
                            else "FAIL")
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return result
