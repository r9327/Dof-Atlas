from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from logging import Logger


@dataclass
class MacroLease:
    label: str
    started_at: float


class MacroLock:
    def __init__(self, logger: Logger):
        self._logger = logger
        self._lock = threading.Lock()
        self._lease: MacroLease | None = None
        self.stop_event = threading.Event()

    @property
    def active_label(self) -> str:
        lease = self._lease
        return lease.label if lease is not None else ""

    def try_begin(self, label: str) -> bool:
        with self._lock:
            if self._lease is not None:
                self._logger.debug("%s ignore: boucle macro deja en cours active=%s", label, self._lease.label)
                return False
            self.stop_event.clear()
            self._lease = MacroLease(label=label, started_at=time.monotonic())
            self._logger.info("Macro debut: action=%s", label)
            return True

    def end(self, label: str | None = None) -> None:
        with self._lock:
            if self._lease is None:
                return
            active = self._lease.label
            elapsed = int((time.monotonic() - self._lease.started_at) * 1000)
            self._lease = None
            self._logger.info("Macro fin: action=%s elapsed_ms=%s", label or active, elapsed)

    def request_stop(self, reason: str = "stop urgence") -> None:
        self.stop_event.set()
        with self._lock:
            active = self._lease.label if self._lease else ""
        self._logger.warning("Stop urgence: reason=%s active=%s", reason, active)

    def should_stop(self) -> bool:
        return self.stop_event.is_set()

    def wait(self, duration_ms: int) -> bool:
        return self.stop_event.wait(max(0, int(duration_ms)) / 1000.0)
