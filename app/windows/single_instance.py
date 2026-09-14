from __future__ import annotations

import ctypes
import os
from typing import Protocol


ATLAS_MUTEX_NAME = r"Local\DofusAtlas.Desktop.SingleInstance"
ERROR_ALREADY_EXISTS = 183


class _MutexBackend(Protocol):
    def create(self, name: str) -> tuple[int, bool]: ...

    def close(self, handle: int) -> None: ...


class _WindowsMutexBackend:
    def __init__(self) -> None:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool
        self._kernel32 = kernel32

    def create(self, name: str) -> tuple[int, bool]:
        self._kernel32.SetLastError(0)
        raw_handle = self._kernel32.CreateMutexW(None, False, name)
        error = int(self._kernel32.GetLastError())
        if not raw_handle:
            raise OSError(error, f"Unable to create Windows mutex {name!r}")
        return int(raw_handle), error == ERROR_ALREADY_EXISTS

    def close(self, handle: int) -> None:
        if not self._kernel32.CloseHandle(handle):
            error = int(self._kernel32.GetLastError())
            raise OSError(error, "Unable to close Windows mutex")


class SingleInstanceGuard:
    """Own the process-wide Atlas mutex for the lifetime of the GUI."""

    def __init__(self, name: str = ATLAS_MUTEX_NAME, *, backend: _MutexBackend | None = None) -> None:
        self.name = str(name)
        self._backend = backend
        self._handle: int | None = None
        self._acquired = False

    def acquire(self) -> bool:
        if self._acquired:
            return True
        if self._backend is None and os.name != "nt":
            self._acquired = True
            return True

        backend = self._backend or _WindowsMutexBackend()
        handle, already_exists = backend.create(self.name)
        if already_exists:
            backend.close(handle)
            return False
        self._backend = backend
        self._handle = handle
        self._acquired = True
        return True

    def release(self) -> None:
        if not self._acquired:
            return
        handle = self._handle
        backend = self._backend
        self._handle = None
        self._acquired = False
        if handle is not None and backend is not None:
            backend.close(handle)


__all__ = ["ATLAS_MUTEX_NAME", "SingleInstanceGuard"]
