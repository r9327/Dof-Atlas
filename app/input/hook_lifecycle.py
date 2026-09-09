from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import threading
from typing import Any


WM_QUIT = 0x0012
HOOK_THREAD_JOIN_TIMEOUT_SECONDS = 1.5


def current_native_thread_id(logger) -> int:
    """Return the current Win32 thread id, or 0 when unavailable."""
    if os.name != "nt":
        return 0
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentThreadId.argtypes = ()
        kernel32.GetCurrentThreadId.restype = ctypes.wintypes.DWORD
        return int(kernel32.GetCurrentThreadId())
    except Exception:
        logger.exception("Impossible de memoriser l'id de thread du hook Win32.")
        return 0


def stop_message_hook(owner: Any) -> None:
    """Stop one low-level Win32 hook without leaving a blocked GetMessage thread.

    The owner is expected to expose ``_thread``, ``_hook``, ``_hook_thread_id``,
    ``_stop_event``, ``_start_ok`` and ``logger``. Keeping this lifecycle in one
    helper prevents keyboard and mouse hooks from drifting into two subtly
    different implementations.
    """
    thread = getattr(owner, "_thread", None)
    owner._stop_event.set()

    if os.name == "nt":
        thread_id = int(getattr(owner, "_hook_thread_id", 0) or 0)
        if thread_id:
            try:
                user32 = ctypes.windll.user32
                user32.PostThreadMessageW.argtypes = (
                    ctypes.wintypes.DWORD,
                    ctypes.wintypes.UINT,
                    ctypes.wintypes.WPARAM,
                    ctypes.wintypes.LPARAM,
                )
                user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL
                if not user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0):
                    owner.logger.warning(
                        "WM_QUIT non poste au thread hook Win32: thread_id=%s",
                        thread_id,
                    )
            except Exception:
                owner.logger.exception("Arret du message loop du hook Win32 impossible.")

        hook = getattr(owner, "_hook", None)
        if hook:
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(hook)
            except Exception:
                owner.logger.exception("UnhookWindowsHookEx a echoue pendant l'arret du runtime.")

    if thread is not None and thread is not threading.current_thread() and thread.is_alive():
        thread.join(HOOK_THREAD_JOIN_TIMEOUT_SECONDS)

    if thread is not None and thread.is_alive():
        owner.logger.error(
            "Thread hook Win32 toujours actif apres demande d'arret: %s",
            thread.name,
        )
        # Preserve the live reference so start() cannot create a second hook.
        owner._thread = thread
    else:
        owner._thread = None

    owner._hook = None
    owner._start_ok = False
