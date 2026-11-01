"""Create the portable Sylvestre route before PyInstaller bundles any assets.

This is a build-time operation, never a launcher/bootstrap/on-click job.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _build_service():
    from app.modules.encyclopedia.providers.guide_provider import GuideProvider
    from app.modules.encyclopedia.providers.quest_provider import QuestProvider
    from app.modules.encyclopedia.services.guide_catalog_manual_runtime_service import (
        GuideCatalogManualRuntimeService,
    )
    quest_provider = QuestProvider()
    guide = GuideProvider(quest_provider=quest_provider).get_by_id("dofus_sylvestre")
    if guide is None:
        raise RuntimeError("Canonical Sylvestre Guide is missing")
    service = object.__new__(GuideCatalogManualRuntimeService)
    service.guide_id = str(guide.id)
    service.guide_title = str(guide.title)
    service.catalog_guide = guide
    service.quest_provider = quest_provider
    service.use_disk_cache = False
    return service


def build(output: Path, source_sha: str) -> dict[str, object]:
    from app.modules.encyclopedia.services.guide_catalog_prebuilt_route import (
        publish_prebuilt_route,
    )
    service = _build_service()
    service._load_manual_preview()
    metadata = publish_prebuilt_route(service, output, source_sha=source_sha)
    verify(output)
    return metadata


def verify(output: Path) -> dict[str, int]:
    from app.modules.encyclopedia.services.guide_catalog_prebuilt_route import (
        restore_prebuilt_route,
    )
    from app.modules.encyclopedia.services.guide_catalog_route_store import load_detail
    service = _build_service()
    if not restore_prebuilt_route(service, directory=output):
        raise RuntimeError("Portable Sylvestre route rejected by runtime verification")
    if len(service.cards) < 1000:
        raise RuntimeError("Portable Sylvestre route is incomplete")
    for index in (0, len(service.cards) // 2, len(service.cards) - 1):
        detail = load_detail(service._catalog_detail_store_path, index)
        if not isinstance(detail.get("manual_lines"), list):
            raise RuntimeError(f"Portable route details missing at {index}")
    return {"cards": len(service.cards), "quests": len(service._common_quest_ids)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build certified Sylvestre portable SQLite")
    parser.add_argument("--output", type=Path, default=Path("data/bootstrap/guide_routes"))
    parser.add_argument("--source-sha", default="")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    if args.verify_only:
        result = verify(args.output)
    else:
        result = build(args.output, args.source_sha)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
