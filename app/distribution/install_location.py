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


def has_saved_location() -> bool:
    """Was the install location explicitly selected or confirmed?"""
    return _SETTINGS.is_file()


def relocate_runtime(target: Path, progress=None) -> Path:
    """Switch the payload drive without downloading again.

    Copy into a temporary sibling, validate the active executable, then
    switch installation.json atomically. Keep the previous runtime as a
    recovery copy; it can be deleted once the new installation is confirmed.
    """
    import shutil
    from .install import active_executable, read_state

    destination = _valid_root(target)
    source = _valid_root(runtime_root())
    if destination == source:
        return source
    if source in destination.parents or destination in source.parents:
        raise UpdateError("Choisissez un dossier en dehors de l'installation actuelle")
    if destination.exists():
        raise UpdateError("Le dossier de destination existe deja; choisissez un dossier vide")

    state = read_state(source)
    if not state.get("active"):
        # First installation: no multi-gigabyte payload to migrate.
        return set_runtime_root(destination)
    if active_executable(source) is None:
        raise UpdateError("Installation existante incomplete; reparation necessaire")

    total = 0
    for base, directories, names in os.walk(source, followlinks=False):
        where = Path(base)
        directories[:] = [name for name in directories
                          if not (where == source and name == ".health")]
        if any((where / name).is_symlink() for name in directories):
            raise UpdateError("Impossible de deplacer une installation contenant des liens")
        for name in names:
            if where == source and name == ".launcher.lock":
                continue
            entry = where / name
            if entry.is_symlink():
                raise UpdateError("Impossible de deplacer une installation contenant des liens")
            total += entry.stat().st_size
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(destination.parent).free < total + 256 * 1024**2:
        raise UpdateError("Espace insuffisant sur le disque choisi pour copier Atlas")

    stage = Path(tempfile.mkdtemp(prefix=".atlas-move-", dir=destination.parent))
    copied = 0

    def ignore(directory, names):
        if Path(directory) == source:
            return {name for name in names if name in (".health", ".launcher.lock")}
        return set()

    def copy_checked(src, dst):
        nonlocal copied
        shutil.copy2(src, dst)
        size = Path(src).stat().st_size
        if Path(dst).stat().st_size != size:
            raise UpdateError("Copie Atlas incomplete; ancien disque preserve")
        copied += size
        if progress:
            progress(copied, max(total, 1))

    try:
        shutil.copytree(source, stage, dirs_exist_ok=True, symlinks=True,
                        ignore=ignore, copy_function=copy_checked)
        if read_state(stage) != state or active_executable(stage) is None:
            raise UpdateError("La copie Atlas n'a pas pu etre validee")
        os.replace(stage, destination)
        try:
            set_runtime_root(destination)
        except Exception:
            os.replace(destination, stage)
            raise
        return destination
    finally:
        if stage.exists():
            shutil.rmtree(stage)
