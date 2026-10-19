"""Turn source-observed action hints into gated, reversible Ganymède drafts.

Only consumes factual short action proposals and a saved source-link snapshot.
This tool never writes an active guide, migrates progress or certifies objectives.
Use --write explicitly to update a *review-only* candidate and one draft.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from tools.audit_ganymede_master_refs import ROOT
from tools.audit_ganymede_step_actions import KINDS, audit_action_candidates
from tools.build_ganymede_replacement_previews import build_dofus_replacement_previews

DIRECTORY = Path("data/encyclopedia/guides")
REFERENCE_FIELDS = {
    "quest_id": "quest", "object_id": "object",
    "monster_id": "monster", "dungeon_id": "dungeon",
}

def _source_guide(root: Path, source_id: int) -> dict[str, Any]:
    found: list[dict] = []
    for path in (root / DIRECTORY).glob("ganymede_*_observed_links.json"):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if snapshot["source"]["guide_id"] == source_id:
            found.append(snapshot)
    if len(found) != 1:
        raise ValueError(f"expected exactly one observed snapshot for {source_id}")
    return found[0]

def build_review_hints(snapshot: dict, atlas_id: str, proposals: dict) -> dict:
    source_id = snapshot["source"]["guide_id"]
    source_steps = snapshot["steps"]
    if not isinstance(proposals, dict) or not isinstance(proposals.get("steps"), list):
        raise ValueError("source proposals require a steps list")
    expected = {step["source_step_number"]: step for step in source_steps}
    if sorted(expected) != list(range(1, len(source_steps) + 1)):
        raise ValueError("source steps must be continuous")
    processed: list[dict] = []
    seen: set[int] = set()
    for proposed in proposals["steps"]:
        num = proposed.get("number")
        if type(num) is not int or num not in expected or num in seen:
            raise ValueError(f"unknown or repeated source step: {num}")
        seen.add(num)
        step = expected[num]
        incoming = proposed.get("actions")
        if not isinstance(incoming, list):
            raise ValueError(f"step {num} must have action list")
        actions: list[dict] = []
        for item in incoming:
            if not isinstance(item, dict):
                raise ValueError(f"invalid source action on step {num}")
            kind, label = item.get("kind"), item.get("label")
            if kind not in KINDS or not isinstance(label, str):
                raise ValueError(f"invalid source kind or label at step {num}")
            label = " ".join(label.split())
            if not label or len(label) > 120 or "](http" in label:
                raise ValueError(f"unclear or unlicensed label at step {num}")
            action: dict[str, Any] = {"kind": kind, "label": label}
            for field, namespace in REFERENCE_FIELDS.items():
                if field in item:
                    value = item[field]
                    if type(value) is not int or value not in step["external_dofusdb_ids"][namespace]:
                        raise ValueError(f"unobserved {field} on step {num}: {value}")
                    action[field] = value
            if "guide_id" in item:
                value = item["guide_id"]
                if type(value) is not int or value not in step["linked_guide_ids"]:
                    raise ValueError(f"unobserved guide link on step {num}")
                action["guide_id"] = value
            if "object_ids" in item:
                values = item["object_ids"]
                if not isinstance(values, list) or not values or any(
                    type(value) is not int or
                    value not in step["external_dofusdb_ids"]["object"]
                    for value in values
                ):
                    raise ValueError(f"unobserved object_ids on step {num}")
                action["object_ids"] = values
            for field in ("quantity", "participants_min"):
                if field in item:
                    value = item[field]
                    if type(value) is not int or value < 1:
                        raise ValueError(f"invalid {field} on step {num}")
                    action[field] = value
            if item.get("optional") is True:
                action["optional"] = True
            if "alternative_group" in item:
                group = item["alternative_group"]
                if not isinstance(group, str) or not group.strip():
                    raise ValueError(f"invalid alternative group on step {num}")
                action["alternative_group"] = group.strip()
            actions.append(action)
        if not actions:
            continue  # Missing evidence is not a reconstructed stage.
        processed.append({
            "source_step_number": num,
            "stable_step_id": f"ganymede_{source_id}_step_{num:04d}",
            "source_page": step["source_page"],
            "review_status": "AUTO_EXTRACTED_NEEDS_REVIEW",
            "quest_objectives_verified": False,
            "at": step["coordinate_mentions"][0] if step["coordinate_mentions"] else None,
            "next": step["coordinate_mentions"][-1] if step["coordinate_mentions"] else None,
            "actions": actions,
        })
    processed.sort(key=lambda step: step["source_step_number"])
    return {
        "schema_version": 1, "atlas_guide_id": atlas_id,
        "source_guide_id": source_id, "source_url": snapshot["source"]["source_url"],
        "source_step_count": len(source_steps),
        "evidence_level": "AUTOMATED_SOURCE_ACTION_HINTS_UNVERIFIED",
        "editorial_text_copied": False, "certified_actions": 0,
        "ready_to_replace": False, "steps": processed,
    }

def write_gated_preview(root: Path, evidence: dict, *, write: bool) -> dict:
    root = root.resolve()
    source_id, atlas_id = evidence["source_guide_id"], evidence["atlas_guide_id"]
    candidates = root / DIRECTORY / f"ganymede_{source_id}_action_candidates.json"
    if candidates.exists():
        previous = json.loads(candidates.read_text(encoding="utf-8"))
        if previous.get("evidence_level") != "AUTOMATED_SOURCE_ACTION_HINTS_UNVERIFIED":
            raise ValueError("refusing to overwrite human-reviewed candidate actions")
    previous_bytes = candidates.read_bytes() if candidates.exists() else None
    generated = json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    if not write:
        return {"status": "PREVIEW_ONLY", "source_guide_id": source_id,
                "action_hint_steps": len(evidence["steps"]),
                "certified_actions": 0, "replacement_activated": False}
    target = root / DIRECTORY / "replacement_drafts" / f"{atlas_id}.json"
    if not target.is_file():
        raise ValueError("refusing to create a replacement without an existing draft")
    saved = target.read_bytes()
    try:
        candidates.write_text(generated, encoding="utf-8")
        validation = audit_action_candidates(root, candidates)
        if validation["status"] != "AUTO_EXTRACTED_NEEDS_MANUAL_REVIEW":
            raise ValueError(f"candidate audit failed: {validation['issues']}")
        report = build_dofus_replacement_previews(root)
        if report["status"] != "PREVIEWS_READY_NOT_PLAYABLE":
            raise ValueError(f"preview build failed: {report['issues']}")
        preview = report["previews"][atlas_id]
        if preview["replacement_active"] or preview["playable_step_count"]:
            raise ValueError("unsafe automatic activation")
        target.write_text(json.dumps(preview, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    except Exception:
        if previous_bytes is None:
            candidates.unlink(missing_ok=True)
        else:
            candidates.write_bytes(previous_bytes)
        target.write_bytes(saved)
        raise
    return {"status": "CANDIDATES_DRAFT_ONLY", "source_guide_id": source_id,
            "action_hint_steps": len(evidence["steps"]),
            "certified_actions": 0, "replacement_activated": False}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--atlas-id", required=True)
    parser.add_argument("--source-guide-id", type=int, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    source = _source_guide(root, args.source_guide_id)
    proposals = json.loads(args.input.read_text(encoding="utf-8"))
    result = write_gated_preview(
        root, build_review_hints(source, args.atlas_id, proposals),
        write=args.write,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
