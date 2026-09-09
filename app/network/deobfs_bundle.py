from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from app.core.settings import load_settings
from app.network.build_fingerprint import ActiveProtocolBuildFingerprintProvider
from app.network.deobfs_report import DeobfuscationReportError, parse_deobfuscation_report


_BUNDLE_PURPOSE = "protocol_deobfuscation_report_bundle"


class DeobfuscationEvidenceBundleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DeobfuscationReportDigest:
    name: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class DeobfuscationEvidenceBundle:
    build_sha256: str
    reports: tuple[DeobfuscationReportDigest, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "purpose": _BUNDLE_PURPOSE,
            "authoritative_mapping": False,
            "privacy": "deobfs_report_hashes_and_build_fingerprint_only",
            "build_sha256": self.build_sha256,
            "report_count": len(self.reports),
            "reports": [report.to_dict() for report in self.reports],
        }


def create_deobfuscation_evidence_bundle(
    build_sha256: str,
    report_paths: Iterable[str | Path],
) -> DeobfuscationEvidenceBundle:
    build = str(build_sha256 or "").strip().casefold()
    if not _is_sha256(build):
        raise DeobfuscationEvidenceBundleError("invalid build_sha256")

    paths = tuple(Path(path) for path in report_paths)
    if not paths:
        raise DeobfuscationEvidenceBundleError("at least one deobfuscation report is required")

    rows: list[DeobfuscationReportDigest] = []
    names: set[str] = set()
    digests: set[str] = set()
    for path in paths:
        name = path.name.strip()
        if not name or name in names:
            raise DeobfuscationEvidenceBundleError("deobfuscation report names must be unique")
        try:
            payload = path.read_bytes()
            text = payload.decode("utf-8", errors="strict")
        except (OSError, UnicodeError) as exc:
            raise DeobfuscationEvidenceBundleError(f"cannot read deobfuscation report: {path}") from exc
        try:
            parse_deobfuscation_report(text)
        except DeobfuscationReportError as exc:
            raise DeobfuscationEvidenceBundleError(
                f"invalid deobfuscation report: {path}"
            ) from exc

        digest = hashlib.sha256(payload).hexdigest()
        if digest in digests:
            raise DeobfuscationEvidenceBundleError(
                "duplicate deobfuscation report content is not independent evidence"
            )
        names.add(name)
        digests.add(digest)
        rows.append(
            DeobfuscationReportDigest(
                name=name,
                sha256=digest,
                size_bytes=len(payload),
            )
        )

    return DeobfuscationEvidenceBundle(
        build_sha256=build,
        reports=tuple(sorted(rows, key=lambda row: row.name.casefold())),
    )


def parse_deobfuscation_evidence_bundle(raw: Mapping[str, Any]) -> DeobfuscationEvidenceBundle:
    if not isinstance(raw, Mapping):
        raise DeobfuscationEvidenceBundleError("deobfuscation bundle must be an object")
    if raw.get("schema_version") != 1:
        raise DeobfuscationEvidenceBundleError("unsupported deobfuscation bundle schema_version")
    if str(raw.get("purpose") or "").strip() != _BUNDLE_PURPOSE:
        raise DeobfuscationEvidenceBundleError("unexpected deobfuscation bundle purpose")
    if raw.get("authoritative_mapping") is not False:
        raise DeobfuscationEvidenceBundleError("deobfuscation bundle must remain non-authoritative")
    if str(raw.get("privacy") or "").strip() != "deobfs_report_hashes_and_build_fingerprint_only":
        raise DeobfuscationEvidenceBundleError("unexpected deobfuscation bundle privacy contract")

    build_sha256 = str(raw.get("build_sha256") or "").strip().casefold()
    if not _is_sha256(build_sha256):
        raise DeobfuscationEvidenceBundleError("invalid deobfuscation bundle build_sha256")

    raw_reports = raw.get("reports")
    if not isinstance(raw_reports, list) or not raw_reports:
        raise DeobfuscationEvidenceBundleError("deobfuscation bundle reports must be a non-empty list")
    report_count = _strict_non_negative_int(raw.get("report_count"), "report_count")
    if report_count != len(raw_reports):
        raise DeobfuscationEvidenceBundleError("deobfuscation bundle report_count is inconsistent")

    rows: list[DeobfuscationReportDigest] = []
    names: set[str] = set()
    digests: set[str] = set()
    for raw_report in raw_reports:
        if not isinstance(raw_report, Mapping):
            raise DeobfuscationEvidenceBundleError("deobfuscation bundle report must be an object")
        name = str(raw_report.get("name") or "").strip()
        if not name or Path(name).name != name or name in names:
            raise DeobfuscationEvidenceBundleError("invalid or duplicate deobfuscation report name")
        sha256 = str(raw_report.get("sha256") or "").strip().casefold()
        if not _is_sha256(sha256) or sha256 in digests:
            raise DeobfuscationEvidenceBundleError("invalid or duplicate deobfuscation report sha256")
        size_bytes = _strict_non_negative_int(raw_report.get("size_bytes"), "size_bytes")
        names.add(name)
        digests.add(sha256)
        rows.append(
            DeobfuscationReportDigest(
                name=name,
                sha256=sha256,
                size_bytes=size_bytes,
            )
        )

    return DeobfuscationEvidenceBundle(
        build_sha256=build_sha256,
        reports=tuple(sorted(rows, key=lambda row: row.name.casefold())),
    )


