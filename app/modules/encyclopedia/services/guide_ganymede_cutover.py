"""Fail-closed selection of exactly one Ganymède Dofus route per existing guide.

Keep canonical certification distinct from source-trusted manual step completion;
never silently certify Doduda objectives or migrate historical progress.
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


def certified_payload_sha256(payload: dict) -> str:
    """Bind the cutover manifest to the full replacement payload."""
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()




def reconstruct_trusted_manual_route(guide: object) -> dict:
    """Rehydrate only the currently selected route from compact typed models.

    MemoryBoundGuideProvider/IndexedGuideProvider remove nested raw sections to
    avoid retaining duplicate JSON trees. The Ganymède reader must not assume
    guide.raw still contains 'sections'; nor should it read all routes again.
    All source action facts remain in GuideStep.raw and the integrity-gated
    cutover was checked when the provider selected this guide.
    """
    root = getattr(guide, "raw", None)
    if not isinstance(root, dict) or root.get("replacement_status") != "TRUSTED_SOURCE_STEPS":
        raise ValueError("not an active manual source route")
    sections = getattr(guide, "sections", ())
    if len(sections) != 1:
        raise ValueError("manual source route must have one section")
    rebuilt = dict(root)
    rebuilt["sections"] = []
    for section in sections:
        original = getattr(section, "raw", None)
        if not isinstance(original, dict):
            raise ValueError("missing source section metadata")
        section_data = dict(original)
        section_data["steps"] = []
        for step in getattr(section, "steps", ()):
            raw_step = getattr(step, "raw", None)
            if not isinstance(raw_step, dict):
                raise ValueError("missing source step metadata")
            section_data["steps"].append(dict(raw_step))
        rebuilt["sections"].append(section_data)
    # Validate all IDs and the declared count before the UI uses the payload.
    source_id = rebuilt.get("source_guide_id")
    count = rebuilt.get("expected_source_step_count")
    steps = rebuilt["sections"][0]["steps"]
    if (type(source_id) is not int or type(count) is not int
            or count < 1 or len(steps) != count
            or any(
                row.get("id") != f"ganymede_{source_id}_step_{i:04d}"
                or row.get("source_step_number") != i
                or row.get("source_guide_id") != source_id
                for i, row in enumerate(steps, 1)
            )):
        raise ValueError("source route lost its certified step order")
    return rebuilt


def select_verified_replacement_path(
    guides_dir: Path,
    catalog_row: dict,
    *,
    allow_source_manual: bool = False,
) -> Path | None:
    """Select exactly one integrity-checked Dofus route, or keep the legacy file.

    Two explicit levels are supported: canonical actions verified by Atlas, or
    source-trusted Ganymede steps with *manual* progress only. The latter never
    claims canonical objective completion or migrates old per-step saves.
    """
    if not isinstance(catalog_row, dict) or catalog_row.get("category") != "dofus":
        return None
    guide_id = catalog_row.get("id")
    if not isinstance(guide_id, str) or _ID.fullmatch(guide_id) is None:
        return None

    drafts = Path(guides_dir) / "replacement_drafts"
    trusted = drafts / "cutovers"
    root = trusted if (trusted / _MANIFEST).is_file() else drafts
    manifest_path = root / _MANIFEST
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
            return None
        declarations = manifest.get("guides")
        if not isinstance(declarations, dict):
            return None
        declaration = declarations.get(guide_id)
        status = declaration.get("status") if isinstance(declaration, dict) else None
        if (not isinstance(declaration, dict)
                or declaration.get("enabled") is not True
                or status not in {"CERTIFIED_FOR_CUTOVER", "TRUSTED_SOURCE_STEPS"}):
            return None

        # Source-hint routes have no canonical quest/objective connections yet.
        # Until the guide UI explicitly supports them, keep the legacy runtime
        # route and all existing quest navigation/progression contracts.
        if status == "TRUSTED_SOURCE_STEPS" and allow_source_manual is not True:
            return None

        source_id = declaration.get("source_guide_id")
        count = declaration.get("source_step_count")
        expected_hash = declaration.get("fingerprint")
        expected_payload_hash = declaration.get("payload_sha256")
        if (type(source_id) is not int or source_id <= 0
                or type(count) is not int or count <= 0
                or not isinstance(expected_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected_hash) is None
                or not isinstance(expected_payload_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", expected_payload_hash) is None):
            return None
        path = root / f"{guide_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or certified_payload_sha256(payload) != expected_payload_hash:
            return None
        if (payload.get("schema_version") != 1
                or payload.get("id") != guide_id
                or payload.get("category") != "dofus"
                or payload.get("source_guide_id") != source_id
                or payload.get("route_origin") != "GANYMEDE_CONTINUOUS_STEP_ORDER"
                or payload.get("replacement_status") != status
                or payload.get("replacement_active") is not True
                or payload.get("completeness_status") != "complete"
                or payload.get("expected_source_step_count") != count
                or payload.get("playable_step_count") != count
                or payload.get("source_text_copied") is not False
                or payload.get("guide_progress_id_unchanged") is not True
                or payload.get("cutover_blockers") != []):
            return None
        if status == "CERTIFIED_FOR_CUTOVER":
            if payload.get("legacy_manual_steps_migration_verified") is not True:
                return None
        else:
            if (root != trusted
                    or payload.get("progress_migration_not_required") is not True
                    or payload.get("legacy_manual_steps_migration_verified") is not False
                    or payload.get("canonical_objectives_certified") is not False
                    or payload.get("auto_completion_allowed") is not False
                    or not isinstance(payload.get("source_link_snapshot"), str)
                    or not payload["source_link_snapshot"].endswith("_observed_links.json")):
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
                    or (status == "TRUSTED_SOURCE_STEPS" and step.get("auto_completion_allowed") is not False)
                    or step.get("original_prose_imported") is not False):
                return None
            if status == "CERTIFIED_FOR_CUTOVER":
                if step.get("source_action_review_status") != "CERTIFIED_CANONICAL_ACTIONS":
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
            else:
                if (step.get("source_action_review_status") not in {
                        "REVIEW_SOURCE_ACTION", "AUTO_EXTRACTED_NEEDS_REVIEW"}
                        or step.get("verified_actions") != []):
                    return None
                actions = step.get("source_action_candidates")
                if not isinstance(actions, list) or not actions:
                    return None
                labels = []
                for action in actions:
                    if not isinstance(action, dict) or not isinstance(action.get("kind"), str):
                        return None
                    label = action.get("label")
                    if not isinstance(label, str) or not label.strip() or len(label) > 120:
                        return None
                    labels.append(" ".join(label.split()))
                if (not isinstance(step.get("content"), str)
                        or step["content"] != "\n".join(labels)):
                    return None
            step_ids.append(expected_id)
        if route_fingerprint(source_id, step_ids) != expected_hash:
            return None
        return path
    except (OSError, ValueError, TypeError, KeyError):
        return None


def active_manual_catalog_sources(provider: object, guides: list[object]) -> dict[str, tuple[int, int]]:
    """Return (source ID, step count) for *selected* trusted manual routes.

    Only the small manifest is read. Memory-bound providers have already
    selected an integrity-checked cutover and retain its exact file path in
    _detail_entries; never rehydrate all 1,694 steps for the home counters.
    A legacy fallback must not display the Ganymède manual progress.
    """
    guides_dir = getattr(provider, "guides_dir", None)
    if guides_dir is None:
        return {}
    trusted = Path(guides_dir) / "replacement_drafts" / "cutovers"
    try:
        manifest = json.loads((trusted / _MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        return {}
    declarations = manifest.get("guides")
    if not isinstance(declarations, dict):
        return {}
    selected_entries = getattr(provider, "_detail_entries", None)
    result: dict[str, tuple[int, int]] = {}
    for guide in guides:
        guide_id = getattr(guide, "id", None)
        if (not isinstance(guide_id, str) or guide_id in {
                "guide_complet", "dofus_sylvestre"}
                or getattr(guide, "category", None) != "dofus"):
            continue
        declaration = declarations.get(guide_id)
        if not isinstance(declaration, dict) or declaration.get("enabled") is not True:
            continue
        if declaration.get("status") != "TRUSTED_SOURCE_STEPS":
            continue
        source_id = declaration.get("source_guide_id")
        total = declaration.get("source_step_count")
        if type(source_id) is not int or source_id <= 0 or type(total) is not int or total <= 0:
            continue
        if isinstance(selected_entries, dict):
            selected = selected_entries.get(guide_id)
            if (not isinstance(selected, tuple) or not selected
                    or Path(selected[0]) != trusted / f"{guide_id}.json"):
                continue
        else:
            raw = getattr(guide, "raw", None)
            if not isinstance(raw, dict) or raw.get("replacement_status") != "TRUSTED_SOURCE_STEPS":
                continue
        result[guide_id] = (source_id, total)
    return result


def manual_source_completed_count(
    progress_service: object, character_key: str, guide_id: str,
    source_id: int, total: int,
) -> int:
    """Count only stable Ganymède step keys; never count finished quests."""
    from app.core.character_identity import is_character_key

    if not is_character_key(character_key):
        return 0
    checked = progress_service.manual_steps(character_key, guide_id)
    return sum(
        f"ganymede_{source_id}_step_{position:04d}" in checked
        for position in range(1, total + 1)
    )
