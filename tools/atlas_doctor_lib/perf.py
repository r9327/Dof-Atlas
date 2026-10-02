from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .core import (
    git_state,
    load_json,
    milliseconds,
    runtime_dir,
    tracked_files,
    utc_now,
    write_json,
)

DATA_EXTENSIONS = {'.json', '.jsonl', '.csv', '.txt', '.yaml', '.yml'}
DATA_PREFIXES = ('data/', 'config/', 'local_dofus_data/')
DEFAULT_RUNTIME_SAMPLES = 3
RUNTIME_ARTIFACT = Path('artifacts/doctor/perf/runtime.json')


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


def _previous_runtime_benchmark(root: Path) -> dict[str, Any] | None:
    previous = load_json(root, 'latest_perf') or {}
    benchmark = ((previous.get('runtime') or {}).get('benchmark') or {})
    return benchmark if isinstance(benchmark, dict) and benchmark else None


def _runtime_environment(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    current_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = str(root) + (
        os.pathsep + current_pythonpath if current_pythonpath else ''
    )
    env.setdefault('QT_QPA_PLATFORM', 'offscreen')
    env.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu --no-sandbox')
    env.setdefault('QTWEBENGINE_DISABLE_SANDBOX', '1')
    env.setdefault('PYTHONUNBUFFERED', '1')
    env.setdefault('PYTHONUTF8', '1')
    return env


def run_runtime_benchmark(
    root: Path,
    *,
    timeout: int = 180,
    samples: int = DEFAULT_RUNTIME_SAMPLES,
) -> dict[str, Any]:
    """Run canonical UI/RAM samples in isolated processes and aggregate medians."""

    from .runtime_benchmark import aggregate_samples, attach_baseline_comparison

    sample_count = max(1, int(samples))
    sample_dir = runtime_dir(root) / 'perf_samples'
    sample_dir.mkdir(parents=True, exist_ok=True)
    for stale in sample_dir.glob('sample-*.json'):
        stale.unlink(missing_ok=True)

    env = _runtime_environment(root)
    collected: list[dict[str, Any]] = []
    executions: list[dict[str, Any]] = []
    started = time.perf_counter()
    worker = (
        'import sys; from pathlib import Path; '
        'from tools.atlas_doctor_lib.runtime_benchmark import write_sample; '
        'write_sample(Path(sys.argv[1]), Path(sys.argv[2]))'
    )

    for index in range(1, sample_count + 1):
        output_path = sample_dir / f'sample-{index}.json'
        command = [
            sys.executable,
            '-c',
            worker,
            str(root),
            str(output_path),
        ]
        sample_started = time.perf_counter()
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                env=env,
                text=True,
                encoding='utf-8',
                errors='replace',
                capture_output=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                'status': 'FAIL',
                'reason': f'Runtime sample {index}/{sample_count} timed out after {timeout}s.',
                'duration_ms': milliseconds(started),
                'sample_count': len(collected),
                'command': command,
                'stdout_tail': (exc.stdout or '').splitlines()[-20:] if isinstance(exc.stdout, str) else [],
                'stderr_tail': (exc.stderr or '').splitlines()[-40:] if isinstance(exc.stderr, str) else [],
            }

        execution = {
            'sample': index,
            'returncode': completed.returncode,
            'duration_ms': milliseconds(sample_started),
            'stdout_tail': completed.stdout.splitlines()[-10:],
            'stderr_tail': completed.stderr.splitlines()[-20:],
        }
        executions.append(execution)
        if completed.returncode != 0 or not output_path.is_file():
            return {
                'status': 'FAIL',
                'reason': f'Runtime sample {index}/{sample_count} failed.',
                'duration_ms': milliseconds(started),
                'sample_count': len(collected),
                'executions': executions,
                'command': command,
            }
        try:
            sample_payload = json.loads(output_path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                'status': 'FAIL',
                'reason': f'Runtime sample {index}/{sample_count} produced invalid JSON: {exc}',
                'duration_ms': milliseconds(started),
                'sample_count': len(collected),
                'executions': executions,
            }
        collected.append(sample_payload)

    benchmark = aggregate_samples(collected)
    benchmark = attach_baseline_comparison(
        benchmark,
        _previous_runtime_benchmark(root),
    )
    artifact = root / RUNTIME_ARTIFACT
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(benchmark, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    total_duration_ms = milliseconds(started)
    return {
        'status': 'PASS',
        'duration_ms': total_duration_ms,
        'clean_duration_ms': total_duration_ms,
        'trace_duration_ms': 0.0,
        'sample_count': sample_count,
        'executions': executions,
        'benchmark': benchmark,
        'artifact': str(RUNTIME_ARTIFACT).replace('\\', '/'),
        'io_trace_status': 'NOT_RUN',
        'io_trace_reason': 'Runtime performance uses isolated clean samples; use Doctor live for I/O tracing.',
        'io_trace': None,
    }


def run_performance(root: Path, *, include_runtime: bool = True, save: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    payload: dict[str, Any] = {
        'schema_version': 2,
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
