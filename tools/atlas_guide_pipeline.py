"""Single offline entry for staged Guide candidates, never live Atlas activation.

The ordinary CLI only evaluates metadata gates and cannot be made to publish.
Only a trusted certification host may inject a witness verifier into the
library API, after tools/UI have independently passed qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.atlas_guide_candidate_store import publish_candidate
from tools.atlas_guide_conformity import before_after, compare
from tools.atlas_guide_importer import prepare_preview
from tools.atlas_guide_sequence_gate import (
    WitnessVerifier, assess_next,
)

# Static contract for Atlas Doctor's derived AI tool catalog; no import side effects.
TOOL_SPEC = {
    "schema_version": 1,
    "id": "atlas-guide-pipeline",
    "role": "guide_candidate_control_plane",
    "capabilities": ["guide","validation"],
    "modes": ["readonly_sequence_cli","trusted_host_stage_api"],
    "cost_hint": "variable",
    "side_effects": "repo_mutation_explicit",
    "structured_output": True,
    "canonical": True,
    "recommended_tests": ["tests.test_atlas_guide_pipeline"],
    "target_scopes": ["encyclopedia_guide"],
}


class GuidePipelineBlocked(ValueError):
    """Refuse to prepare an uncertified or unverified candidate."""


def stage_checked_candidate(
    *,
    plan: Mapping[str, Any],
    head_sha: str,
    verifier: WitnessVerifier | None,
    authorized_source: dict[str, Any],
    independent_reference: dict[str, Any],
    atlas_before: dict[str, Any],
    atlas_after: dict[str, Any],
    candidate_root: Path,
    expected_selected: str = "NONE",
) -> dict[str, Any]:
    """Stage ONE checked candidate only, with no live app/character mutation.

    Fail closed before any storage write. This function is not exposed by
    the CLI and cannot issue a gameplay certificate. A trusted host must
    validate its witness receipts separately, including real Windows evidence.
    """
    policy = assess_next(plan, head_sha=head_sha, verifier=verifier)
    if not policy["may_prepare_next"]:
        raise GuidePipelineBlocked("pilot/sequence gate: missing trusted evidence")
    next_id = plan["next_guide_id"]
    if any(not isinstance(doc, dict) for doc in (
        authorized_source, independent_reference, atlas_before, atlas_after
    )):
        raise GuidePipelineBlocked("all source/reference/Atlas exports must be objects")
    guides = authorized_source.get("guides")
    if not isinstance(guides, list) or len(guides) != 1:
        raise GuidePipelineBlocked("one and only one guide is permitted per transaction")
    if not isinstance(guides[0], dict):
        raise GuidePipelineBlocked("source guide must be an object")
    if guides[0].get("guide_id") != next_id:
        raise GuidePipelineBlocked("source guide ID differs from authorized next ID")
    for name, doc in (("reference", independent_reference),
                      ("before", atlas_before), ("after", atlas_after)):
        rows = doc.get("guides")
        if not isinstance(rows, list) or len(rows) != 1:
            raise GuidePipelineBlocked(f"{name}: exactly one guide required")
        if not isinstance(rows[0], dict):
            raise GuidePipelineBlocked(f"{name}: guide must be an object")
        if rows[0].get("guide_id") != next_id:
            raise GuidePipelineBlocked(f"{name}: guide ID mismatch")
    # Semantic equality cannot establish independent provenance: a caller
    # might submit the same export as both 'source' and 'reference'. Demand
    # two independent, exact-SHA attestations before the first side effect.
    def _source_digest(document: dict[str, Any]) -> str:
        try:
            raw = json.dumps(
                document, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise GuidePipelineBlocked(
                "source/reference contains non-JSON-compatible values"
            ) from exc
        return hashlib.sha256(raw).hexdigest()

    source_digest = _source_digest(authorized_source)
    reference_digest = _source_digest(independent_reference)
    for label, digest in (("current.source_rights", source_digest),
                          ("current.independent_reference", reference_digest)):
        try:
            trusted = (verifier is not None
                       and verifier(label, digest, head_sha, source_digest) is True)
        except Exception:
            trusted = False
        if not trusted:
            raise GuidePipelineBlocked(f"{label}: missing independent trusted attestation")
    source_parity = compare(independent_reference, authorized_source)
    if source_parity["issue_count"] or source_parity["status"] != "PARITY_CHECK_PASS":
        raise GuidePipelineBlocked("source differs from independently reviewed reference")
    atlas_parity = compare(independent_reference, atlas_after)
    if atlas_parity["issue_count"] or atlas_parity["status"] != "PARITY_CHECK_PASS":
        raise GuidePipelineBlocked("Atlas route differs from independently reviewed reference")
    delta = before_after(independent_reference, atlas_before, atlas_after)
    if delta["persistent"] or delta["introduced"]:
        raise GuidePipelineBlocked("before/after includes persistent or new discrepancies")
    if authorized_source.get("complete") is not True:
        raise GuidePipelineBlocked("single-guide input must declare complete=true")
    steps = guides[0].get("steps")
    if not isinstance(steps, list) or not steps:
        raise GuidePipelineBlocked("empty guide cannot be prepared")
    preview = prepare_preview(
        authorized_source, expected_guides=1, expected_steps=len(steps), partial=False
    )
    if preview["guide_count"] != 1 or preview["step_count"] != len(steps):
        raise GuidePipelineBlocked("projection lost or duplicated steps")
    receipt = publish_candidate(
        preview, root=candidate_root, expected_selected=expected_selected
    )
    # The result is explicitly a STAGED candidate. Independent manual guide
    # review is still needed before any certified/live publication.
    return {
        "status": "STAGED_NOT_ACTIVE_NOT_CERTIFIED",
        "certified": False,
        "runtime_activation": False,
        "guide_id": next_id,
        "head_sha": head_sha,
        "source_sha256": preview["source_sha256"],
        "reference_sha256": source_parity["reference_sha256"],
        "atlas_after_sha256": atlas_parity["atlas_sha256"],
        "resolved_issue_count": len(delta["resolved"]),
        "candidate_sha256": receipt["candidate_sha256"],
        "next_selected_sha256": receipt["candidate_sha256"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One Guide pipeline control-plane (read-only; no live actions)"
    )
    parser.add_argument("--plan", type=Path, required=True,
                        help="Metadata/receipts only; no guide or source text")
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args(argv)
    try:
        doc = json.loads(args.plan.read_text(encoding="utf-8"))
        # Deliberately no --apply, --publish, --trust, --skip-checks or
        # --synthetic-pass flags. The CLI has no independent trust root.
        result = assess_next(doc, head_sha=args.head_sha)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"GUIDE_PIPELINE_BLOCKED: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["may_prepare_next"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
