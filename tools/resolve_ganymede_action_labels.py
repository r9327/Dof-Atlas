"""Resolve numeric Ganymède action labels from pinned Doduda French sources.

Creates a non-destructive, source-positioned label overlay. A localized entity
name is a reference hint, never proof of an objective, route or prerequisite.
Raw source files must match Atlas' pinned release; no network access is needed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import tempfile

from app.quest_catalog import localized_name
from app.quest_source_index import QuestSources
from scripts.windows.quest_assets import RELATIVE_ROOT, _digest, read_lock
from tools.audit_ganymede_master_refs import INDEX, ROOT
from tools.audit_ganymede_step_actions import audit_action_candidates

GUIDES = Path("data/encyclopedia/guides")
PATTERN = re.compile(r"\bn[º°o]\s*(\d+)\b", re.IGNORECASE)
ENTITY_FIELDS = {
    "object_id": ("object", "items.json"),
    "quest_id": ("quest", "quests.json"),
    "monster_id": ("monster", "monsters.json"),
    "dungeon_id": ("dungeon", "dungeons.json"),
    "guide_id": ("guide", None),
}
KIND_NOUN = {
    "object": "objet",
    "quest": "quête",
    "monster": "monstre",
    "dungeon": "donjon",
    "guide": "guide",
}


def render_labels(candidate: dict, names: dict[tuple[str, int], str]) -> dict:
    """Resolve only IDs explicitly attached to their *own* source action.

    Never fill missing names from adjacent steps, a generic number or an
    unrelated source. Keep unresolvable labels verbatim with provenance.
    """
    overrides = []
    gaps = []
    generic_count = 0
    for step in candidate["steps"]:
        for index, action in enumerate(step["actions"]):
            label = action["label"]
            found = list(PATTERN.finditer(label))
            if not found:
                continue
            generic_count += 1
            referenced = {}
            for field, (namespace, _) in ENTITY_FIELDS.items():
                value = action.get(field)
                if type(value) is int and value > 0:
                    referenced.setdefault(value, set()).add(namespace)
            for value in action.get("object_ids", []):
                if type(value) is int and value > 0:
                    referenced.setdefault(value, set()).add("object")
            resolved = {}
            for match in found:
                identifier = int(match.group(1))
                linked_types = referenced.get(identifier, set())
                # Refuse a name if the same ID is ambiguous across categories.
                options = [(category, names[(category, identifier)])
                           for category in linked_types
                           if names.get((category, identifier))]
                if len(linked_types) != 1 or len(options) != 1:
                    gaps.append({
                        "source_step_number": step["source_step_number"],
                        "action_index": index,
                        "external_id": identifier,
                        "cause": ("unlinked_or_ambiguous_id" if len(linked_types) != 1
                                  else "localized_name_unavailable"),
                    })
                    continue
                category, name = options[0]
                resolved[match.start()] = (match.end(), category, name)
            if not resolved:
                continue
            updated = []
            offset = 0
            for start, (end, category, name) in sorted(resolved.items()):
                updated.append(label[offset:start])
                updated.append(f"«{name}»")
                offset = end
            updated.append(label[offset:])
            override = "".join(updated)
            overrides.append({
                "source_step_number": step["source_step_number"],
                "stable_step_id": step["stable_step_id"],
                "action_index": index,
                "source_label": label,
                "display_label": override,
                "source_review_status": step["review_status"],
                "canonical_objective_verified": False,
            })
    return {
        "source_guide_id": candidate["source_guide_id"],
        "atlas_guide_id": candidate["atlas_guide_id"],
        "source_steps": candidate["source_step_count"],
        "generic_label_actions": generic_count,
        "resolved_action_labels": len(overrides),
        "unresolved_references": gaps,
        "label_overrides": overrides,
    }


def _gather_requested(paths: list[Path]) -> tuple[list[dict], dict[str, set[int]]]:
    candidates = []
    needed = {namespace: set() for namespace, _ in ENTITY_FIELDS.values()}
    for path in paths:
        doc = json.loads(path.read_text(encoding="utf-8"))
        candidates.append(doc)
        for step in doc["steps"]:
            for action in step["actions"]:
                if not PATTERN.search(action["label"]):
                    continue
                for field, (namespace, _) in ENTITY_FIELDS.items():
                    value = action.get(field)
                    if type(value) is int and value > 0:
                        needed[namespace].add(value)
                for value in action.get("object_ids", []):
                    if type(value) is int and value > 0:
                        needed["object"].add(value)
    return candidates, needed


def resolve_all(root: Path, *, raw_dir: Path | None = None) -> dict:
    root = Path(root).resolve()
    raw = Path(raw_dir).resolve() if raw_dir else root / RELATIVE_ROOT
    paths = sorted((root / GUIDES).glob("ganymede_*_action_candidates.json"))
    if len(paths) != 20:
        return {"status": "FAIL", "reason": "expected exactly 20 candidate guides",
                "observed_candidate_guides": len(paths), "ready_to_replace": False}
    for path in paths:
        validation = audit_action_candidates(root, path)
        if validation["status"] not in {
            "REVIEW_ACTION_CANDIDATES_ONLY", "AUTO_EXTRACTED_NEEDS_MANUAL_REVIEW"
        }:
            return {"status": "FAIL", "reason": "invalid source candidate",
                    "file": path.name, "issues": validation["issues"],
                    "ready_to_replace": False}
    candidates, requested = _gather_requested(paths)
    lock = read_lock(root)
    missing = []
    for namespace, filename in {v for v in ENTITY_FIELDS.values()}:
        if filename is None or not requested[namespace]:
            continue
        info = lock["assets"][filename]
        target = raw / filename
        if _digest(target, info["size"]) != info["sha256"]:
            missing.append(filename)
    if requested["guide"]:
        guide_index = root / INDEX
        if not guide_index.is_file():
            missing.append(str(INDEX))
    # The pinned French dictionary is mandatory if any entity requires lookup.
    if any(requested[category] for category in ("object", "quest", "monster", "dungeon")):
        language = raw / "languages/fr.json"
        info = lock["assets"]["languages/fr.json"]
        if _digest(language, info["size"]) != info["sha256"]:
            missing.append("languages/fr.json")
    if missing:
        return {
            "schema_version": 1,
            "status": "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE",
            "missing_or_stale_pinned_assets": sorted(missing),
            "requested_namespaces": {k: len(v) for k, v in requested.items()},
            "ready_to_replace": False,
        }

    names: dict[tuple[str, int], str] = {}
    if requested["guide"]:
        index = json.loads((root / INDEX).read_text(encoding="utf-8"))
        for row in index["guides"]:
            gid, title = row.get("ganymede_guide_id"), row.get("title")
            if gid in requested["guide"] and isinstance(title, str) and title.strip():
                names["guide", gid] = title.strip()
    with tempfile.TemporaryDirectory(prefix="atlas-ganymede-names-") as temp:
        sources = QuestSources(Path(temp), disk_backed=True)
        try:
            language = sources.mapping(raw / "languages/fr.json", "entries", required=True) \
                if any(requested[k] for k in ("object", "quest", "monster", "dungeon")) \
                else {}
            for namespace, filename in {v for v in ENTITY_FIELDS.values()}:
                if filename is None or not requested[namespace]:
                    continue
                rows = sources.rows(raw / filename)
                for identifier in sorted(requested[namespace]):
                    row = rows.get(identifier)
                    if not isinstance(row, dict) or row.get("id", identifier) != identifier:
                        continue
                    name = localized_name(row, language, fallback="")
                    if name:
                        names[namespace, identifier] = name
        finally:
            sources.close()

    guides = [render_labels(doc, names) for doc in candidates]
    unresolved = [dict(source_guide_id=guide["source_guide_id"], **ref)
                  for guide in guides for ref in guide["unresolved_references"]]
    totals = Counter()
    for guide in guides:
        totals["generic_label_actions"] += guide["generic_label_actions"]
        totals["resolved_action_labels"] += guide["resolved_action_labels"]
    return {
        "schema_version": 1,
        "status": "REVIEW_NAME_GAPS" if unresolved else "REVIEW_NAMES_RESOLVED",
        "source": "doduda_pinned_french_names_and_ganymede_public_index",
        "pinned_release": lock["tag"],
        "resolved_namespaces": {k: sum(category == k for category, _ in names)
                                for k in requested},
        "guides": guides,
        "generic_label_actions": totals["generic_label_actions"],
        "resolved_action_labels": totals["resolved_action_labels"],
        "unresolved_reference_count": len(unresolved),
        "unresolved_references": unresolved,
        "canonical_objectives_verified": 0,
        "ready_to_replace": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = resolve_all(args.root, raw_dir=args.raw_dir)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 1 if result["status"] == "FAIL" else 2 if result["status"].startswith("BLOCKED_") else 0


if __name__ == "__main__":
    raise SystemExit(main())
