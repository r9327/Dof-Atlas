"""Attribution-only diagnostics for DOFUS ATLAS performance experiments.

These helpers are deliberately stdlib-only. Profiles are OBSERVATIONS, not
evidence of a root cause unless a second comparable run reproduces it.
"""
from __future__ import annotations

import cProfile
import ctypes
import html
import os
import pstats
import sys
import threading
import time
import tracemalloc
import traceback
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]


def source_path(filename: str) -> str:
    try:
        path = Path(filename).resolve()
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except (ValueError, OSError):
        # Never upload arbitrary user-directory paths from CI/stacks.
        return Path(filename).name


class SpanAttributor:
    """Opt-in method timers, with exclusive time to avoid double-counting."""

    def __init__(self) -> None:
        self.phase = ""
        self.rows: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
        self.local = threading.local()

    @contextmanager
    def instrument(self, klass: type, names: tuple[str, ...]) -> Iterator[None]:
        originals: dict[str, Any] = {}
        for name in names:
            # Only wrap methods truly defined on this class; avoid descriptors.
            original = klass.__dict__.get(name)
            if original is None or not callable(original):
                continue
            originals[name] = original

            def timed(instance: Any, *args: Any, _original=original, _name=name, **kwargs: Any) -> Any:
                phase = self.phase
                if not phase:
                    return _original(instance, *args, **kwargs)
                stack = getattr(self.local, "calls", None)
                if stack is None:
                    stack = []
                    self.local.calls = stack
                entry = {"child_ms": 0.0}
                stack.append(entry)
                started = time.perf_counter()
                try:
                    return _original(instance, *args, **kwargs)
                finally:
                    elapsed = (time.perf_counter() - started) * 1000
                    stack.pop()
                    if stack:
                        stack[-1]["child_ms"] += elapsed
                    key = f"{klass.__module__}.{klass.__name__}.{_name}"
                    group = self.rows[phase].setdefault(
                        key, {"calls": 0.0, "inclusive_ms": 0.0,
                              "self_ms": 0.0, "max_ms": 0.0}
                    )
                    group["calls"] += 1
                    group["inclusive_ms"] += elapsed
                    group["self_ms"] += max(0.0, elapsed - entry["child_ms"])
                    group["max_ms"] = max(group["max_ms"], elapsed)

            setattr(klass, name, timed)
        try:
            yield
        finally:
            for name, original in originals.items():
                setattr(klass, name, original)

    @contextmanager
    def active(self, phase: str) -> Iterator[None]:
        old = self.phase
        self.phase = phase
        try:
            yield
        finally:
            self.phase = old

    def top(self, phase: str, limit: int = 25) -> list[dict[str, Any]]:
        groups = self.rows.get(phase, {})
        return [
            {"method": name, **{k: round(v, 2) for k, v in values.items()}}
            for name, values in sorted(groups.items(),
                                       key=lambda item: item[1]["self_ms"], reverse=True)[:limit]
        ]


