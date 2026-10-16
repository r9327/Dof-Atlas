"""Small Tkinter updater: only the single launcher is visible to users."""
from __future__ import annotations

import logging
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .install import (
    active_executable, install_release, mark_healthy, read_state, rollback_pending, slot_path,
)
from .release_client import UpdateError, download_archive, latest_release
from .disk_space import ensure_space
from .user_data import prepare_user_data
from .self_update import schedule_launcher_upgrade
from .install_location import runtime_root, set_runtime_root
from .manifest import verify_file

APP_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "DofusAtlas"
ROOT = runtime_root()
USER_DIR = APP_DIR / "user"
LOG_DIR = APP_DIR / "logs"


def _logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("dofus_atlas_updater")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(LOG_DIR / "updater.log", maxBytes=1_000_000,
                                      backupCount=2, encoding="utf-8")
        logger.addHandler(handler)
    return logger


def _run_lock():
    """Prevent concurrent install state changes from multiple launchers."""
    ROOT.mkdir(parents=True, exist_ok=True)
    handle = (ROOT / ".launcher.lock").open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        handle.close()
        raise UpdateError("Dofus Atlas est deja en cours de lancement") from exc
    return handle


def _launch_with_health(executable: Path, report, *, settle_seconds: float = 0) -> bool:
    USER_DIR.mkdir(parents=True, exist_ok=True)
    install_state = read_state(ROOT)
    previous = install_state.get("previous") if install_state.get("pending") else None
    previous_root = (slot_path(ROOT, previous) / "AtlasApp" / "_internal"
                     if previous else None)
    prepare_user_data(executable, USER_DIR,
                      legacy_root=Path(sys.executable).resolve().parent,
                      previous_install_root=previous_root)
    health_dir = ROOT / ".health"
    health_dir.mkdir(parents=True, exist_ok=True)
    ready = health_dir / (uuid.uuid4().hex + ".ready")
    env = os.environ.copy()
    env["DOFUS_ATLAS_HEALTH_FILE"] = str(ready)
    env["DOFUS_ATLAS_USER_ROOT"] = str(USER_DIR)
    report("Lancement de Dofus Atlas...", 98)
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen([str(executable)], cwd=str(executable.parent),
                                env=env, creationflags=flags)
        for _ in range(500):  # 50 seconds maximum, checked without blocking Tk
            if ready.is_file():
                ready.unlink(missing_ok=True)
                if settle_seconds > 0:
                    # A window that appears and crashes immediately must not
                    # certify an update. Wait only on a new, pending version.
                    deadline = time.monotonic() + settle_seconds
                    while time.monotonic() < deadline:
                        if proc.poll() is not None:
                            return False
                        time.sleep(0.1)
                return proc.poll() is None
            if proc.poll() is not None:
                return False
            time.sleep(0.1)
        return False
    finally:
        ready.unlink(missing_ok=True)


