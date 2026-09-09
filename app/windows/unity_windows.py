from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from typing import Iterable


UNITY_CLASS = "UnityWndClass"


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, int(self.right - self.left))

    @property
    def height(self) -> int:
        return max(0, int(self.bottom - self.top))

    def contains(self, x: int, y: int) -> bool:
        return self.left <= int(x) < self.right and self.top <= int(y) < self.bottom


@dataclass(frozen=True)
class UnityWindow:
    hwnd: int
    title: str
    rect: Rect
    client_rect: Rect


def enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _win32():
    import win32con
    import win32gui

    return win32con, win32gui


def root_window(hwnd: int) -> int:
    if os.name != "nt" or not hwnd:
        return 0
    try:
        win32con, win32gui = _win32()
        return int(win32gui.GetAncestor(int(hwnd), win32con.GA_ROOT) or hwnd)
    except Exception:
        return int(hwnd or 0)


def is_window(hwnd: int) -> bool:
    if os.name != "nt" or not hwnd:
        return False
    try:
        _win32con, win32gui = _win32()
        return bool(win32gui.IsWindow(int(hwnd)))
    except Exception:
        return False


def is_unity_window(hwnd: int) -> bool:
    if os.name != "nt" or not hwnd:
        return False
    try:
        _win32con, win32gui = _win32()
        return bool(win32gui.IsWindow(int(hwnd)) and win32gui.GetClassName(int(hwnd)) == UNITY_CLASS)
    except Exception:
        return False


def window_rect(hwnd: int) -> Rect | None:
    try:
        _win32con, win32gui = _win32()
        left, top, right, bottom = win32gui.GetWindowRect(int(hwnd))
        if right <= left or bottom <= top:
            return None
        return Rect(int(left), int(top), int(right), int(bottom))
    except Exception:
        return None


def client_rect(hwnd: int) -> Rect | None:
    try:
        _win32con, win32gui = _win32()
        left, top, right, bottom = win32gui.GetClientRect(int(hwnd))
        screen_left, screen_top = win32gui.ClientToScreen(int(hwnd), (left, top))
        screen_right, screen_bottom = win32gui.ClientToScreen(int(hwnd), (right, bottom))
        if screen_right <= screen_left or screen_bottom <= screen_top:
            return None
        return Rect(int(screen_left), int(screen_top), int(screen_right), int(screen_bottom))
    except Exception:
        return None


def get_unity_window(hwnd: int) -> UnityWindow | None:
    if not is_unity_window(hwnd):
        return None
    rect = window_rect(hwnd)
    client = client_rect(hwnd)
    if rect is None or client is None:
        return None
    try:
        _win32con, win32gui = _win32()
        title = win32gui.GetWindowText(int(hwnd))
    except Exception:
        title = ""
    return UnityWindow(hwnd=int(hwnd), title=title, rect=rect, client_rect=client)


def foreground_window() -> int:
    if os.name != "nt":
        return 0
    try:
        _win32con, win32gui = _win32()
        return root_window(int(win32gui.GetForegroundWindow()))
    except Exception:
        return 0


def window_from_point(screen_x: int, screen_y: int) -> int:
    if os.name != "nt":
        return 0
    try:
        _win32con, win32gui = _win32()
        hwnd = win32gui.WindowFromPoint((int(screen_x), int(screen_y)))
        return root_window(int(hwnd))
    except Exception:
        return 0


def find_known_client_from_point(
    screen_x: int,
    screen_y: int,
    handles: Iterable[int],
) -> int:
    """
    Renvoie uniquement la fenêtre Unity Dofus réellement située au premier
    plan sous le curseur.

    Une fenêtre Dofus simplement présente derrière une autre application ne
    doit pas être choisie comme source. Dans ce cas, la macro utilisera le
    personnage favori via son propre fallback.
    """
    point_hwnd = window_from_point(screen_x, screen_y)
    if point_hwnd <= 0 or not is_unity_window(point_hwnd):
        return 0

    known_handles: set[int] = set()
    for handle in handles:
        try:
            hwnd = int(handle or 0)
        except (TypeError, ValueError):
            continue
        if hwnd > 0:
            known_handles.add(hwnd)

    return point_hwnd if point_hwnd in known_handles else 0


def screen_to_client(hwnd: int, screen_x: int, screen_y: int) -> tuple[int, int] | None:
    if os.name != "nt":
        return None
    try:
        _win32con, win32gui = _win32()
        x, y = win32gui.ScreenToClient(int(hwnd), (int(screen_x), int(screen_y)))
        return int(x), int(y)
    except Exception:
        return None


def client_to_screen(hwnd: int, client_x: int, client_y: int) -> tuple[int, int] | None:
    if os.name != "nt":
        return None
    try:
        _win32con, win32gui = _win32()
        x, y = win32gui.ClientToScreen(int(hwnd), (int(client_x), int(client_y)))
        return int(x), int(y)
    except Exception:
        return None


def client_size(hwnd: int) -> tuple[int, int]:
    rect = client_rect(hwnd)
    if rect is None:
        return 0, 0
    return rect.width, rect.height


def clamp_client_point(hwnd: int, client_x: int, client_y: int) -> tuple[int, int]:
    width, height = client_size(hwnd)
    if width <= 0 or height <= 0:
        return max(0, int(client_x)), max(0, int(client_y))
    return max(0, min(width - 1, int(client_x))), max(0, min(height - 1, int(client_y)))


def client_point_ratio(hwnd: int, client_x: int, client_y: int) -> tuple[float, float] | None:
    width, height = client_size(hwnd)
    if width <= 1 or height <= 1:
        return None
    x, y = clamp_client_point(hwnd, client_x, client_y)
    return x / (width - 1), y / (height - 1)


def client_point_from_ratio(hwnd: int, x_ratio: float, y_ratio: float) -> tuple[int, int] | None:
    width, height = client_size(hwnd)
    if width <= 0 or height <= 0:
        return None
    x = round((width - 1) * max(0.0, min(1.0, float(x_ratio))))
    y = round((height - 1) * max(0.0, min(1.0, float(y_ratio))))
    return clamp_client_point(hwnd, x, y)


def client_center(hwnd: int) -> tuple[int, int] | None:
    width, height = client_size(hwnd)
    if width <= 0 or height <= 0:
        return None
    return max(0, (width - 1) // 2), max(0, (height - 1) // 2)
