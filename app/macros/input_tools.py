from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import sys
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
    0x5C,  # Right Windows key
    0x6F,  # Numpad divide
    0xA3,  # Right Ctrl
    0xA5,  # Right Alt
}


def _configure_keyboard_api() -> None:
    if os.name != "nt":
        return
    user32 = ctypes.windll.user32
    user32.MapVirtualKeyW.argtypes = (ctypes.wintypes.UINT, ctypes.wintypes.UINT)
    user32.MapVirtualKeyW.restype = ctypes.wintypes.UINT
    # Keep SendInput setup adjacent to first real use, not at import-time.
    # Its INPUT pointer uses the shared native layout from app.windows.clicks.
    from app.windows.clicks import INPUT
    user32.SendInput.argtypes = (ctypes.wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = ctypes.wintypes.UINT


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


def _send_keyboard(vk_code: int, *, up: bool) -> None:
    if os.name != "nt" or not vk_code:
        return
    from app.windows.clicks import INPUT, INPUT_UNION, KEYBDINPUT

    _configure_keyboard_api()
    vk = int(vk_code)
    user32 = ctypes.windll.user32
    scan = int(user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC))
    flags = (KEYEVENTF_KEYUP if up else 0) | (
        KEYEVENTF_EXTENDEDKEY if vk in EXTENDED_VKS else 0
    )
    event = INPUT(
        type=1,  # INPUT_KEYBOARD
        union=INPUT_UNION(ki=KEYBDINPUT(
            vk, scan, flags, 0,
            ctypes.c_void_p(ATLAS_SYNTHETIC_KEYBOARD_EXTRA_INFO),
        )),
    )
    sent = int(user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT)))
    if sent != 1:
        # Preserve the immediate Win32 diagnostic when available. UIPI is not
        # identified by SendInput's return value or GetLastError alone.
        try:
            win32_error = int(ctypes.windll.kernel32.GetLastError())
        except (AttributeError, OSError, ValueError):
            win32_error = 0
        raise OSError(
            f"Windows SendInput refused a keyboard event (sent={sent}/1, "
            f"win32_error={win32_error}; check integrity and focus)"
        )


def key_down(vk_code: int) -> None:
    _send_keyboard(vk_code, up=False)


def key_up(vk_code: int) -> None:
    _send_keyboard(vk_code, up=True)


def press_key(key_name: str, hold_ms: int = 0) -> None:
    vk_code = _vk(key_name)
    if not vk_code:
        return
    key_down(vk_code)
    try:
        if hold_ms > 0:
            time.sleep(hold_ms / 1000.0)
    finally:
        original_error = sys.exc_info()[1]
        try:
            key_up(vk_code)
        except Exception:
            if original_error is None:
                raise
            # Preserve the initial failure; an unsuccessful release must still
            # be visible to diagnostics and the emergency-stop mechanism.
            import logging
            logging.getLogger(__name__).exception(
                "Relachement touche impossible apres une erreur d'entree"
            )


def press_hotkey(*key_names: str, hold_ms: int = 0) -> None:
    vk_codes = [_vk(str(name)) for name in key_names]
    held: list[int] = []
    try:
        for code in vk_codes:
            if not code:
                continue
            key_down(code)
            held.append(code)
        if hold_ms > 0:
            time.sleep(hold_ms / 1000.0)
    finally:
        original_error = sys.exc_info()[1]
        errors: list[Exception] = []
        for code in reversed(held):
            try:
                key_up(code)
            except Exception as exc:
                errors.append(exc)
        if errors:
            if original_error is not None:
                # Preserve the original SendInput/key-down failure. The
                # release problem is still recorded for troubleshooting.
                import logging
                logging.getLogger(__name__).error(
                    "Relachement clavier incomplet apres erreur: %s",
                    errors[0],
                )
            else:
                raise errors[0]


def release_common_inputs() -> None:
    # Emergency stop must continue releasing *all* buttons/modifiers even
    # when Windows refuses an individual input.
    import logging
    from app.input.hotkeys import VK_CONTROL, VK_MENU, VK_SHIFT
    if os.name == "nt":
        from app.windows.clicks import _send_mouse_flag
        for flag in (0x0004, 0x0010, 0x0040):  # left/right/middle UP
            try:
                if not _send_mouse_flag(flag):
                    logging.getLogger(__name__).warning(
                        "Stop urgence: SendInput souris refuse le relachement flag=%s", flag
                    )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Stop urgence: erreur relachement souris flag=%s", flag
                )
    for vk_code in (VK_SHIFT, VK_CONTROL, VK_MENU):
        try:
            key_up(vk_code)
        except Exception:
            logging.getLogger(__name__).exception(
                "Stop urgence: relachement touche refuse vk=%s", vk_code
            )


