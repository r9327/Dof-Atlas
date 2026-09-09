from __future__ import annotations

import ctypes
import logging
import os
from ctypes import wintypes
from threading import RLock
from typing import Any, Callable, Iterable


LOGGER = logging.getLogger(__name__)


user32 = None
kernel32 = None
EnumWindowsProc = None
WinEventProc = None
_WINDOWS_API_READY = False
_WINDOWS_API_LOCK = RLock()


def _ensure_windows_api() -> bool:
    """Bind user32/kernel32 lazily on first real Windows operation."""

    global user32, kernel32, EnumWindowsProc, WinEventProc, _WINDOWS_API_READY

    if os.name != "nt":
        return False
    if _WINDOWS_API_READY:
        return bool(user32 and kernel32 and EnumWindowsProc and WinEventProc)

    with _WINDOWS_API_LOCK:
        if _WINDOWS_API_READY:
            return bool(user32 and kernel32 and EnumWindowsProc and WinEventProc)

        resolved_user32 = ctypes.WinDLL("user32", use_last_error=True)
        resolved_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        enum_windows_proc = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            wintypes.HWND,
            wintypes.LPARAM,
        )
        win_event_proc = ctypes.WINFUNCTYPE(
            None,
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.HWND,
            wintypes.LONG,
            wintypes.LONG,
            wintypes.DWORD,
            wintypes.DWORD,
        )

        resolved_user32.EnumWindows.argtypes = [enum_windows_proc, wintypes.LPARAM]
        resolved_user32.SetParent.argtypes = [wintypes.HWND, wintypes.HWND]
        resolved_user32.SetParent.restype = wintypes.HWND
        resolved_user32.GetParent.argtypes = [wintypes.HWND]
        resolved_user32.GetParent.restype = wintypes.HWND
        resolved_user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        resolved_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        resolved_user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        resolved_user32.GetWindowTextLengthW.restype = ctypes.c_int
        resolved_user32.GetWindowTextW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        resolved_user32.GetWindowTextW.restype = ctypes.c_int
        resolved_user32.GetClassNameW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        resolved_user32.GetClassNameW.restype = ctypes.c_int
        resolved_user32.IsWindow.argtypes = [wintypes.HWND]
        resolved_user32.IsWindow.restype = wintypes.BOOL
        resolved_user32.IsWindowVisible.argtypes = [wintypes.HWND]
        resolved_user32.IsWindowVisible.restype = wintypes.BOOL
        resolved_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        resolved_user32.ShowWindow.restype = wintypes.BOOL
        resolved_user32.MoveWindow.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.BOOL,
        ]
        resolved_user32.MoveWindow.restype = wintypes.BOOL
        resolved_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        resolved_user32.GetWindowLongW.restype = ctypes.c_long
        resolved_user32.SetWindowLongW.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_long,
        ]
        resolved_user32.SetWindowLongW.restype = ctypes.c_long
        resolved_user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        resolved_user32.SetWindowPos.restype = wintypes.BOOL
        resolved_user32.GetClientRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        resolved_user32.GetClientRect.restype = wintypes.BOOL
        resolved_user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        resolved_user32.PostMessageW.restype = wintypes.BOOL
        resolved_user32.SetWinEventHook.argtypes = [
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HMODULE,
            win_event_proc,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        resolved_user32.SetWinEventHook.restype = wintypes.HANDLE
        resolved_user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        resolved_user32.UnhookWinEvent.restype = wintypes.BOOL
        resolved_kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        resolved_kernel32.OpenProcess.restype = wintypes.HANDLE
        resolved_kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        resolved_kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        resolved_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        resolved_kernel32.CloseHandle.restype = wintypes.BOOL

        user32 = resolved_user32
        kernel32 = resolved_kernel32
        EnumWindowsProc = enum_windows_proc
        WinEventProc = win_event_proc
        _WINDOWS_API_READY = True
        return True


GWL_STYLE = -16
GWL_EXSTYLE = -20
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_BORDER = 0x00800000
WS_DLGFRAME = 0x00400000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SW_HIDE = 0
SW_SHOW = 5
WM_CLOSE = 0x0010
EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_CREATE = 0x8000
EVENT_OBJECT_DESTROY = 0x8001
EVENT_OBJECT_SHOW = 0x8002
EVENT_OBJECT_HIDE = 0x8003
EVENT_OBJECT_NAMECHANGE = 0x800C
OBJID_WINDOW = 0
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
UNITY_WINDOW_EVENTS = (
    EVENT_SYSTEM_FOREGROUND,
    EVENT_OBJECT_CREATE,
    EVENT_OBJECT_DESTROY,
    EVENT_OBJECT_SHOW,
    EVENT_OBJECT_HIDE,
    EVENT_OBJECT_NAMECHANGE,
)


def hwnd_value(value: Any) -> int:
    try:
        return 0 if value is None else int(value)
    except (TypeError, ValueError):
        return 0


def window_title(hwnd: int) -> str:
    if not _ensure_windows_api():
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def window_class(hwnd: int) -> str:
    if not _ensure_windows_api():
        return ""
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, 256)
    return buffer.value


def window_process_id(hwnd: int) -> int:
    if not _ensure_windows_api():
        return 0
    process_id = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
    return int(process_id.value)


