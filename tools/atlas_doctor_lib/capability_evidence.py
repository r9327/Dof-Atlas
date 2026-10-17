from __future__ import annotations

"""Exact-worktree test evidence for Doctor's capability inventory.

This module proves only that the declared behavioral witnesses passed for one
repository snapshot.  It deliberately cannot issue release certification.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .capability_matrix import BEHAVIOR_ANCHORS, NEGATIVE_BEHAVIOR_ANCHORS, capability_test_ids, capability_control_ids
from .core import git_state, utc_now

SCHEMA_VERSION = 2
# Keep the full bounded unittest -v transcript for per-method attestation.
# 12 KiB truncated ordinary 36-witness runs; exceeding this larger limit still blocks.
MAX_LOG_CHARS = 256_000


def _tail(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return (value or "")[-MAX_LOG_CHARS:]


def _digest(payload: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in payload.items()
                if key != "evidence_digest"}
    raw = json.dumps(unsigned, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _witness_suite_passed(stderr: Any, expected_count: int) -> bool:
    """A zero exit can include skips/expected failures; require all witnesses."""
    if not isinstance(stderr, str):
        return False
    summary = re.search(
        r"(?:^|\n)Ran ([0-9]+) tests? in [^\r\n]+\r?\n\r?\n([^\r\n]+)\r?\n?\Z",
        stderr,
    )
    return bool(summary and summary[1] == str(expected_count) and summary[2] == "OK")


def _verbose_verdicts(stderr: Any) -> dict[str, list[str]]:
    """Observe exact unittest methods, not just a green aggregate count."""
    verdicts: dict[str, list[str]] = {}
    if not isinstance(stderr, str):
        return verdicts
    for line in stderr.splitlines():
        matched = re.fullmatch(
            r"(test_[A-Za-z0-9_]+) \(((?:tests\.)?test_[A-Za-z0-9_]+\.[A-Za-z0-9_]+)\) \.\.\. (ok|FAIL|ERROR|skipped .+|expected failure|unexpected success)",
            line.strip(),
        )
        if matched:
            # Rebuild the canonical ID even when the tests package is not imported.
            ident = ("tests." if not matched[2].startswith("tests.") else "") + matched[2] + "." + matched[1]
            verdicts.setdefault(ident, []).append(matched[3])
    return verdicts


def _evidence_rows(mapping: dict[str, str], verdicts: dict[str, list[str]], *, suite_pass: bool) -> list[dict[str, str]]:
    return [
        {"capability_id": ident, "test_id": test_id,
         "observed_result": verdicts.get(test_id, ["NOT_OBSERVED"]),
         "result": "PASS" if suite_pass and verdicts.get(test_id) == ["ok"] else "UNVERIFIED"}
        for ident, test_id in sorted(mapping.items())
    ]


def run_capability_witnesses(root: Path, *, timeout: int = 300) -> dict[str, Any]:
    """Execute positive + negative controls in one bounded fresh process."""
    root = root.resolve()
    before = git_state(root)
    test_ids = capability_test_ids(root)
    control_ids = capability_control_ids(root)
    missing = sorted((set(BEHAVIOR_ANCHORS) - set(test_ids))
                     | (set(NEGATIVE_BEHAVIOR_ANCHORS) - set(control_ids)))
    duplicate_ids = len(set([*test_ids.values(), *control_ids.values()])) != len(test_ids) + len(control_ids)
    requested = sorted([*test_ids.values(), *control_ids.values()])
    started_at = utc_now()
    started = time.monotonic()
    # Import the test files as top-level modules. Importing "tests.<module>" would
    # execute tests/__init__.py, which eagerly requires a Qt QApplication.
    # The focused stdlib job deliberately has no PySide6 installed.
    command = [sys.executable, "-m", "unittest", "-v",
               *[test_id.removeprefix("tests.") for test_id in requested]]
    return_code: int | None = None
    stdout = ""
    stderr = ""
    timed_out = False
    raw_log_size = 0
    if not missing and not duplicate_ids:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        # Make bare test modules importable; preserve the repository imports.
        env["PYTHONPATH"] = os.pathsep.join(filter(None, (
            str(root / "tests"), str(root), env.get("PYTHONPATH", ""),
        )))
        try:
            completed = subprocess.run(
                command, cwd=root, env=env, text=True, capture_output=True,
                check=False, timeout=max(1, min(timeout, 900)),
            )
            return_code = completed.returncode
            raw_log_size = len(completed.stderr or "")
            stdout = _tail(completed.stdout)
            stderr = _tail(completed.stderr)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _tail(exc.stdout)
            stderr = _tail(exc.stderr)
            raw_log_size = MAX_LOG_CHARS + 1
    after = git_state(root)
    unchanged = (before["head"] == after["head"]
                 and before["dirty_digest"] == after["dirty_digest"])
    log_truncated = raw_log_size > MAX_LOG_CHARS
    observed = _verbose_verdicts(stderr)
    exact_results = all(observed.get(test_id) == ["ok"] for test_id in requested)
    aggregate_pass = (
        not missing and not duplicate_ids and not timed_out and not log_truncated
        and return_code == 0 and unchanged
        and _witness_suite_passed(stderr, len(requested)) and exact_results
    )
    status = ("PASS" if aggregate_pass else "BLOCKED"
              if missing or duplicate_ids or timed_out or log_truncated or not unchanged
              else "FAIL")
    result = {
        "schema_version": SCHEMA_VERSION,
        "kind": "doctor_capability_test_evidence",
        "status": status,
        "candidate_sha": before["head"],
        "dirty": before["dirty"],
        "dirty_digest": before["dirty_digest"],
        "worktree_unchanged": unchanged,
        "started_at": started_at,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "command": command,
        "return_code": return_code,
        "timed_out": timed_out,
        "log_truncated": log_truncated,
        "log_limit_chars": MAX_LOG_CHARS,
        "raw_stderr_chars": raw_log_size,
        "missing_witnesses": missing,
        "duplicate_test_ids": duplicate_ids,
        "witnesses": _evidence_rows(test_ids, observed, suite_pass=aggregate_pass),
        "control_witnesses": _evidence_rows(control_ids, observed, suite_pass=aggregate_pass),
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "certification": "NOT_CERTIFIED",
        "limits": (
            "These are fresh exact-worktree unittest witnesses including boundary "
            "controls, not production Qt/Windows runtime observations, independent "
            "CI attestation or release certification."
        ),
    }
    result["evidence_digest"] = _digest(result)
    return result


def validate_capability_evidence(root: Path, payload: Any) -> dict[str, Any]:
    """Validate every executed method and same-worktree provenance; fail closed."""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"status": "BLOCKED", "errors": ["EVIDENCE_NOT_OBJECT"]}
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append("SCHEMA_VERSION_UNSUPPORTED")
    if payload.get("kind") != "doctor_capability_test_evidence":
        errors.append("EVIDENCE_KIND_INVALID")
    if payload.get("evidence_digest") != _digest(payload):
        errors.append("EVIDENCE_DIGEST_MISMATCH")
    state = git_state(root.resolve())
    if payload.get("candidate_sha") != state["head"]:
        errors.append("CANDIDATE_SHA_MISMATCH")
    if payload.get("dirty_digest") != state["dirty_digest"]:
        errors.append("WORKTREE_DIGEST_MISMATCH")
    if payload.get("dirty") is not state["dirty"]:
        errors.append("WORKTREE_DIRTY_STATE_MISMATCH")
    if payload.get("worktree_unchanged") is not True:
        errors.append("WORKTREE_CHANGED_DURING_RUN")
    if payload.get("status") != "PASS" or payload.get("return_code") != 0:
        errors.append("WITNESS_SUITE_NOT_PASS")
    if payload.get("log_truncated") is not False or payload.get("timed_out") is not False:
        errors.append("WITNESS_LOG_TRUNCATED_OR_TIMED_OUT")
    expected = capability_test_ids(root.resolve())
    controls = capability_control_ids(root.resolve())
    requested = sorted([*expected.values(), *controls.values()])
    if len(expected) != len(BEHAVIOR_ANCHORS) or len(controls) != len(NEGATIVE_BEHAVIOR_ANCHORS):
        errors.append("WITNESS_ANCHOR_MISSING")
    if len(requested) != len(set(requested)):
        errors.append("WITNESS_TEST_DUPLICATE")
    if payload.get("command") != [sys.executable, "-m", "unittest", "-v",
                                  *[test_id.removeprefix("tests.") for test_id in requested]]:
        errors.append("WITNESS_COMMAND_MISMATCH")
    log = payload.get("stderr_tail")
    if not _witness_suite_passed(log, len(requested)):
        errors.append("WITNESS_SUITE_INCOMPLETE_OR_NOT_ALL_PASSED")
    observed = _verbose_verdicts(log)
    if any(observed.get(test_id) != ["ok"] for test_id in requested):
        errors.append("WITNESS_VERBOSE_VERDICTS_INCOMPLETE")
    for key, required in (("witnesses", expected), ("control_witnesses", controls)):
        supplied: dict[str, str] = {}
        rows = payload.get(key)
        if not isinstance(rows, list):
            errors.append(key.upper() + "_NOT_LIST")
            continue
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("capability_id"), str):
                errors.append("WITNESS_INVALID")
                continue
            ident = row["capability_id"]
            if ident in supplied:
                errors.append("WITNESS_DUPLICATE")
            supplied[ident] = row.get("test_id", "")
            if row.get("result") != "PASS":
                errors.append("WITNESS_NOT_PASS")
        if supplied != required:
            errors.append(key.upper() + "_SET_MISMATCH")
    return {
        "status": "PASS" if not errors else "BLOCKED",
        "errors": sorted(set(errors)),
        "candidate_sha": state["head"],
        "dirty_digest": state["dirty_digest"],
        "tested_capability_ids": sorted(expected) if not errors else [],
        "certification": "NOT_CERTIFIED",
    }


def read_evidence(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Capability evidence must be a regular JSON file <= 1 MiB")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Capability evidence must contain a JSON object")
    return payload


def write_evidence(root: Path, path: Path, payload: dict[str, Any]) -> Path:
    root = root.resolve()
    target = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not target.is_relative_to(root):
        raise ValueError("Capability evidence output must stay inside the repository")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink() or target.is_symlink():
        raise ValueError("Capability evidence output cannot use symlinks")
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(target)
    return target
