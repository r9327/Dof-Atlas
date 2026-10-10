from __future__ import annotations

"""Bounded opt-in developer feedback, not a release or merge gate.

Unlike legacy Doctor verify --gate fast this command never invokes Atlas
Integrity or application-wide test suites. Required gates are listed as
deferred evidence, never counted as passed.
"""
import ast
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from tools import ai_context, atlas_integrity

MAX_CHANGED_FILES = 80
MAX_PYTHON_SOURCES = 16
MAX_PYTHON_BYTES = 512 * 1024
MAX_TARGETED_MODULES = 8
DEFAULT_TEST_TIMEOUT = 90
MODULE_RE = re.compile(r"tests\.test_[a-zA-Z0-9_]+$")


def _review_python_sources(root: Path, changed: list[str]) -> dict[str, Any]:
    trusted_root = root.resolve()
    sources = [path for path in changed if path.endswith(".py")]
    errors: list[dict[str, str]] = []
    checked = 0
    for name in sources[:MAX_PYTHON_SOURCES]:
        relative = Path(name)
        selected = root / relative
        if (relative.is_absolute() or "\\" in name
                or any(part in {".", "..", ""} for part in relative.parts)
                or selected.is_symlink()
                or not selected.is_file()
                or not selected.resolve().is_relative_to(trusted_root)):
            errors.append({"path": name, "reason": "UNSAFE_OR_MISSING_SOURCE"})
            continue
        try:
            if selected.stat().st_size > MAX_PYTHON_BYTES:
                errors.append({"path": name, "reason": "SOURCE_OVER_512K"})
                continue
            ast.parse(selected.read_text(encoding="utf-8-sig"), filename=name)
            checked += 1
        except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
            errors.append({"path": name, "reason": type(exc).__name__})
    return {
        "status": "FAIL" if errors else "PARTIAL" if len(sources) > MAX_PYTHON_SOURCES else "PASS",
        "checked": checked, "source_total": len(sources),
        "truncated": len(sources) > MAX_PYTHON_SOURCES,
        "errors": errors[:MAX_PYTHON_SOURCES],
        "scope": "Changed Python sources only, AST syntax; no imports or UI execution.",
    }


def _select_modules(root: Path, changed: list[str], limit: int) -> dict[str, Any]:
    trusted_root = root.resolve()
    # Explicit edited tests first. Domain recommendations follow, preserving
    # the existing AI context mapper but never importing application modules.
    direct = [
        name[:-3].replace("/", ".")
        for name in changed
        if name.startswith("tests/test_") and name.endswith(".py")
        and (root / name).is_file()
    ]
    proposed = list(dict.fromkeys([*direct, *ai_context.recommended_tests(root, changed)]))
    verified: list[str] = []
    rejected: list[str] = []
    for module in proposed:
        if not isinstance(module, str) or not MODULE_RE.fullmatch(module):
            rejected.append(str(module)[:100])
            continue
        source = root / (module.replace(".", "/") + ".py")
        if (not source.is_file() or source.is_symlink()
                or not source.resolve().is_relative_to(trusted_root)):
            rejected.append(module)
            continue
        verified.append(module)
    return {
        "selected": verified[:limit],
        "total_recommended": len(verified),
        "truncated": len(verified) > limit,
        "rejected": rejected[:16],
        "status": "REVIEW" if len(verified) > limit or rejected else "READY",
    }


def _run_focused_tests(root: Path, modules: list[str], timeout: int) -> dict[str, Any]:
    if not modules:
        return {"status": "NOT_REQUIRED", "duration_seconds": 0.0,
                "modules": [], "tests_executed": False}
    command = [sys.executable, "-X", "faulthandler", "-m", "unittest", "-v", *modules]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command, cwd=root, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False, timeout=timeout,
        )
        result = {
            "status": "PASS" if completed.returncode == 0 else "FAIL",
            "exit_code": completed.returncode,
            "stdout_tail": completed.stdout.splitlines()[-12:],
            "stderr_tail": completed.stderr.splitlines()[-25:],
            "tests_executed": True,
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "status": "TIMEOUT", "exit_code": None,
            "stdout_tail": [], "stderr_tail": [],
            "reason": f"Focused tests exceeded {timeout}s",
            "tests_executed": True,
        }
    except OSError as exc:
        result = {"status": "FAIL", "exit_code": None,
                  "reason": type(exc).__name__, "tests_executed": False}
    result["duration_seconds"] = round(time.perf_counter() - started, 3)
    result["modules"] = modules
    return result


