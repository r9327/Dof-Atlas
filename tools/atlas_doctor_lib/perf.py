from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .core import git_state, milliseconds, tracked_files, utc_now, write_json

DATA_EXTENSIONS = {'.json', '.jsonl', '.csv', '.txt', '.yaml', '.yml'}
DATA_PREFIXES = ('data/', 'config/', 'local_dofus_data/')


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 3)


def profile_data_files(root: Path, *, max_file_mb: float = 64.0) -> dict[str, Any]:
    started = time.perf_counter()
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    limit = int(max_file_mb * 1024 * 1024)
    for relative in tracked_files(root):
        if not relative.startswith(DATA_PREFIXES):
            continue
        path = root / relative
        if path.suffix.lower() not in DATA_EXTENSIONS or not path.is_file():
            continue
        try:
            size = path.stat().st_size
        except OSError as exc:
            skipped.append({'path': relative, 'reason': str(exc)})
            continue
        if size > limit:
            skipped.append({'path': relative, 'reason': f'>{max_file_mb:.0f} MiB', 'size_bytes': size})
            continue

        read_started = time.perf_counter()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            skipped.append({'path': relative, 'reason': str(exc)})
            continue
        read_ms = milliseconds(read_started)
        parse_ms = 0.0
        parse_error = ''
        if path.suffix.lower() == '.json':
            parse_started = time.perf_counter()
            try:
                json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                parse_error = str(exc)
            parse_ms = milliseconds(parse_started)
        total_ms = round(read_ms + parse_ms, 3)
        rows.append({
            'path': relative,
            'size_bytes': size,
            'read_ms': read_ms,
            'json_parse_ms': parse_ms,
            'total_ms': total_ms,
            'parse_error': parse_error,
            'throughput_mb_s': round((size / 1024 / 1024) / max(read_ms / 1000.0, 1e-9), 2),
        })

    rows.sort(key=lambda item: item['total_ms'], reverse=True)
    totals = [float(item['total_ms']) for item in rows]
    return {
        'generated_at': utc_now(),
        'duration_ms': milliseconds(started),
        'files_measured': len(rows),
        'files_skipped': len(skipped),
        'total_read_ms': round(sum(float(item['read_ms']) for item in rows), 3),
        'total_json_parse_ms': round(sum(float(item['json_parse_ms']) for item in rows), 3),
        'p50_file_total_ms': _percentile(totals, 0.50),
        'p95_file_total_ms': _percentile(totals, 0.95),
        'slowest': rows[:50],
        'skipped': skipped[:100],
    }


def run_runtime_benchmark(root: Path, *, timeout: int = 180) -> dict[str, Any]:
    benchmark = root / 'app/modules/encyclopedia/tools/benchmark_guides_performance.py'
    runner = root / 'tools/atlas_doctor_io_runner.py'
    if not benchmark.is_file():
        return {'status': 'UNAVAILABLE', 'reason': f'Benchmark canonique absent: {benchmark.relative_to(root)}'}
    if not runner.is_file():
        return {'status': 'UNAVAILABLE', 'reason': 'atlas_doctor_io_runner.py absent'}

    trace_path = root / '.ai/runtime/atlas_doctor/runtime_io_trace.json'
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.unlink(missing_ok=True)
    artifact = root / 'artifacts/quests_guides_performance.json'
    artifact.unlink(missing_ok=True)

    # Run the canonical benchmark without instrumentation first so its timing/RAM
    # remains comparable with historical same-machine baselines.
    clean_command = [sys.executable, '-m', 'app.modules.encyclopedia.tools.benchmark_guides_performance']
    env = os.environ.copy()
    current_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = str(root) + (os.pathsep + current_pythonpath if current_pythonpath else '')
    started = time.perf_counter()
    clean = subprocess.run(
        clean_command,
        cwd=root,
        env=env,
        text=True,
        encoding='utf-8',
        errors='replace',
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    clean_duration_ms = milliseconds(started)
    benchmark_payload: dict[str, Any] | None = None
    if artifact.is_file():
        try:
            benchmark_payload = json.loads(artifact.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            benchmark_payload = None

    # Separate traced run: diagnostic I/O overhead must not contaminate the
    # canonical performance numbers above.
    env['ATLAS_DOCTOR_IO_TRACE'] = str(trace_path)
    trace_command = [sys.executable, '-m', 'tools.atlas_doctor_io_runner', str(benchmark)]
    trace_started = time.perf_counter()
    traced = subprocess.run(
        trace_command,
        cwd=root,
        env=env,
        text=True,
        encoding='utf-8',
        errors='replace',
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    trace_duration_ms = milliseconds(trace_started)
    trace_payload: dict[str, Any] | None = None
    if trace_path.is_file():
        try:
            trace_payload = json.loads(trace_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            trace_payload = None

    clean_ok = clean.returncode == 0 and benchmark_payload is not None
    trace_ok = traced.returncode == 0 and trace_payload is not None
    return {
        'status': 'PASS' if clean_ok else 'FAIL',
        'clean_returncode': clean.returncode,
        'trace_returncode': traced.returncode,
        'duration_ms': round(clean_duration_ms + trace_duration_ms, 3),
        'clean_duration_ms': clean_duration_ms,
        'trace_duration_ms': trace_duration_ms,
        'clean_command': clean_command,
        'trace_command': trace_command,
        'benchmark': benchmark_payload,
        'io_trace_status': 'PASS' if trace_ok else 'FAIL',
        'io_trace': trace_payload,
        'clean_stdout_tail': clean.stdout.splitlines()[-20:],
        'clean_stderr_tail': clean.stderr.splitlines()[-40:],
        'trace_stderr_tail': traced.stderr.splitlines()[-40:],
    }


def run_performance(root: Path, *, include_runtime: bool = True, save: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    payload: dict[str, Any] = {
        'schema_version': 1,
        'kind': 'performance',
        'generated_at': utc_now(),
        'git': git_state(root),
        'file_profile': profile_data_files(root),
    }
    if include_runtime:
        payload['runtime'] = run_runtime_benchmark(root)
    payload['duration_ms'] = milliseconds(started)
    if save:
        write_json(root, 'latest_perf', payload, rotate=True)
    return payload
