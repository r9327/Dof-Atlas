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
        self._previous_finish = time.perf_counter()
        self._test_started = self._previous_finish
        self._fixture_before_test = 0.0

    def startTest(self, test):
        now = time.perf_counter()
        self._fixture_before_test = max(0.0, now - self._previous_finish)
        self._test_started = now
        super().startTest(test)

    def stopTest(self, test):
        finished = time.perf_counter()
        try:
            identity = canonical(test.id())
        except ValueError:
            identity = None
        if identity is not None:
            elapsed = max(0.0, finished - self._test_started)
            self.timings.append({
                "test_id": identity,
                "test_seconds": round(elapsed, 6),
                "preceding_fixture_seconds": round(self._fixture_before_test, 6),
                "total_seconds": round(elapsed + self._fixture_before_test, 6),
            })
        self._previous_finish = finished
        super().stopTest(test)

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


def timing_report(expected: list[str], timings: list[dict[str, object]], *,
                  sha: str, suite_seconds: float, successful: bool) -> dict:
    """Diagnostic only: never substitutes for the exact-SHA success ledger.

    Preceding fixture time includes class setup/teardown between test cases.
    Time after the final test remains separately unattributed.
    """
    if not SHA.fullmatch(sha):
        raise ValueError("Invalid timing SHA")
    names = [row["test_id"] for row in timings]
    if not expected or len(set(expected)) != len(expected) or sorted(names) != sorted(expected):
        raise ValueError("Incomplete or duplicate per-test timings")
    ordered = sorted(timings, key=lambda row: (-row["total_seconds"], row["test_id"]))
    observed = sum(row["total_seconds"] for row in ordered)
    return {
        "schema_version": 1,
        "kind": "atlas_full_unittest_timing_diagnostic",
        "candidate_sha": sha,
        "status": "COMPLETE" if successful else "FAILED",
        "tests_timed": len(ordered),
        "suite_seconds": round(suite_seconds, 3),
        "unattributed_tail_seconds": round(max(0.0, suite_seconds - observed), 3),
        "slowest_20": ordered[:20],
        "per_test": ordered,
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
    args = parser.parse_args(argv)
    args.proof_file.unlink(missing_ok=True)
    timing_file = args.proof_file.with_name(args.proof_file.stem + "_timings.json")
    # Phase Certification uploads this directory, not ci_app_logs.
    phase_logs = Path("artifacts/phase_certification")
    if phase_logs.is_dir():
        timing_file = phase_logs / "05_full_unittest_timings.json"
    timing_file.unlink(missing_ok=True)
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
    started = time.perf_counter()
    result = unittest.TextTestRunner(
        verbosity=2 if args.verbose else 1, resultclass=ProofResult,
    ).run(suite)
    suite_seconds = time.perf_counter() - started
    try:
        timing = timing_report(expected, result.timings, sha=head,
                               suite_seconds=suite_seconds,
                               successful=result.wasSuccessful())
        timing_file.parent.mkdir(parents=True, exist_ok=True)
        temporary_timing = timing_file.with_suffix(".json.tmp")
        temporary_timing.write_text(
            json.dumps(timing, ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        temporary_timing.replace(timing_file)
        for slow in timing["slowest_20"]:
            print("FULL_SLOW_TEST {:.3f}s (fixture {:.3f}s) {}".format(
                slow["total_seconds"], slow["preceding_fixture_seconds"],
                slow["test_id"],
            ), file=sys.stderr)
    except (OSError, ValueError) as exc:
        print("FULL timing diagnostics unavailable: " + str(exc), file=sys.stderr)
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
