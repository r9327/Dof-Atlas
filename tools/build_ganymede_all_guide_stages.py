"""Export factual Ganymède source stages for every public guide, including non-Dofus.

The 95 public tree entries supply numbered steps, coordinate mentions and
observed IDs. This is a *source reference catalogue*, not a playable quest
route: a linked quest, item or dungeon does not prove a required action.
No copyrighted editorial text, personal progress or runtime guide is changed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

from app.quest_source_index import QuestSources
from scripts.windows.quest_assets import RELATIVE_ROOT, _digest, read_lock
from tools.audit_ganymede_master_refs import (
    INDEX, ROOT, audit_ganymede_master_refs,
)
from tools.resolve_ganymede_action_labels import _french_name

GUIDES = Path("data/encyclopedia/guides")
REFERENCE_FILES = {
    "quest": "quests.json",
    "object": "items.json",
    "monster": "monsters.json",
    "dungeon": "dungeons.json",
}


def collect_public_stage_refs(root: Path) -> tuple[list[dict], dict[str, set[int]]]:
    """Read all 95 checked snapshots without manufacturing step actions."""
    root = Path(root).resolve()
    index = json.loads((root / INDEX).read_text(encoding="utf-8"))
    expected = index.get("guides", [])
    if len(expected) != 95:
        raise ValueError("Ganymède public index must contain exactly 95 guides")
    rows = {}
    for path in sorted((root / GUIDES).glob("ganymede_*_observed_links.json")):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        gid = snapshot.get("source", {}).get("guide_id")
        if type(gid) is not int or gid in rows:
            raise ValueError("Duplicate or invalid Ganymède source guide")
        result = audit_ganymede_master_refs(root, snapshot=path.relative_to(root))
        if result.get("status") != "PASS_OBSERVED_LINKS_ONLY":
            raise ValueError(f"Invalid source snapshot {path.name}: {result.get('issues')}")
        rows[gid] = snapshot
    expected_ids = {row["ganymede_guide_id"] for row in expected}
    if len(expected_ids) != 95 or set(rows) != expected_ids:
        raise ValueError("Ganymède source snapshot/index identity mismatch")

    needed = {kind: set() for kind in REFERENCE_FILES}
    result = []
    for record in expected:
        gid = record["ganymede_guide_id"]
        snapshot = rows[gid]
        steps = snapshot["steps"]
        if len(steps) != record["listed_step_count"]:
            raise ValueError(f"Source stage coverage mismatch: guide {gid}")
        published = []
        for number, step in enumerate(steps, 1):
            if step.get("source_step_number") != number:
                raise ValueError(f"Source stage order mismatch: {gid}/{number}")
            external = step.get("external_dofusdb_ids", {})
            ids = {}
            for namespace in REFERENCE_FILES:
                values = external.get(namespace)
                if (not isinstance(values, list)
                        or any(type(v) is not int or v <= 0 for v in values)):
                    raise ValueError(f"Invalid public ID list: {gid}/{number}/{namespace}")
                ids[namespace] = list(values)
                needed[namespace].update(values)
            published.append({
                "stable_step_id": f"ganymede_{gid}_step_{number:04d}",
                "source_step_number": number,
                "source_page": step["source_page"],
                "observed_coordinates": step["coordinate_mentions"],
                "linked_guide_ids": step["linked_guide_ids"],
                "external_dofusdb_ids": ids,
                "has_verified_action": False,
                "auto_completion_allowed": False,
            })
        result.append({
            "source_guide_id": gid,
            "source_guide_url": record["source_url"],
            "source_title_original": record["title"],
            "source_step_count": len(published),
            "steps": published,
            "playable": False,
        })
    if sum(row["source_step_count"] for row in result) != 7705:
        raise ValueError("Expected exactly 7705 Ganymède numbered source stages")
    return result, needed


def attach_names(guides: list[dict], names: dict[tuple[str, int], str]) -> dict:
    """Attach verified FR names without changing the source's raw IDs."""
    counts = Counter()
    output = []
    for guide in guides:
        rows = []
        for step in guide["steps"]:
            links = {}
            for namespace, values in step["external_dofusdb_ids"].items():
                links[namespace] = []
                for ident in values:
                    name = names.get((namespace, ident))
                    counts["references"] += 1
                    counts["named" if name else "unresolved"] += 1
                    links[namespace].append({
                        "source_id": ident,
                        "localized_name_fr": name,
                        "canonical_objective_verified": False,
                    })
            rows.append({
                **step,
                "source_references": links,
            })
        output.append({**guide, "steps": rows})
    return {
        "schema_version": 1,
        "status": "REVIEW_PUBLIC_REFERENCES_ONLY",
        "source": "ganymede_public_observed_links_plus_pinned_doduda_fr",
        "source_guides": len(output),
        "source_steps": sum(g["source_step_count"] for g in output),
        "reference_occurrences": counts["references"],
        "localized_reference_occurrences": counts["named"],
        "unresolved_reference_occurrences": counts["unresolved"],
        "canonical_objectives_verified": 0,
        "playable_guides": 0,
        "ready_to_replace": False,
        "guides": output,
    }


def build_all_guide_stages(root: Path, *, raw_dir: Path | None = None) -> dict:
    root = Path(root).resolve()
    guides, requested = collect_public_stage_refs(root)
    raw = Path(raw_dir).resolve() if raw_dir else root / RELATIVE_ROOT
    lock = read_lock(root)
    pinned = list(REFERENCE_FILES.values()) + ["languages/fr.json"]
    missing = []
    for filename in pinned:
        expected = lock["assets"][filename]
        path = raw / filename
        if _digest(path, expected["size"]) != expected["sha256"]:
            missing.append(filename)
    if missing:
        return {
            "schema_version": 1,
            "status": "BLOCKED_CANONICAL_SOURCE_UNAVAILABLE",
            "missing_or_stale_pinned_assets": missing,
            "source_guides": len(guides),
            "source_steps": sum(g["source_step_count"] for g in guides),
            "ready_to_replace": False,
        }
    names = {}
    with tempfile.TemporaryDirectory(prefix="atlas-ganymede-all-guide-names-") as tmp:
        sources = QuestSources(Path(tmp), disk_backed=True)
        try:
            language = sources.mapping(raw / "languages/fr.json", "entries", required=True)
            for namespace, filename in REFERENCE_FILES.items():
                table = sources.rows(raw / filename)
                for ident in sorted(requested[namespace]):
                    record = table.get(ident)
                    if not isinstance(record, dict) or record.get("id", ident) != ident:
                        continue
                    name = _french_name(record, language)
                    if name:
                        names[namespace, ident] = name
        finally:
            sources.close()
    return {
        **attach_names(guides, names),
        "pinned_release": lock["tag"],
        "distinct_named_entities": len(names),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = build_all_guide_stages(args.root, raw_dir=args.raw_dir)
    except (OSError, KeyError, ValueError, TypeError) as exc:
        result = {"schema_version": 1, "status": "FAIL", "reason": str(exc),
                  "ready_to_replace": False}
    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 1 if result["status"] == "FAIL" else 2 if result["status"].startswith("BLOCKED_") else 0


if __name__ == "__main__":
    raise SystemExit(main())
