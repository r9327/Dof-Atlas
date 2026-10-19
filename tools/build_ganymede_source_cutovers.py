"""Build explicit Ganymède source-trusted manual routes without fake Doduda certification.

The source defines the order. Technical checks protect IDs, step completeness,
provenance and human-visible action hints. No quest objective is auto-completed.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    certified_payload_sha256, route_fingerprint,
)
from tools.audit_ganymede_master_refs import ROOT
from tools.build_ganymede_replacement_previews import build_dofus_replacement_previews
from tools.build_ganymede_trusted_cutovers import assert_reviewed_source_parity

DIRECTORY = Path("data/encyclopedia/guides/replacement_drafts")
# Static presentation/catalogue context is not a step, objective or progress.
# It must survive a source-route cutover without copying old journey steps.
_LEGACY_METADATA = (
    "recommended_level_min", "recommended_level_max",
    "reward_item_id", "illustration_item_id", "image",
    "linked_achievement_ids",
)


def retain_legacy_display_metadata(route: dict, legacy: dict) -> dict:
    """Keep verified local guide identity/icon/reward; never reuse old steps."""
    if route.get("id") != legacy.get("id") or route.get("category") != legacy.get("category"):
        raise ValueError("Cannot reuse metadata from a different local guide")
    for field in _LEGACY_METADATA:
        if field in legacy:
            route[field] = deepcopy(legacy[field])
    route["display_metadata_source"] = "ATLAS_LEGACY_CATALOGUE"
    return route

_SOURCE_STATUSES = {"REVIEW_SOURCE_ACTION", "AUTO_EXTRACTED_NEEDS_REVIEW"}


def prepare_source_cutover(draft: dict) -> dict:
    payload = deepcopy(draft)
    if (payload.get("category") != "dofus"
            or payload.get("route_origin") != "GANYMEDE_CONTINUOUS_STEP_ORDER"
            or payload.get("source_text_copied") is not False
            or payload.get("guide_progress_id_unchanged") is not True):
        raise ValueError("Untrusted source route or progress identity")
    sections = payload.get("sections")
    if not isinstance(sections, list) or len(sections) != 1:
        raise ValueError("Exactly one continuous section required")
    steps = sections[0].get("steps")
    source_id = payload.get("source_guide_id")
    count = payload.get("expected_source_step_count")
    if (type(source_id) is not int or source_id < 1 or not isinstance(steps, list)
            or not steps or type(count) is not int or count != len(steps)):
        raise ValueError("Invalid source IDs or step coverage")
    for number, step in enumerate(steps, 1):
        if (not isinstance(step, dict)
                or step.get("id") != f"ganymede_{source_id}_step_{number:04d}"
                or step.get("source_guide_id") != source_id
                or step.get("source_step_number") != number
                or step.get("original_prose_imported") is not False
                or step.get("source_action_review_status") not in _SOURCE_STATUSES
                or step.get("verified_actions") != []):
            raise ValueError(f"Invalid source step {number}")
        actions = step.get("source_action_candidates")
        if not isinstance(actions, list) or not actions:
            raise ValueError(f"Missing source action candidates at {number}")
        labels = []
        for action in actions:
            if not isinstance(action, dict) or not isinstance(action.get("kind"), str):
                raise ValueError(f"Malformed action at {number}")
            label = action.get("label")
            if not isinstance(label, str) or not label.strip() or len(label) > 120:
                raise ValueError(f"Empty or oversized action at {number}")
            labels.append(" ".join(label.split()))
        step["title"] = f"Étape {number} — {labels[0]}"
        step["content"] = "\n".join(labels)
        step["manual_completion_allowed"] = True
        step["auto_completion_allowed"] = False
        # Old Atlas quest-occurrence joins are available in the untouched draft.
        # They are not consumed by the active renderer; dropping duplicate
        # occurrences prevents the new routes from retaining needless RAM.
        step.pop("atlas_quest_candidates", None)
    payload["description"] = "Étapes Ganymède en suivi continu (validation manuelle ; objectifs non certifiés)."
    payload["completeness_status"] = "complete"
    payload["replacement_status"] = "TRUSTED_SOURCE_STEPS"
    payload["replacement_active"] = True
    payload["progress_migration_not_required"] = True
    payload["legacy_manual_steps_migration_verified"] = False
    payload["canonical_objectives_certified"] = False
    payload["auto_completion_allowed"] = False
    payload["playable_step_count"] = len(steps)
    payload["cutover_blockers"] = []
    return payload


def build_source_cutovers(root: Path) -> dict:
    report = build_dofus_replacement_previews(root)
    if report.get("status") != "PREVIEWS_READY_NOT_PLAYABLE":
        raise ValueError(f"Invalid source snapshots: {report.get('issues')}")
    payloads = {}
    declarations = {}
    for guide_id, freshly_built in sorted(report["previews"].items()):
        path = root / DIRECTORY / f"{guide_id}.json"
        stored = json.loads(path.read_text(encoding="utf-8"))
        assert_reviewed_source_parity(stored, freshly_built)
        payload = prepare_source_cutover(stored)
        # Reuse catalogue display identity, not old quest routes or progress.
        legacy = json.loads((root / DIRECTORY.parent / f"{guide_id}.json").read_text(encoding="utf-8"))
        retain_legacy_display_metadata(payload, legacy)
        steps = payload["sections"][0]["steps"]
        source_id = payload["source_guide_id"]
        payloads[guide_id] = payload
        declarations[guide_id] = {
            "enabled": True,
            "status": "TRUSTED_SOURCE_STEPS",
            "source_guide_id": source_id,
            "source_step_count": len(steps),
            "fingerprint": route_fingerprint(source_id, [step["id"] for step in steps]),
            "payload_sha256": certified_payload_sha256(payload),
        }
    if len(payloads) != 20 or sum(x["playable_step_count"] for x in payloads.values()) != 1694:
        raise ValueError("Dofus source coverage changed; re-audit before cutover")
    return {"payloads": payloads, "manifest": {"schema_version": 1,
            "guides": declarations}, "unmapped": report["dofus_guides_without_direct_ganymede"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.name != "cutovers" or args.output_dir.parent.name != "replacement_drafts":
        parser.error("Output must be replacement_drafts/cutovers")
    result = build_source_cutovers(args.root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for guide_id, payload in result["payloads"].items():
        (args.output_dir / f"{guide_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "cutover_manifest.json").write_text(
        json.dumps(result["manifest"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({"guides": len(result["payloads"]),
                      "steps": sum(x["playable_step_count"] for x in result["payloads"].values()),
                      "unmapped": result["unmapped"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