def run_update(report) -> None:
    log = _logger()
    _run_handle = _run_lock()
    try:
        # An interrupted first boot should never strand the user on the new version.
        if read_state(ROOT).get("pending"):
            rollback_pending(ROOT)
            report("Version precedente restauree", 3)
        prior = read_state(ROOT)
        remote = None
        update_failure: UpdateError | OSError | None = None
        try:
            report("Verification des mises a jour...", 5)
            remote = latest_release()
            try:
                current_exe = active_executable(ROOT)
            except UpdateError:
                current_exe = None
            if current_exe is not None and prior.get("source_sha") == remote.manifest.source_sha:
                report("Verification de l'installation...", 7)
                installed = slot_path(ROOT, prior["active"])
                if any(not verify_file(installed / entry.path, entry)
                       for entry in remote.manifest.files):
                    current_exe = None
                    report("Installation endommagee — reparation...", 9)
            if prior.get("blocked_source_sha") == remote.manifest.source_sha:
                report("Mise a jour en attente de correction", 10)
            elif prior.get("source_sha") != remote.manifest.source_sha or current_exe is None:
                delta_installed = False
                can_delta = (
                    remote.manifest.delta is not None
                    and remote.delta_url is not None
                    and prior.get("source_sha") == remote.manifest.delta.base_source_sha
                    and not prior.get("pending")
                )
                if can_delta:
                    report("Telechargement des fichiers modifies...", 10)
                    archive = None
                    try:
                        archive = download_archive(
                            remote, ROOT / "downloads",
                            lambda done, total: report(
                                f"Differentiel : {int(done * 100 / total)} %",
                                10 + int(done * 65 / total),
                            ),
                            differential=True,
                        )
                        report("Verification des fichiers existants...", 76)
                        delta_installed = install_release(
                            ROOT, archive, remote.manifest,
                            lambda done, total: report(
                                "Installation differentielle...",
                                76 + int(done * 20 / max(total, 1)),
                            ),
                            delta=True,
                        )
                    except (UpdateError, OSError) as exc:
                        log.warning("Differential update failed, using full release: %s", exc)
                        if archive is not None:
                            archive.unlink(missing_ok=True)
                if not delta_installed:
                    ensure_space(remote.manifest, ROOT, archive_size=remote.archive_size)
                    report("Telechargement complet de la nouvelle version...", 10)
                    archive = download_archive(
                        remote, ROOT / "downloads",
                        lambda done, total: report(
                            f"Telechargement : {int(done * 100 / total)} %",
                            10 + int(done * 65 / total),
                        ),
                    )
                    report("Verification et installation...", 76)
                    try:
                        install_release(
                            ROOT, archive, remote.manifest,
                            lambda done, total: report(
                                "Verification des fichiers...",
                                76 + int(done * 20 / max(total, 1)),
                            ),
                        )
                    except UpdateError:
                        archive.unlink(missing_ok=True)
                        raise
                report("Mise a jour installee", 96)
            else:
                report("Atlas est a jour", 96)
        except (UpdateError, OSError) as exc:
            update_failure = exc
            log.warning("Update unavailable, trying last installed version: %s", exc, exc_info=True)
            if active_executable(ROOT) is not None:
                report("Mise a jour indisponible — mode hors ligne", 90)
        executable = active_executable(ROOT)
        if executable is None:
            if update_failure is not None:
                raise UpdateError(
                    f"Premiere installation impossible : {update_failure}"
                ) from update_failure
            raise UpdateError("Premiere installation impossible : aucune version disponible")
        was_pending = read_state(ROOT)["pending"]
        if not _launch_with_health(executable, report,
                                   settle_seconds=2.0 if was_pending else 0):
            if was_pending and rollback_pending(ROOT):
                report("Demarrage echoue — restauration precedente", 95)
                previous = active_executable(ROOT)
                if previous is not None and _launch_with_health(previous, report):
                    report("Version precedente demarree", 100)
                    return
            raise UpdateError("Atlas n'a pas confirme son demarrage")
        if was_pending:
            mark_healthy(ROOT)
        # Never upgrade the bootstrap to a release whose AtlasApp did not
        # successfully activate; offline/rollback must keep the old launcher.
        if remote is not None and read_state(ROOT).get("source_sha") == remote.manifest.source_sha:
            try:
                schedule_launcher_upgrade(remote, ROOT / "downloads", report)
            except (UpdateError, OSError, ValueError) as exc:
                log.warning("Launcher upgrade deferred: %s", exc)
        report("Dofus Atlas est pret", 100)
    finally:
        _run_handle.close()


