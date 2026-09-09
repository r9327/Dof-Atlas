from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from app.network.contracts import DEFAULT_PROTOCOL_MAPPING_DIR
from app.network.deobfs_bundle import DeobfuscationEvidenceBundleError
from app.network.deobfs_report import DeobfuscationReportError
from app.network.discovery_evidence import ProtocolDiscoveryEvidenceError
from app.network.mapping_manifest import ProtocolMappingError
from app.network.mapping_registry import ProtocolMappingRegistry
from app.network.readiness_audit import audit_protocol_mapping_readiness


@dataclass(frozen=True, slots=True)
class ProtocolMappingInstallResult:
    success: bool
    installed: bool
    reason: str
    build_sha256: str = ""
    destination: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "purpose": "explicit_verified_protocol_mapping_install",
            "capture_started": False,
            "success": self.success,
            "installed": self.installed,
            "reason": self.reason,
            "build_sha256": self.build_sha256,
            "destination": str(self.destination) if self.destination is not None else "",
        }


def install_verified_protocol_mapping(
    candidate_path: str | Path,
    consensus_paths: Sequence[str | Path],
    bundle_path: str | Path,
    report_paths: Sequence[str | Path],
    *,
    destination_root: str | Path = DEFAULT_PROTOCOL_MAPPING_DIR,
) -> ProtocolMappingInstallResult:
    """Explicitly install one candidate only after every evidence gate passes.

    This function never starts capture or progression. It is intentionally
    separate from application startup. The candidate bytes are hashed before
    audit and checked again before the atomic write so a modified candidate
    cannot be installed from a stale validation result.
    """

    candidate = Path(candidate_path)
    try:
        before_bytes = candidate.read_bytes()
    except OSError as exc:
        raise ProtocolMappingError(f"cannot read protocol mapping candidate: {candidate}") from exc
    before_sha256 = hashlib.sha256(before_bytes).hexdigest()

    manifest, _consensuses, readiness = audit_protocol_mapping_readiness(
        candidate,
        consensus_paths,
        bundle_path,
        report_paths,
    )
    if not readiness.valid:
        return ProtocolMappingInstallResult(
            False,
            False,
            "candidate_evidence_invalid",
            build_sha256=manifest.build_sha256,
        )

    try:
        after_bytes = candidate.read_bytes()
    except OSError as exc:
        raise ProtocolMappingError(f"cannot re-read protocol mapping candidate: {candidate}") from exc
    if hashlib.sha256(after_bytes).hexdigest() != before_sha256 or after_bytes != before_bytes:
        return ProtocolMappingInstallResult(
            False,
            False,
            "candidate_changed_during_audit",
            build_sha256=manifest.build_sha256,
        )

    root = Path(destination_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ProtocolMappingError(f"cannot create protocol mapping directory: {root}") from exc

    registry = ProtocolMappingRegistry((root,))
    existing = registry.select(manifest.build_sha256)
    if existing.usable and existing.manifest is not None and len(existing.matched_paths) == 1:
        existing_path = existing.matched_paths[0]
        try:
            existing_bytes = existing_path.read_bytes()
        except OSError as exc:
            raise ProtocolMappingError(f"cannot read existing protocol mapping: {existing_path}") from exc
        if existing_bytes == before_bytes:
            return ProtocolMappingInstallResult(
                True,
                False,
                "mapping_already_installed",
                build_sha256=manifest.build_sha256,
                destination=existing_path,
            )
        return ProtocolMappingInstallResult(
            False,
            False,
            "different_mapping_already_installed",
            build_sha256=manifest.build_sha256,
            destination=existing_path,
        )
    if existing.reason == "ambiguous_exact_match":
        return ProtocolMappingInstallResult(
            False,
            False,
            "existing_mapping_ambiguous",
            build_sha256=manifest.build_sha256,
        )

    destination = root / f"mapping_{manifest.build_sha256[:16]}.json"
    if destination.exists():
        return ProtocolMappingInstallResult(
            False,
            False,
            "destination_exists_unselected",
            build_sha256=manifest.build_sha256,
            destination=destination,
        )

    temporary = destination.with_name(destination.name + ".tmp")
    installed = False
    try:
        temporary.write_bytes(before_bytes)
        temporary.replace(destination)
        installed = True

        selected = registry.select(manifest.build_sha256)
        if (
            not selected.usable
            or selected.manifest is None
            or len(selected.matched_paths) != 1
            or selected.matched_paths[0] != destination
        ):
            _rollback_destination(destination, reason="post-install selection failed")
            installed = False
            return ProtocolMappingInstallResult(
                False,
                False,
                "post_install_selection_failed",
                build_sha256=manifest.build_sha256,
                destination=destination,
            )
    except OSError as exc:
        if installed:
            try:
                _rollback_destination(destination, reason="install I/O failure")
            except ProtocolMappingError as rollback_exc:
                raise ProtocolMappingError(
                    f"protocol mapping install failed and rollback failed: {destination}"
                ) from rollback_exc
        raise ProtocolMappingError(f"cannot install protocol mapping: {destination}") from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

    return ProtocolMappingInstallResult(
        True,
        True,
        "mapping_installed_not_started",
        build_sha256=manifest.build_sha256,
        destination=destination,
    )


def _rollback_destination(destination: Path, *, reason: str) -> None:
    try:
        destination.unlink(missing_ok=True)
    except OSError as exc:
        raise ProtocolMappingError(
            f"cannot rollback protocol mapping after {reason}: {destination}"
        ) from exc
    if destination.exists():
        raise ProtocolMappingError(
            f"protocol mapping still exists after rollback ({reason}): {destination}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Explicitly install an exact-build protocol mapping only after network "
            "consensus, build-bound deobfs reports and semantic readiness all pass. "
            "This command never starts capture."
        )
    )
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--bundle", required=True)
    parser.add_argument(
        "--report",
        action="append",
        required=True,
        help="dofus-deobfs report path; complete set must match the bundle.",
    )
    parser.add_argument(
        "--destination-root",
        default=str(DEFAULT_PROTOCOL_MAPPING_DIR),
        help="Mapping directory. Defaults to Dofus Atlas runtime mapping directory.",
    )
    parser.add_argument("consensus", nargs="+")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = install_verified_protocol_mapping(
            args.candidate,
            args.consensus,
            args.bundle,
            args.report,
            destination_root=args.destination_root,
        )
    except (
        ProtocolMappingError,
        ProtocolDiscoveryEvidenceError,
        DeobfuscationReportError,
        DeobfuscationEvidenceBundleError,
        ValueError,
    ) as exc:
        print(f"network mapping install failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.success else 3


__all__ = ["ProtocolMappingInstallResult", "install_verified_protocol_mapping"]


if __name__ == "__main__":
    raise SystemExit(main())
