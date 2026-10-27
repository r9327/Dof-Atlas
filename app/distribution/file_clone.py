"""Optional filesystem copy-on-write for unchanged, immutable release files.

Never hardlink release slots: a later write would corrupt *both* the active
version and its rollback. Windows ReFS block clone has copy-on-write semantics.
Normal NTFS and unsupported volumes fall back to a verified streaming copy.
"""
from __future__ import annotations

import os
from pathlib import Path


def clone_unchanged_cow(source: Path, destination: Path, size: int) -> bool:
    """Optional best-effort fast path: Win32 failures fall back to safe copy."""
    if os.name != "nt" or size <= 0 or destination.exists():
        return False
    try:
        return _clone_unchanged_cow_impl(source, destination, size)
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        # Filesystem APIs and ctypes differ across Windows builds. Clear an
        # incomplete private stage file before falling back to verified copy.
        # The caller requires an absent destination on entry.
        destination.unlink(missing_ok=True)
        return False


def _clone_unchanged_cow_impl(source: Path, destination: Path, size: int) -> bool:
    """Try ReFS extent cloning on Windows; leave no target on failure.

    Source and destination must already be verified as regular, distinct paths
    by the installer. This is only a speed optimization: the caller MUST hash
    the resulting target against the release manifest before activating it.
    """
    if os.name != "nt" or size <= 0:
        return False
    # ReFS is a Windows volume; never attempt clone across volumes or UNC paths.
    drive = source.drive
    if not drive or drive.casefold() != destination.drive.casefold():
        return False

    import ctypes
    import msvcrt
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    fs_name = ctypes.create_unicode_buffer(32)
    root = drive + "\\"
    kernel32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
    ]
    kernel32.GetVolumeInformationW.restype = wintypes.BOOL
    if not kernel32.GetVolumeInformationW(root, None, 0, None, None, None, fs_name, len(fs_name)):
        return False
    if fs_name.value.casefold() != "refs":
        return False

    sectors = wintypes.DWORD()
    bytes_per_sector = wintypes.DWORD()
    free_clusters = wintypes.DWORD()
    clusters = wintypes.DWORD()
    kernel32.GetDiskFreeSpaceW.argtypes = [
        wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetDiskFreeSpaceW.restype = wintypes.BOOL
    if not kernel32.GetDiskFreeSpaceW(
        root, ctypes.byref(sectors), ctypes.byref(bytes_per_sector),
        ctypes.byref(free_clusters), ctypes.byref(clusters),
    ):
        return False
    cluster_size = sectors.value * bytes_per_sector.value
    # Keep every clone single-range and aligned. Unaligned files stream-copy.
    if not cluster_size or size % cluster_size or size > 512 * 1024**2:
        return False

    class DuplicateExtentsData(ctypes.Structure):
        _fields_ = [
            ("FileHandle", wintypes.HANDLE),
            ("SourceFileOffset", ctypes.c_longlong),
            ("TargetFileOffset", ctypes.c_longlong),
            ("ByteCount", ctypes.c_longlong),
        ]

    kernel32.DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
    ]
    kernel32.DeviceIoControl.restype = wintypes.BOOL
    cloned = False
    try:
        with source.open("rb") as original, destination.open("xb+") as output:
            output.truncate(size)
            output.flush()
            request = DuplicateExtentsData(
                msvcrt.get_osfhandle(original.fileno()), 0, 0, size
            )
            returned = wintypes.DWORD()
            cloned = bool(kernel32.DeviceIoControl(
                msvcrt.get_osfhandle(output.fileno()),
                0x00098344,  # FSCTL_DUPLICATE_EXTENTS_TO_FILE
                ctypes.byref(request), ctypes.sizeof(request),
                None, 0, ctypes.byref(returned), None,
            ))
    except (OSError, ValueError):
        cloned = False
    finally:
        if not cloned:
            destination.unlink(missing_ok=True)
    return cloned
