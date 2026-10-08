from __future__ import annotations

"""Opt-in bounded Python runtime observations for Doctor; never enabled at startup.

Python calls/imports and process/file side effects are observable. Native Qt
signals, C++ allocations and reference ownership are NOT observable without
explicit test instrumentation or separate platform profilers.
"""
import argparse
import gc
import json
import runpy
import sys
import threading
import time
import weakref
from pathlib import Path
from typing import Any


class RuntimeObserver:
    def __init__(self, root: Path, *, max_events: int = 5000):
        if not 1 <= max_events <= 50000:
            raise ValueError("max_events must be 1..50000")
        self.root = root.resolve()
        self.max_events = max_events
        self.events: list[dict[str, Any]] = []
        self._edges: set[tuple[str, str]] = set()
        self._watched: list[tuple[str, str, weakref.ReferenceType]] = []
        self._overflow = False
        self._active = False
        self._busy = False
        self._old_profile = None
        self._old_thread_profile = None
        self.started_ns = 0

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
        if not self._active or self._busy or event != "call":
            return
        self._busy = True
        try:
            target = self._path(frame.f_code.co_filename)
            caller = self._path(frame.f_back.f_code.co_filename) if frame.f_back else None
            if target and caller and target.endswith(".py") and caller.endswith(".py"):
                key = caller, target
                if key not in self._edges:
                    self._edges.add(key)
                    self._record({"type": "python_call_edge", "source": caller, "target": target})
        finally:
            self._busy = False

    def _audit_event(self, event: str, args: tuple[Any, ...]) -> None:
        if not self._active or self._busy:
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
            try:
                caller = self._path(sys._getframe(1).f_code.co_filename)
            except ValueError:
                caller = None
            if not caller or not caller.endswith(".py"):
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
        if self._active:
            raise RuntimeError("observer already started")
        self.started_ns = time.monotonic_ns()
        self._old_profile = sys.getprofile()
        self._old_thread_profile = threading.getprofile()
        self._active = True
        ref = weakref.ref(self)
        def audit(event: str, args: tuple[Any, ...]) -> None:
            observer = ref()
            if observer is not None:
                observer._audit_event(event, args)
        sys.addaudithook(audit)
        sys.setprofile(self._profile)
        threading.setprofile(self._profile)
        return self

    def __exit__(self, *_errors: Any) -> None:
        self._active = False
        sys.setprofile(self._old_profile)
        threading.setprofile(self._old_thread_profile)

    def report(self, *, collect: bool = False) -> dict[str, Any]:
        if collect:
            gc.collect()
        watched = [{"label": label, "kind": kind, "still_referenced": ref() is not None}
                   for label, kind, ref in self._watched]
        return {
            "schema_version": 1, "kind": "doctor_runtime_observation",
            "root": str(self.root), "duration_ms": round((time.monotonic_ns() - self.started_ns) / 1e6, 3)
            if self.started_ns else 0.0,
            "status": "TRUNCATED" if self._overflow else "RECORDED",
            "events": self.events, "events_captured": len(self.events),
            "truncated": self._overflow, "object_watches": watched,
            "limits": [
                "Opt-in Python tracing only: native Qt/C++ signals and memory ownership not inferred.",
                "Still referenced objects may be intentionally retained; not a proof of a memory leak.",
                "No arguments, variable values or outside-repository paths collected.",
            ],
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
    observed = {(e["source"], e["target"]) for e in trace.get("events", [])
                if e.get("type") == "python_call_edge"}
    return {
        "status": "REVIEW" if trace.get("truncated") else "PASS",
        "observed_runtime_edges": len(observed),
        "static_edges_with_runtime_evidence": len(observed & known),
        "observed_unmapped_edges": [{"source": a, "target": b}
                                    for a, b in sorted(observed - known)[:50]],
        "static_coverage_claim": False,
        "notes": "Observed Python calls are not necessarily static import relationships; no runtime event means unobserved, not unused.",
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
