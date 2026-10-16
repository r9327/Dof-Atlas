"""Emit the startup acknowledgement after the Qt event loop becomes responsive."""
from __future__ import annotations

import os
from pathlib import Path


def announce_ready() -> None:
    """Called from the Qt event loop, after the main window is shown."""
    requested = os.environ.get("DOFUS_ATLAS_HEALTH_FILE", "")
    if not requested:
        return
    path = Path(requested)
    if path.suffix != ".ready" or not path.parent.is_dir():
        return
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
    except OSError:
        # A damaged launcher must not prevent the actual application starting.
        return
