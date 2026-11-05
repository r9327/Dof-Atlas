from __future__ import annotations

"""Strict allowlist for on-demand PR diagnostics; reuse Atlas engines, never a shell.

The workflow provides a credentials-free exact-SHA checkout. Only these named
developer diagnostics may run. A report is NOT Phase Certification evidence.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any

SHA = re.compile(r"[0-9a-f]{40}\Z")
LIGHT_MODES = frozenset({"tools", "audit", "ponytail", "oss", "bench-quick"})
WINDOWS_MODES = frozenset({
    "bench-runtime", "bench-memory", "bench-preload", "bench-8", "bench-full",
})
MODES = LIGHT_MODES | WINDOWS_MODES
OUTPUT_ROOT = Path("artifacts/atlas_tools_on_demand")
_MAX_OSS_FILES = 16
# Each command is bounded independently; the workflow also has a job deadline.
TIMEOUT_SECONDS = {
    "tools": 90, "audit": 240, "ponytail": 120, "oss": 180,
    "bench-quick": 120, "bench-runtime": 900, "bench-memory": 1500,
    "bench-preload": 1500, "bench-8": 1500, "bench-full": 3600,
}


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], text=True, encoding="utf-8", errors="replace",
        capture_output=True, check=False, timeout=30,
    )
    if proc.returncode:
        raise ValueError("Unable to verify checkout or exact PR diff")
    return proc.stdout.strip()


def changed_oss_files(base_sha: str, head_sha: str, root: Path) -> list[str]:
    """Use a stable, bounded set of existing changed Python/workflow paths."""
    paths = _git("diff", "--name-only", "--diff-filter=ACM", f"{base_sha}...{head_sha}")
    selected = []
    for raw in paths.splitlines():
        p = Path(raw)
        if (not raw or "\\" in raw or ".." in p.parts
                or not (root / p).is_file() or (root / p).is_symlink()):
            continue
        python_file = p.suffix == ".py" and p.parts[0] in (
            "app", "tools", "tests", "scripts")
        workflow = (p.parts[:2] == (".github", "workflows")
                    and p.suffix in (".yml", ".yaml"))
        if python_file or workflow:
            selected.append(p.as_posix())
    return sorted(set(selected))[:_MAX_OSS_FILES]


def command_plan(mode: str, base_sha: str, head_sha: str,
                 oss_paths: list[str] | None = None) -> list[tuple[str, list[str], str | None]]:
    if mode not in MODES or not SHA.fullmatch(base_sha) or not SHA.fullmatch(head_sha):
        raise ValueError("Unknown mode or invalid exact SHA")
    py = sys.executable
    doctor = [py, "-m", "tools.atlas_doctor"]
    perf = [py, "-X", "faulthandler", "-m", "tools.atlas_doctor", "perf"]
    memory = [py, "-X", "faulthandler", "tools/benchmark_phase8_memory.py",
              "--output", str(OUTPUT_ROOT / "memory.json")]
    preload = [py, "-X", "faulthandler", "tools/benchmark_phase8_preload.py",
               "--output", str(OUTPUT_ROOT / "preload.json")]
    app = [*perf, "--app", "--cycles", "2", "--max-seconds", "600",
           "--timeout", "18", "--output", str(OUTPUT_ROOT / "app.json")]
    eight = [*perf, "--app", "--parallel-instances", "8", "--cycles", "1",
             "--max-seconds", "540", "--timeout", "18",
             "--output", str(OUTPUT_ROOT / "eight.json")]
    plans = {
        "tools": [
            ("catalog", [py, "-m", "tools.tool_catalog", "--json"], None),
            ("tool_audit", [py, "-m", "tools.tool_audit", "--json"], None),
        ],
        "audit": [
            ("quick", [*doctor, "quick", "--json"], None),
            ("code_inspect", [*doctor, "code-inspect", "--base-ref", base_sha, "--json"], None),
        ],
        "ponytail": [("ponytail", [*doctor, "ponytail", "--json"], None)],
        "bench-quick": [("files_perf", [*doctor, "perf", "--files-only", "--json"], None)],
        "bench-runtime": [("runtime", [*perf, "--json"], None)],
        "bench-memory": [("memory", memory, str(OUTPUT_ROOT / "memory.json"))],
        "bench-preload": [("preload", preload, str(OUTPUT_ROOT / "preload.json"))],
        "bench-8": [("eight", eight, str(OUTPUT_ROOT / "eight.json"))],
        # Explicit extended performance campaign, NOT the release/Phase FULL.
        # No duplicated benchmark engine; all probes use the canonical entrypoints.
        "bench-full": [
            ("app", app, str(OUTPUT_ROOT / "app.json")),
            ("eight", eight, str(OUTPUT_ROOT / "eight.json")),
            ("memory", memory, str(OUTPUT_ROOT / "memory.json")),
            ("preload", preload, str(OUTPUT_ROOT / "preload.json")),
            ("guides", [*perf, "--deep", "--cycles", "2", "--checkpoints", "3",
                        "--output", str(OUTPUT_ROOT / "guides.json")],
             str(OUTPUT_ROOT / "guides.json")),
        ],
    }
    if mode == "oss":
        paths = oss_paths or []
        if len(paths) > _MAX_OSS_FILES:
            raise ValueError("Too many changed files for OSS check")
        if not paths:
            return []
        return [("oss", [*doctor, "oss", *paths, "--run", "--json"], None)]
    return plans[mode]


def _parse_status(stdout: str) -> str | None:
    try:
        value = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(value, dict):
        return str(value["status"]) if value.get("status") is not None else None
    return None


def run(mode: str, base_sha: str, head_sha: str,
        *, root: Path = Path("."), dry_run: bool = False) -> dict[str, Any]:
    root = root.resolve()
    if mode not in MODES or not SHA.fullmatch(base_sha) or not SHA.fullmatch(head_sha):
        raise ValueError("Invalid mode or exact SHA")
    if mode in WINDOWS_MODES and os.name != "nt" and not dry_run:
        raise ValueError("Windows-only benchmark requires a Windows runner")
    actual = _git("rev-parse", "HEAD")
    if actual != head_sha:
        raise ValueError("STALE candidate checkout; refusing a different SHA")
    _git("cat-file", "-e", f"{base_sha}^{{commit}}")
    selected = changed_oss_files(base_sha, head_sha, root) if mode == "oss" else []
    plan = command_plan(mode, base_sha, head_sha, selected)
    report: dict[str, Any] = {
        "schema_version": 1, "kind": "atlas_pr_on_demand_tool_execution",
        "mode": mode, "candidate_sha": head_sha, "base_sha": base_sha,
        "runner_os": os.name, "python": sys.version.split()[0],
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "phase_certified": False, "full_suite_executed": False,
        "live_dofus_accounts_tested": False,
        "benchmark_kind": (
            "eight_atlas_processes_not_eight_dofus_accounts" if mode in {"bench-8", "bench-full"}
            else "candidate_only_not_base_comparison" if mode == "bench-preload"
            else "developer_diagnostic"
        ),
        "status": "NOT_RUN", "commands": [],
    }
    output = root / OUTPUT_ROOT
    output.mkdir(parents=True, exist_ok=True)
    if dry_run:
        report["commands"] = [{"name": name, "argv": argv, "status": "NOT_RUN"}
                              for name, argv, _ in plan]
        return report
    if not plan:
        report["status"] = "NOT_APPLICABLE"
        report["reason"] = "No eligible changed Python/workflow files"
    else:
        for name, command, evidence in plan:
            started = time.monotonic()
            try:
                result = subprocess.run(
                    command, cwd=root, capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=TIMEOUT_SECONDS[mode], check=False,
                    env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONUTF8": "1"},
                )
                code = result.returncode
                stdout, stderr = result.stdout, result.stderr
                status = _parse_status(stdout) or ("EXECUTED_NOT_CERTIFIED" if code == 0 else "FAIL")
                if code != 0:
                    status = "FAIL"
                if evidence and not (root / evidence).is_file():
                    status = "FAIL"
                    stderr += "\nMissing required benchmark evidence: " + evidence
                elif evidence:
                    try:
                        payload = json.loads((root / evidence).read_text(encoding="utf-8"))
                        if not isinstance(payload, dict):
                            raise ValueError("Benchmark evidence is not a JSON object")
                        metrics = payload.get("metrics") or {}
                        observed = (payload.get("candidate_sha") or payload.get("git_head")
                                    or (metrics.get("git_head") if isinstance(metrics, dict) else None))
                        if observed is not None and observed != head_sha:
                            raise ValueError("STALE benchmark data source SHA")
                    except (OSError, ValueError, json.JSONDecodeError) as exc:
                        status = "FAIL"
                        stderr += "\nInvalid benchmark evidence: " + str(exc)
                if _git("rev-parse", "HEAD") != head_sha:
                    status = "FAIL"
                    stderr += "\nCandidate SHA changed during the diagnostic"
            except subprocess.TimeoutExpired:
                code, status, stdout, stderr = 124, "TIMEOUT", "", "Bounded on-demand command exceeded deadline"
            (output / f"{name}.stdout.txt").write_text(stdout, encoding="utf-8")
            (output / f"{name}.stderr.txt").write_text(stderr, encoding="utf-8")
            report["commands"].append({
                "name": name, "argv": command,
                "exit_code": code, "status": status, "seconds": round(time.monotonic()-started, 2),
                "evidence": evidence,
            })
        failures = {"FAIL", "TIMEOUT", "BLOCKED", "ERROR"}
        report["status"] = (
            "FAIL" if any(row["status"] in failures for row in report["commands"])
            else "REVIEW" if any(row["status"] in {"REVIEW", "UNAVAILABLE", "NOT_AVAILABLE"}
                                 for row in report["commands"])
            else "EXECUTED_NOT_CERTIFIED"
        )
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(MODES), required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run(args.mode, args.base_sha, args.head_sha, dry_run=args.dry_run)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        report = {
            "schema_version": 1, "status": "BLOCKED", "mode": args.mode,
            "candidate_sha": args.head_sha, "reason": str(exc),
            "phase_certified": False, "full_suite_executed": False,
        }
        OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        (OUTPUT_ROOT / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report["status"] in ("FAIL", "BLOCKED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
