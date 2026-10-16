"""Verify and stage optional launcher upgrades without writing a running executable."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path
from typing import Callable

from .manifest import verify_file, ReleaseFile
from .release_client import RemoteRelease, UpdateError, _open

_MAX_LAUNCHER_BYTES = 128 * 1024**2


def stage_launcher(release: RemoteRelease, downloads: Path,
                   progress: Callable[[int, int], None] | None = None) -> Path | None:
    """Return a SHA-256 checked standalone executable, or None for legacy releases."""
    manifest = release.manifest
    if not release.launcher_url or not manifest.launcher_sha256 or not manifest.launcher_size:
        return None
    if not 0 < manifest.launcher_size <= _MAX_LAUNCHER_BYTES:
        raise UpdateError("Launcher exceeds safe download limit")
    downloads.mkdir(parents=True, exist_ok=True)
    entry = ReleaseFile("DofusAtlas.exe", manifest.launcher_size, manifest.launcher_sha256)
    target = downloads / (manifest.launcher_sha256 + ".exe")
    if verify_file(target, entry):
        return target
    target.unlink(missing_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".atlas-launcher-", suffix=".part", dir=downloads)
    try:
        with os.fdopen(fd, "wb") as output, _open(release.launcher_url) as response:
            count = 0
            digest = hashlib.sha256()
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                count += len(block)
                if count > manifest.launcher_size:
                    raise UpdateError("Oversized launcher response")
                output.write(block)
                digest.update(block)
                if progress:
                    progress(count, manifest.launcher_size)
            output.flush()
            os.fsync(output.fileno())
        if count != manifest.launcher_size or digest.hexdigest() != manifest.launcher_sha256:
            raise UpdateError("Launcher SHA-256 verification failed")
        with open(tmp, "rb") as check:
            if check.read(2) != b"MZ":
                raise UpdateError("Launcher is not a Windows executable")
        os.replace(tmp, target)
        return target
    except (OSError, urllib.error.URLError) as exc:
        raise UpdateError("Launcher download interrupted") from exc
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def schedule_launcher_upgrade(release: RemoteRelease, downloads: Path,
                              report: Callable[[str, int], None]) -> bool:
    """Run the separately installed maintenance helper after this launcher exits."""
    if not getattr(sys, "frozen", False) or os.name != "nt":
        return False
    local = os.environ.get("LOCALAPPDATA")
    if not local or not release.launcher_url or not release.manifest.launcher_sha256:
        return False
    installed = Path(local) / "Programs" / "DofusAtlas"
    target = installed / "DofusAtlas.exe"
    helper = installed / "DofusAtlasMaintenance.exe"
    if (not target.is_file() or target.is_symlink() or not helper.is_file()
            or helper.is_symlink() or Path(sys.executable).resolve() != target.resolve()):
        return False
    with target.open("rb") as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() == release.manifest.launcher_sha256:
        return False
    report("Mise a jour du lanceur...", 98)
    candidate = stage_launcher(
        release, downloads,
        lambda done, total: report(
            "Telechargement du lanceur...", 98 + int(done / total) if total else 98,
        ),
    )
    if candidate is None:
        return False
    subprocess.Popen(
        [str(helper), "--finish-upgrade", "--candidate", str(candidate),
         "--sha256", release.manifest.launcher_sha256,
         "--parent-pid", str(os.getpid())],
        cwd=str(installed), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return True
