from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import time
from contextlib import contextmanager
from logging import Logger
from typing import Callable

from app.input.input_state import ATLAS_SYNTHETIC_KEYBOARD_EXTRA_INFO

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
MAPVK_VK_TO_VSC = 0
EXTENDED_VKS = {
    0x21,  # PageUp
    0x22,  # PageDown
    0x23,  # End
    0x24,  # Home
    0x25,  # Left
    0x26,  # Up
    0x27,  # Right
    0x28,  # Down
    0x2D,  # Insert
    0x2E,  # Delete
    0x5B,  # Left Windows key
}


def _configure_keyboard_api() -> None:
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    user32.MapVirtualKeyW.argtypes = (ctypes.wintypes.UINT, ctypes.wintypes.UINT)
    user32.MapVirtualKeyW.restype = ctypes.wintypes.UINT
    user32.keybd_event.argtypes = (
        ctypes.c_ubyte,
        ctypes.c_ubyte,
        ctypes.wintypes.DWORD,
        ctypes.c_void_p,
    )
    user32.keybd_event.restype = None


def _vk(key_name: str) -> int:
    # Hotkey parsing is part of the runtime hook backend. Keep that relatively
    # large module out of the pre-splash import path; the first synthetic input
    # or runtime hotkey reload will load it on demand.
    from app.input.hotkeys import NAMED_KEYS, VK_CONTROL, VK_LWIN, VK_MENU, VK_SHIFT

    key = str(key_name or "").strip().upper()
    if key in {"CTRL", "CONTROL"}:
        return VK_CONTROL
    if key == "ALT":
        return VK_MENU
    if key == "SHIFT":
        return VK_SHIFT
    if key in {"WIN", "LWIN"}:
        return VK_LWIN
    if len(key) == 1 and ("A" <= key <= "Z" or "0" <= key <= "9"):
        return ord(key)
    return int(NAMED_KEYS.get(key, 0))


def key_down(vk_code: int) -> None:
    if os.name == "nt" and vk_code:
        _configure_keyboard_api()
        vk = int(vk_code)
        scan = int(ctypes.windll.user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC))
        flags = KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_VKS else 0
        ctypes.windll.user32.keybd_event(
            vk,
            scan,
            flags,
            ctypes.c_void_p(ATLAS_SYNTHETIC_KEYBOARD_EXTRA_INFO),
        )


def key_up(vk_code: int) -> None:
    if os.name == "nt" and vk_code:
        _configure_keyboard_api()
        vk = int(vk_code)
        scan = int(ctypes.windll.user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC))
        flags = KEYEVENTF_KEYUP | (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_VKS else 0)
        ctypes.windll.user32.keybd_event(
            vk,
            scan,
            flags,
            ctypes.c_void_p(ATLAS_SYNTHETIC_KEYBOARD_EXTRA_INFO),
        )


def press_key(key_name: str, hold_ms: int = 0) -> None:
    vk_code = _vk(key_name)
    if not vk_code:
        return
    key_down(vk_code)
    if hold_ms > 0:
        time.sleep(hold_ms / 1000.0)
    key_up(vk_code)


def press_hotkey(*key_names: str, hold_ms: int = 0) -> None:
    vk_codes = [_vk(name) if len(str(name)) > 1 else _vk(str(name)) for name in key_names]
    vk_codes = [code for code in vk_codes if code]
    for code in vk_codes:
        key_down(code)
    if hold_ms > 0:
        time.sleep(hold_ms / 1000.0)
    for code in reversed(vk_codes):
        key_up(code)


def release_common_inputs() -> None:
    if os.name == "nt":
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(0x0040, 0, 0, 0, 0)
    from app.input.hotkeys import VK_CONTROL, VK_MENU, VK_SHIFT

    for vk_code in (VK_SHIFT, VK_CONTROL, VK_MENU):
        key_up(vk_code)


@contextmanager
def clipboard_text(text: str, logger: Logger):
    if os.name != "nt":
        yield
        return
    try:
        import win32clipboard
        import win32con
    except Exception:
        logger.error("Clipboard indisponible: pywin32 introuvable.")
        yield
        return

    previous = ""
    captured = False
    for _attempt in range(10):
        try:
            win32clipboard.OpenClipboard()
            try:
                try:
                    previous = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                    captured = True
                except Exception:
                    previous = ""
                    captured = False
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(str(text), win32con.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            break
        except Exception:
            time.sleep(0.03)
    try:
        yield
    finally:
        for _attempt in range(10):
            try:
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    if captured:
                        win32clipboard.SetClipboardText(previous, win32con.CF_UNICODETEXT)
                finally:
                    win32clipboard.CloseClipboard()
                return
            except Exception:
                time.sleep(0.03)
        logger.warning("Clipboard: restauration impossible.")


def _sleep_ms(duration_ms: int, should_stop: Callable[[], bool] | None = None) -> bool:
    deadline = time.monotonic() + max(0, int(duration_ms)) / 1000.0
    while time.monotonic() < deadline:
        if should_stop is not None and should_stop():
            return True
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    return bool(should_stop is not None and should_stop())


def replace_chat_text_with_clipboard(
    chat_open_ms: int = 0,
    key_step_ms: int = 0,
    paste_settle_ms: int = 0,
    should_stop: Callable[[], bool] | None = None,
) -> bool:
    if should_stop is not None and should_stop():
        return False
    press_key("SPACE")
    if _sleep_ms(chat_open_ms, should_stop):
        return False
    press_hotkey("CTRL", "A")
    if _sleep_ms(key_step_ms, should_stop):
        return False
    press_key("DELETE")
    if _sleep_ms(key_step_ms, should_stop):
        return False
    press_hotkey("CTRL", "V")
    if _sleep_ms(paste_settle_ms, should_stop):
        return False
    return True


def send_chat_command(
    text: str,
    logger: Logger,
    submit_twice: bool = False,
    chat_open_ms: int = 0,
    key_step_ms: int = 0,
    paste_settle_ms: int = 0,
    should_stop: Callable[[], bool] | None = None,
) -> bool:
    with clipboard_text(text, logger):
        if not replace_chat_text_with_clipboard(
            chat_open_ms=chat_open_ms,
            key_step_ms=key_step_ms,
            paste_settle_ms=paste_settle_ms,
            should_stop=should_stop,
        ):
            logger.info("Commande chat stoppee avant validation.")
            return False
        press_key("ENTER")
        if submit_twice:
            if _sleep_ms(key_step_ms, should_stop):
                return False
            press_key("ENTER")
    return True
