from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from logging import Logger
from typing import Callable


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
        self._emergency_latched = False

    @property
    def active_label(self) -> str:
        lease = self._lease
        return lease.label if lease is not None else ""

    @property
    def emergency_latched(self) -> bool:
        with self._lock:
            return self._emergency_latched

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
            if self._lease is not None or self._emergency_latched:
                try:
                    self._logger.debug("%s ignore: macro occupée ou Stop urgence verrouillé active=%s", label, self._lease.label if self._lease else "")
                except Exception:
                    # A faulty diagnostic sink must not escape admission.
                    pass
                return None
            self.stop_event.clear()
            self._generation += 1
            self._lease = MacroLease(
                label=label, started_at=time.monotonic(),
                generation=self._generation,
            )
            try:
                self._logger.info("Macro debut: action=%s", label)
            except Exception:
                # The lease is already owned; never strand it on a log error.
                pass
            return self._generation

    def try_begin(self, label: str) -> bool:
        # Legacy callers still receive an unchanged boolean contract.
        return self.try_begin_generation(label) is not None

    def end(
        self, label: str | None = None, *, generation: int | None = None,
        on_owner_end: Callable[[], None] | None = None,
    ) -> None:
        with self._lock:
            if self._lease is None:
                return
            active = self._lease.label
            if generation is not None and (
                type(generation) is not int or generation != self._lease.generation
            ):
                try:
                    self._logger.warning(
                        "Macro fin refusée: génération périmée owner=%s caller=%s",
                        self._lease.generation, generation,
                    )
                except Exception:
                    pass
                return
            # A stale completion must never release another macro's lease.
            # Only the owner (or an explicit administrative end) may unlock.
            if label is not None and label != active:
                try:
                    self._logger.warning(
                        "Macro fin refusée: owner=%s caller=%s", active, label,
                    )
                except Exception:
                    pass
                return
            elapsed = int((time.monotonic() - self._lease.started_at) * 1000)
            # An old runner must never reset a NEW runner's synthetic input
            # protection between owns() and end(). Perform its cleanup while
            # holding the same admission lock, only for the exact owner.
            try:
                if on_owner_end is not None:
                    on_owner_end()
            except Exception:
                # A failing synthetic-guard reset must be observable, but
                # must not leave the exclusive macro lease permanently held.
                try:
                    self._logger.exception(
                        "Macro nettoyage propriétaire impossible: action=%s",
                        active,
                    )
                except Exception:
                    pass
            finally:
                self._lease = None
            try:
                self._logger.info("Macro fin: action=%s elapsed_ms=%s", label or active, elapsed)
            except Exception:
                # Cleanup has already completed, regardless of diagnostics.
                pass

    def request_stop(self, reason: str = "stop urgence", *, latch: bool = False) -> None:
        # Wake native and Python waits immediately, even if a worker is
        # finishing while holding the lease lock.
        self.stop_event.set()
        with self._lock:
            # A concurrent try_begin_generation may clear the shared event
            # between our first set() and the lock acquisition. Set it again
            # under the same lock used by admission so Stop always wins that
            # overlap. A genuinely NEW admission after Stop may clear it.
            self.stop_event.set()
            if latch:
                self._emergency_latched = True
            active = self._lease.label if self._lease else ""
        try:
            self._logger.warning("Stop urgence: reason=%s active=%s", reason, active)
        except Exception:
            # Stop is already latched under the admission lock; do not
            # rethrow into a physical hotkey hook.
            pass

    def resume_after_stop(self) -> bool:
        """Explicit Relancer only: never resurrect an interrupted live worker."""
        with self._lock:
            if self._lease is not None:
                return False
            self._emergency_latched = False
            self.stop_event.clear()
            return True

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

    def wait(
        self, duration_ms: int, *,
        interrupted: Callable[[], bool] | None = None,
    ) -> bool:
        # The stop Event is shared across generations; always recheck the
        # actual worker token. An optional pointer collision signal lets
        # Miroir relinquish the cursor during a client-settle delay instead
        # of swallowing additional physical clicks for the whole duration.
        def should_abort() -> bool:
            return self.should_stop() or bool(
                interrupted is not None and interrupted()
            )

        deadline = time.monotonic() + max(0, int(duration_ms)) / 1000.0
        while True:
            if should_abort():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return should_abort()
            # The native hook can swallow another physical DOWN while a
            # Miroir pointer lease is active. React within 5 ms instead of
            # the ordinary 25 ms slice; keep the normal low-wakeup path for
            # all waits without a collision probe.
            slice_seconds = 0.005 if interrupted is not None else 0.025
            if self.stop_event.wait(min(remaining, slice_seconds)):
                return True
