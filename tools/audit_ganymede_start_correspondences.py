"""Explicit offline audit of Ganymède steps vs canonical Doduda start maps.

Run: python -m tools.audit_ganymede_start_correspondences --output artifacts/ganymede_starts_review.json
Does not modify signed guides, start Organizer, or create travel commands.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from app.constants import DATA_DIR, RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.providers.quest_provider import QuestProvider
from app.modules.encyclopedia.services.guide_ultime_route_adapter import GuideUltimeRouteAdapter
from app.modules.encyclopedia.services.guide_ganymede_continuous_plan import (
    canonical_map_positions_from_doduda,
)
from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    select_verified_replacement_path,
)
from app.modules.encyclopedia.services.guide_ganymede_start_review import (
    review_ganymede_start_correspondences,
)

GUIDES = DATA_DIR / "encyclopedia/guides"


def signed_source_quest_ids(
    guides_dir: Path, guide_ids: tuple[str, ...],
) -> tuple[int, ...]:
    """Read *only* allowed signed routes and exact source quest-start IDs."""
    ids: set[int] = set()
    for guide_id in guide_ids:
        path = select_verified_replacement_path(
            guides_dir, {"id": guide_id, "category": "dofus"},
            allow_source_manual=True,
        )
        if path is None:
            raise ValueError(f"Untrusted signed guide: {guide_id}")
        route = json.loads(path.read_text(encoding="utf-8"))
        for step in route["sections"][0]["steps"]:
            for candidate in step["source_action_candidates"]:
                if candidate.get("kind") == "quest_start":
                    quest_id = candidate.get("quest_id")
                    if type(quest_id) is not int or quest_id <= 0:
                        raise ValueError(f"Malformed quest start: {guide_id}")
                    ids.add(quest_id)
    return tuple(sorted(ids))


def build_review_report(
    guides_dir: Path = GUIDES,
    raw_data_dir: Path = RAW_QUEST_DATA_DIR,
    guide_ids: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Audit the signed route corpus once using one shared local Atlas adapter."""
    manifest_path = guides_dir / "replacement_drafts/cutovers/cutover_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    declarations = manifest.get("guides")
    if not isinstance(declarations, dict):
        raise ValueError("Malformed Ganymède cutover manifest")
    eligible = {
        guide_id for guide_id, row in declarations.items()
        if isinstance(row, dict)
        and row.get("enabled") is True
        and row.get("status") == "TRUSTED_SOURCE_STEPS"
    }
    selected = tuple(sorted(eligible)) if guide_ids is None else tuple(guide_ids)
    if not selected or len(set(selected)) != len(selected) or any(
        guide not in eligible for guide in selected
    ):
        raise ValueError("Guide selection not in the signed manual cutover")
    quest_ids = signed_source_quest_ids(guides_dir, selected)
    provider = QuestProvider(data_dir=raw_data_dir)
    catalog = provider.get_catalog()
    # Use the player-safe, sentinel-aware canonical adapter shared with the
    # other Ganymède audit CLI; a mapId=0 is not a location.
    adapter = GuideUltimeRouteAdapter(
        catalog, SimpleNamespace(quest_ids=quest_ids), raw_data_dir=raw_data_dir,
    )
    # A missing local Doduda snapshot is a hard failure, not a zero-match
    # success report. Do not replace it with guesses from source text.
    if not adapter.raw_quests or not adapter.raw_maps:
        raise FileNotFoundError("Canonical Doduda quest/map snapshot unavailable")
    route = adapter.build()
    map_ids = (
        action.location.map_id for action in route.actions
        if action.kind == "start" and type(action.location.map_id) is int
        and action.location.map_id > 0
    )
    maps = canonical_map_positions_from_doduda(adapter.raw_maps, map_ids)
    reviews = {
        guide: review_ganymede_start_correspondences(
            guides_dir, guide, ("character:1",), route.actions, maps,
        )
        for guide in selected
    }
    return {
        "schema_version": 1,
        "status": "REVIEW_ONLY_NO_AUTOMATIC_TRAVEL",
        "raw_data_source": str(raw_data_dir),
        "guide_count": len(reviews),
        "quest_start_id_count": len(quest_ids),
        "corroborated_count": sum(
            review["corroborated_count"] for review in reviews.values()
        ),
        "requires_review_count": sum(
            review["requires_review_count"] for review in reviews.values()
        ),
        "ready_for_automatic_travel": False,
        "runtime_verified_travel_plans": {},
        "guides": reviews,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guide", action="append", dest="guides")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = build_review_report(
        guide_ids=tuple(args.guides) if args.guides else None,
    )
    data = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(data, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data, encoding="utf-8")
        print(f"Report written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
