from __future__ import annotations

import ctypes
import ctypes.wintypes
import hashlib
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from app.core.admin import PROCESS_QUERY_LIMITED_INFORMATION, process_id_for_window


@dataclass(frozen=True, slots=True)
class ProtocolBuildFiles:
    game_assembly: Path
    global_metadata: Path


@dataclass(frozen=True, slots=True)
class _CachedFingerprint:
    signature: tuple[tuple[str, int, int], ...]
    sha256: str


def process_executable_path(pid: int) -> Path | None:
    """Return the executable path for one Windows process, or ``None`` safely."""

    try:
        process_id = int(pid)
    except (TypeError, ValueError, OverflowError):
        return None
    if os.name != "nt" or process_id <= 0:
        return None

    try:
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
        open_process.restype = ctypes.wintypes.HANDLE
        query = kernel32.QueryFullProcessImageNameW
        query.argtypes = [
            ctypes.wintypes.HANDLE,
            ctypes.wintypes.DWORD,
            ctypes.wintypes.LPWSTR,
            ctypes.POINTER(ctypes.wintypes.DWORD),
        ]
        query.restype = ctypes.wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [ctypes.wintypes.HANDLE]
        close_handle.restype = ctypes.wintypes.BOOL
    except Exception:
        return None

    process = open_process(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
    if not process:
        return None
    try:
        size = ctypes.wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(int(size.value))
        if not query(process, 0, buffer, ctypes.byref(size)):
            return None
        raw_path = str(buffer.value or "").strip()
        return Path(raw_path) if raw_path else None
    except Exception:
        return None
    finally:
        try:
            close_handle(process)
        except Exception:
            pass


def protocol_build_files_for_executable(executable: str | Path) -> ProtocolBuildFiles | None:
    """Locate the IL2CPP files that define the active Dofus protocol build.

    Unity places ``GameAssembly.dll`` beside the executable and
    ``global-metadata.dat`` inside the matching ``*_Data`` directory. We do not
    guess alternate locations: if this exact layout is absent the network
    decoder remains disabled until the local build is explicitly supported.
    """

    executable_path = Path(executable)
    root = executable_path.parent
    game_assembly = root / "GameAssembly.dll"
    global_metadata = (
        root
        / f"{executable_path.stem}_Data"
        / "il2cpp_data"
        / "Metadata"
        / "global-metadata.dat"
    )
    try:
        if not game_assembly.is_file() or not global_metadata.is_file():
            return None
    except OSError:
        return None
    return ProtocolBuildFiles(
        game_assembly=game_assembly,
        global_metadata=global_metadata,
    )


def protocol_build_sha256(files: ProtocolBuildFiles) -> str | None:
    """Hash the exact IL2CPP protocol inputs without retaining their contents.

    File size/mtime are checked before and after hashing. If Ankama updates the
    client while the fingerprint is being computed, the mixed snapshot is
    discarded instead of being treated as a stable build identity.
    """

    paths = (files.game_assembly, files.global_metadata)
    before = _file_signature(paths)
    if before is None:
        return None

    digest = hashlib.sha256()
    try:
        for label, path in (
            (b"GameAssembly.dll", files.game_assembly),
            (b"global-metadata.dat", files.global_metadata),
        ):
            digest.update(label)
            digest.update(b"\0")
            with path.open("rb") as stream:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
            digest.update(b"\0")
    except OSError:
        return None

    after = _file_signature(paths)
    if after is None or after != before:
        return None
    return digest.hexdigest()


class ActiveProtocolBuildFingerprintProvider:
    """Resolve and cache one fingerprint shared by all configured Dofus windows.

    The callable is intentionally fail-closed. Every supplied positive window
    handle must resolve to a process and supported Unity layout, and all clients
    must point to the same build fingerprint. File contents are hashed only when
    path/size/mtime changes; normal message decoding performs cheap stat checks.
    """

    def __init__(self, window_handles_provider: Callable[[], Iterable[int]]) -> None:
        self.window_handles_provider = window_handles_provider
        self._lock = threading.RLock()
        self._cache: dict[tuple[tuple[str, int, int], ...], _CachedFingerprint] = {}

    def __call__(self) -> str | None:
        handles = self._handles()
        if not handles:
            return None

        unique_files: dict[tuple[str, str], ProtocolBuildFiles] = {}
        for handle in handles:
            pid = process_id_for_window(handle)
            if pid <= 0:
                return None
            executable = process_executable_path(pid)
            if executable is None:
                return None
            files = protocol_build_files_for_executable(executable)
            if files is None:
                return None
            try:
                key = (
                    os.path.normcase(str(files.game_assembly.resolve())),
                    os.path.normcase(str(files.global_metadata.resolve())),
                )
            except OSError:
                return None
            unique_files.setdefault(key, files)

        fingerprints: set[str] = set()
        for key in sorted(unique_files):
            fingerprint = self._fingerprint_for_files(unique_files[key])
            if not fingerprint:
                return None
            fingerprints.add(fingerprint)
        if len(fingerprints) != 1:
            return None
        return next(iter(fingerprints))

    def _handles(self) -> tuple[int, ...]:
        try:
            raw_handles = self.window_handles_provider() or ()
        except Exception:
            return ()
        handles: list[int] = []
        for raw_handle in raw_handles:
            try:
                handle = int(raw_handle)
            except (TypeError, ValueError, OverflowError):
                continue
            if handle > 0:
                handles.append(handle)
        return tuple(dict.fromkeys(handles))

    def _fingerprint_for_files(self, files: ProtocolBuildFiles) -> str | None:
        paths = (files.game_assembly, files.global_metadata)
        signature = _file_signature(paths)
        if signature is None:
            return None
        with self._lock:
            cached = self._cache.get(signature)
            if cached is not None:
                return cached.sha256
        fingerprint = protocol_build_sha256(files)
        if not fingerprint:
            return None
        # The hashing routine independently checks that the build files stayed
        # stable. Re-read their signature so the cache key describes the exact
        # snapshot that was hashed.
        stable_signature = _file_signature(paths)
        if stable_signature is None or stable_signature != signature:
            return None
        with self._lock:
            self._cache[stable_signature] = _CachedFingerprint(
                signature=stable_signature,
                sha256=fingerprint,
            )
            while len(self._cache) > 8:
                oldest_key = next(iter(self._cache))
                if oldest_key == stable_signature and len(self._cache) == 1:
                    break
                self._cache.pop(oldest_key, None)
        return fingerprint


def _file_signature(paths: Iterable[Path]) -> tuple[tuple[str, int, int], ...] | None:
    rows: list[tuple[str, int, int]] = []
    try:
        for path in paths:
            resolved = path.resolve()
            stat = resolved.stat()
            rows.append(
                (
                    os.path.normcase(str(resolved)),
                    int(stat.st_size),
                    int(stat.st_mtime_ns),
                )
            )
    except OSError:
        return None
    return tuple(rows)


__all__ = [
    "ActiveProtocolBuildFingerprintProvider",
    "ProtocolBuildFiles",
    "process_executable_path",
    "protocol_build_files_for_executable",
    "protocol_build_sha256",
]
