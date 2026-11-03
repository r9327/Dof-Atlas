"""Fail-closed Guide sequencing policy. No guide data and no runtime writes.

Phase 0: only synthetic fixtures. Pilot: Cawotte after tool/UI qualification.
Following guides: only after trusted, independently attested proof for EVERY
preceding guide. This module cannot issue or independently verify certificates;
a trusted verifier must be supplied by the certification host.
"""
from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

# Static contract for Atlas Doctor's derived AI tool catalog; no import side effects.
TOOL_SPEC = {
    "schema_version": 1,
    "id": "atlas-guide-sequence",
    "role": "guide_sequential_interlock",
    "capabilities": ["guide","validation"],
    "modes": ["read_only_advisory_cli","trusted_witness_api"],
    "cost_hint": "cheap",
    "side_effects": "read_only",
    "structured_output": True,
    "canonical": False,
    "recommended_tests": ["tests.test_atlas_guide_sequence_gate"],
    "target_scopes": ["encyclopedia_guide"],
}

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
_ZERO_SOURCE = "0" * 64
_ZERO_HEAD = "0" * 40
_GUIDE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,119}\Z")
_PILOT = "dofus_cawotte"
_FALLBACK = "dokoko"
_PHASE0 = (
    "doctor", "graphify", "unit_tests", "ui_interactions", "windows_dofus",
    "memory_benchmark", "importer", "comparator", "candidate_store",
    "rollback", "character_progression", "optimized_guides_regression",
)
_PER_GUIDE = (
    "authorized_independent_source", "complete_step_action_inventory",
    "source_to_atlas_comparison", "before_after_delta", "no_blocking_differences",
    "ui_common_components", "ui_clicks_and_travel", "guide_specific_validation",
    "character_progression", "doctor_and_unit_tests", "graphify",
    "windows_dofus_manual_review", "independent_human_comparison",
    "independent_final_certificate",
)
# The callback is supplied exclusively by a trusted test/CI/certification host.
# User-edited JSON claims alone can NEVER satisfy a required witness.
WitnessVerifier = Callable[[str, str, str, str], bool]


def _sha(value: Any) -> bool:
    return isinstance(value, str) and value != _ZERO_SOURCE and bool(_SHA256.fullmatch(value))


def _git_sha(value: Any) -> bool:
    return isinstance(value, str) and value != _ZERO_HEAD and bool(_GIT_SHA.fullmatch(value))


def _verify(
    name: str,
    receipt: Any,
    head_sha: str,
    source_sha: str,
    verifier: WitnessVerifier | None,
) -> bool:
    if not isinstance(receipt, dict) or receipt.get("status") != "PASS":
        return False
    if receipt.get("head_sha") != head_sha or receipt.get("source_sha") != source_sha:
        return False
    digest = receipt.get("artifact_sha256")
    if not _sha(digest) or verifier is None:
        return False
    try:
        return verifier(name, digest, head_sha, source_sha) is True
    except Exception:
        return False


def _gate(
    required: tuple[str, ...],
    receipts: Any,
    head_sha: str,
    source_sha: str,
    verifier: WitnessVerifier | None,
    prefix: str,
) -> list[str]:
    mapping = receipts if isinstance(receipts, dict) else {}
    return [
        f"{prefix}.{name}"
        for name in required
        if not _verify(f"{prefix}.{name}", mapping.get(name), head_sha, source_sha, verifier)
    ]


