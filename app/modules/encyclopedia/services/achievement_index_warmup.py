from __future__ import annotations

import json

from app.constants import RAW_QUEST_DATA_DIR, ROOT_DIR
from app.quest_source_index import QuestSources


_SOURCE_SPECS = (
    ("mapping", "languages/fr.json", "entries", True),
    ("rows", "achievements.json", "", True),
    ("rows", "achievement_categories.json", "", True),
    ("rows", "achievement_objectives.json", "", True),
    ("rows", "quests.json", "", True),
    ("rows", "monsters.json", "", True),
    ("rows", "dungeons.json", "", True),
    ("rows", "achievement_rewards.json", "", False),
    ("rows", "items.json", "", False),
    ("rows", "spells.json", "", False),
    ("rows", "titles.json", "", False),
    ("rows", "emoticons.json", "", False),
    ("rows", "ornaments.json", "", False),
    ("rows", "alterations.json", "", False),
)


def warm_achievement_source_indexes() -> int:
    """Build durable byte-offset indexes in this disposable process."""

    sources = QuestSources(
        ROOT_DIR / ".cache" / "dofus_atlas" / "achievement_sources_v1"
    )
    try:
        count = 0
        for kind, relative_path, field, required in _SOURCE_SPECS:
            path = RAW_QUEST_DATA_DIR / relative_path
            if not required and not path.is_file():
                continue
            mapping = (
                sources.mapping(path, field, required=required)
                if kind == "mapping"
                else sources.rows(path)
            )
            len(mapping)
            count += 1
        return count
    finally:
        sources.close()


def main() -> int:
    count = warm_achievement_source_indexes()
    print(json.dumps({"warmed_source_count": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
