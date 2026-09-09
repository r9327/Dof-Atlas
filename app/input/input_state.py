from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from logging import Logger


ATLAS_SYNTHETIC_MOUSE_EXTRA_INFO = 0xA71A5C1
ATLAS_SYNTHETIC_KEYBOARD_EXTRA_INFO = 0xA71A5C2


@dataclass(frozen=True)
class MouseClick:
    button: str
    x: int
    y: int
    injected: bool = False


class InputState:
    def __init__(self):
        self._lock = threading.RLock()
        self.pressed_vks: set[int] = set()
        self.active_hotkeys: set[str] = set()
        self._mouse_block_count = 0
        self._mouse_block_label = ""

    def set_key(self, vk_code: int, pressed: bool) -> None:
        with self._lock:
            if pressed:
                self.pressed_vks.add(int(vk_code))
            else:
                self.pressed_vks.discard(int(vk_code))

    def snapshot(self) -> set[int]:
        with self._lock:
            return set(self.pressed_vks)

    def mark_hotkey_active(self, action_id: str, active: bool) -> bool:
        with self._lock:
            already = action_id in self.active_hotkeys
            if active:
                self.active_hotkeys.add(action_id)
                return not already
            self.active_hotkeys.discard(action_id)
            return already

    def reset_armed(self) -> None:
        with self._lock:
            self.active_hotkeys.clear()
            self.pressed_vks.clear()

    def begin_mouse_block(self, label: str) -> int:
        with self._lock:
            self._mouse_block_count += 1
            self._mouse_block_label = str(label or "macro")
            return self._mouse_block_count

    def end_mouse_block(self) -> int:
        with self._lock:
            self._mouse_block_count = max(0, self._mouse_block_count - 1)
            if self._mouse_block_count == 0:
                self._mouse_block_label = ""
            return self._mouse_block_count

    def clear_mouse_block(self) -> None:
        with self._lock:
            self._mouse_block_count = 0
            self._mouse_block_label = ""

    def is_mouse_blocked(self) -> bool:
        with self._lock:
            return self._mouse_block_count > 0

    def mouse_block_label(self) -> str:
        with self._lock:
            return self._mouse_block_label


class SyntheticInputGuard:
    def __init__(self, logger: Logger):
        self._logger = logger
        self._lock = threading.RLock()
        self._until = 0.0
        self._active_count = 0

    def begin(self, duration_ms: int = 250) -> None:
        with self._lock:
            self._active_count += 1
            self._until = max(self._until, time.monotonic() + max(0, duration_ms) / 1000.0)
            self._logger.debug("Protection clic synthetique active: count=%s", self._active_count)

    def end(self, duration_ms: int = 120) -> None:
        with self._lock:
            self._active_count = max(0, self._active_count - 1)
            self._until = max(self._until, time.monotonic() + max(0, duration_ms) / 1000.0)
            self._logger.debug("Protection clic synthetique relachee: count=%s", self._active_count)

    def reset(self) -> None:
        with self._lock:
            self._active_count = 0
            self._until = 0.0

    def is_synthetic_window(self) -> bool:
        with self._lock:
            return self._active_count > 0 or time.monotonic() < self._until
