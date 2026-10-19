"""Build a provenance-preserving ID registry across Ganymède, Atlas and DPLN.

Read-only: inputs are the tracked Atlas guide JSON files, public-link
snapshots and independently reviewed DPLN evidence. No user progress data,
runtime Doduda sources, estimated item quantities or inferred route orders.
The generated registry is review evidence, NOT an executable guide.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from tools.audit_ganymede_master_refs import INDEX, ROOT
from tools.audit_ganymede_quest_candidates import (
    CROSSWALK, GUIDES_DIR, _load, audit_ganymede_quest_candidates,
)

CATALOG = GUIDES_DIR / "catalog.json"
LINK_TYPES = ("quest", "dungeon", "object", "monster")


def _strict_id(value: object) -> int | None:
    return value if type(value) is int and value > 0 else None


def build_ganymede_id_registry(root: Path) -> dict[str, object]:
    """Group references by *typed* ID, retaining every occurrence/provenance."""
    root = Path(root).resolve()
    upstream = audit_ganymede_quest_candidates(root)
    if upstream.get("status") != "REVIEW_REQUIRED":
        return {
            "schema_version": 1, "status": "FAIL",
            "issues": [{"code": "upstream_invalid",
                        "detail": str(upstream.get("issues", []))}],
            "certified_objectives": 0, "certified_routes": 0,
        }
    problems: list[dict[str, str]] = []
    try:
        manifest = _load(root / INDEX)
        atlas_catalog = _load(root / CATALOG)
        crosswalk = _load(root / CROSSWALK)
    except (OSError, ValueError) as exc:
        return {
            "schema_version": 1, "status": "FAIL",
            "issues": [{"code": "source_unavailable", "detail": str(exc)}],
            "certified_objectives": 0, "certified_routes": 0,
        }
    observed_guides = manifest.get("guides", [])
    local_guides = atlas_catalog.get("guides", [])
    guide_links = {
        row["ganymede_guide_id"]: row["atlas_guide_ids"]
        for row in crosswalk.get("guides", [])
        if isinstance(row, dict)
    }
    if (not isinstance(observed_guides, list) or
            not isinstance(local_guides, list) or
            not all(isinstance(x, dict) for x in local_guides)):
        return {
            "schema_version": 1, "status": "FAIL",
            "issues": [{"code": "bad_catalog", "detail": "guide index/catalog shape"}],
            "certified_objectives": 0, "certified_routes": 0,
        }

    # Typed namespaces prevent a monster ID from becoming a quest/item ID.
    entities: dict[str, dict[int, dict]] = {kind: {} for kind in LINK_TYPES}
    def entity(kind: str, ident: int) -> dict:
        return entities[kind].setdefault(ident, {
            "id": ident, "type": kind, "ganymede_occurrences": [],
            "atlas_occurrences": [], "dpln_evidence": [],
        })

    # Early snapshots use semantic filenames (e.g. ganymede_cawotte_*),
    # later ones use numeric guide IDs. Resolve by the verified source ID.
    expected_source_ids = {row["ganymede_guide_id"] for row in observed_guides}
    seen_source_ids: set[int] = set()
    for path in sorted((root / GUIDES_DIR).glob("ganymede_*_observed_links.json")):
        try:
            snapshot = _load(path)
            gid = snapshot["source"]["guide_id"]
            if gid not in expected_source_ids or gid in seen_source_ids:
                raise ValueError(f"unknown or duplicate source ID: {gid}")
            seen_source_ids.add(gid)
            for step in snapshot["steps"]:
                no = step["source_step_number"]
                page = step["source_page"]
                for kind in LINK_TYPES:
                    for ident in step["external_dofusdb_ids"][kind]:
                        if _strict_id(ident) is None:
                            raise ValueError(f"bad external {kind} ID")
                        entity(kind, ident)["ganymede_occurrences"].append({
                            "source_guide_id": gid, "source_step": no,
                            "source_page": page,
                            # Hints, not confirmed quest-to-Atlas equivalences.
                            "mapped_atlas_guide_hints": guide_links.get(gid, []),
                        })
        except (OSError, ValueError, TypeError, KeyError) as exc:
            problems.append({"code": "invalid_source_guide",
                             "detail": f"{gid}: {exc}"})

    missing_source_ids = sorted(expected_source_ids - seen_source_ids)
    if missing_source_ids:
        problems.append({
            "code": "missing_source_snapshots",
            "detail": str(missing_source_ids),
        })

    atlas_guide_metadata: list[dict[str, object]] = []
    seen_local: set[str] = set()
    for item in local_guides:
        guide_id = item.get("id")
        filename = item.get("file")
        if (not isinstance(guide_id, str) or not guide_id or
                guide_id in seen_local or not isinstance(filename, str) or
                Path(filename).name != filename or
                not filename.endswith(".json")):
            problems.append({"code": "bad_local_guide_reference",
                             "detail": str(guide_id)})
            continue
        seen_local.add(guide_id)
        try:
            guide = _load(root / GUIDES_DIR / filename)
            if guide.get("id") != guide_id:
                raise ValueError("local guide ID does not match catalog")
            all_steps = guide["sections"]
            if not isinstance(all_steps, list):
                raise ValueError("guide has invalid sections")
            count = 0
            for section in all_steps:
                if not isinstance(section, dict) or not isinstance(section.get("steps"), list):
                    raise ValueError("invalid guide section")
                for row in section["steps"]:
                    if not isinstance(row, dict):
                        raise ValueError("invalid local guide step")
                    kind = row.get("type")
                    # Non-quest entries remain guide-owned until typed and verified.
                    if kind != "quest":
                        continue
                    ident = _strict_id(row.get("entity_id"))
                    if ident is None:
                        raise ValueError("quest step has invalid entity ID")
                    prereqs = row.get("prerequisites", [])
                    if not isinstance(prereqs, list):
                        raise ValueError("invalid local prerequisites")
                    for req in prereqs:
                        if (not isinstance(req, dict) or
                                not isinstance(req.get("type"), str) or
                                _strict_id(req.get("entity_id")) is None):
                            raise ValueError("invalid prerequisite entity")
                    alternatives = row.get("alternative_groups", [])
                    if not isinstance(alternatives, list) or not all(
                        isinstance(x, str) and x for x in alternatives
                    ):
                        raise ValueError("invalid OR alternatives")
                    entity("quest", ident)["atlas_occurrences"].append({
                        "atlas_guide_id": guide_id,
                        "atlas_step_id": row.get("id"),
                        "atlas_section_id": section.get("id"),
                        "local_optional": row.get("optional"),
                        "local_relation": row.get("relation"),
                        "local_alternative_groups": alternatives,
                        "local_declared_prerequisites": [
                            {"type": req["type"], "entity_id": req["entity_id"]}
                            for req in prereqs
                        ],
                        "source_confidence": "ATLAS_GUIDE_UNVERIFIED_DECLARATION",
                    })
                    count += 1
            atlas_guide_metadata.append({
                "id": guide_id, "category": item.get("category"),
                "completeness_status": guide.get("completeness_status"),
                "generation_source": guide.get("generation_source"),
                "graph_semantics": guide.get("graph_semantics", {}),
                "local_quest_step_occurrences": count,
                "linked_achievement_ids": guide.get("linked_achievement_ids", []),
            })
        except (OSError, ValueError, KeyError, TypeError) as exc:
            problems.append({"code": "invalid_atlas_guide",
                             "detail": f"{guide_id}: {exc}"})

    preparation_sources: list[dict[str, object]] = []
    for path in sorted((root / GUIDES_DIR).glob("ganymede_dpln_*_evidence.json")):
        try:
            evidence = _load(path)
            gid = evidence["source_guide_id"]
            atlas_guide = evidence["atlas_guide_id"]
            for key, role in (
                ("main_quests", "DPLN_MAIN_REVIEW"),
                ("access_and_prerequisites", "DPLN_CONTEXT_PREREQUISITE_REVIEW"),
                ("non_main_references", "DPLN_SIDE_OR_CONTEXT_REVIEW"),
            ):
                for row in evidence.get(key, []):
                    ident = _strict_id(row.get("quest_id"))
                    if ident is None:
                        raise ValueError(f"invalid {key} quest ID")
                    entity("quest", ident)["dpln_evidence"].append({
                        "source_guide_id": gid,
                        "atlas_guide_id": atlas_guide,
                        "evidence_file": path.name,
                        "source_role": role,
                        "source_name": row.get("name"),
                        "dofusdb_quest_url": row.get("dofusdb_url"),
                        "local_quest_identity_certified": False,
                    })
            if "preparation_evidence" in evidence or "timed_progression_evidence" in evidence:
                preparation_sources.append({
                    "source_guide_id": gid, "atlas_guide_id": atlas_guide,
                    "evidence_file": path.name,
                    # These are guide-scoped, NOT attached to every quest.
                    "source_global_preparation": evidence.get("preparation_evidence"),
                    "source_global_timing": evidence.get("timed_progression_evidence"),
                    "ready_for_shopping_list": False,
                    "per_character_quantities_verified": False,
                })
        except (OSError, ValueError, KeyError, TypeError) as exc:
            problems.append({"code": "invalid_evidence",
                             "detail": f"{path.name}: {exc}"})

    def serialize(kind: str) -> dict[str, dict]:
        return {
            str(k): entities[kind][k] for k in sorted(entities[kind])
        }

    quests = serialize("quest")
    referenced_by_both = sum(
        bool(q["ganymede_occurrences"]) and bool(q["atlas_occurrences"])
        for q in quests.values()
    )
    main_reviewed = sum(
        any(ev["source_role"] == "DPLN_MAIN_REVIEW" for ev in q["dpln_evidence"])
        for q in quests.values()
    )
    result = {
        "schema_version": 1,
        "status": "FAIL" if problems else "REVIEW_REQUIRED",
        "evidence_level": "typed_entity_id_registry_with_provenance_not_gameplay_certification",
        "source": {"ganymede_main_index": str(INDEX),
                   "atlas_guide_catalog": str(CATALOG),
                   "guide_crosswalk": str(CROSSWALK)},
        "summary": {
            "ganymede_guides": len(observed_guides),
            "atlas_guides": len(atlas_guide_metadata),
            "distinct_quest_ids": len(quests),
            "quest_ids_mentioned_by_both_sources": referenced_by_both,
            "dpln_main_quest_ids_for_review": main_reviewed,
            "distinct_dungeon_ids": len(entities["dungeon"]),
            "distinct_object_ids": len(entities["object"]),
            "distinct_monster_ids": len(entities["monster"]),
        },
        "quest_by_id": quests,
        "dungeon_by_id": serialize("dungeon"),
        "object_by_id": serialize("object"),
        "monster_by_id": serialize("monster"),
        "atlas_guide_metadata": atlas_guide_metadata,
        "guide_level_preparation_sources": preparation_sources,
        "certified_quest_mappings": 0,
        "certified_objectives": 0,
        "certified_prerequisites": 0,
        "certified_routes": 0,
        "issues": problems,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path,
                        help="write review JSON to an explicit destination")
    args = parser.parse_args()
    report = build_ganymede_id_registry(args.root)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 1 if report["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
