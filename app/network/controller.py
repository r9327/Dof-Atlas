from __future__ import annotations

import threading
from dataclasses import dataclass
from logging import Logger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

from app.core.logger import get_runtime_logger
from app.network.build_fingerprint import ActiveProtocolBuildFingerprintProvider
from app.quest_catalog import QuestCatalog

if TYPE_CHECKING:
    from app.network.bootstrap import NetworkBootstrapResult
    from app.network.progress_bridge import EventApplicationResult
    from app.network.runtime import NetworkEventRuntime
    from app.network.transport import ProtocolMessageSource


@dataclass(frozen=True, slots=True)
class NetworkRuntimeContext:
    quest_catalog: QuestCatalog
    achievement_provider: Any
    guide_provider: Any = None


@dataclass(frozen=True, slots=True)
class NetworkControllerStatus:
    running: bool
    reason: str
    build_sha256: str = ""
    mapping_path: Path | None = None
    catchup_ready: bool = False


class NetworkRuntimeController:
    """Own the optional verified network runtime without making it mandatory.

    Missing handles, mapping or encyclopedia context are normal disabled states,
    not application failures. The controller never opens capture during
    construction and never creates progression stores of its own.
    """

    def __init__(
        self,
        window_handles_provider: Callable[[], Iterable[int]],
        *,
        mapping_roots: Iterable[str | Path] | None = None,
        protocol_source: ProtocolMessageSource | None = None,
        logger: Logger | None = None,
    ) -> None:
        self.window_handles_provider = window_handles_provider
        self.mapping_roots = tuple(mapping_roots) if mapping_roots is not None else None
        self.protocol_source = protocol_source
        self.logger = logger or get_runtime_logger()
        self._fingerprint_provider = ActiveProtocolBuildFingerprintProvider(window_handles_provider)
        self._lock = threading.RLock()
        self._context: NetworkRuntimeContext | None = None
        self._runtime: NetworkEventRuntime | None = None
        self._last_bootstrap: NetworkBootstrapResult | None = None
        self._last_reason = "waiting_context"

    @property
    def is_running(self) -> bool:
        with self._lock:
            runtime = self._runtime
        return bool(runtime is not None and runtime.is_running)

    @property
    def last_bootstrap(self) -> NetworkBootstrapResult | None:
        with self._lock:
            return self._last_bootstrap

    def status(self) -> NetworkControllerStatus:
        with self._lock:
            runtime = self._runtime
            reason = self._last_reason
            if runtime is not None and not runtime.is_running:
                reason = runtime.start_failure_reason or "runtime_stopped"
        return self._status(reason)

    def configure_context(
        self,
        *,
        quest_catalog: QuestCatalog,
        achievement_provider: Any,
        guide_provider: Any = None,
    ) -> None:
        if not isinstance(quest_catalog, QuestCatalog):
            raise TypeError("quest_catalog must be a QuestCatalog")
        if achievement_provider is None:
            raise ValueError("achievement_provider is required for network progression")
        with self._lock:
            self._context = NetworkRuntimeContext(
                quest_catalog=quest_catalog,
                achievement_provider=achievement_provider,
                guide_provider=guide_provider,
            )
            if self._last_reason == "waiting_context":
                self._last_reason = "context_ready"

    def start_if_ready(self) -> NetworkControllerStatus:
        with self._lock:
            runtime = self._runtime
            context = self._context
        if runtime is not None and runtime.is_running:
            return self._status("running")
        if context is None:
            with self._lock:
                self._last_reason = "waiting_context"
            return self._status("waiting_context")

        if runtime is not None:
            if not runtime.stop():
                with self._lock:
                    self._last_reason = "stale_runtime_stop_failed"
                return self._status("stale_runtime_stop_failed")
            with self._lock:
                if self._runtime is runtime:
                    self._runtime = None

        # Import the full capture/decoder/progression composition only when a
        # configured controller actually starts. Home imports this controller
        # before the splash and must not pay for the Windows network stack.
        from app.network.bootstrap import build_windows_network_runtime

        bootstrap = build_windows_network_runtime(
            window_handles_provider=self.window_handles_provider,
            quest_catalog=context.quest_catalog,
            achievement_provider=context.achievement_provider,
            guide_provider=context.guide_provider,
            mapping_roots=self.mapping_roots,
            build_sha256_provider=self._fingerprint_provider,
            protocol_source=self.protocol_source,
            logger=self.logger,
        )
        with self._lock:
            self._last_bootstrap = bootstrap
            self._last_reason = bootstrap.reason
        if not bootstrap.ready or bootstrap.runtime is None:
            return self._status(bootstrap.reason)

        # Historical idr catch-up is deliberately non-authoritative. A verified
        # exact-build live idz runtime must therefore remain usable even when
        # catchup_ready is false; that flag is diagnostic only and must never
        # gate safe S2C live progression.
        candidate = bootstrap.runtime
        if not candidate.start():
            start_reason = str(
                getattr(candidate, "start_failure_reason", "")
                or "runtime_start_failed"
            )
            cleanup_ok = candidate.stop()
            resolved_reason = (
                "runtime_start_cleanup_failed" if not cleanup_ok else start_reason
            )
            with self._lock:
                if not cleanup_ok:
                    self._runtime = candidate
                self._last_reason = resolved_reason
            return self._status(resolved_reason)

        with self._lock:
            self._runtime = candidate
            self._last_reason = "running"
        return self._status("running")

    def stop(self) -> bool:
        with self._lock:
            runtime = self._runtime
        if runtime is None:
            with self._lock:
                self._last_reason = "stopped"
            return True

        stopped = bool(runtime.stop())
        with self._lock:
            if stopped and self._runtime is runtime:
                self._runtime = None
                self._last_reason = "stopped"
            elif not stopped:
                # Keep the reference so a future start cannot create a second
                # reader while the previous thread is still alive.
                self._last_reason = "runtime_stop_failed"
        return stopped

    def drain_results(self, limit: int = 100) -> list[EventApplicationResult]:
        with self._lock:
            runtime = self._runtime
        if runtime is None:
            return []
        return runtime.drain_results(limit)

    def _status(self, reason: str) -> NetworkControllerStatus:
        with self._lock:
            bootstrap = self._last_bootstrap
            running = bool(self._runtime is not None and self._runtime.is_running)
        return NetworkControllerStatus(
            running=running,
            reason=str(reason or ""),
            build_sha256=str(getattr(bootstrap, "build_sha256", "") or ""),
            mapping_path=getattr(bootstrap, "mapping_path", None),
            catchup_ready=bool(getattr(bootstrap, "catchup_ready", False)),
        )


__all__ = [
    "NetworkControllerStatus",
    "NetworkRuntimeContext",
    "NetworkRuntimeController",
]
