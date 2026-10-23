"""Build local-only AI diagnostic input from an actual Doctor Qt UI session.

Consumes Doctor's existing SHA-bound, hash-verified UI evidence. Never treats
an LLM response as certification and never forwards screenshots, logs or
untrusted free-form page text to the model.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .local_ai_evidence import (
    DiagnosticEnvelope, InvalidDiagnostic, prepare_local_evidence,
)

_MAX_ASSERTIONS = 4000
_MAX_ID = 240


def from_verified_ui_session(
    folder: Path, *, candidate_sha: str, affected_paths: tuple[str, ...] = (),
) -> DiagnosticEnvelope:
    """Convert known-failing UI assertion IDs into bounded advisory evidence.

    A full PASS is deliberately not turned into an AI request; do not waste
    inference or let an AI reinterpret passing deterministic tests.
    """
    if not isinstance(folder, Path) or folder.is_symlink():
        raise InvalidDiagnostic("unsafe UI evidence folder")
    # Validate exact SHA before touching session files.
    prepare_local_evidence(source_sha=candidate_sha, affected_paths=[],
                           failing_test_ids=[], issue_ids=[])
    try:
        from .doctor_ui_ci import read_evidence
        report = read_evidence(folder, candidate_sha)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        raise InvalidDiagnostic("UI session lacks verified exact-SHA artifacts") from exc
    if (report.get("candidate_sha") != candidate_sha or
        report.get("dirty") is not False or
        report.get("tests_executed") is not True or
        report.get("status") not in {"FAIL", "BLOCKED", "REVIEW"}):
        raise InvalidDiagnostic("UI session is unexecuted, green or untrusted")
    rows = report.get("assertions")
    required = report.get("required_assertions")
    if (not isinstance(rows, list) or not isinstance(required, list)
            or len(rows) > _MAX_ASSERTIONS or len(required) > _MAX_ASSERTIONS
            or not required):
        raise InvalidDiagnostic("invalid required UI assertion inventory")
    by_id: dict[str, str] = {}
    for row in rows:
        if (not isinstance(row, dict) or
            not isinstance(row.get("assertion_id"), str) or
            not isinstance(row.get("assertion_status"), str)):
            raise InvalidDiagnostic("malformed UI assertion")
        ident, status = row["assertion_id"], row["assertion_status"]
        if (not 1 <= len(ident) <= _MAX_ID or ident in by_id or
                status not in {"PASS", "FAIL", "BLOCKED", "REVIEW", "NOT_COVERED"}):
            raise InvalidDiagnostic("duplicate, unbounded or unknown UI assertion")
        by_id[ident] = status
    if any(not isinstance(ident, str) or not 1 <= len(ident) <= _MAX_ID
           for ident in required) or len(set(required)) != len(required):
        raise InvalidDiagnostic("invalid required UI assertion ID")
    failures = sorted({ident for ident in required if by_id.get(ident) != "PASS"})
    # An adverse report with all required assertions green cannot be explained
    # by real failing assertion IDs; no speculative diagnosis is justified.
    if not failures:
        raise InvalidDiagnostic("no failed or missing UI assertion to investigate")
    capped = failures[:63] if len(failures) > 64 else failures[:64]
    issues = ["UI_" + report["status"]]
    if len(failures) > 64:
        issues.append("UI_ASSERTIONS_TRUNCATED")
    return prepare_local_evidence(
        source_sha=candidate_sha,
        affected_paths=affected_paths,
        failing_test_ids=capped,
        issue_ids=issues,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract bounded local-AI input from verified Doctor UI session")
    parser.add_argument("session", type=Path)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--out", type=Path, required=True, help="new JSON only; never overwrite")
    parser.add_argument("--affected-path", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        envelope = from_verified_ui_session(
            args.session, candidate_sha=args.candidate_sha,
            affected_paths=tuple(args.affected_path),
        )
        if args.out.is_symlink():
            raise InvalidDiagnostic("unsafe output file")
        payload = json.dumps(envelope.to_payload(), sort_keys=True,
                             ensure_ascii=False).encode("utf-8") + b"\n"
        if len(payload) > 65536:
            raise InvalidDiagnostic("diagnostic envelope exceeds 64 KiB")
        with args.out.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except (InvalidDiagnostic, OSError, ValueError) as exc:
        print(json.dumps({"status": "UNAVAILABLE", "reason": str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"status": "ADVISORY_ONLY",
                      "source_sha": envelope.source_sha,
                      "failing_test_ids": len(envelope.failing_test_ids)},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
