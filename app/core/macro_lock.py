from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from logging import Logger


@dataclass
class MacroLease:
    label: str
    started_at: float
    generation: int = 0


class MacroLock:
    def __init__(self, logger: Logger):
        self._logger = logger
        self._lock = threading.Lock()
        self._lease: MacroLease | None = None
        self._generation = 0
        self._worker_generation = threading.local()
        self.stop_event = threading.Event()

    @property
    def active_label(self) -> str:
        lease = self._lease
        return lease.label if lease is not None else ""

    @property
    def active_generation(self) -> int | None:
        with self._lock:
            return self._lease.generation if self._lease is not None else None

    def snapshot_active(self) -> tuple[str, int] | None:
        """Read an active label and its exact generation atomically."""
        with self._lock:
            lease = self._lease
            return (lease.label, lease.generation) if lease is not None else None

    def owns(self, label: str, generation: int) -> bool:
        """True only while this exact worker generation owns the lease."""
        with self._lock:
            return (
                type(generation) is int and self._lease is not None
                and self._lease.generation == generation
                and self._lease.label == label
            )

    def bind_worker(self, label: str, generation: int) -> bool:
        """Bind the runner to the lease acquired before thread scheduling."""
        with self._lock:
            if (
                type(generation) is not int
                or self._lease is None
                or self._lease.label != label
                or self._lease.generation != generation
                or self.stop_event.is_set()
            ):
                return False
            self._worker_generation.token = generation
            return True

    def unbind_worker(self) -> None:
        self._worker_generation.token = None

    def try_begin_generation(self, label: str) -> int | None:
        """Atomically reserve a macro worker and return its exact lease ID."""
        with self._lock:
            if self._lease is not None:
                self._logger.debug("%s ignore: boucle macro deja en cours active=%s", label, self._lease.label)
                return None
            self.stop_event.clear()
            self._generation += 1
            self._lease = MacroLease(
                label=label, started_at=time.monotonic(),
                generation=self._generation,
            )
            self._logger.info("Macro debut: action=%s", label)
            return self._generation

    def try_begin(self, label: str) -> bool:
        # Legacy callers still receive an unchanged boolean contract.
        return self.try_begin_generation(label) is not None

    def end(self, label: str | None = None, *, generation: int | None = None) -> None:
        with self._lock:
            if self._lease is None:
                return
            active = self._lease.label
            if generation is not None and (
                type(generation) is not int or generation != self._lease.generation
            ):
                self._logger.warning(
                    "Macro fin refusée: génération périmée owner=%s caller=%s",
                    self._lease.generation, generation,
                )
                return
            # A stale completion must never release another macro's lease.
            # Only the owner (or an explicit administrative end) may unlock.
            if label is not None and label != active:
                self._logger.warning(
                    "Macro fin refusée: owner=%s caller=%s", active, label,
                )
                return
            elapsed = int((time.monotonic() - self._lease.started_at) * 1000)
            self._lease = None
            self._logger.info("Macro fin: action=%s elapsed_ms=%s", label or active, elapsed)

    def request_stop(self, reason: str = "stop urgence") -> None:
        # Wake native and Python waits immediately, even if a worker is
        # finishing while holding the lease lock.
        self.stop_event.set()
        with self._lock:
            # A concurrent try_begin_generation may clear the shared event
            # between our first set() and the lock acquisition. Set it again
            # under the same lock used by admission so Stop always wins that
            # overlap. A genuinely NEW admission after Stop may clear it.
            self.stop_event.set()
            active = self._lease.label if self._lease else ""
        self._logger.warning("Stop urgence: reason=%s active=%s", reason, active)

    def should_stop(self) -> bool:
        if self.stop_event.is_set():
            return True
        worker = getattr(self._worker_generation, "token", None)
        if worker is None:
            return False
        with self._lock:
            return (
                self._lease is None or self._lease.generation != worker
            )

    def wait(self, duration_ms: int) -> bool:
        # The same Event is reused across generations: a new start may clear
        # it before a suspended OLD worker gets scheduled after Stop. Bound
        # waits so stale threads recheck their generation in <= 25 ms, even
        # if they miss the transient Event.set() notification.
        deadline = time.monotonic() + max(0, int(duration_ms)) / 1000.0
        while True:
            if self.should_stop():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self.should_stop()
            if self.stop_event.wait(min(remaining, 0.025)):
                return True
