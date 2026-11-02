from __future__ import annotations

"""Opt-in advisory OSS diagnostics routed through Atlas Doctor.

The canonical Doctor and tool_catalog remain responsible for planning and
certification. This module never installs, updates or silently runs candidates.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Iterable

from tools.tool_catalog import catalog, local_candidate_preflight, select_tools
from tools.atlas_doctor_lib.oss_intelligence import intelligent_plan

MAX_FILES = 16
MAX_TIMEOUT = 60
_ALLOWED = re.compile(r"^[A-Za-z0-9_./-]{1,240}$")
_CODE_ROOTS = frozenset({"app", "tools", "tests", "scripts"})


def _open_source_inventory(root: Path) -> dict[str, Any]:
    """Reflect the 29 candidates from the existing study, not a second registry."""
    study = root / "docs" / "roadmap" / "GITHUB_OPEN_SOURCE_INTEGRATION_2026-10-31.md"
    if not study.is_file():
        return {"status": "NOT_AVAILABLE", "candidates": [], "count": 0}
    candidates: list[dict[str, str]] = []
    supplements: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in study.read_text(encoding="utf-8").splitlines():
        if not line.startswith(("| ATOSS-", "| AT-SUP-")):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not re.fullmatch(r"(ATOSS-[0-9]{2}|AT-SUP-[0-9]{2})", cells[0]):
            continue
        candidate_id, source, decision = cells[:3]
        if candidate_id in seen:
            return {"status": "REVIEW", "reason": "Duplicate source candidate",
                    "count": len(candidates), "candidates": candidates,
                    "supplemental": supplements}
        seen.add(candidate_id)
        match = re.search(r"\[([^\]]+)\]\(https://github.com/[^)]+\)", source)
        name = match.group(1) if match else source[:64]
        integration = "NOT_VERIFIED"
        if "REJECT" in decision:
            integration = "REJECTED"
        elif candidate_id in {"ATOSS-06", "ATOSS-10", "AT-SUP-02"}:
            integration = "EXISTING_OWNER_NOT_RETESTED"
        elif candidate_id in {"ATOSS-20", "ATOSS-21"}:
            integration = "DOCTOR_OPT_IN_ONLY"
        row = {"id": candidate_id, "name": name, "study_decision": decision,
               "integration": integration}
        if candidate_id.startswith("ATOSS-"):
            candidates.append(row)
        else:
            supplements.append(row)
    return {
        "status": ("INVENTORIED_NOT_CERTIFIED"
                   if len(candidates) == 29 and len(supplements) == 5 else "REVIEW"),
        "count": len(candidates), "candidates": candidates,
        "supplemental_count": len(supplements), "supplemental": supplements,
        "execution_witnesses": 0,
        "note": "Static study decisions; execution requires independent exact-SHA evidence.",
    }


def _safe_files(root: Path, paths: Iterable[str]) -> list[str]:
    """Validate all paths before any discovery or subprocess invocation."""
    given = list(paths)
    if not 1 <= len(given) <= MAX_FILES:
        raise ValueError("Expected 1..16 explicit files")
    clean: list[str] = []
    base = root.resolve()
    for value in given:
        if not isinstance(value, str) or not _ALLOWED.fullmatch(value):
            raise ValueError("Invalid repository-relative file")
        rel = PurePosixPath(value)
        if (value.startswith("/") or "\\" in value
                or any(part in {".", ".."} for part in rel.parts)
                or (len(rel.parts) < 2
                    and value not in {"requirements-pyside.txt", "pyproject.toml"})):
            raise ValueError("Unsafe repository-relative file")
        if rel.parts[0] in _CODE_ROOTS or rel.parts[0] == "data":
            if rel.suffix not in {".py", ".pyi", ".json", ".png", ".jpg",
                                  ".jpeg", ".webp", ".ttf", ".otf"}:
                raise ValueError("Unsupported scoped source or asset file")
        elif rel.parts[:2] == (".github", "workflows"):
            if rel.suffix not in {".yml", ".yaml"}:
                raise ValueError("Only workflow YAML files can be analyzed here")
        elif value not in {"requirements-pyside.txt", "pyproject.toml"}:
            raise ValueError("Scope is not owned by this advisory diagnostic")
        target = base.joinpath(*rel.parts)
        if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(base):
            raise ValueError("File is missing, symlinked or outside the checkout")
        if value not in clean:
            clean.append(value)
    return clean



def _execute_zizmor(root: Path, files: list[str], timeout: int) -> dict[str, Any]:
    """Run an installed workflow scanner, explicitly offline, without changes."""
    # Strictly bound input volume; inputs are pre-validated regular files.
    if any((root / file).stat().st_size > 1024 * 1024 for file in files):
        return {"status": "NOT_APPLICABLE", "tool": "zizmor",
                "reason": "Workflow exceeds bounded scan size"}
    command = ["zizmor", "--offline", "--no-config", "--no-progress",
               "--no-exit-codes", "--format=json", "--", *files]
    # No GitHub token or proxy environment is inherited. --offline is mandatory
    # even if zizmor happens to be configured with credentials elsewhere.
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME"}}
    env.update({"ZIZMOR_OFFLINE": "1", "NO_COLOR": "1"})
    try:
        completed = subprocess.run(command, cwd=root, env=env,
                                   capture_output=True, text=True,
                                   timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "tool": "zizmor"}
    except OSError:
        return {"status": "UNAVAILABLE", "tool": "zizmor"}
    if completed.returncode != 0:
        return {"status": "ERROR", "tool": "zizmor",
                "reason": "Tool failed or incompatible CLI"}
    if len(completed.stdout) > 2_000_000:
        return {"status": "ERROR", "tool": "zizmor",
                "reason": "Bounded report limit exceeded"}
    try:
        findings = json.loads(completed.stdout)
        if not isinstance(findings, list) or not all(
                isinstance(row, dict) for row in findings):
            raise ValueError("unexpected zizmor JSON")
    except (ValueError, TypeError):
        return {"status": "ERROR", "tool": "zizmor",
                "reason": "Invalid scanner response"}
    # Never return excerpts of source, secrets, host paths or arbitrary messages.
    return {"status": "FINDINGS" if findings else "CLEAN", "tool": "zizmor",
            "finding_count": len(findings), "exit_code": completed.returncode,
            "offline_requested": True}


def select_eligible_diagnostics(root: Path, paths: Iterable[str], *,
                                limit: int = MAX_FILES) -> dict[str, Any]:
    """Bound automatic Doctor checks to explicit, existing and safe input files.

    No directory discovery, globbing, automatic imports or opportunistic
    execution of new candidates. Unsupported files stay with canonical owners.
    An invalid candidate is never forwarded to an external scanner.
    """
    if not 1 <= limit <= MAX_FILES:
        raise ValueError("eligible diagnostic limit must be 1..16")
    eligible: list[str] = []
    seen: set[str] = set()
    ignored = 0
    over_limit = 0
    for raw in paths:
        # Only the two audited adapters are automatically executable.
        if not isinstance(raw, str) or not (
                raw.endswith((".py", ".pyi"))
                or (raw.startswith(".github/workflows/")
                    and raw.endswith((".yml", ".yaml")))):
            ignored += 1
            continue
        try:
            safe = _safe_files(root, [raw])[0]
        except ValueError:
            ignored += 1
            continue
        if safe in seen:
            continue
        seen.add(safe)
        if len(eligible) < limit:
            eligible.append(safe)
        else:
            over_limit += 1
    return {
        "schema_version": 1,
        "source": "tools.atlas_doctor_lib.oss_router.select_eligible_diagnostics",
        "files": eligible,
        "selected_count": len(eligible),
        "ignored_count": ignored,
        "truncated_count": over_limit,
        "coverage_complete": over_limit == 0,
        "scope": "Only explicit existing Python files and GitHub Actions workflows",
        "certified": False,
    }



def _file_digests(root: Path, files: list[str]) -> dict[str, str]:
    """Bound input-file integrity evidence; no writes or recursive discovery."""
    digests: dict[str, str] = {}
    for name in files:
        target = root / name
        if target.is_symlink() or not target.is_file() or target.stat().st_size > 2_000_000:
            raise ValueError("Unverifiable or oversized diagnostic input")
        digests[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    return digests



def _observed_tool_version(root: Path, name: str) -> str | None:
    """Capture an actually running local tool version without leaking stdout."""
    if name not in {"ruff", "zizmor"}:
        return None
    command = ([sys.executable, "-m", "ruff", "--version"]
               if name == "ruff" else ["zizmor", "--version"])
    env = {key: value for key, value in os.environ.items()
           if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME"}}
    env.update({"ZIZMOR_OFFLINE": "1", "PIP_NO_INDEX": "1",
                "PYTHONNOUSERSITE": "1", "PYTHONPATH": "", "NO_COLOR": "1"})
    try:
        result = subprocess.run(command, cwd=root, env=env,
                                capture_output=True, text=True,
                                timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    match = re.fullmatch(
        rf"{name}\s+v?([0-9]+(?:\.[0-9]+){{1,3}}(?:[-+][a-zA-Z0-9.-]+)?)",
        result.stdout.strip(), re.IGNORECASE)
    return match.group(1) if match else None


def qualify_live(root: Path, paths: Iterable[str], *,
                 timeout_seconds: int = 30) -> dict[str, Any]:
    """Attest actual local subprocess execution, never Windows or phase certification.

    This explicit check is separate from mocked unit tests and only speaks about
    the inspected input files on the runner where the command was executed.
    """
    files = _safe_files(root, paths)
    python_files = [name for name in files if name.endswith((".py", ".pyi"))]
    workflows = [name for name in files if name.startswith(".github/workflows/")
                 and name.endswith((".yml", ".yaml"))]
    if not python_files or not workflows:
        return {
            "schema_version": 1, "status": "REVIEW",
            "reason": "Live qualification requires both Python and workflow inputs",
            "requested_tools": ["ruff", "zizmor"],
            "actual_executions": 0, "input_files_unchanged": None,
            "windows_13_qualified": False, "phase_certified": False,
        }
    try:
        before = _file_digests(root, files)
    except (OSError, ValueError):
        return {
            "schema_version": 1, "status": "BLOCKED",
            "reason": "Cannot snapshot explicit inputs",
            "requested_tools": ["ruff", "zizmor"],
            "actual_executions": 0, "input_files_unchanged": None,
            "windows_13_qualified": False, "phase_certified": False,
        }
    diagnostic = route_oss(root, files, run=True, timeout_seconds=timeout_seconds)
    try:
        after = _file_digests(root, files)
        unchanged = before == after
    except (OSError, ValueError):
        unchanged = False
    expected = ("ruff", "zizmor")
    results = diagnostic.get("execution_results", [])
    statuses = [row.get("status") for row in results if isinstance(row, dict)]
    witnesses = sum(status in {"CLEAN", "FINDINGS"} for status in statuses)
    all_executed = len(statuses) == len(expected) and witnesses == len(expected)
    versions = ({tool: _observed_tool_version(root, tool) for tool in expected}
                if all_executed else {})
    intact = unchanged and all_executed and all(versions.get(tool) for tool in expected)
    # A local test on Linux/macOS is not a native Windows qualification.
    windows_13 = sys.platform == "win32" and sys.version_info[:2] == (3, 13)
    return {
        "schema_version": 1,
        "source": "tools.atlas_doctor_lib.oss_router.qualify_live",
        "status": "LIVE_PASS" if intact else "REVIEW" if unchanged else "FAIL",
        "reason": ("All approved tools returned valid JSON on actual local inputs"
                   if intact else "Input was modified or scanner execution incomplete"),
        "requested_tools": list(expected),
        "actual_executions": witnesses,
        "tool_statuses": [{"tool": name,
                           "status": statuses[index] if index < len(statuses) else "NOT_RUN"}
                          for index, name in enumerate(expected)],
        "input_files_unchanged": unchanged,
        "input_sha256": before if unchanged else {},
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "platform": sys.platform,
        "windows_13_qualified": bool(intact and windows_13),
        "version_claims": {row.get("id"): row.get("version_claim")
                           for row in diagnostic.get("oss_candidates", [])
                           if isinstance(row, dict)},
        "versions_observed": versions,
        "version_proof": "Actual --version subprocesses; not license attestation",
        "gaps": diagnostic.get("execution_summary", {}).get("gaps", []),
        "phase_certified": False,
        "network_verified_by_traffic_capture": False,
        "scope_limit": "Source-file hashes only; no proof of unrelated file or network effects",
    }


def route_oss(root: Path, paths: Iterable[str], *, run: bool = False,
              timeout_seconds: int = 20) -> dict[str, Any]:
    """Select useful tools by file type; run only reviewed Ruff on explicit opt-in."""
    if not 1 <= timeout_seconds <= MAX_TIMEOUT:
        raise ValueError("timeout_seconds must be in 1..60")
    files = _safe_files(root, paths)
    python_files = [name for name in files if name.endswith((".py", ".pyi"))]
    workflows = [name for name in files if name.endswith((".yml", ".yaml"))]
    capability = "validation" if python_files else "ci_intelligence"
    # The existing catalog is the only source for native Doctor tool readiness.
    native_report = catalog(root)
    native = select_tools(native_report, capability=capability,
                          safe_only=True, ready_only=True, limit=5)
    study = _open_source_inventory(root)
    selection = intelligent_plan(files, study)
    probe = local_candidate_preflight(
        packages=["ruff"] if python_files else [],
        binaries=["zizmor"] if workflows else [])
    discovered = {((row.get("kind") or "python_distribution"), row["name"].casefold()): row
                  for row in probe["results"]}
    detected = discovered.get(("python_distribution", "ruff"))
    available = bool(detected and detected["available"])
    workflow_candidate = discovered.get(("path_executable", "zizmor"))
    workflow_available = bool(workflow_candidate and workflow_candidate["available"])
    timeout_each = max(1, timeout_seconds // max(1, int(bool(python_files)) + int(bool(workflows))))
    execution: dict[str, Any] = {"status": "NOT_RUN", "reason": "Explicit --run required"}
    if run and not python_files:
        execution = {"status": "NOT_APPLICABLE", "reason": "No approved workflow OSS executor"}
    elif run and not available:
        execution = {"status": "NOT_AVAILABLE", "reason": "Ruff not installed; no auto-install"}
    elif run:
        # Fixed argv and Python interpreter: never evaluate a PATH binary or shell.
        # Ruff's --isolated/--no-cache/--no-fix forbid configuration-driven writes.
        command = [sys.executable, "-m", "ruff", "check", "--isolated",
                   "--no-cache", "--no-fix", "--output-format", "json",
                   "--target-version", "py313", "--", *python_files]
        env = {key: value for key, value in os.environ.items()
               if key in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME"}}
        env.update({"PYTHONNOUSERSITE": "1", "PYTHONPATH": "",
                    "RUFF_NO_CACHE": "1", "NO_COLOR": "1", "PIP_NO_INDEX": "1"})
        try:
            result = subprocess.run(command, cwd=root, env=env,
                                    capture_output=True, text=True,
                                    timeout=timeout_each, check=False)
        except subprocess.TimeoutExpired:
            execution = {"status": "TIMEOUT", "reason": "Bounded OSS diagnostic timed out"}
        except OSError:
            execution = {"status": "UNAVAILABLE", "reason": "Cannot start local Ruff module"}
        else:
            try:
                findings = json.loads(result.stdout)
                if not isinstance(findings, list) or result.returncode not in (0, 1):
                    raise ValueError("unexpected Ruff output")
                counts: dict[str, int] = {}
                for item in findings:
                    if not isinstance(item, dict):
                        raise ValueError("unexpected diagnostic item")
                    code = item.get("code")
                    if isinstance(code, str) and re.fullmatch(r"[A-Z0-9]{1,10}", code):
                        counts[code] = counts.get(code, 0) + 1
                execution = {"status": "FINDINGS" if findings else "CLEAN",
                             "exit_code": result.returncode,
                             "finding_count": len(findings),
                             "rule_counts": counts,
                             "tool": "ruff"}
            except (ValueError, TypeError, json.JSONDecodeError):
                execution = {"status": "ERROR", "reason": "Unexpected Ruff response"}
    workflow_execution = None
    if workflows:
        if not run:
            workflow_execution = {"status": "NOT_RUN", "tool": "zizmor"}
        elif not workflow_available:
            workflow_execution = {"status": "NOT_AVAILABLE", "tool": "zizmor",
                                  "reason": "Not installed; no installation attempted"}
        else:
            workflow_execution = _execute_zizmor(root, workflows, timeout_each)
        if not python_files:
            execution = workflow_execution
    results = ([execution] if python_files else []) + (
        [workflow_execution] if workflow_execution is not None else [])
    expected_tools = (["ruff"] if python_files else []) + (
        ["zizmor"] if workflows else [])
    summarized = [
        {"tool": tool, "status": results[index].get("status", "ERROR")}
        for index, tool in enumerate(expected_tools)
    ]
    gaps = [row for row in summarized if row["status"] not in {"CLEAN", "FINDINGS"}]
    execution_summary = {
        "status": ("NOT_RUN" if not run else "NOT_APPLICABLE"
                   if not expected_tools else "COMPLETE" if not gaps else "INCOMPLETE"),
        "expected_tools": expected_tools,
        "confirmed_executions": len(expected_tools) - len(gaps) if run else 0,
        "gaps": gaps,
        "does_not_override_doctor": True,
    }
    return {
        "schema_version": 1,
        "source": "tools.atlas_doctor_lib.oss_router.route_oss",
        "status": "ADVISORY_ONLY",
        "files": files,
        "scope": {"python": len(python_files), "workflows": len(workflows)},
        "native_tools": [{"path": item["path"], "capabilities": item["capabilities"]}
                         for item in native["tools"]],
        "native_tools_executed": False,
        "native_catalog": {
            "source": "tools.tool_catalog.catalog",
            "tool_count": native_report.get("tool_count"),
            "agent_ready_count": native_report.get("agent_ready_count"),
            "automation_ready_count": native_report.get("automation_ready_count"),
            "unguarded_mutator_count": native_report.get("unguarded_mutator_count"),
            "unready_total": sum(not item.get("automation_ready", False)
                                 for item in native_report.get("tools", [])),
            "unready_sample": [
                {"path": item.get("path"), "readiness": item.get("readiness")}
                for item in native_report.get("tools", [])
                if not item.get("automation_ready", False)
            ][:25],
            "execution_witnesses": 0,
        },
        "open_source_inventory": study,
        "intelligent_selection": selection,
        "oss_candidates": [
            {"id": "ruff", "selected": bool(python_files),
             "available": available, "version_claim": detected["version"] if detected else None,
             "license_verified": False, "platform_verified": False,
             "automation_ready": False},
            {"id": "zizmor", "selected": bool(workflows),
             "available": workflow_available,
             "version_claim": None, "license_verified": False,
             "platform_verified": False, "automation_ready": False},
        ],
        "execution_results": results,
        "execution_summary": execution_summary,
        "execution_count": sum(result["status"] in {"CLEAN", "FINDINGS"}
                               for result in results),
        "execution": execution,
        "network_requested": False,
        "network_used": None if run and (available or workflow_available) else False,
        "dependencies_installed": False,
        "files_modified": False,
        "phase_certified": False,
        "benchmark_executed": False,
        "note": "Advisory OSS evidence only; Doctor's canonical gates still apply.",
    }
