"""Single offline entry for staged Guide candidates, never live Atlas activation.

The ordinary CLI only evaluates metadata gates and cannot be made to publish.
Only a trusted certification host may inject a witness verifier into the
library API, after tools/UI have independently passed qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.atlas_guide_candidate_store import (
    publish_candidate, read_selected_route, read_selected_step,
    list_selected_preview_routes,
)
from tools.atlas_guide_conformity import before_after, compare
from tools.atlas_guide_importer import prepare_preview
from tools.atlas_guide_sequence_gate import (
    WitnessVerifier, _load_strict_plan, _plan_snapshot, assess_next,
)

# Static contract for Atlas Doctor's derived AI tool catalog; no import side effects.
TOOL_SPEC = {
    "schema_version": 1,
    "id": "atlas-guide-pipeline",
    "role": "guide_candidate_control_plane",
    "capabilities": ["guide","validation"],
    "modes": [
        "readonly_sequence_cli", "trusted_host_stage_api",
        "staged_readonly_preview_api", "staged_readonly_card_api",
        "staged_readonly_preview_cli",
    ],
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
    if "sequence.plan_mutated_during_attestation" in policy["missing_proofs"]:
        raise GuidePipelineBlocked("sequencing plan changed during verification")
    if not policy["may_prepare_next"]:
        raise GuidePipelineBlocked("pilot/sequence gate: missing trusted evidence")
    next_id = policy["next_guide_id"]
    if plan.get("next_guide_id") != next_id:
        raise GuidePipelineBlocked("sequencing plan changed during verification")
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
                "guide export contains non-JSON-compatible values"
            ) from exc
        return hashlib.sha256(raw).hexdigest()

    plan_snapshot = _plan_snapshot(plan)
    source_digest = _source_digest(authorized_source)
    reference_digest = _source_digest(independent_reference)
    before_digest = _source_digest(atlas_before)
    after_digest = _source_digest(atlas_after)

    def _require_pinned_sources() -> None:
        # A verifier may call external code. Never allow it to replace either
        # attested source or the Atlas before/after observations between
        # comparison and immutable staging.
        if (_plan_snapshot(plan) != plan_snapshot
                or _source_digest(authorized_source) != source_digest
                or _source_digest(independent_reference) != reference_digest
                or _source_digest(atlas_before) != before_digest
                or _source_digest(atlas_after) != after_digest):
            raise GuidePipelineBlocked(
                "source/reference/Atlas snapshots changed during verification"
            )

    for label, digest in (("current.source_rights", source_digest),
                          ("current.independent_reference", reference_digest)):
        try:
            trusted = (verifier is not None
                       and verifier(label, digest, head_sha, source_digest) is True)
        except Exception:
            trusted = False
        if not trusted:
            raise GuidePipelineBlocked(f"{label}: missing independent trusted attestation")
    _require_pinned_sources()
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
    _require_pinned_sources()
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


def preview_staged_guide(
    *, candidate_root: Path, expected_selected: str, route_id: str,
) -> dict[str, Any]:
    """Connect the canonical staging tool to the existing UI-card contract.

    Explicit, SHA-pinned preview ONLY: this function must never publish
    into the application catalog, unlock gameplay or modify any progress.
    Production activation requires a separate trusted certification gate.
    """
    route = read_selected_route(
        root=candidate_root,
        expected_selected=expected_selected,
        route_id=route_id,
    )
    return {
        "status": "STAGED_PREVIEW_ONLY",
        "candidate_sha256": expected_selected,
        "route": route,
        "certified": False,
        "runtime_activation": False,
    }


def preview_staged_step(
    *, candidate_root: Path, expected_selected: str,
    route_id: str, stage_id: str,
) -> dict[str, Any]:
    """On-demand canonical card for the shared reader, by stable source ID.

    The return value is detached and strictly non-active; no guide is added to
    the live catalogue and no character progression can be written here.
    """
    card = read_selected_step(
        root=candidate_root, expected_selected=expected_selected,
        route_id=route_id, stage_id=stage_id,
    )
    return {
        "status": "STAGED_PREVIEW_ONLY",
        "candidate_sha256": expected_selected,
        "route_id": route_id,
        "stage_id": stage_id,
        "card": card,
        "certified": False,
        "runtime_activation": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One Guide pipeline control-plane (read-only; no live actions)"
    )
    parser.add_argument("--plan", type=Path,
                        help="Metadata/receipts only; no guide or source text")
    parser.add_argument("--head-sha")
    parser.add_argument("--preview-root", type=Path,
                        help="Explicit managed candidate store, read-only")
    parser.add_argument("--expected-selected",
                        help="Exact pinned candidate SHA-256; no default")
    parser.add_argument("--list", action="store_true",
                        help="Metadata only; no full guide/step text")
    parser.add_argument("--route-id", help="Exact source_guide:<id> identity")
    parser.add_argument("--stage-id", help="Exact source:<guide>:<step> identity")
    args = parser.parse_args(argv)

    # Preserve the original sequence CLI as the default and keep previews
    # opt-in. This existing canonical control-plane is already classified as
    # read-only by Doctor. The mutating candidate store stays library-only.
    if args.preview_root is not None:
        if args.plan is not None or args.head_sha is not None:
            parser.error("preview and sequencing modes cannot be combined")
        if args.expected_selected is None:
            parser.error("preview requires --expected-selected")
        if args.list == bool(args.route_id):
            parser.error("preview requires exactly one of --list or --route-id")
        if args.stage_id is not None and args.route_id is None:
            parser.error("--stage-id requires --route-id")
        try:
            if args.list:
                result = list_selected_preview_routes(
                    root=args.preview_root,
                    expected_selected=args.expected_selected,
                )
            elif args.stage_id is not None:
                result = preview_staged_step(
                    candidate_root=args.preview_root,
                    expected_selected=args.expected_selected,
                    route_id=args.route_id, stage_id=args.stage_id,
                )
            else:
                result = preview_staged_guide(
                    candidate_root=args.preview_root,
                    expected_selected=args.expected_selected,
                    route_id=args.route_id,
                )
        except (OSError, ValueError, TypeError) as exc:
            print(json.dumps({
                "status": "PREVIEW_BLOCKED", "reason": str(exc),
                "certified": False, "runtime_activation": False,
            }, ensure_ascii=False, sort_keys=True), file=sys.stderr)
            return 2
        print(json.dumps(result, ensure_ascii=False, sort_keys=True,
                         allow_nan=False))
        return 0
    if (args.plan is None or args.head_sha is None
            or args.expected_selected is not None or args.list
            or args.route_id is not None or args.stage_id is not None):
        parser.error("sequence requires --plan and --head-sha; no preview flags")
    try:
        doc = _load_strict_plan(args.plan)
        # Deliberately no --apply, --publish, --trust, --skip-checks or
        # --synthetic-pass flags. The CLI has no independent trust root.
        result = assess_next(doc, head_sha=args.head_sha)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"GUIDE_PIPELINE_BLOCKED: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["may_prepare_next"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