def development_preflight(
    root: Path, *, base_ref: str,
    run_tests: bool = False, max_tests: int = MAX_TARGETED_MODULES,
    timeout_seconds: int = DEFAULT_TEST_TIMEOUT,
) -> dict[str, Any]:
    """Git diff -> bounded syntax/impact planning -> optionally focused unittest.

    No application import, graph rebuild, Qt lifecycle, benchmark, or Integrity
    gate. Never returns an unqualified certified/PASS result.
    """
    if not 1 <= max_tests <= MAX_TARGETED_MODULES:
        raise ValueError("max_tests must be between 1 and 8")
    if not 10 <= timeout_seconds <= 180:
        raise ValueError("timeout_seconds must be between 10 and 180")
    if not base_ref or base_ref.startswith("-"):
        raise ValueError("Explicit safe --base-ref required")
    root = root.resolve()
    started = time.perf_counter()
    try:
        atlas_integrity.resolve_base_ref(root, base_ref)
        changed = atlas_integrity.changed_files(root, base_ref)
        sha = atlas_integrity.repository_head(root)
        classification = atlas_integrity.classify_risk(changed)
        policy = atlas_integrity.load_policy(root)
        required = atlas_integrity._required_groups(
            policy, "FAST", classification)
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "kind": "doctor_development_preflight", "status": "BLOCKED",
            "reason": f"{type(exc).__name__}: {str(exc)[:180]}",
            "tests_executed": False, "integrity_executed": False,
            "merge_gate_satisfied": False, "certified": False,
        }
    if len(changed) > MAX_CHANGED_FILES:
        selected = changed[:MAX_CHANGED_FILES]
    else:
        selected = changed
    syntax_started = time.perf_counter()
    syntax = _review_python_sources(root, selected)
    syntax_seconds = round(time.perf_counter() - syntax_started, 3)
    planning_started = time.perf_counter()
    modules = _select_modules(root, selected, max_tests)
    planning_seconds = round(time.perf_counter() - planning_started, 3)
    tests = (_run_focused_tests(root, modules["selected"], timeout_seconds)
             if run_tests else {"status": "NOT_RUN", "modules": modules["selected"],
                                "tests_executed": False})
    changed_over_budget = len(changed) > MAX_CHANGED_FILES
    structural_paths = [path for path in changed if path.endswith(".py")
                        and not (root / path).is_file()]
    incomplete = (changed_over_budget or syntax["truncated"]
                  or modules["status"] != "READY" or bool(structural_paths))
    failed = (syntax["status"] == "FAIL"
              or tests["status"] in {"FAIL", "TIMEOUT"})
    return {
        "schema_version": 1, "kind": "doctor_development_preflight",
        "status": ("FAIL" if failed else "PARTIAL_REVIEW" if incomplete
                   else "FOCUSED_CHECKED" if run_tests and tests["status"] == "PASS"
                   else "NO_CHANGES" if not changed else "PLANNED"),
        "candidate_sha": sha, "base_ref": base_ref,
        "risk": classification["risk"],
        "changed_count": len(changed), "changed_files": selected,
        "changed_truncated": changed_over_budget,
        "structural_missing_files": structural_paths[:16],
        "syntax": syntax, "targeted_test_selection": modules,
        "targeted_test_execution": tests,
        "deferred_integrity_groups": required,
        "full_suite_waived": False, "merge_gate_satisfied": False,
        "certified": False, "integrity_executed": False,
        "tests_executed": tests["tests_executed"],
        "benchmarks_executed": False, "graph_rebuilt": False,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "timings_seconds": {"syntax": syntax_seconds, "test_selection": planning_seconds,
                            "test_execution": tests.get("duration_seconds", 0)},
        "next_action": (
            "Fix syntax/test failures before continuing." if failed
            else "Review truncated/structural changes before refactoring." if incomplete
            else "Complete policy-required Atlas Integrity and CI before merge."),
        "limits": ("Development feedback only; source syntax and up to 8 "
                   "suggested test modules do not certify full behavior, RAM, "
                   "preload, Qt ownership or the release policy."),
    }
