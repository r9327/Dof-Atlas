from __future__ import annotations

import json

from app.constants import ROOT_DIR


_CACHE_ROOT = ROOT_DIR / ".cache" / "dofus_atlas" / "achievement_sources_v1"
_ACHIEVEMENT_NAMES_FILE = _CACHE_ROOT / "achievement_names.json"
_ACHIEVEMENT_COMPACT_CACHE = (
    ROOT_DIR / ".cache" / "dofus_atlas" / "achievement_catalogue_v1.jsonl"
)


def warm_achievement_source_indexes() -> int:
    """Compatibility hook: Phase 8 no longer pre-indexes monolithic sources."""

    return 0


def achievement_name_index() -> dict[int, str]:
    """Read id/name pairs from the already materialized compact Success store."""

    names: dict[int, str] = {}
    try:
        with _ACHIEVEMENT_COMPACT_CACHE.open("r", encoding="utf-8") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if not isinstance(row, dict) or row.get("kind") != "achievement":
                    continue
                value = row.get("value")
                if not isinstance(value, dict):
                    continue
                try:
                    achievement_id = int(value.get("id"))
                except (TypeError, ValueError):
                    continue
                names[achievement_id] = str(
                    value.get("name") or f"Succès {achievement_id}"
                )
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return names


def write_achievement_name_index() -> int:
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
