from __future__ import annotations

import builtins
import io
import json
import os
import runpy
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

_ORIGINAL_OPEN = builtins.open
_ORIGINAL_IO_OPEN = io.open
_ORIGINAL_JSON_LOAD = json.load
_ORIGINAL_JSON_LOADS = json.loads
_ORIGINAL_READ_TEXT = Path.read_text

_LOCK = threading.Lock()
_STATS: dict[str, dict[str, float | int]] = defaultdict(lambda: {
    'open_count': 0,
    'open_ms': 0.0,
    'read_calls': 0,
    'read_ms': 0.0,
    'bytes_read': 0,
    'json_calls': 0,
    'json_ms': 0.0,
})


def _norm(value: Any) -> str:
    try:
        return str(Path(value).resolve())
    except Exception:
        return str(value)


def _add(path: str, key: str, value: float | int) -> None:
    with _LOCK:
        _STATS[path][key] = _STATS[path].get(key, 0) + value


class _TrackedFile:
    def __init__(self, wrapped, path: str):
        self._wrapped = wrapped
        self._atlas_path = path

    @property
    def name(self):
        return getattr(self._wrapped, 'name', self._atlas_path)

    def __getattr__(self, name):
        return getattr(self._wrapped, name)

    def __enter__(self):
        self._wrapped.__enter__()
        return self

    def __exit__(self, *args):
        return self._wrapped.__exit__(*args)

    def __iter__(self):
        return self

    def __next__(self):
        started = time.perf_counter()
        value = next(self._wrapped)
        elapsed = (time.perf_counter() - started) * 1000.0
        _add(self._atlas_path, 'read_calls', 1)
        _add(self._atlas_path, 'read_ms', elapsed)
        _add(self._atlas_path, 'bytes_read', len(value) if hasattr(value, '__len__') else 0)
        return value

    def _read(self, method: str, *args, **kwargs):
        started = time.perf_counter()
        value = getattr(self._wrapped, method)(*args, **kwargs)
        elapsed = (time.perf_counter() - started) * 1000.0
        _add(self._atlas_path, 'read_calls', 1)
        _add(self._atlas_path, 'read_ms', elapsed)
        _add(self._atlas_path, 'bytes_read', len(value) if hasattr(value, '__len__') else 0)
        return value

    def read(self, *args, **kwargs):
        return self._read('read', *args, **kwargs)

    def readline(self, *args, **kwargs):
        return self._read('readline', *args, **kwargs)

    def readlines(self, *args, **kwargs):
        return self._read('readlines', *args, **kwargs)


class _SourcedText(str):
    source_path: str


def _wrap_open(original):
    def traced(file, mode='r', *args, **kwargs):
        started = time.perf_counter()
        handle = original(file, mode, *args, **kwargs)
        elapsed = (time.perf_counter() - started) * 1000.0
        if 'r' not in mode and '+' not in mode:
            return handle
        path = _norm(file)
        _add(path, 'open_count', 1)
        _add(path, 'open_ms', elapsed)
        return _TrackedFile(handle, path)
    return traced


def _json_load(fp, *args, **kwargs):
    path = _norm(getattr(fp, 'name', '<json.load>'))
    started = time.perf_counter()
    try:
        return _ORIGINAL_JSON_LOAD(fp, *args, **kwargs)
    finally:
        _add(path, 'json_calls', 1)
        _add(path, 'json_ms', (time.perf_counter() - started) * 1000.0)


def _json_loads(value, *args, **kwargs):
    path = getattr(value, 'source_path', '')
    started = time.perf_counter()
    try:
        return _ORIGINAL_JSON_LOADS(value, *args, **kwargs)
    finally:
        if path:
            _add(path, 'json_calls', 1)
            _add(path, 'json_ms', (time.perf_counter() - started) * 1000.0)


def _read_text(path_obj: Path, *args, **kwargs):
    value = _ORIGINAL_READ_TEXT(path_obj, *args, **kwargs)
    sourced = _SourcedText(value)
    sourced.source_path = _norm(path_obj)
    return sourced


def install() -> None:
    builtins.open = _wrap_open(_ORIGINAL_OPEN)
    io.open = _wrap_open(_ORIGINAL_IO_OPEN)
    json.load = _json_load
    json.loads = _json_loads
    Path.read_text = _read_text


def restore() -> None:
    builtins.open = _ORIGINAL_OPEN
    io.open = _ORIGINAL_IO_OPEN
    json.load = _ORIGINAL_JSON_LOAD
    json.loads = _ORIGINAL_JSON_LOADS
    Path.read_text = _ORIGINAL_READ_TEXT


def save_trace(output: Path) -> None:
    rows = []
    for path, values in _STATS.items():
        row = {'path': path, **values}
        row['total_io_ms'] = round(float(values.get('open_ms', 0.0)) + float(values.get('read_ms', 0.0)), 3)
        row['open_ms'] = round(float(values.get('open_ms', 0.0)), 3)
        row['read_ms'] = round(float(values.get('read_ms', 0.0)), 3)
        row['json_ms'] = round(float(values.get('json_ms', 0.0)), 3)
        rows.append(row)
    rows.sort(key=lambda item: (item['total_io_ms'] + item['json_ms']), reverse=True)
    payload = {
        'schema_version': 1,
        'files': rows,
        'summary': {
            'unique_files': len(rows),
            'open_count': sum(int(item['open_count']) for item in rows),
            'read_calls': sum(int(item['read_calls']) for item in rows),
            'bytes_read': sum(int(item['bytes_read']) for item in rows),
            'open_ms': round(sum(float(item['open_ms']) for item in rows), 3),
            'read_ms': round(sum(float(item['read_ms']) for item in rows), 3),
            'json_ms': round(sum(float(item['json_ms']) for item in rows), 3),
        },
        'slowest': rows[:75],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> int:
    if len(sys.argv) < 2:
        print('Usage: atlas_doctor_io_runner.py <script.py> [args...]', file=sys.stderr)
        return 2
    target = Path(sys.argv[1]).resolve()
    repo_root = next((candidate for candidate in (target.parent, *target.parents) if (candidate / 'main.py').is_file()), None)
    if repo_root is not None and str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    output_value = os.environ.get('ATLAS_DOCTOR_IO_TRACE')
    if not output_value:
        print('ATLAS_DOCTOR_IO_TRACE manquant', file=sys.stderr)
        return 2
    output = Path(output_value)
    sys.argv = [str(target), *sys.argv[2:]]
    exit_code = 0
    install()
    try:
        runpy.run_path(str(target), run_name='__main__')
    except SystemExit as exc:
        value = exc.code
        exit_code = int(value) if isinstance(value, int) else (0 if value is None else 1)
    finally:
        restore()
        save_trace(output)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
