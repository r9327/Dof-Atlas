"""Per-user Windows setup for the standalone DofusAtlas launcher.

The updater executable is installed independently from versioned app payloads.
No Python installation, administrator elevation or PowerShell policy change is
required for the desktop shortcut.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_LAUNCHER_NAME = "DofusAtlas.exe"
_MAINTENANCE_NAME = "DofusAtlasMaintenance.exe"
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


def choose_runtime_before_setup() -> None:
    """Let the user select the large AtlasApp drive before installing anything."""
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from .install_location import runtime_root, relocate_runtime

    window = tk.Tk()
    window.withdraw()
    try:
        current = runtime_root()
        if not messagebox.askyesno(
            "Dofus Atlas - emplacement",
            "Les fichiers du jeu (~3 Go) peuvent etre installes sur le disque "
            "de votre choix. Le petit lanceur reste dans AppData.\n\n"
            f"Emplacement actuel :\n{current}\n\n"
            "Choisir un autre disque ou dossier ?",
            parent=window,
        ):
            return
        folder = filedialog.askdirectory(
            parent=window, title="Choisir le disque ou dossier des fichiers Atlas",
            initialdir=str(current.parent if current.parent.exists() else Path.home()),
        )
        if not folder:
            return
        target = Path(folder) / "DofusAtlas" / "runtime"
        if target == current:
            return
        progress_window = tk.Toplevel(window)
        progress_window.title("Deplacement Dofus Atlas")
        progress_window.geometry("460x140")
        progress_window.resizable(False, False)
        tk.Label(progress_window, text="Preparation du disque choisi...").pack(pady=(14, 8))
        bar = ttk.Progressbar(progress_window, length=400, maximum=100)
        bar.pack(pady=4)
        note = tk.Label(progress_window, text="L'ancienne installation est preservee par securite.")
        note.pack(pady=6)
        progress_window.protocol("WM_DELETE_WINDOW", lambda: None)
        progress_window.update()

        def update_progress(done, total):
            bar["value"] = int(done * 100 / max(total, 1))
            progress_window.update()

        try:
            relocate_runtime(target, progress=update_progress)
        finally:
            progress_window.destroy()
    finally:
        window.destroy()


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



def install_maintenance_helper(source: Path, root: Path) -> Path:
    """Keep a detached setup helper for safe future launcher replacement."""
    if not source.is_file() or source.is_symlink():
        raise ValueError("Invalid maintenance executable")
    target = root / _MAINTENANCE_NAME
    fd, name = tempfile.mkstemp(prefix=".atlas-maintenance-", dir=root)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as stream:
            shutil.copyfileobj(stream, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, target)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return target


def _wait_for_parent(pid: int) -> None:
    """Wait for the original launcher by handle, avoiding PID reuse races."""
    if os.name != "nt" or pid < 1:
        raise RuntimeError("Invalid Windows parent process")
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    kernel.WaitForSingleObject.restype = ctypes.c_ulong
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_int
    handle = kernel.OpenProcess(0x00100000, 0, pid)
    if not handle:
        # A onefile maintenance helper starts slower than the exiting Tk
        # process. ERROR_INVALID_PARAMETER means the parent already exited.
        if ctypes.get_last_error() == 87:
            return
        raise RuntimeError("Cannot safely identify the launcher process")
    try:
        if kernel.WaitForSingleObject(handle, 60000) != 0:
            raise RuntimeError("Launcher did not exit before maintenance deadline")
    finally:
        kernel.CloseHandle(handle)


def _verify_launcher_starts(executable: Path) -> None:
    """Exercise the frozen bootstrap without starting the GUI or contacting GitHub."""
    try:
        result = subprocess.run(
            [str(executable), "--atlas-self-test"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=35, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("New Atlas launcher startup timed out") from exc
    if result.returncode != 0:
        raise RuntimeError("New Atlas launcher failed offline startup self-test")


def finish_launcher_upgrade(candidate: Path, digest: str, parent_pid: int,
                            root: Path | None = None) -> None:
    """Replace only our launcher after its process exits; restore on failure."""
    from .manifest import valid_sha

    valid_sha(digest)
    program = root if root is not None else user_programs_directory()
    target = program / _LAUNCHER_NAME
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA missing")
    from .install_location import runtime_root
    allowed = (runtime_root() / "downloads").resolve()
    if candidate.is_symlink() or not candidate.is_file() or not candidate.resolve().is_relative_to(allowed):
        raise ValueError("Upgrade source is outside verified updater cache")
    if target.is_symlink() or not target.is_file():
        raise ValueError("Installed launcher missing")

    def valid_binary(path: Path) -> bool:
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                return False
            stream.seek(0)
            check = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                check.update(block)
            return check.hexdigest() == digest

    if not valid_binary(candidate):
        raise ValueError("Unverified launcher candidate")
    _wait_for_parent(parent_pid)
    if not valid_binary(candidate):
        raise ValueError("Launcher changed while waiting")
    _verify_launcher_starts(candidate)
    backup = program / "DofusAtlas.exe.previous"
    if backup.exists() and (backup.is_symlink() or not backup.is_file()):
        raise ValueError("Unsafe launcher backup")
    # Preserve the old EXE first, then atomically replace the existing target.
    # A crash at any point leaves a launchable file at the shortcut target.
    fd, name = tempfile.mkstemp(prefix=".atlas-previous-", dir=program)
    try:
        with os.fdopen(fd, "wb") as output, target.open("rb") as source:
            shutil.copyfileobj(source, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.replace(name, backup)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    os.replace(candidate, target)
    try:
        _verify_launcher_starts(target)
    except (OSError, RuntimeError):
        # The desktop shortcut must always point to a working bootstrap.
        os.replace(backup, target)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Installer Dofus Atlas sans Python")
    parser.add_argument("--no-launch", action="store_true",
                        help="Installer le raccourci sans demarrer l'application")
    parser.add_argument("--legacy-root", type=Path,
                        help="Importer les donnees de l'ancien dossier DOFUS.bat")
    parser.add_argument("--finish-upgrade", action="store_true")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--parent-pid", type=int)
    args = parser.parse_args(argv)
    try:
        if os.name != "nt":
            raise RuntimeError("Dofus Atlas Setup fonctionne uniquement sur Windows")
        if args.finish_upgrade:
            if args.candidate is None or args.sha256 is None or args.parent_pid is None:
                raise ValueError("Incomplete maintenance request")
            finish_launcher_upgrade(args.candidate, args.sha256, args.parent_pid)
            return 0
        if not args.no_launch:
            choose_runtime_before_setup()
        launcher = install_launcher(embedded_launcher())
        install_maintenance_helper(Path(sys.executable), launcher.parent)
        legacy = args.legacy_root
        if legacy is None and (Path.cwd() / "DOFUS.bat").is_file():
            legacy = Path.cwd()
        if legacy is not None:
            if legacy.is_symlink() or not (legacy / "DOFUS.bat").is_file():
                raise ValueError("Ancien dossier Atlas invalide : DOFUS.bat absent")
            from .user_data import prepare_user_data
            local = Path(os.environ["LOCALAPPDATA"])
            prepare_user_data(launcher, local / "DofusAtlas" / "user",
                              legacy_root=legacy.resolve())
        if not args.no_launch:
            subprocess.Popen([str(launcher)], cwd=str(launcher.parent),
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Installation Atlas impossible : {exc}", file=sys.stderr)
        # Automated --no-launch installs must fail via exit code, never a modal
        # dialog that can block the headless Windows release certification.
        if os.name == "nt" and not args.no_launch:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, str(exc), "Installation Dofus Atlas", 0x10
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
