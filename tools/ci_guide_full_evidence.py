"""Fail-closed reuse of exact, successful FULL unittest coverage in Guide CI.

Only the three independently re-executed test modules are eligible. No
equivalence is claimed from mere module names, counts or a stale SHA.
Absent/ambiguous evidence means the canonical Guide runner executes them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REUSED_MODULES = {
    "11_existing_guides_tests": "tests.test_guides_phase3",
    "12_existing_success_tests": "tests.test_achievements_lot7",
    "13_existing_shell_tests": "tests.test_pyside_shell",
}
TEST_HEADER = re.compile(
    r"(?m)^test_[A-Za-z0-9_]+\s+\(((?:tests\.)?test_[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.test_[A-Za-z0-9_]+)\)\s+\.\.\.\s+([^\r\n]+)$"
)
FULL_SUCCESS = re.compile(
    r"(?ms)^Ran\s+(\d+)\s+tests?\s+in\s+[0-9.]+s\s*\n\s*OK\s*\Z"
)


def _all_test_ids(suite: unittest.TestSuite) -> list[str]:
    names = []
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            names.extend(_all_test_ids(item))
        else:
            names.append(item.id())
    return names


def expected_tests() -> dict[str, list[str]]:
    loader = unittest.TestLoader()
    output = {}
    for stage, module in REUSED_MODULES.items():
        suite = loader.loadTestsFromName(module)
        names = _all_test_ids(suite)
        if loader.errors or not names or len(names) != len(set(names)):
            raise ValueError("unreliable unittest discovery: " + module)
        output[stage] = names
    return output


def prove(log_text: str, expected: dict[str, list[str]]) -> dict[str, int]:
    log_text = log_text.replace("\r\n", "\n")
    if not FULL_SUCCESS.search(log_text):
        raise ValueError("FULL has no successful terminal unittest verdict")
    records: dict[str, list[tuple[str, str]]] = {
        module: [] for module in REUSED_MODULES.values()
    }
    # Require every actual target test to end in 'ok', with no skip/xfail.
    for match in TEST_HEADER.finditer(log_text):
        test_id = match.group(1)
        canonical = test_id if test_id.startswith("tests.") else "tests." + test_id
        module = ".".join(canonical.split(".")[:2])
        if module in records:
            records[module].append((canonical, match.group(2).strip()))
    result = {}
    for stage, module in REUSED_MODULES.items():
        observed = records[module]
        needed = expected.get(stage, [])
        if not needed or len(needed) != len(set(needed)):
            raise ValueError("missing or duplicate discovery for " + module)
        if len(observed) != len(needed):
            raise ValueError("missing, extra or duplicate test for " + module)
        if any(status != "ok" for _, status in observed):
            raise ValueError("non-successful test status in " + module)
        if sorted(test_id for test_id, _ in observed) != sorted(needed):
            raise ValueError("test ID mismatch in " + module)
        result[stage] = len(needed)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        root = args.root.resolve(strict=True)
        log = args.log.resolve(strict=True)
        target = args.out.resolve()
        if not log.is_relative_to(root) or not target.is_relative_to(root):
            raise ValueError("evidence paths must stay inside the checkout")
        if os.getenv("ATLAS_FULL_SUITE_SUCCESS") != "success":
            raise ValueError("FULL job did not report a successful test step")
        if os.getenv("GITHUB_SHA") != args.sha:
            raise ValueError("GitHub exact SHA mismatch")
        actual = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root,
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
        if actual != args.sha:
            raise ValueError("checkout exact SHA mismatch")
        raw = log.read_bytes()
        covered = prove(raw.decode("utf-8"), expected_tests())
        payload = {
            "schema_version": 1, "kind": "atlas_guide_exact_full_reuse",
            "head": actual, "full_log_sha256": hashlib.sha256(raw).hexdigest(),
            "stages": covered, "status": "PROVEN",
            "reason": "All discovered test IDs succeeded in exact-SHA FULL",
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("EXACT FULL TEST EVIDENCE PASS: " + str(covered))
        return 0
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        # Never leave a stale proof: caller must run original tests on failure.
        try:
            args.out.unlink(missing_ok=True)
        except OSError:
            pass
        print("NO REUSE: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
