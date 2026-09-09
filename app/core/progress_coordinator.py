from __future__ import annotations

import threading
from pathlib import Path


class ProgressFileCoordinator:
    """Process-local coordination for services sharing the same progress file.

    Each service instance may keep its own parsed payload, but all instances for
    one path share the same lock and generation counter. A successful mutation
    increments the generation so stale readers can refresh lazily before serving
    their next value.
    """

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self._generation = 0

    @property
    def generation(self) -> int:
        with self.lock:
            return self._generation

    def mark_changed(self) -> int:
        with self.lock:
            self._generation += 1
            return self._generation


_REGISTRY_LOCK = threading.RLock()
_COORDINATORS: dict[str, ProgressFileCoordinator] = {}


def _path_key(path: Path) -> str:
    target = Path(path)
    try:
        return str(target.resolve())
    except OSError:
        return str(target.absolute())


def coordinator_for(path: Path) -> ProgressFileCoordinator:
    key = _path_key(Path(path))
    with _REGISTRY_LOCK:
        coordinator = _COORDINATORS.get(key)
        if coordinator is None:
            coordinator = ProgressFileCoordinator()
            _COORDINATORS[key] = coordinator
        return coordinator


__all__ = ["ProgressFileCoordinator", "coordinator_for"]
