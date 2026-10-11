from __future__ import annotations

"""Structured, exact-run unittest evidence; never infer passes from log text.

This runner executes the *same* canonical unittest discovery and emits a
bounded per-test ledger only after the complete suite returns successfully.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import unittest

SCHEMA = 1
SHA = re.compile(r"^[0-9a-f]{40}$")


def canonical(test_id: str) -> str:
    if not isinstance(test_id, str) or not re.fullmatch(
        r"(?:tests\.)?test_[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+",
        test_id,
    ):
        raise ValueError(f"Unsupported unittest identity: {test_id!r}")
    return test_id if test_id.startswith("tests.") else "tests." + test_id


def ids(suite: unittest.TestSuite) -> list[str]:
    result: list[str] = []
    for child in suite:
        if isinstance(child, unittest.TestSuite):
            result.extend(ids(child))
        else:
            result.append(canonical(child.id()))
    return result


class ProofResult(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.completed: list[tuple[str, str]] = []
        self.timings: list[dict[str, object]] = []
        self._last_stop = time.perf_counter()
        self._active_start = self._last_stop
        self._gap_before = 0.0

    def startTest(self, test):
        started = time.perf_counter()
        # The gap includes class/module fixture setup and preceding teardown.
        self._gap_before = max(0.0, started - self._last_stop)
        self._active_start = started
        super().startTest(test)

    def stopTest(self, test):
        elapsed = max(0.0, time.perf_counter() - self._active_start)
        self.timings.append({
            "id": canonical(test.id()),
            "test_seconds": round(elapsed, 6),
            "fixture_gap_before_seconds": round(self._gap_before, 6),
        })
        super().stopTest(test)
        self._last_stop = time.perf_counter()

    def _record(self, test: unittest.case.TestCase, status: str) -> None:
        self.completed.append((canonical(test.id()), status))

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "ok")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "skip")

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._record(test, "expected_failure")

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record(test, "unexpected_success")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "fail")

    def addError(self, test, err):
        super().addError(test, err)
        try:
            self._record(test, "error")
        except ValueError:
            # A setUpClass/tearDownClass _ErrorHolder is not a real TestCase.
            pass


def validated_ledger(expected: list[str], completed: list[tuple[str, str]],
                     *, tests_run: int, successful: bool, sha: str) -> dict:
    if not SHA.fullmatch(sha):
        raise ValueError("Expected exact Git SHA")
    if not successful:
        raise ValueError("FULL suite did not succeed")
    if not expected or len(set(expected)) != len(expected) or len(expected) != tests_run:
        raise ValueError("Discovered test ids are incomplete or duplicated")
    if len(completed) != len(expected):
        raise ValueError("Missing or multiple per-test status records")
    statuses: dict[str, str] = {}
    for test_id, status in completed:
        if test_id in statuses or status not in ("ok", "skip", "expected_failure"):
            raise ValueError("Duplicate or non-pass terminal test event")
        statuses[test_id] = status
    if set(statuses) != set(expected):
        raise ValueError("Unexpected or missing exact test IDs")
    return {
        "schema_version": SCHEMA,
        "kind": "atlas_full_unittest_exact_ledger",
        "candidate_sha": sha,
        "status": "COMPLETE",
        "tests_run": tests_run,
        "expected_test_ids": sorted(expected),
        "successful_test_ids": sorted(k for k, v in statuses.items() if v == "ok"),
        "non_successful_test_ids": sorted(k for k, v in statuses.items() if v != "ok"),
        "source": "unittest.TextTestResult.addSuccess/addSkip/addExpectedFailure",
    }


def timing_profile(ledger: dict, rows: list[dict[str, object]], *,
                   elapsed_seconds: float) -> dict:
    """Advisory timing data; never a substitute for actual test results."""
    expected = set(ledger["expected_test_ids"])
    if len(rows) != len(expected) or {row["id"] for row in rows} != expected:
        raise ValueError("Timings are incomplete or duplicated")
    cases = []
    modules: dict[str, dict[str, float | int]] = {}
    for row in rows:
        test_seconds = float(row["test_seconds"])
        fixture_seconds = float(row["fixture_gap_before_seconds"])
        if not (0 <= test_seconds < float("inf") and 0 <= fixture_seconds < float("inf")):
            raise ValueError("Invalid per-test timing")
        test_id = str(row["id"])
        module = ".".join(test_id.split(".")[:2])
        cases.append({
            "id": test_id,
            "test_seconds": test_seconds,
            "fixture_gap_before_seconds": fixture_seconds,
            "total_seconds": round(test_seconds + fixture_seconds, 6),
        })
        aggregate = modules.setdefault(module, {"cases": 0, "test_seconds": 0.0,
                                                "fixture_gap_seconds": 0.0})
        aggregate["cases"] += 1
        aggregate["test_seconds"] += test_seconds
        aggregate["fixture_gap_seconds"] += fixture_seconds
    for module in modules.values():
        module["test_seconds"] = round(module["test_seconds"], 6)
        module["fixture_gap_seconds"] = round(module["fixture_gap_seconds"], 6)
    return {
        "kind": "atlas_full_test_timings",
        "schema_version": 1,
        "candidate_sha": ledger["candidate_sha"],
        "advisory_only": True,
        "cases_run": len(cases),
        "suite_seconds": round(elapsed_seconds, 3),
        "modules": dict(sorted(modules.items(), key=lambda x: -(
            x[1]["test_seconds"] + x[1]["fixture_gap_seconds"]))),
        "top20": sorted(cases, key=lambda x: -x["total_seconds"])[:20],
        "cases": cases,
    }


def load_verified(path: Path, *, sha: str) -> dict[str, object]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_500_000:
        raise ValueError("Missing, unsafe or oversized FULL test ledger")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(payload, dict)
            or payload.get("kind") != "atlas_full_unittest_exact_ledger"
            or payload.get("schema_version") != SCHEMA
            or payload.get("status") != "COMPLETE"
            or payload.get("candidate_sha") != sha):
        raise ValueError("FULL evidence is stale or invalid")
    expected = payload.get("expected_test_ids")
    success = payload.get("successful_test_ids")
    non_success = payload.get("non_successful_test_ids")
    count = payload.get("tests_run")
    if (not isinstance(expected, list) or not isinstance(success, list)
            or not isinstance(non_success, list) or type(count) is not int
            or not expected or count != len(expected)):
        raise ValueError("Incomplete FULL result ledger")
    if any(not isinstance(x, str) for x in (*expected, *success, *non_success)):
        raise ValueError("Invalid test identity in FULL ledger")
    if (expected != sorted(set(expected))
            or success != sorted(set(success))
            or non_success != sorted(set(non_success))
            or set(success) & set(non_success)
            or set(expected) != set(success) | set(non_success)):
        raise ValueError("FULL ledger does not account for all tests")
    if any(canonical(x) != x for x in expected):
        raise ValueError("Noncanonical test identity")
    return payload


def module_proofs(payload: dict) -> dict[str, int]:
    expected = payload["expected_test_ids"]
    non_success = set(payload["non_successful_test_ids"])
    all_module_ids: dict[str, set[str]] = {}
    for test_id in expected:
        module = ".".join(test_id.split(".")[:2])
        all_module_ids.setdefault(module, set()).add(test_id)
    return {
        module: len(tests) for module, tests in all_module_ids.items()
        if tests and not tests.intersection(non_success)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("discover",))
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-s", "--start-directory", default="tests")
    parser.add_argument("-p", "--pattern", default="test_*.py")
    parser.add_argument("--proof-file", type=Path,
                        default=Path("artifacts/ci_app_logs/05_full_unittest_proof.json"))
    parser.add_argument("--timings-file", type=Path,
                        default=Path("artifacts/phase_certification/05_full_test_timings.json"))
    args = parser.parse_args(argv)
    args.proof_file.unlink(missing_ok=True)
    args.timings_file.unlink(missing_ok=True)
    loader = unittest.TestLoader()
    suite = loader.discover(args.start_directory, pattern=args.pattern)
    if loader.errors:
        for err in loader.errors:
            print(err, file=sys.stderr)
        return 1
    try:
        expected = ids(suite)
    except ValueError as exc:
        print("Invalid full discovery: " + str(exc), file=sys.stderr)
        return 1
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True, timeout=10).stdout.strip()
    timing_started = time.perf_counter()
    result = unittest.TextTestRunner(
        verbosity=2 if args.verbose else 1, resultclass=ProofResult,
    ).run(suite)
    suite_elapsed = time.perf_counter() - timing_started
    if not result.wasSuccessful():
        return 1
    try:
        proof = validated_ledger(expected, result.completed,
                                 tests_run=result.testsRun,
                                 successful=result.wasSuccessful(), sha=head)
    except ValueError as exc:
        print("No reusable FULL evidence: " + str(exc), file=sys.stderr)
        return 0  # Tests passed, but all other groups will run independently.
    args.proof_file.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.proof_file.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(proof, ensure_ascii=False, separators=(",", ":")) + "\n",
                         encoding="utf-8")
    temporary.replace(args.proof_file)
    try:
        timings = timing_profile(proof, result.timings, elapsed_seconds=suite_elapsed)
        args.timings_file.parent.mkdir(parents=True, exist_ok=True)
        timing_tmp = args.timings_file.with_suffix(".json.tmp")
        timing_tmp.write_text(json.dumps(timings, ensure_ascii=False, separators=(",", ":")) + "\n",
                              encoding="utf-8")
        timing_tmp.replace(args.timings_file)
    except (OSError, ValueError) as exc:
        # Diagnostic telemetry must not alter the certified unittest result.
        print("Optional FULL timing report unavailable: " + str(exc), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
