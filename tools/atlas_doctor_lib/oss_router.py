from __future__ import annotations

"""Opt-in advisory OSS diagnostics routed through Atlas Doctor.

The canonical Doctor and tool_catalog remain responsible for planning and
certification. This module never installs, updates or silently runs candidates.
"""

import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Iterable

from tools.tool_catalog import catalog, local_candidate_preflight, select_tools

MAX_FILES = 16
MAX_TIMEOUT = 60
_ALLOWED = re.compile(r"^[A-Za-z0-9_./-]{1,240}$")
_CODE_ROOTS = frozenset({"app", "tools", "tests", "scripts"})


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
                or len(rel.parts) < 2):
            raise ValueError("Unsafe repository-relative file")
        if rel.parts[0] in _CODE_ROOTS:
            if rel.suffix not in {".py", ".pyi"}:
                raise ValueError("Only Python source files can be analyzed here")
        elif rel.parts[:2] == (".github", "workflows"):
            if rel.suffix not in {".yml", ".yaml"}:
                raise ValueError("Only workflow YAML files can be analyzed here")
        else:
            raise ValueError("Scope is not owned by this advisory diagnostic")
        target = base.joinpath(*rel.parts)
        if not target.is_file() or target.is_symlink() or not target.resolve().is_relative_to(base):
            raise ValueError("File is missing, symlinked or outside the checkout")
        if value not in clean:
            clean.append(value)
    return clean


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
    native = select_tools(catalog(root), capability=capability,
                          safe_only=True, ready_only=True, limit=5)
    probe = local_candidate_preflight(packages=["ruff"] if python_files else [])
    detected = next(iter(probe["results"]), None)
    available = bool(detected and detected["available"])
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
                                    timeout=timeout_seconds, check=False)
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
    return {
        "schema_version": 1,
        "source": "tools.atlas_doctor_lib.oss_router.route_oss",
        "status": "ADVISORY_ONLY",
        "files": files,
        "scope": {"python": len(python_files), "workflows": len(workflows)},
        "native_tools": [{"path": item["path"], "capabilities": item["capabilities"]}
                         for item in native["tools"]],
        "native_tools_executed": False,
        "oss_candidates": [{
            "id": "ruff", "selected": bool(python_files),
            "available": available, "version_claim": detected["version"] if detected else None,
            "license_verified": False, "platform_verified": False,
            "automation_ready": False,
        }],
        "execution": execution,
        "network_requested": False,
        "network_used": None if run and available else False,
        "dependencies_installed": False,
        "files_modified": False,
        "phase_certified": False,
        "benchmark_executed": False,
        "note": "Advisory OSS evidence only; Doctor's canonical gates still apply.",
    }
