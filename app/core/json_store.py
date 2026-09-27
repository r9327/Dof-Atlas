from __future__ import annotations

import copy
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from local_dofus_data.utils import save_json_atomic


LOGGER = logging.getLogger("dofus_atlas.persistence")
JsonValidator = Callable[[Any], str | None]


class InvalidPersistentJsonError(ValueError):
    """A persistent JSON document cannot safely be interpreted or rewritten."""

    def __init__(self, path: Path, reason: str, backup: Path | None) -> None:
        self.path = Path(path)
        self.reason = str(reason)
        self.backup = backup
        backup_text = str(backup) if backup is not None else "backup impossible"
        super().__init__(f"JSON persistant refusé: {self.path} ({self.reason}); {backup_text}")



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


def read_json_validated(
    path: Path,
    default: Any,
    validator: JsonValidator,
    *,
    logger: logging.Logger | None = None,
) -> Any:
    """Read a critical JSON document without authorizing a destructive fallback."""

    target = Path(path)
    if not target.exists():
        return copy.deepcopy(default)
    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _reject_persistent_json(target, f"lecture impossible: {exc}", logger) from exc
    reason = validator(payload)
    if reason is not None:
        raise _reject_persistent_json(target, reason, logger)
    return payload


def _reject_persistent_json(
    path: Path,
    reason: str,
    logger: logging.Logger | None,
) -> InvalidPersistentJsonError:
    backup = backup_corrupt_json(path)
    active_logger = logger or LOGGER
    active_logger.error(
        "JSON persistant refusé: path=%s backup=%s reason=%s",
        path,
        backup or "<backup impossible>",
        reason,
    )
    return InvalidPersistentJsonError(path, reason, backup)


def _same_path(left: Path, right: Path) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:
        return Path(left).absolute() == Path(right).absolute()


def _is_shared_profile_path(path: Path) -> bool:
    # Local import avoids making the low-level JSON module depend on application
    # constants during module initialization. PROFILE_FILE is a protected shared
    # document: only ProfileSettingsService may perform its final replacement.
    from app.constants import PROFILE_FILE

    return _same_path(Path(path), Path(PROFILE_FILE))


def _write_json_atomic_unchecked(path: Path, payload: Any) -> None:
    """Low-level atomic replacement reserved for coordinated persistence services."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    save_json_atomic(target, payload)


def write_json_atomic(path: Path, payload: Any) -> None:
    target = Path(path)
    if _is_shared_profile_path(target):
        raise RuntimeError(
            "PROFILE_FILE is shared state; write through ProfileSettingsService"
        )
    _write_json_atomic_unchecked(target, payload)


def backup_corrupt_json(path: Path) -> Path | None:
    target = Path(path)
    if not target.exists():
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = target.with_suffix(target.suffix + f".corrupt.{timestamp}.bak")
    try:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
    except OSError:
        return None
    return backup
