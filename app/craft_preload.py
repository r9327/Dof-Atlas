from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from app.constants import DATA_DIR


def build_compact_craft_preload() -> dict[str, object]:
    """Validate the Craft disk store without retaining runtime metadata in Atlas."""

    payload: dict[str, object] = {
        "items": [],
        "items_by_name": {},
        "_prepared": True,
        "_lazy_items": True,
        "errors": [],
    }

    database_path = DATA_DIR / "local" / "dofus_data.sqlite"
    if not database_path.exists():
        payload["_skipped_reason"] = "catalogue Craft local absent"
        return payload

    try:
        connection = sqlite3.connect(database_path)
        try:
            has_items = (
                connection.execute("SELECT 1 FROM items LIMIT 1").fetchone()
                is not None
            )
        finally:
            connection.close()
    except sqlite3.Error as exc:
        payload["errors"].append(str(exc))
        return payload

    if not has_items:
        payload["_skipped_reason"] = "catalogue Craft local vide"
        return payload

    # Jobs, leveling guides, selection and lookup rows are intentionally omitted.
    # Craft reads those compact sources when the page is actually opened, so the
    # functional preload cannot pin reconstructible dictionaries in the parent.
    payload["_catalogue_ready"] = True
    return payload


def main() -> int:
    payload = json.dumps(
        build_compact_craft_preload(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if "--result-file" in sys.argv:
        try:
            result_path = Path(sys.argv[sys.argv.index("--result-file") + 1])
        except (ValueError, IndexError):
            return 2
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
