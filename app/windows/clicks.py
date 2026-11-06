from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
from logging import Logger
from typing import Callable

from app.input.input_state import ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO, SyntheticInputGuard
from app.windows.timing import wait_ms
from app.windows.unity_windows import (
    clamp_client_point,
    client_to_screen,
    foreground_window,
    is_unity_window,
)

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
INPUT_MOUSE = 0


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    # Win32 ABI: one INPUT must have enough union storage for the mouse
    # even when it carries a keyboard event.
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", INPUT_UNION)]


def current_cursor_pos() -> tuple[int, int]:
    if os.name != "nt":
        return 0, 0
    point = ctypes.wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
        # The POINT buffer remains zero-initialized on a refused Win32 read.
        # Treating it as the genuine old cursor would move the user's
        # pointer to (0, 0) during cleanup after the macro finishes.
        raise OSError("Windows GetCursorPos refused; position unavailable")
    return int(point.x), int(point.y)


def set_cursor_pos(screen_x: int, screen_y: int) -> None:
    if os.name == "nt":
        x, y = int(screen_x), int(screen_y)
        if not ctypes.windll.user32.SetCursorPos(x, y):
            # A refused move must not be mistaken for a successful aim:
            # send_screen_click would otherwise click at the old position.
            try:
                win32_error = int(ctypes.windll.kernel32.GetLastError())
            except (AttributeError, OSError, ValueError):
                win32_error = 0
            raise OSError(
                f"Windows SetCursorPos refused at ({x},{y}) "
                f"(win32_error={win32_error})"
            )
        # Win32 can return success while ClipCursor silently clamps the
        # position. A SendInput click at that OTHER position is unsafe.
        actual = current_cursor_pos()
        if actual != (x, y):
            raise OSError(
                f"Windows cursor confined or moved: wanted=({x},{y}) "
                f"actual={actual}"
            )


def _send_mouse_flag(flag: int) -> bool:
    event = INPUT(
        type=INPUT_MOUSE,
        union=INPUT_UNION(
            mi=MOUSEINPUT(0, 0, 0, flag, 0, ctypes.c_void_p(ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO))
        ),
    )
    sent = ctypes.windll.user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))
    return int(sent) == 1


def send_screen_click(
    screen_x: int,
    screen_y: int,
    button: str,
    click_count: int,
    down_ms: int,
    double_gap_ms: int,
    pre_click_ms: int,
    post_up_ms: int,
    synthetic_guard: SyntheticInputGuard,
    logger: Logger,
    should_stop: Callable[[], bool] | None = None,
) -> bool:
    if os.name != "nt":
        return False
    if should_stop is not None and should_stop():
        logger.info(
            "Clic synthetique stoppe avant envoi: x=%s y=%s",
            screen_x,
            screen_y,
        )
        return False

    normalized_button = str(button or "").strip().casefold()
    if normalized_button not in {"left", "right"}:
        logger.warning("Clic synthetique refuse: bouton invalide=%r", button)
        return False

    button_name = "Right" if normalized_button == "right" else "Left"
    try:
        requested_count = int(click_count)
    except (TypeError, ValueError, OverflowError):
        requested_count = 1
    click_total = 2 if requested_count >= 2 else 1
    try:
        down_ms = max(0, int(down_ms))
        double_gap_ms = max(0, int(double_gap_ms))
        pre_click_ms = max(0, int(pre_click_ms))
        post_up_ms = max(0, int(post_up_ms))
    except (TypeError, ValueError, OverflowError):
        # Corrupted profiles must not crash the mouse worker before the
        # synthetic guard or accidentally emit a click using bad timings.
        logger.warning("Clic synthetique refuse: temporisation invalide.")
        return False

    down_flag = (
        MOUSEEVENTF_RIGHTDOWN
        if button_name == "Right"
        else MOUSEEVENTF_LEFTDOWN
    )
    up_flag = (
        MOUSEEVENTF_RIGHTUP
        if button_name == "Right"
        else MOUSEEVENTF_LEFTUP
    )

    timing_budget_ms = (
        pre_click_ms + post_up_ms + click_total * down_ms
        + max(0, click_total - 1) * double_gap_ms
    )
    # Normal Unity profiles need under 200 ms for a double-click. Reject
    # extreme finite values before arming a mouse guard lasting minutes.
    if timing_budget_ms > 1000:
        logger.warning(
            "Clic synthetique refuse: temporisation excessive budget=%s ms.",
            timing_budget_ms,
        )
        return False
    guard_duration_ms = max(250, timing_budget_ms + 120)
    button_is_down = False
    synthetic_guard.begin(guard_duration_ms)
    try:
        # Unity needs hover time AFTER the pointer reaches the interactive
        # object. Sleeping at the old location cannot update Unity's target.
        set_cursor_pos(int(screen_x), int(screen_y))
        if pre_click_ms > 0 and wait_ms(pre_click_ms, should_stop):
            return False

        ok = True

        for index in range(click_total):
            if should_stop is not None and should_stop():
                logger.info(
                    "Clic synthetique stoppe pendant sequence: index=%s",
                    index + 1,
                )
                return False

            logger.debug(
                "Clic synthetique envoye: button=%s count=%s x=%s y=%s",
                button_name,
                index + 1,
                screen_x,
                screen_y,
            )

            down_ok = _send_mouse_flag(down_flag)
            if not down_ok:
                # Never emit an unpaired mouse UP when Windows rejected
                # the DOWN. A stray UP could land in a different window.
                logger.warning(
                    "Clic synthétique annulé: DOWN refusé button=%s index=%s",
                    button_name, index + 1,
                )
                return False
            button_is_down = True

            if down_ms > 0 and wait_ms(down_ms, should_stop):
                return False

            up_ok = _send_mouse_flag(up_flag)
            button_is_down = bool(down_ok and not up_ok)
            if not up_ok:
                # An unconfirmed release means this button may STILL be held.
                # Never stack the next DOWN of a double-click onto it.
                # The finally block owns the single emergency release.
                return False
            ok = up_ok and ok

            if (
                index < click_total - 1
                and double_gap_ms > 0
                and wait_ms(double_gap_ms, should_stop)
            ):
                return False

        if post_up_ms > 0:
            # Once UP is confirmed, settle errors/Stop must not downgrade a
            # delivered click and cause duplicate delivery at the next layer.
            try:
                wait_ms(post_up_ms, should_stop)
            except Exception:
                # Delivery has already completed. A broken diagnostic sink
                # must not turn a real click into a reported failure.
                try:
                    logger.exception(
                        "Clic envoyé: temporisation après UP impossible; livraison conservée."
                    )
                except Exception:
                    pass

        return ok
    except Exception:
        logger.exception(
            "Erreur pendant le clic synthetique: button=%s x=%s y=%s",
            button_name,
            screen_x,
            screen_y,
        )
        return False
    finally:
        if button_is_down:
            try:
                if not _send_mouse_flag(up_flag):
                    logger.warning(
                        "Relachement souris de secours refuse: button=%s",
                        button_name,
                    )
            except Exception:
                # The pointer guard must be released even when a failed UP
                # and a broken diagnostic sink happen at the same time.
                try:
                    logger.exception(
                        "Relachement souris de secours impossible: button=%s",
                        button_name,
                    )
                except Exception:
                    pass
        synthetic_guard.end(120)


