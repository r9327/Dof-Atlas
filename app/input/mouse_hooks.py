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
# Static: WM_MOUSEMOVE can flood the busy hook, never allocate a new map per event.
BLOCKED_DOWN_TO_UP = {
    WM_LBUTTONDOWN: WM_LBUTTONUP,
    WM_RBUTTONDOWN: WM_RBUTTONUP,
    WM_MBUTTONDOWN: WM_MBUTTONUP,
    WM_XBUTTONDOWN: WM_XBUTTONUP,
}

MouseCallback = Callable[[str, int, int], bool]
WheelCallback = Callable[[int, int, int, bool], bool]
MouseReleaseCallback = Callable[[str, int, int], bool]


def _physical_release_token(up_message: int, mouse_data: int) -> int:
    """Distinguish XBUTTON1 and XBUTTON2 ownership during a mouse block.

    Both thumb buttons share WM_XBUTTONUP. Without its HIWORD identity,
    releasing one can discharge the other's swallowed DOWN and leak an
    orphaned UP into whichever window the macro has focused.
    """
    if up_message == WM_XBUTTONUP:
        xbutton = (int(mouse_data) >> 16) & 0xFFFF
        if xbutton in (1, 2):
            return up_message | (xbutton << 16)
    return up_message


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
        self._blocked_click_count = 0
        self._blocked_wheel_count = 0
        # A consumed DOWN must always swallow its matching physical UP.
        self._consumed_releases: set[int] = set()
        # Multiple native DOWNs of one button can precede their UPs during
        # hardware bounce or an overloaded multi-client hook. A plain set
        # would consume only the first UP and leak the next one into Unity.
        self._consumed_release_depth: dict[int, int] = {}

    def _reserve_physical_up(self, token: int) -> None:
        if token not in self._consumed_releases:
            self._consumed_release_depth[token] = 0
        self._consumed_releases.add(token)
        self._consumed_release_depth[token] = (
            self._consumed_release_depth.get(token, 0) + 1
        )

    def _take_reserved_physical_up(self, token: int) -> bool:
        if token not in self._consumed_releases:
            return False
        remaining = self._consumed_release_depth.get(token, 1) - 1
        if remaining > 0:
            self._consumed_release_depth[token] = remaining
        else:
            self._consumed_release_depth.pop(token, None)
            self._consumed_releases.discard(token)
        return True

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
        # Keep ownership of consumed physical DOWN/UP pairs until Windows
        # actually unhooks us. Clearing first can leak an orphaned UP during
        # the shutdown race while the hook callback is still active.
        stop_message_hook(self)
        # The shared lifecycle deliberately retains a live hook thread if
        # Win32 teardown timed out. Keep ownership of intercepted DOWN/UP
        # pairs until that thread's _run_hook finally block exits.
        thread = self._thread
        if thread is None or not thread.is_alive():
            self._consumed_releases.clear()
            self._consumed_release_depth.clear()
        else:
            self.logger.warning(
                "Hook souris toujours actif après stop: relâchements réservés=%s",
                len(self._consumed_releases),
            )
        if self._blocked_click_count or self._blocked_wheel_count:
            # Final totals include the suppressed events that did not survive
            # the 400ms warning throttle just before the hook stopped.
            self.logger.info(
                "Organizer hooks arrêtés: clics bloqués=%s molettes bloquées=%s",
                self._blocked_click_count, self._blocked_wheel_count,
            )
        self._blocked_click_count = 0
        self._blocked_wheel_count = 0
        self._last_block_log = 0.0

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
            self._consumed_release_depth.clear()
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
                # WM_MOUSEMOVE floods this hook. Decode the X-button
                # HIWORD only for a possible pending release, not per move.
                if (not atlas_synthetic and self._consumed_releases
                        and (w_param in self._consumed_releases
                             or w_param == WM_XBUTTONUP)):
                    release_token = _physical_release_token(
                        w_param, int(event.mouseData),
                    )
                    if self._take_reserved_physical_up(release_token):
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
                    # An UP with no consumed DOWN can belong to a real press
                    # that began BEFORE the worker blocked input. Swallowing
                    # only that UP would leave the user's button held. The
                    # consumed-release branch above already protects every
                    # DOWN intercepted by this hook.
                    if w_param in (
                        WM_LBUTTONUP, WM_RBUTTONUP,
                        WM_MBUTTONUP, WM_XBUTTONUP,
                    ):
                        return ctypes.windll.user32.CallNextHookEx(
                            self._hook, n_code, w_param, l_param,
                        )
                    # A DOWN blocked during replay must retain ownership of
                    # its matching UP even if the worker ends before the user
                    # releases the button. Otherwise an orphaned physical UP
                    # could be delivered to Unity or another application.
                    paired_up = BLOCKED_DOWN_TO_UP.get(w_param)
                    if paired_up is not None:
                        self._reserve_physical_up(
                            _physical_release_token(paired_up, int(event.mouseData))
                        )
                    try:
                        self._log_blocked_event(w_param, x, y)
                    except Exception:
                        # Diagnostics must never turn a blocked physical
                        # gesture into an accidental input to another window.
                        self.logger.exception(
                            "Hook souris: journalisation blocage impossible.",
                        )
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
                            self._reserve_physical_up(
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
        if w_param in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN):
            self._blocked_click_count += 1
        elif w_param in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL):
            self._blocked_wheel_count += 1
        now = time.monotonic()
        if now - self._last_block_log < BLOCK_LOG_INTERVAL_SECONDS:
            return
        self._last_block_log = now
        label = self.input_state.mouse_block_label()
        # Cumulative counters include all observed blocked physical gestures,
        # not just warnings surviving the 400ms log rate limiter.
        self.logger.info(
            "Organizer entrées physiques bloquées: clics=%s molettes=%s",
            self._blocked_click_count, self._blocked_wheel_count,
        )
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
