from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


_ROW_RE = re.compile(
    r"^\s*(?P<obfuscated>\S+)\s+→\s+(?P<original>\S+)\s+"
    r"(?P<file>\S+)\s+\[conf:\s*(?P<confidence>[0-9]+(?:\.[0-9]+)?)%\]\s*$"
)
_TOTAL_RE = re.compile(r"^\s*Total matches:\s*(?P<count>[0-9]+)\s*$")


class DeobfuscationReportError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DeobfuscationMatch:
    obfuscated_message: str
    original_message: str
    original_file: str
    confidence: float


@dataclass(frozen=True, slots=True)
class DeobfuscationReport:
    matches: tuple[DeobfuscationMatch, ...]
    uncertain_aliases: tuple[str, ...]
    total_declared: int

    def definitive_for_alias(
        self,
        alias: str,
        *,
        minimum_confidence: float = 100.0,
    ) -> DeobfuscationMatch | None:
        target = str(alias or "").strip()
        if not target or target in self.uncertain_aliases:
            return None
        rows = [
            row
            for row in self.matches
            if row.obfuscated_message == target and row.confidence >= float(minimum_confidence)
        ]
        return rows[0] if len(rows) == 1 else None


def load_deobfuscation_report(path: str | Path) -> DeobfuscationReport:
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise DeobfuscationReportError(f"cannot load deobfuscation report: {source}") from exc
    return parse_deobfuscation_report(text)


def parse_deobfuscation_report(text: str) -> DeobfuscationReport:
    """Parse the text report emitted by RuinedYourLife/dofus-deobfs.

    Only definitive rows are returned as matches. Rows whose original/file are
    ``???`` are tracked as uncertain aliases and can never satisfy
    ``definitive_for_alias``. The declared total is required and must match the
    number of report rows so truncated/copied reports fail closed.
    """

    matches: list[DeobfuscationMatch] = []
    uncertain: list[str] = []
    seen_aliases: set[str] = set()
    total_declared: int | None = None
    report_row_count = 0

    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip("\r\n")
        total_match = _TOTAL_RE.match(line)
        if total_match:
            if total_declared is not None:
                raise DeobfuscationReportError("duplicate Total matches declaration")
            total_declared = int(total_match.group("count"))
            continue

        row_match = _ROW_RE.match(line)
        if row_match is None:
            continue
        alias = row_match.group("obfuscated").strip()
        original = row_match.group("original").strip()
        original_file = row_match.group("file").strip()
        confidence = float(row_match.group("confidence"))

        if alias == "Obf" and original == "Orig" and original_file == "File":
            continue
        if not alias or confidence < 0.0 or confidence > 100.0:
            raise DeobfuscationReportError("invalid deobfuscation report row")
        if alias in seen_aliases:
            raise DeobfuscationReportError(f"duplicate deobfuscation alias: {alias}")
        seen_aliases.add(alias)
        report_row_count += 1

        if original == "???" or original_file == "???":
            if original != "???" or original_file != "???":
                raise DeobfuscationReportError(
                    f"partially uncertain deobfuscation row for alias {alias}"
                )
            uncertain.append(alias)
            continue

        matches.append(
            DeobfuscationMatch(
                obfuscated_message=alias,
                original_message=original,
                original_file=original_file,
                confidence=confidence,
            )
        )

    if total_declared is None:
        raise DeobfuscationReportError("missing Total matches declaration")
    if total_declared != report_row_count:
        raise DeobfuscationReportError(
            f"deobfuscation report row count mismatch: declared={total_declared} parsed={report_row_count}"
        )

    return DeobfuscationReport(
        matches=tuple(matches),
        uncertain_aliases=tuple(uncertain),
        total_declared=total_declared,
    )


def ankama_type_alias(type_url: str) -> str:
    value = str(type_url or "").strip()
    prefix = "ankama.com/"
    if not value.startswith(prefix) or len(value) <= len(prefix):
        return ""
    alias = value[len(prefix):]
    return alias if "/" not in alias and alias.strip() else ""


__all__ = [
    "DeobfuscationMatch",
    "DeobfuscationReport",
    "DeobfuscationReportError",
    "ankama_type_alias",
    "load_deobfuscation_report",
    "parse_deobfuscation_report",
]
