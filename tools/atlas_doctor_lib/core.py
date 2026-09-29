from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

RUNTIME_RELATIVE = Path('.ai/runtime/atlas_doctor')
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Issue:
    rule: str
    category: str
    severity: str
    confidence: str
    path: str
    line: int | None
    title: str
    evidence: str
    recommendation: str

    @property
    def id(self) -> str:
        raw = f'{self.rule}|{self.path}|{self.line or 0}|{self.title}'.encode('utf-8')
        return hashlib.sha1(raw).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload['id'] = self.id
        return payload


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def project_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / '.git').exists() or (candidate / 'main.py').is_file():
            return candidate
    raise RuntimeError('Impossible de localiser la racine du depot Dofus Atlas.')


def run_git(root: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ['git', *args],
        cwd=root,
        text=True,
        encoding='utf-8',
        errors='replace',
        capture_output=True,
        check=False,
        timeout=30,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or f'git {" ".join(args)} a echoue')
    return completed.stdout.strip()


def git_state(root: Path) -> dict[str, Any]:
    head = run_git(root, 'rev-parse', 'HEAD')
    branch = run_git(root, 'branch', '--show-current', check=False) or '(detached)'
    status = run_git(root, 'status', '--short', '--untracked-files=all', check=False)
    remote = run_git(root, 'remote', 'get-url', 'origin', check=False)
    dirty_digest = hashlib.sha256(status.encode('utf-8')).hexdigest() if status else ''
    return {
        'head': head,
        'branch': branch,
        'remote': remote,
        'dirty': bool(status),
        'dirty_digest': dirty_digest,
        'status_lines': status.splitlines()[:200],
    }


def tracked_files(root: Path) -> list[str]:
    output = run_git(root, 'ls-files', '-z')
    return [item for item in output.split('\0') if item]


def runtime_dir(root: Path) -> Path:
    path = root / RUNTIME_RELATIVE
    path.mkdir(parents=True, exist_ok=True)
    return path


def _json_path(root: Path, name: str) -> Path:
    return runtime_dir(root) / f'{name}.json'


def load_json(root: Path, name: str) -> dict[str, Any] | None:
    path = _json_path(root, name)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def write_json(root: Path, name: str, payload: dict[str, Any], *, rotate: bool = False) -> Path:
    path = _json_path(root, name)
    if rotate and path.exists():
        previous = _json_path(root, f'previous_{name.removeprefix("latest_")}')
        try:
            previous.write_bytes(path.read_bytes())
        except OSError:
            pass
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)
    return path


def cache_matches_git(payload: dict[str, Any] | None, state: dict[str, Any]) -> bool:
    if not payload:
        return False
    cached = payload.get('git') or {}
    return (
        cached.get('head') == state.get('head')
        and cached.get('dirty_digest', '') == state.get('dirty_digest', '')
    )


def severity_counts(issues: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {'CRITICAL': 0, 'HIGH': 0, 'MEDIUM': 0, 'LOW': 0, 'INFO': 0}
    for issue in issues:
        severity = str(issue.get('severity', 'INFO')).upper()
        counts[severity] = counts.get(severity, 0) + 1
    return counts


def verdict_from_counts(counts: dict[str, int]) -> str:
    if counts.get('CRITICAL', 0):
        return 'FAIL'
    if counts.get('HIGH', 0):
        return 'WARN'
    return 'PASS'


def milliseconds(started: float) -> float:
    return round((time.perf_counter() - started) * 1000.0, 3)


def python_executable() -> str:
    return sys.executable or 'python'