class QtStallStackSampler:
    """Read UI Python stack from watchdog thread when Qt heartbeat stops.

    C extensions, OS/GPU thread stalls and the GIL may hide true causes;
    a sampled Python stack is an indicator, never a definitive culprit.
    """

    def __init__(self, *, threshold_ms: int = 150, interval: float = 0.05,
                 max_samples: int = 20) -> None:
        self.threshold_seconds = threshold_ms / 1000
        self.interval = interval
        self.max_samples = max_samples
        self.main_thread_id = threading.main_thread().ident
        self.phase = ""
        self.last_heartbeat = time.perf_counter()
        self.samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_capture = 0.0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._watch, daemon=True,
                                        name="AtlasQtStallWatchdog")
        self._thread.start()

    def begin(self, phase: str) -> None:
        with self._lock:
            self.phase = phase
            self.last_heartbeat = time.perf_counter()
            self._last_capture = 0.0

    def heartbeat(self) -> None:
        with self._lock:
            self.last_heartbeat = time.perf_counter()

    def end(self) -> None:
        with self._lock:
            self.phase = ""

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)

    def get(self, phase: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.samples.get(phase, []))

    def _watch(self) -> None:
        while not self._stop.wait(self.interval):
            now = time.perf_counter()
            with self._lock:
                phase = self.phase
                lag = now - self.last_heartbeat
                capture = (bool(phase) and lag >= self.threshold_seconds and
                           now - self._last_capture >= 0.20 and
                           len(self.samples[phase]) < self.max_samples)
                if capture:
                    self._last_capture = now
            if not capture or self.main_thread_id is None:
                continue
            frame = sys._current_frames().get(self.main_thread_id)
            if frame is None:
                continue
            frames = traceback.extract_stack(frame, limit=35)
            # Preserve order from oldest to newest, bounded and sanitized.
            stack = [
                {"file": source_path(item.filename),
                 "line": item.lineno, "function": item.name}
                for item in frames if "/app/" in item.filename.replace("\\", "/")
                or "/tools/" in item.filename.replace("\\", "/")
                or item.filename.replace("\\", "/").endswith("/main.py")
            ][-18:]
            if not stack:
                continue
            with self._lock:
                if phase == self.phase and len(self.samples[phase]) < self.max_samples:
                    self.samples[phase].append({
                        "qt_unresponsive_ms_at_sample": round(lag * 1000, 1),
                        "stack": stack,
                        "interpretation": "sampled Python UI thread; attribution unconfirmed",
                    })


class TargetedProfile:
    """High-overhead cProfile+Python allocator diff for a targeted replay.

    Must not be silently combined with non-profiled latency percentile samples.
    """

    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled
        self.profiler: cProfile.Profile | None = None
        self.before: tracemalloc.Snapshot | None = None
        self.memory_owned = False
        self.result: dict[str, Any] = {}

    def __enter__(self) -> "TargetedProfile":
        if self.enabled:
            self.profiler = cProfile.Profile()
            self.memory_owned = not tracemalloc.is_tracing()
            if self.memory_owned:
                tracemalloc.start(3)
            self.before = tracemalloc.take_snapshot()
            self.profiler.enable()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.profiler is None:
            return
        self.profiler.disable()
        try:
            current = tracemalloc.take_snapshot()
            diff = current.compare_to(self.before, "lineno") if self.before else []
            self.result["python_allocations_top"] = [
                {"file": source_path(row.traceback[0].filename),
                 "line": row.traceback[0].lineno,
                 "delta_bytes": row.size_diff, "delta_blocks": row.count_diff}
                for row in diff[:25]
            ]
            profile_stats = pstats.Stats(self.profiler)
            top = sorted(profile_stats.stats.items(),
                         key=lambda kv: kv[1][3], reverse=True)[:35]
            self.result["python_functions_top"] = [
                {"file": source_path(func[0]), "line": func[1], "function": func[2],
                 "primitive_calls": values[0], "total_calls": values[1],
                 "self_cpu_sec": round(values[2], 5),
                 "cumulative_cpu_sec": round(values[3], 5)}
                for func, values in top
            ]
            self.result["limitations"] = (
                "cProfile perturbs timing; Python allocations exclude native Qt heaps; "
                "a large cumulative CPU time is not proof of a memory leak"
            )
        finally:
            if self.memory_owned:
                tracemalloc.stop()