def main() -> int:
    # Fast, offline bootstrap self-test used by the detached maintenance helper.
    # Do not open Tk, contact GitHub or launch AtlasApp during this health check.
    if sys.argv[1:2] == ["--atlas-self-test"]:
        return 0
    events: queue.Queue[tuple[str, int | str]] = queue.Queue()
    try:
        import tkinter as tk
        from tkinter import ttk
        window = tk.Tk()
    except Exception:
        # A broken/missing Tk UI must not prevent access to an already installed Atlas.
        try:
            run_update(lambda label, percentage: print(f"{percentage}% {label}", flush=True))
            return 0
        except (UpdateError, OSError) as exc:
            print(f"Dofus Atlas : {exc}", file=sys.stderr)
            return 1

    window.title("Dofus Atlas — Mise a jour")
    choosing_install = not read_state(ROOT).get("active") and "--atlas-auto-install" not in sys.argv
    window.geometry("590x370" if choosing_install else "510x260")
    window.resizable(False, False)
    window.configure(bg="#101826")
    try:
        window.eval("tk::PlaceWindow . center")
    except tk.TclError:
        pass
    tk.Label(window, text="DOFUS ATLAS", bg="#101826", fg="#eaf3ff",
             font=("Segoe UI", 23, "bold")).pack(pady=(24, 4))
    tk.Label(window, text="Lancement et mises a jour automatiques",
             bg="#101826", fg="#8fa5bd", font=("Segoe UI", 10)).pack()
    start_button = None
    if choosing_install:
        selection = tk.Frame(window, bg="#101826")
        selection.pack(pady=(12, 2))
        tk.Label(selection, text="Dossier des fichiers Atlas (~3 Go)", bg="#101826",
                 fg="#d2deeb", font=("Segoe UI", 10)).pack()
        chosen = tk.StringVar(value=str(ROOT))
        tk.Label(selection, textvariable=chosen, bg="#101826",
                 fg="#8fa5bd", font=("Segoe UI", 9), wraplength=545).pack()

        def choose_install_folder():
            global ROOT
            from tkinter import filedialog, messagebox
            folder = filedialog.askdirectory(parent=window, title="Choisir le disque / dossier Atlas",
                                             initialdir=str(ROOT.parent))
            if not folder:
                return
            target = Path(folder) / "DofusAtlas" / "runtime"
            try:
                if read_state(target).get("active"):
                    raise UpdateError("Ce dossier contient deja une installation Atlas")
                ROOT = set_runtime_root(target)
                chosen.set(str(ROOT))
            except (OSError, UpdateError) as exc:
                messagebox.showerror("Emplacement Atlas", str(exc), parent=window)

        tk.Button(selection, text="Changer de dossier...", command=choose_install_folder).pack(pady=5)
    status = tk.StringVar(value="Choisissez le dossier puis lancez l'installation."
                          if choosing_install else "Initialisation...")
    tk.Label(window, textvariable=status, bg="#101826", fg="#d2deeb",
             font=("Segoe UI", 10), wraplength=475, justify="center").pack(pady=(19, 7))
    style = ttk.Style(window)
    style.theme_use("clam")
    style.configure("Atlas.Horizontal.TProgressbar", troughcolor="#27364b",
                    background="#23c4db", borderwidth=0, thickness=15)
    percent = tk.IntVar(value=0)
    bar = ttk.Progressbar(window, orient="horizontal", mode="determinate", maximum=100,
                          variable=percent, style="Atlas.Horizontal.TProgressbar",
                          length=430)
    bar.pack(pady=(0, 6))
    numeric = tk.StringVar(value="0 %")
    tk.Label(window, textvariable=numeric, bg="#101826", fg="#8fa5bd",
             font=("Segoe UI", 9)).pack()
    finished = False

    def report(message: str, value: int):
        events.put(("progress", (message, value)))

    def worker():
        try:
            run_update(report)
            events.put(("done", 0))
        except Exception as exc:
            _logger().exception("Updater failed")
            events.put(("error", str(exc)))

    def poll():
        nonlocal finished
        try:
            while True:
                kind, payload = events.get_nowait()
                if kind == "progress":
                    message, value = payload
                    status.set(message)
                    percent.set(max(0, min(100, value)))
                    numeric.set(f"{percent.get()} %")
                elif kind == "done":
                    finished = True
                    window.after(550, window.destroy)
                elif kind == "error":
                    finished = True
                    status.set("Echec : " + str(payload))
                    numeric.set("Journal : DofusAtlas/logs/updater.log")
        except queue.Empty:
            pass
        if not finished:
            window.after(70, poll)

    if choosing_install:
        def begin_install():
            start_button.configure(state="disabled")
            status.set("Installation en cours...")
            threading.Thread(target=worker, name="atlas-updater", daemon=True).start()
        start_button = tk.Button(window, text="Installer et lancer", command=begin_install)
        start_button.pack(pady=(2, 4))
    else:
        threading.Thread(target=worker, name="atlas-updater", daemon=True).start()
    window.after(70, poll)
    window.mainloop()
    return 0 if percent.get() == 100 else 1


if __name__ == "__main__":
    raise SystemExit(main())
