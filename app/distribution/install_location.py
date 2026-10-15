"""Persist the large Atlas runtime location separately from user profiles and launcher.

The small standalone launcher and durable user data remain under LocalAppData.
Only the multi-gigabyte, versioned, replaceable payload is user-selectable.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .release_client import UpdateError

APP_DATA = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "DofusAtlas"
DEFAULT_RUNTIME = APP_DATA / "runtime"
_SETTINGS = APP_DATA / "installation.json"


def _valid_root(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise UpdateError("Le dossier d'installation doit etre un chemin absolu")
    if os.name == "nt" and (path.drive.startswith("\\\\") or str(path).startswith("\\\\")):
        raise UpdateError("Un dossier reseau n'est pas accepte pour Atlas")
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise UpdateError("Un lien symbolique n'est pas accepte pour le dossier Atlas")
    path = path.resolve()
    if path == Path(path.anchor) or (path.exists() and not path.is_dir()):
        raise UpdateError("Dossier d'installation invalide")
    return path


def runtime_root() -> Path:
    if not _SETTINGS.exists():
        return DEFAULT_RUNTIME
    try:
        data = json.loads(_SETTINGS.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema_version") != 1:
            raise ValueError("Unexpected install location schema")
        return _valid_root(data["runtime_root"])
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise UpdateError("Emplacement Atlas enregistre invalide; corrigez installation.json") from exc


def set_runtime_root(root: Path) -> Path:
    location = _valid_root(root)
    APP_DATA.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".atlas-location-", dir=APP_DATA)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump({"schema_version": 1, "runtime_root": str(location)}, out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, _SETTINGS)
    finally:
        Path(name).unlink(missing_ok=True)
    return location