def load_deobfuscation_evidence_bundle(path: str | Path) -> DeobfuscationEvidenceBundle:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeobfuscationEvidenceBundleError(f"cannot load deobfuscation bundle: {source}") from exc
    return parse_deobfuscation_evidence_bundle(raw)


def verify_deobfuscation_evidence_bundle(
    bundle: DeobfuscationEvidenceBundle,
    report_paths: Iterable[str | Path],
    *,
    expected_build_sha256: str,
) -> tuple[Path, ...]:
    expected_build = str(expected_build_sha256 or "").strip().casefold()
    if bundle.build_sha256 != expected_build:
        raise DeobfuscationEvidenceBundleError("deobfuscation bundle build does not match mapping build")

    paths = tuple(Path(path) for path in report_paths)
    actual_by_name: dict[str, Path] = {}
    for path in paths:
        name = path.name.strip()
        if not name or name in actual_by_name:
            raise DeobfuscationEvidenceBundleError("supplied deobfuscation report names must be unique")
        actual_by_name[name] = path

    expected_names = {report.name for report in bundle.reports}
    if set(actual_by_name) != expected_names:
        raise DeobfuscationEvidenceBundleError(
            "supplied deobfuscation reports do not match bundle report names"
        )

    ordered_paths: list[Path] = []
    for expected in bundle.reports:
        path = actual_by_name[expected.name]
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise DeobfuscationEvidenceBundleError(f"cannot read deobfuscation report: {path}") from exc
        if len(payload) != expected.size_bytes:
            raise DeobfuscationEvidenceBundleError(
                f"deobfuscation report size changed after bundling: {expected.name}"
            )
        digest = hashlib.sha256(payload).hexdigest()
        if digest != expected.sha256:
            raise DeobfuscationEvidenceBundleError(
                f"deobfuscation report hash changed after bundling: {expected.name}"
            )
        ordered_paths.append(path)
    return tuple(ordered_paths)


def _active_build_sha256() -> str:
    settings = load_settings()
    handles = tuple(
        dict.fromkeys(
            int(client.handle)
            for client in settings.clients
            if _positive_int(getattr(client, "handle", None)) is not None
        )
    )
    if not handles:
        raise DeobfuscationEvidenceBundleError(
            "no connected Dofus window handle is configured in Dofus Atlas"
        )
    build_sha256 = ActiveProtocolBuildFingerprintProvider(lambda: handles)()
    if not build_sha256:
        raise DeobfuscationEvidenceBundleError("could not fingerprint the active Dofus Unity build")
    return build_sha256


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _strict_non_negative_int(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DeobfuscationEvidenceBundleError(f"{label} must be a non-negative integer")
    return int(value)


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _is_sha256(value: str) -> bool:
    if len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bind local dofus-deobfs report hashes to the exact active Dofus Unity "
            "build fingerprint. The bundle contains no packet payload or character data."
        )
    )
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--report",
        action="append",
        required=True,
        help="dofus-deobfs report path; repeat for each report included in the bundle.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        bundle = create_deobfuscation_evidence_bundle(
            _active_build_sha256(),
            args.report,
        )
        _write_json_atomic(Path(args.output), bundle.to_dict())
    except (DeobfuscationEvidenceBundleError, OSError, ValueError) as exc:
        print(f"network deobfuscation bundle failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


__all__ = [
    "DeobfuscationEvidenceBundle",
    "DeobfuscationEvidenceBundleError",
    "DeobfuscationReportDigest",
    "create_deobfuscation_evidence_bundle",
    "load_deobfuscation_evidence_bundle",
    "parse_deobfuscation_evidence_bundle",
    "verify_deobfuscation_evidence_bundle",
]


if __name__ == "__main__":
    raise SystemExit(main())
