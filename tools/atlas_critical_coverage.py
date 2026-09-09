from __future__ import annotations

import argparse
import io
import json
import trace
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = Path("tools/atlas_critical_coverage.json")


def load_policy(root: Path, policy: Path = DEFAULT_POLICY) -> dict[str, Any]:
    path = policy if policy.is_absolute() else root / policy
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    targets = payload.get("targets")
    if payload.get("schema_version") != 1 or not isinstance(targets, list) or not targets:
        raise ValueError("critical coverage policy schema_version must be 1")
    for target in targets:
        minimum = target.get("minimum_percent")
        if not isinstance(minimum, (int, float)) or not 0 <= minimum <= 100:
            raise ValueError("critical coverage minimum must be between 0 and 100")
    return payload


def execute(root: Path = ROOT, policy_path: Path = DEFAULT_POLICY, *, measure_only: bool = False) -> dict[str, Any]:
    policy = load_policy(root, policy_path)
    modules = sorted({name for target in policy["targets"] for name in target["tests"]})
    stream = io.StringIO()
    holder: dict[str, Any] = {}

    def run_tests() -> None:
        suite = unittest.TestLoader().loadTestsFromNames(modules)
        holder["result"] = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)

    tracer = trace.Trace(count=True, trace=False)
    tracer.runfunc(run_tests)
    counts = tracer.results().counts
    rows = []
    for target in policy["targets"]:
        path = (root / target["module"]).resolve()
        executable = set(trace._find_executable_linenos(str(path)))
        covered = {line for (filename, line), hits in counts.items() if hits and Path(filename).resolve() == path}
        covered &= executable
        percent = round(100.0 * len(covered) / len(executable), 2) if executable else 0.0
        minimum = float(target["minimum_percent"])
        rows.append(
            {
                "module": target["module"],
                "covered_lines": len(covered),
                "executable_lines": len(executable),
                "percent": percent,
                "minimum_percent": minimum,
                "status": "MEASURED" if measure_only else ("PASS" if percent >= minimum else "BLOCKED"),
            }
        )
    test_result = holder["result"]
    tests_passed = test_result.wasSuccessful()
    verdict = "MEASURED_ONLY" if measure_only and tests_passed else (
        "PASS" if tests_passed and all(row["status"] == "PASS" for row in rows) else "BLOCKED"
    )
    return {
        "schema_version": 1,
        "tests": {"run": test_result.testsRun, "passed": tests_passed, "output": "" if tests_passed else stream.getvalue()},
        "modules": rows,
        "verdict": verdict,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure critical Atlas module coverage without external dependencies.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--measure-only", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = execute(args.root.resolve(), args.policy, measure_only=args.measure_only)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print("ATLAS CRITICAL COVERAGE")
        for row in report["modules"]:
            print(f"{row['module']:56} {row['percent']:6.2f}% floor={row['minimum_percent']:6.2f}% {row['status']}")
        print(f"VERDICT: {report['verdict']}")
    return 0 if report["verdict"] in {"PASS", "MEASURED_ONLY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
