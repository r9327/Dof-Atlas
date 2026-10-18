"""Fail-closed, single-route cutover for fully certified Ganymède Dofus guides.

Never show source-link drafts as playable. A verified replacement is selected
in place of, not in addition to, the legacy catalogue entry. The user's
existing per-character guide progression remains untouched.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_MANIFEST = "cutover_manifest.json"
_ID = re.compile(r"^[a-z0-9_]+$")
_ALLOWED_ACTION_KINDS = frozenset({
    "quest_objective", "interaction", "travel", "combat",
    "dungeon", "collect", "craft", "prepare", "information",
})


def route_fingerprint(source_guide_id: int, step_ids: list[str]) -> str:
    return hashlib.sha256(json.dumps(
        {"source_guide_id": source_guide_id, "step_ids": step_ids},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def select_verified_replacement_path(
    guides_dir: Path,
    catalog_row: dict,
) -> Path | None:
    """Return a certified replacement or None; no files/progress are modified."""
    if not isinstance(catalog_row, dict) or catalog_row.get("category") != "dofus":
        return None
    guide_id = catalog_row.get("id")
    if not isinstance(guide_id, str) or _ID.fullmatch(guide_id) is None:
        return None

    root = Path(guides_dir) / "replacement_drafts"
    manifest_path = root / _MANIFEST
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != 1:
            return None
        declarations = manifest.get("guides")
        if not isinstance(declarations, dict):
            return None
        declaration = declarations.get(guide_id)
        if (not isinstance(declaration, dict)
                or declaration.get("enabled") is not True
                or declaration.get("status") != "CERTIFIED_FOR_CUTOVER"
                or declaration.get("progress_migration_verified") is not True):
            return None

        source_id = declaration.get("source_guide_id")
        count = declaration.get("source_step_count")
        expected_hash = declaration.get("fingerprint")
        if (type(source_id) is not int or source_id <= 0
                or type(count) is not int or count <= 0
                or not isinstance(expected_hash, str) or len(expected_hash) != 64):
            return None

        path = root / f"{guide_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (payload.get("schema_version") != 1
                or payload.get("id") != guide_id
                or payload.get("category") != "dofus"
                or payload.get("source_guide_id") != source_id
                or payload.get("route_origin") != "GANYMEDE_CONTINUOUS_STEP_ORDER"
                or payload.get("replacement_status") != "CERTIFIED_FOR_CUTOVER"
                or payload.get("replacement_active") is not True
                or payload.get("completeness_status") != "complete"
                or payload.get("legacy_manual_steps_migration_verified") is not True
                or payload.get("expected_source_step_count") != count
                or payload.get("playable_step_count") != count
                or payload.get("source_text_copied") is not False):
            return None
        sections = payload.get("sections")
        if (not isinstance(sections, list) or len(sections) != 1
                or not isinstance(sections[0], dict)):
            return None
        steps = sections[0].get("steps")
        if not isinstance(steps, list) or len(steps) != count:
            return None

        step_ids = []
        for n, step in enumerate(steps, 1):
            expected_id = f"ganymede_{source_id}_step_{n:04d}"
            if (not isinstance(step, dict)
                    or step.get("id") != expected_id
                    or step.get("source_guide_id") != source_id
                    or step.get("source_step_number") != n
                    or step.get("manual_completion_allowed") is not True
                    or step.get("original_prose_imported") is not False):
                return None
            actions = step.get("verified_actions")
            if not isinstance(actions, list) or not actions:
                return None
            for action in actions:
                if (not isinstance(action, dict)
                        or action.get("verified") is not True
                        or action.get("kind") not in _ALLOWED_ACTION_KINDS
                        or not isinstance(action.get("text"), str)
                        or not action["text"].strip()
                        or not isinstance(action.get("evidence"), list)
                        or not action["evidence"]):
                    return None
            step_ids.append(expected_id)
        if route_fingerprint(source_id, step_ids) != expected_hash:
            return None
        return path
    except (OSError, ValueError, TypeError, KeyError):
        return None
