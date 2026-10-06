from __future__ import annotations

import json
import sys

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
    ("rows", "item_types.json", "", False),
    ("rows", "spells.json", "", False),
    ("rows", "titles.json", "", False),
    ("rows", "emoticons.json", "", False),
    ("rows", "ornaments.json", "", False),
    ("rows", "alterations.json", "", False),
)

_CACHE_ROOT = ROOT_DIR / ".cache" / "dofus_atlas" / "achievement_sources_v1"
_ACHIEVEMENT_NAMES_FILE = _CACHE_ROOT / "achievement_names.json"


def warm_achievement_source_indexes() -> int:
    """Build durable byte-offset indexes in this disposable process."""

    sources = QuestSources(_CACHE_ROOT)
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


def achievement_name_index() -> dict[int, str]:
    """Return only id/name pairs without materializing the rich Success runtime."""

    sources = QuestSources(_CACHE_ROOT)
    try:
        entries = sources.mapping(
            RAW_QUEST_DATA_DIR / "languages" / "fr.json",
            "entries",
            required=True,
        )
        achievements = sources.rows(RAW_QUEST_DATA_DIR / "achievements.json")
        names: dict[int, str] = {}
        for achievement_id in achievements:
            row = achievements[achievement_id]
            name_id = row.get("nameId") if isinstance(row, dict) else None
            value = ""
            if name_id is not None:
                try:
                    value = str(entries[str(name_id)] or "")
                except KeyError:
                    try:
                        value = str(entries[int(name_id)] or "")
                    except (KeyError, TypeError, ValueError):
                        value = ""
            names[int(achievement_id)] = value or f"Succès {achievement_id}"
        return names
    finally:
        sources.close()



def write_achievement_name_index() -> int:
    """Persist the small id/name map consumed by Guide workers at runtime."""

    names = achievement_name_index()
    _ACHIEVEMENT_NAMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = _ACHIEVEMENT_NAMES_FILE.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(names, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(_ACHIEVEMENT_NAMES_FILE)
    return len(names)


def main() -> int:
    if "--names" in sys.argv:
        print(json.dumps(achievement_name_index(), ensure_ascii=False, separators=(",", ":")))
        return 0
    count = warm_achievement_source_indexes()
    name_count = write_achievement_name_index()
    print(
        json.dumps(
            {
                "warmed_source_count": count,
                "achievement_name_count": name_count,
            }
        )
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
