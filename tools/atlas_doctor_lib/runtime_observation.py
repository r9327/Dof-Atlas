from __future__ import annotations

"""Opt-in bounded Python runtime observations for Doctor; never enabled at startup.

Python calls/imports and process/file side effects are observable. Native Qt
signals, C++ allocations and reference ownership are NOT observable without
explicit test instrumentation or separate platform profilers.
"""
import argparse
import hashlib
import math
import re
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
MAX_WEAK_WATCHES = 128
_AUDIT_HOOK_INSTALLED = False
_ACTIVE_AUDIT_REF: weakref.ReferenceType | None = None


def _audit_dispatch(event: str, args: tuple[Any, ...]) -> None:
    reference = _ACTIVE_AUDIT_REF
    observer = reference() if reference else None
    if observer is not None:
        observer._audit_event(event, args)


def active_observer() -> RuntimeObserver | None:
    """Return the opt-in recorder only while an explicit trace is running."""
    ref = _ACTIVE_AUDIT_REF
    current = ref() if ref else None
    return current if current is not None and current._active else None


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
        self._json_read_tokens: set[str] = set()
        self._json_serial = 0
        self._qt_thread_serial = 0
        self._qt_destroy_serial = 0
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
        for _ in range(8):
            if isinstance(method, partial):
                method = method.func
                continue
            wrapped = getattr(method, "__wrapped__", None)
            if wrapped is not None and wrapped is not method:
                method = wrapped
                continue
            original = getattr(method, "__func__", None)
            if original is not None and original is not method:
                method = original
                continue
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

    def watch_qt_destroyed(self, obj: Any, *, label: str) -> bool:
        """Opt-in QObject.destroyed signal evidence, without retaining QObject.

        Signal delivery is observable, not wrapper garbage collection, C++
        ownership or proof that WebEngine released its external processes.
        """
        if not self._active:
            raise RuntimeError("Qt destruction watch requires an active observer")
        if self._qt_destroy_serial >= MAX_WEAK_WATCHES:
            return False
        source = self._path(sys._getframe(1).f_code.co_filename)
        signal = getattr(obj, "destroyed", None)
        connect = getattr(signal, "connect", None)
        if source is None or not callable(connect):
            return False
        reference = weakref.ref(self)
        safe_label = str(label)[:100]
        self._qt_destroy_serial += 1
        token = f"qt-destroy-{self._qt_destroy_serial}"

        def destroyed(*_args: Any) -> None:
            observer = reference()
            if observer is not None and observer._active:
                observer._record({
                    "type": "qt_destroyed_observed", "source": source,
                    "label": safe_label, "qt_watch_token": token,
                    "confidence": "QT_DESTROYED_SIGNAL_DELIVERED",
                })

        try:
            connect(destroyed)
        except (TypeError, RuntimeError):
            return False
        self._record({"type": "qt_destroy_watch_registered", "source": source,
                      "label": safe_label, "qt_watch_token": token,
                      "confidence": "QT_DESTROYED_SIGNAL_CONNECTED"})
        return True

    def watch_qt_thread(self, thread: Any, *, label: str) -> bool:
        """Connect to genuine Qt started/finished signals when explicitly asked.

        No strong reference to the QThread is retained. Signal callbacks hold
        only a weak observer reference; they cannot establish thread ownership.
        """
        if not self._active:
            raise RuntimeError("Qt worker watch requires an active observer")
        if self._qt_thread_serial >= 128:
            return False
        source = self._path(sys._getframe(1).f_code.co_filename)
        start = getattr(getattr(thread, "started", None), "connect", None)
        finish = getattr(getattr(thread, "finished", None), "connect", None)
        if source is None or not callable(start) or not callable(finish):
            return False
        self._qt_thread_serial += 1
        token = f"qt-thread-{self._qt_thread_serial}"
        watcher = weakref.ref(self)
        safe_label = str(label)[:80]

        def record(kind: str, confidence: str) -> None:
            observer = watcher()
            if observer is not None and observer._active:
                observer._record({
                    "type": kind, "source": source, "target": source,
                    "label": safe_label, "qt_worker_token": token,
                    "confidence": confidence,
                })

        try:
            start(lambda: record("qt_worker_started", "QT_STARTED_SIGNAL_DELIVERED"))
            finish(lambda: record("qt_worker_finished", "QT_FINISHED_SIGNAL_DELIVERED"))
        except (TypeError, RuntimeError):
            # Failed or partial connections do not create positive observations.
            return False
        self.watch(thread, label=label, kind="qobject")
        return True

    def watch(self, obj: Any, *, label: str, kind: str = "object") -> bool:
        """Explicit, non-owning watch for Qt workers, timers or cache holders."""
        if len(self._watched) >= MAX_WEAK_WATCHES:
            return False
        try:
            reference = weakref.ref(obj)
        except TypeError:
            return False
        self._watched.append((str(label)[:100], str(kind)[:40], reference))
        return True

    def read_json(self, relative_path: str | Path) -> tuple[Any, str]:
        """Decode a repo JSON explicitly and record *successful* decode, no content.

        Test and opt-in scenarios only; this does not intercept app file APIs.
        Caller must explicitly hand off the returned token after UI binding.
        """
        if not self._active:
            raise RuntimeError("JSON read tracing requires an active observer")
        candidate = Path(relative_path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("Expected a repository-relative JSON path")
        original = self.root / candidate
        current = self.root
        for part in candidate.parts:
            current = current / part
            if current.is_symlink():
                raise ValueError("Symlinked JSON path forbidden")
        selected = original.resolve()
        if (not selected.is_relative_to(self.root) or selected.suffix.lower() != ".json"
                or not selected.is_file() or selected.stat().st_size > 4_000_000):
            raise ValueError("JSON file absent, outside repository or larger than 4 MB")
        # Parsing exceptions propagate. Emit no successful read event on failure.
        payload = json.loads(selected.read_text(encoding="utf-8-sig"))
        self._json_serial += 1
        token = f"json-{self._json_serial}"
        relative = selected.relative_to(self.root).as_posix()
        source = self._path(sys._getframe(1).f_code.co_filename)
        if source and len(self.events) < self.max_events:
            self._json_read_tokens.add(token)
            self._record({"type": "json_decoded", "source": source,
                          "target": relative, "token": token,
                          "confidence": "JSON_DECODE_RETURNED"})
        return payload, token

    def mark_ui_bound(self, token: str) -> bool:
        """Positive marker after scenario code actually binds decoded data to UI.

        Not proof that native Qt rendered a frame or that the UI is visible.
        """
        if not self._active or token not in self._json_read_tokens or len(self.events) >= self.max_events:
            return False
        source = self._path(sys._getframe(1).f_code.co_filename)
        if not source or not source.endswith(".py"):
            return False
        self._record({"type": "json_ui_bound", "source": source, "token": token,
                      "confidence": "EXPLICIT_UI_BINDING_MARKER"})
        return True

    def bind_json_label_text(self, token: str, label: Any, value: str) -> bool:
        """Explicitly perform + verify QLabel setText without logging content.

        The returned event proves a Python/Qt text-setter returned and matches
        the expected value, not that a frame was painted or a user saw it.
        """
        if not self._active or token not in self._json_read_tokens:
            return False
        if len(self.events) >= self.max_events or not isinstance(value, str):
            return False
        set_text = getattr(label, "setText", None)
        get_text = getattr(label, "text", None)
        if not callable(set_text) or not callable(get_text):
            return False
        # Prefer the source file defining the real owner QWidget (e.g.
        # EquipmentPage) over an injected scenario module or native QLabel.
        source = None
        owner = getattr(label, "parentWidget", None)
        if callable(owner):
            try:
                parent = owner()
                if parent is not None:
                    import inspect
                    defining_file = inspect.getsourcefile(type(parent))
                    source = self._path(defining_file) if defining_file else None
            except (OSError, TypeError, RuntimeError, ValueError):
                source = None
        if not source:
            source = self._path(sys._getframe(1).f_code.co_filename)
        set_text(value)
        if get_text() != value or not source or not source.endswith(".py"):
            return False
        self._record({
            "type": "json_ui_bound", "source": source, "token": token,
            "confidence": "EXPLICIT_QT_LABEL_SETTEXT_RETURNED",
        })
        return True

    def snapshot_watches(self, *, label: str) -> dict[str, int]:
        """Opt-in weakref counts: reference liveness, never leak/ownership proof."""
        if not self._active:
            raise RuntimeError("Weak reference snapshots require an active observer")
        alive = sum(ref() is not None for _, _, ref in self._watched)
        summary = {"watched": len(self._watched), "alive": alive,
                   "not_referenced": len(self._watched) - alive}
        source = self._path(sys._getframe(1).f_code.co_filename)
        if source:
            self._record({"type": "weak_watch_snapshot", "source": source,
                          "label": str(label)[:60], **summary,
                          "confidence": "WEAKREF_LIVENESS_ONLY"})
        return summary

    def snapshot_qt_objects(self, *, label: str) -> dict[str, Any]:
        """Distinguish live Python wrappers from native C++ Qt validity.

        This observes only explicitly weak-watched Qt objects while tracing.
        Invalid wrappers do not by themselves establish leaked memory.
        """
        if not self._active:
            raise RuntimeError("Qt object snapshot requires an active observer")
        try:
            from shiboken6 import isValid
        except ImportError:
            result: dict[str, Any] = {
                "status": "UNAVAILABLE", "reason": "shiboken6_not_installed",
                "not_memory_leak_proof": True,
            }
        else:
            native_valid = native_invalid = python_gone = inspect_errors = 0
            parent_present = parent_absent = parent_errors = webengine_wrappers = 0
            for _, kind, reference in self._watched:
                if kind not in {"qt", "qwidget", "qobject"}:
                    continue
                obj = reference()
                if obj is None:
                    python_gone += 1
                    continue
                try:
                    if isValid(obj):
                        native_valid += 1
                        if type(obj).__name__.startswith("QWebEngine"):
                            webengine_wrappers += 1
                        parent_getter = getattr(obj, "parent", None)
                        if callable(parent_getter):
                            try:
                                parent = parent_getter()
                                if parent is None:
                                    parent_absent += 1
                                elif isValid(parent):
                                    parent_present += 1
                                else:
                                    parent_errors += 1
                            except (TypeError, RuntimeError, ValueError):
                                parent_errors += 1
                    else:
                        native_invalid += 1
                except (TypeError, RuntimeError, ValueError):
                    inspect_errors += 1
            result = {
                "status": "REVIEW" if inspect_errors or parent_errors else "OBSERVED",
                "native_valid_wrappers": native_valid,
                "parent_present_native_valid": parent_present,
                "parent_absent_at_snapshot": parent_absent,
                "parent_inspection_errors": parent_errors,
                "webengine_wrappers_sampled": webengine_wrappers,
                "parent_is_not_full_ownership_proof": True,
                "native_invalid_wrappers": native_invalid,
                "python_wrappers_collected": python_gone,
                "inspect_errors": inspect_errors,
                "truncated": len(self._watched) >= MAX_WEAK_WATCHES,
                "not_memory_leak_proof": True,
            }
        source = self._path(sys._getframe(1).f_code.co_filename)
        if source:
            self._record({"type": "qt_native_snapshot", "source": source,
                          "label": str(label)[:60], **result})
        return result

    def snapshot_process_tree(self, *, label: str) -> dict[str, Any]:
        """Opt-in psutil process-tree sample (no arguments or personal data).

        QtWebEngine child process names are only hints; process ownership and
        Qt object lifecycle are not established by an RSS sample.
        """
        if not self._active:
            raise RuntimeError("Process snapshot requires an active observer")
        try:
            import psutil
            root_process = psutil.Process()
            children = root_process.children(recursive=True)
            truncated = len(children) > 64
            selected = [root_process, *children[:64]]
            total_bytes = 0
            observed = 0
            webengine = 0
            errors = 0
            cpu_total = 0.0
            cpu_measured = 0
            identities: list[str] = []
            for process in selected:
                try:
                    total_bytes += int(process.memory_info().rss)
                    name = process.name().lower()
                    webengine += int("qtwebengineprocess" in name)
                    observed += 1
                    # CPU times are cumulative kernel counters, not utilization.
                    cpu_getter = getattr(process, "cpu_times", None)
                    if callable(cpu_getter):
                        times = cpu_getter()
                        seconds = float(times.user) + float(times.system)
                        if math.isfinite(seconds) and seconds >= 0:
                            cpu_total += seconds
                            cpu_measured += 1
                    pid = getattr(process, "pid", None)
                    created = getattr(process, "create_time", None)
                    if isinstance(pid, int) and callable(created):
                        identities.append(f"{pid}:{created():.5f}")
                except (psutil.Error, OSError, AttributeError, ValueError):
                    errors += 1
            identity_digest = (hashlib.sha256("|".join(sorted(identities)).encode("utf-8")).hexdigest()[:24]
                               if identities and len(identities) == observed and not errors else None)
            result = {"status": "REVIEW" if errors or truncated else "OBSERVED",
                      "rss_tree_bytes": total_bytes, "processes_counted": observed,
                      "webengine_children_named": webengine, "truncated": truncated,
                      "processes_inaccessible": errors,
                      "cpu_time_cumulative_seconds": round(cpu_total, 6) if cpu_measured == observed and observed else None,
                      "process_group_fingerprint": identity_digest,
                      "not_native_qt_ownership_proof": True}
        except (ImportError, OSError, RuntimeError) as exc:
            result = {"status": "UNAVAILABLE", "reason": type(exc).__name__,
                      "not_native_qt_ownership_proof": True}
        source = self._path(sys._getframe(1).f_code.co_filename)
        if source:
            self._record({"type": "process_tree_snapshot", "source": source,
                          "label": str(label)[:60], **result})
        return result

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


def summarize_process_checkpoints(trace: dict[str, Any] | None) -> dict[str, Any]:
    """Compare existing opt-in process samples; never measure while reading.

    CPU is cumulative and comparable only when the same process identities
    were sampled; no sampling delays, workload claims or peak-memory inference.
    """
    empty = {"status": "NOT_PROVIDED", "samples": [], "comparisons": [],
             "peak_rss_proven": False, "tests_executed": False}
    if not isinstance(trace, dict) or not isinstance(trace.get("events"), list):
        return empty
    events = trace["events"]
    if trace.get("truncated") is not False or len(events) > 50000:
        return {**empty, "status": "INCOMPLETE"}
    samples: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for row in events:
        if not isinstance(row, dict) or row.get("type") != "process_tree_snapshot":
            continue
        if len(samples) >= 32:
            return {**empty, "status": "TRUNCATED", "samples": samples,
                    "comparisons": comparisons}
        rss = row.get("rss_tree_bytes")
        cpu = row.get("cpu_time_cumulative_seconds")
        digest = row.get("process_group_fingerprint")
        if (row.get("status") != "OBSERVED" or not isinstance(rss, int)
                or isinstance(rss, bool) or rss < 0 or rss > 100_000_000_000
                or not isinstance(row.get("processes_counted"), int)
                or row.get("processes_counted", 0) <= 0):
            samples.append({"label": str(row.get("label", ""))[:60], "status": "UNAVAILABLE"})
            previous = None
            continue
        sample = {
            "label": str(row.get("label", ""))[:60], "rss_tree_bytes": rss,
            "processes_counted": row["processes_counted"],
            "webengine_children_named": row.get("webengine_children_named", 0),
            "cpu_time_cumulative_seconds": cpu if isinstance(cpu, (int, float))
            and not isinstance(cpu, bool) and math.isfinite(cpu) and cpu >= 0 else None,
            "process_group_fingerprint": digest if isinstance(digest, str) and len(digest) == 24 else None,
        }
        samples.append(sample)
        if previous is not None:
            same = (sample["process_group_fingerprint"] is not None
                    and sample["process_group_fingerprint"] == previous["process_group_fingerprint"])
            if same:
                old_cpu, new_cpu = previous["cpu_time_cumulative_seconds"], sample["cpu_time_cumulative_seconds"]
                comparisons.append({
                    "from": previous["label"], "to": sample["label"],
                    "rss_delta_bytes": rss - previous["rss_tree_bytes"],
                    "cpu_time_delta_seconds": round(new_cpu - old_cpu, 6)
                    if old_cpu is not None and new_cpu is not None and new_cpu >= old_cpu else None,
                    "same_sampled_process_set": True,
                    "peak_rss_proven": False,
                })
            else:
                comparisons.append({"from": previous["label"], "to": sample["label"],
                                    "same_sampled_process_set": False,
                                    "rss_delta_bytes": None, "cpu_time_delta_seconds": None,
                                    "peak_rss_proven": False})
        previous = sample
    return {"status": "REVIEW" if any(x.get("status") == "UNAVAILABLE" for x in samples) else
            "OBSERVED_SNAPSHOTS" if samples else "NOT_PROVIDED",
            "samples": samples, "comparisons": comparisons,
            "peak_rss_proven": False, "tests_executed": False,
            "limits": "Up to 32 opt-in snapshot events, no CPU percentage, no native WebEngine ownership, no peak RAM or certified benchmark.",
    }


def summarize_runtime_lifecycle(trace: dict[str, Any]) -> dict[str, Any]:
    """Explicit lifecycle markers, without claiming Qt ownership or leaks."""
    events = trace.get("events")
    if not isinstance(events, list) or len(events) > 50000:
        return {"status": "REVIEW", "reason": "Missing or oversized runtime events",
                "truncated": True, "proof_of_memory_leak": False,
                "worker_starts_unpaired": [], "cache_release_sources": []}
    pending: dict[tuple[str, str], int] = {}
    qt_pending: dict[tuple[int, str, str], int] = {}
    qt_started = qt_finished = qt_unmatched = 0
    qt_parent_snapshots: list[dict[str, Any]] = []
    releases: set[str] = set()
    destroyed_sources: set[str] = set()
    destroyed_count = 0
    qt_watch_registered: dict[tuple[int, str, str], str] = {}
    qt_watch_completed: set[tuple[int, str, str]] = set()
    started = stopped = unmatched = 0
    for event in events:
        if not isinstance(event, dict):
            return {"status": "REVIEW", "reason": "Malformed runtime event",
                    "truncated": True, "proof_of_memory_leak": False,
                    "worker_starts_unpaired": [], "cache_release_sources": []}
        kind = event.get("type")
        if kind == "qt_native_snapshot":
            if len(qt_parent_snapshots) < 32:
                qt_parent_snapshots.append({
                    "trace_group": event.get("_trace_group", 0),
                    "label": str(event.get("label", ""))[:60],
                    "status": event.get("status", "UNAVAILABLE"),
                    "parent_present_native_valid": event.get("parent_present_native_valid"),
                    "parent_absent_at_snapshot": event.get("parent_absent_at_snapshot"),
                    "parent_inspection_errors": event.get("parent_inspection_errors"),
                    "webengine_wrappers_sampled": event.get("webengine_wrappers_sampled"),
                    "native_valid_wrappers": event.get("native_valid_wrappers"),
                    "native_invalid_wrappers": event.get("native_invalid_wrappers"),
                })
            continue
        if kind not in {"worker_start", "worker_stop", "cache_release", "qt_destroy_watch_registered",
                        "qt_destroyed_observed", "qt_worker_started", "qt_worker_finished"}:
            continue
        source = event.get("source")
        target = event.get("target") or ""
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if kind in {"qt_destroy_watch_registered", "qt_destroyed_observed"}:
            token, group = event.get("qt_watch_token"), event.get("_trace_group", 0)
            key = (group, source, token) if (
                isinstance(group, int) and not isinstance(group, bool)
                and 0 <= group < 8 and isinstance(token, str)
                and re.fullmatch(r"qt-destroy-[1-9][0-9]{0,6}", token)
            ) else None
            if kind == "qt_destroy_watch_registered":
                if key is not None and event.get("confidence") == "QT_DESTROYED_SIGNAL_CONNECTED":
                    qt_watch_registered[key] = str(event.get("label", ""))[:100]
                continue
            if key is not None and event.get("confidence") == "QT_DESTROYED_SIGNAL_DELIVERED":
                qt_watch_completed.add(key)
            if event.get("confidence") == "QT_DESTROYED_SIGNAL_DELIVERED":
                destroyed_count += 1
                destroyed_sources.add(source)
            continue
        if kind == "cache_release":
            releases.add(source)
            continue
        if kind in {"qt_worker_started", "qt_worker_finished"}:
            token = event.get("qt_worker_token")
            group = event.get("_trace_group", 0)
            if (not isinstance(token, str) or len(token) > 40
                    or not isinstance(group, int) or isinstance(group, bool) or not 0 <= group < 8
                    or event.get("confidence") != ("QT_STARTED_SIGNAL_DELIVERED" if kind == "qt_worker_started"
                                                   else "QT_FINISHED_SIGNAL_DELIVERED")):
                continue
            worker = (group, source, token)
            if kind == "qt_worker_started":
                qt_started += 1
                qt_pending[worker] = qt_pending.get(worker, 0) + 1
            else:
                qt_finished += 1
                if qt_pending.get(worker, 0):
                    qt_pending[worker] -= 1
                else:
                    qt_unmatched += 1
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
    qt_open = [
        {"source": source, "trace_group": group, "qt_worker_token": token,
         "unpaired_starts": count}
        for (group, source, token), count in sorted(qt_pending.items()) if count > 0
    ]
    qt_unpaired_destroy = [
        {"trace_group": group, "source": source, "qt_watch_token": token,
         "label": label, "destruction_not_observed": True}
        for (group, source, token), label in sorted(qt_watch_registered.items())
        if (group, source, token) not in qt_watch_completed
    ]
    return {
        "status": "REVIEW" if trace.get("truncated") or open_workers or unmatched or qt_open or qt_unmatched or qt_unpaired_destroy else "OBSERVED",
        "qt_worker_started_events": qt_started, "qt_worker_finished_events": qt_finished,
        "qt_worker_unmatched_finished": qt_unmatched,
        "qt_worker_unpaired": qt_open[:80],
        "worker_start_events": started, "worker_stop_events": stopped,
        "unmatched_stop_events": unmatched,
        "worker_starts_unpaired": open_workers[:80],
        "cache_release_sources": sorted(releases)[:80],
        "qt_destroyed_sources": sorted(destroyed_sources)[:80],
        "qt_destroyed_events": destroyed_count,
        "qt_destroy_watches_registered": len(qt_watch_registered),
        "qt_destroy_watches_delivered": len(qt_watch_completed & set(qt_watch_registered)),
        "qt_destroy_watches_pending": qt_unpaired_destroy[:80],
        "qt_destroy_watches_pending_count": len(qt_unpaired_destroy),
        "qt_parent_snapshots": qt_parent_snapshots,
        "parent_is_not_full_ownership_proof": True,
        "truncated": bool(trace.get("truncated") or len(open_workers) > 80 or len(qt_open) > 80
                          or len(qt_unpaired_destroy) > 80 or len(releases) > 80),
        "qt_destroyed_is_not_ownership_proof": True,
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
        payload = observer.report()
        payload["scenario_module"] = module
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return payload
