from __future__ import annotations

"""Opt-in, diff-scoped developer tests. Never a substitute for Atlas FULL CI."""

import argparse
import json
import platform
import subprocess
import sys
import time
import unittest
from pathlib import Path
from typing import Iterable

from tools import ai_context


ROOT = Path(__file__).resolve().parents[1]
MAX_CHANGED_PATHS = 512
MAX_SELECTED_MODULES = 128

TOOL_SPEC = {
    "schema_version": 1,
    "id": "ci_development_tests",
    "role": "developer_test_selection_and_timing",
    "capabilities": ["validation", "ai_context", "performance"],
    "modes": ["plan", "run"],
    "cost_hint": "variable",
    "side_effects": "repo_mutation_explicit",
    "structured_output": True,
    "canonical": True,
    "recommended_tests": ["tests.test_ci_dev_tests"],
    "target_scopes": ["quality_ci"],
}


class SelectionError(ValueError):
    """A safe, deterministic selection cannot be established."""


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    if completed.returncode != 0:
        raise SelectionError(completed.stderr.strip() or f"git {args[0]} failed")
    return completed.stdout.strip()


def changed_paths(root: Path, base_ref: str) -> list[str]:
    """Include committed, staged, unstaged and untracked local changes."""
    if not base_ref or base_ref.startswith("-"):
        raise SelectionError("base ref required")
    _git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
    paths: set[str] = set()
    for args in (
        ("diff", "--name-only", "--diff-filter=ACDMRTUXB", f"{base_ref}...HEAD"),
        ("diff", "--name-only", "--diff-filter=ACDMRTUXB"),
        ("diff", "--cached", "--name-only", "--diff-filter=ACDMRTUXB"),
        ("ls-files", "--others", "--exclude-standard"),
    ):
        paths.update(_git(root, *args).splitlines())
    return sorted(path for path in paths if path.strip())


def plan(root: Path, paths: Iterable[str], *, head: str = "") -> dict[str, object]:
    """Use the canonical AI Context routing and fail closed on unknown files."""
    selected_paths = sorted(set(ai_context.normalize_path(p) for p in paths))
    if not selected_paths or len(selected_paths) > MAX_CHANGED_PATHS:
        raise SelectionError("Expected 1..512 changed paths; no implicit full-suite fallback")
    if any(not p or p.startswith("/") or p == ".." or p.startswith("../") or
           "/../" in p for p in selected_paths):
        raise SelectionError("Changed paths must be relative repository paths")

    routed = ai_context.recommended_tests(root, selected_paths)
    if len(routed) > MAX_SELECTED_MODULES:
        raise SelectionError("Too many test modules for developer runner")
    unmapped = [p for p in selected_paths if ai_context.classify_path(p) == "repository"]
    modules = list(dict.fromkeys(routed))
    status = "TARGETED_ADVISORY" if modules and not unmapped else "REVIEW_REQUIRED"
    return {
        "schema_version": 1,
        "kind": "atlas_developer_targeted_tests",
        "status": status,
        "mode": "DEVELOPMENT_ONLY",
        "head": head,
        "changed_paths": selected_paths,
        "modules": modules,
        "unmapped_paths": unmapped,
        "full_suite_waived": False,
        "certified": False,
        "tests_executed": False,
        "reason": "Canonical AI Context recommendations; not proof of exhaustive dependency coverage",
        "next_gate": "Run Atlas Integrity gates appropriate to diff risk; FULL certification remains mandatory",
    }


class TimedResult(unittest.TextTestResult):
    """Capture measured per-test duration without altering unittest semantics."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._started: dict[int, float] = {}
        self.durations: list[dict[str, object]] = []

    def startTest(self, test):
        self._started[id(test)] = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        started = self._started.pop(id(test), None)
        if started is not None:
            self.durations.append({
                "test": test.id(),
                "seconds": round(max(0.0, time.perf_counter() - started), 6),
            })
        super().stopTest(test)


def run_targeted(modules: list[str], *, head: str) -> tuple[int, dict[str, object]]:
    """Run a selected suite in one process, preserving Qt/test isolation order."""
    start = time.perf_counter()
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    result = unittest.TextTestRunner(verbosity=2, resultclass=TimedResult).run(suite)
    duration = round(time.perf_counter() - start, 3)
    succeeded = result.wasSuccessful() and result.testsRun > 0
    report: dict[str, object] = {
        "schema_version": 1,
        "kind": "atlas_developer_test_timings",
        "head": head,
        "mode": "DEVELOPMENT_ONLY",
        "status": "PASS" if succeeded else "FAIL",
        "selected_modules": list(modules),
        "python_version": platform.python_version(),
        "platform": sys.platform,
        "test_count": result.testsRun,
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skipped": len(result.skipped),
        "expected_failures": len(result.expectedFailures),
        "unexpected_successes": len(result.unexpectedSuccesses),
        "duration_seconds": duration,
        "top_slowest_tests": sorted(result.durations, key=lambda row: (-row["seconds"], row["test"]))[:20],
        "certified": False,
        "full_suite_waived": False,
        "benchmark_executed": False,
    }
    return (0 if succeeded else 1), report


def _write_report(root: Path, relative: str, payload: dict[str, object]) -> None:
    """Explicit artifact output, never writing to tracked product files."""
    if not relative:
        return
    candidate = root / relative
    target = candidate.resolve()
    artifact_root = (root / "artifacts").resolve()
    if candidate.is_symlink() or not target.is_relative_to(artifact_root) or target.suffix != ".json":
        raise SelectionError("--report must be a JSON file inside artifacts/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default="origin/main", help="Git merge-base for diff selection")
    parser.add_argument("--path", action="append", dest="paths", default=[], help="Explicit changed path (repeatable); skips git discovery")
    parser.add_argument("--run", action="store_true", help="Opt in to executing selected tests; by default, plan only")
    parser.add_argument("--report", default="", help="Optional JSON report under artifacts/; explicit write")
    parser.add_argument("--json", action="store_true", help="Print machine-readable plan")
    args = parser.parse_args(argv)
    root = ROOT.resolve()
    try:
        paths = args.paths if args.paths else changed_paths(root, args.base_ref)
        head = _git(root, "rev-parse", "HEAD")
        selection = plan(root, paths, head=head)
        if args.json:
            print(json.dumps(selection, indent=2, ensure_ascii=False))
        else:
            print(f"Atlas developer tests: {selection['status']} ({len(selection['modules'])} modules)")
            for module in selection["modules"]:
                print(f"  {module}")
            for path in selection["unmapped_paths"]:
                print(f"  UNMAPPED: {path}")
        if not args.run:
            if args.report:
                _write_report(root, args.report, selection)
            return 0 if selection["status"] == "TARGETED_ADVISORY" else 2
        if selection["status"] != "TARGETED_ADVISORY":
            print("Refusing incomplete selection; use canonical gates for broad changes", file=sys.stderr)
            return 2
        code, metrics = run_targeted(selection["modules"], head=head)
        metrics["changed_paths"] = selection["changed_paths"]
        if args.report:
            _write_report(root, args.report, metrics)
        return code
    except (SelectionError, OSError) as exc:
        print(f"Atlas developer tests: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
