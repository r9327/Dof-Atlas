"""Build integrity-bound Ganymède cutover files from complete trusted action sets.

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


def _action_label(action: dict) -> str:
    value = action.get("label")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Ganymède action has no readable label")
    return value.strip()


def prepare_trusted_cutover(preview: dict) -> dict:
    """Transform a fully populated candidate route into one playable route."""
    payload = deepcopy(preview)
    steps = payload["sections"][0]["steps"]
    if not steps:
        raise ValueError("Empty route")
    expected_count = payload.get("expected_source_step_count")
    if type(expected_count) is not int or expected_count != len(steps):
        raise ValueError("Source step count mismatch")
    source_id = payload.get("source_guide_id")
    for number, step in enumerate(steps, 1):
        if (step.get("id") != f"ganymede_{source_id}_step_{number:04d}"
                or step.get("source_step_number") != number):
            raise ValueError("Unstable or unordered Ganymède step IDs")
        actions = step.get("source_action_candidates")
        if not isinstance(actions, list) or not actions:
            raise ValueError(f"Missing Ganymède actions at {step['id']}")
        labels = [_action_label(action) for action in actions]
        step["title"] = labels[0]
        step["content"] = "\n".join(labels)
        step["manual_completion_allowed"] = True
        step["auto_completion_allowed"] = False
        # Preserve action kinds, IDs, quantities, conditions and route coordinates.
    payload["replacement_status"] = "TRUSTED_SOURCE_CUTOVER"
    payload["replacement_active"] = True
    payload["completeness_status"] = "complete"
    payload["playable_step_count"] = len(steps)
    payload["cutover_blockers"] = []
    return payload


def build_trusted_cutovers(root: Path) -> dict:
    report = build_dofus_replacement_previews(root)
    if report["status"] != "PREVIEWS_READY_NOT_PLAYABLE":
        raise ValueError(f"Invalid Ganymède inputs: {report['issues']}")
    payloads = {}
    declarations = {}
    skipped = {}
    for guide_id, preview in sorted(report["previews"].items()):
        try:
            payload = prepare_trusted_cutover(preview)
        except (ValueError, KeyError, TypeError) as exc:
            skipped[guide_id] = str(exc)
            continue
        steps = payload["sections"][0]["steps"]
        source_id = payload["source_guide_id"]
        payloads[guide_id] = payload
        declarations[guide_id] = {
            "enabled": True,
            "status": "TRUSTED_SOURCE_CUTOVER",
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
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_trusted_cutovers(args.root)
    write_trusted_cutovers(result, args.output_dir)
    print(json.dumps({
        "ready": len(result["payloads"]),
        "skipped": result["skipped"],
        "unmapped": result["unmapped"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
