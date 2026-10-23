"""Advisory-only Doctor evidence envelope for optional LOCAL model diagnostics.

No model calls, commands, mutations, certificate statuses or network access.
The deterministic Doctor remains the only issuer of test/QA verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

_SHA = re.compile(r"[0-9a-f]{40}\Z", re.ASCII)
_ITEM = re.compile(r"[A-Za-z0-9_./:-]{1,240}\Z", re.ASCII)
_FORBIDDEN = frozenset({"PASS", "FAIL", "CERTIFIED", "DONE", "APPROVED"})
_MAX_ITEMS = 64


class InvalidDiagnostic(ValueError):
    pass


def _items(values: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or len(values) > _MAX_ITEMS:
        raise InvalidDiagnostic(f"invalid {label} list")
    result = []
    for item in values:
        if (not isinstance(item, str) or not _ITEM.fullmatch(item) or
            ".." in item or item.startswith("/") or "\\" in item):
            raise InvalidDiagnostic(f"invalid {label} item")
        result.append(item)
    return tuple(sorted(set(result)))


@dataclass(frozen=True, slots=True)
class DiagnosticEnvelope:
    """The only status it can report is ADVISORY_ONLY."""
    source_sha: str
    affected_paths: tuple[str, ...]
    failing_test_ids: tuple[str, ...]
    issue_ids: tuple[str, ...]
    status: str = "ADVISORY_ONLY"

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": "atlas-doctor-local-diagnostic/v1",
            "source_sha": self.source_sha,
            "affected_paths": list(self.affected_paths),
            "failing_test_ids": list(self.failing_test_ids),
            "issue_ids": list(self.issue_ids),
            "status": "ADVISORY_ONLY",
        }


def prepare_local_evidence(*, source_sha: str, affected_paths: object,
                           failing_test_ids: object, issue_ids: object) -> DiagnosticEnvelope:
    if not isinstance(source_sha, str) or not _SHA.fullmatch(source_sha):
        raise InvalidDiagnostic("source SHA must be an exact commit")
    return DiagnosticEnvelope(
        source_sha=source_sha,
        affected_paths=_items(affected_paths, label="paths"),
        failing_test_ids=_items(failing_test_ids, label="tests"),
        issue_ids=_items(issue_ids, label="issues"),
    )


@dataclass(frozen=True, slots=True)
class DiagnosticSuggestion:
    hypothesis: str
    recommended_test_ids: tuple[str, ...]
    status: str = "ADVISORY_ONLY"


def parse_local_suggestion(response: object) -> DiagnosticSuggestion:
    """Reject models attempting to forge an independent Doctor verdict.

    Suggested test IDs are plain data; callers must authorize actual execution.
    """
    if not isinstance(response, dict) or set(response) != {"hypothesis", "recommended_test_ids"}:
        raise InvalidDiagnostic("unexpected diagnostic response schema")
    hypothesis = response["hypothesis"]
    if not isinstance(hypothesis, str) or not 1 <= len(hypothesis) <= 1600:
        raise InvalidDiagnostic("invalid hypothesis")
    if any(word in hypothesis.upper().split() for word in _FORBIDDEN):
        # Do not confuse an opinion with a certificate.
        raise InvalidDiagnostic("suggestion claims a Doctor verdict")
    test_ids = _items(response["recommended_test_ids"], label="recommended tests")
    return DiagnosticSuggestion(hypothesis, test_ids)
