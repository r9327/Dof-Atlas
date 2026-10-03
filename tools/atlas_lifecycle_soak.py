from __future__ import annotations

import argparse
import io
import json
import time
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CYCLES = 3


def _flatten(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


def execute(
    modules: list[str],
    *,
    cycles: int = DEFAULT_CYCLES,
    suite_factory: Callable[[], unittest.TestSuite] | None = None,
) -> dict[str, Any]:
    if cycles < 2:
        raise ValueError("lifecycle soak requires at least two cycles")
    if not modules and suite_factory is None:
        raise ValueError("lifecycle soak requires test modules")

    loader = unittest.TestLoader()
    factory = suite_factory or (lambda: loader.loadTestsFromNames(modules))
    expected_ids: list[str] | None = None
    rows: list[dict[str, Any]] = []
    total_tests = 0

    for cycle in range(1, cycles + 1):
        tests = list(_flatten(factory()))
        test_ids = [test.id() for test in tests]
        if expected_ids is None:
            expected_ids = test_ids
        elif test_ids != expected_ids:
            return {
                "schema_version": 1,
                "kind": "lifecycle_soak",
                "verdict": "FAIL",
                "reason": "test inventory changed between cycles",
                "cycles_requested": cycles,
                "cycles_completed": cycle - 1,
                "counts": {"tests_per_cycle": len(expected_ids), "total_tests": total_tests},
                "cycles": rows,
            }

        stream = io.StringIO()
        started = time.perf_counter()
        result = unittest.TextTestRunner(stream=stream, verbosity=1).run(
            unittest.TestSuite(tests)
        )
        total_tests += result.testsRun
        successful = result.wasSuccessful() and not result.skipped
        row = {
            "cycle": cycle,
            "tests": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "status": "PASS" if successful else "FAIL",
        }
        if not successful:
            row["output_tail"] = "\n".join(stream.getvalue().splitlines()[-40:])
        rows.append(row)
        if not successful:
            break

    passed = len(rows) == cycles and all(row["status"] == "PASS" for row in rows)
    return {
        "schema_version": 1,
        "kind": "lifecycle_soak",
        "verdict": "PASS" if passed else "FAIL",
        "cycles_requested": cycles,
        "cycles_completed": len(rows),
        "counts": {
            "tests_per_cycle": len(expected_ids or ()),
            "total_tests": total_tests,
            "failures": sum(row["failures"] for row in rows),
            "errors": sum(row["errors"] for row in rows),
            "skipped": sum(row["skipped"] for row in rows),
        },
        "cycles": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Repeat lifecycle contracts in one long-lived Python process."
    )
    parser.add_argument("--cycles", type=int, default=DEFAULT_CYCLES)
    parser.add_argument("--modules", nargs="+", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = execute(args.modules, cycles=args.cycles)
    except ValueError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("ATLAS LIFECYCLE SOAK")
        print(
            f"Cycles: {report['cycles_completed']}/{report['cycles_requested']} | "
            f"Tests: {report['counts']['total_tests']} | Verdict: {report['verdict']}"
        )
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
