from __future__ import annotations

"""Opt-in bounded Python runtime observations for Doctor; never enabled at startup.

Python calls/imports and process/file side effects are observable. Native Qt
signals, C++ allocations and reference ownership are NOT observable without
explicit test instrumentation or separate platform profilers.
"""
import argparse
import gc
import json
from functools import partial, wraps
import runpy
import subprocess
import sys
import threading
import time
import weakref
from pathlib import Path
from typing import Any


# CPython audit hooks cannot be unregistered. Install one dispatcher for the
# process, and point it at at most one opt-in observer using a weak reference.
MAX_SYMBOL_EDGES = 384
_AUDIT_HOOK_INSTALLED = False
_ACTIVE_AUDIT_REF: weakref.ReferenceType | None = None


def _audit_dispatch(event: str, args: tuple[Any, ...]) -> None:
    reference = _ACTIVE_AUDIT_REF
    observer = reference() if reference else None
    if observer is not None:
        observer._audit_event(event, args)


class RuntimeObserver:
    def __init__(self, root: Path, *, max_events: int = 5000):
        if not 1 <= max_events <= 50000:
            raise ValueError("max_events must be 1..50000")
        self.root = root.resolve()
        self.candidate_sha = self._head_sha()
        self.worktree_clean_before = self._clean_worktree()
        self.worktree_clean = self.worktree_clean_before
        self.max_events = max_events
        self.events: list[dict[str, Any]] = []
        self._edges: set[tuple[str, str]] = set()
        self._symbol_edges: set[tuple[str, str, int, str, str]] = set()
        self._symbol_overflow = False
        self._watched: list[tuple[str, str, weakref.ReferenceType]] = []
        self._overflow = False
        self._active = False
        self._busy = False
        self._old_profile = None
        self._old_thread_profile = None
        self.started_ns = 0

    def _head_sha(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--verify", "HEAD"], cwd=self.root,
                text=True, capture_output=True, timeout=5, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        value = result.stdout.strip()
        return value if result.returncode == 0 and len(value) == 40 else None

    def _clean_worktree(self) -> bool:
        """Unknown Git state fails closed; ignored runtime output is not source."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain=v1", "--untracked-files=all"],
                cwd=self.root, text=True, capture_output=True, check=False, timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 and not result.stdout.strip()

    def _path(self, value: Any) -> str | None:
        if not isinstance(value, (str, bytes)):
            return None
        try:
            path = Path(value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value)
            resolved = path.resolve()
            rel = resolved.relative_to(self.root).as_posix()
            if rel.startswith(".ai/runtime/"):
                return None
            return rel
        except (OSError, ValueError, RuntimeError):
            return None

    def _record(self, event: dict[str, Any]) -> None:
        if not self._active:
            return
        if len(self.events) >= self.max_events:
            self._overflow = True
            return
        self.events.append(event)

    def _profile(self, frame: Any, event: str, arg: Any) -> None:
        if not self._active:
            # threading.setprofile controls *future* threads; a worker created
            # during tracing keeps its thread-local hook after context exit.
            # Remove that residual hook on its next event, restoring exactly
            # the previous thread-default profile without any background timer.
            current = sys.getprofile()
            if (getattr(current, "__self__", None) is self
                    and getattr(current, "__func__", None) is RuntimeObserver._profile):
                sys.setprofile(self._old_thread_profile)
            return
        # Once the bounded event log is full, do not keep expanding the
        # deduplication sets (or pay for source path resolution).
        if self._overflow and len(self.events) >= self.max_events:
            return
        if self._busy or event not in {"call", "c_call"}:
            return
        self._busy = True
        try:
            if event == "c_call":
                caller = self._path(frame.f_code.co_filename)
                name = getattr(arg, "__name__", None)
                module = type(getattr(arg, "__self__", None)).__module__
                if (caller and caller.endswith(".py") and
                        (module.startswith("PySide6.") or module.startswith("shiboken6")) and
                        name in {"connect", "disconnect", "start", "stop"}):
                    self._record({"type": "qt_c_call_site", "source": caller,
                                  "action": name, "confidence": "CALL_SITE_ONLY"})
                return
            target = self._path(frame.f_code.co_filename)
            caller = self._path(frame.f_back.f_code.co_filename) if frame.f_back else None
            if target and caller and target.endswith(".py") and caller.endswith(".py"):
                key = caller, target
                if key not in self._edges:
                    if len(self.events) >= self.max_events:
                        self._overflow = True
                        return
                    self._edges.add(key)
                    self._record({"type": "python_call_edge", "source": caller, "target": target})
                previous = frame.f_back
                origin_name = previous.f_code.co_qualname if previous else "<unknown>"
                destination_name = frame.f_code.co_qualname
                origin_line = previous.f_lineno if previous else 0
                symbol_key = (caller, origin_name, origin_line, target, destination_name)
                if symbol_key not in self._symbol_edges:
                    if len(self._symbol_edges) >= MAX_SYMBOL_EDGES:
                        self._symbol_overflow = True
                    elif len(self.events) < self.max_events:
                        self._symbol_edges.add(symbol_key)
                        self._record({
                            "type": "python_symbol_call",
                            "source": caller, "caller_symbol": origin_name,
                            "caller_line": origin_line, "target": target,
                            "callee_symbol": destination_name,
                            "callee_line": frame.f_code.co_firstlineno,
                            "confidence": "OBSERVED_CALL_ENTRY",
                        })
                    else:
                        self._overflow = True
        finally:
            self._busy = False

    def _audit_event(self, event: str, args: tuple[Any, ...]) -> None:
        if not self._active or self._busy:
            return
        if self._overflow and len(self.events) >= self.max_events:
            return
        kind = {
            "open": "file_open", "os.remove": "file_remove",
            "os.rename": "file_rename", "subprocess.Popen": "process_spawn",
            "import": "import_attempt",
        }.get(event)
        if kind is None:
            return
        self._busy = True
        try:
            # Audit callback stack: _audit_event <- _audit_dispatch <- source.
            # Avoid attributing every import/open to Doctor's dispatcher itself.
            caller = None
            try:
                frame = sys._getframe(2)
            except ValueError:
                frame = None
            for _ in range(12):
                if frame is None:
                    break
                current = self._path(frame.f_code.co_filename)
                if current and current.endswith(".py") and current != "tools/atlas_doctor_lib/runtime_observation.py":
                    caller = current
                    break
                frame = frame.f_back
            if caller is None:
                return
            if event in {"open", "os.remove", "os.rename"}:
                target = self._path(args[0]) if args else None
                if target is None:
                    return
                self._record({"type": kind, "source": caller, "target": target})
            elif event == "import":
                name = args[0] if args else None
                if isinstance(name, str):
                    self._record({"type": kind, "source": caller, "module": name})
            else:
                # Do not retain process arguments, environment or user information.
                self._record({"type": kind, "source": caller})
        finally:
            self._busy = False

    def connect_qt_signal(self, signal: Any, callback: Any) -> Any:
        """Explicit Qt scenario wrapper; no global monkeypatch or auto-attach.

        A successful connect call proves only that registration was attempted
        without raising; it does not prove future slot delivery or ownership.
        """
        if not self._active:
            raise RuntimeError("Qt connection capture requires an active observer")
        caller = self._path(sys._getframe(1).f_code.co_filename)
        method = callback
        # functools.partial is common for Qt bindings; unwrap without
        # invoking the callback, and cap pathological nested partials.
        for _ in range(6):
            if isinstance(method, partial):
                method = method.func
                continue
            method = getattr(method, "__func__", method)
            break
        code = getattr(method, "__code__", None)
        receiver_file = self._path(code.co_filename) if code is not None else None
        result = signal.connect(callback)
        if caller:
            entry = {
                "type": "qt_signal_connect_returned",
                "source": caller,
                "confidence": "CONNECT_RETURNED_NOT_CALLBACK_INVOKED",
            }
            if receiver_file:
                entry["target"] = receiver_file
            self._record(entry)
        return result


    def wrap_qt_slot(self, callback: Any) -> Any:
        """Opt-in scenario wrapper: prove entry of a Python callback, not Qt ownership.

        Register the returned callable explicitly; no existing connection is
        monkeypatched. Native Qt signal signatures must be checked per scenario.
        """
        if not self._active:
            raise RuntimeError("Qt slot instrumentation requires an active observer")
        if not callable(callback):
            raise TypeError("Qt slot must be callable")
        source = self._path(sys._getframe(1).f_code.co_filename)
        function = callback
        for _ in range(6):
            if isinstance(function, partial):
                function = function.func
                continue
            function = getattr(function, "__func__", function)
            break
        code = getattr(function, "__code__", None)
        target = self._path(code.co_filename) if code is not None else None
        reference = weakref.ref(self)

        @wraps(callback)
        def observed_slot(*args: Any, **kwargs: Any) -> Any:
            observer = reference()
            if observer is not None and observer._active and source and target:
                observer._record({
                    "type": "qt_callback_invoked", "source": source,
                    "target": target, "confidence": "WRAPPED_PYTHON_CALLBACK_ENTERED",
                })
            return callback(*args, **kwargs)

        return observed_slot

    def watch(self, obj: Any, *, label: str, kind: str = "object") -> bool:
        """Explicit, non-owning watch for Qt workers, timers or cache holders."""
        try:
            reference = weakref.ref(obj)
        except TypeError:
            return False
        self._watched.append((str(label)[:100], str(kind)[:40], reference))
        return True

    def mark(self, kind: str, *, source: str, target: str | None = None) -> None:
        """Explicit instrumentation for Qt signal connect/disconnect or lifecycle events."""
        if kind not in {"qt_connect", "qt_disconnect", "worker_start", "worker_stop", "cache_release"}:
            raise ValueError("Unexpected runtime marker type")
        a = self._path(source)
        b = self._path(target) if target else None
        if a:
            self._record({"type": kind, "source": a, **({"target": b} if b else {})})

    def __enter__(self) -> "RuntimeObserver":
        global _AUDIT_HOOK_INSTALLED, _ACTIVE_AUDIT_REF
        if self._active:
            raise RuntimeError("observer already started")
        active = _ACTIVE_AUDIT_REF() if _ACTIVE_AUDIT_REF else None
        if active is not None and active._active:
            raise RuntimeError("another observer is already recording")
        if not _AUDIT_HOOK_INSTALLED:
            sys.addaudithook(_audit_dispatch)
            _AUDIT_HOOK_INSTALLED = True
        self.started_ns = time.monotonic_ns()
        self._old_profile = sys.getprofile()
        self._old_thread_profile = threading.getprofile()
        _ACTIVE_AUDIT_REF = weakref.ref(self)
        self._active = True
        try:
            sys.setprofile(self._profile)
            threading.setprofile(self._profile)
        except BaseException:
            sys.setprofile(self._old_profile)
            threading.setprofile(self._old_thread_profile)
            self._active = False
            _ACTIVE_AUDIT_REF = None
            raise
        return self

    def __exit__(self, *_errors: Any) -> None:
        global _ACTIVE_AUDIT_REF
        self._active = False
        sys.setprofile(self._old_profile)
        threading.setprofile(self._old_thread_profile)
        if _ACTIVE_AUDIT_REF is not None and _ACTIVE_AUDIT_REF() is self:
            _ACTIVE_AUDIT_REF = None
        # A trace made while editing files must never appear exact-SHA.
        self.worktree_clean = (
            self.worktree_clean_before and self._clean_worktree()
            and self.candidate_sha is not None
            and self._head_sha() == self.candidate_sha
        )

    def report(self, *, collect: bool = False) -> dict[str, Any]:
        if collect:
            gc.collect()
        watched = [{"label": label, "kind": kind, "still_referenced": ref() is not None}
                   for label, kind, ref in self._watched]
        return {
            "schema_version": 1, "kind": "doctor_runtime_observation",
            "candidate_sha": self.candidate_sha,
            "worktree_clean": self.worktree_clean,
            "root": str(self.root), "duration_ms": round((time.monotonic_ns() - self.started_ns) / 1e6, 3)
            if self.started_ns else 0.0,
            "status": "TRUNCATED" if self._overflow else "RECORDED",
            "events": self.events, "events_captured": len(self.events),
            "truncated": self._overflow, "symbol_edges_truncated": self._symbol_overflow,
            "symbol_edges_recorded": len(self._symbol_edges),
            "object_watches": watched,
            "lifecycle": summarize_runtime_lifecycle({"events": self.events, "truncated": self._overflow}),
            "limits": [
                "Qt connections require explicit connect_qt_signal instrumentation; callback execution and native ownership remain unknown.",
                "Still referenced objects may be intentionally retained; not a proof of a memory leak.",
                "No arguments, variable values or outside-repository paths collected.",
                "Symbol call sites are bounded, observed positives only; no negative reachability proof.",
            ],
        }


def summarize_runtime_lifecycle(trace: dict[str, Any]) -> dict[str, Any]:
    """Explicit lifecycle markers, without claiming Qt ownership or leaks."""
    events = trace.get("events")
    if not isinstance(events, list) or len(events) > 50000:
        return {"status": "REVIEW", "reason": "Missing or oversized runtime events",
                "truncated": True, "proof_of_memory_leak": False,
                "worker_starts_unpaired": [], "cache_release_sources": []}
    pending: dict[tuple[str, str], int] = {}
    releases: set[str] = set()
    started = stopped = unmatched = 0
    for event in events:
        if not isinstance(event, dict):
            return {"status": "REVIEW", "reason": "Malformed runtime event",
                    "truncated": True, "proof_of_memory_leak": False,
                    "worker_starts_unpaired": [], "cache_release_sources": []}
        kind = event.get("type")
        if kind not in {"worker_start", "worker_stop", "cache_release"}:
            continue
        source = event.get("source")
        target = event.get("target") or ""
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if kind == "cache_release":
            releases.add(source)
            continue
        key = (source, target)
        if kind == "worker_start":
            started += 1
            pending[key] = pending.get(key, 0) + 1
        else:
            stopped += 1
            if pending.get(key, 0):
                pending[key] -= 1
            else:
                unmatched += 1
    open_workers = [
        {"source": source, "target": target, "unpaired_starts": count}
        for (source, target), count in sorted(pending.items()) if count > 0
    ]
    return {
        "status": "REVIEW" if trace.get("truncated") or open_workers or unmatched else "OBSERVED",
        "worker_start_events": started, "worker_stop_events": stopped,
        "unmatched_stop_events": unmatched,
        "worker_starts_unpaired": open_workers[:80],
        "cache_release_sources": sorted(releases)[:80],
        "truncated": bool(trace.get("truncated") or len(open_workers) > 80 or len(releases) > 80),
        "proof_of_memory_leak": False,
        "limits": "Markers are explicit and opt-in; an open worker at trace end may be intentional. Native Qt ownership and memory remain unproven.",
    }


def compare_runtime_to_graph(trace: dict[str, Any], graph: dict[str, Any]) -> dict[str, Any]:
    nodes = {node["id"]: node for node in graph.get("nodes", [])}
    known = set()
    for edge in graph.get("links", []):
        source, target = nodes.get(edge.get("source")), nodes.get(edge.get("target"))
        if source and target:
            a, b = source.get("source_file"), target.get("source_file")
            if isinstance(a, str) and isinstance(b, str):
                known.add((a, b))
    trace_sha, graph_sha = trace.get("candidate_sha"), graph.get("built_at_commit")
    trusted = (
        isinstance(trace_sha, str) and isinstance(graph_sha, str)
        and len(graph_sha) == 40 and trace_sha == graph_sha
        and trace.get("worktree_clean") is True and not trace.get("truncated")
    )
    # Retain raw observations for forensic review, but never call unverified
    # traces proof of actual current static relationships.
    observed = {(e["source"], e["target"]) for e in trace.get("events", [])
                if e.get("type") == "python_call_edge"
                and isinstance(e.get("source"), str) and isinstance(e.get("target"), str)}
    verified = observed if trusted else set()
    return {
        "status": "PASS" if trusted else "REVIEW",
        "runtime_evidence_valid": trusted,
        "observed_runtime_edges": len(observed),
        "static_edges_with_runtime_evidence": len(verified & known),
        "observed_unmapped_edges": [{"source": a, "target": b}
                                    for a, b in sorted(verified - known)[:50]],
        "static_coverage_claim": False,
        "notes": "An exact commit and clean worktree are required to validate runtime edges. No event never proves dead code.",
    }


def run_traced_module(root: Path, module: str, output: Path, *, max_events: int = 5000) -> dict[str, Any]:
    if not module or not all(part.isidentifier() for part in module.split(".")):
        raise ValueError("Expected a dotted module, not arbitrary code")
    root = root.resolve()
    if not (root / (module.replace(".", "/") + ".py")).is_file() and not (
        root / module.replace(".", "/") / "__main__.py"
    ).is_file():
        raise ValueError("Module must exist inside the repository")
    output = output.resolve()
    if not output.is_relative_to(root / ".ai" / "runtime"):
        raise ValueError("Trace output must be inside .ai/runtime")
    observer = RuntimeObserver(root, max_events=max_events)
    try:
        with observer:
            runpy.run_module(module, run_name="__main__", alter_sys=True)
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(observer.report(), indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return observer.report()