def process_image_path(pid: int) -> str:
    if pid <= 0 or not _ensure_windows_api():
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return ""
        return buffer.value
    finally:
        kernel32.CloseHandle(handle)


def client_size(hwnd: int) -> tuple[int, int]:
    if not hwnd or not _ensure_windows_api():
        return (0, 0)
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        return (0, 0)
    return (max(0, int(rect.right - rect.left)), max(0, int(rect.bottom - rect.top)))


def enumerate_windows(visible: bool = False) -> list[dict[str, Any]]:
    if not _ensure_windows_api():
        return []
    rows: list[dict[str, Any]] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        is_visible = bool(user32.IsWindowVisible(hwnd))
        if visible and not is_visible:
            return True
        rows.append(
            {
                "hwnd": int(hwnd),
                "pid": window_process_id(hwnd),
                "title": window_title(hwnd),
                "class": window_class(hwnd),
                "visible": is_visible,
                "parent": hwnd_value(user32.GetParent(hwnd)),
            }
        )
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return rows


def describe_window_row(row: dict[str, Any]) -> str:
    return (
        "hwnd={hwnd} pid={pid} parent={parent} visible={visible} "
        "class={cls!r} title={title!r}"
    ).format(
        hwnd=int(row.get("hwnd") or 0),
        pid=int(row.get("pid") or 0),
        parent=int(row.get("parent") or 0),
        visible=bool(row.get("visible")),
        cls=str(row.get("class") or ""),
        title=str(row.get("title") or ""),
    )


def scan_unity_sessions() -> list[dict[str, Any]]:
    if not _ensure_windows_api():
        return []
    sessions: list[dict[str, Any]] = []

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        if window_class(hwnd) != "UnityWndClass":
            return True
        raw_title = window_title(hwnd).strip()
        if not raw_title:
            return True
        parts = [part.strip() for part in raw_title.split(" - ") if part.strip()]
        title = f"{parts[0]} - {parts[1]}" if len(parts) >= 2 else raw_title
        sessions.append(
            {
                "nom": title,
                "detected_title": title,
                "hwnd": int(hwnd),
                "pid": window_process_id(hwnd),
            }
        )
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return uniquify_session_names(sessions)


def uniquify_session_names(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, int] = {}
    for session in sessions:
        key = str(session.get("nom") or "").strip()
        if key:
            totals[key] = totals.get(key, 0) + 1

    seen: dict[str, int] = {}
    unique_sessions: list[dict[str, Any]] = []
    for session in sessions:
        name = str(session.get("nom") or "").strip()
        if not name or totals.get(name, 0) <= 1:
            unique_sessions.append(session)
            continue
        seen[name] = seen.get(name, 0) + 1
        unique_session = dict(session)
        unique_session["nom"] = f"{name} {seen[name]}"
        unique_sessions.append(unique_session)
    return unique_sessions


class UnityWindowEventWatcher:
    """Observe Unity top-level windows without polling or a worker thread."""

    def __init__(self, callback: Callable[[int, int], None]) -> None:
        self.callback = callback
        self._event_proc = None
        self._hooks: list[Any] = []
        self._tracked_hwnds: set[int] = set()

    @property
    def active(self) -> bool:
        return bool(self._hooks)

    def replace_tracked_hwnds(self, hwnds: Iterable[int]) -> None:
        self._tracked_hwnds = {int(hwnd) for hwnd in hwnds if int(hwnd) > 0}

    def start(self) -> bool:
        if self.active:
            return True
        if not _ensure_windows_api():
            return False

        self._event_proc = WinEventProc(self._handle_event)
        hooks: list[Any] = []
        for event_id in UNITY_WINDOW_EVENTS:
            hook = user32.SetWinEventHook(
                event_id,
                event_id,
                None,
                self._event_proc,
                0,
                0,
                WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS,
            )
            if not hook:
                for installed_hook in hooks:
                    user32.UnhookWinEvent(installed_hook)
                self._event_proc = None
                LOGGER.error("Impossible d'installer l'observateur des fenêtres Unity (event=%s).", event_id)
                return False
            hooks.append(hook)
        self._hooks = hooks
        return True

    def stop(self) -> None:
        hooks = self._hooks
        self._hooks = []
        for hook in hooks:
            if user32:
                user32.UnhookWinEvent(hook)
        self._event_proc = None
        self._tracked_hwnds.clear()

    def _handle_event(
        self,
        _hook,
        event_id: int,
        hwnd,
        object_id: int,
        child_id: int,
        _event_thread: int,
        _event_time: int,
    ) -> None:
        try:
            hwnd_int = hwnd_value(hwnd)
            event_int = int(event_id)
            if hwnd_int <= 0 or int(object_id) != OBJID_WINDOW or int(child_id) != 0:
                return

            tracked = hwnd_int in self._tracked_hwnds
            if event_int in {EVENT_OBJECT_DESTROY, EVENT_OBJECT_HIDE}:
                if not tracked:
                    return
                self._tracked_hwnds.discard(hwnd_int)
            else:
                if window_class(hwnd_int) != "UnityWndClass":
                    return
                self._tracked_hwnds.add(hwnd_int)
            self.callback(event_int, hwnd_int)
        except Exception:
            LOGGER.exception("Erreur dans l'observateur des fenêtres Unity.")
