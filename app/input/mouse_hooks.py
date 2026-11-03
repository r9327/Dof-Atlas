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
WheelCallback = Callable[[int, int, int, bool], bool]
MouseReleaseCallback = Callable[[str, int, int], bool]


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
        wheel_callback: WheelCallback | None = None,
        release_callback: MouseReleaseCallback | None = None,
    ):
        self.input_state = input_state
        self.synthetic_guard = synthetic_guard
        self.logger = logger
        self.callback = callback
        self.wheel_callback = wheel_callback
        self.release_callback = release_callback
        self._hook = None
        self._callback_ref = None
        self._thread: threading.Thread | None = None
        self._hook_thread_id = 0
        self._stop_event = threading.Event()
        self._startup_event = threading.Event()
        self._start_ok = False
        self._last_block_log = 0.0
        # A consumed DOWN must always swallow its matching physical UP.
        self._consumed_releases: set[int] = set()

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
        self._consumed_releases.clear()
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
            self._consumed_releases.clear()
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

                # A swallowed DOWN owns its matching physical UP. Never run
                # native-release callbacks for that pair: an UP without its
                # corresponding DOWN can activate an unrelated Unity target.
                if not atlas_synthetic and w_param in self._consumed_releases:
                    self._consumed_releases.discard(int(w_param))
                    return 1

                # A native source DOWN that was NOT swallowed must keep its
                # matching UP, even when the release callback starts a replay
                # worker which blocks subsequent mouse events.
                if (
                    not atlas_synthetic
                    and w_param in (WM_LBUTTONUP, WM_RBUTTONUP)
                    and self.release_callback is not None
                ):
                    button = "Left" if w_param == WM_LBUTTONUP else "Right"
                    if self.release_callback(button, x, y):
                        return ctypes.windll.user32.CallNextHookEx(
                            self._hook, n_code, w_param, l_param,
                        )

                if self.input_state.is_mouse_blocked() and not atlas_synthetic:
                    self._log_blocked_event(w_param, x, y)
                    return 1

                if w_param in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
                    # Win32 marks injected mouse events explicitly. A time
                    # window after an earlier SendInput is not evidence that
                    # the NEXT physical wheel tick is synthetic.
                    if not atlas_synthetic and self.wheel_callback is not None:
                        delta = ctypes.c_short((int(event.mouseData) >> 16) & 0xFFFF).value
                        if delta and self.wheel_callback(
                            delta, x, y, w_param == WM_MOUSEHWHEEL,
                        ):
                            return 1

                if w_param in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
                    button = "Left" if w_param == WM_LBUTTONDOWN else "Right"
                    if atlas_synthetic:
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
                            self._consumed_releases.add(
                                WM_LBUTTONUP if w_param == WM_LBUTTONDOWN else WM_RBUTTONUP
                            )
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
        # MouseMove floods the low-level hook. It must not hide a subsequent
        # user click from the throttled diagnostic, nor spam logs at 8 clients.
        if w_param in (
            WM_MOUSEMOVE,
            WM_LBUTTONUP, WM_RBUTTONUP, WM_MBUTTONUP, WM_XBUTTONUP,
        ):
            # A release cannot explain why a gesture was lost; it must not
            # consume the only warning slot before the next physical DOWN.
            return
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
        if w_param in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN):
            # A blocked DOWN can represent a genuinely lost native gesture.
            # Keep it visible at a bounded rate until the busy-event policy
            # is validated on Windows; never claim it was replayed.
            self.logger.warning(
                "Clic physique non diffusé (macro occupée=%s): event=%s",
                label or "macro", event_name,
            )
        elif w_param in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
            self.logger.warning(
                "Molette physique non diffusée (macro occupée=%s): event=%s",
                label or "macro", event_name,
            )
        else:
            self.logger.debug(
                "Souris physique bloquee pendant %s: event=%s x=%s y=%s",
                label or "macro", event_name, x, y,
            )
