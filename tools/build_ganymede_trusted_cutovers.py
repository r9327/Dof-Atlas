"""Build integrity-bound Ganymède cutovers from separately certified actions.

Does not alter the live catalogue. Incomplete guides remain unactivated.
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


# No automatically extracted hint or candidate label can certify a quest action.
# Canonical action evidence and a verified legacy-progress mapping are mandatory.
_ALLOWED_ACTION_KINDS = frozenset({
    "quest_objective", "interaction", "travel", "combat",
    "dungeon", "collect", "craft", "prepare", "information",
})


def prepare_trusted_cutover(preview: dict) -> dict:
    """Prepare an already-certified continuous route; never certify candidates."""
    payload = deepcopy(preview)
    if payload.get("guide_progress_id_unchanged") is not True:
        raise ValueError("Guide progress identity is not preserved")
    if payload.get("legacy_manual_steps_migration_verified") is not True:
        raise ValueError("Legacy progress mapping has not been certified")
    if payload.get("cutover_blockers") != []:
        raise ValueError("Unresolved cutover blockers")
    if payload.get("source_text_copied") is not False:
        raise ValueError("Unlicensed source text cannot be imported")

    sections = payload.get("sections")
    if not isinstance(sections, list) or len(sections) != 1 or not isinstance(sections[0], dict):
        raise ValueError("Expected one continuous source route")
    steps = sections[0].get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("Empty route")
    expected_count = payload.get("expected_source_step_count")
    if type(expected_count) is not int or expected_count != len(steps):
        raise ValueError("Source step count mismatch")
    source_id = payload.get("source_guide_id")
    if type(source_id) is not int or source_id <= 0:
        raise ValueError("Invalid source guide ID")
    for number, step in enumerate(steps, 1):
        expected_id = f"ganymede_{source_id}_step_{number:04d}"
        if (not isinstance(step, dict)
                or step.get("id") != expected_id
                or step.get("source_guide_id") != source_id
                or step.get("source_step_number") != number
                or step.get("original_prose_imported") is not False):
            raise ValueError(f"Unstable or unordered Ganymède step at {number}")
        if step.get("source_action_review_status") != "CERTIFIED_CANONICAL_ACTIONS":
            raise ValueError(f"Unreviewed source actions at {expected_id}")
        actions = step.get("verified_actions")
        if not isinstance(actions, list) or not actions:
            raise ValueError(f"Missing canonical verified actions at {expected_id}")
        for action in actions:
            if (not isinstance(action, dict)
                    or action.get("verified") is not True
                    or action.get("kind") not in _ALLOWED_ACTION_KINDS
                    or not isinstance(action.get("text"), str)
                    or not action["text"].strip()
                    or not isinstance(action.get("evidence"), list)
                    or not action["evidence"]):
                raise ValueError(f"Unverified action at {expected_id}")
        labels = [action["text"].strip() for action in actions]
        step["title"] = labels[0]
        step["content"] = "\n".join(labels)
        step["manual_completion_allowed"] = True
        step["auto_completion_allowed"] = False

    payload["replacement_status"] = "CERTIFIED_FOR_CUTOVER"
    payload["replacement_active"] = True
    payload["completeness_status"] = "complete"
    payload["playable_step_count"] = len(steps)
    return payload



_GUIDES = Path("data/encyclopedia/guides")
_SOURCE_FIELDS = (
    "id", "source_guide_id", "source_step_number", "source_page",
    "source_coordinates_mentioned", "source_linked_guide_ids",
    "external_dofusdb_ids",
)
_ROUTE_FIELDS = (
    "id", "category", "source_guide_id", "expected_source_step_count",
    "source_link_snapshot", "route_origin", "source_text_copied",
)


def assert_reviewed_source_parity(reviewed: dict, fresh: dict) -> None:
    """Check immutable source facts against a freshly audited public snapshot.

    Human-reviewed action evidence is stored in replacement_drafts; rebuilding
    previews would erase it. Do not trust a reviewed file's source IDs alone.
    """
    if not isinstance(reviewed, dict):
        raise ValueError("Reviewed route must be a JSON object")
    for key in _ROUTE_FIELDS:
        if reviewed.get(key) != fresh.get(key):
            raise ValueError(f"Reviewed route differs from source in {key}")
    lhs = reviewed.get("sections")
    rhs = fresh.get("sections")
    if (not isinstance(lhs, list) or len(lhs) != 1
            or not isinstance(rhs, list) or len(rhs) != 1):
        raise ValueError("Missing continuous route")
    source_steps = rhs[0].get("steps")
    reviewed_steps = lhs[0].get("steps")
    if (not isinstance(source_steps, list)
            or not isinstance(reviewed_steps, list)
            or len(reviewed_steps) != len(source_steps)):
        raise ValueError("Reviewed source step coverage differs")
    for number, (actual, expected) in enumerate(zip(reviewed_steps, source_steps), 1):
        if not isinstance(actual, dict) or not isinstance(expected, dict):
            raise ValueError(f"Malformed step {number}")
        for key in _SOURCE_FIELDS:
            if actual.get(key) != expected.get(key):
                raise ValueError(f"Source mismatch in {key} at step {number}")


def build_trusted_cutovers(root: Path) -> dict:
    report = build_dofus_replacement_previews(root)
    if report["status"] != "PREVIEWS_READY_NOT_PLAYABLE":
        raise ValueError(f"Invalid Ganymède inputs: {report['issues']}")
    payloads = {}
    declarations = {}
    skipped = {}
    for guide_id, preview in sorted(report["previews"].items()):
        try:
            # Reviewed files preserve the independently verified actions;
            # freshly generated previews intentionally contain candidates only.
            reviewed_path = root / _GUIDES / "replacement_drafts" / f"{guide_id}.json"
            reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
            assert_reviewed_source_parity(reviewed, preview)
            payload = prepare_trusted_cutover(reviewed)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            skipped[guide_id] = str(exc)
            continue
        steps = payload["sections"][0]["steps"]
        source_id = payload["source_guide_id"]
        payloads[guide_id] = payload
        declarations[guide_id] = {
            "enabled": True,
            "status": "CERTIFIED_FOR_CUTOVER",
            "source_guide_id": source_id,
            "source_step_count": len(steps),
            "fingerprint": route_fingerprint(source_id, [step["id"] for step in steps]),
            "payload_sha256": certified_payload_sha256(payload),
        }
    return {
        "payloads": payloads,
        "manifest": {"schema_version": 1, "guides": declarations},
        "skipped": skipped,
        "unmapped": report["dofus_guides_without_direct_ganymede"],
    }


def write_trusted_cutovers(result: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for guide_id, payload in result["payloads"].items():
        (output_dir / f"{guide_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output_dir / "cutover_manifest.json").write_text(
        json.dumps(result["manifest"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Explicit replacement_drafts directory, never the live guides root")
    args = parser.parse_args()
    if args.output_dir.name != "replacement_drafts":
        parser.error("--output-dir must name an explicit replacement_drafts directory")
    result = build_trusted_cutovers(args.root)
    if result["skipped"]:
        print(json.dumps({"skipped": result["skipped"]}, ensure_ascii=False, indent=2))
        return 2
    write_trusted_cutovers(result, args.output_dir)
    print(json.dumps({
        "ready": len(result["payloads"]),
        "skipped": result["skipped"],
        "unmapped": result["unmapped"],
    }, ensure_ascii=False, indent=2))
    return 0 if not result["skipped"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
