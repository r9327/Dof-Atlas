from __future__ import annotations

from dataclasses import dataclass
from logging import Logger
from queue import Empty, Queue
from threading import Thread
from time import monotonic, sleep
from typing import Any, Callable, Protocol


class EventPump(Protocol):
    def processEvents(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PreloadTask:
    label: str
    load: Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class PreloadReport:
    payload: dict[str, Any]
    elapsed_seconds: float
    completed_tasks: tuple[str, ...]
    error: str = ""
    timed_out: bool = False


class StartupPreloader:
    """Run a selected lightweight data plan off the Qt thread.

    Tasks share one payload so dependencies (for example Craft selection ->
    Quests) are explicit. The caller pumps Qt events only to keep the splash
    responsive; all catalogue/database work remains on the worker.
    """

    def __init__(
        self,
        event_pump: EventPump,
        *,
        logger: Logger,
        timeout_seconds: float = 90.0,
        poll_seconds: float = 0.1,
    ) -> None:
        self.event_pump = event_pump
        self.logger = logger
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.poll_seconds = max(0.005, min(0.25, float(poll_seconds)))

    def run(
        self,
        tasks: tuple[PreloadTask, ...],
        *,
        status_callback: Callable[[str], None] | None = None,
    ) -> PreloadReport:
        updates: Queue[tuple[str, object]] = Queue()
        started_at = monotonic()

        def worker() -> None:
            payload: dict[str, Any] = {}
            completed: list[str] = []
            try:
                for task in tasks:
                    updates.put(("status", task.label))
                    partial = task.load(payload)
                    if not isinstance(partial, dict):
                        raise TypeError(f"Preload task {task.label!r} did not return a dictionary")
                    _merge_payload(payload, partial)
                    completed.append(task.label)
                updates.put(("done", (payload, tuple(completed))))
            except Exception as exc:
                self.logger.exception("Préchargement initial interrompu à l'étape %s.", completed[-1:] or "début")
                updates.put(("error", (payload, tuple(completed), str(exc))))

        Thread(target=worker, name="DofusAtlas-StartupPreloader", daemon=True).start()
        latest_status = ""
        while True:
            try:
                kind, value = updates.get_nowait()
            except Empty:
                kind = ""
                value = None

            if kind == "status":
                latest_status = str(value or "")
                if status_callback is not None:
                    status_callback(latest_status)
            elif kind == "done":
                payload, completed = value  # type: ignore[misc]
                return PreloadReport(payload, monotonic() - started_at, completed)
            elif kind == "error":
                payload, completed, error = value  # type: ignore[misc]
                return PreloadReport(payload, monotonic() - started_at, completed, error=str(error))

            if monotonic() - started_at >= self.timeout_seconds:
                message = f"Préchargement expiré pendant : {latest_status or 'initialisation'}"
                self.logger.error(message)
                return PreloadReport({}, monotonic() - started_at, (), error=message, timed_out=True)
            self.event_pump.processEvents()
            sleep(self.poll_seconds)


def _merge_payload(target: dict[str, Any], partial: dict[str, Any]) -> None:
    for key, value in partial.items():
        current = target.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            current.update(value)
        else:
            target[key] = value


__all__ = ["PreloadReport", "PreloadTask", "StartupPreloader"]
