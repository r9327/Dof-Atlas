from __future__ import annotations

import json

from app.constants import RAW_QUEST_DATA_DIR, ROOT_DIR
from app.quest_source_index import QuestSources


_SOURCE_SPECS = (
    ("mapping", "languages/fr.json", "entries"),
    ("rows", "achievements.json", ""),
    ("rows", "achievement_categories.json", ""),
    ("rows", "achievement_objectives.json", ""),
    ("rows", "quests.json", ""),
    ("rows", "monsters.json", ""),
    ("rows", "dungeons.json", ""),
)


def warm_achievement_source_indexes() -> int:
    """Build durable byte-offset indexes in this disposable process."""

    sources = QuestSources(
        ROOT_DIR / ".cache" / "dofus_atlas" / "achievement_sources_v1"
    )
    try:
        count = 0
        for kind, relative_path, field in _SOURCE_SPECS:
            path = RAW_QUEST_DATA_DIR / relative_path
            mapping = (
                sources.mapping(path, field, required=True)
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
