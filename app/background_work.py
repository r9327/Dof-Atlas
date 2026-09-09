from __future__ import annotations

import ctypes
import os
from contextlib import contextmanager
from typing import Iterator


# Windows lowers CPU, memory and I/O scheduling priority for the current thread
# while it is in background mode. This is intentionally thread-scoped: Atlas'
# UI/network threads keep their normal responsiveness.
_THREAD_MODE_BACKGROUND_BEGIN = 0x00010000
_THREAD_MODE_BACKGROUND_END = 0x00020000


@contextmanager
def background_io_priority() -> Iterator[None]:
    """Run heavy reconstructible cache work without monopolising the PC."""

    enabled = False
    kernel32 = None
    handle = None
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetCurrentThread()
            enabled = bool(
                kernel32.SetThreadPriority(
                    handle,
                    _THREAD_MODE_BACKGROUND_BEGIN,
                )
            )
        except (AttributeError, OSError, TypeError, ValueError):
            enabled = False

    try:
        yield
    finally:
        if enabled and kernel32 is not None and handle is not None:
            try:
                kernel32.SetThreadPriority(
                    handle,
                    _THREAD_MODE_BACKGROUND_END,
                )
            except (AttributeError, OSError, TypeError, ValueError):
                pass


__all__ = ["background_io_priority"]
