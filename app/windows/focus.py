from __future__ import annotations

import ctypes
import os
from logging import Logger
from typing import Callable

from app.windows.timing import wait_ms
from app.windows.unity_windows import foreground_window, is_unity_window


def activate_window(
    hwnd: int,
    settle_ms: int,
    attempts: int,
    retry_ms: int,
    logger: Logger,
    action_label: str,
    should_stop: Callable[[], bool] | None = None,
) -> bool:
    if os.name != "nt" or not hwnd:
        return False
    try:
        import win32con
        import win32gui
        import win32api
        import win32process
    except Exception:
        logger.error("%s activation impossible: pywin32 introuvable.", action_label)
        return False

    if not is_unity_window(hwnd):
        logger.info("%s activation impossible: cible non Unity hwnd=%s", action_label, hwnd)
        return False

    def attach_threads() -> list[tuple[int, int]]:
        current_thread = int(win32api.GetCurrentThreadId())
        try:
            target_thread = int(win32process.GetWindowThreadProcessId(int(hwnd))[0])
        except Exception:
            target_thread = 0
        try:
            foreground = int(win32gui.GetForegroundWindow() or 0)
            foreground_thread = (
                int(win32process.GetWindowThreadProcessId(foreground)[0])
                if foreground
                else 0
            )
        except Exception:
            foreground_thread = 0

        attached: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for source_thread, target in (
            (current_thread, target_thread),
            (current_thread, foreground_thread),
            (foreground_thread, target_thread),
        ):
            if (
                source_thread <= 0
                or target <= 0
                or source_thread == target
            ):
                continue
            pair = (source_thread, target)
            if pair in seen:
                continue
            seen.add(pair)
            try:
                win32process.AttachThreadInput(source_thread, target, True)
                attached.append(pair)
            except Exception as exc:
                logger.debug(
                    "%s activation attach thread echec: source=%s cible=%s error=%s",
                    action_label,
                    source_thread,
                    target,
                    exc,
                )
        return attached

    def detach_threads(attached: list[tuple[int, int]]) -> None:
        for source_thread, target_thread in reversed(attached):
            try:
                win32process.AttachThreadInput(
                    source_thread,
                    target_thread,
                    False,
                )
            except Exception as exc:
                logger.debug(
                    "%s activation detach thread echec: source=%s cible=%s error=%s",
                    action_label,
                    source_thread,
                    target_thread,
                    exc,
                )

    hwnd = int(hwnd)
    attempt_count = max(1, int(attempts))
    settle_ms = max(0, int(settle_ms))
    retry_ms = max(0, int(retry_ms))

    try:
        if not win32gui.IsWindow(hwnd):
            logger.info(
                "%s activation impossible: fenetre absente hwnd=%s",
                action_label,
                hwnd,
            )
            return False
    except Exception:
        return False

    if foreground_window() == hwnd:
        if settle_ms > 0 and wait_ms(settle_ms, should_stop):
            return False
        return True

    for attempt in range(attempt_count):
        if should_stop is not None and should_stop():
            logger.info(
                "%s activation stoppee avant tentative hwnd=%s",
                action_label,
                hwnd,
            )
            return False

        attached: list[tuple[int, int]] = []
        try:
            try:
                ctypes.windll.user32.AllowSetForegroundWindow(-1)
            except Exception:
                pass

            attached = attach_threads()

            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

            win32gui.BringWindowToTop(hwnd)
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOP,
                0,
                0,
                0,
                0,
                win32con.SWP_NOMOVE
                | win32con.SWP_NOSIZE
                | win32con.SWP_SHOWWINDOW,
            )

            try:
                win32gui.SetActiveWindow(hwnd)
            except Exception as exc:
                logger.debug(
                    "%s activation SetActiveWindow echec tentative=%s error=%s",
                    action_label,
                    attempt + 1,
                    exc,
                )

            win32gui.SetForegroundWindow(hwnd)

            try:
                win32gui.SetFocus(hwnd)
            except Exception as exc:
                logger.debug(
                    "%s activation SetFocus echec tentative=%s error=%s",
                    action_label,
                    attempt + 1,
                    exc,
                )

            # Dernier recours bref. La fenetre est immediatement retiree du
            # mode topmost pour ne jamais rester au-dessus des autres applis.
            if (
                attempt == attempt_count - 1
                and foreground_window() != hwnd
            ):
                flags = (
                    win32con.SWP_NOMOVE
                    | win32con.SWP_NOSIZE
                    | win32con.SWP_SHOWWINDOW
                )
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_TOPMOST,
                    0,
                    0,
                    0,
                    0,
                    flags,
                )
                win32gui.SetWindowPos(
                    hwnd,
                    win32con.HWND_NOTOPMOST,
                    0,
                    0,
                    0,
                    0,
                    flags,
                )
                win32gui.SetForegroundWindow(hwnd)
        except Exception as exc:
            logger.debug(
                "%s activation tentative=%s erreur=%s",
                action_label,
                attempt + 1,
                exc,
            )
        finally:
            detach_threads(attached)

        if settle_ms > 0 and wait_ms(settle_ms, should_stop):
            logger.info(
                "%s activation stoppee pendant settle hwnd=%s",
                action_label,
                hwnd,
            )
            return False

        foreground = foreground_window()
        if foreground == hwnd:
            logger.debug(
                "%s activation reussie hwnd=%s tentative=%s/%s",
                action_label,
                hwnd,
                attempt + 1,
                attempt_count,
            )
            return True

        logger.debug(
            "%s activation non confirmee hwnd=%s foreground=%s tentative=%s/%s",
            action_label,
            hwnd,
            foreground,
            attempt + 1,
            attempt_count,
        )

        if (
            attempt < attempt_count - 1
            and retry_ms > 0
            and wait_ms(retry_ms, should_stop)
        ):
            logger.info(
                "%s activation stoppee pendant retry hwnd=%s",
                action_label,
                hwnd,
            )
            return False

    logger.info(
        "%s activation echec hwnd=%s foreground=%s",
        action_label,
        hwnd,
        foreground_window(),
    )
    return False
