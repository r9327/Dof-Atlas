from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Callable


_PROFILE_ENV = "DOFUS_ATLAS_STARTUP_PROFILE"
_PROFILE_FILE_ENV = "DOFUS_ATLAS_STARTUP_PROFILE_FILE"
_PYTHON_BASELINE_ENV = "DOFUS_ATLAS_PYTHON_STARTED_PERF"
_LAUNCHER_STARTED_ENV = "DOFUS_ATLAS_LAUNCHER_STARTED_AT"
_TRUTHY = {"1", "true", "yes", "on"}
_DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "logs" / "startup_profile.jsonl"


class StartupTimeline:
    """Cheap, opt-in startup timeline with first-occurrence markers.

    Marking only touches memory. Disk I/O happens explicitly through ``flush``
    so profiling does not add file writes to every startup milestone.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        output_path: str | Path,
        clock: Callable[[], float] = perf_counter,
        started_at: float | None = None,
        launcher_started_at: str = "",
    ) -> None:
        self.enabled = bool(enabled)
        self.output_path = Path(output_path)
        self._clock = clock
        now = float(clock())
        baseline = now if started_at is None else float(started_at)
        self._started_at = baseline if 0.0 <= baseline <= now else now
        self._last_at = self._started_at
        self._launcher_started_at = str(launcher_started_at or "").strip()
        self._lock = Lock()
        self._names: set[str] = set()
        self._marks: list[dict[str, float | str]] = []

    def mark(self, name: str) -> None:
        if not self.enabled:
            return
        label = str(name or "").strip()
        if not label:
            return
        with self._lock:
            if label in self._names:
                return
            now = float(self._clock())
            elapsed_ms = max(0.0, (now - self._started_at) * 1000.0)
            delta_ms = max(0.0, (now - self._last_at) * 1000.0)
            self._names.add(label)
            self._marks.append(
                {
                    "name": label,
                    "elapsed_ms": round(elapsed_ms, 3),
                    "delta_ms": round(delta_ms, 3),
                }
            )
            self._last_at = now

    def snapshot(self, phase: str) -> dict[str, object]:
        with self._lock:
            marks = [dict(mark) for mark in self._marks]
        total_ms = float(marks[-1]["elapsed_ms"]) if marks else 0.0
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
            "pid": os.getpid(),
            "phase": str(phase or "snapshot"),
            "total_ms": round(total_ms, 3),
            "marks": marks,
        }
        if self._launcher_started_at:
            payload["launcher_started_at"] = self._launcher_started_at
        return payload

    def flush(self, phase: str) -> None:
        if not self.enabled:
            return
        payload = self.snapshot(phase)
        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with self.output_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                stream.write("\n")
        except OSError:
            # Profiling must never make the application fail to start.
            return


def _enabled_from_environment() -> bool:
    return os.environ.get(_PROFILE_ENV, "").strip().casefold() in _TRUTHY


def _output_from_environment() -> Path:
    configured = os.environ.get(_PROFILE_FILE_ENV, "").strip()
    return Path(configured) if configured else _DEFAULT_OUTPUT


def _python_baseline_from_environment() -> float | None:
    raw = os.environ.get(_PYTHON_BASELINE_ENV, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


_STARTUP_TIMELINE = StartupTimeline(
    enabled=_enabled_from_environment(),
    output_path=_output_from_environment(),
    started_at=_python_baseline_from_environment(),
    launcher_started_at=os.environ.get(_LAUNCHER_STARTED_ENV, ""),
)


def startup_mark(name: str) -> None:
    _STARTUP_TIMELINE.mark(name)


def startup_flush(phase: str) -> None:
    _STARTUP_TIMELINE.flush(phase)


def startup_profile_enabled() -> bool:
    return _STARTUP_TIMELINE.enabled


__all__ = [
    "StartupTimeline",
    "startup_flush",
    "startup_mark",
    "startup_profile_enabled",
]
