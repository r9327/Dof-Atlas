"""Precompute global Guide rewards during the certified Windows build.

This path never executes during installation, launcher startup or a user click.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build(*, output: Path, source_sha: str) -> dict[str, int]:
    from app.modules.encyclopedia.providers.guide_provider import GuideProvider
    from app.modules.encyclopedia.providers.quest_provider import QuestProvider
    from app.modules.encyclopedia.services.guide_prebuilt_rewards import (
        write_bundle,
    )

    quests = QuestProvider()
    guides = GuideProvider(quest_provider=quests)
    # A source build may have partial/draft Guides. Only ship the exact
    # published catalogue entries; the runtime validates each Guide file.
    result = write_bundle(
        guides.load_all(), quests.get_catalog(), guides.achievement_provider,
        output, source_sha=source_sha,
    )
    if result["guides"] < 20:
        raise RuntimeError("Guide reward index is incomplete")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build canonical Guide reward index")
    parser.add_argument("--output", type=Path, default=Path("data/bootstrap/guide_rewards_v1.json"))
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
    result = build(output=args.output, source_sha=args.source_sha)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
