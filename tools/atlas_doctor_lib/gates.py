from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .core import milliseconds

INTEGRITY_MODES = {'fast', 'critical', 'full', 'deep'}


def run_integrity_gate(root: Path, mode: str = 'critical', *, timeout: int = 900) -> dict[str, Any]:
    normalized = mode.casefold()
    if normalized not in INTEGRITY_MODES:
        raise ValueError(f'Mode integrity inconnu: {mode}')
    integrity = root / 'tools/atlas_integrity.py'
    if not integrity.is_file():
        return {
            'status': 'UNAVAILABLE',
            'mode': normalized.upper(),
            'reason': 'tools/atlas_integrity.py absent',
        }

    env = os.environ.copy()
    current_pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = str(root) + (os.pathsep + current_pythonpath if current_pythonpath else '')
    command = [
        sys.executable,
        '-m',
        'tools.atlas_integrity',
        normalized,
        '--base-ref',
        'HEAD',
        '--root',
        str(root),
        '--json',
    ]
    started = time.perf_counter()
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
            'status': 'TIMEOUT',
            'mode': normalized.upper(),
            'duration_ms': milliseconds(started),
            'command': command,
            'reason': f'Integrity gate depasse {timeout}s',
            'stdout_tail': (exc.stdout or '').splitlines()[-30:] if isinstance(exc.stdout, str) else [],
            'stderr_tail': (exc.stderr or '').splitlines()[-30:] if isinstance(exc.stderr, str) else [],
        }

    payload: dict[str, Any] | None = None
    try:
        decoded = json.loads(completed.stdout)
        if isinstance(decoded, dict):
            payload = decoded
    except json.JSONDecodeError:
        payload = None

    verdict = str((payload or {}).get('verdict', '')).upper()
    status = 'PASS' if completed.returncode == 0 and verdict == 'PASS' else 'FAIL'
    return {
        'status': status,
        'mode': normalized.upper(),
        'duration_ms': milliseconds(started),
        'returncode': completed.returncode,
        'command': command,
        'report': payload,
        'stdout_tail': [] if payload is not None else completed.stdout.splitlines()[-40:],
        'stderr_tail': completed.stderr.splitlines()[-40:],
    }
