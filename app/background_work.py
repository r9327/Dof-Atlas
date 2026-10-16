from __future__ import annotations

import ctypes
import logging
import os
from contextlib import contextmanager
from threading import RLock, current_thread, get_native_id
from typing import Any, Iterator


_LOGGER = logging.getLogger(__name__)


# Use a promotable Windows priority instead of THREAD_MODE_BACKGROUND_*: the
# latter can only be ended by the worker itself, so a click could not elevate an
# already-running preload. The worker registry is task-scoped and short-lived.
_THREAD_PRIORITY_BELOW_NORMAL = -1
_THREAD_PRIORITY_NORMAL = 0
_THREAD_PRIORITY_ERROR_RETURN = 0x7FFFFFFF
_THREAD_SET_INFORMATION = 0x0020
_PRELOAD_THREAD_PREFIX = "DofusAtlasPreload-"
_PRELOAD_PRIORITY_LOCK = RLock()
_PRELOAD_THREAD_IDS: dict[str, int] = {}
_USER_PRIORITY_TASKS: set[str] = set()


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


def _current_preload_task() -> str:
    name = str(current_thread().name or "")
    if not name.startswith(_PRELOAD_THREAD_PREFIX):
        return ""
    return name[len(_PRELOAD_THREAD_PREFIX) :].strip().casefold()


def _register_current_preload_worker(task: str) -> tuple[int, bool]:
    native_id = int(get_native_id())
    with _PRELOAD_PRIORITY_LOCK:
        _PRELOAD_THREAD_IDS[task] = native_id
        foreground = task in _USER_PRIORITY_TASKS
    return native_id, foreground


def _unregister_preload_worker(task: str, native_id: int) -> None:
    with _PRELOAD_PRIORITY_LOCK:
        if _PRELOAD_THREAD_IDS.get(task) == native_id:
            _PRELOAD_THREAD_IDS.pop(task, None)


@contextmanager
def background_io_priority() -> Iterator[None]:
    """Run reconstructible preload work below normal priority until user demand."""

    task = _current_preload_task()
    native_id = 0
    foreground = False
    if task:
        native_id, foreground = _register_current_preload_worker(task)

    changed = False
    kernel32 = None
    handle = None
    previous_priority = _THREAD_PRIORITY_NORMAL
    if os.name == "nt" and not foreground:
        try:
            kernel32 = ctypes.windll.kernel32
            _configure_kernel32(kernel32)
            handle = kernel32.GetCurrentThread()
            current = int(kernel32.GetThreadPriority(handle))
            if current != _THREAD_PRIORITY_ERROR_RETURN:
                previous_priority = current
            changed = bool(
                kernel32.SetThreadPriority(handle, _THREAD_PRIORITY_BELOW_NORMAL)
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
                _LOGGER.debug(
                    "Unable to restore Windows background thread priority.",
                    exc_info=True,
                )
        if task and native_id:
            _unregister_preload_worker(task, native_id)


def promote_background_thread(native_thread_id: int) -> bool:
    """Promote one in-flight Windows preload worker to normal priority."""

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
        _LOGGER.debug(
            "Unable to promote preload worker thread %s.",
            thread_id,
            exc_info=True,
        )
        return False
    finally:
        if kernel32 is not None and handle:
            try:
                kernel32.CloseHandle(handle)
            except (AttributeError, OSError, TypeError, ValueError):
                _LOGGER.debug(
                    "Unable to close preload worker thread handle.",
                    exc_info=True,
                )


def request_preload_user_priority(task: str) -> bool:
    """Mark a task foreground and promote its worker if it already exists."""

    key = str(task or "").strip().casefold()
    if not key:
        return False
    with _PRELOAD_PRIORITY_LOCK:
        _USER_PRIORITY_TASKS.add(key)
        native_id = _PRELOAD_THREAD_IDS.get(key)
    if not native_id:
        return False
    return promote_background_thread(native_id)


def release_preload_user_priority(task: str) -> None:
    key = str(task or "").strip().casefold()
    if not key:
        return
    with _PRELOAD_PRIORITY_LOCK:
        _USER_PRIORITY_TASKS.discard(key)


class PreloadUserTaskSet(set[str]):
    """Drop-in set that connects AtlasWindow's existing state to OS priority."""

    def add(self, element: str) -> None:
        key = str(element or "").strip().casefold()
        super().add(key)
        request_preload_user_priority(key)

    def discard(self, element: str) -> None:
        key = str(element or "").strip().casefold()
        super().discard(key)
        release_preload_user_priority(key)

    def clear(self) -> None:
        for task in tuple(self):
            release_preload_user_priority(task)
        super().clear()


def install_preload_priority_bridge(owner: Any) -> bool:
    """Upgrade AtlasWindow's preload-user set without changing its public API."""

    current = getattr(owner, "preload_user_tasks", None)
    if isinstance(current, PreloadUserTaskSet):
        return True
    if not isinstance(current, set):
        return False
    upgraded = PreloadUserTaskSet(current)
    setattr(owner, "preload_user_tasks", upgraded)
    for task in tuple(upgraded):
        request_preload_user_priority(task)
    return True


__all__ = [
    "PreloadUserTaskSet",
    "background_io_priority",
    "install_preload_priority_bridge",
    "promote_background_thread",
    "release_preload_user_priority",
    "request_preload_user_priority",
]