def send_client_click(
    hwnd: int,
    client_x: int,
    client_y: int,
    button: str,
    click_count: int,
    down_ms: int,
    double_gap_ms: int,
    pre_click_ms: int,
    post_up_ms: int,
    synthetic_guard: SyntheticInputGuard,
    logger: Logger,
    should_stop: Callable[[], bool] | None = None,
) -> bool:
    # Never coerce bool, fraction, string, or an out-of-range HWND into a
    # different real window. This is the final boundary before SendInput.
    if type(hwnd) is not int or not 0 < hwnd <= (2**64 - 1):
        logger.info("Clic ignore: hwnd invalide=%r", hwnd)
        return False

    if not is_unity_window(hwnd):
        logger.info("Clic ignore: cible non Unity hwnd=%s", hwnd)
        return False

    client_x, client_y = clamp_client_point(hwnd, client_x, client_y)
    point = client_to_screen(hwnd, client_x, client_y)
    if point is None:
        logger.info(
            "Clic ignore: conversion client->ecran impossible hwnd=%s",
            hwnd,
        )
        return False
    # The focus can be stolen during Unity's hover-settle delay after the
    # cursor moves. A callback checked only before the move is not enough:
    # keep each DOWN (including the second click) bound to its original HWND.
    def should_abort() -> bool:
        if should_stop is not None and should_stop():
            return True
        if foreground_window() != hwnd:
            logger.warning(
                "Clic synthétique annulé: focus modifié avant entrée hwnd=%s",
                hwnd,
            )
            return True
        return False

    return send_screen_click(
        point[0],
        point[1],
        button,
        click_count,
        down_ms,
        double_gap_ms,
        pre_click_ms,
        post_up_ms,
        synthetic_guard,
        logger,
        should_stop=should_abort,
    )


MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_HWHEEL = 0x1000


def send_screen_wheel(delta: int, *, horizontal: bool = False) -> bool:
    """One SendInput wheel gesture with native signed high-word delta."""
    if os.name != "nt" or type(delta) is not int or delta == 0 or abs(delta) > 32767:
        return False
    flag = MOUSEEVENTF_HWHEEL if horizontal else MOUSEEVENTF_WHEEL
    event = INPUT(
        type=INPUT_MOUSE,
        union=INPUT_UNION(mi=MOUSEINPUT(
            0, 0, delta & 0xFFFFFFFF, flag, 0,
            ctypes.c_void_p(ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO),
        )),
    )
    return int(ctypes.windll.user32.SendInput(
        1, ctypes.byref(event), ctypes.sizeof(INPUT),
    )) == 1
