from __future__ import annotations

import copy
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from local_dofus_data.utils import save_json_atomic


LOGGER = logging.getLogger("dofus_atlas.persistence")


def read_json_resilient(path: Path, default: Any, *, logger: logging.Logger | None = None) -> Any:
    """Read JSON without silently turning corruption into fresh user state.

    Missing files legitimately return a copy of the supplied default. Existing
    unreadable/invalid files are preserved as a timestamped ``.corrupt`` backup
    and logged before falling back.
    """
    target = Path(path)
    if not target.exists():
        return copy.deepcopy(default)
    try:
        return json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        backup = backup_corrupt_json(target)
        active_logger = logger or LOGGER
        active_logger.error(
            "JSON invalide: path=%s backup=%s error=%s",
            target,
            backup or "<backup impossible>",
            exc,
        )
        return copy.deepcopy(default)


def write_json_atomic(path: Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    save_json_atomic(target, payload)


def backup_corrupt_json(path: Path) -> Path | None:
    target = Path(path)
    if not target.exists():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = target.with_suffix(target.suffix + f".corrupt.{timestamp}.bak")
    try:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
    except OSError:
        return None
    return backup
