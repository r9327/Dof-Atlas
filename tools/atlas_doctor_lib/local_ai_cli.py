"""Read-only command-line entrypoint for optional Atlas Doctor local diagnostics.

The model can suggest hypotheses and existing test IDs, never execute tests,
modify files or change Doctor's independent PASS/FAIL/REVIEW verdict.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .local_ai_client import LocalDoctorModelError, diagnose_local
from .local_ai_evidence import InvalidDiagnostic, prepare_local_evidence


def _load_evidence(path: Path):
    if path.stat().st_size > 65536:
        raise InvalidDiagnostic("evidence file exceeds 64 KiB")
    raw = path.read_bytes()
    doc = json.loads(raw)
    if (not isinstance(doc, dict) or set(doc) != {
        "schema", "source_sha", "affected_paths", "failing_test_ids", "issue_ids", "status"
    } or doc["schema"] != "atlas-doctor-local-diagnostic/v1"
            or doc["status"] != "ADVISORY_ONLY"):
        raise InvalidDiagnostic("invalid evidence contract")
    return prepare_local_evidence(
        source_sha=doc["source_sha"],
        affected_paths=doc["affected_paths"],
        failing_test_ids=doc["failing_test_ids"],
        issue_ids=doc["issue_ids"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optional local Doctor AI (no certification)")
    parser.add_argument("evidence", type=Path, help="Doctor advisory evidence JSON")
    parser.add_argument("--model", required=True, help="Name of locally available Ollama model")
    parser.add_argument("--local-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--validate-only", action="store_true", help="Never invoke a model")
    args = parser.parse_args(argv)
    try:
        envelope = _load_evidence(args.evidence)
        if args.validate_only:
            print(json.dumps({"status": "ADVISORY_ONLY", "evidence_sha": envelope.source_sha,
                              "mode": "validated_without_model"}, sort_keys=True))
            return 0
        suggestion = diagnose_local(envelope, model=args.model,
                                    base_url=args.local_url, timeout=args.timeout)
        print(json.dumps({
            "status": "ADVISORY_ONLY",
            "source_sha": envelope.source_sha,
            "hypothesis": suggestion.hypothesis,
            "recommended_test_ids": list(suggestion.recommended_test_ids),
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, UnicodeError, ValueError, InvalidDiagnostic, LocalDoctorModelError) as exc:
        # Never print a model's raw untrusted response as a Doctor result.
        print(json.dumps({"status": "UNAVAILABLE", "reason": str(exc)}, ensure_ascii=False),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
