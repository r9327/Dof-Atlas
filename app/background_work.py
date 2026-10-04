from __future__ import annotations

import ctypes
import logging
import os
from contextlib import contextmanager
from typing import Iterator


_LOGGER = logging.getLogger(__name__)


# A below-normal Windows thread priority keeps reconstructible cache work polite
# while still allowing the UI thread to promote an already-running preload when
# the user explicitly asks for that same resource. THREAD_MODE_BACKGROUND_* is
# not used here because Windows only allows ending that mode from the current
# thread, which would make an in-flight preload impossible to promote safely.
_THREAD_PRIORITY_BELOW_NORMAL = -1
_THREAD_PRIORITY_NORMAL = 0
_THREAD_PRIORITY_ERROR_RETURN = 0x7FFFFFFF
_THREAD_SET_INFORMATION = 0x0020


def _configure_kernel32(kernel32) -> None:
    from ctypes import wintypes

    kernel32.GetCurrentThread.argtypes = []
    kernel32.GetCurrentThread.restype = wintypes.HANDLE
    kernel32.GetThreadPriority.argtypes = [wintypes.HANDLE]
    kernel32.GetThreadPriority.restype = ctypes.c_int
    kernel32.SetThreadPriority.argtypes = [wintypes.HANDLE, ctypes.c_int]
    kernel32.SetThreadPriority.restype = wintypes.BOOL
    kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL


@contextmanager
def background_io_priority() -> Iterator[None]:
    """Run heavy reconstructible cache work below normal Windows CPU priority."""

    changed = False
    kernel32 = None
    handle = None
    previous_priority = _THREAD_PRIORITY_NORMAL
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            _configure_kernel32(kernel32)
            handle = kernel32.GetCurrentThread()
            current = int(kernel32.GetThreadPriority(handle))
            if current != _THREAD_PRIORITY_ERROR_RETURN:
                previous_priority = current
            changed = bool(
                kernel32.SetThreadPriority(
                    handle,
                    _THREAD_PRIORITY_BELOW_NORMAL,
                )
            )
        except (AttributeError, OSError, TypeError, ValueError):
            changed = False

    try:
        yield
    finally:
        if changed and kernel32 is not None and handle is not None:
            try:
                kernel32.SetThreadPriority(handle, previous_priority)
            except (AttributeError, OSError, TypeError, ValueError):
                _LOGGER.debug("Unable to restore Windows background thread priority.", exc_info=True)


def promote_background_thread(native_thread_id: int) -> bool:
    """Promote one in-flight Windows preload worker to normal user priority.

    The caller owns the native thread id captured by ``threading.get_native_id``.
    On non-Windows platforms the worker already runs with the platform default
    scheduler, so there is nothing to promote.
    """

    try:
        thread_id = int(native_thread_id)
    except (TypeError, ValueError, OverflowError):
        return False
    if thread_id <= 0 or os.name != "nt":
        return False

    kernel32 = None
    handle = None
    try:
        kernel32 = ctypes.windll.kernel32
        _configure_kernel32(kernel32)
        handle = kernel32.OpenThread(_THREAD_SET_INFORMATION, False, thread_id)
        if not handle:
            return False
        return bool(kernel32.SetThreadPriority(handle, _THREAD_PRIORITY_NORMAL))
    except (AttributeError, OSError, TypeError, ValueError):
        _LOGGER.debug("Unable to promote preload worker thread %s.", thread_id, exc_info=True)
        return False
    finally:
        if kernel32 is not None and handle:
            try:
                kernel32.CloseHandle(handle)
            except (AttributeError, OSError, TypeError, ValueError):
                _LOGGER.debug("Unable to close preload worker thread handle.", exc_info=True)


__all__ = ["background_io_priority", "promote_background_thread"]