@contextmanager
def clipboard_text(text: str, logger: Logger):
    if os.name != "nt":
        yield
        return
    try:
        import win32clipboard
        import win32con
    except Exception as exc:
        logger.error("Clipboard indisponible: pywin32 introuvable.")
        # Sending Ctrl+V now would paste unrelated user clipboard data.
        raise OSError("Clipboard indisponible pour la commande macro") from exc

    previous = ""
    captured = False
    prepared = False
    clipboard_seq = 0
    for _attempt in range(10):
        unsupported_formats = False
        recovery_failed = False
        try:
            win32clipboard.OpenClipboard()
            try:
                # This owner only snapshots Unicode text. Refuse rich/media
                # formats rather than irreversibly stripping them (Word,
                # Excel, images, file drops, custom application formats).
                fmt = 0
                for _index in range(64):
                    fmt = win32clipboard.EnumClipboardFormats(fmt)
                    if not fmt:
                        break
                    if fmt not in (1, 7, 13, 16):  # CF_TEXT/OEMTEXT/UNICODETEXT/LOCALE
                        unsupported_formats = True
                        raise ValueError("Clipboard contient des formats non restaurables")
                else:
                    unsupported_formats = True
                    raise ValueError("Clipboard contient trop de formats")
                try:
                    previous = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
                    captured = True
                except Exception as exc:
                    # Never destroy a user's image, files, or other clipboard
                    # formats that cannot be restored by this text-only path.
                    # An actually empty clipboard is safe to temporarily use.
                    try:
                        empty = win32clipboard.EnumClipboardFormats(0) == 0
                    except Exception:
                        empty = False
                    if not empty:
                        raise OSError(
                            "Clipboard non texte ou illisible: commande annulee"
                        ) from exc
                    previous = ""
                    captured = False
                win32clipboard.EmptyClipboard()
                try:
                    win32clipboard.SetClipboardText(str(text), win32con.CF_UNICODETEXT)
                except Exception:
                    # Failed preparation must not leave a previously captured
                    # Unicode clipboard empty. Restore it under the SAME lock
                    # before retrying the send or reporting an error.
                    if captured:
                        try:
                            win32clipboard.SetClipboardText(
                                previous, win32con.CF_UNICODETEXT,
                            )
                        except Exception:
                            recovery_failed = True
                            logger.exception(
                                "Clipboard: reparation immediate apres echec SetClipboardText impossible."
                            )
                    raise
                # Snapshot under the same OpenClipboard lease. Capturing the
                # serial after closing would race a new user Copy.
                try:
                    serial = win32clipboard.GetClipboardSequenceNumber()
                    if type(serial) is int:
                        clipboard_seq = serial
                except Exception:
                    clipboard_seq = 0
            finally:
                win32clipboard.CloseClipboard()
            prepared = True
            break
        except Exception as exc:
            if unsupported_formats:
                # Unsupported formats cannot be recovered by retrying.
                logger.warning("Clipboard conservé: %s", exc)
                raise OSError("Clipboard multi-format non restaure: commande annulee") from exc
            if recovery_failed:
                # Never retry over an already damaged clipboard snapshot:
                # it would be misread as empty and the backup would be lost.
                raise OSError("Clipboard non restaure apres echec de preparation") from exc
            time.sleep(0.03)
    if not prepared:
        logger.error("Clipboard: impossible de preparer la commande apres 10 tentatives.")
        raise OSError("Clipboard non prepare: commande macro annulee")
    # Win32 increments this serial when another process changes clipboard.
    # Zero means sequence tracking was unavailable during preparation.
    try:
        yield
    finally:
        restored = False
        for _attempt in range(10):
            try:
                win32clipboard.OpenClipboard()
                try:
                    if clipboard_seq:
                        current_seq = win32clipboard.GetClipboardSequenceNumber()
                        if current_seq != clipboard_seq:
                            logger.info(
                                "Clipboard utilisateur modifie pendant la macro: restauration ignoree."
                            )
                            restored = True  # The NEW clipboard content is authoritative.
                            break
                    win32clipboard.EmptyClipboard()
                    if captured:
                        win32clipboard.SetClipboardText(previous, win32con.CF_UNICODETEXT)
                finally:
                    win32clipboard.CloseClipboard()
                restored = True
                break
            except Exception:
                time.sleep(0.03)
        if not restored:
            logger.warning("Clipboard: restauration impossible.")
        # Never return from this finally: contextlib would swallow exceptions
        # from the caller (SendInput, focus, Stop, etc.) and report fake success.


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
    # Stop is authoritative before touching the system clipboard at all.
    # The later checks remain necessary for a Stop during the paste sequence.
    if should_stop is not None and should_stop():
        logger.info("Commande chat stoppee avant preparation du clipboard.")
        return False
    with clipboard_text(text, logger):
        if not replace_chat_text_with_clipboard(
            chat_open_ms=chat_open_ms,
            key_step_ms=key_step_ms,
            paste_settle_ms=paste_settle_ms,
            should_stop=should_stop,
        ):
            logger.info("Commande chat stoppee avant validation.")
            return False
        # Stop can arrive after the final clipboard paste and before ENTER.
        # Never submit a command after an emergency-stop request.
        if should_stop is not None and should_stop():
            logger.info("Commande chat stoppee avant validation.")
            return False
        press_key("ENTER")
        if submit_twice:
            if _sleep_ms(key_step_ms, should_stop):
                return False
            if should_stop is not None and should_stop():
                return False
            press_key("ENTER")
    return True
