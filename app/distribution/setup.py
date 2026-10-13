"""Per-user Windows setup for the standalone DofusAtlas launcher.

The updater executable is installed independently from versioned app payloads.
No Python installation, administrator elevation or PowerShell policy change is
required for the desktop shortcut.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_LAUNCHER_NAME = "DofusAtlas.exe"
_SHORTCUT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
if ([string]::IsNullOrWhiteSpace($desktop) -or -not (Test-Path -LiteralPath $desktop)) {
    throw 'Windows Desktop folder is unavailable.'
}
$launcher = $env:DOFUS_ATLAS_SETUP_TARGET
if ([string]::IsNullOrWhiteSpace($launcher) -or -not (Test-Path -LiteralPath $launcher)) {
    throw 'The installed Atlas launcher is missing.'
}
$shortcutPath = Join-Path $desktop 'Dofus Atlas.lnk'
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($shortcutPath)
$link.TargetPath = $launcher
$link.WorkingDirectory = Split-Path -Parent $launcher
$link.Description = 'Dofus Atlas - mise a jour et lancement automatique'
$link.IconLocation = "$launcher,0"
$link.Save()
"""


def embedded_launcher() -> Path:
    """Find the launcher contained in the PyInstaller setup image."""
    packed = getattr(sys, "_MEIPASS", None)
    root = Path(packed) if packed else Path(__file__).resolve().parents[2]
    result = root / _LAUNCHER_NAME
    if not result.is_file():
        raise FileNotFoundError("Installer incomplete : DofusAtlas.exe introuvable")
    return result


def user_programs_directory() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA unavailable; cannot install Atlas safely")
    return Path(local) / "Programs" / "DofusAtlas"


def _create_shortcut(target: Path) -> None:
    env = os.environ.copy()
    env["DOFUS_ATLAS_SETUP_TARGET"] = str(target)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _SHORTCUT_SCRIPT],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
        timeout=30, creationflags=flags, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Creation du raccourci impossible : " + result.stderr.strip()[:500]
        )


def install_launcher(source: Path, install_root: Path | None = None) -> Path:
    """Copy launcher atomically and create exactly one Desktop shortcut.

    Reinstallation never modifies user profiles or versioned AtlasApp payloads.
    An in-use launcher cannot be replaced on Windows and is left untouched.
    """
    if not source.is_file() or source.is_symlink():
        raise ValueError("Invalid setup launcher")
    with source.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError("Launcher is not a Windows executable")
    root = install_root or user_programs_directory()
    root.mkdir(parents=True, exist_ok=True)
    target = root / _LAUNCHER_NAME
    fd, tmp_name = tempfile.mkstemp(prefix=".atlas-launcher-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "wb") as dest, source.open("rb") as current:
            shutil.copyfileobj(current, dest, 1024 * 1024)
            dest.flush()
            os.fsync(dest.fileno())
        try:
            os.replace(tmp_name, target)
        except PermissionError as exc:
            raise RuntimeError("Fermez Dofus Atlas avant de mettre a jour le lanceur") from exc
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    _create_shortcut(target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Installer Dofus Atlas sans Python")
    parser.add_argument("--no-launch", action="store_true",
                        help="Installer le raccourci sans demarrer l'application")
    args = parser.parse_args(argv)
    try:
        if os.name != "nt":
            raise RuntimeError("Dofus Atlas Setup fonctionne uniquement sur Windows")
        launcher = install_launcher(embedded_launcher())
        if not args.no_launch:
            subprocess.Popen([str(launcher)], cwd=str(launcher.parent),
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Installation Atlas impossible : {exc}", file=sys.stderr)
        if os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, str(exc), "Installation Dofus Atlas", 0x10
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
