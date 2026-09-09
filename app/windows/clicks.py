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


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", INPUT_UNION)]


def current_cursor_pos() -> tuple[int, int]:
    if os.name != "nt":
        return 0, 0
    point = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def set_cursor_pos(screen_x: int, screen_y: int) -> None:
    if os.name == "nt":
        ctypes.windll.user32.SetCursorPos(int(screen_x), int(screen_y))


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
    except (TypeError, ValueError):
        requested_count = 1
    click_total = 2 if requested_count >= 2 else 1
    down_ms = max(0, int(down_ms))
    double_gap_ms = max(0, int(double_gap_ms))
    pre_click_ms = max(0, int(pre_click_ms))
    post_up_ms = max(0, int(post_up_ms))

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

    guard_duration_ms = max(
        250,
        pre_click_ms
        + post_up_ms
        + click_total * down_ms
        + max(0, click_total - 1) * double_gap_ms
        + 120,
    )
    button_is_down = False
    synthetic_guard.begin(guard_duration_ms)
    try:
        if pre_click_ms > 0 and wait_ms(pre_click_ms, should_stop):
            return False

        set_cursor_pos(int(screen_x), int(screen_y))
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
            button_is_down = down_ok
            ok = down_ok and ok

            if down_ms > 0 and wait_ms(down_ms, should_stop):
                return False

            up_ok = _send_mouse_flag(up_flag)
            button_is_down = bool(down_ok and not up_ok)
            ok = up_ok and ok

            if (
                index < click_total - 1
                and double_gap_ms > 0
                and wait_ms(double_gap_ms, should_stop)
            ):
                return False

        if post_up_ms > 0 and wait_ms(post_up_ms, should_stop):
            return False

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
                _send_mouse_flag(up_flag)
            except Exception:
                logger.exception(
                    "Relachement souris de secours impossible: button=%s",
                    button_name,
                )
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
    try:
        hwnd = int(hwnd)
    except (TypeError, ValueError):
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
        should_stop=should_stop,
    )
