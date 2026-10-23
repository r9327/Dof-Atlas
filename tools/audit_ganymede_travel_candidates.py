"""Read-only CLI: compare signed Ganymède quest-starts with local Atlas maps.

Example: python -m tools.audit_ganymede_travel_candidates
             --guide-id dofus_cawotte --character-key character:12345

Results are review candidates, NEVER confirmed routes or game commands.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from app.constants import RAW_QUEST_DATA_DIR
from app.modules.encyclopedia.providers.guide_provider import GUIDES_DIR
from app.modules.encyclopedia.providers.quest_provider import QuestProvider
from app.modules.encyclopedia.services.guide_ganymede_continuous_plan import (
    canonical_map_positions_from_doduda,
)
from app.modules.encyclopedia.services.guide_ganymede_cutover import (
    select_verified_replacement_path,
)
from app.modules.encyclopedia.services.guide_ganymede_travel_review import (
    review_signed_ganymede_start_candidates,
    signed_source_start_ids,
)
from app.modules.encyclopedia.services.guide_ultime_route_adapter import (
    GuideUltimeRouteAdapter,
)


def signed_quest_start_ids(steps: list[dict]) -> tuple[int, ...]:
    """Extract exact source IDs for a read-only Atlas catalogue lookup."""
    return signed_source_start_ids(steps, strict=False)


def build_report(
    guides_dir: Path, atlas_guide_id: str, character_keys: tuple[str, ...],
    raw_data_dir: Path = RAW_QUEST_DATA_DIR,
) -> dict[str, object]:
    """Use the *existing* Atlas adapter; never construct movement plans."""
    signed = select_verified_replacement_path(
        guides_dir, {"id": atlas_guide_id, "category": "dofus"},
        allow_source_manual=True,
    )
    if signed is None:
        raise ValueError("Guide absent or Ganymède source signature invalid")
    source = json.loads(signed.read_text(encoding="utf-8"))
    # Full audits fail closed on malformed starts; only the standalone
    # compatibility preview helper may skip incomplete suggestions.
    ids = signed_source_start_ids(source["sections"][0]["steps"])
    provider = QuestProvider(data_dir=raw_data_dir)
    catalog = provider.get_catalog()
    adapter = GuideUltimeRouteAdapter(
        catalog, SimpleNamespace(quest_ids=ids), raw_data_dir=raw_data_dir,
    )
    if not adapter.raw_quests or not adapter.raw_maps:
        raise FileNotFoundError(
            "Canonical Doduda quest/map snapshot unavailable for review"
        )
    canonical = adapter.build()
    map_ids = tuple(
        action.location.map_id
        for action in canonical.actions
        if type(action.location.map_id) is int and action.location.map_id > 0
    )
    positions = canonical_map_positions_from_doduda(adapter.raw_maps, map_ids)
    report = review_signed_ganymede_start_candidates(
        guides_dir, atlas_guide_id, canonical.actions, positions, character_keys,
    )
    report["canonical_quest_starts_requested"] = len(ids)
    report["canonical_adapter_warning_count"] = len(canonical.warnings)
    report["canonical_maps_checked"] = len(positions)
    report["generated_commands"] = 0
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guide-id", required=True)
    parser.add_argument("--character-key", action="append", required=True)
    parser.add_argument("--guides-dir", type=Path, default=GUIDES_DIR)
    parser.add_argument("--raw-data-dir", type=Path, default=RAW_QUEST_DATA_DIR)
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional report output; otherwise print to stdout")
    args = parser.parse_args(argv)
    report = build_report(
        args.guides_dir, args.guide_id, tuple(args.character_key),
        args.raw_data_dir,
    )
    data = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(data, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(data, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
