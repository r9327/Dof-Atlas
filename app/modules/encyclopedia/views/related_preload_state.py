from __future__ import annotations

from enum import Enum


class RelatedPreloadState(str, Enum):
    IDLE = "idle"
    LOADING = "loading"
    READY = "ready"
    FAILED = "failed"


class RelatedPreloadGate:
    """Small terminal state machine for the related-data background preload."""

    def __init__(self, *, ready: bool = False) -> None:
        self._state = RelatedPreloadState.READY if ready else RelatedPreloadState.IDLE
        self._attempts = 0

    @property
    def state(self) -> RelatedPreloadState:
        return self._state

    @property
    def attempts(self) -> int:
        return self._attempts

    def begin(self) -> bool:
        if self._state is not RelatedPreloadState.IDLE:
            return False
        self._state = RelatedPreloadState.LOADING
        self._attempts += 1
        return True

    def mark_ready(self) -> None:
        self._state = RelatedPreloadState.READY

    def mark_failed(self) -> None:
        self._state = RelatedPreloadState.FAILED
