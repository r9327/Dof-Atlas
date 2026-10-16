from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .core import milliseconds

INTEGRITY_MODES = {'fast', 'critical', 'full', 'deep'}
INTEGRITY_TIMEOUT_SECONDS = {
    'fast': 900,
    'critical': 900,
    'full': 7200,
    'deep': 7200,
}


def _decode_lines(value: str | bytes | None) -> list[str]:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").splitlines()
    return value.splitlines() if isinstance(value, str) else []


def _read_gate_progress(path: Path) -> list[dict[str, str]]:
    try:
        contents = path.read_text(encoding="utf-8")
    except OSError:
        return []
    result: list[dict[str, str]] = []
    for line in contents.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(record, dict)
            and isinstance(record.get("group"), str)
            and record.get("event") in {"STARTED", "FINISHED", "FAILED"}
        ):
            result.append(record)
    return result


def run_integrity_gate(
    root: Path,
    mode: str = 'critical',
    *,
    base_ref: str = 'HEAD',
    timeout: int | None = None,
) -> dict[str, Any]:
    normalized = mode.casefold()
    if normalized not in INTEGRITY_MODES:
        raise ValueError(f'Mode integrity inconnu: {mode}')
    effective_timeout = timeout if timeout is not None else INTEGRITY_TIMEOUT_SECONDS[normalized]
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
    env.setdefault('PYTHONUTF8', '1')
    command = [
        sys.executable,
        '-m',
        'tools.atlas_integrity',
        normalized,
        '--base-ref',
        base_ref,
        '--root',
        str(root),
        '--json',
    ]
    started = time.perf_counter()
    # Keep progress independent of the JSON stdout contract. The last STARTED
    # group remains visible if a child blocks and the outer timeout kills it.
    with tempfile.TemporaryDirectory(prefix="atlas-doctor-integrity-") as scratch:
        progress_path = Path(scratch) / "groups.jsonl"
        env['ATLAS_INTEGRITY_PROGRESS_PATH'] = str(progress_path)
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
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            progress = _read_gate_progress(progress_path)
            started_groups = [item["group"] for item in progress if item.get("event") == "STARTED"]
            finished_groups = {
                item["group"] for item in progress
                if item.get("event") in {"FINISHED", "FAILED"}
            }
            current = next((name for name in reversed(started_groups) if name not in finished_groups), None)
            reason = f'Integrity gate depasse {effective_timeout}s'
            if current:
                reason += f' (groupe bloque: {current})'
            return {
                'status': 'TIMEOUT',
                'mode': normalized.upper(),
                'duration_ms': milliseconds(started),
                'command': command,
                'reason': reason,
                'current_group': current,
                'group_progress': progress[-40:],
                'stdout_tail': _decode_lines(exc.stdout)[-30:],
                'stderr_tail': _decode_lines(exc.stderr)[-30:],
            }
        progress = _read_gate_progress(progress_path)


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
        'group_progress': progress[-40:],
        'stdout_tail': [] if payload is not None else completed.stdout.splitlines()[-40:],
        'stderr_tail': completed.stderr.splitlines()[-40:],
    }