def process_io() -> dict[str, int] | None:
    """Process logical I/O bytes; not physical disk throughput."""
    if os.name == "nt":
        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "read_ops", "write_ops", "other_ops", "read_bytes",
                "write_bytes", "other_bytes",
            )]
        kernel = ctypes.windll.kernel32
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.GetProcessIoCounters.argtypes = [ctypes.c_void_p, ctypes.POINTER(IoCounters)]
        kernel.GetProcessIoCounters.restype = ctypes.c_int
        counters = IoCounters()
        if not kernel.GetProcessIoCounters(kernel.GetCurrentProcess(), ctypes.byref(counters)):
            return None
        return {key: int(getattr(counters, key)) for key, _ in counters._fields_}
    proc = Path("/proc/self/io")
    if proc.exists():
        data = dict(line.split(": ", 1) for line in proc.read_text().splitlines() if ": " in line)
        return {"read_bytes": int(data.get("rchar", "0")),
                "write_bytes": int(data.get("wchar", "0"))}
    return None


def io_delta(before: dict[str, int] | None,
             after: dict[str, int] | None) -> dict[str, int] | None:
    if before is None or after is None:
        return None
    return {name: max(0, after[name] - before[name]) for name in before.keys() & after.keys()}


def render_report(payload: dict[str, Any]) -> str:
    """Static HTML without external scripts or leaking any local environment paths."""
    samples = payload.get("samples", [])
    worst = sorted((row for row in samples if row.get("open_ms") is not None),
                   key=lambda row: row["open_ms"], reverse=True)
    failures = [row for row in samples if row.get("status") != "PASS"]

    def cell(value: Any) -> str:
        return html.escape(str(value if value is not None else "—"))

    def table(headers: tuple[str, ...], data: list[tuple[Any, ...]]) -> str:
        head = "".join(f"<th>{cell(col)}</th>" for col in headers)
        rows = "".join("<tr>" + "".join(f"<td>{cell(v)}</td>" for v in row) + "</tr>"
                       for row in data)
        return f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>"

    timings = payload.get("timeline", {})
    timings_table = table(("Phase", "Temps (ms)"), [
        (key, value) for key, value in timings.items()
    ])
    slow_table = table(("Guide", "Cycle", "Ouverture ms", "Lag P99 ms", "Statut"), [
        (r["guide_id"], r["cycle"], r.get("open_ms"),
         (r.get("open_ui") or {}).get("lag_p99_ms"), r.get("status"))
        for r in worst[:40]
    ])
    fail_table = table(("Guide", "Cycle", "Erreur"), [
        (r["guide_id"], r["cycle"], r.get("error", "échec"))
        for r in failures
    ])
    hot = []
    for row in worst[:15]:
        for method in (row.get("method_hotspots") or [])[:10]:
            hot.append((row["guide_id"], row["cycle"], method["method"],
                        method["self_ms"], method["inclusive_ms"], method["calls"]))
    hotspots_table = table(("Guide", "Cycle", "Fonction", "Self ms", "Inclusive ms", "Appels"), hot)
    status = cell(payload.get("status", "UNKNOWN"))
    return ("""<!doctype html><html lang="fr"><meta charset="utf-8">
<title>ATLAS — Diagnostic performance</title>
<style>
body{font:14px system-ui,Segoe UI,sans-serif;max-width:1280px;margin:32px auto;
padding:0 24px;color:#26333d;background:#f5f7fb}
h1,h2{color:#223c57}section{background:white;margin:22px 0;padding:20px;
border:1px solid #dce4ec;border-radius:10px;overflow:auto}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #e3e8ee}
th{background:#eef3f9}small{color:#617080}
</style><h1>ATLAS — Profilage des guides</h1>"""
            + f"<p>Révision : {cell(payload.get('git_head'))} | État : {status}</p>"
            + "<small>Mesure Qt hors écran : ne démontre pas les FPS réels. "
              "Les profils ciblés changent le coût d'exécution ; ils ne sont pas comparables aux latences normales.</small>"
            + f"<section><h2>Chronologie de chargement</h2>{timings_table}</section>"
            + f"<section><h2>Ouvertures les plus lentes</h2>{slow_table}</section>"
            + f"<section><h2>Fonctions chronométrées (non exclusives sauf Self)</h2>{hotspots_table}</section>"
            + f"<section><h2>Erreurs à corriger</h2>{fail_table}</section></html>")
