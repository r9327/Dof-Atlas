"""Emit separate acknowledgements for a live Qt loop and a painted Home."""
from __future__ import annotations

import os
from pathlib import Path


def _write_marker(path: Path) -> None:
    if not path.parent.is_dir():
        return
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
    except OSError:
        # A damaged launcher must not prevent the actual application starting.
        return


def announce_ready() -> None:
    """Acknowledge that the Qt event loop is alive (not that Home is usable)."""
    requested = os.environ.get("DOFUS_ATLAS_HEALTH_FILE", "")
    if not requested:
        return
    path = Path(requested)
    if path.suffix != ".ready" or not path.parent.is_dir():
        return
    home = os.environ.get("DOFUS_ATLAS_HOME_HEALTH_FILE", "")
    if home:
        home_path = Path(home)
        if home_path.suffix == ".home" and home_path.parent == path.parent:
            # Publish capability BEFORE the legacy ACK, so a new launcher can
            # reliably distinguish this process from an older installed app.
            _write_marker(home_path.with_suffix(".capable"))
    _write_marker(path)


def announce_home_ready() -> None:
    """Acknowledge Home only after a paint plus a subsequent Qt event-loop turn."""
    requested = os.environ.get("DOFUS_ATLAS_HOME_HEALTH_FILE", "")
    if not requested:
        return
    path = Path(requested)
    if path.suffix != ".home" or not path.parent.is_dir():
        return
    _write_marker(path)
