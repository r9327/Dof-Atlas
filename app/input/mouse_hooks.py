from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import threading
import time
from logging import Logger
from typing import Callable

from app.input.hook_lifecycle import current_native_thread_id, stop_message_hook
from app.input.input_state import ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO, InputState, SyntheticInputGuard

WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
WM_MOUSEHWHEEL = 0x020E
LLMHF_INJECTED = 0x00000001
HOOK_START_TIMEOUT_SECONDS = 2.0
BLOCK_LOG_INTERVAL_SECONDS = 0.4

MouseCallback = Callable[[str, int, int], bool]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


LRESULT = getattr(ctypes.wintypes, "LRESULT", ctypes.c_ssize_t)
LowLevelMouseProc = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
    LRESULT,
    ctypes.c_int,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
)


def _configure_hook_api(user32, kernel32) -> None:
    kernel32.GetModuleHandleW.argtypes = (ctypes.wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p
    kernel32.GetLastError.argtypes = ()
    kernel32.GetLastError.restype = ctypes.wintypes.DWORD
    user32.SetWindowsHookExW.argtypes = (
        ctypes.c_int,
        LowLevelMouseProc,
        ctypes.c_void_p,
        ctypes.wintypes.DWORD,
    )
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)
    user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
    user32.CallNextHookEx.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.wintypes.WPARAM,
        ctypes.wintypes.LPARAM,
    )
    user32.CallNextHookEx.restype = LRESULT
    user32.GetMessageW.argtypes = (
        ctypes.POINTER(ctypes.wintypes.MSG),
        ctypes.wintypes.HWND,
        ctypes.wintypes.UINT,
        ctypes.wintypes.UINT,
    )
    user32.GetMessageW.restype = ctypes.wintypes.BOOL
    user32.TranslateMessage.argtypes = (ctypes.POINTER(ctypes.wintypes.MSG),)
    user32.TranslateMessage.restype = ctypes.wintypes.BOOL
    user32.DispatchMessageW.argtypes = (ctypes.POINTER(ctypes.wintypes.MSG),)
    user32.DispatchMessageW.restype = LRESULT


class MouseHook:
    def __init__(
        self,
        input_state: InputState,
        synthetic_guard: SyntheticInputGuard,
        logger: Logger,
        callback: MouseCallback,
    ):
        self.input_state = input_state
        self.synthetic_guard = synthetic_guard
        self.logger = logger
        self.callback = callback
        self._hook = None
        self._callback_ref = None
        self._thread: threading.Thread | None = None
        self._hook_thread_id = 0
        self._stop_event = threading.Event()
        self._startup_event = threading.Event()
        self._start_ok = False
        self._last_block_log = 0.0

    def start(self) -> bool:
        if os.name != "nt":
            self.logger.warning("Hooks souris indisponibles hors Windows.")
            return False
        if self._thread is not None:
            if self._thread.is_alive():
                return self._start_ok
            self._thread = None
            self._hook = None
            self._start_ok = False
        self._stop_event.clear()
        self._startup_event.clear()
        self._start_ok = False
        self._thread = threading.Thread(target=self._run_hook, name="DofusAtlasMouseHook", daemon=True)
        self._thread.start()
        self._startup_event.wait(HOOK_START_TIMEOUT_SECONDS)
        return self._start_ok

    def stop(self) -> None:
        stop_message_hook(self)

    def _run_hook(self) -> None:
        self._hook_thread_id = current_native_thread_id(self.logger)
        try:
            self._callback_ref = LowLevelMouseProc(self._mouse_proc)
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            _configure_hook_api(user32, kernel32)
            module_handle = kernel32.GetModuleHandleW(None)
            self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._callback_ref, module_handle, 0)
            if not self._hook:
                error_code = int(kernel32.GetLastError())
                self.logger.error(
                    "Hook souris Python impossible: error=%s module_handle=%s. Relancer Dofus Atlas avec les memes droits que Dofus.",
                    error_code,
                    module_handle,
                )
                self._start_ok = False
                self._startup_event.set()
                return
            self._start_ok = True
            self._startup_event.set()
            self.logger.info("Hook souris Python actif.")
            msg = ctypes.wintypes.MSG()
            while not self._stop_event.is_set() and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            self._hook_thread_id = 0

    def _mouse_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        try:
            if n_code >= 0:
                event = ctypes.cast(
                    ctypes.c_void_p(l_param),
                    ctypes.POINTER(MSLLHOOKSTRUCT),
                ).contents
                x = int(event.pt.x)
                y = int(event.pt.y)
                injected = bool(event.flags & LLMHF_INJECTED)
                extra_info = int(event.dwExtraInfo or 0)
                atlas_synthetic = (
                    injected
                    or extra_info == ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO
                )

                if self.input_state.is_mouse_blocked() and not atlas_synthetic:
                    self._log_blocked_event(w_param, x, y)
                    return 1

                if w_param in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
                    button = "Left" if w_param == WM_LBUTTONDOWN else "Right"
                    if atlas_synthetic or self.synthetic_guard.is_synthetic_window():
                        self.logger.debug(
                            "Clic synthétique ignoré: button=%s injected=%s",
                            button,
                            injected,
                        )
                    else:
                        self.logger.debug(
                            "Clic utilisateur détecté: button=%s x=%s y=%s",
                            button,
                            x,
                            y,
                        )
                        consumed = bool(self.callback(button, x, y))
                        if consumed:
                            self.logger.debug(
                                "Clic utilisateur consommé par macro switch: "
                                "button=%s x=%s y=%s",
                                button,
                                x,
                                y,
                            )
                            return 1
        except Exception:
            self.logger.exception("Hook souris: erreur callback.")

        return ctypes.windll.user32.CallNextHookEx(
            self._hook,
            n_code,
            w_param,
            l_param,
        )

    def _log_blocked_event(self, w_param: int, x: int, y: int) -> None:
        now = time.monotonic()
        if now - self._last_block_log < BLOCK_LOG_INTERVAL_SECONDS:
            return
        self._last_block_log = now
        label = self.input_state.mouse_block_label()
        event_name = {
            WM_MOUSEMOVE: "move",
            WM_LBUTTONDOWN: "left_down",
            WM_LBUTTONUP: "left_up",
            WM_RBUTTONDOWN: "right_down",
            WM_RBUTTONUP: "right_up",
            WM_MBUTTONDOWN: "middle_down",
            WM_MBUTTONUP: "middle_up",
            WM_MOUSEWHEEL: "wheel",
            WM_MOUSEHWHEEL: "hwheel",
            WM_XBUTTONDOWN: "x_down",
            WM_XBUTTONUP: "x_up",
        }.get(int(w_param), str(int(w_param)))
        self.logger.debug(
            "Souris physique bloquee pendant %s: event=%s x=%s y=%s",
            label or "macro",
            event_name,
            x,
            y,
        )
