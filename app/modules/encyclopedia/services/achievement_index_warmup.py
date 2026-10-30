from __future__ import annotations

import json
import os
from uuid import uuid4
from time import sleep

from app.constants import ROOT_DIR
from app.core.cache_write_lock import exclusive_cache_write_lock


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


def _replace_name_index_with_windows_retry(
    temporary, destination, *, windows: bool | None = None
) -> None:
    """Retry only a genuine Windows sharing violation, not arbitrary errors.

    The cache is rebuildable and each writer uses a unique .tmp file. Windows
    may briefly deny replacement while another Atlas worker opens the name
    index. Never return success without a completed atomic replace.
    """
    is_windows = os.name == "nt" if windows is None else windows
    for attempt in range(10):
        try:
            temporary.replace(destination)
            return
        except PermissionError as exc:
            if not is_windows or getattr(exc, "winerror", None) != 32 or attempt == 9:
                raise
            sleep(0.025 * (attempt + 1))


def write_achievement_name_index() -> int:
    # Unique temp names prevent source collisions, but Windows also requires
    # serializing replacement of the *same destination* across Atlas workers.
    # Do not classify WinError 5 as transient: a real ACL denial must still fail.
    with exclusive_cache_write_lock(_ACHIEVEMENT_NAMES_FILE):
        names = achievement_name_index()
        temporary = _ACHIEVEMENT_NAMES_FILE.with_name(
            f".{_ACHIEVEMENT_NAMES_FILE.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        temporary.write_text(
            json.dumps(names, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        try:
            _replace_name_index_with_windows_retry(temporary, _ACHIEVEMENT_NAMES_FILE)
        finally:
            temporary.unlink(missing_ok=True)
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
