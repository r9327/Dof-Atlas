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
        self._last_move_probe_error_log = 0.0
        self._last_block_click_log = 0.0
        self._last_block_wheel_log = 0.0
        self._blocked_click_count = 0
        self._blocked_wheel_count = 0
        # A consumed DOWN must always swallow its matching physical UP.
        self._consumed_releases: set[int] = set()
        # Only duplicates need extra bookkeeping: the set still reflects
        # distinct outstanding UP tokens for existing hook consumers/tests.
        self._consumed_release_duplicates: dict[int, int] = {}
        # Only DOWN events actually passed through this hook may trigger the
        # native UP dispatcher. An orphan UP must never start replay or
        # discharge another button's pending click.
        self._native_releases: set[int] = set()

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
            self._consumed_release_duplicates.clear()
            self._native_releases.clear()
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
        self._last_move_probe_error_log = 0.0
        self._last_block_click_log = 0.0
        self._last_block_wheel_log = 0.0

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
            self._consumed_release_duplicates.clear()
            self._native_releases.clear()
            self._hook_thread_id = 0

    def _reserve_consumed_release(self, token: int) -> None:
        """One physical UP must be swallowed for each intercepted DOWN."""
        if token in self._consumed_releases:
            self._consumed_release_duplicates[token] = (
                self._consumed_release_duplicates.get(token, 0) + 1
            )
        else:
            self._consumed_releases.add(token)

    def _finish_consumed_release(self, token: int) -> None:
        extra = self._consumed_release_duplicates.get(token, 0)
        if extra > 0:
            if extra == 1:
                self._consumed_release_duplicates.pop(token, None)
            else:
                self._consumed_release_duplicates[token] = extra - 1
        else:
            self._consumed_releases.discard(token)

    def _mouse_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        try:
            if n_code >= 0 and w_param == WM_MOUSEMOVE:
                # MOVE never owns a DOWN/UP pair and has no user callback.
                # When the pointer is free, skip even ctypes decoding.
                try:
                    blocked = self.input_state.is_mouse_blocked()
                except Exception:
                    # A failed ownership probe is NOT proof that the cursor
                    # is free. Never leak a physical MOVE to the Unity client
                    # currently activated by an in-flight mirror worker.
                    self._log_move_probe_error("initial")
                    return 1
                if not blocked:
                    return ctypes.windll.user32.CallNextHookEx(
                        self._hook, n_code, w_param, l_param,
                    )
                # Under a pointer lease only the injected marker is needed.
                # Do not decode x/y, allocate a release token, or log MOVE
                # for every physical update during a 2–8 client fan-out.
                try:
                    move = ctypes.cast(
                        ctypes.c_void_p(l_param),
                        ctypes.POINTER(MSLLHOOKSTRUCT),
                    ).contents
                    atlas_synthetic = (
                        bool(move.flags & LLMHF_INJECTED)
                        or int(move.dwExtraInfo or 0)
                        == ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO
                    )
                except Exception:
                    # Only this active-lease path decodes MOVE. A malformed
                    # native event or ctypes failure must not silently leak
                    # a physical movement to a temporarily focused client.
                    self._log_move_probe_error("payload")
                    return 1
                if not atlas_synthetic:
                    # A long 8-client fan-out can release the pointer while
                    # this hook is decoding MOVE. Do not swallow the first
                    # now-native movement on a lease that already ended.
                    # This extra O(1) check runs ONLY during an active lease;
                    # the free-pointer MOVE path above still skips ctypes.
                    try:
                        still_blocked = self.input_state.is_mouse_blocked()
                    except Exception:
                        # A late Win32/state failure must not turn an active
                        # pointer lease into a native movement on another
                        # character. Keep injected movements independent.
                        self._log_move_probe_error("final")
                        return 1
                    if still_blocked:
                        return 1
                return ctypes.windll.user32.CallNextHookEx(
                    self._hook, n_code, w_param, l_param,
                )
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
                    if release_token in self._consumed_releases:
                        self._finish_consumed_release(release_token)
                        return 1

                # A native source DOWN that was NOT swallowed must keep its
                # matching UP, even when the release callback starts a replay
                # worker which blocks subsequent mouse events.
                if (not atlas_synthetic
                        and w_param in (WM_LBUTTONUP, WM_RBUTTONUP)
                        and w_param in self._native_releases):
                    # Consume the pair ownership BEFORE the callback:
                    # the callback can start a new worker and block input,
                    # but the real UP must still reach its original window.
                    self._native_releases.discard(w_param)
                    if self.release_callback is not None:
                        button = "Left" if w_param == WM_LBUTTONUP else "Right"
                        if self.release_callback(button, x, y):
                            return ctypes.windll.user32.CallNextHookEx(
                                self._hook, n_code, w_param, l_param,
                            )

                # An unreadable pointer lease is not proof that it is safe
                # to forward a new physical click to the foreground Unity
                # client. Preserve DOWN/UP ownership even if diagnostics fail.
                pointer_blocked = False
                if not atlas_synthetic:
                    try:
                        pointer_blocked = self.input_state.is_mouse_blocked()
                    except Exception:
                        paired_up = BLOCKED_DOWN_TO_UP.get(w_param)
                        if paired_up is not None:
                            self._reserve_consumed_release(
                                _physical_release_token(
                                    paired_up, int(event.mouseData),
                                ),
                            )
                        if (paired_up is not None
                                or w_param in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL)):
                            try:
                                self.logger.exception(
                                    "Hook souris: verrou illisible, geste physique refusé.",
                                )
                            except Exception:
                                pass
                            return 1
                        # A native UP with no intercepted DOWN must still
                        # reach its original client to avoid a stuck button.
                if pointer_blocked:
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
                    # A blocking lease can end between the first hot-path
                    # check and deciding whether this physical gesture lives.
                    # Capture its generation and accept the collision under
                    # the SAME state lock. Never swallow a newly native DOWN
                    # merely because a previous worker owned the cursor.
                    # An unreadable safety epoch must never make a
                    # previously blocked physical DOWN escape to Unity.
                    epoch_probe_failed = False
                    try:
                        lease_epoch = self.input_state.mouse_block_epoch_if_active()
                    except Exception:
                        lease_epoch = None
                        epoch_probe_failed = True
                        try:
                            self.logger.exception(
                                "Hook souris: génération du verrou illisible.",
                            )
                        except Exception:
                            pass
                    if lease_epoch is None and not epoch_probe_failed:
                        return ctypes.windll.user32.CallNextHookEx(
                            self._hook, n_code, w_param, l_param,
                        )
                    paired_up = BLOCKED_DOWN_TO_UP.get(w_param)
                    if (not epoch_probe_failed
                            and (paired_up is not None
                                 or w_param in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL))):
                        try:
                            claimed = self.input_state.note_blocked_physical_gesture(
                                expected_epoch=lease_epoch,
                            )
                        except Exception:
                            claimed = None
                            # If the pointer status is now unverifiable,
                            # fail closed to avoid a DOWN landing in the
                            # previously activated Unity target.
                            try:
                                self.logger.exception(
                                    "Hook souris: signal d'interruption impossible.",
                                )
                            except Exception:
                                pass
                        if claimed is False:
                            # Old worker released its lease before admission.
                            # If a NEW worker has begun, preserve its safety
                            # block but do not cancel its generation.
                            try:
                                current_epoch = self.input_state.mouse_block_epoch_if_active()
                            except Exception:
                                # We cannot prove the pointer is free:
                                # preserve the DOWN/UP ownership below.
                                current_epoch = lease_epoch
                                try:
                                    self.logger.exception(
                                        "Hook souris: nouvelle génération illisible.",
                                    )
                                except Exception:
                                    pass
                            if current_epoch is None:
                                return ctypes.windll.user32.CallNextHookEx(
                                    self._hook, n_code, w_param, l_param,
                                )
                    # Once interception is decided, own the matching UP even
                    # after Stop/restart. Never emit an orphaned release.
                    if paired_up is not None:
                        self._reserve_consumed_release(
                            _physical_release_token(paired_up, int(event.mouseData))
                        )
                    try:
                        self._log_blocked_event(w_param, x, y)
                    except Exception:
                        # Keep the physical DOWN/UP pair intercepted even if
                        # the logger itself fails. Returning to the outer
                        # exception handler could leak a physical release
                        # into another focused Unity window.
                        try:
                            self.logger.exception(
                                "Hook souris: journalisation blocage impossible.",
                            )
                        except Exception:
                            pass
                    return 1

                # A fresh physical DOWN with the pointer now free starts a
                # new press. Any old swallowed DOWN of this SAME button that
                # never received UP is obsolete: retaining its reservation
                # would eat the new native UP and leave a real press stuck.
                # Other buttons (including X1/X2) keep their own ownership.
                if not atlas_synthetic:
                    paired_up = BLOCKED_DOWN_TO_UP.get(w_param)
                    if paired_up is not None:
                        token = _physical_release_token(
                            paired_up, int(event.mouseData),
                        )
                        if token in self._consumed_releases:
                            self._consumed_releases.discard(token)
                            self._consumed_release_duplicates.pop(token, None)

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
                            self._reserve_consumed_release(
                                WM_LBUTTONUP if w_param == WM_LBUTTONDOWN else WM_RBUTTONUP
                            )
                            # Ownership is already recorded: a failing
                            # debug sink must never forward this DOWN while
                            # swallowing its matching physical UP.
                            try:
                                self.logger.debug(
                                    "Clic utilisateur consommé par macro switch: "
                                    "button=%s x=%s y=%s",
                                    button,
                                    x,
                                    y,
                                )
                            except Exception:
                                pass
                            return 1
                        # The original physical DOWN stays native. Its exact
                        # UP is the only event allowed to start a queued
                        # classic SwitchClick replay after release.
                        if self.release_callback is not None:
                            self._native_releases.add(
                                WM_LBUTTONUP if w_param == WM_LBUTTONDOWN
                                else WM_RBUTTONUP
                            )
        except Exception:
            # Before ownership is established, preserve the original native
            # event even if both the callback and the logger fail.
            try:
                self.logger.exception("Hook souris: erreur callback.")
            except Exception:
                pass

        return ctypes.windll.user32.CallNextHookEx(
            self._hook,
            n_code,
            w_param,
            l_param,
        )

    def _log_move_probe_error(self, probe: str) -> None:
        # MOVE can arrive thousands of times a second. A failed pointer
        # probe is fail-closed in _mouse_proc; its diagnostic must be
        # bounded independently of the click/wheel loss warnings.
        try:
            now = time.monotonic()
            if now - self._last_move_probe_error_log < BLOCK_LOG_INTERVAL_SECONDS:
                return
            self._last_move_probe_error_log = now
            self.logger.exception(
                "Hook souris: contrôle MOVE illisible probe=%s", probe,
            )
        except Exception:
            # Neither time nor a damaged logger may reopen the native hook.
            pass

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
        click = w_param in (WM_LBUTTONDOWN, WM_RBUTTONDOWN,
                            WM_MBUTTONDOWN, WM_XBUTTONDOWN)
        wheel = w_param in (WM_MOUSEWHEEL, WM_MOUSEHWHEEL)
        if click:
            self._blocked_click_count += 1
        elif wheel:
            self._blocked_wheel_count += 1
        now = time.monotonic()
        # A wheel burst must not consume the single diagnostic slot for a
        # genuinely lost click (and vice versa). Bound both to <= 2.5/s.
        if click:
            if now - self._last_block_click_log < BLOCK_LOG_INTERVAL_SECONDS:
                return
            self._last_block_click_log = now
        elif wheel:
            if now - self._last_block_wheel_log < BLOCK_LOG_INTERVAL_SECONDS:
                return
            self._last_block_wheel_log = now
        else:
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