def assess_next(
    plan: Mapping[str, Any],
    *,
    head_sha: str,
    verifier: WitnessVerifier | None = None,
) -> dict[str, Any]:
    """Return an advisory interlock decision, not a gameplay certificate.

    No side effects. It NEVER infers 95 certified guides from one pilot.
    A human/host must independently validate source, Windows and each receipt.
    """
    if not _git_sha(head_sha):
        raise ValueError("head_sha must be the exact 40-character Git commit SHA")
    if (not isinstance(plan, Mapping) or type(plan.get("schema_version")) is not int
            or plan["schema_version"] != 1):
        raise ValueError("unsupported sequencing plan")
    failures: list[str] = []
    next_id = plan.get("next_guide_id")
    completed = plan.get("completed", [])
    if (not isinstance(next_id, str) or not _GUIDE_ID.fullmatch(next_id)
            or not isinstance(completed, list)):
        raise ValueError("invalid guide sequencing request")
    if not isinstance(plan.get("phase0"), dict):
        failures.append("phase0.missing")
    failures.extend(_gate(
        _PHASE0, plan.get("phase0"), head_sha, _ZERO_SOURCE, verifier, "phase0"
    ))
    seen: set[str] = set()
    prior = ""
    if len(completed) > 95:
        failures.append("sequence.exceeds_inventory")
    for index, record in enumerate(completed):
        label = f"completed[{index}]"
        if not isinstance(record, dict):
            failures.append(f"{label}.invalid")
            continue
        guide_id = record.get("guide_id")
        source_sha = record.get("source_sha")
        if (not isinstance(guide_id, str) or not _GUIDE_ID.fullmatch(guide_id)
                or guide_id in seen):
            failures.append(f"{label}.duplicate_or_invalid_id")
        else:
            seen.add(guide_id)
        if index == 0 and guide_id not in {_PILOT, _FALLBACK}:
            failures.append(f"{label}.pilot_must_be_first")
        if index == 0 and record.get("predecessor_id", "") not in ("", None):
            failures.append(f"{label}.unexpected_predecessor")
        if index == 0 and guide_id == _FALLBACK and not _verify(
            "pilot.cawotte_unavailable", plan.get("fallback_evidence"),
            head_sha, _ZERO_SOURCE, verifier
        ):
            failures.append("pilot.cawotte_source_unavailability_not_proven")
        if index > 0 and record.get("predecessor_id") != prior:
            failures.append(f"{label}.broken_chain")
        prior = guide_id if isinstance(guide_id, str) else ""
        if not _sha(source_sha):
            failures.append(f"{label}.missing_source_sha")
            source_sha = ""
        if (
            type(record.get("total_steps")) is not int
            or record["total_steps"] <= 0
            or type(record.get("certified_steps")) is not int
            or record["certified_steps"] != record["total_steps"]
            or type(record.get("total_actions")) is not int
            or record["total_actions"] <= 0
            or type(record.get("certified_actions")) is not int
            or record["certified_actions"] != record["total_actions"]
            or type(record.get("blocking_issues")) is not int
            or record["blocking_issues"] != 0
            or type(record.get("unverified_issues")) is not int
            or record["unverified_issues"] != 0
        ):
            failures.append(f"{label}.incomplete_coverage")
        if record.get("certification_status") != "CERTIFIED":
            failures.append(f"{label}.not_certified")
        if record.get("head_sha") != head_sha:
            failures.append(f"{label}.stale_code_sha")
        failures.extend(_gate(
            _PER_GUIDE, record.get("receipts"), head_sha, source_sha, verifier, label
        ))
    if next_id in seen:
        failures.append("sequence.guide_already_completed")
    if next_id == _FALLBACK and not completed:
        fallback = plan.get("fallback_evidence")
        if not _verify("pilot.cawotte_unavailable", fallback, head_sha,
                       _ZERO_SOURCE, verifier):
            failures.append("pilot.cawotte_source_unavailability_not_proven")
    if not completed and next_id not in {_PILOT, _FALLBACK}:
        failures.append("pilot.cawotte_must_be_first")
    if completed and not failures:
        if len(completed) >= 95:
            failures.append("sequence.inventory_already_complete")
        if next_id in {_PILOT, _FALLBACK} and next_id not in seen:
            failures.append("sequence.cannot_restart_pilot")
    allowed = not failures
    return {
        "schema_version": 1,
        "status": "ELIGIBLE_FOR_INDEPENDENT_REVIEW" if allowed else "BLOCKED",
        "may_prepare_next": allowed,
        "certified": False,
        "real_guide_processed": False,
        "next_guide_id": next_id,
        "verified_completed_count": len(completed) if allowed else 0,
        "missing_proofs": sorted(set(failures)),
        "note": (
            "Advisory only: trusted external witnesses and independent manual "
            "certification remain mandatory. No guide execution/activation here."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Guide sequence interlock")
    parser.add_argument("--plan", type=Path, required=True,
                        help="Metadata/receipts only; no route/quest content")
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args(argv)
    try:
        data = json.loads(args.plan.read_text(encoding="utf-8"))
        # The standalone CLI does not possess a trusted verification authority.
        result = assess_next(data, head_sha=args.head_sha)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"GUIDE_SEQUENCE_BLOCKED: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["may_prepare_next"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
