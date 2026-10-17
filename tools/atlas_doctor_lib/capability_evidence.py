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

from .capability_matrix import BEHAVIOR_ANCHORS, capability_test_ids
from .core import git_state, utc_now

SCHEMA_VERSION = 1
MAX_LOG_CHARS = 12_000


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


def run_capability_witnesses(root: Path, *, timeout: int = 300) -> dict[str, Any]:
    """Run all 18 exact witness methods once and bind the result to the tree."""
    root = root.resolve()
    before = git_state(root)
    test_ids = capability_test_ids(root)
    missing = sorted(set(BEHAVIOR_ANCHORS) - set(test_ids))
    started_at = utc_now()
    started = time.monotonic()
    command = [sys.executable, "-m", "unittest",
               *(test_ids[ident] for ident in sorted(test_ids))]
    return_code: int | None = None
    stdout = ""
    stderr = ""
    timed_out = False
    if not missing:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        try:
            completed = subprocess.run(
                command, cwd=root, env=env, text=True, capture_output=True,
                check=False, timeout=max(1, min(timeout, 900)),
            )
            return_code = completed.returncode
            stdout = _tail(completed.stdout)
            stderr = _tail(completed.stderr)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = _tail(exc.stdout)
            stderr = _tail(exc.stderr)
    after = git_state(root)
    unchanged = (before["head"] == after["head"]
                 and before["dirty_digest"] == after["dirty_digest"])
    aggregate_pass = (not missing and not timed_out and return_code == 0 and unchanged
                      and _witness_suite_passed(stderr, len(test_ids)))
    status = ("PASS" if aggregate_pass else "BLOCKED"
              if missing or timed_out or not unchanged else "FAIL")
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
        "missing_witnesses": missing,
        "witnesses": [
            {
                "capability_id": ident,
                "test_id": test_ids[ident],
                "result": "PASS" if aggregate_pass else "UNVERIFIED",
            }
            for ident in sorted(test_ids)
        ],
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "certification": "NOT_CERTIFIED",
        "limits": (
            "A local exact-worktree behavioral test result is not runtime "
            "observation, independent CI attestation, or release certification."
        ),
    }
    result["evidence_digest"] = _digest(result)
    return result


def validate_capability_evidence(root: Path, payload: Any) -> dict[str, Any]:
    """Validate provenance and completeness without executing supplied data."""
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
    expected = capability_test_ids(root.resolve())
    if not _witness_suite_passed(payload.get("stderr_tail"), len(expected)):
        errors.append("WITNESS_SUITE_INCOMPLETE_OR_NOT_ALL_PASSED")
    supplied: dict[str, str] = {}
    witnesses = payload.get("witnesses")
    if not isinstance(witnesses, list):
        errors.append("WITNESSES_NOT_LIST")
    else:
        for row in witnesses:
            if not isinstance(row, dict) or not isinstance(row.get("capability_id"), str):
                errors.append("WITNESS_INVALID")
                continue
            ident = row["capability_id"]
            if ident in supplied:
                errors.append("WITNESS_DUPLICATE")
            supplied[ident] = row.get("test_id", "")
            if row.get("result") != "PASS":
                errors.append("WITNESS_NOT_PASS")
    if supplied != expected:
        errors.append("WITNESS_SET_MISMATCH")
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
